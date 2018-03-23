#-------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
#--------------------------------------------------------------------------


from libc cimport stdint
from libc.stdlib cimport malloc, free
from libc.string cimport memset

cimport c_cbs
cimport c_utils
cimport c_strings
cimport c_session


cdef class CBSTokenAuth:
    cdef const char* audience
    cdef const char* token_type
    cdef const char* token
    cdef stdint.uint64_t expiry
    cdef stdint.uint64_t _refresh_window
    cdef c_cbs.CBS_HANDLE _cbs_handle
    cdef c_cbs.AUTH_STATUS state
    cdef stdint.uint64_t auth_timeout
    cdef stdint.uint64_t _token_put_time
    cdef unsigned int token_status_code
    cdef const char* token_status_description
    cpdef destroy(self)
    cpdef set_trace(self, bint trace_on)
    cpdef authenticate(self)
    cpdef get_status(self)
    cpdef get_failure_info(self)
    cpdef refresh(self)
    cpdef _update_status(self)
    cpdef _check_put_timeout_status(self)
    cpdef _check_expiration_and_refresh_status(self)
    cpdef _cbs_open_complete(self, result)
    cpdef on_cbs_open_complete(self, result)
    cpdef _cbs_error(self)
    cpdef on_cbs_error(self)
    cpdef _cbs_put_token_compelete(self, result, status_code, status_description)
    cpdef on_cbs_put_token_complete(self, result, status_code, status_description)

cpdef create_sas_token(const char* key, const char* scope, const char* keyname, size_t expiry)