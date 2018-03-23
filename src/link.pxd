#-------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
#--------------------------------------------------------------------------


from libc cimport stdint
cimport base
cimport amqpvalue
cimport session
cimport c_link
cimport c_session
cimport c_amqp_definitions
cimport c_amqpvalue


cpdef create_link(session.cSession session_c, const char* name, bint role, amqpvalue.AMQPValue source, amqpvalue.AMQPValue target)

cdef class cLink(base.StructBase):
    cdef c_link.LINK_HANDLE _c_value
    cdef _validate(self)
    cpdef destroy(self)
    cdef wrap(self, c_link.LINK_HANDLE value)
    cdef create(self, c_session.SESSION_HANDLE session, const char* name, c_amqp_definitions.role role, c_amqpvalue.AMQP_VALUE source, c_amqpvalue.AMQP_VALUE target)
    cpdef set_prefetch_count(self, stdint.uint32_t prefetch)
    cpdef set_attach_properties(self, amqpvalue.AMQPValue properties)
