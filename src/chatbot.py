import os
import sys
import json
import logging
import argparse

from dotenv import load_dotenv
from threading import Thread
from langchain_openai import ChatOpenAI
from langchain.schema import SystemMessage, HumanMessage

from utils import (
    TOPIC_RAG,
    TOPIC_CUSTOMER_ACTIONS,
    TOPIC_CHATBOT_RESPONSES,
    TOPIC_CUSTOMER_PROFILES,
    KafkaClient,
    SerializationContext,
    MessageField,
    sys_exc,
    adjust_html,
    calculate_age,
    initial_prompt,
)


###########
# Classes #
###########
class LoadRAG:
    """Load in memory RAG / Customer Profiles"""

    def __init__(self, topics) -> None:
        self.rag = dict()
        self.customer_profile = dict()
        self.topics = topics

    def consumer(self, kafka) -> None:
        while True:
            for topic, headers, key, value in kafka.avro_string_consumer(
                kafka.consumer_earliest,
                self.topics,
            ):
                # Load Customer Profiles
                if topic == TOPIC_CUSTOMER_PROFILES:
                    if value is None:
                        self.customer_profile.pop(key, None)
                        logging.info(f"Deleted profile for {key}")
                    else:
                        self.customer_profile[key] = value
                        logging.info(f"Loaded profile for {key}: {json.dumps(value)}")

                # Load RAG
                else:
                    rag_name = topic.split("-")[-1]
                    prefix, *suffix = rag_name.split("_")

                    # Main and Kids menu
                    if prefix in ["menu", "kidsmenu"]:
                        suffix = "_".join(suffix)
                        if prefix not in self.rag.keys():
                            self.rag[prefix] = dict()
                        if suffix not in self.rag[prefix].keys():
                            self.rag[prefix][suffix] = dict()

                        if value is None:  # drop from RAG
                            self.rag[prefix][suffix].pop(key, None)
                        else:
                            self.rag[prefix][suffix][key] = value

                    # Policies, Restaurant and AI Rules
                    else:
                        if rag_name not in self.rag.keys():
                            self.rag[rag_name] = dict()

                        if value is None:  # drop from RAG
                            self.rag[rag_name].pop(key, None)
                        else:
                            self.rag[rag_name][key] = value["description"]

                    if value is None:
                        logging.info(f"Deleted RAG {rag_name} for {key}")
                    else:
                        logging.info(f"Loaded RAG {rag_name}: {json.dumps(value)}")


####################
# Global Variables #
####################
chatSessions = dict()
chatMessages = dict()

kafka = None
customer_action_serialiser = None

rag = LoadRAG(topics=[TOPIC_CUSTOMER_PROFILES, TOPIC_RAG])


########
# Main #
########
def main(args):

    # Load env variables
    load_dotenv(args.env_vars)

    kafka = KafkaClient(
        args.config,
        args.client_id,
        set_admin=True,
        set_producer=True,
        set_consumer_latest=True,
        set_consumer_earliest=True,
    )

    # Start RAG / Customer Profile Consumer thread (Kafka consumer #1)
    Thread(
        target=rag.consumer,
        args=(kafka,),
    ).start()

    # Avro serialiser (for the response topic)
    with open(os.path.join("schemas", "chatbot_response.avro"), "r") as f:
        schema_str = f.read()
    avro_serializer = kafka.avro_serialiser(schema_str)

    # Process messages submitted by the customers (Kafka consumer #2)
    while True:
        for topic, headers, key, value in kafka.avro_string_consumer(
            kafka.consumer_latest,
            [TOPIC_CUSTOMER_ACTIONS],
        ):
            session_id = key
            mid = value["mid"]
            username = value["username"]

            if mid is None:  # Logout message
                chatSessions.pop(session_id, None)
                chatMessages.pop(session_id, None)
                logging.info(f"{username} has logged out!")

            else:
                try:

                    if mid == 0:  # Initial message (after login)

                        # LLM Session
                        chatSessions[session_id] = ChatOpenAI(
                            model=os.environ.get("BASE_MODEL"),
                            temperature=float(os.environ.get("MODEL_TEMPERATURE")),
                        )

                        waiter_name = value["waiter_name"]
                        customer_name = rag.customer_profile[username]["full_name"]
                        customer_dob = rag.customer_profile[username]["dob"]
                        customer_allergies = (
                            rag.customer_profile[username]["allergies"] or "nothing"
                        )

                        context = initial_prompt(rag.rag, waiter_name)
                        try:
                            customer_age = calculate_age(customer_dob)
                            dob_string = f"is {customer_age} years old"
                        except Exception:
                            logging.error(sys_exc(sys.exc_info()))
                            dob_string = f"was born in {customer_dob}"
                        finally:
                            query = f"We have a new customer (name is {customer_name}, {dob_string}, allergic to {customer_allergies}). Greet they with a welcoming message"

                        chatMessages[session_id] = [
                            SystemMessage(context),
                            HumanMessage(query),
                        ]
                        logging.info(f"{username} has logged in!")
                        logging.info(f"Message ID: {mid}")
                        logging.info(f"Context: {context}")
                        logging.info(f"Query: {query}")

                    else:  # new customer message
                        customer_message = value["message"] or ""
                        logging.info(
                            f"Message received from {username}: {customer_message}"
                        )

                        chatMessages[session_id].append(HumanMessage(customer_message))

                    # Submit promt to LLM model
                    response = chatSessions[session_id].invoke(chatMessages[session_id])
                    chatMessages[session_id].append(response)
                    response = adjust_html(
                        response.content or "",
                        "table",
                        "table table-striped table-hover table-responsive table-sm",
                    )

                except Exception:
                    logging.error(sys_exc(sys.exc_info()))
                    response = "<span class='error_message'>Uh-oh! The back-end gears got jammed. Please try again in a bit</span>"

                finally:  # publish message in the response topic
                    try:
                        message = {
                            "mid": mid,
                            "response": response,
                        }
                        kafka.producer.poll(0.0)
                        kafka.producer.produce(
                            topic=TOPIC_CHATBOT_RESPONSES,
                            key=kafka.string_serializer(session_id),
                            value=avro_serializer(
                                message,
                                SerializationContext(
                                    TOPIC_CHATBOT_RESPONSES,
                                    MessageField.VALUE,
                                ),
                            ),
                            on_delivery=kafka.delivery_report,
                        )
                    except Exception:
                        logging.error(sys_exc(sys.exc_info()))
                    finally:
                        if kafka.producer:
                            kafka.producer.flush()


if __name__ == "__main__":
    FILE_APP = os.path.splitext(os.path.split(__file__)[-1])[0]
    logging.basicConfig(
        format=f"[{FILE_APP}] %(asctime)s.%(msecs)03d [%(levelname)s]: %(message)s",
        level=logging.INFO,
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="Chatbot - Backend Application")
    parser.add_argument(
        "--config",
        dest="config",
        type=str,
        help="Enter config filename (default: config/localhost.ini)",
        default=os.path.join("config", "localhost.ini"),
    )
    parser.add_argument(
        "--env-vars",
        dest="env_vars",
        type=str,
        help="Enter environment variables file name (default: .env_demo)",
        default=".env_demo",
    )
    parser.add_argument(
        "--client-id",
        dest="client_id",
        type=str,
        help="Producer/Consumer's Group/Client ID prefix (default: chatbot-beapp)",
        default="chatbot-app",
    )

    args = parser.parse_args()

    main(parser.parse_args())
