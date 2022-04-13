FROM tiangolo/uvicorn-gunicorn-fastapi:latest

RUN pip install requests

COPY ./app /app

ENV PYTHONUNBUFFERED=1

ENV PYTHONIOENCODING=UTF-8

ENTRYPOINT uvicorn --workers=0 --port 80 --host 0.0.0.0 main:app
