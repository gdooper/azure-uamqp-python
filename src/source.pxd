#-------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
#--------------------------------------------------------------------------


cimport base
cimport c_amqp_definitions
cimport c_amqpvalue


cdef class cSource(base.StructBase):
    cdef c_amqp_definitions.SOURCE_HANDLE _c_value
    cdef _validate(self)
    cpdef destroy(self)
    cdef wrap(self, c_amqp_definitions.SOURCE_HANDLE value)

cpdef create_source()