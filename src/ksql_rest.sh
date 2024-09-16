#!/bin/bash

# Global variables
KSQLDB_ENDPOINT="http://ksqldb-server:8088"

# Submit ksqlDB SQL Statements
for file in ./ksqldb/*.sql; do
	response=$(curl -w "\n%{http_code}" -X POST $KSQLDB_ENDPOINT/ksql \
		-H "Content-Type: application/vnd.ksql.v1+json; charset=utf-8" \
		--silent \
		-d @<(cat <<EOF
			{"ksql": "`(cat $file | tr '"' '\"' | tr '\n' ' ' | tr '\t' ' ' | tr -s ' ')`",
			"streamsProperties": {"ksql.streams.auto.offset.reset": "earliest", "ksql.streams.cache.max.bytes.buffering": "0"}}
EOF
	))
	echo "$response" | {
	  read body
	  read code
	  echo ""
	  echo "$body"
	  echo "Status: $code"
	}
	sleep 5;
done
