import sys
import hmac
import json
import base64
import signal
import hashlib
import logging

from bs4 import BeautifulSoup
from datetime import date, datetime
from configparser import ConfigParser
from dateutil.relativedelta import relativedelta

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


####################
# Global Variables #
####################
TOPIC_RAG = "^chatbot-restaurant-rag-.*"
TOPIC_CUSTOMER_ACTIONS = "chatbot-restaurant-customer_actions"
TOPIC_CUSTOMER_PROFILES = "chatbot-restaurant-customer_profiles"
TOPIC_CHATBOT_RESPONSES = "chatbot-restaurant-chatbot_responses"

###########
# Classes #
###########
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
                "enable.auto.commit": "false",
            }
            self._consumer_config_earliest.update(dict(self._config["kafka"]))
            self.consumer_earliest = Consumer(self._consumer_config_earliest)

        # Consumer Latest
        if set_consumer_latest:
            self._consumer_config_latest = {
                "group.id": f"{client_id}-consumer-latest",
                "client.id": f"{client_id}-consumer-latest-01",
                "auto.offset.reset": "latest",
                "enable.auto.commit": "true",
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
                self.consumer_latest.commit()
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

    def avro_string_consumer(
        self,
        consumer,
        topics: list,
        schema_str: str = None,
    ):
        avro_deserialiser = self.avro_deserialiser(schema_str=schema_str)
        consumer.subscribe(topics)

        while True:
            try:
                if consumer:
                    msg = consumer.poll(timeout=0.25)
                    if msg is not None:
                        if msg.error():
                            raise KafkaException(msg.error())
                        else:
                            if msg.value() is not None:
                                if msg.value()[0] == 0:  # Avro serialised
                                    message = avro_deserialiser(
                                        msg.value(),
                                        SerializationContext(
                                            msg.topic(),
                                            MessageField.VALUE,
                                        ),
                                    )
                                else:
                                    message = self.string_deserializer(msg.value())
                            else:
                                message = msg.value()

                            yield (
                                msg.topic(),
                                msg.headers(),
                                self.string_deserializer(msg.key()),
                                message,
                            )

            except Exception:
                logging.error(sys_exc(sys.exc_info()))


class CustomerProfiles:
    """Load customer profile in memory"""

    def __init__(self, topics) -> None:
        self.data = dict()
        self.topics = topics

    def consumer(self, kafka) -> None:
        while True:
            for topic, headers, key, value in kafka.avro_string_consumer(
                kafka.consumer_earliest,
                self.topics,
            ):
                if value is None:
                    self.data.pop(key, None)
                    logging.info(f"Deleted profile for {key}")
                else:
                    self.data[key] = value
                    logging.info(f"Loaded profile for {key}: {json.dumps(value)}")


#############
# Functions #
#############
def calculate_age(birth_date: str) -> int:
    birth_date_parsed = datetime.strptime(birth_date, "%Y/%m/%d")
    today = date.today()
    age = relativedelta(today, birth_date_parsed)
    return age.years


def sys_exc(exc_info) -> str:
    exc_type, exc_obj, exc_tb = exc_info
    return f"{exc_type} | {exc_tb.tb_lineno} | {exc_obj}"


def initial_prompt(
    rag_data: dict,
    waiter_name: str,
) -> str:
    result = f"You are an AI Assistant for a restaurant. Your name is: {waiter_name}.\n"
    result += f"Here is the context required to answer all customers questions:\n"
    result += f"1. Details about the restaurant you work for:\n{json.dumps(rag_data['restaurant'])}\n"
    result += f"2. Restaurant policies:\n{json.dumps(rag_data['policies'])}\n"
    result += f"3. You MUST comply with these AI rules:\n{json.dumps(rag_data['ai_rules'])}\n"
    result += f"4. Main menu:\n{json.dumps(rag_data['menu'])}\n"
    result += f"5. Kids menu:\n{json.dumps(rag_data['kidsmenu'])}"
    return result


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


def adjust_html(
    html: str,
    element: str,
    classes: str,
) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for item in soup.find_all(element):
        item["class"] = classes
    for e in ["h1", "h2", "h3", "h4", "h5"]:
        for header in soup.find_all(e):
            header.name = "h6"
    return str(soup)
