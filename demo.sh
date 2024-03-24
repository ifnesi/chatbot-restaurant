#!/bin/bash

## Functions
function usage() {
  echo "usage: ./demo.sh [-h, --help] [-x, --start] [-p, --stop]"
  echo ""
  echo "Demo: Chatbot for a Restaurant (Confluent - All rights reserved)"
  echo ""
  echo "Options:"
  echo " -h, --help    Show this help message and exit"
  echo " -x, --start   Start demo"
  echo " -p, --stop    Stop demo"
  echo ""
}

function logging() {
  TIMESTAMP=`date "+%Y-%m-%d %H:%M:%S.000"`
  LEVEL=${2-"INFO"}
  if [[ $3 == "-n" ]]; then
    echo -n "$TIMESTAMP [$LEVEL]: $1"
  else
    echo "$TIMESTAMP [$LEVEL]: $1"
  fi
}

## Main
source .env
if [[ "$1" == "--stop" || "$1" == "-p" ]]; then
  # Stop demo
  logging "Stopping docker compose"
  echo ""
  if docker compose down ; then
    echo ""
    logging "Demo successfully stopped"
    exit 0
  else
    logging "Please start Docker Desktop!" "ERROR"
    exit -1
  fi
elif [[ "$1" == "--help" || "$1" == "-h" ]]; then
  # Demo help
  usage
  exit 0
elif [[ "$1" != "--start" && "$1" != "-x" ]]; then
  logging "Invalid argument '$1'" "ERROR"
  usage
  exit -1
fi

# Start demo
logging "Setting environment variables"
if [ ! -f $ENV_VAR_FILE ]; then
    logging "File '$ENV_VAR_FILE' not found!" "ERROR"
    echo ""
    echo "Generate the API Key(s) required and have them saved into the file '$ENV_VAR_FILE':"
    echo "cat > $ENV_VAR_FILE <<EOF"
    echo "export OPENAI_API_KEY=\"<OpenAI_Key_here>\"       # https://platform.openai.com/docs/quickstart/account-setup?context=python"
    echo "export PASSWORD_SALT=\"<Any_string_here>\""
    echo "export BASE_MODEL=\"gpt-3.5-turbo-16k\""
    echo "export MODEL_TEMPERATURE=\"0.3\""
    echo "EOF"
    echo ""
    exit -1
fi
source $ENV_VAR_FILE

logging "Starting docker compose"
if ! docker compose up -d --build ; then
    logging "Please start Docker Desktop!" "ERROR"
    exit -1
fi

echo ""

# Waiting services to be ready
logging "Waiting Schema Registry to be ready" "INFO" -n
while [[ "$(curl -s -o /dev/null -w ''%{http_code}'' http://$HOST:8081)" != "200" ]]
do
    echo -n "."
    sleep 1
done

echo ""
logging "Waiting Confluent Control Center to be ready" "INFO" -n
while [[ "$(curl -s -o /dev/null -w ''%{http_code}'' http://$HOST:9021)" != "200" ]]
do
    echo -n "."
    sleep 1
done

echo ""
logging "Waiting Chatbot Web application to be ready" "INFO" -n
while [[ "$(curl -s -o /dev/null -w ''%{http_code}'' http://$HOST:8888/login)" != "200" ]]
do
    echo -n "."
    sleep 1
done

echo ""
logging "Demo environment is ready!"
echo ""

# Open browser with C3 and Chatbot Web application
python3 -m webbrowser -t "http://$HOST:9021"
python3 -m webbrowser -t "http://$HOST:8888/login"
