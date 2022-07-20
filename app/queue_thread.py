import asyncio
import threading
from pydantic import BaseModel
from typing import Dict
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import requests
from service import Input
from service import Service
import asyncio
import aiormq
import json
from base64 import b64encode, b64decode

from aiormq.abc import DeliveredMessage
import pika

import os
from base64 import b64encode, b64decode
import json
import threading
from threading import Barrier
import os
import pika
from service import Input, Service
from functools import wraps
import ast


class RabbitBody:
    fibo: int

    def __init__(self, fibo):
        self.fibo = fibo

    def encode(self):
        dicc = {"fibo": self.fibo}
        return b64encode(json.dumps(dicc).encode())

    @staticmethod
    def decode(encoded):
        dicc = json.loads(b64decode(encoded))
        fibo = dicc["fibo"]
        return RabbitBody(fibo)


class RabbitMQConnection(object):

    def __init__(self, decorated_function):
        """
        Initializes the class
        """
        self.decorated_function = decorated_function
        self.__exchange_name = os.environ.get("EXCHANGE_NAME")
        self.__rabbitmq_host = os.environ.get("RABBITMQ_HOST")
        self.__rabbitmq_user = os.environ.get("RABBITMQ_USER")
        self.__rabbitmq_password = os.environ.get("RABBITMQ_PASSWORD")

        self.__credentials = pika.credentials.PlainCredentials(
            username=self.__rabbitmq_user,
            password=self.__rabbitmq_password)

        self.__params = pika.ConnectionParameters(
            host=self.__rabbitmq_host,
            port=5672,
            credentials=self.__credentials,
            heartbeat=600)
        self._stopping = False
        self._closing = False
        self._connection = None
        self._channel = None

        print('RabbitMQConnection init complete')

    def __call__(self, *args, **kwargs):
        print("connection called")
        self._stopping = False
        self._closing = False
        self._connection = None
        self._channel = None
        print(self)
        print(args)
        print(kwargs)
        self.args = args
        #self.rabbitmq_thread_instance = args[0]
        self.run()
        print("run finished")
        self._stopping = False
        self._closing = False
        print('self._stopping reset')
        # output = self.get_channel(self.decorated_function(*args, **kwargs))
        # return output

    def __get__(self, instance, owner):
        from functools import partial
        return partial(self.__call__, instance)

    def get_connection(self):
        """
        create a new SelectConnection
        :return: SelectConnection
        """
        return pika.SelectConnection(
                self.__params,
                on_open_callback=self.__connection_callback,
                on_open_error_callback=self.__connection_open_error_callback,
                on_close_callback=self.__unexpected_close_connection_callback,
                )

    def __connection_callback(self, conn):
        """
        Run on connecting to the server
        :param conn: The connection created in the previous step
        """
        print(f'connection created at {id(conn)}')
        self.get_channel()

    def __connection_open_error_callback(self, conn, exception):
        """
        Run on failure to connect to the server
        :param conn: The connection created in the previous step
        :param exception: The exception describing the failure
        """
        print(f'failed to create new connection at {id(conn)} due to {type(exception)}')
        if self._closing:
            self._connection.ioloop.stop()
        else:
            print(f'retrying')
            self._connection.ioloop.call_later(5, self._connection.ioloop.stop)

    def __unexpected_close_connection_callback(self, conn, message):

        if self._closing:
            print('expected close')
            self._connection.ioloop.stop()
        else:
            print(f'failed to create new connection at {id(conn)} due to {message}')
            print(f'retrying')
            #self._connection.add_timeout(5, self.reconnect)
            self._connection.ioloop.call_later(5, self._connection.ioloop.stop)

    def reconnect(self):
        """Will be invoked by the IOLoop timer if the connection is
        closed. See the on_connection_closed method.

        """
        print("Reconnecting to broker")

        # This is the old connection IOLoop instance, stop its ioloop
        try:
            self._connection.ioloop.stop()
        except Exception as error:
            self.logger.error("Error stopping connection ioloop: {0}".format(error))

        # Create a new connection
        self._connection = self.connect()

        try:
            # There is now a new connection, needs a new ioloop to run
            self._connection.ioloop.start()
        except Exception as error:
            print(f"Error starting connection ioloop: {'error'}")

            self.on_open_error_callback(self._connection, "Problem reconecting to broker")

    def get_channel(self):
        """
        Run on connecting to the server

        :param conn: The connection created in the previous step
        """
        print('channel created')
        #self._channel = self._connection.channel() # on_open_callback=channel_callback)
        self._connection.channel(on_open_callback=self.__on_channel_open)

    def __on_channel_open(self, channel):
        self.add_on_channel_close_callback(channel)
        self.decorated_function(*self.args, channel=channel)

    def add_on_channel_close_callback(self, channel):
        """This method tells pika to call the on_channel_closed method if
        RabbitMQ unexpectedly closes the channel.
        """
        channel.add_on_close_callback(self.on_channel_closed)

    def on_channel_closed(self, channel, reason):
        """Invoked by pika when RabbitMQ unexpectedly closes the channel.
        Channels are usually closed if you attempt to do something that
        violates the protocol, such as re-declare an exchange or queue with
        different parameters. In this case, we'll close the connection
        to shutdown the object.
        :param pika.channel.Channel channel: The closed channel
        :param Exception reason: why the channel was closed
        """
        print('stopping')
        #self._closing = True
        self._stopping = True
        self._connection.ioloop.stop()

    def run(self):
        """open the connection and then start the IOLoop.
        """
        print('RabbbitMQConnection starting')
        while not self._stopping:
            self._connection = None

            try:
                self._connection = self.get_connection()
                self._connection.ioloop.start()
            except KeyboardInterrupt:
                self.stop()
                if (self._connection is not None and
                        not self._connection.is_closed):
                    # Finish closing
                    self._connection.ioloop.start()
            except StopIteration:
                print('stopping')
                self._closing = True
                self._stopping = True
                #self.stop()
                self._connection.ioloop.stop()
                #if (self._connection is not None and
                #        not self._connection.is_closed):
                #    # Finish closing
                #    self._connection.ioloop.start()

        print('stopping')
        self._closing = True
        self._stopping = True
        self._connection.ioloop.stop()


class RabbitMQConnectionExampleCode(object):

    def __init__(self, decorated_function):
        """
        Initializes the class
        """
        self.decorated_function = decorated_function
        self.__exchange_name = os.environ.get("EXCHANGE_NAME")
        self.__rabbitmq_host = os.environ.get("RABBITMQ_HOST")
        self.__rabbitmq_user = os.environ.get("RABBITMQ_USER")
        self.__rabbitmq_password = os.environ.get("RABBITMQ_PASSWORD")

        self.__credentials = pika.credentials.PlainCredentials(
            username=self.__rabbitmq_user,
            password=self.__rabbitmq_password)

        self.__params = pika.ConnectionParameters(
            host=self.__rabbitmq_host,
            port=5672,
            credentials=self.__credentials,
            heartbeat=600)

        self._connection = None
        self._channel = None

        self._deliveries = None
        self._acked = None
        self._nacked = None
        self._message_number = None

        self._stopping = False
        self._url = amqp_url

        self.should_reconnect = False
        self.was_consuming = False

        self._closing = False
        self._consumer_tag = None
        self._url = amqp_url
        self._consuming = False
        # In production, experiment with higher prefetch values
        # for higher consumer throughput
        self._prefetch_count = 1

        print('RabbitMQConnection init complete')

    def __call__(self, *args, **kwargs):
        print(self)
        print(args)
        print(kwargs)
        self.rabbitmq_thread_instance = args[0]
        self.run()
        print("run finished?")
        # output = self.get_channel(self.decorated_function(*args, **kwargs))
        # return output

    def __get__(self, instance, owner):
        from functools import partial
        return partial(self.__call__, instance)

    def connect(self):
        """This method connects to RabbitMQ, returning the connection handle.
        When the connection is established, the on_connection_open method
        will be invoked by pika.
        :rtype: pika.SelectConnection
        """
        LOGGER.info('Connecting to %s', self._url)
        return pika.SelectConnection(
            pika.URLParameters(self._url),
            on_open_callback=self.on_connection_open,
            on_open_error_callback=self.on_connection_open_error,
            on_close_callback=self.on_connection_closed)

    def on_connection_open(self, _unused_connection):
        """This method is called by pika once the connection to RabbitMQ has
        been established. It passes the handle to the connection object in
        case we need it, but in this case, we'll just mark it unused.
        :param pika.SelectConnection _unused_connection: The connection
        """
        LOGGER.info('Connection opened')
        self.open_channel()

    def on_connection_open_error(self, _unused_connection, err):
        """This method is called by pika if the connection to RabbitMQ
        can't be established.
        :param pika.SelectConnection _unused_connection: The connection
        :param Exception err: The error
        """
        LOGGER.error('Connection open failed, reopening in 5 seconds: %s', err)
        self._connection.ioloop.call_later(5, self._connection.ioloop.stop)

    def on_connection_closed(self, _unused_connection, reason):
        """This method is invoked by pika when the connection to RabbitMQ is
        closed unexpectedly. Since it is unexpected, we will reconnect to
        RabbitMQ if it disconnects.
        :param pika.connection.Connection connection: The closed connection obj
        :param Exception reason: exception representing reason for loss of
            connection.
        """
        self._channel = None
        if self._stopping:
            self._connection.ioloop.stop()
        else:
            LOGGER.warning('Connection closed, reopening in 5 seconds: %s',
                           reason)
            self._connection.ioloop.call_later(5, self._connection.ioloop.stop)

    def open_channel(self):
        """This method will open a new channel with RabbitMQ by issuing the
        Channel.Open RPC command. When RabbitMQ confirms the channel is open
        by sending the Channel.OpenOK RPC reply, the on_channel_open method
        will be invoked.
        """
        LOGGER.info('Creating a new channel')
        self._connection.channel(on_open_callback=self.on_channel_open)

    def on_channel_open(self, channel):
        """This method is invoked by pika when the channel has been opened.
        The channel object is passed in so we can make use of it.
        Since the channel is now open, we'll declare the exchange to use.
        :param pika.channel.Channel channel: The channel object
        """
        LOGGER.info('Channel opened')
        self._channel = channel
        self.add_on_channel_close_callback()
        self.setup_exchange(self.EXCHANGE)

    def add_on_channel_close_callback(self):
        """This method tells pika to call the on_channel_closed method if
        RabbitMQ unexpectedly closes the channel.
        """
        LOGGER.info('Adding channel close callback')
        self._channel.add_on_close_callback(self.on_channel_closed)

    def on_channel_closed(self, channel, reason):
        """Invoked by pika when RabbitMQ unexpectedly closes the channel.
        Channels are usually closed if you attempt to do something that
        violates the protocol, such as re-declare an exchange or queue with
        different parameters. In this case, we'll close the connection
        to shutdown the object.
        :param pika.channel.Channel channel: The closed channel
        :param Exception reason: why the channel was closed
        """
        LOGGER.warning('Channel %i was closed: %s', channel, reason)
        self._channel = None
        if not self._stopping:
            self._connection.close()

    def setup_exchange(self, exchange_name):
        """Setup the exchange on RabbitMQ by invoking the Exchange.Declare RPC
        command. When it is complete, the on_exchange_declareok method will
        be invoked by pika.
        :param str|unicode exchange_name: The name of the exchange to declare
        """
        LOGGER.info('Declaring exchange %s', exchange_name)
        # Note: using functools.partial is not required, it is demonstrating
        # how arbitrary data can be passed to the callback when it is called
        cb = functools.partial(
            self.on_exchange_declareok, userdata=exchange_name)
        self._channel.exchange_declare(
            exchange=exchange_name,
            exchange_type=self.EXCHANGE_TYPE,
            callback=cb)

    def on_exchange_declareok(self, _unused_frame, userdata):
        """Invoked by pika when RabbitMQ has finished the Exchange.Declare RPC
        command.
        :param pika.Frame.Method unused_frame: Exchange.DeclareOk response frame
        :param str|unicode userdata: Extra user data (exchange name)
        """
        LOGGER.info('Exchange declared: %s', userdata)
        self.setup_queue(self.QUEUE)

    def setup_queue(self, queue_name):
        """Setup the queue on RabbitMQ by invoking the Queue.Declare RPC
        command. When it is complete, the on_queue_declareok method will
        be invoked by pika.
        :param str|unicode queue_name: The name of the queue to declare.
        """
        LOGGER.info('Declaring queue %s', queue_name)
        self._channel.queue_declare(
            queue=queue_name, callback=self.on_queue_declareok)

    def on_queue_declareok(self, _unused_frame):
        """Method invoked by pika when the Queue.Declare RPC call made in
        setup_queue has completed. In this method we will bind the queue
        and exchange together with the routing key by issuing the Queue.Bind
        RPC command. When this command is complete, the on_bindok method will
        be invoked by pika.
        :param pika.frame.Method method_frame: The Queue.DeclareOk frame
        """
        LOGGER.info('Binding %s to %s with %s', self.EXCHANGE, self.QUEUE,
                    self.ROUTING_KEY)
        self._channel.queue_bind(
            self.QUEUE,
            self.EXCHANGE,
            routing_key=self.ROUTING_KEY,
            callback=self.on_bindok)

    def on_bindok(self, _unused_frame):
        """This method is invoked by pika when it receives the Queue.BindOk
        response from RabbitMQ. Since we know we're now setup and bound, it's
        time to start publishing."""
        LOGGER.info('Queue bound')
        self.start_publishing()

    def start_publishing(self):
        """This method will enable delivery confirmations and schedule the
        first message to be sent to RabbitMQ
        """
        LOGGER.info('Issuing consumer related RPC commands')
        self.enable_delivery_confirmations()
        self.schedule_next_message()

    def enable_delivery_confirmations(self):
        """Send the Confirm.Select RPC method to RabbitMQ to enable delivery
        confirmations on the channel. The only way to turn this off is to close
        the channel and create a new one.
        When the message is confirmed from RabbitMQ, the
        on_delivery_confirmation method will be invoked passing in a Basic.Ack
        or Basic.Nack method from RabbitMQ that will indicate which messages it
        is confirming or rejecting.
        """
        LOGGER.info('Issuing Confirm.Select RPC command')
        self._channel.confirm_delivery(self.on_delivery_confirmation)

    def on_delivery_confirmation(self, method_frame):
        """Invoked by pika when RabbitMQ responds to a Basic.Publish RPC
        command, passing in either a Basic.Ack or Basic.Nack frame with
        the delivery tag of the message that was published. The delivery tag
        is an integer counter indicating the message number that was sent
        on the channel via Basic.Publish. Here we're just doing house keeping
        to keep track of stats and remove message numbers that we expect
        a delivery confirmation of from the list used to keep track of messages
        that are pending confirmation.
        :param pika.frame.Method method_frame: Basic.Ack or Basic.Nack frame
        """
        confirmation_type = method_frame.method.NAME.split('.')[1].lower()
        LOGGER.info('Received %s for delivery tag: %i', confirmation_type,
                    method_frame.method.delivery_tag)
        if confirmation_type == 'ack':
            self._acked += 1
        elif confirmation_type == 'nack':
            self._nacked += 1
        self._deliveries.remove(method_frame.method.delivery_tag)
        LOGGER.info(
            'Published %i messages, %i have yet to be confirmed, '
            '%i were acked and %i were nacked', self._message_number,
            len(self._deliveries), self._acked, self._nacked)

    def schedule_next_message(self):
        """If we are not closing our connection to RabbitMQ, schedule another
        message to be delivered in PUBLISH_INTERVAL seconds.
        """
        LOGGER.info('Scheduling next message for %0.1f seconds',
                    self.PUBLISH_INTERVAL)
        self._connection.ioloop.call_later(self.PUBLISH_INTERVAL,
                                           self.publish_message)

    def publish_message(self):
        """If the class is not stopping, publish a message to RabbitMQ,
        appending a list of deliveries with the message number that was sent.
        This list will be used to check for delivery confirmations in the
        on_delivery_confirmations method.
        Once the message has been sent, schedule another message to be sent.
        The main reason I put scheduling in was just so you can get a good idea
        of how the process is flowing by slowing down and speeding up the
        delivery intervals by changing the PUBLISH_INTERVAL constant in the
        class.
        """
        if self._channel is None or not self._channel.is_open:
            return

        hdrs = {u'مفتاح': u' قيمة', u'键': u'值', u'キー': u'値'}
        properties = pika.BasicProperties(
            app_id='example-publisher',
            content_type='application/json',
            headers=hdrs)

        message = u'مفتاح قيمة 键 值 キー 値'
        self._channel.basic_publish(self.EXCHANGE, self.ROUTING_KEY,
                                    json.dumps(message, ensure_ascii=False),
                                    properties)
        self._message_number += 1
        self._deliveries.append(self._message_number)
        LOGGER.info('Published message # %i', self._message_number)
        self.schedule_next_message()

    def run(self):
        """Run the example code by connecting and then starting the IOLoop.
        """
        while not self._stopping:
            self._connection = None
            self._deliveries = []
            self._acked = 0
            self._nacked = 0
            self._message_number = 0

            try:
                self._connection = self.connect()
                self._connection.ioloop.start()
            except KeyboardInterrupt:
                self.stop()
                if (self._connection is not None and
                        not self._connection.is_closed):
                    # Finish closing
                    self._connection.ioloop.start()

        LOGGER.info('Stopped')

    def stop(self):
        """Stop the example by closing the channel and connection. We
        set a flag here so that we stop scheduling new messages to be
        published. The IOLoop is started because this method is
        invoked by the Try/Catch below when KeyboardInterrupt is caught.
        Starting the IOLoop again will allow the publisher to cleanly
        disconnect from RabbitMQ.
        """
        LOGGER.info('Stopping')
        self._stopping = True
        self.close_channel()
        self.close_connection()

    def close_channel(self):
        """Invoke this command to close the channel with RabbitMQ by sending
        the Channel.Close RPC command.
        """
        if self._channel is not None:
            LOGGER.info('Closing the channel')
            self._channel.close()

    def close_connection(self):
        """This method closes the connection to RabbitMQ."""
        if self._connection is not None:
            LOGGER.info('Closing connection')
            self._connection.close()

    def close_connection(self):
        self._consuming = False
        if self._connection.is_closing or self._connection.is_closed:
            LOGGER.info('Connection is closing or already closed')
        else:
            LOGGER.info('Closing connection')
            self._connection.close()

    def on_connection_open_error(self, _unused_connection, err):
        """This method is called by pika if the connection to RabbitMQ
        can't be established.
        :param pika.SelectConnection _unused_connection: The connection
        :param Exception err: The error
        """
        LOGGER.error('Connection open failed: %s', err)
        self.reconnect()

    def setup_queue(self, queue_name):
        """Setup the queue on RabbitMQ by invoking the Queue.Declare RPC
        command. When it is complete, the on_queue_declareok method will
        be invoked by pika.
        :param str|unicode queue_name: The name of the queue to declare.
        """
        LOGGER.info('Declaring queue %s', queue_name)
        cb = functools.partial(self.on_queue_declareok, userdata=queue_name)
        self._channel.queue_declare(queue=queue_name, callback=cb)

    def on_queue_declareok(self, _unused_frame, userdata):
        """Method invoked by pika when the Queue.Declare RPC call made in
        setup_queue has completed. In this method we will bind the queue
        and exchange together with the routing key by issuing the Queue.Bind
        RPC command. When this command is complete, the on_bindok method will
        be invoked by pika.
        :param pika.frame.Method _unused_frame: The Queue.DeclareOk frame
        :param str|unicode userdata: Extra user data (queue name)
        """
        queue_name = userdata
        LOGGER.info('Binding %s to %s with %s', self.EXCHANGE, queue_name,
                    self.ROUTING_KEY)
        cb = functools.partial(self.on_bindok, userdata=queue_name)
        self._channel.queue_bind(
            queue_name,
            self.EXCHANGE,
            routing_key=self.ROUTING_KEY,
            callback=cb)

    def on_bindok(self, _unused_frame, userdata):
        """Invoked by pika when the Queue.Bind method has completed. At this
        point we will set the prefetch count for the channel.
        :param pika.frame.Method _unused_frame: The Queue.BindOk response frame
        :param str|unicode userdata: Extra user data (queue name)
        """
        LOGGER.info('Queue bound: %s', userdata)
        self.set_qos()

    def set_qos(self):
        """This method sets up the consumer prefetch to only be delivered
        one message at a time. The consumer must acknowledge this message
        before RabbitMQ will deliver another one. You should experiment
        with different prefetch values to achieve desired performance.
        """
        self._channel.basic_qos(
            prefetch_count=self._prefetch_count, callback=self.on_basic_qos_ok)

    def on_basic_qos_ok(self, _unused_frame):
        """Invoked by pika when the Basic.QoS method has completed. At this
        point we will start consuming messages by calling start_consuming
        which will invoke the needed RPC commands to start the process.
        :param pika.frame.Method _unused_frame: The Basic.QosOk response frame
        """
        LOGGER.info('QOS set to: %d', self._prefetch_count)
        self.start_consuming()

    def start_consuming(self):
        """This method sets up the consumer by first calling
        add_on_cancel_callback so that the object is notified if RabbitMQ
        cancels the consumer. It then issues the Basic.Consume RPC command
        which returns the consumer tag that is used to uniquely identify the
        consumer with RabbitMQ. We keep the value to use it when we want to
        cancel consuming. The on_message method is passed in as a callback pika
        will invoke when a message is fully received.
        """
        LOGGER.info('Issuing consumer related RPC commands')
        self.add_on_cancel_callback()
        self._consumer_tag = self._channel.basic_consume(
            self.QUEUE, self.on_message)
        self.was_consuming = True
        self._consuming = True

    def add_on_cancel_callback(self):
        """Add a callback that will be invoked if RabbitMQ cancels the consumer
        for some reason. If RabbitMQ does cancel the consumer,
        on_consumer_cancelled will be invoked by pika.
        """
        LOGGER.info('Adding consumer cancellation callback')
        self._channel.add_on_cancel_callback(self.on_consumer_cancelled)

    def on_consumer_cancelled(self, method_frame):
        """Invoked by pika when RabbitMQ sends a Basic.Cancel for a consumer
        receiving messages.
        :param pika.frame.Method method_frame: The Basic.Cancel frame
        """
        LOGGER.info('Consumer was cancelled remotely, shutting down: %r',
                    method_frame)
        if self._channel:
            self._channel.close()

    def on_message(self, _unused_channel, basic_deliver, properties, body):
        """Invoked by pika when a message is delivered from RabbitMQ. The
        channel is passed for your convenience. The basic_deliver object that
        is passed in carries the exchange, routing key, delivery tag and
        a redelivered flag for the message. The properties passed in is an
        instance of BasicProperties with the message properties and the body
        is the message that was sent.
        :param pika.channel.Channel _unused_channel: The channel object
        :param pika.Spec.Basic.Deliver: basic_deliver method
        :param pika.Spec.BasicProperties: properties
        :param bytes body: The message body
        """
        LOGGER.info('Received message # %s from %s: %s',
                    basic_deliver.delivery_tag, properties.app_id, body)
        self.acknowledge_message(basic_deliver.delivery_tag)

    def acknowledge_message(self, delivery_tag):
        """Acknowledge the message delivery from RabbitMQ by sending a
        Basic.Ack RPC method for the delivery tag.
        :param int delivery_tag: The delivery tag from the Basic.Deliver frame
        """
        LOGGER.info('Acknowledging message %s', delivery_tag)
        self._channel.basic_ack(delivery_tag)

    def stop_consuming(self):
        """Tell RabbitMQ that you would like to stop consuming by sending the
        Basic.Cancel RPC command.
        """
        if self._channel:
            LOGGER.info('Sending a Basic.Cancel RPC command to RabbitMQ')
            cb = functools.partial(
                self.on_cancelok, userdata=self._consumer_tag)
            self._channel.basic_cancel(self._consumer_tag, cb)

    def on_cancelok(self, _unused_frame, userdata):
        """This method is invoked by pika when RabbitMQ acknowledges the
        cancellation of a consumer. At this point we will close the channel.
        This will invoke the on_channel_closed method once the channel has been
        closed, which will in-turn close the connection.
        :param pika.frame.Method _unused_frame: The Basic.CancelOk frame
        :param str|unicode userdata: Extra user data (consumer tag)
        """
        self._consuming = False
        LOGGER.info(
            'RabbitMQ acknowledged the cancellation of the consumer: %s',
            userdata)
        self.close_channel()

    def close_channel(self):
        """Call to close the channel with RabbitMQ cleanly by issuing the
        Channel.Close RPC command.
        """
        LOGGER.info('Closing the channel')
        self._channel.close()

    def run(self):
        """Run the example consumer by connecting to RabbitMQ and then
        starting the IOLoop to block and allow the SelectConnection to operate.
        """
        self._connection = self.connect()
        self._connection.ioloop.start()

    def stop(self):
        """Cleanly shutdown the connection to RabbitMQ by stopping the consumer
        with RabbitMQ. When RabbitMQ confirms the cancellation, on_cancelok
        will be invoked by pika, which will then closing the channel and
        connection. The IOLoop is started again because this method is invoked
        when CTRL-C is pressed raising a KeyboardInterrupt exception. This
        exception stops the IOLoop which needs to be running for pika to
        communicate with RabbitMQ. All of the commands issued prior to starting
        the IOLoop will be buffered but not processed.
        """
        if not self._closing:
            self._closing = True
            LOGGER.info('Stopping')
            if self._consuming:
                self.stop_consuming()
                self._connection.ioloop.start()
            else:
                self._connection.ioloop.stop()
            LOGGER.info('Stopped')


class ReconnectingExampleConsumer(object):
    """This is an example consumer that will reconnect if the nested
    ExampleConsumer indicates that a reconnect is necessary.
    """

    def __init__(self, amqp_url):
        self._reconnect_delay = 0
        self._amqp_url = amqp_url
        self._consumer = ExampleConsumer(self._amqp_url)

    def run(self):
        while True:
            try:
                self._consumer.run()
            except KeyboardInterrupt:
                self._consumer.stop()
                break
            self._maybe_reconnect()

    def _maybe_reconnect(self):
        if self._consumer.should_reconnect:
            self._consumer.stop()
            reconnect_delay = self._get_reconnect_delay()
            LOGGER.info('Reconnecting after %d seconds', reconnect_delay)
            time.sleep(reconnect_delay)
            self._consumer = ExampleConsumer(self._amqp_url)

    def _get_reconnect_delay(self):
        if self._consumer.was_consuming:
            self._reconnect_delay = 0
        else:
            self._reconnect_delay += 1
        if self._reconnect_delay > 30:
            self._reconnect_delay = 30
        return self._reconnect_delay


class RabbitMQPublish:
    """
    RabbitMQ operations
    """

    def __init__(self, publish_function):
        """
        Initializes the class
        """
        self.publish_function = publish_function
        self._barrier = Barrier(2, timeout=120)
        self.__exchange_name = os.environ.get("EXCHANGE_NAME")
        self.__rabbitmq_host = os.environ.get("RABBITMQ_HOST")
        self.__rabbitmq_user = os.environ.get("RABBITMQ_USER")
        self.__rabbitmq_password = os.environ.get("RABBITMQ_PASSWORD")
        self.__params = pika.ConnectionParameters(
            host=self.__rabbitmq_host,
            port=5672,
            credentials=pika.credentials.PlainCredentials(username=self.__rabbitmq_user,
                                                          password=self.__rabbitmq_password),
            heartbeat=600
        )
        print('RabbitMQPublish init complete')

    def __call__(self, *args, **kwargs):
        print('RabbitMQ call running')
        print(f"args: {args}, kwargs: {kwargs}")

        self.output = args[0]
        self.publish_exchange = args[1]
        self.publish_queue = args[2]
        print(f"got kwargs: \n 1. output {self.output} \n 2. publish_exchange {self.publish_exchange} \n 3. publish_queue {self.publish_queue}")
        self.run()

    def connection_callback(self, conn):
        """
        Run on connecting to the server

        :param conn: The connection created in the previous step
        """
        print('connection_callback')
        self._connection.channel(on_open_callback=self.channel_callback)

    def channel_callback(self, ch):
        """
        Publish to the channel. You can use other methods with callbacks but only the channel
        creation method provides a channel. Other methods provide a frame you can choose to
        discard.

        :param ch: The channel established
        """
        print('channel_callback')
        self.publish_function(ch, self.output, self.publish_exchange, self.publish_queue)
        print('publish function done')
        #self._barrier.wait(timeout=1)
        ch.close()
        #self._connection.close()

    def run(self):
        """
        Runs the example
        """
        def run_io_loop(conn):
            conn.ioloop.start()

        self._connection = pika.SelectConnection(
            self.__params, on_open_callback=self.connection_callback)
        if self._connection:
            print("got connection")
            #self._connection.ioloop.start()
            t = threading.Thread(target=run_io_loop, args=(self._connection, ))
            t.start()
            #self._barrier.wait(timeout=60)
            #self._connection.ioloop.stop()
        else:
            raise ValueError

    def consumer(self):
        """
        Run the example.
        """

        self._connection = AsyncioConnection(parameters=self.__params,
                                             on_open_callback=self.open_connection_callback,
                                             #on_open_error_callback=self.open_connection_error_callback,
                                             #on_close_callback=self.close_connection_callback
                                             )
        if self._connection:
            self._connection.ioloop.run_forever()
            return self._closing


class RabbitMQThread(threading.Thread):
    """
    a class to tie all the functions of my RabbitMQ workflow together,
    1) thread CONSUMES from RabbitMQ
    2) a CALLBACK is triggered that PROCESSES data from queue
    3) PROCESS output is PUBLISHED to rabbitMQ
    """
    def __init__(self, FRONT_END_URL=None):
        threading.Thread.__init__(self)
        try:
            pod_type = os.environ.get("POD_TYPE")
        except:
            pod_type = None
        print(f'pod_type: {pod_type}')
        self.__rabbitmq_listen_queue = None
        self.__exchange_name = '' #os.environ.get("EXCHANGE_NAME")
        self.FRONT_END_URL = f'http://{os.environ.get("FRONTEND_URL")}/log/'
        print(f'frontend url is: {self.FRONT_END_URL}')
        if pod_type == 'nt':
            self.__rabbitmq_listen_queue = os.environ.get("RABBITMQ_LISTEN_QUEUE")
        else:
            #t = threading.Thread(target=self.get_queue, args=os.environ.get("RABBITMQ_LISTEN_QUEUE"))
            #t.start()
            #while not self.__rabbitmq_listen_queue:
            #    print("waiting for listen queue")
            get_queue_call = self.get_queue(os.environ.get("RABBITMQ_LISTEN_QUEUE"))
            get_queue_call = None
            #    time.sleep(10)
            print(f'listening to {self.__rabbitmq_listen_queue}')

    @RabbitMQConnection
    def get_queue(self, service_name, channel=None):
        print(channel)
        print(type(channel))
        print("getting listen queue")

        #channel.basic_qos(prefetch_count=1)

        channel.basic_consume(queue=f'{service_name}-current-designs',
                              on_message_callback=self.read_current_designs_queue,
                              auto_ack=False)

    def read_current_designs_queue(self, ch, method, properties, body):
        print('get design name')
        print(" [x] Received %r" % body)
        body = json.loads(b64decode(body))
        design_target = body['design_target']
        #self.design_target = design_target
        ch.basic_nack(method.delivery_tag, requeue=True)
        if self.__rabbitmq_listen_queue is None:
            print('no listen queue established')
            try:
                self.check_for_consumers(design_target)
                self.design_target = design_target
            except ValueError:
                pass

        else:
            print('listen queue established, closing current designs queue')
            ch.close()

    @RabbitMQConnection
    def check_for_consumers(self, design_target, channel=None):

        self.channel = channel

        print(f'checking {os.environ.get("RABBITMQ_LISTEN_QUEUE")}-{design_target}')

        self.channel.queue_declare(
            queue=f'{os.environ.get("RABBITMQ_LISTEN_QUEUE")}-{design_target}',
            durable=True,
            exclusive=False,
            callback=self.on_queue_declareok
        )
        print("done")

    def on_queue_declareok(self, declared_queue):

        print(f'declared_queue: {declared_queue}')

        #try:
        if declared_queue.method.consumer_count == 0:
            print("found a queue with no consumer")
            self.__rabbitmq_listen_queue = declared_queue.method.queue
            #RabbitMQConnection._stopping = True
            #raise StopIteration
            #RabbitMQConnection.close()
            self.channel.close()
            self.channel = None
            #self.design_target = design_target
            return self.__rabbitmq_listen_queue
        else:
            #self.channel.close()
            #self.channel = None
            print('this queue already has a consumer')
            raise ValueError
        #except Exception as e:
        #    print(e)

    @RabbitMQConnection
    def consume(self, channel=None):

        #channel = self._connection.channel()

        channel.queue_declare(
            queue=self.__rabbitmq_listen_queue,
            durable=True,
            exclusive=False,
            #auto_delete=False
        )

        channel.basic_consume(queue=self.__rabbitmq_listen_queue, on_message_callback=self.callback, auto_ack=True)

        print(' [*] Waiting for messages. To exit press CTRL+C')
        #channel.start_consuming()

    def callback(self, ch, method, properties, body):
        print(" [x] Received %r" % body)
        body = json.loads(b64decode(body))
        print(body)
        print(type(body))
        if properties.reply_to:
            #publish_exchange = properties.reply_to['exchange']
            publish_exchange = ''
            publish_queue = properties.reply_to
        else:
            publish_exchange = self.__exchange_name
            publish_queue = f"{body['pathway'][0]}-{self.design_target}"
        output = self.process(body)
        #design_still_running = self.check_current_designs()
        self.publish(ch, output, publish_exchange, publish_queue)

    def process(self, input):
        print('processing')
        service = Service(input)
        status_update = service.get_status_update()
        status_update['design_target'] = self.design_target
        print(status_update)
        log_response = requests.post(self.FRONT_END_URL, json=status_update)
        print(f'log response is {log_response}')
        output = service.run(input)
        status_update = service.get_status_update()
        if status_update['status'] == 'done':
            #response = requests.post(NEXT_SERVICE_URL, json=output)
            #loop = asyncio.get_event_loop()
            #asyncio.run(self.push_to_rabbit(output))
            #print("Sent")
            #print(response)
            #pass
            return output
        else:
            status_update = service.get_status_update()
            status_update['design_target'] = self.design_target
            print(status_update['status'])
            log_response = requests.post(self.FRONT_END_URL, json=status_update)
            print(f'log response is {log_response}')
            return None

    #@RabbitMQConnection
    def publish(self, channel, output, publish_exchange, publish_queue):
        print("publish function")
        # Declare the queue
        #channel.queue_declare(
        #    queue=publish_queue,
        #    durable=True,
        #    exclusive=False,
        #    #auto_delete=False
        #)

        #_barrier = Barrier(2, timeout=120)
        print("queue declared")
        if isinstance(output, list):
            print('output is list')
            properties = pika.BasicProperties(content_type='application/json')
            for item in output:
                print(item)
                channel.basic_publish(exchange='', #publish_exchange,
                                      routing_key=publish_queue,
                                      properties=properties,
                                      body=b64encode(json.dumps(item).encode()))
                #_barrier.wait(timeout=6)
                print('item pushed')
        else:
            print('output not list')

    def get_q_size(self):
        # ...

        # Re-declare the queue with passive flag
        res = channel.queue_declare(
            # callback=on_callback,
            queue="test",
            durable=True,
            exclusive=False,
            #auto_delete=False,
            passive=True
        )
        print(f'Messages in queue: {res.method.message_count}')

    def run(self):
        """
        a function that runs consume
        """
        #while not self._stop_event.isSet():
        self.consume()

    def stop(self):
        self._stop_event.set()


class RabbitMQThreadBackup(threading.Thread):
    """
    a class to tie all the functions of my RabbitMQ workflow together,
    1) thread CONSUMES from RabbitMQ
    2) a CALLBACK is triggered that PROCESSES data from queue
    3) PROCESS output is PUBLISHED to rabbitMQ
    """
    def __init__(self, FRONT_END_URL=None):
        threading.Thread.__init__(self)
        self.FRONT_END_URL = FRONT_END_URL
        self.__exchange_name = os.environ.get("EXCHANGE_NAME")
        self.__rabbitmq_host = os.environ.get("RABBITMQ_HOST")
        self.__rabbitmq_user = os.environ.get("RABBITMQ_USER")
        self.__rabbitmq_password = os.environ.get("RABBITMQ_PASSWORD")
        self._stop_event = threading.Event()
        self.__params = pika.ConnectionParameters(
            host=self.__rabbitmq_host,
            port=5672,
            heartbeat=600,
            credentials=pika.credentials.PlainCredentials(username=self.__rabbitmq_user,
                                                          password=self.__rabbitmq_password),
        )
        self._connection = pika.BlockingConnection(self.__params)
        try:
            pod_type = os.environ.get("POD_TYPE")
        except:
            pod_type = None
        print(f'pod_type: {pod_type}')
        if pod_type == 'nt':
            self.__rabbitmq_listen_queue = os.environ.get("RABBITMQ_LISTEN_QUEUE")
        else:
            self.__rabbitmq_listen_queue = self.get_queue(os.environ.get("RABBITMQ_LISTEN_QUEUE"))
        #self.killed_designs = killed_designs

    @staticmethod
    def __connection_callback():
        print("connection established")

    def get_queue(self, listen_queue):
        print("getting listen queue")
        self._connection = pika.BlockingConnection(
            self.__params)

        self.queue_channel = self._connection.channel()

        self.queue_channel.basic_consume(queue=f'{os.environ.get("RABBITMQ_LISTEN_QUEUE")}-current-designs',
                                         on_message_callback=self.read_current_designs_queue,
                                         auto_ack=False)

        #print(' [*] Waiting for messages. To exit press CTRL+C')
        self.queue_channel.start_consuming()
        print(f'listening to {self.__rabbitmq_listen_queue}')
        return self.__rabbitmq_listen_queue

    def read_current_designs_queue(self, ch, method, properties, body):
        print('get design name')
        print(" [x] Received %r" % body)
        body = json.loads(b64decode(body))
        design_target = body['design_target']

        # check if the {step}-{target} queue has any consumers
        channel = self._connection.channel()

        print(f'checking {os.environ.get("RABBITMQ_LISTEN_QUEUE")}-{design_target}')

        declared_queue = channel.queue_declare(
            queue=f'{os.environ.get("RABBITMQ_LISTEN_QUEUE")}-{design_target}',
            durable=True,
            exclusive=False
            # auto_delete=False
        )

        ch.basic_nack(method.delivery_tag, requeue=True)

        try:
            print("still going")
            if declared_queue.method.consumer_count == 0:
                self.__rabbitmq_listen_queue = f'{os.environ.get("RABBITMQ_LISTEN_QUEUE")}-{design_target}'
                self.design_target = design_target
                #self.queue_channel.stop_consuming()
                ch.stop_consuming()
                ch.basic_nack(method.delivery_tag, requeue=True)
        except Exception as e:
            print(e)

    def consume(self):

        channel = self._connection.channel()

        channel.queue_declare(
            queue=self.__rabbitmq_listen_queue,
            durable=True,
            exclusive=False,
            #auto_delete=False
        )

        channel.basic_consume(queue=self.__rabbitmq_listen_queue, on_message_callback=self.callback, auto_ack=True)

        print(' [*] Waiting for messages. To exit press CTRL+C')
        channel.start_consuming()

    def callback(self, ch, method, properties, body):
        print(" [x] Received %r" % body)
        body = json.loads(b64decode(body))
        print(body)
        print(type(body))
        if properties.reply_to:
            #publish_exchange = properties.reply_to['exchange']
            publish_exchange = ''
            publish_queue = properties.reply_to
        else:
            publish_exchange = self.__exchange_name
            publish_queue = f"{body['pathway'][0]}-{self.design_target}"
        output = self.process(body)
        #design_still_running = self.check_current_designs()
        self.publish(output, publish_exchange, publish_queue)

    def process(self, input):

        service = Service(input)
        status_update = service.get_status_update()
        log_response = requests.post(self.FRONT_END_URL, json=service.get_status_update())
        output = service.run(input)
        status_update = service.get_status_update()
        if status_update['status'] == 'done':
            #response = requests.post(NEXT_SERVICE_URL, json=output)
            #loop = asyncio.get_event_loop()
            #asyncio.run(self.push_to_rabbit(output))
            #print("Sent")
            #print(response)
            #pass
            return output
        else:
            print(status_update['status'])
            log_response = requests.post(self.FRONT_END_URL, json=service.get_status_update())
            return None

    @staticmethod
    @RabbitMQPublish
    def publish(channel, output, publish_exchange, publish_queue):
        print("publish function")
        # Declare the queue
        #channel.queue_declare(
        #    queue=publish_queue,
        #    durable=True,
        #    exclusive=False,
        #    #auto_delete=False
        #)

        _barrier = Barrier(2, timeout=120)
        print("queue declared")
        if isinstance(output, list):
            print('output is list')
            properties = pika.BasicProperties(content_type='application/json')
            for item in output:
                print(item)
                channel.basic_publish(exchange='', #publish_exchange,
                                      routing_key=publish_queue,
                                      properties=properties,
                                      body=b64encode(json.dumps(item).encode()))
                #_barrier.wait(timeout=6)
                print('item pushed')
        else:
            print('output not list')

    def get_q_size(self):
        # ...

        # Re-declare the queue with passive flag
        res = channel.queue_declare(
            # callback=on_callback,
            queue="test",
            durable=True,
            exclusive=False,
            #auto_delete=False,
            passive=True
        )
        print(f'Messages in queue: {res.method.message_count}')

    def run(self):
        """
        a function that runs consume
        """
        #while not self._stop_event.isSet():
        self.consume()

    def stop(self):
        self._stop_event.set()


class SequentialQueueThread(threading.Thread):
    """
    a class to tie all the functions of my queue workflow together,
    this thread queues and processes requests, but does NOT send the requests
    1) post requests are added to an intake queue
    2) post requests are taken from this queue and processed
    3) processed post requests are added to an outlet queue
    4) processed post requests are taken from this queue and sent on BY THE POST THREAD (not this thread).
    """
    def __init__(self, intake_q=asyncio.Queue(maxsize=0), FRONT_END_URL=None,  outlet_q=asyncio.Queue(maxsize=0)):
        threading.Thread.__init__(self)
        self.intake_q = intake_q
        self.outlet_q = outlet_q
        self.FRONT_END_URL = FRONT_END_URL
        self._stop_event = threading.Event()

    #class Input(BaseModel):
    #    design_id: str
    #    data: list
    #    priority: str
    #    metadata: Dict[str, list]
    #    pathway: list

    async def intake(self, input: Input):
        """
        a function defining how to add items to the intake queue
        """
        self.intake_q.put_nowait(input)
        return HTMLResponse(content="ready", status_code=200)

    def publish(self, output):

        exchange_name = os.environ.get("EXCHANGE_NAME")
        rabbitmq_host = os.environ.get("RABBITMQ_HOST")
        rabbitmq_user = os.environ.get("RABBITMQ_USER")
        rabbitmq_password = os.environ.get("RABBITMQ_PASSWORD")

        params = pika.ConnectionParameters(
            host=rabbitmq_host,
            port=5672,
            credentials=pika.credentials.PlainCredentials(username=rabbitmq_user, password=rabbitmq_password),
        )

        # Open a connection to RabbitMQ on localhost using all default parameters
        connection = pika.BlockingConnection(parameters=params)

        # Open the channel
        channel = connection.channel()

        # Declare the queue
        channel.queue_declare(
            queue="clusterservice",
            durable=True,
            exclusive=False,
            #auto_delete=False
        )

        channel.basic_publish(exchange='', routing_key='clusterservice', body=b64encode(json.dumps(output).encode()))

    def process(self, input: Input):
        NEXT_SERVICE_URL = input.pathway[0]
        service = Service(input)
        log_response = requests.post(self.FRONT_END_URL, json=service.get_status_update())
        output = service.run(input)
        status_update = service.get_status_update()
        if status_update['status'] == 'done':
            #response = requests.post(NEXT_SERVICE_URL, json=output)
            #loop = asyncio.get_event_loop()
            self.publish(output)
            print("Sent")
            #print(response)
            #pass
        else:
            print(status)
            log_response = requests.post(self.FRONT_END_URL, json=service.get_status_update())

    def run(self):
        """
        a function that checks if the intake queue is not empty,
        and if it is not empty, calls the process function.
        this should run in the class as a deamon thread.
        """
        while not self._stop_event.isSet():
            if not self.intake_q.empty():

                input = self.intake_q.get_nowait()

                self.process(input)

                # send a signal to the queue that the job is done
                self.intake_q.task_done()

    def stop(self):
        self._stop_event.set()

