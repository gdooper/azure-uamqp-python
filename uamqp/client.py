#-------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
#--------------------------------------------------------------------------

import logging
import uuid
import queue
try:
    from urllib import unquote_plus
except ImportError:
    from urllib.parse import unquote_plus

import uamqp
from uamqp import authentication
from uamqp import constants
from uamqp import sender
from uamqp import receiver
from uamqp import address
from uamqp import errors
from uamqp import c_uamqp
from uamqp import Connection
from uamqp import Session


_logger = logging.getLogger(__name__)


class AMQPClient:
    """An AMQP client.

    :param remote_address: The AMQP endpoint to connect to. This could be a send target
     or a receive source.
    :type remote_address: str, bytes or ~uamqp.address.Address
    :param auth: Authentication for the connection. If none is provided SASL Annoymous
     authentication will be used.
    :type auth: ~uamqp.authentication.AMQPAuth
    :param client_name: The name for the client, also known as the Container ID.
     If no name is provided, a random GUID will be used.
    :type client_name: str or bytes
    :param debug: Whether to turn on network trace logs. If `True`, trace logs
     will be logged at INFO level. Default is `False`.
    :type debug: bool
    :param max_frame_size: Maximum AMQP frame size. Default is 63488 bytes.
    :type max_frame_size: int
    :param channel_max: Maximum number of Session channels in the Connection.
    :type channel_max: int
    :param idle_timeout: Timeout in milliseconds after which the Connection will close
     if there is no further activity.
    :type idle_timeout: int
    :param properties: Connection properties.
    :type properties: dict
    :param remote_idle_timeout_empty_frame_send_ratio: Ratio of empty frames to
     idle time for Connections with no activity. Value must be between
     0.0 and 1.0 inclusive. Default is 0.5.
    :type remote_idle_timeout_empty_frame_send_ratio: float
    :param incoming_window: The size of the allowed window for incoming messages.
    :type incoming_window: int
    :param outgoing_window: The size of the allowed window for outgoing messages.
    :type outgoing_window: int
    :param handle_max: The maximum number of concurrent link handles.
    :type handle_max: int
    :param encoding: The encoding to use for parameters supplied as strings.
     Default is 'UTF-8'
    :type encoding: str
    """

    def __init__(self, remote_address, auth=None, client_name=None, debug=False, **kwargs):
        self._remote_address = remote_address if isinstance(remote_address, address.Address) \
            else address.Address(remote_address)
        self._hostname = self._remote_address.parsed_address.hostname
        if not auth:
            username = self._remote_address.parsed_address.username
            password = self._remote_address.parsed_address.password
            if username and password:
                username = unquote_plus(username)
                password = unquote_plus(password)
                auth = authentication.SASLPlain(self._hostname, username, password)

        self._auth = auth if auth else authentication.SASLAnonymous(self._hostname)
        self._name = client_name if client_name else str(uuid.uuid4())
        self._debug_trace = debug
        self._counter = c_uamqp.TickCounter()
        self._shutdown = False
        self._connection = None
        self._ext_connection = False
        self._session = None
        self._encoding = kwargs.pop('encoding', None) or 'UTF-8'

        # Connection settings
        self._max_frame_size = kwargs.pop('max_frame_size', None) or constants.MAX_FRAME_SIZE_BYTES
        self._channel_max = kwargs.pop('channel_max', None)
        self._idle_timeout = kwargs.pop('idle_timeout', None)
        self._properties = kwargs.pop('properties', None)
        self._remote_idle_timeout_empty_frame_send_ratio = kwargs.pop(
            'remote_idle_timeout_empty_frame_send_ratio', None)

        # Session settings
        self._outgoing_window = kwargs.pop('outgoing_window', None) or constants.MAX_FRAME_SIZE_BYTES
        self._incoming_window = kwargs.pop('incoming_window', None) or constants.MAX_FRAME_SIZE_BYTES
        self._handle_max = kwargs.pop('handle_max', None)

        # AMQP object settings
        self.connection_type = Connection
        self.session_type = Session

        if kwargs:
            raise ValueError("Received unrecognized kwargs: {}".format(", ".join(kwargs.keys())))

    def __enter__(self):
        """Run Client in a context manager."""
        self.open()
        return self

    def __exit__(self, *args):
        """Close and destroy Client on exiting a context manager."""
        self.close()

    def _client_ready(self):  # pylint: disable=no-self-use
        """Determine whether the client is ready to start sending and/or
        receiving messages. To be ready, the connection must be open and
        authentication complete.
        :returns: bool
        """
        return True

    def _client_run(self):
        """Perform a single Connection iteration."""
        self._connection.work()

    def open(self, connection=None):
        """Open the client. The client can create a new Connection
        or an existing Connection can be passed in. This existing Connection
        may have an existing CBS authentication Session, which will be
        used for this client as well. Otherwise a new Session will be
        created.

        :param connection: An existing Connection that may be shared between
         multiple clients.
        :type connetion: ~uamqp.Connection
        """
        # pylint: disable=protected-access
        if self._session:
            return  # already open.
        _logger.debug("Opening client connection.")
        if connection:
            _logger.debug("Using existing connection.")
            self._auth = connection.auth
            self._ext_connection = True
        self._connection = connection or self.connection_type(
            self._hostname,
            self._auth,
            container_id=self._name,
            max_frame_size=self._max_frame_size,
            channel_max=self._channel_max,
            idle_timeout=self._idle_timeout,
            properties=self._properties,
            remote_idle_timeout_empty_frame_send_ratio=self._remote_idle_timeout_empty_frame_send_ratio,
            debug=self._debug_trace,
            encoding=self._encoding)
        if not self._connection.cbs and isinstance(self._auth, authentication.CBSAuthMixin):
            self._connection.cbs = self._auth.create_authenticator(
                self._connection,
                debug=self._debug_trace)
            self._session = self._auth._session
        elif self._connection.cbs:
            self._session = self._auth._session
        else:
            self._session = self.session_type(
                self._connection,
                incoming_window=self._incoming_window,
                outgoing_window=self._outgoing_window,
                handle_max=self._handle_max)

    def close(self):
        """Close the client. This includes closing the Session
        and CBS authentication layer as well as the Connection.
        If the client was opened using an external Connection,
        this will be left intact.
        """
        if not self._session:
            return  # already closed.
        else:
            if self._connection.cbs and not self._ext_connection:
                _logger.debug("Closing CBS session.")
                self._auth.close_authenticator()
                self._connection.cbs = None
            elif not self._connection.cbs:
                _logger.debug("Closing non-CBS session.")
                self._session.destroy()
            else:
                _logger.debug("Not closing CBS session.")
            self._session = None
            if not self._ext_connection:
                _logger.debug("Closing unshared connection.")
                self._connection.destroy()
            else:
                _logger.debug("Shared connection remaining open.")
            self._connection = None

    def mgmt_request(self, message, operation, op_type=None, node=None, **kwargs):
        """Run a request/response operation. These are frequently used for management
        tasks against a $management node, however any node name can be specified
        and the available options will depend on the target service.

        :param message: The message to send in the management request.
        :type message: ~uamqp.Message
        :param operation: The type of operation to be performed. This value will
         be service-specific, but common values incluse READ, CREATE and UPDATE.
         This value will be added as an application property on the message.
        :type operation: bytes
        :param op_type: The type on which to carry out the operation. This will
         be specific to the entities of the service. This value will be added as
         an application property on the message.
        :type op_type: bytes
        :param node: The target node. Default is `b"$management"`.
        :type node: bytes
        :param timeout: Provide an optional timeout in milliseconds within which a response
         to the management request must be received.
        :type timeout: int
        :param status_code_field: Provide an alternate name for the status code in the
         response body which can vary between services due to the spec still being in draft.
         The default is `b"statusCode"`.
        :type status_code_field: bytes
        :param description_fields: Provide an alternate name for the description in the
         response body which can vary between services due to the spec still being in draft.
         The default is `b"statusDescription"`.
        :type description_fields: bytes
        :returns: ~uamqp.Message
        """
        timeout = False
        auth_in_progress = False
        while True:
            if self._connection.cbs:
                timeout, auth_in_progress = self._auth.handle_token()
            if timeout:
                raise TimeoutError("Authorization timeout.")
            elif auth_in_progress:
                self._connection.work()
            else:
                break
        if not self._session:
            raise ValueError("Session not yet open")
        response = self._session.mgmt_request(
            message,
            operation,
            op_type=op_type,
            node=node,
            encoding=self._encoding,
            debug=self._debug_trace,
            **kwargs)
        return response

    def do_work(self):
        """Run a single connection iteration.
        This will return `True` if the connection is still open
        and ready to be used for further work, or `False` if it needs
        to be shut down.

        :returns: bool
        :raises: TimeoutError if CBS authentication timeout reached.
        """
        timeout = False
        auth_in_progress = False
        if self._connection.cbs:
            timeout, auth_in_progress = self._auth.handle_token()
        if self._shutdown:
            return False
        if timeout:
            raise TimeoutError("Authorization timeout.")
        elif auth_in_progress:
            self._connection.work()
            return True
        elif not self._client_ready():
            self._connection.work()
            return True
        else:
            result = self._client_run()
            return result


class SendClient(AMQPClient):
    """An AMQP client for sending messages.

    :param target: The target AMQP service endpoint. This can either be the URI as
     a string or a ~uamqp.Target object.
    :type target: str, bytes or ~uamqp.Target
    :param auth: Authentication for the connection. If none is provided SASL Annoymous
     authentication will be used.
    :type auth: ~uamqp.authentication.AMQPAuth
    :param client_name: The name for the client, also known as the Container ID.
     If no name is provided, a random GUID will be used.
    :type client_name: str or bytes
    :param debug: Whether to turn on network trace logs. If `True`, trace logs
     will be logged at INFO level. Default is `False`.
    :type debug: bool
    :param msg_timeout: A timeout in seconds for messages from when they have been
     added to the send queue to when the message is actually sent. This prevents potentially
     expired data from being sent. If set to 0, messages will not expire. Default is 0.
    :type msg_timeout: int
    :param send_settle_mode: The mode by which to settle message send
     operations. If set to `Unsettled`, the client will wait for a confirmation
     from the service that the message was successfully sent. If set to 'Settled',
     the client will not wait for confirmation and assume success.
    :type send_settle_mode: ~uamqp.constants.SenderSettleMode
    :param max_message_size: The maximum allowed message size negotiated for the Link.
    :type max_message_size: int
    :param link_properties: Data to be sent in the Link ATTACH frame.
    :type link_properties: dict
    :param link_credit: The sender Link credit that determines how many
     messages the Link will attempt to handle per connection iteration.
    :type link_credit: int
    :param max_frame_size: Maximum AMQP frame size. Default is 63488 bytes.
    :type max_frame_size: int
    :param channel_max: Maximum number of Session channels in the Connection.
    :type channel_max: int
    :param idle_timeout: Timeout in milliseconds after which the Connection will close
     if there is no further activity.
    :type idle_timeout: int
    :param properties: Connection properties.
    :type properties: dict
    :param remote_idle_timeout_empty_frame_send_ratio: Ratio of empty frames to
     idle time for Connections with no activity. Value must be between
     0.0 and 1.0 inclusive. Default is 0.5.
    :type remote_idle_timeout_empty_frame_send_ratio: float
    :param incoming_window: The size of the allowed window for incoming messages.
    :type incoming_window: int
    :param outgoing_window: The size of the allowed window for outgoing messages.
    :type outgoing_window: int
    :param handle_max: The maximum number of concurrent link handles.
    :type handle_max: int
    :param encoding: The encoding to use for parameters supplied as strings.
     Default is 'UTF-8'
    :type encoding: str
    """

    def __init__(self, target, auth=None, client_name=None, debug=False, msg_timeout=0, **kwargs):
        target = target if isinstance(target, address.Address) else address.Target(target)
        self._msg_timeout = msg_timeout
        self._pending_messages = []
        self._message_sender = None
        self._shutdown = None

        # Sender and Link settings
        self._send_settle_mode = kwargs.pop('send_settle_mode', None) or constants.SenderSettleMode.Unsettled
        self._max_message_size = kwargs.pop('max_message_size', None) or constants.MAX_MESSAGE_LENGTH_BYTES
        self._link_properties = kwargs.pop('link_properties', None)
        self._link_credit = kwargs.pop('link_credit', None)

        # AMQP object settings
        self.sender_type = sender.MessageSender

        super(SendClient, self).__init__(target, auth=auth, client_name=client_name, debug=debug, **kwargs)

    def _client_ready(self):
        """Determine whether the client is ready to start sending messages.
        To be ready, the connection must be open and authentication complete,
        The Session, Link and MessageSender must be open and in non-errored
        states.
        :returns: bool
        :raises: ~uamqp.errors.AMQPConnectionError if the MessageSender
         goes into an error state.
        """
        # pylint: disable=protected-access
        if not self._message_sender:
            self._message_sender = self.sender_type(
                self._session, self._name, self._remote_address,
                name='sender-link-{}'.format(uuid.uuid4()),
                debug=self._debug_trace,
                send_settle_mode=self._send_settle_mode,
                max_message_size=self._max_message_size,
                link_credit=self._link_credit,
                properties=self._link_properties,
                encoding=self._encoding)
            self._message_sender.open()
            return False
        elif self._message_sender._state == constants.MessageSenderState.Error:
            raise errors.AMQPConnectionError(
                "Message Sender Client was unable to open. "
                "Please confirm credentials and access permissions."
                "\nSee debug trace for more details.")
        elif self._message_sender._state != constants.MessageSenderState.Open:
            return False
        return True

    def _client_run(self):
        """MessageSender Link is now open - perform message send
        on all pending messages.
        Will return True if operation successful and client can remain open for
        further work.
        :returns: bool
        """
        # pylint: disable=protected-access
        for message in self._pending_messages[:]:
            if message.state in [constants.MessageState.Complete, constants.MessageState.Failed]:
                try:
                    self._pending_messages.remove(message)
                except ValueError:
                    pass
            elif message.state == constants.MessageState.WaitingToBeSent:
                message.state = constants.MessageState.WaitingForAck
                try:
                    current_time = self._counter.get_current_ms()
                    elapsed_time = (current_time - message.idle_time)/1000
                    if self._msg_timeout > 0 and elapsed_time > self._msg_timeout:
                        message._on_message_sent(constants.MessageSendResult.Timeout)
                    else:
                        timeout = self._msg_timeout - elapsed_time if self._msg_timeout > 0 else 0
                        self._message_sender.send_async(message, timeout=timeout)
                except Exception as exp:  # pylint: disable=broad-except
                    message._on_message_sent(constants.MessageSendResult.Error, error=exp)
        self._connection.work()
        return True

    def close(self):
        """Close down the client. No further messages
        can be sent and the client cannot be re-opened.

        All pending, unsent messages will be cleared.
        """
        if self._message_sender:
            self._message_sender.destroy()
            self._message_sender = None
        super(SendClient, self).close()
        self._pending_messages = []

    def queue_message(self, messages):
        """Add a message to the send queue.
        No further action will be taken until either SendClient.wait()
        or SendClient.send_all_messages() has been called.
        The client does not need to be open yet for messages to be added
        to the queue.

        :param messages: A message to send. This can either be a single instance
         of ~uamqp.Message, or multiple messages wrapped in an instance
         of ~uamqp.BatchMessage.
        :type message: ~uamqp.Message
        """
        for message in messages.gather():
            message.idle_time = self._counter.get_current_ms()
            self._pending_messages.append(message)

    def send_message(self, messages, close_on_done=False):
        """Send a single message or batched message.

        :param messages: A message to send. This can either be a single instance
         of ~uamqp.Message, or multiple messages wrapped in an instance
         of ~uamqp.BatchMessage.
        :type message: ~uamqp.Message
        :param close_on_done: Close the client once the message is sent. Default is `False`.
        :type close_on_done: bool
        :raises: ~uamqp.errors.MessageSendFailed if message fails to send after retry policy
         is exhausted.
        """
        batch = messages.gather()
        pending_batch = []
        for message in batch:
            message.idle_time = self._counter.get_current_ms()
            self._pending_messages.append(message)
            pending_batch.append(message)
        self.open()
        try:
            while any([m for m in pending_batch if m.state not in constants.DONE_STATES]):
                self.do_work()
        except:
            raise
        else:
            failed = [m for m in pending_batch if m.state == constants.MessageState.Failed]
            if any(failed):
                raise errors.MessageSendFailed("Failed to send message.")
        finally:
            if close_on_done:
                self.close()

    def messages_pending(self):
        """Check whether the client is holding any unsent
        messages in the queue.
        :returns: bool
        """
        return bool(self._pending_messages)

    def wait(self):
        """Run the client until all pending message in the queue
        have been processed.
        """
        while self.messages_pending():
            self.do_work()

    def send_all_messages(self, close_on_done=True):
        """Send all pending messages in the queue. This will return a list
        of the send result of all the pending messages so it can be
        determined if any messages failed to send.
        This function will open the client if it is not already open.

        :param close_on_done: Close the client once the messages are sent.
         Default is `True`.
        :type close_on_done: bool
        :returns: list[~uamqp.constants.MessageState]
        """
        self.open()
        try:
            messages = self._pending_messages[:]
            self.wait()
        except:
            raise
        else:
            results = [m.state for m in messages]
            return results
        finally:
            if close_on_done:
                self.close()


class ReceiveClient(AMQPClient):
    """An AMQP client for receiving messages.

    :param target: The source AMQP service endpoint. This can either be the URI as
     a string or a ~uamqp.Source object.
    :type target: str, bytes or ~uamqp.Source
    :param auth: Authentication for the connection. If none is provided SASL Annoymous
     authentication will be used.
    :type auth: ~uamqp.authentication.AMQPAuth
    :param client_name: The name for the client, also known as the Container ID.
     If no name is provided, a random GUID will be used.
    :type client_name: str or bytes
    :param debug: Whether to turn on network trace logs. If `True`, trace logs
     will be logged at INFO level. Default is `False`.
    :type debug: bool
    :param timeout: A timeout in milliseconds. The receiver will shut down if no
     new messages are received after the specified timeout. If set to 0, the receiver
     will never timeout and will continue to listen. The default is 0.
    :type timeout: int
    :param receive_settle_mode: The mode by which to settle message receive
     operations. If set to `PeekLock`, the receiver will lock a message once received until
     the client accepts or rejects the message. If set to `ReceiveAndDelete`, the service
     will assume successful receipt of the message and clear it from the queue. The
     default is `PeekLock`.
    :type receive_settle_mode: ~uamqp.constants.ReceiverSettleMode
    :param max_message_size: The maximum allowed message size negotiated for the Link.
    :type max_message_size: int
    :param link_properties: Data to be sent in the Link ATTACH frame.
    :type link_properties: dict
    :param prefetch: The receiver Link credit that determines how many
     messages the Link will attempt to handle per connection iteration.
     The default is 300.
    :type prefetch: int
    :param max_frame_size: Maximum AMQP frame size. Default is 63488 bytes.
    :type max_frame_size: int
    :param channel_max: Maximum number of Session channels in the Connection.
    :type channel_max: int
    :param idle_timeout: Timeout in milliseconds after which the Connection will close
     if there is no further activity.
    :type idle_timeout: int
    :param properties: Connection properties.
    :type properties: dict
    :param remote_idle_timeout_empty_frame_send_ratio: Ratio of empty frames to
     idle time for Connections with no activity. Value must be between
     0.0 and 1.0 inclusive. Default is 0.5.
    :type remote_idle_timeout_empty_frame_send_ratio: float
    :param incoming_window: The size of the allowed window for incoming messages.
    :type incoming_window: int
    :param outgoing_window: The size of the allowed window for outgoing messages.
    :type outgoing_window: int
    :param handle_max: The maximum number of concurrent link handles.
    :type handle_max: int
    :param encoding: The encoding to use for parameters supplied as strings.
     Default is 'UTF-8'
    :type encoding: str
    """

    def __init__(self, source, auth=None, client_name=None, debug=False, timeout=0, **kwargs):
        source = source if isinstance(source, address.Address) else address.Source(source)
        self._timeout = timeout
        self._message_receiver = None
        self._last_activity_timestamp = None
        self._was_message_received = False
        self._message_received_callback = None
        self._received_messages = None

        # Receiver and Link settings
        self._receive_settle_mode = kwargs.pop('receive_settle_mode', None) or constants.ReceiverSettleMode.PeekLock
        self._max_message_size = kwargs.pop('max_message_size', None) or constants.MAX_MESSAGE_LENGTH_BYTES
        self._prefetch = kwargs.pop('prefetch', None) or 300
        self._link_properties = kwargs.pop('link_properties', None)

        # AMQP object settings
        self.receiver_type = receiver.MessageReceiver

        super(ReceiveClient, self).__init__(source, auth=auth, client_name=client_name, debug=debug, **kwargs)

    def _client_ready(self):
        """Determine whether the client is ready to start receiving messages.
        To be ready, the connection must be open and authentication complete,
        The Session, Link and MessageReceiver must be open and in non-errored
        states.
        :returns: bool
        :raises: ~uamqp.errors.AMQPConnectionError if the MessageReceiver
         goes into an error state.
        """
        # pylint: disable=protected-access
        if not self._message_receiver:
            self._message_receiver = self.receiver_type(
                self._session, self._remote_address, self._name,
                on_message_received=self,
                name='receiver-link-{}'.format(uuid.uuid4()),
                debug=self._debug_trace,
                receive_settle_mode=self._receive_settle_mode,
                prefetch=self._prefetch,
                max_message_size=self._max_message_size,
                properties=self._link_properties,
                encoding=self._encoding)
            self._message_receiver.open()
            return False
        elif self._message_receiver._state == constants.MessageReceiverState.Error:
            raise errors.AMQPConnectionError(
                "Message Receiver Client was unable to open. "
                "Please confirm credentials and access permissions."
                "\nSee debug trace for more details.")
        elif self._message_receiver._state != constants.MessageReceiverState.Open:
            self._last_activity_timestamp = self._counter.get_current_ms()
            return False
        return True

    def _client_run(self):
        """MessageReceiver Link is now open - start receiving messages.
        Will return True if operation successful and client can remain open for
        further work.
        :returns: bool
        """
        self._connection.work()
        if self._timeout > 0:
            now = self._counter.get_current_ms()
            if self._last_activity_timestamp and not self._was_message_received:
                timespan = now - self._last_activity_timestamp
                if timespan >= self._timeout:
                    _logger.info("Timeout reached, closing receiver.")
                    self._shutdown = True
            else:
                self._last_activity_timestamp = now
        self._was_message_received = False
        return True

    def _message_generator(self):
        """Iterate over processed messages in the receive queue.
        :returns: generator[~uamqp.Message]
        """
        self.open()
        receiving = True
        try:
            while receiving:
                while receiving and self._received_messages.empty():
                    receiving = self.do_work()
                while not self._received_messages.empty():
                    message = self._received_messages.get()
                    self._received_messages.task_done()
                    yield message
        except:
            raise
        finally:
            self.close()

    def _message_received(self, message):
        """Callback run on receipt of every message. If there is
        a user-defined callback, this will be called.
        Additionally if the client is retrieving messages for a batch
        or iterator, the message will be added to an internal queue.
        :param message: c_uamqp.Message
        """
        self._was_message_received = True
        wrapped_message = uamqp.Message(message=message, encoding=self._encoding)
        if self._message_received_callback:
            wrapped_message = self._message_received_callback(wrapped_message) or wrapped_message
        if self._received_messages:
            self._received_messages.put(wrapped_message)

    def receive_message_batch(self, max_batch_size=None, on_message_received=None, timeout=0):
        """Receive a batch of messages. Messages returned in the batch have already been
        accepted - if you wish to add logic to accept or reject messages based on custom
        criteria, pass in a callback. This method will return as soon as some messages are
        available rather than waiting to achieve a specific batch size, and therefore the
        number of messages returned per call will vary up to the maximum allowed.

        :param max_batch_size: The maximum number of messages that can be returned in
         one call. This value cannot be larger than the prefetch value, and if not specified,
         the prefetch value will be used.
        :type max_batch_size: int
        :param on_message_received: A callback to process messages as they arrive from the
         service. It takes a single argument, a ~uamqp.Message object. The callback can also
         optionally return an altered Message instance to replace that which will be returned
         by this function. If the callback returns nothing, the original ~uamqp.Message object
         will be returned in the batch.
        :type on_message_received: callable[~uamqp.Message]
        :param timeout: I timeout in milliseconds for which to wait to receive any messages.
         If no messages are received in this time, an empty list will be returned. If set to
         0, the client will continue to wait until at least one message is received. The
         default is 0.
        :type timeout: int
        """
        self._message_received_callback = on_message_received
        max_batch_size = max_batch_size or self._prefetch
        if max_batch_size > self._prefetch:
            raise ValueError(
                'Maximum batch size cannot be greater than the '
                'connection prefetch: {}'.format(self._prefetch))
        timeout = self._counter.get_current_ms() + timeout if timeout else 0
        expired = False
        self._received_messages = self._received_messages or queue.Queue()
        self.open()
        receiving = True
        batch = []
        while not self._received_messages.empty() and len(batch) < max_batch_size:
            batch.append(self._received_messages.get())
            self._received_messages.task_done()
        if len(batch) >= max_batch_size:
            return batch

        while receiving and not expired and len(batch) < max_batch_size:
            while receiving and self._received_messages.qsize() < max_batch_size:
                if timeout > 0 and self._counter.get_current_ms() > timeout:
                    expired = True
                    break
                before = self._received_messages.qsize()
                receiving = self.do_work()
                received = self._received_messages.qsize() - before
                if self._received_messages.qsize() > 0 and received == 0:
                    # No new messages arrived, but we have some - so return what we have.
                    expired = True
                    break
            while not self._received_messages.empty() and len(batch) < max_batch_size:
                batch.append(self._received_messages.get())
                self._received_messages.task_done()
        return batch

    def receive_messages(self, on_message_received):
        """Receive messages. This function will run indefinitely, until the client
        closes either via timeout, error or forced interruption (e.g. keyboard interrupt).

        :param on_message_received: A callback to process messages as they arrive from the
         service. It takes a single argument, a ~uamqp.Message object.
        :type on_message_received: callable[~uamqp.Message]
        """
        self.open()
        self._message_received_callback = on_message_received
        receiving = True
        try:
            while receiving:
                receiving = self.do_work()
        except:
            receiving = False
            raise
        finally:
            if not receiving:
                self.close()

    def receive_messages_iter(self, on_message_received=None):
        """Receive messages by generator. Messages returned in the generator have already been
        accepted - if you wish to add logic to accept or reject messages based on custom
        criteria, pass in a callback.

        :param on_message_received: A callback to process messages as they arrive from the
         service. It takes a single argument, a ~uamqp.Message object. The callback can also
         optionally return an altered Message instance to replace that which will be returned
         by this function. If the callback returns nothing, the original ~uamqp.Message object
         will be returned in the batch.
        :type on_message_received: callable[~uamqp.Message]
        """
        self._message_received_callback = on_message_received
        self._received_messages = queue.Queue()
        return self._message_generator()

    def close(self):
        if self._message_receiver:
            self._message_receiver.destroy()
            self._message_receiver = None
        super(ReceiveClient, self).close()
        self._shutdown = False
        self._last_activity_timestamp = None
        self._was_message_received = False
