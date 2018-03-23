#-------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
#--------------------------------------------------------------------------

from libc cimport stdint
cimport amqpvalue
cimport base
cimport c_message
cimport c_amqp_definitions
cimport c_amqpvalue


cdef class cMessage(base.StructBase):
    cdef c_message.MESSAGE_HANDLE _c_value
    cdef wrap(self, c_message.MESSAGE_HANDLE value)
    cdef create(self)
    cpdef clone(self)
    cpdef destroy(self)
    cdef _validate(self)
    cpdef add_body_data(self, bytes value)
    cpdef get_body_data(self, size_t index)
    cpdef count_body_data(self)
    cpdef set_body_value(self, amqpvalue.AMQPValue value)
    cpdef get_body_value(self)
    cpdef add_body_sequence(self, amqpvalue.AMQPValue sequence)
    cpdef get_body_sequence(self, size_t index)
    cpdef count_body_sequence(self)

cdef message_factory(c_message.MESSAGE_HANDLE value)
cpdef create_message()
cpdef size_t get_encoded_message_size(cMessage message)