import sys
import hmac
import json
import time
import base64
import signal
import hashlib
import logging

from queue import Queue
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
TOPIC_LOGGING = "chatbot-restaurant-logs"
TOPIC_CUSTOMER_ACTIONS = "chatbot-restaurant-customer_actions"
TOPIC_CUSTOMER_PROFILES = "chatbot-restaurant-customer_profiles"
TOPIC_CHATBOT_RESPONSES = "chatbot-restaurant-chatbot_responses"


###########
# Classes #
###########
class KafkaLogHandler(logging.StreamHandler):
    def __init__(
        self,
        kafka,
        topic: str,
    ) -> None:
        super(KafkaLogHandler, self).__init__()
        self.string_serializer = StringSerializer("utf_8")
        self.kafka = kafka
        self.topic = topic

    def emit(
        self,
        record: str,
    ) -> None:
        if self.kafka.producer_log:
            try:
                self.kafka.producer_log.poll(0.0)
                self.kafka.producer_log.produce(
                    topic=self.topic,
                    value=self.string_serializer(self.format(record)),
                )
                self.kafka.producer_log.flush()
            except Exception:
                pass
            finally:
                self.flush()


class KafkaClient:
    def __init__(
        self,
        config_file: str,
        client_id: str,
        file_app,
        set_consumer_earliest: bool = False,
        set_consumer_latest: bool = False,
    ) -> None:
        self.producer = None
        self.producer_log = None
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
        self.producer = Producer(self._producer_config)
        self._producer_config["client.id"] = f"{client_id}-producer-logger"
        self.producer_log = Producer(self._producer_config)

        # Admin
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

        # Add Kafka log handler
        self.create_topic(
            TOPIC_LOGGING,
            cleanup_policy="delete",
            sync=True,
        )
        kafka_log_handler = KafkaLogHandler(
            self,
            TOPIC_LOGGING,
        )
        kafka_log_handler.setLevel(logging.INFO)
        kafka_log_handler.setFormatter(
            logging.Formatter(f"[{file_app}] %(asctime)s.%(msecs)03d [%(levelname)s]: %(message)s")
        )
        logging.getLogger().addHandler(kafka_log_handler)

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

            try:
                self.producer_log.flush()
                self.producer_log = None
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
        sync: bool = False,
        timeout_seconds_sync: int = 30,
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
            # The create topic API is asynchronous, so to make it synchronous it is needed to check whether the topic has been created
            if sync:
                start_time = time.time()
                topic_created = False
                while time.time() - start_time < timeout_seconds_sync:
                    time.sleep(1)
                    if topic in self.get_topics():
                        topic_created = True
                        break
                if not topic_created:
                    raise KafkaException(f"Unable to create topic '{topic}': Timeout")
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


class CustomerProfilesAndLogs:
    """Load customer profile in memory and Logs into a queue"""

    def __init__(self, topics) -> None:
        self.data = dict()
        self.queue = Queue()
        self.topics = topics

    def consumer(self, kafka) -> None:
        while True:
            for topic, headers, key, value in kafka.avro_string_consumer(
                kafka.consumer_earliest,
                self.topics,
            ):
                if value is None:
                    self.data.pop(key, None)
                    logging.info(f"Deleted customer profile for {key}")
                else:
                    if topic == TOPIC_LOGGING:
                        value = value.strip()
                        while "\n" in value:
                            value = value.replace("\n", "<br>")
                        self.queue.put(f"{value}<br>")
                    else:
                        self.data[key] = value
                        logging.info(f"Loaded customer profile for {key}: {json.dumps(value)}")


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
    def get_menu(
        rag_data: dict,
        sections: list,
        ord: int,
    ) -> str:
        result = ""
        for n, section in enumerate(sections):
            result += f"- {ord}.{n+1} {section}:\n"
            for m, data in enumerate(rag_data[section].values()):
                result += (
                    f"  - {ord}.{n+1}.{m+1} {data['name']} ({data['description']}): "
                )
                items = list()
                for key, value in data.items():
                    if key not in ["name", "description"]:
                        items.append(f"{key} {value}")
                result += f"{', '.join(items)}\n"
        return result

    result = f"You are an AI Assistant for a restaurant. Your name is: {waiter_name}.\n"
    result += "1. You MUST comply with these AI rules:\n"
    for key, value in rag_data["ai_rules"].items():
        result += f"- {key}: {value}\n"
    result += "2. Details about the restaurant you work for:\n"
    for key, value in rag_data["restaurant"].items():
        result += f"- {key}: {value}\n"
    result += "3. Restaurant policies:\n"
    for key, value in rag_data["policies"].items():
        result += f"- {key}: {value}\n"
    result += "4. Main menu:\n"
    result += get_menu(
        rag_data["menu"],
        [
            "starters",
            "mains",
            "alcoholic_drinks",
            "non_alcoholic_drinks",
            "hot_drinks",
            "desserts",
        ],
        4,
    )
    result += f"5. Kids menu:\n"
    result += get_menu(
        rag_data["kidsmenu"],
        [
            "starters",
            "mains",
            "drinks",
            "desserts",
        ],
        5,
    )
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
    replacements = [
        ["`` `", "```"],
        ["`` ` ", "```"],
        ["```html", ""],
        ["```json", ""],
        ["```", ""],
    ]
    result = str(soup)
    for repl in replacements:
        result = result.replace(repl[0], repl[1])
    return result


def md5_int(text: bytes) -> int:
    return int(hashlib.md5(text.encode("utf-8")).hexdigest(), 16)
