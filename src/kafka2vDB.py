import os
import sys
import json
import logging
import requests

from dotenv import load_dotenv, find_dotenv

from qdrant_client import QdrantClient
from qdrant_client.http import models

from utils import (
    VDB_COLLECTION,
    TOPIC_DB_EXTRAS,
    KafkaClient,
    md5_hash,
    sys_exc,
    set_flag,
    unset_flag,
    get_key_value,
)


########
# Main #
########
if __name__ == "__main__":
    # Load env variables
    load_dotenv(find_dotenv())
    env_vars = dict(os.environ)

    FLAG_FILE = env_vars.get("FLAG_FILE")
    unset_flag(FLAG_FILE)

    FILE_APP = os.path.splitext(os.path.split(__file__)[-1])[0]
    logging.basicConfig(
        format=f"[{FILE_APP}] %(asctime)s.%(msecs)03d [%(levelname)s]: %(message)s",
        level=logging.INFO,
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    kafka = KafkaClient(
        env_vars.get("KAFKA_CONFIG"),
        env_vars.get("CLIENT_ID_VDB"),
        file_app=FILE_APP,
        set_consumer=True,
        enable_auto_commit=True,
    )

    # Qdrant (Vector-DB)
    logging.info("Loading VectorDB client (Qdrant)")
    VDB_CLIENT = QdrantClient(
        host="qdrant",
        port=6333,
    )

    # Create collection
    logging.info(f"Creating VectorDB collection: {VDB_COLLECTION}")
    VDB_CLIENT.create_collection(
        collection_name=VDB_COLLECTION,
        vectors_config=models.VectorParams(
            size=384,
            distance=models.Distance.COSINE,
        ),
    )

    # Set flag here to allow time to create Vector DB collection
    set_flag(FLAG_FILE)

    embedding_url = f"http://localhost:{os.environ.get('EMBEDDING_PORT')}{os.environ.get('EMBEDDING_PATH')}"

    for topic, _, _, value in kafka.avro_string_consumer(
        kafka.consumer,
        [TOPIC_DB_EXTRAS],
    ):
        try:
            if isinstance(value, dict):
                payload_op, payload_key, payload_value = get_key_value(value)

                id = md5_hash(payload_key)

                if payload_op == "d":
                    # Deleting document from collection
                    VDB_CLIENT.delete(
                        collection_name=VDB_COLLECTION,
                        points_selector=models.PointIdsList(
                            points=[id],
                        ),
                    )
                    logging.info(
                        f"Deleted Vector DB collection {VDB_COLLECTION}: {id} | {payload_key}"
                    )

                else:
                    # Generate vector Data
                    response = requests.get(
                        embedding_url,
                        headers={
                            "Content-Type": "text/plain; charset=UTF-8",
                        },
                        data=json.dumps(
                            {
                                payload_key: payload_value["description"],
                            }
                        ),
                    )
                    embeddings = response.json().get("embeddings", list())

                    # Upsert collection
                    logging.info(
                        f"Upserting Vector DB collection {VDB_COLLECTION}: {id} | {payload_key}: {payload_value['description']}"
                    )
                    VDB_CLIENT.upsert(
                        collection_name=VDB_COLLECTION,
                        points=[
                            models.PointStruct(
                                id=id,
                                vector=embeddings,
                                payload={
                                    "title": payload_key,
                                    "description": payload_value["description"],
                                },
                            ),
                        ],
                    )

        except Exception:
            logging.error(sys_exc(sys.exc_info()))
