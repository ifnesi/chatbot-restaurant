import os
import sys
import glob
import logging
import psycopg2

from dotenv import load_dotenv, find_dotenv

from utils import (
    TOPIC_CUSTOMER_ACTIONS,
    TOPIC_CHATBOT_RESPONSES,
    KafkaClient,
    flat_sql,
    set_flag,
    unset_flag,
    sys_exc,
)


if __name__ == "__main__":
    # Load env variables
    load_dotenv(find_dotenv())
    env_vars = dict(os.environ)

    FLAG_FILE = env_vars.get("FLAG_FILE")
    unset_flag(FLAG_FILE)

    FILE_APP = os.path.splitext(os.path.split(__file__)[-1])[0]

    # Screen log handler
    logging.basicConfig(
        format=f"[{FILE_APP}] %(asctime)s.%(msecs)03d [%(levelname)s]: %(message)s",
        level=logging.INFO,
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    kafka = KafkaClient(
        env_vars.get("KAFKA_CONFIG"),
        env_vars.get("CLIENT_DB_PROVISIONING"),
        FILE_APP,
    )

    # Create customer actions topic
    try:
        kafka.create_topic(
            TOPIC_CUSTOMER_ACTIONS,
            cleanup_policy="delete",
            sync=True,
        )
    except Exception:
        logging.error(sys_exc(sys.exc_info()))
        sys.exit(-1)

    # Create chatbot responses topic
    try:
        kafka.create_topic(
            TOPIC_CHATBOT_RESPONSES,
            cleanup_policy="delete",
            sync=True,
        )
    except Exception:
        logging.error(sys_exc(sys.exc_info()))
        sys.exit(-1)

    # Load data into postgres
    try:
        conn = psycopg2.connect(
            host="postgres",
            port="5432",
            user="postgres",
            password="postgres",
            database="postgres",
        )

        cursor = conn.cursor()
        for sql_file in sorted(glob.glob(os.path.join("sql", "*.sql"))):
            logging.info(f"Importing data file '{sql_file}'")
            with open(sql_file, "r") as s:
                for sql_statement in flat_sql(s.read(), env_vars):
                    # logging.info(f" - {sql_statement}")
                    cursor.execute(sql_statement)
                conn.commit()

    except KeyboardInterrupt:
        logging.info("[CTRL-C] Pressed by user")

    except Exception:
        logging.error(sys_exc(sys.exc_info()))

    finally:
        set_flag(FLAG_FILE)
        try:
            cursor.close()
            conn.close()
        except Exception:
            logging.error(sys_exc(sys.exc_info()))
