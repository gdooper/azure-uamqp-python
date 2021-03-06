#-------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
#--------------------------------------------------------------------------

# TODO: check this
# pylint: disable=super-init-not-called

import asyncio
import collections.abc
import logging
import uuid
import queue

from uamqp import client
from uamqp import constants
from uamqp import errors

from uamqp.async.connection_async import ConnectionAsync
from uamqp.async.session_async import SessionAsync
from uamqp.async.sender_async import MessageSenderAsync
from uamqp.async.receiver_async import MessageReceiverAsync
from uamqp.async.authentication_async import CBSAsyncAuthMixin


_logger = logging.getLogger(__name__)


class AMQPClientAsync(client.AMQPClient):
    """An asynchronous AMQP client.

    :param remote_address: The AMQP endpoint to connect to. This could be a send target
     or a receive source.
    :type remote_address: str, bytes or ~uamqp.address.Address
    :param auth: Authentication for the connection. If none is provided SASL Annoymous
     authentication will be used.
    :type auth: ~uamqp.authentication.AMQPAuth
    :param client_name: The name for the client, also known as the Container ID.
     If no name is provided, a random GUID will be used.
    :type client_name: str or bytes
    :param loop: A user specified event loop.
    :type loop: ~asycnio.AbstractEventLoop
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

    def __init__(self, remote_address, auth=None, client_name=None, loop=None, debug=False, **kwargs):
        self.loop = loop or asyncio.get_event_loop()
        super(AMQPClientAsync, self).__init__(
            remote_address, auth=auth, client_name=client_name, debug=debug, **kwargs)

        # AMQP object settings
        self.connection_type = ConnectionAsync
        self.session_type = SessionAsync

    async def __aenter__(self):
        """Run Client in an async context manager."""
        await self.open_async()
        return self

    async def __aexit__(self, *args):
        """Close and destroy Client on exiting an async context manager."""
        await self.close_async()

    async def open_async(self, connection=None):
        """Asynchronously open the client. The client can create a new Connection
        or an existing Connection can be passed in. This existing Connection
        may have an existing CBS authentication Session, which will be
        used for this client as well. Otherwise a new Session will be
        created.

        :param connection: An existing Connection that may be shared between
         multiple clients.
        :type connetion: ~uamqp.ConnectionAsync
        """
        # pylint: disable=protected-access
        if self._session:
            return  # already open
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
            loop=self.loop)
        if not self._connection.cbs and isinstance(self._auth, CBSAsyncAuthMixin):
            self._connection.cbs = await self._auth.create_authenticator_async(
                self._connection,
                debug=self._debug_trace,
                loop=self.loop)
            self._session = self._auth._session
        elif self._connection.cbs:
            self._session = self._auth._session
        else:
            self._session = self.session_type(
                self._connection,
                incoming_window=self._incoming_window,
                outgoing_window=self._outgoing_window,
                handle_max=self._handle_max,
                loop=self.loop)

    async def close_async(self):
        """Close the client asynchronously. This includes closing the Session
        and CBS authentication layer as well as the Connection.
        If the client was opened using an external Connection,
        this will be left intact.
        """
        if not self._session:
            return  # already closed.
        else:
            if self._connection.cbs and not self._ext_connection:
                _logger.debug("Closing CBS session.")
                await self._auth.close_authenticator_async()
                self._connection.cbs = None
            elif not self._connection.cbs:
                _logger.debug("Closing non-CBS session.")
                await self._session.destroy_async()
            else:
                _logger.debug("Not closing CBS session.")
            self._session = None
            if not self._ext_connection:
                _logger.debug("Closing unshared connection.")
                await self._connection.destroy_async()
            else:
                _logger.debug("Shared connection remaining open.")
            self._connection = None

    async def mgmt_request_async(self, message, operation, op_type=None, node=None, **kwargs):
        """Run an asynchronous request/response operation. These are frequently used
        for management tasks against a $management node, however any node name can be
        specified and the available options will depend on the target service.

        :param message: The message to send in the management request.
        :type message: ~uamqp.Message
        :param operation: The type of operation to be performed. This value will
         be service-specific, but common values incluse READ, CREATE and UPDATE.
         This value will be added as an application property on the message.
        :type operation: bytes or str
        :param op_type: The type on which to carry out the operation. This will
         be specific to the entities of the service. This value will be added as
         an application property on the message.
        :type op_type: bytes
        :param node: The target node. Default is `b"$management"`.
        :type node: bytes or str
        :param timeout: Provide an optional timeout in milliseconds within which a response
         to the management request must be received.
        :type timeout: int
        :param status_code_field: Provide an alternate name for the status code in the
         response body which can vary between services due to the spec still being in draft.
         The default is `b"statusCode"`.
        :type status_code_field: bytes or str
        :param description_fields: Provide an alternate name for the description in the
         response body which can vary between services due to the spec still being in draft.
         The default is `b"statusDescription"`.
        :type description_fields: bytes or str
        :returns: ~uamqp.Message
        """
        timeout = False
        auth_in_progress = False
        while True:
            if self._connection.cbs:
                timeout, auth_in_progress = await self._auth.handle_token_async()
            if timeout:
                raise TimeoutError("Authorization timeout.")
            elif auth_in_progress:
                await self._connection.work_async()
            else:
                break
        if not self._session:
            raise ValueError("Session not yet open")
        response = await self._session.mgmt_request_async(
            message,
            operation,
            op_type=op_type,
            node=node,
            encoding=self._encoding,
            **kwargs)
        return response

    async def do_work_async(self):
        """Run a single connection iteration asynchronously.
        This will return `True` if the connection is still open
        and ready to be used for further work, or `False` if it needs
        to be shut down.

        :returns: bool
        :raises: TimeoutError if CBS authentication timeout reached.
        """
        timeout = False
        auth_in_progress = False
        if self._connection.cbs:
            timeout, auth_in_progress = await self._auth.handle_token_async()

        if self._shutdown:
            return False
        if timeout:
            raise TimeoutError("Authorization timeout.")
        elif auth_in_progress:
            await self._connection.work_async()
            return True
        elif not await self._client_ready():
            await self._connection.work_async()
            return True
        else:
            return await self._client_run()


class SendClientAsync(client.SendClient, AMQPClientAsync):
    """An AMQP client for sending messages asynchronously.

    :param target: The target AMQP service endpoint. This can either be the URI as
     a string or a ~uamqp.Target object.
    :type target: str, bytes or ~uamqp.Target
    :param auth: Authentication for the connection. If none is provided SASL Annoymous
     authentication will be used.
    :type auth: ~uamqp.authentication.AMQPAuth
    :param client_name: The name for the client, also known as the Container ID.
     If no name is provided, a random GUID will be used.
    :type client_name: str or bytes
    :param loop: A user specified event loop.
    :type loop: ~asycnio.AbstractEventLoop
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

    def __init__(self, target, auth=None, client_name=None, loop=None, debug=False, msg_timeout=0, **kwargs):
        self.loop = loop or asyncio.get_event_loop()
        client.SendClient.__init__(
            self, target, auth=auth, client_name=client_name, debug=debug, msg_timeout=msg_timeout, **kwargs)

        # AMQP object settings
        self.sender_type = MessageSenderAsync

    async def _client_ready(self):
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
                properties=self._link_properties,
                encoding=self._encoding,
                loop=self.loop)
            await self._message_sender.open_async()
            return False
        elif self._message_sender._state == constants.MessageSenderState.Error:
            raise errors.AMQPConnectionError(
                "Message Sender Client was unable to open. "
                "Please confirm credentials and access permissions."
                "\nSee debug trace for more details.")
        elif self._message_sender._state != constants.MessageSenderState.Open:
            return False
        return True

    async def _client_run(self):
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
                    if self._msg_timeout > 0 and elapsed_time/1000 > self._msg_timeout:
                        message._on_message_sent(constants.MessageSendResult.Timeout)
                    else:
                        timeout = self._msg_timeout - elapsed_time if self._msg_timeout > 0 else 0
                        self._message_sender.send_async(message, timeout=timeout)

                except Exception as exp:  # pylint: disable=broad-except
                    message._on_message_sent(constants.MessageSendResult.Error, error=exp)
        await self._connection.work_async()
        return True

    async def close_async(self):
        """Close down the client asynchronously. No further
        messages can be sent and the client cannot be re-opened.

        All pending, unsent messages will be cleared.
        """
        if self._message_sender:
            await self._message_sender.destroy_async()
            self._message_sender = None
        await super(SendClientAsync, self).close_async()
        self._pending_messages = []

    async def wait_async(self):
        """Run the client asynchronously until all pending messages
        in the queue have been processed.
        """
        while self.messages_pending():
            await self.do_work_async()

    async def send_message_async(self, messages, close_on_done=False):
        """Send a single message or batched message asynchronously.

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
        await self.open_async()
        try:
            while any([m for m in pending_batch if m.state not in constants.DONE_STATES]):
                await self.do_work_async()
        except:
            raise
        else:
            failed = [m for m in pending_batch if m.state == constants.MessageState.Failed]
            if any(failed):
                raise errors.MessageSendFailed("Failed to send message.")
        finally:
            if close_on_done:
                await self.close_async()

    async def send_all_messages_async(self, close_on_done=True):
        """Send all pending messages in the queue asynchronously.
        This will return a list of the send result of all the pending
        messages so it can be determined if any messages failed to send.
        This function will open the client if it is not already open.

        :param close_on_done: Close the client once the messages are sent.
         Default is `True`.
        :type close_on_done: bool
        :returns: list[~uamqp.constants.MessageState]
        """
        await self.open_async()
        try:
            messages = self._pending_messages[:]
            await self.wait_async()
        except:
            raise
        else:
            results = [m.state for m in messages]
            return results
        finally:
            if close_on_done:
                await self.close_async()


class ReceiveClientAsync(client.ReceiveClient, AMQPClientAsync):
    """An AMQP client for receiving messages asynchronously.

    :param target: The source AMQP service endpoint. This can either be the URI as
     a string or a ~uamqp.Source object.
    :type target: str, bytes or ~uamqp.Source
    :param auth: Authentication for the connection. If none is provided SASL Annoymous
     authentication will be used.
    :type auth: ~uamqp.authentication.AMQPAuth
    :param client_name: The name for the client, also known as the Container ID.
     If no name is provided, a random GUID will be used.
    :type client_name: str or bytes
    :param loop: A user specified event loop.
    :type loop: ~asycnio.AbstractEventLoop
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

    def __init__(self, source, auth=None, client_name=None, loop=None, debug=False, timeout=0, **kwargs):
        self.loop = loop or asyncio.get_event_loop()
        client.ReceiveClient.__init__(
            self, source, auth=auth, client_name=client_name, debug=debug, timeout=timeout, **kwargs)

        # AMQP object settings
        self.receiver_type = MessageReceiverAsync

    async def _client_ready(self):
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
                encoding=self._encoding,
                loop=self.loop)
            await self._message_receiver.open_async()
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

    async def _client_run(self):
        """MessageReceiver Link is now open - start receiving messages.
        Will return True if operation successful and client can remain open for
        further work.
        :returns: bool
        """
        await self._connection.work_async()
        if self._timeout > 0:
            now = self._counter.get_current_ms()
            if self._last_activity_timestamp and not self._was_message_received:
                timespan = now - self._last_activity_timestamp
                if timespan >= self._timeout:
                    _logger.info("Timeout reached, closing receiver: {}".format(self._remote_address))
                    self._shutdown = True
            else:
                self._last_activity_timestamp = now
        self._was_message_received = False
        return True

    async def receive_messages_async(self, on_message_received):
        """Receive messages asynchronously. This function will run indefinitely,
        until the client closes either via timeout, error or forced
        interruption (e.g. keyboard interrupt).

        :param on_message_received: A callback to process messages as they arrive from the
         service. It takes a single argument, a ~uamqp.Message object.
        :type on_message_received: callable[~uamqp.Message]
        """
        await self.open_async()
        self._message_received_callback = on_message_received
        receiving = True
        try:
            while receiving:
                receiving = await self.do_work_async()
        except:
            receiving = False
            raise
        finally:
            if not receiving:
                await self.close_async()

    async def receive_message_batch_async(self, max_batch_size=None, on_message_received=None, timeout=0):
        """Receive a batch of messages asynchronously. Messages returned in the batch have
        already been accepted - if you wish to add logic to accept or reject messages based
        on custom criteria, pass in a callback. This method will return as soon as some
        messages are available rather than waiting to achieve a specific batch size, and
        therefore the number of messages returned per call will vary up to the maximum allowed.

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
                'Maximum batch size {} cannot be greater than the '
                'connection prefetch: {}'.format(max_batch_size, self._prefetch))
        timeout = self._counter.get_current_ms() + int(timeout) if timeout else 0
        expired = False
        self._received_messages = self._received_messages or queue.Queue()
        await self.open_async()
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
                receiving = await self.do_work_async()
                received = self._received_messages.qsize() - before
                if self._received_messages.qsize() > 0 and received == 0:
                    # No new messages arrived, but we have some - so return what we have.
                    expired = True
                    break

            while not self._received_messages.empty() and len(batch) < max_batch_size:
                batch.append(self._received_messages.get())
                self._received_messages.task_done()
        return batch

    def receive_messages_iter_async(self, on_message_received=None):
        """Receive messages by asynchronous generator. Messages returned in the
        generator have already been accepted - if you wish to add logic to accept
        or reject messages based on custom criteria, pass in a callback.

        :param on_message_received: A callback to process messages as they arrive from the
         service. It takes a single argument, a ~uamqp.Message object. The callback can also
         optionally return an altered Message instance to replace that which will be returned
         by this function. If the callback returns nothing, the original ~uamqp.Message object
         will be returned in the batch.
        :type on_message_received: callable[~uamqp.Message]
        """
        self._message_received_callback = on_message_received
        self._received_messages = queue.Queue()
        return AsyncMessageIter(self)

    async def close_async(self):
        if self._message_receiver:
            await self._message_receiver.destroy_async()
            self._message_receiver = None
        await super(ReceiveClientAsync, self).close_async()
        self._shutdown = False
        self._last_activity_timestamp = None
        self._was_message_received = False


class AsyncMessageIter(collections.abc.AsyncIterator):
    """Python 3.5 and 3.6 compatible asynchronous generator.
    :param recv_client: The receiving client.
    :type recv_client: ~uamqp.ReceiveClientAsync
    """

    def __init__(self, rcv_client):
        self._client = rcv_client
        self.receiving = True

    async def __anext__(self):
        # pylint: disable=protected-access
        await self._client.open_async()
        try:
            while self.receiving and self._client._received_messages.empty():
                self.receiving = await self._client.do_work_async()
            if not self._client._received_messages.empty():
                message = self._client._received_messages.get()
                self._client._received_messages.task_done()
                return message
            else:
                raise StopAsyncIteration("Message receive closing.")
        except:
            self.receiving = False
            raise
        finally:
            if not self.receiving:
                await self._client.close_async()
