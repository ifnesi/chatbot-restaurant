# Sentence Transformer REST API
import os
import sys
import uvicorn
import logging

from dotenv import load_dotenv, find_dotenv
from fastapi import Request, FastAPI
from fastapi.responses import JSONResponse
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


# Routing
@app.get("/")
async def root():
    return "OK"


@app.post("/api/v1/embedding/sentence-transformer")
async def embedding(request: Request):
    try:
        sentence = ((await request.body()) or b"").decode("utf-8")
        vector_data = VDB_MODEL.encode([sentence])[0].tolist()
        if sentence:
            logging.info(f"Vector data for '{sentence}': {vector_data}")
        return JSONResponse(
            status_code=200,
            content={
                "error": False,
                "vector_data": vector_data,
            },
        )
    except Exception as e:
        logging.error(sys_exc(sys.exc_info()))
        return JSONResponse(
            status_code=500,
            content={
                "error": True,
                "message": str(e),
            },
        )


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
