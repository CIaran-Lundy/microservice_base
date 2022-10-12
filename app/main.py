from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import requests
import os
from pydantic import BaseModel
from service import Input
from service import Service
from queue_thread import SequentialQueueThread
import threading
import asyncio
import queue


app = FastAPI()

sequential_queue = asyncio.Queue(maxsize=0)


@app.post("/")
async def run(input: Input):
    #global kill_list
    #if input.design_id in kill_list:
    #    return HTMLResponse(content="killed", status_code=200)
    global sequential_queue
    if sequential_queue.qsize() >= 10:
        return HTMLResponse(content="queue_full", status_code=429)
    #input_dict = input.dict()
    sequential_queue.put_nowait(input)#_dict)
    print(sequential_queue.qsize())
    return HTMLResponse(content="ready", status_code=200)


@app.post("/run/")
def process(input: Input):
    input_dict = input.dict()
    service = Service(input_dict)
    output = service.run(input_dict)
    return output


#@app.post("/kill/")
#def kill(design_id):
#    global kill_list
#    kill_list.append(design_id)
#    return HTMLResponse(content="ready", status_code=200)


if __name__ == "__main__":
    print("l49")
    FRONT_END_URL = str("http://" + os.getenv("FRONTEND_URL") + "/log/")
    print("l51")
    sequential_queue_thread = SequentialQueueThread(FRONT_END_URL=FRONT_END_URL, intake_q=sequential_queue)
    print("l53")
    sequential_queue_thread.start()
    print("l55")
    #kill_list = []