import os
import sys
import json
import hashlib
import logging

from dotenv import load_dotenv, find_dotenv
from threading import Thread
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from langchain.callbacks import get_openai_callback
from langchain.schema import SystemMessage, HumanMessage

from qdrant_client import QdrantClient
from qdrant_client.http import models
from sentence_transformers import SentenceTransformer

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
    """Load in memory RAG / Customer Profiles"""

    def __init__(
        self,
        topics,
        vdb_client,
        vdb_model,
        vdb_collection,
    ) -> None:
        self.rag = dict()
        self.customer_profile = dict()
        self.topics = topics
        self.vdb_client = vdb_client
        self.vdb_model = vdb_model
        self.vdb_collection = vdb_collection

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

                    # Load sentences into the Vector DB
                    elif rag_name in ["vector_db"]:
                        sentence = f"{key}: {value['description']}"
                        embeddings = self.vdb_model.encode([sentence])

                        # Upsert collection
                        id = int(hashlib.md5(key.encode("utf-8")).hexdigest(), 16)
                        logging.info(f"Upserting Vector DB collection {self.vdb_collection}: {id} | {sentence}")
                        self.vdb_client.upsert(
                            collection_name=self.vdb_collection,
                            points=[
                                models.PointStruct(
                                    id=id,
                                    vector=embeddings[0],
                                    payload={
                                        "title": key,
                                        "description": value['description'],
                                    },
                                ),
                            ],
                        )

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

    # Load env variables
    load_dotenv(find_dotenv())

    VECTOR_DB_MIN_SCORE = float(os.environ.get("VECTOR_DB_MIN_SCORE", 0.6))
    VECTOR_DB_SEARCH_LIMIT = int(os.environ.get("VECTOR_DB_SEARCH_LIMIT", 2))

    # Vector DB Collection
    VDB_COLLECTION = "chatbot_restaurant"

    # Load Sentence Transformer
    SENTENCE_TRANSFORMER = "all-MiniLM-L6-v2"
    logging.info(f"Loading sentence transformer, model: {SENTENCE_TRANSFORMER}")
    VDB_MODEL = SentenceTransformer(SENTENCE_TRANSFORMER)

    # Qdrant (Vector-DB), load it in memory
    logging.info("Loading VectorDB in memory (Qdrant)")
    VDB_CLIENT = QdrantClient(":memory:")

    # Create collection
    logging.info(f"Creating VectorDB collection: {VDB_COLLECTION}")
    VDB_CLIENT.create_collection(
        collection_name=VDB_COLLECTION,
        vectors_config=models.VectorParams(
            size=384,
            distance=models.Distance.COSINE,
        ),
    )

    # Class instance to load RAG data
    rag = LoadRAG(
        topics=[
            TOPIC_CUSTOMER_PROFILES,
            TOPIC_RAG,
        ],
        vdb_client=VDB_CLIENT,
        vdb_model=VDB_MODEL,
        vdb_collection=VDB_COLLECTION,
    )

    kafka = KafkaClient(
        os.environ.get("KAFKA_CONFIG"),
        os.environ.get("CLIENT_ID_CHATBOT"),
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
                        if os.environ.get("LLM_ENGINE").lower() == "openai":
                            chatSessions[session_id] = ChatOpenAI(
                                api_key=os.environ.get("OPENAI_API_KEY"),
                                model=os.environ.get("BASE_MODEL"),
                                temperature=float(os.environ.get("MODEL_TEMPERATURE")),
                            )

                        else:
                            chatSessions[session_id] = ChatGroq(
                                groq_api_key=os.environ.get("GROQ_API_KEY"),
                                model_name=os.environ.get("BASE_MODEL"),
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
                        query = value["message"] or ""

                        # Query Vector DB based on the customer message content
                        vdb_context = list()
                        if query:
                            embeddings = VDB_MODEL.encode([query])
                            result_search = VDB_CLIENT.search(
                                collection_name=VDB_COLLECTION,
                                query_vector=embeddings[0],
                                limit=VECTOR_DB_SEARCH_LIMIT,
                            )
                            for search in result_search:
                                if search.score >= VECTOR_DB_MIN_SCORE:
                                    if search.payload["title"] not in chatVectorDB[session_id]:
                                        chatVectorDB[session_id].append(search.payload["title"])
                                        vdb_context.append(f"{search.payload['title']}: {search.payload['description']}")

                        if len(vdb_context) > 0:
                            context = "Additional context:"
                            for item in vdb_context:
                                context += f"\n- {item}"
                            logging.info(context)
                            chatMessages[session_id].append(SystemMessage(context))

                        logging.info(f"Customer query: {query}")
                        chatMessages[session_id].append(HumanMessage(query))

                    # Submit promt to LLM model and count tokens
                    with get_openai_callback() as cb:
                        response = chatSessions[session_id].invoke(
                            chatMessages[session_id]
                        )
                        total_tokens = cb.total_tokens

                    # Update chat history
                    chatMessages[session_id].append(response)

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