#-------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
#--------------------------------------------------------------------------

# pylint: disable=super-init-not-called,no-self-use

import logging
import time
import datetime
import threading
import certifi
try:
    from urllib import parse as urllib_parse
except ImportError:
    import urllib as urllib_parse  # Py2

from uamqp import Session
from uamqp import utils
from uamqp import constants
from uamqp import errors
from uamqp import c_uamqp


_logger = logging.getLogger(__name__)


class TokenRetryPolicy:
    """Retry policy for sending authentication tokens
    for CBS authentication.

    :param retries: The number of retry attempts for a failed
     PUT token request. The default is 3. This is exclusive of
     the initial attempt.
    :type retries: int
    :param backoff: The time in miliseconds to wait between
     retry attempts.
    :type backoff: int
    """

    def __init__(self, retries=3, backoff=0):
        self.retries = retries
        self.backoff = float(backoff)/1000


class AMQPAuth:
    """AMQP authentication mixin.

    :param hostname: The AMQP endpoint hostname.
    :type hostname: str or bytes
    :param port: The TLS port - default for AMQP is 5671.
    :type port: int
    :param verify: The path to a user-defined certificate.
    :type verify: str
    :param encoding: The encoding to use if hostname is provided as a str.
     Default is 'UTF-8'.
    :type encoding: str
    """

    def __init__(self, hostname, port=constants.DEFAULT_AMQPS_PORT, verify=None, encoding='UTF-8'):
        self._encoding = encoding
        self.hostname = hostname.encode(self._encoding) if isinstance(hostname, str) else hostname
        self.cert_file = verify
        self.sasl = _SASL()
        self.set_tlsio(self.hostname, port)

    def set_tlsio(self, hostname, port):
        """Setup the default underlying TLS IO layer. On Windows this is
        Schannel, on Linux and MacOS this is OpenSSL.

        :param hostname: The endpoint hostname.
        :type hostname: bytes
        :param port: The TLS port.
        :type port: int
        """
        _default_tlsio = c_uamqp.get_default_tlsio()
        _tlsio_config = c_uamqp.TLSIOConfig()
        _tlsio_config.hostname = hostname
        _tlsio_config.port = int(port)
        self._underlying_xio = c_uamqp.xio_from_tlsioconfig(_default_tlsio, _tlsio_config)

        cert = self.cert_file or certifi.where()
        with open(cert, 'rb') as cert_handle:
            cert_data = cert_handle.read()
            self._underlying_xio.set_certificates(cert_data)
        self.sasl_client = _SASLClient(self._underlying_xio, self.sasl)

    def close(self):
        """Close the authentication layer and cleanup
        all the authentication wrapper objects.
        """
        self.sasl.mechanism.destroy()
        self.sasl_client.get_client().destroy()
        self._underlying_xio.destroy()


class SASLPlain(AMQPAuth):
    """SASL Plain AMQP authentication.
    This is SASL authentication using a basic username and password.

    :param hostname: The AMQP endpoint hostname.
    :type hostname: str or bytes
    :param username: The authentication username.
    :type username: bytes or str
    :param password: The authentication password.
    :type password: bytes or str
    :param port: The TLS port - default for AMQP is 5671.
    :type port: int
    :param verify: The path to a user-defined certificate.
    :type verify: str
    :param encoding: The encoding to use if hostname and credentials
     are provided as a str. Default is 'UTF-8'.
    :type encoding: str
    """

    def __init__(self, hostname, username, password, port=constants.DEFAULT_AMQPS_PORT, verify=None, encoding='UTF-8'):
        self._encoding = encoding
        self.hostname = hostname.encode(self._encoding) if isinstance(hostname, str) else hostname
        self.username = username.encode(self._encoding) if isinstance(username, str) else username
        self.password = password.encode(self._encoding) if isinstance(password, str) else password
        self.cert_file = verify
        self.sasl = _SASLPlain(self.username, self.password, encoding=self._encoding)
        self.set_tlsio(self.hostname, port)


class SASLAnonymous(AMQPAuth):
    """SASL Annoymous AMQP authentication mixin.
    SASL connection with no credentials. If intending to use annoymous
    auth to set up a CBS session once connected, use SASTokenAuth
    or the CBSAuthMixin instead.

    :param hostname: The AMQP endpoint hostname.
    :type hostname: str or bytes
    :param port: The TLS port - default for AMQP is 5671.
    :type port: int
    :param verify: The path to a user-defined certificate.
    :type verify: str
    :param encoding: The encoding to use if hostname is provided as a str.
     Default is 'UTF-8'.
    :type encoding: str
    """

    def __init__(self, hostname, port=constants.DEFAULT_AMQPS_PORT, verify=None, encoding='UTF-8'):
        self._encoding = encoding
        self.hostname = hostname.encode(self._encoding) if isinstance(hostname, str) else hostname
        self.cert_file = verify
        self.sasl = _SASLAnonymous()
        self.set_tlsio(self.hostname, port)


class CBSAuthMixin:
    """Mixin to handle sending and refreshing CBS auth tokens."""

    def update_token(self):
        """Update a token that is about to expire. This is specific
        to a particular token type, and therefore must be implemented
        in a child class.
        """
        raise errors.TokenExpired(
            "Unable to refresh token - no refresh logic implemented.")

    def create_authenticator(self, connection, debug=False):
        """Create the AMQP session and the CBS channel with which
        to negotiate the token.

        :param connection: The underlying AMQP connection on which
         to create the session.
        :type connection: ~uamqp.Connection
        :param debug: Whether to emit network trace logging events for the
         CBS session. Default is `False`. Logging events are set at INFO level.
        :type debug: bool
        :returns: ~uamqp.c_uamqp.CBSTokenAuth
        """
        self._lock = threading.Lock()
        self._session = Session(
            connection,
            incoming_window=constants.MAX_FRAME_SIZE_BYTES,
            outgoing_window=constants.MAX_FRAME_SIZE_BYTES)
        try:
            self._cbs_auth = c_uamqp.CBSTokenAuth(
                self.audience,
                self.token_type,
                self.token,
                int(self.expires_at),
                self._session._session,  # pylint: disable=protected-access
                self.timeout)
            self._cbs_auth.set_trace(debug)
        except ValueError:
            raise errors.AMQPConnectionError(
                "Unable to open authentication session. "
                "Please confirm target URI exists.")
        return self._cbs_auth

    def close_authenticator(self):
        """Close the CBS auth channel and session."""
        self._cbs_auth.destroy()
        self._session.destroy()

    def handle_token(self):
        """This function is called periodically to check the status of the current
        token if there is one, and request a new one if needed.
        If the token request fails, it will be retried according to the retry policy.
        A token refresh will be attempted if the token will expire soon.

        This function will return a tuple of two booleans. The first represents whether
        the token authentication has not completed within it's given timeout window. The
        second indicates whether the token negotiation is still in progress.

        :raises: ~uamqp.errors.AuthenticationException if the token authentication fails.
        :raises: ~uamqp.errors.TokenExpired if the token has expired and cannot be
         refreshed.
        :returns: tuple[bool, bool]
        """
        timeout = False
        in_progress = False
        self._lock.acquire()
        try:
            auth_status = self._cbs_auth.get_status()
            auth_status = constants.CBSAuthStatus(auth_status)
            if auth_status == constants.CBSAuthStatus.Error:
                if self.retries >= self._retry_policy.retries:  # pylint: disable=no-member
                    _logger.warning("Authentication Put-Token failed. Retries exhausted.")
                    raise errors.TokenAuthFailure(*self._cbs_auth.get_failure_info())
                else:
                    _logger.info("Authentication Put-Token failed. Retrying.")
                    self.retries += 1  # pylint: disable=no-member
                    time.sleep(self._retry_policy.backoff)
                    self._cbs_auth.authenticate()
                    in_progress = True
            elif auth_status == constants.CBSAuthStatus.Failure:
                errors.AuthenticationException("Failed to open CBS authentication link.")
            elif auth_status == constants.CBSAuthStatus.Expired:
                raise errors.TokenExpired("CBS Authentication Expired.")
            elif auth_status == constants.CBSAuthStatus.Timeout:
                timeout = True
            elif auth_status == constants.CBSAuthStatus.InProgress:
                in_progress = True
            elif auth_status == constants.CBSAuthStatus.RefreshRequired:
                _logger.info("Token will expire soon - attempting to refresh.")
                self.update_token()
                self._cbs_auth.refresh(self.token, int(self.expires_at))
            elif auth_status == constants.CBSAuthStatus.Idle:
                self._cbs_auth.authenticate()
                in_progress = True
            elif auth_status != constants.CBSAuthStatus.Ok:
                raise errors.AuthenticationException("Invalid auth state.")
        except ValueError as e:
            raise errors.AuthenticationException(
                "Token authentication failed: {}".format(e))
        except:
            raise
        finally:
            self._lock.release()
        return timeout, in_progress


class SASTokenAuth(AMQPAuth, CBSAuthMixin):
    """CBS authentication using SAS tokens.

    :param audience: The token audience field. For SAS tokens
     this is usually the URI.
    :type audience: str or bytes
    :param uri: The AMQP endpoint URI. This must be provided as
     a decoded string.
    :type uri: str
    :param token: The SAS token.
    :type token: str or bytes.
    :param expires_in: The total remaining seconds until the token
     expires.
    :type expires_in: ~datetime.timedelta
    :param expires_at: The timestamp at which the SAS token will expire
     formatted as seconds since epoch.
    :type expires_at: float
    :param username: The SAS token username, also referred to as the key
     name or policy name. This can optionally be encoded into the URI.
    :type username: str
    :param password: The SAS token password, also referred to as the key.
     This can optionally be encoded into the URI.
    :type password: str
    :param port: The TLS port - default for AMQP is 5671.
    :type port: int
    :param timeout: The timeout in seconds in which to negotiate the token.
     The default value is 10 seconds.
    :type timeout: int
    :param retry_policy: The retry policy for the PUT token request. The default
     retry policy has 3 retries.
    :type retry_policy: ~uamqp.authentication.TokenRetryPolicy
    :param verify: The path to a user-defined certificate.
    :type verify: str
    :param token_type: The type field of the token request.
     Default value is `b"servicebus.windows.net:sastoken"`.
    :type token_type: bytes
    :param encoding: The encoding to use if hostname is provided as a str.
     Default is 'UTF-8'.
    :type encoding: str
    """

    def __init__(self, audience, uri, token,
                 expires_in=None,
                 expires_at=None,
                 username=None,
                 password=None,
                 port=constants.DEFAULT_AMQPS_PORT,
                 timeout=10,
                 retry_policy=TokenRetryPolicy(),
                 verify=None,
                 token_type=b"servicebus.windows.net:sastoken",
                 encoding='UTF-8'):  # pylint: disable=no-member
        self._retry_policy = retry_policy
        self._encoding = encoding
        self.uri = uri
        parsed = urllib_parse.urlparse(uri)  # pylint: disable=no-member

        self.cert_file = verify
        self.hostname = parsed.hostname.encode(self._encoding)
        self.username = urllib_parse.unquote_plus(parsed.username) if parsed.username else None  # pylint: disable=no-member
        self.password = urllib_parse.unquote_plus(parsed.password) if parsed.password else None  # pylint: disable=no-member

        self.username = username or self.username
        self.password = password or self.password
        self.audience = audience if isinstance(audience, bytes) else audience.encode(self._encoding)
        self.token_type = token_type if isinstance(token_type, bytes) else token_type.encode(self._encoding)
        self.token = token if isinstance(token, bytes) else token.encode(self._encoding)
        if not expires_at and not expires_in:
            raise ValueError("Must specify either 'expires_at' or 'expires_in'.")
        elif not expires_at:
            self.expires_in = expires_in
            self.expires_at = time.time() + expires_in.seconds
        else:
            self.expires_at = expires_at
            expires_in = expires_at - time.time()
            if expires_in < 1:
                raise ValueError("Token has already expired.")
            self.expires_in = datetime.timedelta(seconds=expires_in)
        self.timeout = timeout
        self.retries = 0
        self.sasl = _SASL()
        self.set_tlsio(self.hostname, port)

    def update_token(self):
        """If a username and password are present - attempt to use them to
        request a fresh SAS token.
        """
        if not self.username or not self.password:
            raise errors.TokenExpired("Unable to refresh token - no username or password.")
        encoded_uri = urllib_parse.quote_plus(self.uri).encode(self._encoding)  # pylint: disable=no-member
        encoded_key = urllib_parse.quote_plus(self.username).encode(self._encoding)  # pylint: disable=no-member
        self.expires_at = time.time() + self.expires_in.seconds
        self.token = utils.create_sas_token(
            encoded_key,
            self.password.encode(self._encoding),
            encoded_uri,
            self.expires_in)

    @classmethod
    def from_shared_access_key(
            cls,
            uri,
            key_name,
            shared_access_key,
            expiry=None,
            port=constants.DEFAULT_AMQPS_PORT,
            timeout=10,
            retry_policy=TokenRetryPolicy(),
            verify=None,
            encoding='UTF-8'):
        """Attempt to create a CBS token session using a Shared Access Key such
        as is used to connect to Azure services.

        :param uri: The AMQP endpoint URI. This must be provided as
        a decoded string.
        :type uri: str
        :param key_name: The SAS token username, also referred to as the key
        name or policy name.
        :type key_name: str
        :param shared_access_key: The SAS token password, also referred to as the key.
        :type shared_access_key: str
        :param expiry: The lifetime in seconds for the generated token. Default is 1 hour.
        :type expiry: int
        :param port: The TLS port - default for AMQP is 5671.
        :type port: int
        :param timeout: The timeout in seconds in which to negotiate the token.
         The default value is 10 seconds.
        :type timeout: int
        :param retry_policy: The retry policy for the PUT token request. The default
        retry policy has 3 retries.
        :type retry_policy: ~uamqp.authentication.TokenRetryPolicy
        :param verify: The path to a user-defined certificate.
        :type verify: str
        :param encoding: The encoding to use if hostname is provided as a str.
        Default is 'UTF-8'.
        :type encoding: str
        """
        expires_in = datetime.timedelta(seconds=expiry or constants.AUTH_EXPIRATION_SECS)
        encoded_uri = urllib_parse.quote_plus(uri).encode(encoding)  # pylint: disable=no-member
        encoded_key = urllib_parse.quote_plus(key_name).encode(encoding)  # pylint: disable=no-member
        expires_at = time.time() + expires_in.seconds
        token = utils.create_sas_token(
            encoded_key,
            shared_access_key.encode(encoding),
            encoded_uri,
            expires_in)
        return cls(
            uri, uri, token,
            expires_in=expires_in,
            expires_at=expires_at,
            username=key_name,
            password=shared_access_key,
            port=port,
            timeout=timeout,
            retry_policy=retry_policy,
            verify=verify,
            encoding=encoding)


class _SASLClient:

    def __init__(self, tls_io, sasl):
        self._tls_io = tls_io
        self._sasl_mechanism = sasl.mechanism
        self._io_config = c_uamqp.SASLClientIOConfig()
        self._io_config.underlying_io = self._tls_io
        self._io_config.sasl_mechanism = self._sasl_mechanism
        self._xio = c_uamqp.xio_from_saslioconfig(self._io_config)

    def get_client(self):
        return self._xio


class _SASL:

    def __init__(self):
        self._interface = self._get_interface()
        self.mechanism = self._get_mechanism()

    def _get_interface(self):
        return None

    def _get_mechanism(self):
        return c_uamqp.get_sasl_mechanism()


class _SASLAnonymous(_SASL):

    def _get_interface(self):
        return c_uamqp.saslanonymous_get_interface()

    def _get_mechanism(self):
        return c_uamqp.get_sasl_mechanism(self._interface)


class _SASLPlain(_SASL):

    def __init__(self, authcid, passwd, authzid=None, encoding='UTF-8'):
        self._sasl_config = c_uamqp.SASLPlainConfig()
        self._sasl_config.authcid = authcid
        self._sasl_config.passwd = passwd
        if authzid:
            self._sasl_config.authzid = authzid.encode(encoding) if isinstance(authzid, str) else authzid
        super(_SASLPlain, self).__init__()

    def _get_interface(self):
        return c_uamqp.saslplain_get_interface()

    def _get_mechanism(self):
        return c_uamqp.get_plain_sasl_mechanism(self._interface, self._sasl_config)
