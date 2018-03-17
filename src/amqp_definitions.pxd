#-------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
#--------------------------------------------------------------------------

cimport amqpvalue

cpdef create_data(char* binary_data)
cpdef create_sequence(amqpvalue.AMQPValue sequence_data)