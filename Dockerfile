FROM python:3.8-slim-buster

RUN apt-get update -y && apt-get install curl -y

WORKDIR /src

COPY src/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install uvicorn[standard]

COPY .env .
COPY src/ .

ENTRYPOINT ["./start.sh"]