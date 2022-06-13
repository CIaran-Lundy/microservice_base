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
        self.__rabbitmq_listen_queue = self.get_queue(os.environ.get("RABBITMQ_LISTEN_QUEUE"))

    @staticmethod
    def __connection_callback():
        print("connection established")

    def get_queue(self, listen_queue):
        print("getting listen queue")
        self._connection = pika.BlockingConnection(
            self.__params)

        self.queue_channel = self._connection.channel()

        self.queue_channel.queue_declare(
            queue='current-designs',
            durable=True,
            exclusive=False,
        )

        self.queue_channel.basic_consume(queue='current-designs',
                                         on_message_callback=self.read_current_designs_queue,
                                         auto_ack=False)

        #print(' [*] Waiting for messages. To exit press CTRL+C')
        self.queue_channel.start_consuming()
        print(f'listening to {self.__rabbitmq_listen_queue}')
        return self.__rabbitmq_listen_queue

    def read_current_designs_queue(self, ch, method, properties, body):
        print(" [x] Received %r" % body)
        body = json.loads(b64decode(body))
        design_target = body['design_target']

        channel = self._connection.channel()

        print(f'checking {os.environ.get("RABBITMQ_LISTEN_QUEUE")}-{design_target}')
        declared_queue = channel.queue_declare(
            queue=f'{os.environ.get("RABBITMQ_LISTEN_QUEUE")}-{design_target}',
            durable=True,
            exclusive=False,
            passive=True
            # auto_delete=False
        )
        try:
            if declared_queue.method.consumer_count == 0:
                self.__rabbitmq_listen_queue = f'{os.environ.get("RABBITMQ_LISTEN_QUEUE")}-{design_target}'
                self.design_target = design_target
                self.queue_channel.stop_consuming()
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
        self.publish(output, publish_exchange, publish_queue)

    def process(self, input):

        service = Service(input)
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
        channel.queue_declare(
            queue=publish_queue,
            durable=True,
            exclusive=False,
            #auto_delete=False
        )
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

