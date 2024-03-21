import os
import json
import logging
import argparse

from dotenv import load_dotenv
from configparser import ConfigParser

from confluent_kafka import Producer
from confluent_kafka.serialization import (
    StringSerializer,
    SerializationContext,
    MessageField,
)
from confluent_kafka.admin import AdminClient
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer

from utils import create_topic, delivery_report, hash_password


def main(args):
    # Load env variables
    load_dotenv(args.env_vars)

    # Kafka and Schema Registry Config
    config = ConfigParser()
    config.read(args.config)

    schema_registry_config = dict(config["schema-registry"])
    schema_registry_client = SchemaRegistryClient(schema_registry_config)
    string_serializer = StringSerializer("utf_8")

    producer_config = {
        "client.id": args.client_id,
    }
    producer_config.update(dict(config["kafka"]))
    producer = Producer(producer_config)

    # Get list of topics
    admin_client = AdminClient(producer_config)
    topic_list = admin_client.list_topics().topics.keys()

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
                    if topic not in topic_list:
                        logging.info(f"Creating topic '{topic}'")
                        create_topic(admin_client, topic)
                    else:
                        logging.info(f"Topic '{topic}' already exists")

                except Exception as err:
                    logging.error(f"{err}")
                else:
                    # Populate topic
                    with open(param["filename"], "r") as f:
                        data_to_load = json.loads(f.read())
                    for key, value in data_to_load.items():
                        try:
                            producer.poll(0.0)
                            producer.produce(
                                topic=topic,
                                key=string_serializer(key),
                                value=string_serializer(value),
                                on_delivery=delivery_report,
                            )
                        except Exception as err:
                            logging.error(f"{err}")

            elif rag in ["main_menu", "kids_menu"]:
                # Avro serialiser
                with open(param["schema"], "r") as f:
                    schema_str = f.read()
                avro_serializer = AvroSerializer(
                    schema_registry_client,
                    schema_str=schema_str,
                )

                topic_prefix = param["topic_prefix"]
                with open(param["filename"], "r") as f:
                    data_to_load = json.loads(f.read())

                for header, items in data_to_load.items():
                    topic = f"{topic_prefix}{header}"
                    # Create new topic if required
                    try:
                        if topic not in topic_list:
                            logging.info(f"Creating topic '{topic}'")
                            create_topic(admin_client, topic)
                        else:
                            logging.info(f"Topic '{topic}' already exists")
                    except Exception as err:
                        logging.error(f"{err}")
                    else:
                        for key, value in items.items():
                            # Populate topic
                            try:
                                producer.poll(0.0)
                                producer.produce(
                                    topic=topic,
                                    key=string_serializer(key),
                                    value=avro_serializer(
                                        value,
                                        SerializationContext(
                                            topic,
                                            MessageField.VALUE,
                                        ),
                                    ),
                                    on_delivery=delivery_report,
                                )
                            except Exception as err:
                                logging.error(f"{err}")

            elif rag in ["customer_profiles"]:
                password_salt = os.environ.get("PASSWORD_SALT")

                # Avro serialiser
                with open(param["schema"], "r") as f:
                    schema_str = f.read()
                avro_serializer = AvroSerializer(
                    schema_registry_client,
                    schema_str=schema_str,
                )

                # Create new topic if required
                topic = param["topic"]
                try:
                    if topic not in topic_list:
                        logging.info(f"Creating topic '{topic}'")
                        create_topic(admin_client, topic)
                    else:
                        logging.info(f"Topic '{topic}' already exists")
                except Exception as err:
                    logging.error(f"{err}")
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
                            producer.poll(0.0)
                            producer.produce(
                                topic=topic,
                                key=string_serializer(username),
                                value=avro_serializer(
                                    value,
                                    SerializationContext(
                                        topic,
                                        MessageField.VALUE,
                                    ),
                                ),
                                on_delivery=delivery_report,
                            )
                        except Exception as err:
                            logging.error(f"{err}")

    except KeyboardInterrupt:
        pass
    finally:
        logging.info("Flushing records...")
        producer.flush()


if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s.%(msecs)03d [%(levelname)s]: %(message)s",
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
        help="Producer's Client ID (default: xml-producer-demo-01)",
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
