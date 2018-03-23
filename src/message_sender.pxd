#-------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
#--------------------------------------------------------------------------


from libc cimport stdint
cimport base
cimport message
cimport link
cimport c_message_sender
cimport c_link
cimport c_async_operation
cimport c_amqp_definitions


cdef class cMessageSender(base.StructBase):
    cdef c_message_sender.MESSAGE_SENDER_HANDLE _c_value
    cpdef open(self)
    cpdef close(self)
    cdef _create(self)
    cpdef destroy(self)
    cdef wrap(self, c_message_sender.MESSAGE_SENDER_HANDLE value)
    cdef create(self, c_link.LINK_HANDLE link, c_message_sender.ON_MESSAGE_SENDER_STATE_CHANGED on_message_sender_state_changed, void* context)
    cpdef send(self, message.cMessage request, c_amqp_definitions.tickcounter_ms_t timeout, callback_context)
    cpdef set_trace(self, bint value)

cpdef create_message_sender(link.cLink link_c, callback_context)