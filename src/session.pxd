#-------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
#--------------------------------------------------------------------------


from libc cimport stdint
cimport base
cimport connection
cimport c_connection
cimport c_session


cdef class cSession(base.StructBase):
    cdef c_session.SESSION_HANDLE _c_value
    cdef wrap(self, c_session.SESSION_HANDLE value)
    cdef _validate(self)
    cpdef destroy(self)
    cdef create(self, c_connection.CONNECTION_HANDLE connection_c, c_session.ON_LINK_ATTACHED on_link_attached, void* callback_context)
    cpdef begin(self)
    cpdef end(self, const char* condition_value, const char* description)

cpdef create_session(connection.cConnection connection_c)