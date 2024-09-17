DEFINE COLLECTION_NAME = 'chatbot_restaurant';
DEFINE URL_VDB = 'http://chatbot:9999/api/v1/embedding/sentence-transformer';
CREATE STREAM `db_public_extras_vdb` WITH (
   KAFKA_TOPIC='db.public.extras.vdb',
   VALUE_FORMAT='JSON'
) AS
SELECT
	'${COLLECTION_NAME}' AS `collection_name`,
	HASH_MD5(
		CASE
			WHEN OP = 'd' THEN BEFORE->ID
			ELSE AFTER->ID
		END
	) AS `id`,
	TRANSFORM(JSON_ITEMS(EXTRACTJSONFIELD(GET_VECTOR_DATA('${URL_VDB}',
		CASE
			WHEN OP = 'd' THEN ''
			ELSE AFTER->ID + ': ' + AFTER->DESCRIPTION
		END
	), '$.vector_data')), x => CAST(x AS DOUBLE)) AS `vector`,
	CASE
		WHEN OP = 'd' THEN MAP('title':= '', 'description':= '')
		ELSE MAP('title':= AFTER->ID, 'description':= AFTER->DESCRIPTION)
	END  AS `payload`
FROM `db_public_extras`
EMIT CHANGES;