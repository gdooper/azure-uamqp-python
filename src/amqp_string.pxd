#-------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
#--------------------------------------------------------------------------


cimport base
cimport c_strings


cdef class AMQPString(base.StructBase):
    cdef c_strings.STRING_HANDLE _c_value
    cdef wrap(self, c_strings.STRING_HANDLE value)
    cpdef destroy(self)
    cdef _validate(self)
    cdef construct(self, const char* value)
    cpdef append(self, other)
    cpdef clone(self)

cpdef create_empty_string()
cpdef create_string_from_value(value)

