#-------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
#--------------------------------------------------------------------------


from libc cimport stdint
cimport base
cimport amqpvalue
cimport c_amqpvalue
cimport c_amqp_definitions
cimport c_utils


cdef class cProperties(base.StructBase):
    cdef c_amqp_definitions.PROPERTIES_HANDLE _c_value
    cdef _validate(self)
    cpdef destroy(self)
    cdef wrap(self, c_amqp_definitions.PROPERTIES_HANDLE value)
    cdef get_properties(self)
    cpdef clone(self)

cpdef create_properties()
cpdef load_properties(amqpvalue.AMQPValue value)