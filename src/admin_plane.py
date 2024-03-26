import os
import sys
import json
import logging

from dotenv import load_dotenv, find_dotenv
from configparser import ConfigParser

from utils import (
    TOPIC_CUSTOMER_ACTIONS,
    TOPIC_CHATBOT_RESPONSES,
    KafkaClient,
    SerializationContext,
    MessageField,
    hash_password,
    sys_exc,
)


if __name__ == "__main__":
    FILE_APP = os.path.splitext(os.path.split(__file__)[-1])[0]

    # Screen log handler
    logging.basicConfig(
        format=f"[{FILE_APP}] %(asctime)s.%(msecs)03d [%(levelname)s]: %(message)s",
        level=logging.INFO,
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Load env variables
    load_dotenv(find_dotenv())

    kafka = KafkaClient(
        os.environ.get("KAFKA_CONFIG"),
        os.environ.get("CLIENT_ID_ADMIN_PLANE"),
        FILE_APP,
    )

    # Data Config
    config_data = ConfigParser()
    config_data.read(os.environ.get("DATA_LOADER"))
    config_data = dict(config_data)

    # Create customer actions topic
    try:
        kafka.create_topic(
            TOPIC_CUSTOMER_ACTIONS,
            cleanup_policy="delete",
            sync=True,
        )
    except Exception:
        logging.error(sys_exc(sys.exc_info()))
        sys.exit(-1)

    # Create chatbot responses topic
    try:
        kafka.create_topic(
            TOPIC_CHATBOT_RESPONSES,
            cleanup_policy="delete",
            sync=True,
        )
    except Exception:
        logging.error(sys_exc(sys.exc_info()))
        sys.exit(-1)

    try:
        # Load RAG data into Kafka topics
        for rag, param in config_data.items():

            if rag in ["ai_rules", "policies", "restaurant", "vector_db"]:
                # Avro serialiser
                with open(param["schema"], "r") as f:
                    schema_str = f.read()
                avro_serializer = kafka.avro_serialiser(schema_str)

                topic = param["topic"]
                # Create new topic if required
                try:
                    kafka.create_topic(
                        topic,
                        sync=True,
                    )
                except Exception:
                    logging.error(sys_exc(sys.exc_info()))
                else:

                    # Populate topic
                    with open(param["filename"], "r") as f:
                        data_to_load = json.loads(f.read())

                    for key, value in data_to_load.items():
                        try:
                            message = {
                                "description": value,
                            }
                            kafka.producer.poll(0.0)
                            kafka.producer.produce(
                                topic=topic,
                                key=kafka.string_serializer(key),
                                value=avro_serializer(
                                    message,
                                    SerializationContext(
                                        topic,
                                        MessageField.VALUE,
                                    ),
                                ),
                                on_delivery=kafka.delivery_report,
                            )
                        except Exception:
                            logging.error(sys_exc(sys.exc_info()))

            elif rag in ["main_menu", "kids_menu"]:
                # Avro serialiser
                with open(param["schema"], "r") as f:
                    schema_str = f.read()
                avro_serializer = kafka.avro_serialiser(schema_str)

                topic_prefix = param["topic_prefix"]
                with open(param["filename"], "r") as f:
                    data_to_load = json.loads(f.read())

                for header, items in data_to_load.items():
                    topic = f"{topic_prefix}{header}"

                    # Create new topic if required
                    try:
                        kafka.create_topic(
                            topic,
                            sync=True,
                        )
                    except Exception:
                        logging.error(sys_exc(sys.exc_info()))
                    else:

                        # Populate topic
                        for key, value in items.items():
                            try:
                                kafka.producer.poll(0.0)
                                kafka.producer.produce(
                                    topic=topic,
                                    key=kafka.string_serializer(key),
                                    value=avro_serializer(
                                        value,
                                        SerializationContext(
                                            topic,
                                            MessageField.VALUE,
                                        ),
                                    ),
                                    on_delivery=kafka.delivery_report,
                                )
                            except Exception:
                                logging.error(sys_exc(sys.exc_info()))

            elif rag in ["customer_profiles"]:
                password_salt = os.environ.get("PASSWORD_SALT")

                # Avro serialiser
                with open(param["schema"], "r") as f:
                    schema_str = f.read()
                avro_serializer = kafka.avro_serialiser(schema_str)

                # Create new topic if required
                topic = param["topic"]
                try:
                    kafka.create_topic(
                        topic,
                        sync=True,
                    )
                except Exception:
                    logging.error(sys_exc(sys.exc_info()))
                else:

                    # Populate topic
                    with open(param["filename"], "r") as f:
                        data_to_load = json.loads(f.read())

                    for username, value in data_to_load.items():
                        try:
                            value["hashed_password"] = hash_password(
                                password_salt,
                                value["password"],
                            )
                            value.pop("password", None)
                            kafka.producer.poll(0.0)
                            kafka.producer.produce(
                                topic=topic,
                                key=kafka.string_serializer(username),
                                value=avro_serializer(
                                    value,
                                    SerializationContext(
                                        topic,
                                        MessageField.VALUE,
                                    ),
                                ),
                                on_delivery=kafka.delivery_report,
                            )
                        except Exception:
                            logging.error(sys_exc(sys.exc_info()))

    except KeyboardInterrupt:
        pass

    finally:
        logging.info("Flushing records...")
        try:
            kafka.producer.flush()
        except Exception:
            logging.error(sys_exc(sys.exc_info()))