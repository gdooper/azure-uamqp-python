#-------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for
# license information.
#--------------------------------------------------------------------------

import logging
import os
import pytest
import time
import sys
try:
    from urllib import quote_plus #Py2
except Exception:
    from urllib.parse import quote_plus

import uamqp
from uamqp import address
from uamqp import authentication


def get_logger(level):
    uamqp_logger = logging.getLogger("uamqp")
    if not uamqp_logger.handlers:
        handler = logging.StreamHandler(stream=sys.stdout)
        handler.setFormatter(logging.Formatter('%(asctime)s %(name)-12s %(levelname)-8s %(message)s'))
        uamqp_logger.addHandler(handler)
    uamqp_logger.setLevel(level)
    return uamqp_logger


log = get_logger(logging.INFO)


def test_event_hubs_simple_receive(live_eventhub_config):
    plain_auth = authentication.SASLPlain(
        live_eventhub_config['hostname'],
        live_eventhub_config['key_name'],
        live_eventhub_config['access_key'])
    source = "amqps://{}/{}/ConsumerGroups/{}/Partitions/{}".format(
        live_eventhub_config['hostname'],
        live_eventhub_config['event_hub'],
        live_eventhub_config['consumer_group'],
        live_eventhub_config['partition'])

    message = uamqp.receive_message(source, auth=plain_auth)
    log.info("Received: {}".format(message.get_data()))


def test_event_hubs_simple_batch_receive(live_eventhub_config):

    source = "amqps://{}:{}@{}/{}/ConsumerGroups/{}/Partitions/{}".format(
        quote_plus(live_eventhub_config['key_name']),
        quote_plus(live_eventhub_config['access_key']),
        live_eventhub_config['hostname'],
        live_eventhub_config['event_hub'],
        live_eventhub_config['consumer_group'],
        live_eventhub_config['partition'])

    messages = uamqp.receive_messages(source, max_batch_size=10)
    assert len(messages) <= 10

    message = uamqp.receive_messages(source, max_batch_size=1)
    assert len(message) == 1


def test_event_hubs_single_batch_receive(live_eventhub_config):
    plain_auth = authentication.SASLPlain(
        live_eventhub_config['hostname'],
        live_eventhub_config['key_name'],
        live_eventhub_config['access_key'])
    source = "amqps://{}/{}/ConsumerGroups/{}/Partitions/{}".format(
        live_eventhub_config['hostname'],
        live_eventhub_config['event_hub'],
        live_eventhub_config['consumer_group'],
        live_eventhub_config['partition'])

    message = uamqp.receive_messages(source, auth=plain_auth, timeout=5000)
    assert len(message) <= 300


def test_event_hubs_client_receive_sync(live_eventhub_config):
    uri = "sb://{}/{}".format(live_eventhub_config['hostname'], live_eventhub_config['event_hub'])
    sas_auth = authentication.SASTokenAuth.from_shared_access_key(
        uri, live_eventhub_config['key_name'], live_eventhub_config['access_key'])

    source = "amqps://{}/{}/ConsumerGroups/{}/Partitions/{}".format(
        live_eventhub_config['hostname'],
        live_eventhub_config['event_hub'],
        live_eventhub_config['consumer_group'],
        live_eventhub_config['partition'])
    with uamqp.ReceiveClient(source, auth=sas_auth, debug=False, timeout=50, prefetch=50) as receive_client:
        log.info("Created client, receiving...")
        with pytest.raises(ValueError):
            batch = receive_client.receive_message_batch(max_batch_size=100)
        batch = receive_client.receive_message_batch(max_batch_size=10)
        while batch:
            log.info("Got batch: {}".format(len(batch)))
            assert len(batch) <= 10
            for message in batch:
                annotations = message.annotations
                log.info("Sequence Number: {}".format(annotations.get(b'x-opt-sequence-number')))
            batch = receive_client.receive_message_batch(max_batch_size=10)
    log.info("Finished receiving")


def test_event_hubs_callback_receive(live_eventhub_config):
    def on_message_received(message):
        annotations = message.annotations
        log.info("Sequence Number: {}".format(annotations.get(b'x-opt-sequence-number')))
        return message

    uri = "sb://{}/{}".format(live_eventhub_config['hostname'], live_eventhub_config['event_hub'])
    sas_auth = authentication.SASTokenAuth.from_shared_access_key(
        uri, live_eventhub_config['key_name'], live_eventhub_config['access_key'])

    source = "amqps://{}/{}/ConsumerGroups/{}/Partitions/{}".format(
        live_eventhub_config['hostname'],
        live_eventhub_config['event_hub'],
        live_eventhub_config['consumer_group'],
        live_eventhub_config['partition'])

    receive_client = uamqp.ReceiveClient(source, auth=sas_auth, timeout=10, debug=False)
    log.info("Created client, receiving...")
    
    receive_client.receive_messages(on_message_received)
    log.info("Finished receiving")


def test_event_hubs_iter_receive_sync(live_eventhub_config):
    uri = "sb://{}/{}".format(live_eventhub_config['hostname'], live_eventhub_config['event_hub'])
    sas_auth = authentication.SASTokenAuth.from_shared_access_key(
        uri, live_eventhub_config['key_name'], live_eventhub_config['access_key'])
    source = "amqps://{}/{}/ConsumerGroups/{}/Partitions/{}".format(
        live_eventhub_config['hostname'],
        live_eventhub_config['event_hub'],
        live_eventhub_config['consumer_group'],
        live_eventhub_config['partition'])

    receive_client = uamqp.ReceiveClient(source, auth=sas_auth, timeout=10, debug=False, prefetch=10)
    for message in receive_client.receive_messages_iter():
        annotations = message.annotations
        log.info("Sequence Number: {}".format(annotations.get(b'x-opt-sequence-number')))


def test_event_hubs_filter_receive(live_eventhub_config):
    plain_auth = authentication.SASLPlain(
        live_eventhub_config['hostname'],
        live_eventhub_config['key_name'],
        live_eventhub_config['access_key'])
    source_url = "amqps://{}/{}/ConsumerGroups/{}/Partitions/{}".format(
        live_eventhub_config['hostname'],
        live_eventhub_config['event_hub'],
        live_eventhub_config['consumer_group'],
        live_eventhub_config['partition'])
    source = address.Source(source_url)
    source.set_filter(b"amqp.annotation.x-opt-enqueuedtimeutc > 1518731960545")

    with uamqp.ReceiveClient(source, auth=plain_auth, timeout=50, prefetch=50) as receive_client:
        log.info("Created client, receiving...")
        batch = receive_client.receive_message_batch(max_batch_size=10)
        while batch:
            for message in batch:
                annotations = message.annotations
                log.info("Partition Key: {}".format(annotations.get(b'x-opt-partition-key')))
                log.info("Sequence Number: {}".format(annotations.get(b'x-opt-sequence-number')))
                log.info("Offset: {}".format(annotations.get(b'x-opt-offset')))
                log.info("Enqueued Time: {}".format(annotations.get(b'x-opt-enqueued-time')))
                log.info("Message format: {}".format(message._message.message_format))
                log.info("{}".format(list(message.get_data())))
            batch = receive_client.receive_message_batch(max_batch_size=10)
    log.info("Finished receiving")


if __name__ == '__main__':
    config = {}
    config['hostname'] = os.environ['EVENT_HUB_HOSTNAME']
    config['event_hub'] = os.environ['EVENT_HUB_NAME']
    config['key_name'] = os.environ['EVENT_HUB_SAS_POLICY']
    config['access_key'] = os.environ['EVENT_HUB_SAS_KEY']
    config['consumer_group'] = "$Default"
    config['partition'] = "0"
    test_event_hubs_client_receive_sync(config)