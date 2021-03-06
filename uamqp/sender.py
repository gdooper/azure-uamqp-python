#-------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
#--------------------------------------------------------------------------

import logging
import uuid

from uamqp import utils
from uamqp import errors
from uamqp import constants
from uamqp import c_uamqp


_logger = logging.getLogger(__name__)


class MessageSender():
    """A Message Sender that opens its own exclsuive Link on an
    existing Session.

    :ivar send_settle_mode: The mode by which to settle message send
     operations. If set to `Unsettled`, the client will wait for a confirmation
     from the service that the message was successfully send. If set to 'Settled',
     the client will not wait for confirmation and assume success.
    :vartype send_settle_mode: ~uamqp.constants.SenderSettleMode
    :ivar max_message_size: The maximum allowed message size negotiated for the Link.
    :vartype max_message_size: int

    :param session: The underlying Session with which to send.
    :type session: ~uamqp.Session
    :param source: The name of source (i.e. the client).
    :type source: str or bytes
    :param target: The AMQP endpoint to send to.
    :type target: ~uamqp.Target
    :param name: A unique name for the sender. If not specified a GUID will be used.
    :type name: str or bytes
    :param send_settle_mode: The mode by which to settle message send
     operations. If set to `Unsettled`, the client will wait for a confirmation
     from the service that the message was successfully send. If set to 'Settled',
     the client will not wait for confirmation and assume success.
    :type send_settle_mode: ~uamqp.constants.SenderSettleMode
    :param max_message_size: The maximum allowed message size negotiated for the Link.
    :type max_message_size: int
    :param link_credit: The sender Link credit that determines how many
     messages the Link will attempt to handle per connection iteration.
    :type link_credit: int
    :param properties: Data to be sent in the Link ATTACH frame.
    :type properties: dict
    :param debug: Whether to turn on network trace logs. If `True`, trace logs
     will be logged at INFO level. Default is `False`.
    :type debug: bool
    :param encoding: The encoding to use for parameters supplied as strings.
     Default is 'UTF-8'
    :type encoding: str
    """

    def __init__(self, session, source, target,
                 name=None,
                 send_settle_mode=None,
                 max_message_size=None,
                 link_credit=None,
                 properties=None,
                 debug=False,
                 encoding='UTF-8'):
        # pylint: disable=protected-access
        if name:
            self.name = name.encode(encoding) if isinstance(name, str) else name
        else:
            self.name = str(uuid.uuid4()).encode(encoding)
        source = source.encode(encoding) if isinstance(source, str) else source
        role = constants.Role.Sender

        self.source = c_uamqp.Messaging.create_source(source)
        self.target = target._address.value
        self._conn = session._conn
        self._session = session
        self._link = c_uamqp.create_link(session._session, self.name, role.value, self.source, self.target)
        self._link.max_message_size = max_message_size

        if link_credit:
            self._link.set_prefetch_count(link_credit)
        if properties:
            self._link.set_attach_properties(utils.data_factory(properties, encoding=encoding))
        if send_settle_mode:
            self.send_settle_mode = send_settle_mode
        if max_message_size:
            self.max_message_size = max_message_size

        self._sender = c_uamqp.create_message_sender(self._link, self)
        self._sender.set_trace(debug)
        self._state = constants.MessageSenderState.Idle

    def __enter__(self):
        """Open the MessageSender in a context manager."""
        self.open()
        return self

    def __exit__(self, *args):
        """Close the MessageSender when exiting a context manager."""
        self.destroy()

    def destroy(self):
        """Close both the Sender and the Link. Clean up any C objects."""
        self._sender.destroy()
        self._link.destroy()

    def open(self):
        """Open the MessageSender in order to start processing messages.

        :raises: ~uamqp.errors.AMQPConnectionError if the Sender raises
         an error on opening. This can happen if the target URI is invalid
         or the credentials are rejected.
        """
        try:
            self._sender.open()
        except ValueError:
            raise errors.AMQPConnectionError(
                "Failed to open Message Sender. "
                "Please confirm credentials and target URI.")

    def close(self):
        """Close the sender, leaving the link intact."""
        self._sender.close()

    def send_async(self, message, timeout=0):
        """Add a single message to the internal pending queue to be processed
        by the Connection without waiting for it to be sent.
        :param message: The message to send.
        :type message: ~uamqp.Message
        :param timeout: An expiry time for the message added to the queue. If the
         message is not sent within this timeout it will be discarded with an error
         state. If set to 0, the message will not expire. The default is 0.
        """
        c_message = message.get_message()
        self._sender.send(c_message, timeout, message)

    def _state_changed(self, previous_state, new_state):
        """Callback called whenever the underlying Sender undergoes a change
        of state. This function wraps the states as Enums to prepare for
        calling the public callback.
        :param previous_state: The previous Sender state.
        :type previous_state: int
        :param new_state: The new Sender state.
        :type new_state: int
        """
        try:
            _previous_state = constants.MessageSenderState(previous_state)
        except ValueError:
            _previous_state = new_state
        try:
            _new_state = constants.MessageSenderState(new_state)
        except ValueError:
            _new_state = new_state
        self.on_state_changed(_previous_state, _new_state)

    def on_state_changed(self, previous_state, new_state):
        """Callback called whenever the underlying Sender undergoes a change
        of state. This function can be overridden.
        :param previous_state: The previous Sender state.
        :type previous_state: ~uamqp.constants.MessageSenderState
        :param new_state: The new Sender state.
        :type new_state: ~uamqp.constants.MessageSenderState
        """
        _logger.debug("Message sender state changed from {} to {}".format(previous_state, new_state))
        self._state = new_state

    @property
    def send_settle_mode(self):
        return self._link.send_settle_mode

    @send_settle_mode.setter
    def send_settle_mode(self, value):
        self._link.send_settle_mode = value.value

    @property
    def max_message_size(self):
        return self._link.max_message_size

    @max_message_size.setter
    def max_message_size(self, value):
        self._link.max_message_size = int(value)
