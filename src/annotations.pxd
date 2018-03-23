#-------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
#--------------------------------------------------------------------------

# C imports
from libc cimport stdint
cimport base
cimport amqpvalue
cimport c_amqpvalue
cimport c_amqp_definitions
cimport c_utils


#cdef class cAnnotations(base.StructBase):
#    cdef c_amqpvalue.AMQP_VALUE _c_value
#    cdef wrap(self, c_amqp_definitions.annotations value)
#    cpdef create(self, amqpvalue.AMQPValue value)
#   cpdef get_encoded_size(self)
#   cpdef clone
#    cpdef destroy(self)
#    cdef _validate(self)

cdef class cApplicationProperties: #(cAnnotations):
    cpdef create(self, amqpvalue.AMQPValue value)

cdef class cDeliveryAnnotations: #(cAnnotations):
    cpdef create(self, amqpvalue.AMQPValue value)

cdef class cMessageAnnotations: #(cAnnotations):
    cpdef create(self, amqpvalue.AMQPValue value)

cdef class cFields: #(cAnnotations):
    cpdef create(self, amqpvalue.AMQPValue value)

cdef class cFooter: #(cAnnotations):
    cpdef create(self, amqpvalue.AMQPValue value)


cdef annotations_factory(c_amqpvalue.AMQP_VALUE value)
cpdef create_annotations(amqpvalue.AMQPValue value)
cpdef create_application_properties(amqpvalue.AMQPValue value)
cpdef create_delivery_annotations(amqpvalue.AMQPValue value)
cpdef create_message_annotations(amqpvalue.AMQPValue value)
cpdef create_fields(amqpvalue.AMQPValue value)
cpdef create_footer(amqpvalue.AMQPValue value)