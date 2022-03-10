import zlib
import sys
from subprocess import check_output, Popen, PIPE
from pydantic import BaseModel
from typing import Dict
import pytest
import mock
import sys
from fastapi.testclient import TestClient
import os
import requests
import json
import asyncio
import runpy
import imp
#import app

sys.path.append("..")


class Input(BaseModel):
    design_id: str = "Prototheca-SPP.0.5.5.0.0.0.0.959.0"
    data: str = "TTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTT"
    metadata: Dict[str, list] = {'taxid': ['3110']}
    pathway: list = ['this_service', 'next_service']


class Service:
    def __init__(self, input):
        pass

    def get_status_update(self):
        pass

    def run(self, input):
        return "results"


module = type(sys)('service')
module.Input = Input
module.Service = Service
sys.modules['service'] = module
#from app import queue_thread
#from app import main
#from main import app, run
from app.queue_thread import SequentialQueueThread


dummy_post = {"design_id": "design",
              "data": "string",
              "metadata": {"key": ["list", "of", "values"]},
              "pathway": ["this_service", "next_service", "last_service"]}


class MyInput(BaseModel):
    design_id: str = "Prototheca-SPP.0.5.5.0.0.0.0.959.0"
    data: str = "TTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTT"
    metadata: Dict[str, list] = {'taxid': ['3110']}
    pathway: list = ['this_service', 'next_service']


def test__init__():
    sequential_queue_thread = SequentialQueueThread(FRONT_END_URL="test", intake_q=asyncio.Queue(maxsize=0))
    #sequential_queue_thread.start()
    assert getattr(sequential_queue_thread, 'FRONT_END_URL') == "test"
    assert isinstance(getattr(sequential_queue_thread, 'intake_q'), asyncio.Queue)
    assert isinstance(getattr(sequential_queue_thread, 'outlet_q'), asyncio.Queue)


def mocked_requests_get_for_external_api(*args, **kwargs):
    class MockResponse:
        def __init__(self, content, status_code):
            self.content = content
            self.status_code = status_code

    return MockResponse(str('content'), 200)


def mock_get_from_queue(*args):
    pass


def mock_process(*args):
    pass


def mock_get_status_update(*args):
    return {"design_id": "design_id", "step": "step", "status": "done"}


#@mock.patch.object(Service, 'get_status_update', mock_get_status_update)
@mock.patch.object(requests, 'post', mocked_requests_get_for_external_api)
#@mock.patch.object(SequentialQueueThread, 'process', mock_process)
@mock.patch.object(asyncio.Queue, 'get_nowait', mock_get_from_queue)
def test_intake_q_recieves_object():
    input = MyInput()
    sequential_queue_thread = SequentialQueueThread(FRONT_END_URL="http://test/log/",
                                                    intake_q=asyncio.Queue(maxsize=0))
    sequential_queue_thread.intake_q.put_nowait(input)
    running_thread = sequential_queue_thread.start()
    assert sequential_queue_thread.intake_q.qsize() == 1
    sequential_queue_thread.stop()


#@mock.patch.object(Service, 'get_status_update', mock_get_status_update)
#@mock.patch.object(requests, 'post', mocked_requests_get_for_external_api)
#@mock.patch.object(asyncio.Queue, 'get_nowait', mock_get_from_queue)
#@mock.patch('SequentialQueueThread.process', side_effect=[SequentialQueueThread.process, mock_process])
#@mock.patch.object(requests, 'post', mocked_requests_get_for_external_api)
#@mock.patch('app.queue_thread.SequentialQueueThread.process', mock_process)
#def test_run_removes_object_from_queue():
#    input = MyInput()
#    sequential_queue_thread = SequentialQueueThread(FRONT_END_URL="http://test/log/",
#                                                    intake_q=asyncio.Queue(maxsize=0))
#    sequential_queue_thread.intake_q.put_nowait(input)
#    sequential_queue_thread.start()
#    #assertEqual(sequential_queue_thread, SequentialQueueThread)
#    assert sequential_queue_thread.intake_q.qsize() == 0
#    #assert isinstance(sequential_queue_thread.process, mock.mock.MagicMock)
#    sequential_queue_thread.stop()


if __name__ == '__main__':
    sequential_queue_thread = SequentialQueueThread(FRONT_END_URL="http://test/log/",
                                                    intake_q=asyncio.Queue(maxsize=0))
    print(type(sequential_queue_thread))
    input = MyInput()
    pytest.main()
    exit()