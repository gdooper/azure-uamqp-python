#-------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
#--------------------------------------------------------------------------

import asyncio
import logging
import functools

from uamqp import connection


_logger = logging.getLogger(__name__)


class ConnectionAsync(connection.Connection):
    """An Asynchronous AMQP Connection. A single Connection can have multiple
    Sessions, and can be shared between multiple Clients.

    :ivar max_frame_size: Maximum AMQP frame size. Default is 63488 bytes.
    :vartype max_frame_size: int
    :ivar channel_max: Maximum number of Session channels in the Connection.
    :vartype channel_max: int
    :ivar idle_timeout: Timeout in milliseconds after which the Connection will close
     if there is no further activity.
    :vartype idle_timeout: int
    :ivar properties: Connection properties.
    :vartype properties: dict

    :param hostname: The hostname of the AMQP service with which to establish
     a connection.
    :type hostname: bytes or str
    :param sasl: Authentication for the connection. If none is provided SASL Annoymous
     authentication will be used.
    :type sasl: ~uamqp.authentication.AMQPAuth
    :param container_id: The name for the client, also known as the Container ID.
     If no name is provided, a random GUID will be used.
    :type container_id: str or bytes
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
    :param debug: Whether to turn on network trace logs. If `True`, trace logs
     will be logged at INFO level. Default is `False`.
    :type debug: bool
    :param encoding: The encoding to use for parameters supplied as strings.
     Default is 'UTF-8'
    :type encoding: str
    :param loop: A user specified event loop.
    :type loop: ~asycnio.AbstractEventLoop
    """

    def __init__(self, hostname, sasl,
                 container_id=False,
                 max_frame_size=None,
                 channel_max=None,
                 idle_timeout=None,
                 properties=None,
                 remote_idle_timeout_empty_frame_send_ratio=None,
                 debug=False,
                 encoding='UTF-8',
                 loop=None):
        self.loop = loop or asyncio.get_event_loop()
        super(ConnectionAsync, self).__init__(
            hostname, sasl,
            container_id=container_id,
            max_frame_size=max_frame_size,
            channel_max=channel_max,
            idle_timeout=idle_timeout,
            properties=properties,
            remote_idle_timeout_empty_frame_send_ratio=remote_idle_timeout_empty_frame_send_ratio,
            debug=debug,
            encoding=encoding)
        self._lock = asyncio.Lock(loop=self.loop)

    async def __aenter__(self):
        """Open the Connection in an async context manager."""
        return self

    async def __aexit__(self, *args):
        """Close the Connection when exiting an async context manager."""
        await self.destroy_async()

    async def work_async(self):
        """Perform a single Connection iteration asynchronously."""
        await self._lock.acquire()
        await self.loop.run_in_executor(None, functools.partial(self._conn.do_work))
        self._lock.release()

    async def destroy_async(self):
        """Close the connection asynchronously, and close any associated
        CBS authentication session.
        """
        if self.cbs:
            await self.auth.close_authenticator_async()
        await self.loop.run_in_executor(None, functools.partial(self._conn.destroy))
