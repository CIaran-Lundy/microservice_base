from fastapi.responses import HTMLResponse
import requests
import asyncio
from base64 import b64encode, b64decode
import json
import threading
import os
import pika
from service import Input, Service
import time
import logging


pod_name = os.environ.get("POD_NAME")

try:
    pod_type = os.environ.get("POD_TYPE")
except:
    pod_type = None


logging.basicConfig(
                    level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    handlers=[
        logging.FileHandler(filename=f'{pod_name}.log'),
        logging.StreamHandler()
    ])


class RabbitMQConnection(object):
    """
    a class to manage connecting to rabbitMQ cluster.
    -> operates as a decorator
    -> commands it decorates will:
        - have a queue they listen to
        - want a channel
    -> take a function
    -> open connection
    -> provide a channel
    -> check that the queue exists
    """

    def __init__(self, decorated_function):
        """
        Initializes the class
        """
        self.decorated_function = decorated_function
        self.__exchange_name = os.environ.get("EXCHANGE_NAME")
        self.__rabbitmq_host = os.environ.get("RABBITMQ_HOST")
        self.__rabbitmq_user = os.environ.get("RABBITMQ_USER")
        self.__rabbitmq_password = os.environ.get("RABBITMQ_PASSWORD")
        self.kill = None

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

        logging.info('RabbitMQConnection init complete')

    def __call__(self, *args, **kwargs):
        logging.info("RabbitMQConnection called")
        self._stopping = False
        self._closing = False
        self._connection = None
        self._channel = None
        logging.debug(f"RabbitMQConnection called with args: {args}")
        logging.debug(f"RabbitMQConnection called with kwargs: {kwargs}")
        self.args = args
        #self.rabbitmq_thread_instance = args[0]
        self.run()
        logging.info("run finished")
        self._stopping = False
        self._closing = False
        logging.debug('self._stopping reset')
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
        logging.info(f'connection created at {id(conn)}')
        self.get_channel()

    def __connection_open_error_callback(self, conn, exception):
        """
        Run on failure to connect to the server
        :param conn: The connection created in the previous step
        :param exception: The exception describing the failure
        """
        logging.warning('connection_open_error_callback')
        logging.warning(f'failed to create new connection at {id(conn)} due to {type(exception)}')
        if self._closing:
            self._connection.ioloop.stop()
        else:
            logging.info(f'retrying')
            self._connection.ioloop.stop()
            logging.info('old loop stopped')
            self._stopping = False
            self._closing = False
            logging.info('starting new loop')
            self.run()

    def __unexpected_close_connection_callback(self, conn, message):

        if self._closing:
            logging.info('expected close')
            self._connection.ioloop.stop()
        else:
            logging.warning('unexpected_close_connection_callback')
            logging.warning(f'failed to create new connection at {id(conn)} due to {message}')
            logging.info(f'retrying')
            #self._connection.add_timeout(5, self.reconnect)
            #self._connection.ioloop.call_later(5, self._connection.ioloop.stop)
            self._connection.ioloop.stop()
            logging.info('old loop stopped')
            self._stopping = False
            self._closing = False
            logging.info('starting new loop')
            self.run()

    def reconnect(self):
        """Will be invoked by the IOLoop timer if the connection is
        closed. See the on_connection_closed method.

        """
        logging.info("Reconnecting to broker")

        # This is the old connection IOLoop instance, stop its ioloop
        try:
            self._connection.ioloop.stop()
        except Exception as error:
            logging.error(f"Error stopping connection ioloop: {error}")

        # Create a new connection
        self._connection = self.connect()

        try:
            # There is now a new connection, needs a new ioloop to run
            self._connection.ioloop.start()
        except Exception as error:
            logging.error(f"Error starting connection ioloop: {error}")

            self.on_open_error_callback(self._connection, "Problem reconecting to broker")

    def get_channel(self):
        """
        Run on connecting to the server

        :param conn: The connection created in the previous step
        """
        logging.info('channel created')
        #self._channel = self._connection.channel() # on_open_callback=channel_callback)
        self._connection.channel(on_open_callback=self.__on_channel_open)

    def __on_channel_open(self, channel):
        self.add_on_channel_close_callback(channel)
        if self.kill is not None:
            self._connection.ioloop.remove_timeout(self.kill)
            logging.info('queue check suspended')
        else:
            logging.info('no active queue check')
        self.decorated_function(*self.args, channel=channel)
        if not pod_type == 'nt':
            self.kill = self._connection.ioloop.call_later(180, self.stop)
            self.queue_check = self._connection.ioloop.call_later(120, self.__check_queue_exists)
            logging.info('queue check resumed')

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

    def __check_queue_exists(self):
        logging.info("checking queue exists")
        self._connection.channel(on_open_callback=self.__check_queue_exists_channel_open)

    def __check_queue_exists_channel_open(self, channel):
        logging.info("checking queue")
        logging.debug(self.args)
        logging.debug(self.args[1])
        queue = self.args[1]
        self.channel = channel
        queue_declare = channel.queue_declare(
            callback=self.__queue_exists_callback,
            queue=queue,
            passive=True
        )

    def __queue_exists_callback(self, queue_declare):
        logging.info(f'queue_declare {queue_declare}')
        self._connection.ioloop.remove_timeout(self.kill)
        self.kill = self._connection.ioloop.call_later(60, self.stop)
        self._connection.ioloop.call_later(30, self.__check_queue_exists)
        self.channel.close()

    def stop(self):
        logging.warning('kill was never cancelled by queue existing')
        self._closing = True
        self._stopping = True
        self._connection.ioloop.stop()

    def run(self):
        """
        open the connection and then start the IOLoop.
        """
        logging.info('RabbbitMQConnection starting')
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
                logging.info('stopping')
                self._closing = True
                self._stopping = True
                #self.stop()
                self._connection.ioloop.stop()
                #if (self._connection is not None and
                #        not self._connection.is_closed):
                #    # Finish closing
                #    self._connection.ioloop.start()

        logging.info('stopping')
        self._closing = True
        self._stopping = True
        self._connection.ioloop.stop()


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
            self.pod_type = os.environ.get("POD_TYPE")
        except:
            self.pod_type = None
        logging.info(f'pod_type: {self.pod_type}')
        self.__rabbitmq_listen_queue = None
        self.__exchange_name = '' #os.environ.get("EXCHANGE_NAME")
        self.FRONT_END_URL = f'http://{os.environ.get("FRONTEND_URL")}/log/'
        logging.info(f'frontend url is: {self.FRONT_END_URL}')
        if self.pod_type == 'nt':
            self.__rabbitmq_listen_queue = os.environ.get("RABBITMQ_LISTEN_QUEUE")
            self.design_target = 'N/A'
        else:
            get_queue_call = self.get_queue(f'{os.environ.get("RABBITMQ_LISTEN_QUEUE")}-current-designs')
            get_queue_call = None
        print(f'listening to {self.__rabbitmq_listen_queue}')
        self.first_call = True

    @RabbitMQConnection
    def get_queue(self, queue, channel=None):
        logging.info(f'channel is {channel}')
        logging.debug(type(channel))
        logging.info("getting listen queue")

        channel.basic_consume(queue=queue,
                              on_message_callback=self.read_current_designs_queue,
                              auto_ack=False)

    def read_current_designs_queue(self, ch, method, properties, body):
        logging.info('get design name')
        logging.info(" [x] Received %r" % body)
        body = json.loads(b64decode(body))
        design_target = body['design_target']
        ch.basic_nack(method.delivery_tag, requeue=True)
        if self.__rabbitmq_listen_queue is None:
            logging.info('no listen queue established')
            try:
                consumer_check_thread = threading.Thread(self.check_for_consumers(design_target))
                consumer_check_thread.start()
                time.sleep(2)
                consumer_check_thread.join(2)
                logging.info(f'self.__rabbitmq_listen_queue is {self.__rabbitmq_listen_queue}')
                self.design_target = design_target
            except ValueError:
                pass

        else:
            logging.info('listen queue established, closing current designs queue')
            ch.close()

    @RabbitMQConnection
    def check_for_consumers(self, design_target, channel=None):

        self.channel = channel

        logging.info(f'checking {os.environ.get("RABBITMQ_LISTEN_QUEUE")}-{design_target}')

        self.channel.queue_declare(
            queue=f'{os.environ.get("RABBITMQ_LISTEN_QUEUE")}-{design_target}',
            durable=True,
            exclusive=False,
            callback=self.on_queue_declareok
        )
        logging.info("done")

    def on_queue_declareok(self, declared_queue):

        logging.info(f'declared_queue: {declared_queue}')

        if declared_queue.method.consumer_count == 0:
            logging.info("found a queue with no consumer")
            self.__rabbitmq_listen_queue = declared_queue.method.queue
            self.channel.close()
            self.channel = None
            return self.__rabbitmq_listen_queue
        else:
            logging.info('this queue already has a consumer')
            self.channel.close()
            self.channel = None

    @RabbitMQConnection
    def consume(self, queue, channel=None):

        channel.queue_declare(
            queue=queue,
            durable=True,
            exclusive=False,
            #auto_delete=False
        )

        channel.basic_consume(queue=queue, on_message_callback=self.callback, auto_ack=False)

        logging.info(' [*] Waiting for messages. To exit press CTRL+C')

    def callback(self, ch, method, properties, body):
        logging.info(" [x] Received %r" % body)
        body = json.loads(b64decode(body))
        logging.info(body)
        logging.info(type(body))
        if properties.reply_to:
            #publish_exchange = properties.reply_to['exchange']
            print('reply to is set')
            publish_exchange = ''
            publish_queue = properties.reply_to
        else:
            publish_exchange = self.__exchange_name
            publish_queue = f"{body['pathway'][0]}-{self.design_target}"
        output = self.process(body)
        #design_still_running = self.check_current_designs()
        ch.basic_ack(method.delivery_tag)
        self.publish(output, publish_exchange, publish_queue)
     #   ch.basic_ack(method.delivery_tag)

    def process(self, input):
        logging.info('processing')
        service = Service(input)
        status_update = service.get_status_update()
        #if not self.pod_type == 'nt':
        status_update['design_target'] = self.design_target
        logging.info(status_update)
        if self.first_call:
            log_response = requests.post(self.FRONT_END_URL, json=status_update)
            logging.info(f'log response is {log_response}')
            self.first_call = False
        output = service.run(input)
        status_update = service.get_status_update()
        if status_update['status'] == 'done':
            return output
        else:
            #if self.pod_type == 'nt':
            #    self.design_target = self.design_id.split('.')[0]
            #status_update = service.get_status_update()
            status_update['design_target'] = self.design_target
            logging.info(status_update)
            log_response = requests.post(self.FRONT_END_URL, json=status_update)
            logging.info(f'log response is {log_response}')
            return None

    @RabbitMQConnection
    def publish(self, output, publish_exchange, publish_queue, channel=None):
        logging.info("publish function")
        logging.info("queue declared")
        if isinstance(output, list):
            logging.info('output is list')
            properties = pika.BasicProperties(content_type='application/json')
            for item in output:
                logging.info(item)
                if 'priority' in item.keys():
                    properties = pika.BasicProperties(priority=item['priority'],
                                                      content_type='application/json')
                channel.basic_publish(exchange='', #publish_exchange,
                                      routing_key=publish_queue,
                                      properties=properties,
                                      body=b64encode(json.dumps(item).encode()))
                #_barrier.wait(timeout=6)
                logging.info(f'item pushed to: {publish_queue}')

        else:
            logging.info('output not list')

        channel.close()

    def get_q_size(self, channel):
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
        logging.info(f'Messages in queue: {res.method.message_count}')

    def run(self):
        """
        a function that runs consume
        """
        #while not self._stop_event.isSet():
        self.consume(self.__rabbitmq_listen_queue)
        logging.info("rabbitmq thread has stopped completely")
        self.restart()

    def restart(self):
        logging.info("restarting")
        if self.pod_type == 'nt':
            self.__rabbitmq_listen_queue = os.environ.get("RABBITMQ_LISTEN_QUEUE")
        else:
            self.__rabbitmq_listen_queue = None
            get_queue_call = self.get_queue(f'{os.environ.get("RABBITMQ_LISTEN_QUEUE")}-current-designs')
            get_queue_call = None
        logging.info(f'listening to {self.__rabbitmq_listen_queue}')
        self.run()

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
        #log_response = requests.post(self.FRONT_END_URL, json=service.get_status_update())
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
            print(status_update['status'])
        #    log_response = requests.post(self.FRONT_END_URL, json=service.get_status_update())

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
