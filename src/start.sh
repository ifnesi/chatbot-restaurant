#!/bin/bash

set -m

function logging() {
  TIMESTAMP=`date "+%Y-%m-%d %H:%M:%S.000"`
  LEVEL=${2-"INFO"}
  if [[ $3 == "-n" ]]; then
    echo -n "$TIMESTAMP [$LEVEL]: $1"
  else
    echo "$TIMESTAMP [$LEVEL]: $1"
  fi
}

function start_ms() {
  rm $FLAG_FILE 2> /dev/null || true
  logging "Starting microservice $1" "INFO" -n
  exec python $1 &
  while [ ! -f $FLAG_FILE ];  do
      echo -n "."
      sleep 1
  done
  echo ""
  rm $FLAG_FILE
}

source .env

# Waiting services to be ready
logging "Waiting Schema Registry to be ready" "INFO" -n
while [[ "$(curl -s -o /dev/null -w ''%{http_code}'' http://schema-registry:8081)" != "200" ]]
do
    echo -n "."
    sleep 1
done

echo ""
logging "Waiting Connect Cluster to be ready" "INFO" -n
while [[ "$(curl -s -o /dev/null -w ''%{http_code}'' http://connect:8083)" != "200" ]]
do
    echo -n "."
    sleep 1
done

echo ""
logging "Waiting Confluent Control Center to be ready" "INFO" -n
while [[ "$(curl -s -o /dev/null -w ''%{http_code}'' http://control-center:9021)" != "200" ]]
do
    echo -n "."
    sleep 1
done

# Postgres Source Connector
logging "Creating Postgres Source Connector"
curl -i -X PUT http://connect:8083/connectors/postgres_cdc/config \
     -H "Content-Type: application/json" \
     -d '{
          "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
          "tasks.max": "1",
          "database.hostname": "postgres",
          "database.port": "5432",
          "database.user": "postgres",
          "database.password": "postgres",
          "database.dbname" : "postgres",
          "topic.prefix": "db",
          "table.include.list": "public.customer_profiles,public.ai_rules,public.policies,public.restaurant,public.extras,public.main_menu,public.kids_menu"
        }'
sleep 5
echo ""
curl -s http://connect:8083/connectors/postgres_cdc/status
echo ""

# Start DB Provisioning service
start_ms "db_provisioning.py"

# Start Embeddings REST API
start_ms "embeddings.py"

# Create ksqlDB Streams
logging "Creating ksqlDB Streams" "INFO"
./ksql_rest.sh

# Start Chatbot service
start_ms "chatbot.py"

# QDrant Sink Connector
logging "Creating QDrant Sink Connector" "INFO"
curl -i -X PUT http://connect2:8083/connectors/qdrant_sink/config \
    -H "Content-Type: application/json" \
    -d '{
         "connector.class": "io.qdrant.kafka.QdrantSinkConnector",
         "tasks.max": "1",
         "qdrant.grpc.url": "http://qdrant:6334",
         "qdrant.api.key": "",
         "topics": "db.public.extras.vdb"
       }'
sleep 5
echo ""
curl -s http://connect2:8083/connectors/qdrant_sink/status
echo ""

# Start web application
logging "Starting webapplication" "INFO"
exec python webapp.py
