import os
import sys
import json
import logging
import argparse

from dotenv import load_dotenv
from configparser import ConfigParser

from utils import (
    KafkaClient,
    SerializationContext,
    MessageField,
    hash_password,
    sys_exc,
)


def main(args):
    # Load env variables
    load_dotenv(args.env_vars)

    kafka = KafkaClient(
        args.config,
        args.client_id,
        set_admin=True,
        set_producer=True,
    )

    # Data Config
    config_data = ConfigParser()
    config_data.read(args.config_data)
    config_data = dict(config_data)

    try:
        for rag, param in config_data.items():

            if rag in ["ai_rules", "policies", "restaurant"]:
                topic = param["topic"]
                # Create new topic if required
                try:
                    kafka.create_topic(topic)
                except Exception:
                    logging.error(sys_exc(sys.exc_info()))
                else:
                    # Populate topic
                    with open(param["filename"], "r") as f:
                        data_to_load = json.loads(f.read())
                    for key, value in data_to_load.items():
                        try:
                            kafka.producer.poll(0.0)
                            kafka.producer.produce(
                                topic=topic,
                                key=kafka.string_serializer(key),
                                value=kafka.string_serializer(value),
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
                        kafka.create_topic(topic)
                    except Exception:
                        logging.error(sys_exc(sys.exc_info()))
                    else:
                        for key, value in items.items():
                            # Populate topic
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
                    kafka.create_topic(topic)
                except Exception:
                    logging.error(sys_exc(sys.exc_info()))
                else:
                    with open(param["filename"], "r") as f:
                        data_to_load = json.loads(f.read())
                    for username, value in data_to_load.items():
                        # Populate topic
                        try:
                            value["hashed_password"] = hash_password(
                                password_salt,
                                value.get("password", "1234"),
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
        kafka.producer.flush()


if __name__ == "__main__":
    FILE_APP = os.path.splitext(os.path.split(__file__)[-1])[0]
    logging.basicConfig(
        format=f"[{FILE_APP}] %(asctime)s.%(msecs)03d [%(levelname)s]: %(message)s",
        level=logging.INFO,
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="Chatbot - Admin Plane")
    parser.add_argument(
        "--config",
        dest="config",
        type=str,
        help="Enter config filename (default: config/localhost.ini)",
        default=os.path.join("config", "localhost.ini"),
    )
    parser.add_argument(
        "--client-id",
        dest="client_id",
        type=str,
        help="Producer's Client ID prefix (default: chatbot-admin-plane)",
        default="chatbot-admin-plane-producer",
    )
    parser.add_argument(
        "--config-data",
        dest="config_data",
        type=str,
        help="Enter config filename for the data to be produced (default: config/default_loader.ini)",
        default=os.path.join("config", "default_loader.ini"),
    )
    parser.add_argument(
        "--env-vars",
        dest="env_vars",
        type=str,
        help="Enter environment variables file name (default: .env_demo)",
        default=".env_demo",
    )

    main(parser.parse_args())
