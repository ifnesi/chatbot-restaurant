CREATE STREAM `db_public_extras_vdb` WITH (
   KAFKA_TOPIC='db.public.extras.vdb',
   VALUE_FORMAT='JSON'
) AS
SELECT
	'chatbot_restaurant' AS `collection_name`,
	CASE
		WHEN OP = 'd' THEN HASH_MD5(BEFORE->ID)
		ELSE HASH_MD5(AFTER->ID)
	END AS `id`,
	CASE
		WHEN OP = 'd' THEN NULL
		ELSE TRANSFORM(JSON_ITEMS(EXTRACTJSONFIELD(GET_VECTOR_DATA('http://chatbot:9999/api/v1/embedding/sentence-transformer', AFTER->ID + ': ' + AFTER->DESCRIPTION), '$.vector_data')), x => CAST(x AS DOUBLE))
	END  AS `vector`,
	CASE
		WHEN OP = 'd' THEN NULL
		ELSE MAP('title':= AFTER->ID, 'description':= AFTER->DESCRIPTION)
	END  AS `payload`
FROM `db_public_extras`
EMIT CHANGES;