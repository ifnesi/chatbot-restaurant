DEFINE URL_VDB = 'http://chatbot:9999/api/v1/embedding/sentence-transformer';
CREATE STREAM `chatbot_customer_actions_embeddings` WITH (
   KAFKA_TOPIC='chatbot-customer_actions_embeddings',
   KEY_FORMAT='KAFKA',
   VALUE_FORMAT='AVRO'
) AS
SELECT
	*,
	TRANSFORM(
		JSON_ITEMS(
			EXTRACTJSONFIELD(
				GET_VECTOR_DATA('${URL_VDB}', `query`)
			, '$.vector_data')
		), x => CAST(x AS DOUBLE)
	) AS `vector`
FROM `chatbot_customer_actions`
PARTITION BY `key`
EMIT CHANGES;