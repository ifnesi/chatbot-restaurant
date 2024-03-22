import os
import sys
import json
import regex
import logging
import argparse

from dotenv import load_dotenv
from threading import Thread
from langchain_openai import ChatOpenAI
from langchain.schema import SystemMessage, HumanMessage

from utils import (
    KafkaClient,
    sys_exc,
    adjust_html,
    calculate_age,
    initial_prompt,
)


###########
# Classes #
###########
class LoadRAG:
    """Load RAG in memory"""

    def __init__(self, topics) -> None:
        self.rag = dict()
        self.customer_profile = dict()
        self.topics = topics

    def consumer(self, kafka) -> None:
        while True:
            for topic, _, key, value in kafka.avro_string_consumer(
                kafka.consumer_earliest,
                self.topics,
            ):
                if topic == TOPIC_CUSTOMER_PROFILES:
                    if value is None:
                        self.customer_profile.pop(key, None)
                        logging.info(f"Deleted profile for {key}")
                    else:
                        self.customer_profile[key] = value
                        logging.info(f"Loaded profile for {key}: {json.dumps(value)}")

                else:
                    rag_name = topic.split("-")[-1]
                    prefix, *suffix = rag_name.split("_")

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

                    else:
                        if rag_name not in self.rag.keys():
                            self.rag[rag_name] = dict()
                        if value is None:  # drop from RAG
                            self.rag[rag_name].pop(key, None)
                        else:
                            self.rag[rag_name][key] = value

                    if value is None:
                        logging.info(f"Deleted RAG for {key}")
                    else:
                        logging.info(f"Loaded RAG for {key}: {json.dumps(value)}")


####################
# Global Variables #
####################
chatSessions = dict()
chatMessages = dict()

kafka = None
customer_action_serialiser = None

TOPIC_CHATBOT_RESPONSES = "chatbot-restaurant-chatbot_responses"
TOPIC_CUSTOMER_ACTIONS = "chatbot-restaurant-customer_actions"
TOPIC_CUSTOMER_PROFILES = "chatbot-restaurant-customer_profiles"
TOPIC_RAG = "^chatbot-restaurant-rag-.*"
rag = LoadRAG(topics=[TOPIC_CUSTOMER_PROFILES, TOPIC_RAG])


########
# Main #
########
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

    # Start RAG / Customer Profile Consumer thread
    Thread(
        target=rag.consumer,
        args=(kafka,),
    ).start()

    # Process messages submitted by the customers
    while True:
        for _, _, key, value in kafka.avro_string_consumer(
            kafka.consumer_latest,
            [TOPIC_CUSTOMER_ACTIONS],
        ):
            counter = value["counter"]
            username = value["username"]

            if value["counter"] == -1:  # Logout message
                chatSessions.pop(key, None)
                chatMessages.pop(key, None)
                logging.info(f"{username} has logged out!")

            else:
                try:

                    if value["counter"] == 0:  # Initial message

                        # LLM Session
                        chatSessions[key] = ChatOpenAI(
                            model="gpt-3.5-turbo-16k",
                        )

                        waiter_name = value["waiter_name"]
                        customer_name = rag.customer_profile[username]["full_name"]
                        customer_dob = rag.customer_profile[username]["dob"]
                        customer_allergies = (
                            rag.customer_profile[username]["allergies"] or "Nothing"
                        )
                        
                        try:
                            customer_age = calculate_age(customer_dob)
                            dob_string = f"is {customer_age} years old"
                        except Exception:
                            logging.error(sys_exc(sys.exc_info()))
                            dob_string = f"born in {customer_dob}"
                        query = f"We have a new customer (name is {customer_name}, {dob_string}, allergic to {customer_allergies}). Greet they with a welcoming message"

                        context = content=initial_prompt(rag.rag, waiter_name)

                        chatMessages[key] = [
                            SystemMessage(context),
                            HumanMessage(
                                content=query
                            ),
                        ]
                        logging.info(f"{username} has logged in!")
                        logging.info(f"Context: {context}")
                        logging.info(f"Query: {query}")

                    else:  # customer message
                        customer_message = value["message"]
                        logging.info(f"Message received from {username}: {customer_message}")

                        chatMessages[key].append(
                            HumanMessage(
                                f"Customer has send the message below. Please address it making sure to comply with all restaurant policies:\n{customer_message}"
                            )
                        )

                    response = chatSessions[key].invoke(chatMessages[key])
                    chatMessages[key].append(response)
                    response = adjust_html(response.content, "table", "table table-striped table-hover table-responsive table-sm")

                except Exception:
                    logging.error(sys_exc(sys.exc_info()))
                    response = (
                        "<span class='error_message'>Sorry, something went wrong on the back-end! Please try again</span>"
                    )

                finally:  # publish message on the response topic
                    try:
                        kafka.producer.poll(0.0)
                        kafka.producer.produce(
                            topic=TOPIC_CHATBOT_RESPONSES,
                            key=kafka.string_serializer(f"{key}-{counter}"),
                            value=kafka.string_serializer(response),
                            on_delivery=kafka.delivery_report,
                        )
                    except Exception:
                        logging.error(sys_exc(sys.exc_info()))
                    finally:
                        if kafka.producer:
                            kafka.producer.flush()
