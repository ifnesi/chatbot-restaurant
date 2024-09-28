CREATE STREAM `chatbot_customer_actions` (
   `key` STRING KEY,
   `username` STRING,
   `waiter_name` STRING,
   `context` STRING,
   `query` STRING,
   `mid` BIGINT
)
WITH (
   KAFKA_TOPIC='chatbot-customer_actions',
   KEY_FORMAT='KAFKA',
   VALUE_FORMAT='AVRO'
);