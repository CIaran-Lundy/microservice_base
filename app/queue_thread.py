import asyncio
import threading
from pydantic import BaseModel
from typing import Dict
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import requests
from service import Input
from service import Service


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

    def process(self, input: Input):
        NEXT_SERVICE_URL = input.pathway[0]
        service = Service(input)
        log_response = requests.post(self.FRONT_END_URL, json=service.get_status_update())
        output = service.run(input)
        status_update = service.get_status_update()
        if status_update['status'] == 'done':
            response = requests.post(NEXT_SERVICE_URL, json=output)
            print(response)
        #pass

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
