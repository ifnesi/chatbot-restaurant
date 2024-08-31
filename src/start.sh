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

# Postgres Connector
logging "Starting Postgres Connector"
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

logging "Provisioning Postgres DB" "INFO" -n
exec python db_provisioning.py &
# Wait DB provisioning
while [ ! -f $FLAG_FILE ];  do
    echo -n "."
    sleep 1
done
rm $FLAG_FILE

logging "Starting chatbot microservice" "INFO" -n
exec python chatbot.py &
# Allow sentence transformer to load
while [ ! -f $FLAG_FILE ]; do
    echo -n "."
    sleep 1
done
rm $FLAG_FILE

exec python webapp.py
