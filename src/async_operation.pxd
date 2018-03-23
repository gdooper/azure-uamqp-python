#-------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
#--------------------------------------------------------------------------


cimport base
cimport c_async_operation


cdef class AsyncOperation(base.StructBase):
    cdef c_async_operation.ASYNC_OPERATION_HANDLE _c_value
    cdef wrap(self, c_async_operation.ASYNC_OPERATION_HANDLE value)
    cpdef destroy(self)
    cpdef cancel(self)
