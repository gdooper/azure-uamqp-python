#-------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
#--------------------------------------------------------------------------


cimport xio
cimport base
cimport c_connection
cimport c_xio


cdef class cConnection(base.StructBase):
    cdef c_connection.CONNECTION_HANDLE _c_value
    cdef wrap(self, c_connection.CONNECTION_HANDLE value)
    cpdef destroy(self)
    cdef _validate(self)
    cdef create(self, c_xio.XIO_HANDLE io, const char* hostname, const char* container_id, c_connection.ON_CONNECTION_STATE_CHANGED on_connection_state_changed, c_xio.ON_IO_ERROR on_io_error, void* callback_context)
    cpdef open(self)
    cpdef close(self, const char* condition_value, const char* description)
    cpdef set_trace(self, bint value)
    cpdef do_work(self)

cpdef create_connection(xio.XIO sasl_client, const char* hostname, const char* container_id, callback_context)

