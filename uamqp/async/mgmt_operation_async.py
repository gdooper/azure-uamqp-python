#-------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
#--------------------------------------------------------------------------

import logging
import asyncio
import functools
import uuid

#from uamqp.session import Session
from uamqp.mgmt_operation import MgmtOperation
from uamqp import Message
from uamqp import constants


_logger = logging.getLogger(__name__)


class MgmtOperationAsync(MgmtOperation):
    """An asynchronous AMQP request/response operation. These are frequently used
    for management tasks against a $management node, however any node name can be
    specified and the available options will depend on the target service.

    :param session: The AMQP session to use for the operation. Nee send and
     receive links will be created in this Session.
    :type session: ~uamqp.SessionAsync
    :param target: The AMQP node to send the request to.
     The default is `b"$management"`
    :type target: bytes or str
    :param status_code_field: Provide an alternate name for the status code in the
     response body which can vary between services due to the spec still being in draft.
     The default is `b"statusCode"`.
    :type status_code_field: bytes or str
    :param description_fields: Provide an alternate name for the description in the
     response body which can vary between services due to the spec still being in draft.
     The default is `b"statusDescription"`.
    :type description_fields: bytes or str
    :param encoding: The encoding to use for parameters supplied as strings.
     Default is 'UTF-8'
    :type encoding: str
    :param loop: A user specified event loop.
    :type loop: ~asycnio.AbstractEventLoop
    """

    def __init__(self,
                 session,
                 target=None,
                 status_code_field=b'statusCode',
                 description_fields=b'statusDescription',
                 encoding='UTF-8',
                 loop=None):
        self.loop = loop or asyncio.get_event_loop()
        super(MgmtOperationAsync, self).__init__(
            session,
            target=target,
            status_code_field=status_code_field,
            description_fields=description_fields,
            encoding=encoding)

    async def execute_async(self, operation, op_type, message, timeout=0):
        """Execute a request and wait on a response asynchronously.

        :param operation: The type of operation to be performed. This value will
         be service-specific, but common values incluse READ, CREATE and UPDATE.
         This value will be added as an application property on the message.
        :type operation: bytes
        :param op_type: The type on which to carry out the operation. This will
         be specific to the entities of the service. This value will be added as
         an application property on the message.
        :type op_type: bytes
        :param message: The message to send in the management request.
        :type message: ~uamqp.Message
        :param timeout: Provide an optional timeout in milliseconds within which a response
         to the management request must be received.
        :type timeout: int
        :returns: ~uamqp.Message
        """
        start_time = self._counter.get_current_ms()
        operation_id = str(uuid.uuid4())
        self._responses[operation_id] = None

        def on_complete(operation_result, status_code, description, wrapped_message):
            result = constants.MgmtExecuteResult(operation_result)
            if result != constants.MgmtExecuteResult.Ok:
                _logger.error("Failed to complete mgmt operation.\nStatus code: {}\nMessage: {}".format(
                    status_code, description))
            self._responses[operation_id] = Message(message=wrapped_message)

        self._mgmt_op.execute(operation, op_type, None, message.get_message(), on_complete)
        while not self._responses[operation_id] and not self.mgmt_error:
            if timeout > 0:
                now = self._counter.get_current_ms()
                if (now - start_time) >= timeout:
                    raise TimeoutError("Failed to receive mgmt response in {}ms".format(timeout))
            await self.connection.work_async()
        if self.mgmt_error:
            raise self.mgmt_error
        response = self._responses.pop(operation_id)
        return response

    async def destroy_async(self):
        """Close the send/receive links for this node asynchronously."""
        await self.loop.run_in_executor(None, functools.partial(self._mgmt_op.destroy))
