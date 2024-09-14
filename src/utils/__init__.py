import re
import os
import sys
import json
import time
import signal
import hashlib
import logging

from queue import Queue
from bs4 import BeautifulSoup
from datetime import date, datetime
from configparser import ConfigParser
from passlib.hash import des_crypt
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
TOPIC_LOGGING = "chatbot-logs"
TOPIC_CUSTOMER_ACTIONS = "chatbot-customer_actions"
TOPIC_CHATBOT_RESPONSES = "chatbot-chatbot_responses"
TOPIC_DB_EXTRAS = "db.public.extras"
TOPIC_DB_AI_RULES = "db.public.ai_rules"
TOPIC_DB_POLICIES = "db.public.policies"
TOPIC_DB_MAIN_MENU = "db.public.main_menu"
TOPIC_DB_KIDS_MENU = "db.public.kids_menu"
TOPIC_DB_RESTAURANT = "db.public.restaurant"
TOPIC_DB_CUSTOMER_PROFILES = "db.public.customer_profiles"
VDB_COLLECTION = "chatbot_restaurant"
SENTENCE_TRANSFORMER = "all-MiniLM-L6-v2"


###########
# Classes #
###########
class KafkaLogHandler(logging.StreamHandler):
    def __init__(
        self,
        kafka,
        topic: str,
        file_app: str,
    ) -> None:
        """Log handler to submit python logs to Kafka"""
        super(KafkaLogHandler, self).__init__()
        self.string_serializer = StringSerializer("utf_8")
        self.kafka = kafka
        self.topic = topic
        self.formatter = logging.Formatter(
            f"[{file_app}] %(asctime)s.%(msecs)03d [%(levelname)s]: %(message)s"
        )

    def _append_handler(self) -> None:
        self.kafka.create_topic(
            self.topic,
            cleanup_policy="delete",
            sync=True,
        )
        self.setLevel(logging.INFO)
        self.setFormatter(self.formatter)
        logging.getLogger().addHandler(self)

    def emit(
        self,
        record: str,
    ) -> None:
        if self.kafka.producer_log:
            try:
                if record:
                    self.kafka.producer_log.poll(0.0)
                    self.kafka.producer_log.produce(
                        topic=self.topic,
                        value=self.string_serializer(self.format(record)),
                    )
                    self.kafka.producer_log.flush()
            except Exception:
                logging.error(sys_exc(sys.exc_info()))
            finally:
                self.flush()


class KafkaClient:
    """Kafka Producer/Consumer instances with signal handler"""

    def __init__(
        self,
        config_file: str,
        client_id: str,
        file_app: str = None,
        set_producer: bool = False,
        set_consumer: bool = False,
        auto_offset_reset: str = "earliest",
        enable_auto_commit: bool = False,
    ) -> None:
        self.producer = None
        self.producer_log = None
        self.admin_client = None
        self.consumer = None

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

        # Producer(s)
        self._producer_config = dict(self._config["kafka"])
        if set_producer:
            self._producer_config["client.id"] = f"{client_id}-producer"
            self.producer = Producer(self._producer_config)

        # Admin
        self.admin_client = AdminClient(self._producer_config)

        # Get list of topics
        self.topic_list = self.get_topics()

        # Log producer
        if file_app:
            self._producer_config["client.id"] = f"{client_id}-producer-logger"
            self.producer_log = Producer(self._producer_config)
            # Append Log Handlers (Kafka)
            log_handler = KafkaLogHandler(
                self,
                TOPIC_LOGGING,
                file_app,
            )
            log_handler._append_handler()

        # Consumer
        if set_consumer:
            self._consumer_config = {
                "group.id": f"{client_id}-consumer",
                "client.id": f"{client_id}-consumer-01",
                "auto.offset.reset": auto_offset_reset,
                "enable.auto.commit": "true" if enable_auto_commit else "false",
            }
            self._consumer_config.update(dict(self._config["kafka"]))
            self.consumer = Consumer(self._consumer_config)

    def signal_handler(
        self,
        sig,
        frame,
    ):
        if self.producer:
            logging.info("Flushing messages")
            try:
                self.producer.flush()
                self.producer = None
            except Exception:
                logging.error(sys_exc(sys.exc_info()))

        if self.consumer:
            logging.info(
                f"Closing consumer {self._consumer_config['client.id']} ({self._consumer_config['group.id']})"
            )
            try:
                self.consumer.close()
                self.consumer = None
            except Exception:
                logging.error(sys_exc(sys.exc_info()))

        if self.producer_log:
            try:
                self.producer_log.flush()
                self.producer_log = None
            except Exception:
                pass  # do not log response as the logger kafka producer is now closed/flushed

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
        if isinstance(msg.key(), bytes):
            key = msg.key().decode("utf-8")
        else:
            key = msg.key()
        if err is not None:
            logging.error(
                f"Delivery failed for record/key '{key}' for the topic '{msg.topic()}': {err}"
            )
        else:
            logging.info(
                f"Record/key '{key}' successfully produced to topic/partition '{msg.topic()}/{msg.partition()}' at offset #{msg.offset()}"
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
            logging.info(f"Creating topic '{topic}'")
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

    def __init__(self, topics: list = None) -> None:
        self.data = dict()
        self.rag_data = dict()
        self.queue = Queue()
        self.topics = topics
        self._pattern_app = re.compile(r"^\[(.*?)\]")
        self._pattern_level = re.compile(r"\[([A-Z]+)\]\:")

    def _get_regex(self, pattern: re.Pattern, text: str) -> str:
        result = pattern.findall(text) or [""]
        return result[0]

    def consumer(self, kafka) -> None:
        for topic, _, _, value in kafka.avro_string_consumer(
            kafka.consumer,
            self.topics,
        ):
            try:
                if topic == TOPIC_LOGGING:  # Add log data into the local queue
                    file_app = self._get_regex(self._pattern_app, value)
                    value = value.strip().replace(
                        f"[{file_app}]", f"<b>[{file_app}]</b>"
                    )

                    log_level = self._get_regex(self._pattern_level, value)
                    value = value.strip().replace(
                        f"[{log_level}]: ", f"<b>[{log_level}]</b><br>"
                    )

                    while "\n" in value:
                        value = value.replace("\n", "<br>")
                    self.queue.put(f"<div class='log-{file_app}'>{value}</div>")

                else:
                    if isinstance(value, dict):
                        payload_op, payload_key, payload_value = get_key_value(value)

                        if topic == TOPIC_DB_CUSTOMER_PROFILES:  # Load customer profile
                            if payload_op == "d":
                                self.data.pop(payload_key, None)
                                logging.info(f"Deleted {topic} for {payload_key}")

                            else:
                                payload_value["dob"] = time.strftime(
                                    "%Y/%m/%d",
                                    time.localtime(payload_value["dob"] * 60 * 60 * 24),
                                )
                                self.data[payload_key] = payload_value
                                logging.info(
                                    f"Loaded customer profile for {payload_key}: {json.dumps(payload_value)}"
                                )

                        else:
                            if topic == TOPIC_DB_AI_RULES:
                                rag_name = "ai_rules"
                            elif topic == TOPIC_DB_POLICIES:
                                rag_name = "policies"
                            elif topic == TOPIC_DB_EXTRAS:
                                rag_name = "extras"
                            elif topic == TOPIC_DB_MAIN_MENU:
                                rag_name = "menu"
                            elif topic == TOPIC_DB_KIDS_MENU:
                                rag_name = "kidsmenu"
                            else:
                                rag_name = "restaurant"

                            if payload_op == "d":
                                self.rag_data[rag_name].pop(payload_key, None)
                                logging.info(f"Deleted {rag_name} for {payload_key}")

                            else:
                                # Main and Kids menu
                                if rag_name in ["menu", "kidsmenu"]:
                                    rag_value = payload_value
                                # Extras, Policies, Restaurant and AI Rules
                                else:
                                    rag_value = payload_value["description"]

                                # Update Data
                                if rag_name not in self.rag_data.keys():
                                    self.rag_data[rag_name] = dict()
                                self.rag_data[rag_name][payload_key] = rag_value
                                logging.info(
                                    f"Loaded {rag_name} for {payload_key}: {rag_value}"
                                )
            except Exception:
                logging.error(sys_exc(sys.exc_info()))


#############
# Functions #
#############
def flat_sql(
    data: str,
    env_vars: dict,
) -> list:
    result = data.replace("\r", "").replace("\n", " ").replace("\t", " ")
    for var in set(re.findall("\$ENV\.([\w_-]*)", data)):
        result = result.replace(f"$ENV.{var}", env_vars.get(var, ""))
    while "  " in result:
        result = result.replace("  ", " ")
    return [f"{n.strip()};" for n in result.split(";") if n.strip()]


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
            result += (
                f"{ord}.{n+1} {section.replace('_', ' ').replace('-', ' ').title()}:\n"
            )
            m = 0
            for v in rag_data.values():
                # Filter by menu section
                if v["section"] == section:
                    result += f"{ord}.{n+1}.{m+1} {v['name'].replace('_', ' ').replace('-', ' ').title()} ({v['description']}): "
                    items = list()
                    for key, value in v.items():
                        if key not in ["name", "description", "section"]:
                            items.append(f"{key.title()} {value}")
                    result += f"{', '.join(items)}\n"
                    m += 1
        return result

    result = f"You are an AI Assistant for a restaurant. Your name is: {waiter_name}.\n"
    result += "1. You MUST comply with these AI rules:\n"
    for key, value in rag_data.get("ai_rules", dict()).items():
        result += f"- {key.replace('_', ' ').replace('-', ' ').title()}: {value}\n"
    result += "2. Details about the restaurant you work for:\n"
    for key, value in rag_data.get("restaurant", dict()).items():
        result += f"- {key.replace('_', ' ').replace('-', ' ').title()}: {value}\n"
    result += "3. Restaurant policies:\n"
    for key, value in rag_data.get("policies", dict()).items():
        result += f"- {key.replace('_', ' ').replace('-', ' ').title()}: {value}\n"
    result += "4. Main menu:\n"
    result += get_menu(
        rag_data.get("menu", dict()),
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
        rag_data.get("kidsmenu", dict()),
        [
            "starters",
            "mains",
            "drinks",
            "desserts",
        ],
        5,
    )
    return result


def assess_password(
    salt: str,
    hashed_password: str,
    password: str,
) -> bool:
    return des_crypt.using(salt=salt[:2]).hash(password) == hashed_password


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


def md5_hash(text: bytes) -> str:
    # return int(hashlib.md5(text.encode("utf-8")).hexdigest(), 16)
    hash = hashlib.md5(text.encode("utf-8")).hexdigest()
    return f"{hash[:8]}-{hash[8:12]}-{hash[12:16]}-{hash[16:20]}-{hash[20:]}"


def unset_flag(filename: str) -> None:
    if os.path.exists(filename):
        os.remove(filename)


def set_flag(filename: str) -> None:
    open(filename, "w").close()


def get_key_value(
    value: dict,
    key: str = "id",
) -> tuple:
    if value["op"] in ["c", "u"]:  # Create / Update
        index = "after"
    else:  # Delete
        index = "before"
    payload_value = dict(value[index])
    payload_key = payload_value[key]
    payload_value.pop(key, None)
    return (
        value["op"],
        payload_key,
        payload_value,
    )
