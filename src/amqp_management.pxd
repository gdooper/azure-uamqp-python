#-------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
#--------------------------------------------------------------------------


cimport session
cimport message
cimport base
cimport c_amqp_management
cimport c_message


cdef class cManagementOperation(base.StructBase):
    cdef c_amqp_management.AMQP_MANAGEMENT_HANDLE _c_value
    cdef wrap(self, c_amqp_management.AMQP_MANAGEMENT_HANDLE value)
    cdef create(self, session.cSession session_c, const char* management_node)
    cdef _validate(self)
    cpdef destroy(self)
    cpdef set_trace(self, bint value)
    cpdef set_response_field_names(self, const char* status_code, const char* status_description)
    cpdef open(self, callback_context)
    cpdef close(self)
    cpdef execute(self, const char* operation, const char* type, locales, message.cMessage request, callback_context)

cpdef create_management_operation(session.cSession session_c, management_node)