import sys
import hmac
import base64
import signal
import hashlib
import logging

from configparser import ConfigParser

from confluent_kafka import Producer, Consumer, KafkaException
from confluent_kafka.admin import NewTopic
from confluent_kafka.serialization import (
    StringSerializer,
    StringDeserializer,
    SerializationContext,
    MessageField,
)
from confluent_kafka.admin import AdminClient
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer, AvroDeserializer


class KafkaClient:
    def __init__(
        self,
        config_file: str,
        client_id: str,
        set_admin: bool = False,
        set_producer: bool = False,
        set_consumer_earliest: bool = False,
        set_consumer_latest: bool = False,
    ) -> None:
        self.producer = None
        self.admin_client = None
        self.consumer_latest = None
        self.consumer_earliest = None

        # Set signal handlers
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

        self._config = ConfigParser()
        self._config.read(config_file)

        # String SerDes
        self.string_serializer = StringSerializer("utf_8")
        self.string_deserializer = StringDeserializer("utf_8")

        # Schema Registry
        self._schema_registry_config = dict(self._config["schema-registry"])
        self.schema_registry_client = SchemaRegistryClient(self._schema_registry_config)

        # Producer
        self._producer_config = {
            "client.id": f"{client_id}-producer",
        }
        self._producer_config.update(dict(self._config["kafka"]))
        if set_producer:
            self.producer = Producer(self._producer_config)

        # Admin
        if set_admin:
            self.admin_client = AdminClient(self._producer_config)
            # Get list of topics
            self.topic_list = self.get_topics()

        # Consumer Earliest
        if set_consumer_earliest:
            self._consumer_config_earliest = {
                "group.id": f"{client_id}-consumer-earliest",
                "client.id": f"{client_id}-consumer-earliest-01",
                "auto.offset.reset": "earliest",
                "enable.auto.commit": False,
            }
            self._consumer_config_earliest.update(dict(self._config["kafka"]))
            self.consumer_earliest = Consumer(self._consumer_config_earliest)

        # Consumer Latest
        if set_consumer_latest:
            self._consumer_config_latest = {
                "group.id": f"{client_id}-consumer-latest",
                "client.id": f"{client_id}-consumer-latest-01",
                "auto.offset.reset": "earliest",
                "enable.auto.commit": False,
            }
            self._consumer_config_latest.update(dict(self._config["kafka"]))
            self.consumer_latest = Consumer(self._consumer_config_latest)

    def signal_handler(
        self,
        sig,
        frame,
    ):
        if self.producer:
            logging.info("Flushing messages...")
            try:
                self.producer.flush()
                self.producer = None
            except Exception:
                logging.error(sys_exc(sys.exc_info()))

        if self.consumer_earliest:
            logging.info(
                f"Closing consumer {self._consumer_config_earliest['client.id']} ({self._consumer_config_earliest['group.id']})..."
            )
            try:
                self.consumer_earliest.close()
                self.consumer_earliest = None
            except Exception:
                logging.error(sys_exc(sys.exc_info()))

        if self.consumer_latest:
            logging.info(
                f"Closing consumer {self._consumer_config_latest['client.id']} ({self._consumer_config_latest['group.id']})..."
            )
            try:
                self.consumer_latest.close()
                self.consumer_latest = None
            except Exception:
                logging.error(sys_exc(sys.exc_info()))

        sys.exit(0)

    def avro_serialiser(
        self,
        schema_str: str,
    ):
        return AvroSerializer(
            self.schema_registry_client,
            schema_str=schema_str,
        )

    def avro_deserialiser(
        self,
        schema_str: str = None,
    ):
        return AvroDeserializer(
            self.schema_registry_client,
            schema_str=schema_str,
        )

    def get_topics(self) -> list:
        return self.admin_client.list_topics().topics.keys()

    def delivery_report(
        self,
        err,
        msg,
    ) -> None:
        if err is not None:
            logging.error(
                f"Delivery failed for record {msg.key()} for the topic '{msg.topic()}': {err}"
            )
        else:
            logging.info(
                f"Record {msg.key()} successfully produced to topic/partition '{msg.topic()}/{msg.partition()}' at offset #{msg.offset()}"
            )

    def create_topic(
        self,
        topic: str,
        num_partitions: int = 1,
        replication_factor: int = 1,
        cleanup_policy: str = "compact",
    ) -> None:
        if topic not in self.topic_list:
            logging.info(f"Creating topic '{topic}'...")
            self.admin_client.create_topics(
                [
                    NewTopic(
                        topic=topic,
                        num_partitions=num_partitions,
                        replication_factor=replication_factor,
                        config={
                            "cleanup.policy": cleanup_policy,
                        },
                    )
                ]
            )
        else:
            logging.info(f"Topic '{topic}' already exists")

    def avro_consumer(
        self,
        consumer,
        topics: list,
        schema_str: str = None,
    ):
        avro_deserialiser = self.avro_deserialiser(schema_str=schema_str)
        consumer.subscribe(topics)

        while True:
            try:
                msg = consumer.poll(timeout=0.25)
                if msg is not None:
                    if msg.error():
                        raise KafkaException(msg.error())
                    else:
                        message = avro_deserialiser(
                            msg.value(),
                            SerializationContext(
                                msg.topic(),
                                MessageField.VALUE,
                            ),
                        )
                        yield (
                            msg.topic(),
                            msg.headers(),
                            self.string_deserializer(msg.key()),
                            message,
                        )

            except Exception:
                logging.error(sys_exc(sys.exc_info()))


def sys_exc(exc_info) -> str:
    exc_type, exc_obj, exc_tb = exc_info
    return f"{exc_type} | {exc_tb.tb_lineno} | {exc_obj}"


def initial_prompt(
    rag_data: dict,
    waiter_name: str,
) -> str:
    initial_prompt = (
        f"You are an AI Assistant for a restaurant. Your name is: {waiter_name}\n"
    )
    initial_prompt += f"Below the context required to answer all customers questions:\n"
    initial_prompt += "1. Details about the restaurant you work for:\n"
    for key, value in rag_data["restaurant"].items():
        initial_prompt += f"- {key}: {value}\n"

    initial_prompt += "2. Restaurant policies:\n"
    for key, value in rag_data["policies"].items():
        initial_prompt += f"- {key}: {value}\n"

    initial_prompt += "3. Main menu:\n"
    for n, key in enumerate(rag_data["main_menu"].keys()):
        initial_prompt += f"3.{n+1} {key}:\n"
        for item in rag_data["main_menu"][key].values():
            initial_prompt += f"- {item['name']} ({item['description']}): "
            details = list()
            for k, v in item.items():
                if k not in ["name", "description"]:
                    details.append(f"{k}: {v}")
            initial_prompt += f"{', '.join(details)}\n"

    initial_prompt += "4. Kids menu:\n"
    for n, key in enumerate(rag_data["kids_menu"].keys()):
        initial_prompt += f"4.{n+1} {key}:\n"
        for item in rag_data["kids_menu"][key].values():
            initial_prompt += f"- {item['name']} ({item['description']}): "
            details = list()
            for k, v in item.items():
                if k not in ["name", "description"]:
                    details.append(f"{k}: {v}")
            initial_prompt += f"{', '.join(details)}\n"

    initial_prompt += "5. As an AI Assistant you must comply with all policies below:\n"
    for key, value in rag_data["ai_rules"].items():
        initial_prompt += f"- {key}: {value}\n"

    return initial_prompt


def hash_password(
    salt: str,
    password: str,
) -> str:
    hashed_password = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100000,
    )
    return base64.b64encode(hashed_password).decode("utf-8")


def assess_password(
    salt: str,
    hashed_password: str,
    password: str,
) -> bool:
    return hmac.compare_digest(
        base64.b64decode(hashed_password.encode("utf-8")),
        hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            100000,
        ),
    )
