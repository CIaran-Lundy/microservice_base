from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import requests
import os
from pydantic import BaseModel
from service import Input
from service import Service
from queue_thread import SequentialQueueThread, RabbitMQThread
import threading
import asyncio
import queue
import aiormq
from base64 import b64encode, b64decode
import os
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


app = FastAPI()

sequential_queue = asyncio.Queue(maxsize=0)

exchange_name = os.environ.get("EXCHANGE_NAME")
rabbitmq_host = os.environ.get("RABBITMQ_HOST")
rabbitmq_user = os.environ.get("RABBITMQ_USER")
rabbitmq_password = os.environ.get("RABBITMQ_PASSWORD")


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


if __name__ == "nonsense":
    import pika

    exchange_name = os.environ.get("EXCHANGE_NAME")
    rabbitmq_host = os.environ.get("RABBITMQ_HOST")
    rabbitmq_user = os.environ.get("RABBITMQ_USER")
    rabbitmq_password = os.environ.get("RABBITMQ_PASSWORD")

    def on_callback(msg):
        print(msg)


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
        #callback=on_callback,
        queue="clusterservice",
        durable=True,
        exclusive=False,
        auto_delete=False
    )

    channel.basic_publish(exchange='', routing_key='clusterservice', body=b'hello world')

    # ...

    # Re-declare the queue with passive flag
    res = channel.queue_declare(
        #callback=on_callback,
        queue="test",
        durable=True,
        exclusive=False,
        auto_delete=False,
        passive=True
    )
    print(f'Messages in queue: {res.method.message_count}')

    params = pika.ConnectionParameters(
        host=rabbitmq_host,
        port=5672,
        credentials=pika.credentials.PlainCredentials(username=rabbitmq_user, password=rabbitmq_password),
    )

    # Open a connection to RabbitMQ on localhost using all default parameters
    connection = pika.BlockingConnection(parameters=params)
    channel = connection.channel()

    #channel.queue_declare(queue='test')


    def callback(ch, method, properties, body):
        print(" [x] Received %r" % body)


    channel.basic_consume(queue='test', on_message_callback=callback, auto_ack=True)

    print(' [*] Waiting for messages. To exit press CTRL+C')
    channel.start_consuming()

    #loop = asyncio.get_event_loop()
    #loop.run_until_complete(consume())
    #loop.run_forever()


@app.post("/")
async def run(input: Input):
    #global kill_list
    #if input.design_id in kill_list:
    #    return HTMLResponse(content="killed", status_code=200)
    global sequential_queue
    if sequential_queue.qsize() >= 10:
        return HTMLResponse(content="queue_full", status_code=429)
    sequential_queue.put_nowait(input)
    return HTMLResponse(content="ready", status_code=200)


@app.post("/run/")
def process(input: Input):
    input_dict = input.dict()
    service = Service(input_dict)
    output = service.run(input_dict)
    return output


#kill_list = []
#@app.post("/kill/")
#def kill(input):
#    design_id = input['design_id']
#    global kill_list
#    kill_list.append(design_id)
#    return HTMLResponse(content="ready", status_code=200)


#if __name__ == "__main__":

FRONT_END_URL = str("http://" + os.getenv("FRONTEND_URL") + "/log/")

sequential_queue_thread = SequentialQueueThread(FRONT_END_URL=FRONT_END_URL, intake_q=sequential_queue)
sequential_queue_thread.start()

rabbitmq_thread = RabbitMQThread(FRONT_END_URL=FRONT_END_URL)
rabbitmq_thread.start()

kill_list = []