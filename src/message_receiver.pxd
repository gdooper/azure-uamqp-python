#-------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
#--------------------------------------------------------------------------


cimport message
cimport link
cimport base
cimport c_message_receiver
cimport c_message
cimport c_link


cdef class cMessageReceiver(base.StructBase):
    cdef c_message_receiver.MESSAGE_RECEIVER_HANDLE _c_value
    cdef _validate(self)
    cdef create(self, c_link.LINK_HANDLE link, c_message_receiver.ON_MESSAGE_RECEIVER_STATE_CHANGED on_message_sender_state_changed, void* context)
    cpdef open(self, callback_context)
    cpdef close(self)
    cpdef destroy(self)
    cdef wrap(self, c_message_receiver.MESSAGE_RECEIVER_HANDLE value)
    cpdef set_trace(self, bint value)

cpdef create_message_receiver(link.cLink link_c, callback_context)