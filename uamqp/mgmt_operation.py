#-------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
#--------------------------------------------------------------------------

import logging
import uuid

# from uamqp.session import Session
from uamqp import Message
from uamqp import constants
from uamqp import errors
from uamqp import c_uamqp


_logger = logging.getLogger(__name__)


class MgmtOperation:
    """An AMQP request/response operation. These are frequently used
    for management tasks against a $management node, however any node name can be
    specified and the available options will depend on the target service.

    :param session: The AMQP session to use for the operation. Both send and
     receive links will be created in this Session.
    :type session: ~uamqp.Session
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
    """

    def __init__(self,
                 session,
                 target=None,
                 debug=False,
                 status_code_field=b'statusCode',
                 description_fields=b'statusDescription',
                 encoding='UTF-8'):
        self.connection = session._connection  # pylint: disable=protected-access
        # self.session = Session(
        #     connection,
        #     incoming_window=constants.MAX_FRAME_SIZE_BYTES,
        #     outgoing_window=constants.MAX_FRAME_SIZE_BYTES)
        self.target = target or constants.MGMT_TARGET
        if isinstance(self.target, str):
            self.target = self.target.encode(encoding)
        if isinstance(status_code_field, str):
            status_code_field = status_code_field.encode(encoding)
        if isinstance(description_fields, str):
            description_fields = description_fields.encode(encoding)
        self._responses = {}
        self._encoding = encoding
        self._counter = c_uamqp.TickCounter()
        self._mgmt_op = c_uamqp.create_management_operation(session._session, self.target)  # pylint: disable=protected-access
        self._mgmt_op.set_response_field_names(status_code_field, description_fields)
        self._mgmt_op.set_trace(debug)
        self.open = None
        try:
            self._mgmt_op.open(self)
        except ValueError:
            self.mgmt_error = errors.AMQPConnectionError(
                "Unable to open management session. "
                "Please confirm URI namespace exists.")
        else:
            self.mgmt_error = None

    def _management_open_complete(self, result):
        """Callback run when the send/receive links are open and ready
        to process messages.
        :param result: Whether the link opening was successful.
        :type result: int
        """
        self.open = constants.MgmtOpenStatus(result)

    def _management_operation_error(self):
        """Callback run if an error occurs in the send/receive links."""
        self.mgmt_error = ValueError("Management Operation error ocurred.")

    def execute(self, operation, op_type, message, timeout=0):
        """Execute a request and wait on a response.

        :param operation: The type of operation to be performed. This value will
         be service-specific, but common values incluse READ, CREATE and UPDATE.
         This value will be added as an application property on the message.
        :type operation: bytes or str
        :param op_type: The type on which to carry out the operation. This will
         be specific to the entities of the service. This value will be added as
         an application property on the message.
        :type op_type: bytes or str
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
        if isinstance(operation, str):
            operation = operation.encode(self._encoding)
        if isinstance(op_type, str):
            op_type = op_type.encode(self._encoding)

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
            self.connection.work()
        if self.mgmt_error:
            raise self.mgmt_error
        response = self._responses.pop(operation_id)
        return response

    def destroy(self):
        """Close the send/receive links for this node."""
        self._mgmt_op.destroy()
