#-------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
#--------------------------------------------------------------------------


cimport base
cimport c_xio
cimport c_sasl_mechanism


cdef class SASLMechanism(base.StructBase):
    cdef c_sasl_mechanism.SASL_MECHANISM_HANDLE _c_value
    cdef _validate(self)
    cdef wrap(self, c_sasl_mechanism.SASL_MECHANISM_HANDLE value)
    cdef create(self, SASLMechanismInterfaceDescription sasl_mechanism_interface_description)
    cdef create_with_parameters(self, SASLMechanismInterfaceDescription sasl_mechanism_interface_description, void *parameters)
    cpdef destroy(self)

cdef class SASLMechanismInterfaceDescription:
    cdef c_sasl_mechanism.SASL_MECHANISM_INTERFACE_DESCRIPTION* _c_value
    cdef wrap(self, c_sasl_mechanism.SASL_MECHANISM_INTERFACE_DESCRIPTION* value)

cdef class SASLClientIOConfig:
    cdef c_sasl_mechanism.SASLCLIENTIO_CONFIG _c_value

cdef class SASLPlainConfig:
    cdef c_sasl_mechanism.SASL_PLAIN_CONFIG _c_value

cpdef saslanonymous_get_interface()
cpdef saslplain_get_interface()
cpdef get_sasl_mechanism(SASLMechanismInterfaceDescription interface)
cpdef get_plain_sasl_mechanism(SASLMechanismInterfaceDescription interface, SASLPlainConfig parameters)