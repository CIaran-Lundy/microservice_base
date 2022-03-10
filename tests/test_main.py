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
sys.path.append("..")


class Input(BaseModel):
    design_id: str
    data: str
    metadata: Dict[str, list]
    pathway: list


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
from app import main
from main import app, run


dummy_post = {"design_id": "design",
              "data": "string",
              "metadata": {"key": ["list", "of", "values"]},
              "pathway": ["this_service", "next_service", "last_service"]}


client = TestClient(main.app)


@pytest.mark.parametrize("dummy_post, expected_status_code, expected_content", [
    ({"design_id": "design",
      "data": "string",
      "metadata": {"key": ["list", "of", "values"]},
      "pathway": ["this_service", "next_service", "last_service"]},
     200, b"ready"),
    ({"data": "string",
      "metadata": {"key": ["list", "of", "values"]},
      "pathway": ["this_service", "next_service", "last_service"]},
     422, b'{"detail":[{"loc":["body","design_id"],"msg":"field required","type":"value_error.missing"}]}'),
    ({"design_id": "design",
      "data": ["string"],
      "metadata": {"key": ["list", "of", "values"]},
      "pathway": ["this_service", "next_service", "last_service"]},
     422, b'{"detail":[{"loc":["body","data"],"msg":"str type expected","type":"type_error.str"}]}'),
    ({"design_id": "design",
      "data": "string",
      "metadata": {"key": ["list", "of", "values"]},
      "pathway": "last_service"},
     422, b'{"detail":[{"loc":["body","pathway"],"msg":"value is not a valid list","type":"type_error.list"}]}'),
])
def test_root_endpoint_api_type_checking(dummy_post, expected_status_code, expected_content):
    response = client.post("/", json=dummy_post)
    assert response.status_code == expected_status_code
    assert response.content == expected_content


@pytest.mark.parametrize("dummy_post, expected_status_code, expected_content", [
    ({"design_id": "design",
      "data": "string",
      "metadata": {"key": ["list", "of", "values"]},
      "pathway": ["this_service", "next_service", "last_service"]},
     200, b'"results"'),
    ({"data": "string",
      "metadata": {"key": ["list", "of", "values"]},
      "pathway": ["this_service", "next_service", "last_service"]},
     422, b'{"detail":[{"loc":["body","design_id"],"msg":"field required","type":"value_error.missing"}]}'),
    ({"design_id": "design",
      "data": ["string"],
      "metadata": {"key": ["list", "of", "values"]},
      "pathway": ["this_service", "next_service", "last_service"]},
     422, b'{"detail":[{"loc":["body","data"],"msg":"str type expected","type":"type_error.str"}]}'),
    ({"design_id": "design",
      "data": "string",
      "metadata": {"key": ["list", "of", "values"]},
      "pathway": "last_service"},
     422, b'{"detail":[{"loc":["body","pathway"],"msg":"value is not a valid list","type":"type_error.list"}]}'),
])
def test_run_endpoint_api_type_checking(dummy_post, expected_status_code, expected_content):
    response = client.post("/run/", json=dummy_post)
    assert response.status_code == expected_status_code
    assert response.content == expected_content


def mock_queue_size(arg):
    return 110


@mock.patch.object(asyncio.Queue, 'qsize', mock_queue_size)
def test_root_endpoint_queue_filling():
    response = client.post("/", json=dummy_post)
    assert response.status_code == 429
    assert response.content == b"queue_full"


def mocked_run(args):
    pass


@mock.patch.object(main.SequentialQueueThread, 'run', mocked_run)
@mock.patch.dict(os.environ, {"FRONTEND_URL": "test"})
def test_sequential_queue_thread():
    main = imp.load_source('__main__', 'app/main.py')
    runpy.run_module('main', run_name='__main__')
    client = TestClient(main.app)
    response = client.post("/", json=dummy_post)
    assert main.FRONT_END_URL == "http://test/log/"
    assert main.sequential_queue_thread.FRONT_END_URL == "http://test/log/"
    assert main.sequential_queue_thread.intake_q.qsize() == 1


#def mocked_requests_get_for_external_api(*args, **kwargs):
#    class MockResponse:
#        def __init__(self, content, status_code):
#            self.content = content
#            self.status_code = status_code

#    return MockResponse(str('content'), 200), *args


#@mock.patch('requests.post', side_effect=[requests.post, mocked_requests_get_for_external_api])
#@mock.patch('Service.get_status_update', side_effect=[Service.get_status_update, bad_status_update])
#@mock.patch.dict(os.environ, {"FRONTEND_URL": "test"})


if __name__ == '__main__':
    pytest.main()