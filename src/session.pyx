#-------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
#--------------------------------------------------------------------------

# Python imports
import logging

# C imports
from libc cimport stdint
cimport base
cimport connection
cimport c_session
cimport c_connection
cimport c_amqp_definitions


_logger = logging.getLogger(__name__)


cpdef create_session(connection.cConnection connection_c):
    session = cSession()
    session.create(connection_c._c_value, NULL, NULL)
    return session


cdef class cSession(base.StructBase):

    _links = []

    def __cinit__(self):
        pass

    def __dealloc__(self):
        _logger.debug("Deallocating {}".format(self.__class__.__name__))
        self.destroy()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.destroy()

    @property
    def incoming_window(self):
        cdef stdint.uint32_t value
        if c_session.session_get_incoming_window(<c_session.SESSION_HANDLE>self._c_value, &value) != 0:
            self._value_error()
        return value

    @incoming_window.setter
    def incoming_window(self, stdint.uint32_t value):
        if c_session.session_set_incoming_window(<c_session.SESSION_HANDLE>self._c_value, value) != 0:
            self._value_error()

    @property
    def outgoing_window(self):
        cdef stdint.uint32_t value
        if c_session.session_get_outgoing_window(<c_session.SESSION_HANDLE>self._c_value, &value) != 0:
            self._value_error()
        return value

    @outgoing_window.setter
    def outgoing_window(self, stdint.uint32_t value):
        if c_session.session_set_outgoing_window(<c_session.SESSION_HANDLE>self._c_value, value) != 0:
            self._value_error()

    @property
    def handle_max(self):
        cdef c_amqp_definitions.handle value
        if c_session.session_get_handle_max(<c_session.SESSION_HANDLE>self._c_value, &value) != 0:
            self._value_error()
        return value

    @handle_max.setter
    def handle_max(self, c_amqp_definitions.handle value):
        if c_session.session_set_handle_max(<c_session.SESSION_HANDLE>self._c_value, value) != 0:
            self._value_error()

    cdef _validate(self):
        if <void*>self._c_value is NULL:
            self._memory_error()

    cpdef destroy(self):
        if <void*>self._c_value is not NULL:
            _logger.debug("Destroying {}".format(self.__class__.__name__))
            c_session.session_destroy(<c_session.SESSION_HANDLE>self._c_value)
            self._c_value = <c_session.SESSION_HANDLE>NULL

    cdef wrap(self, c_session.SESSION_HANDLE value):
        self.destroy()
        self._c_value = value
        self._validate()

    cdef create(self, c_connection.CONNECTION_HANDLE connection_c, c_session.ON_LINK_ATTACHED on_link_attached, void* callback_context):
        self.destroy()
        self._c_value = c_session.session_create(connection_c, on_link_attached, callback_context)
        self._validate()

    cpdef begin(self):
        if c_session.session_begin(<c_session.SESSION_HANDLE>self._c_value) != 0:
            self._value_error()

    cpdef end(self, const char* condition_value, const char* description):
        if c_session.session_end(<c_session.SESSION_HANDLE>self._c_value, condition_value, description) != 0:
            self._value_error()
