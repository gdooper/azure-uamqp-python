#-------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
#--------------------------------------------------------------------------


cimport tlsio
cimport sasl
cimport c_xio
cimport c_sasl_mechanism


cdef class XIO:
    cdef wrap(self, c_xio.XIO_HANDLE value)
    cdef create(self, c_xio.IO_INTERFACE_DESCRIPTION* io_desc, void *io_params)
    cpdef destroy(self)

cdef class IOInterfaceDescription:
    cdef c_xio.IO_INTERFACE_DESCRIPTION* _c_value
    cdef wrap(self, c_xio.IO_INTERFACE_DESCRIPTION* value)

cpdef xio_from_tlsioconfig(IOInterfaceDescription io_desc, tlsio.TLSIOConfig io_config)
cpdef xio_from_saslioconfig(sasl.SASLClientIOConfig io_config)