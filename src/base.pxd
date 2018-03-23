#-------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
#--------------------------------------------------------------------------


cimport c_tlsio
cimport c_utils


cdef class StructBase:
    pass

cdef class TickCounter:
    cdef c_utils.TICK_COUNTER_HANDLE _c_value
    cpdef get_current_ms(self)
    cpdef destroy(self)