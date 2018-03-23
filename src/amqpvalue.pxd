#-------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
#--------------------------------------------------------------------------


from libc cimport stdint
cimport base
cimport c_amqpvalue


cdef class AMQPValue(base.StructBase):
    cdef c_amqpvalue.AMQP_VALUE _c_value
    cdef wrap(self, c_amqpvalue.AMQP_VALUE value)
    cpdef destroy(self)
    cdef _validate(self)
    cpdef get_encoded_size(self)
    cpdef clone(self)
    cpdef get_map(self)


cpdef enocde_batch_value(AMQPValue value, message_body)
cdef value_factory(c_amqpvalue.AMQP_VALUE value)
cpdef null_value()
cpdef bool_value(bint value)
cpdef ubyte_value(unsigned char value)
cpdef ushort_value(stdint.uint16_t value)
cpdef uint_value(stdint.uint32_t value)
cpdef ulong_value(stdint.uint64_t value)
cpdef byte_value(char value)
cpdef short_value(stdint.int16_t value)
cpdef int_value(stdint.int32_t value)
cpdef long_value(stdint.int64_t value)
cpdef float_value(float value)
cpdef double_value(double value)
cpdef char_value(stdint.uint32_t value)
cpdef timestamp_value(stdint.int64_t value)
cpdef uuid_value(value)
cpdef binary_value(char* value)
cpdef string_value(char* value)
cpdef symbol_value(char* value)
cpdef list_value()
cpdef dict_value()
cpdef array_value()
cpdef described_value(AMQPValue descriptor, AMQPValue value)