import os
import sys
import json
import time
import boto3
import logging
import requests

from dotenv import load_dotenv, find_dotenv
from threading import Thread
from langchain_aws import ChatBedrock
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from langchain.schema import SystemMessage, HumanMessage, AIMessage
from langchain_community.callbacks.manager import get_openai_callback

from qdrant_client import QdrantClient
from qdrant_client.http import models

from utils import (
    TOPIC_CUSTOMER_ACTIONS,
    TOPIC_CHATBOT_RESPONSES,
    TOPIC_DB_CUSTOMER_PROFILES,
    TOPIC_DB_RESTAURANT,
    TOPIC_DB_MAIN_MENU,
    TOPIC_DB_KIDS_MENU,
    TOPIC_DB_AI_RULES,
    TOPIC_DB_POLICIES,
    VDB_COLLECTION,
    KafkaClient,
    SerializationContext,
    MessageField,
    sys_exc,
    set_flag,
    unset_flag,
    adjust_html,
    calculate_age,
    get_key_value,
    initial_prompt,
)


####################
# Global Variables #
####################
chatSessions = dict()
chatMessages = dict()
chatVectorDB = dict()


###########
# Classes #
###########
class LoadRAG:
    """Load RAG / Customer Profiles"""

    def __init__(
        self,
        vdb_client,
        vdb_collection,
        topics: list = None,
    ) -> None:
        self.rag = dict()
        self.customer_profile = dict()
        self.topics = topics
        self.vdb_client = vdb_client
        self.vdb_collection = vdb_collection

    def consumer(self, kafka) -> None:
        for topic, _, _, value in kafka.avro_string_consumer(
            kafka.consumer,
            self.topics,
        ):
            try:
                if isinstance(value, dict):
                    payload_op, payload_key, payload_value = get_key_value(value)

                    # Load Customer Profiles
                    if topic == TOPIC_DB_CUSTOMER_PROFILES:
                        if payload_key not in self.customer_profile:
                            self.customer_profile[payload_key] = dict()

                        if payload_op == "d":
                            self.customer_profile.pop(payload_key, None)
                            logging.info(f"Deleted customer profile for {payload_key}")
                        else:
                            payload_value["dob"] = time.strftime(
                                "%Y/%m/%d",
                                time.localtime(payload_value["dob"] * 60 * 60 * 24),
                            )
                            self.customer_profile[payload_key] = payload_value
                            logging.info(
                                f"Loaded customer profile for {payload_key}: {json.dumps(payload_value)}"
                            )

                    # Main and Kids menu
                    elif topic in [TOPIC_DB_MAIN_MENU, TOPIC_DB_KIDS_MENU]:
                        menu_type = (
                            "menu" if topic == TOPIC_DB_MAIN_MENU else "kidsmenu"
                        )
                        if menu_type not in self.rag:
                            self.rag[menu_type] = dict()
                        if payload_key not in self.rag[menu_type]:
                            self.rag[menu_type][payload_key] = dict()

                        if payload_op == "d":
                            self.rag[menu_type].pop(payload_key, None)
                            logging.info(f"Deleted {menu_type} for {payload_key}")
                        else:
                            self.rag[menu_type][payload_key] = payload_value
                            logging.info(
                                f"Upserted {menu_type} for {payload_key}: {json.dumps(payload_value)}"
                            )

                    # Load additional data (policies, restaurant, ai rules)
                    else:
                        if topic == TOPIC_DB_AI_RULES:
                            rag_name = "ai_rules"
                        elif topic == TOPIC_DB_POLICIES:
                            rag_name = "policies"
                        else:
                            rag_name = "restaurant"

                        if rag_name not in self.rag:
                            self.rag[rag_name] = dict()
                        if payload_key not in self.rag[rag_name]:
                            self.rag[rag_name][payload_key] = dict()

                        if payload_op == "d":
                            self.rag[rag_name].pop(payload_key, None)
                            logging.info(f"Deleted {rag_name} for {payload_key}")
                        else:
                            payload_value = payload_value["description"]
                            self.rag[rag_name][payload_key] = payload_value
                            logging.info(
                                f"Loaded {rag_name} for {payload_key}: {payload_value}"
                            )
            except Exception:
                logging.error(sys_exc(sys.exc_info()))


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

    VECTOR_DB_MIN_SCORE = float(env_vars.get("VECTOR_DB_MIN_SCORE", 0.3))
    VECTOR_DB_SEARCH_LIMIT = int(env_vars.get("VECTOR_DB_SEARCH_LIMIT", 2))

    # Qdrant (Vector-DB)
    logging.info("Loading VectorDB client (Qdrant)")
    VDB_CLIENT = QdrantClient(
        host="qdrant",
        port=6333,
    )

    # # Create collection
    logging.info(f"Creating VectorDB collection: {VDB_COLLECTION}")
    VDB_CLIENT.create_collection(
        collection_name=VDB_COLLECTION,
        vectors_config=models.VectorParams(
            size=384,
            distance=models.Distance.COSINE,
        ),
    )

    # Set flag here to allow time to connect to Qdrant
    set_flag(FLAG_FILE)

    # Class instance to load RAG data
    rag = LoadRAG(
        VDB_CLIENT,
        VDB_COLLECTION,
        topics=[
            TOPIC_DB_CUSTOMER_PROFILES,
            TOPIC_DB_AI_RULES,
            TOPIC_DB_POLICIES,
            TOPIC_DB_RESTAURANT,
            TOPIC_DB_MAIN_MENU,
            TOPIC_DB_KIDS_MENU,
        ],
    )

    # Start RAG / Customer Profile and Restaurant data Consumer thread (Kafka consumer #1)
    kafka_rag = KafkaClient(
        env_vars.get("KAFKA_CONFIG"),
        f"{env_vars.get('CLIENT_ID_CHATBOT')}-RAG",
        file_app=FILE_APP,
        set_consumer=True,
    )
    Thread(
        target=rag.consumer,
        args=(kafka_rag,),
    ).start()

    # Avro serialiser (for the response topic)
    kafka = KafkaClient(
        env_vars.get("KAFKA_CONFIG"),
        env_vars.get("CLIENT_ID_CHATBOT"),
        set_consumer=True,
        set_producer=True,
        auto_offset_reset="latest",
        enable_auto_commit=True,
    )
    with open(os.path.join("schemas", "chatbot_response.avro"), "r") as f:
        schema_str = f.read()
    avro_serializer = kafka.avro_serialiser(schema_str)

    llm_engine = env_vars.get("LLM_ENGINE").lower()
    if llm_engine == "bedrock":
        # Start AWS session
        AWS_SERVER_PUBLIC_KEY, *AWS_SERVER_SECRET_KEY = env_vars.get(
            "AWS_API_KEY"
        ).split(":")
        aws_client = boto3.client(
            "bedrock-runtime",
            aws_access_key_id=AWS_SERVER_PUBLIC_KEY,
            aws_secret_access_key=":".join(AWS_SERVER_SECRET_KEY),
            region_name=env_vars.get("AWS_REGION"),
        )

    embedding_url = f"http://localhost:{os.environ.get('EMBEDDING_PORT')}{os.environ.get('EMBEDDING_PATH')}"

    # Process messages submitted by the customers (Kafka consumer #2)
    for topic, headers, key, value in kafka.avro_string_consumer(
        kafka.consumer,
        topics=[
            TOPIC_CUSTOMER_ACTIONS,
        ],
    ):
        session_id = key
        mid = value["mid"]
        username = value["username"]

        # Vector DB cache per session
        if session_id not in chatVectorDB.keys():
            chatVectorDB[session_id] = list()

        # Chat cache per session
        if session_id not in chatMessages.keys():
            chatMessages[session_id] = list()

        if mid is None:  # Logout message
            chatSessions.pop(session_id, None)
            chatMessages.pop(session_id, None)
            chatVectorDB.pop(session_id, None)
            logging.info(f"{username} has logged out!")

        else:
            total_tokens = -1
            try:

                if mid == 0:  # Initial message (after login)

                    # LLM Session
                    chatVectorDB[
                        session_id
                    ] = list()  # reset cache for that session (in case of page refresh)

                    if llm_engine == "bedrock":
                        chatSessions[session_id] = ChatBedrock(
                            model_id=env_vars.get("BASE_MODEL"),
                            client=aws_client,
                            model_kwargs={
                                "temperature": float(env_vars.get("MODEL_TEMPERATURE")),
                            },
                        )

                    elif llm_engine == "openai":
                        chatSessions[session_id] = ChatOpenAI(
                            api_key=env_vars.get("OPENAI_API_KEY"),
                            model=env_vars.get("BASE_MODEL"),
                            temperature=float(env_vars.get("MODEL_TEMPERATURE")),
                        )

                    else:
                        chatSessions[session_id] = ChatGroq(
                            groq_api_key=env_vars.get("GROQ_API_KEY"),
                            model_name=env_vars.get("BASE_MODEL"),
                            temperature=float(env_vars.get("MODEL_TEMPERATURE")),
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
                        context += f"\nWe have a new customer. Their name is {customer_name}, {dob_string} and is allergic to {customer_allergies}"

                    customer_greeting = "Hi!"
                    chatMessages[session_id] = [
                        SystemMessage(context),
                        HumanMessage(customer_greeting),
                    ]

                    logging.info(f"{username} has logged in!")
                    logging.info(f"Message ID: {mid}")
                    logging.info(f"Context: {context}\n{customer_greeting}")

                else:  # new customer message
                    context = value["context"] or ""
                    query = value["query"] or ""

                    # Query Vector DB based on the customer message content
                    if context:
                        vdb_context = [context]
                    else:
                        vdb_context = list()

                    if query:
                        # Generate vector Data
                        response = requests.post(
                            embedding_url,
                            headers={
                                "Content-Type": "text/plain; charset=UTF-8",
                            },
                            data=query,
                        )
                        vector_data = response.json().get("vector_data", list())

                        # Query Vector DB
                        result_search = VDB_CLIENT.search(
                            collection_name=VDB_COLLECTION,
                            query_vector=vector_data,
                            limit=VECTOR_DB_SEARCH_LIMIT,
                        )
                        for search in result_search:
                            if search.score >= VECTOR_DB_MIN_SCORE:
                                if (
                                    search.payload["title"]
                                    not in chatVectorDB[session_id]
                                ):
                                    chatVectorDB[session_id].append(
                                        search.payload["title"]
                                    )
                                    vdb_context.append(
                                        f"{search.payload['title']}: {search.payload['description']}"
                                    )

                        logging.info(f"Customer query (mid: {mid}): {query}")

                    # In case of any relevant vector DB document is found, add it to the System context
                    if len(vdb_context) > 0:
                        context = "Additional restaurant policies:"
                        for item in vdb_context:
                            context += f"\n- {item}"
                        logging.info(context)
                        chatMessages[session_id].append(AIMessage(context))

                    if query:
                        chatMessages[session_id].append(HumanMessage(query))

                # Submit promt to LLM model and count tokens
                with get_openai_callback() as cb:
                    response = chatSessions[session_id].invoke(chatMessages[session_id])
                    total_tokens = cb.total_tokens

                # Update chat history
                chatMessages[session_id].append(AIMessage(response.content))

                # Adjust HTML response if required
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
                        "total_tokens": total_tokens,
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
