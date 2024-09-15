# Setence Transformer REST API
import os
import sys
import uvicorn
import logging

from dotenv import load_dotenv, find_dotenv
from fastapi import Request, FastAPI
from sentence_transformers import SentenceTransformer

from utils import (
    SENTENCE_TRANSFORMER,
    KafkaClient,
    sys_exc,
    set_flag,
    unset_flag,
)


# Start Fast-API
app = FastAPI()


@app.get("/api/v1/embedding/setence-transformer")
async def embedding(request: Request):
    try:
        sentence = (await request.body()).decode("utf-8")
        embeddings = VDB_MODEL.encode([sentence])[0].tolist()
        logging.info(f"Vector data for '{sentence}': {embeddings}")
        return {
            "embeddings": embeddings,
        }
    except Exception:
        logging.error(sys_exc(sys.exc_info()))


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

    # Set kafka log handler
    kafka = KafkaClient(
        env_vars.get("KAFKA_CONFIG"),
        f"{env_vars.get('CLIENT_ID_EMBEDDING')}",
        file_app=FILE_APP,
    )

    logging.info(f"Loading sentence transformer, model: {SENTENCE_TRANSFORMER}")
    VDB_MODEL = SentenceTransformer(SENTENCE_TRANSFORMER)

    # Set flag here to allow time to load sentence transformer
    set_flag(FLAG_FILE)

    logging.info(f"Starting REST API (Sentence Transformer)")
    uvicorn.run(
        app,
        host=env_vars.get("EMBEDDING_HOST"),
        port=int(env_vars.get("EMBEDDING_PORT")),
        reload=False,
    )
