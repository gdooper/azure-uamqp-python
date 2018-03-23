#-------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
#--------------------------------------------------------------------------


from libc cimport stdint
cimport base
cimport c_amqpvalue
cimport c_amqp_definitions


cdef class cHeader(base.StructBase):
    cdef c_amqp_definitions.HEADER_HANDLE _c_value
    cdef _validate(self)
    cpdef destroy(self)
    cdef wrap(self, c_amqp_definitions.HEADER_HANDLE value)
    cpdef clone(self)