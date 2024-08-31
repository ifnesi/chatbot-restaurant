import os
import sys
import json
import time
import uuid
import logging
import datetime

from threading import Thread
from dotenv import load_dotenv, find_dotenv

from faker import Faker
from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from flask_login import (
    UserMixin,
    LoginManager,
    current_user,
    login_required,
    login_user,
    logout_user,
)

from utils import (
    TOPIC_LOGGING,
    TOPIC_CHATBOT_RESPONSES,
    TOPIC_CUSTOMER_ACTIONS,
    TOPIC_DB,
    KafkaClient,
    SerializationContext,
    MessageField,
    CustomerProfilesAndLogs,
    assess_password,
    sys_exc,
)


##################
# Webapp (Flask) #
##################
app = Flask(
    __name__,
    static_folder="static",
    template_folder="templates",
)
app.config["SECRET_KEY"] = "401338da-c002-48e3-a673-7db0096306ff"
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
log = logging.getLogger("werkzeug")
log.setLevel(logging.WARNING)


###########
# Classes #
###########
class User(UserMixin):
    def __init__(self, id: str) -> None:
        super().__init__()
        self.id = id


class ChatbotResponses:
    """Process chatbot responses"""

    def __init__(self, topics) -> None:
        self.data = dict()
        self.topics = topics

    def consumer(self, kafka) -> None:
        while True:
            for _, _, key, value in kafka.avro_string_consumer(
                kafka.consumer_latest,
                self.topics,
            ):
                if value:
                    response_log = (value["response"] or "").strip()
                    while ">\n<" in response_log:
                        response_log = response_log.replace(">\n<", "><")
                    while "\n\n" in response_log:
                        response_log = response_log.replace("\n\n", "\n")
                    while "\n" in response_log:
                        response_log = response_log.replace("\n", "<br>")
                    value_log = {
                        **value,
                        "response": response_log,
                    }
                    logging.info(f"Message received for session_id {key}: {value_log}")
                    response_key = f"{key}:{value['mid']}"
                    value_log.pop("mid")
                    self.data[response_key] = value_log


####################
# Global Variables #
####################
RESTAURANT_NAME = "StreamBite"

kafka = None
customer_action_serialiser = None
customer_profiles_and_logs = CustomerProfilesAndLogs(
    topics=[
        TOPIC_LOGGING,
        TOPIC_DB,
    ]
)
chatbot_responses = ChatbotResponses(topics=[TOPIC_CHATBOT_RESPONSES])


#################
# Flask routing #
#################
@app.errorhandler(404)
def page_not_found(e):
    return (
        render_template(
            "page_not_found.html",
            title="Page Not Found",
        ),
        404,
    )


@login_manager.unauthorized_handler
def unauthorized():
    return redirect(url_for("login"))


@login_manager.user_loader
def load_user(customer_id):
    return User(id=customer_id)


@app.route("/login", methods=["GET"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("chatbot"))
    else:
        return render_template(
            "login.html",
            restaurant_name=RESTAURANT_NAME,
            title="Login",
        )


@app.route("/login", methods=["POST"])
def do_login():
    request_form = dict(request.form)
    username = request_form["username"]
    password = request_form["password"]

    if username in customer_profiles_and_logs.data.keys():
        password_salt = os.environ.get("MD5_PASSWORD_SALT")
        hashed_pwd = customer_profiles_and_logs.data[username]["hashed_pwd"]
        if assess_password(
            password_salt,
            hashed_pwd,
            password,
        ):
            # Login user
            fake = Faker()
            session["waiter_name"] = fake.name()
            session["session_id"] = uuid.uuid4().hex
            session["restaurant_name"] = RESTAURANT_NAME
            session["customer_name"] = customer_profiles_and_logs.data[username][
                "full_name"
            ]
            session["username"] = username
            login_user(
                User(session["session_id"]),
                duration=datetime.timedelta(hours=1),
                force=True,
            )
            return redirect(url_for("chatbot"))

        else:
            return (
                render_template(
                    "login.html",
                    restaurant_name=RESTAURANT_NAME,
                    title="Login",
                    username=username,
                    error_message="Invalid password! As this is a demo, the password is the username &#128521;",
                ),
                401,
            )

    else:
        return (
            render_template(
                "login.html",
                restaurant_name=RESTAURANT_NAME,
                title="Login",
                username=username,
                error_message="Invalid Username",
            ),
            401,
        )


@app.route("/profiles", methods=["GET"])
def profiles():
    return render_template(
        "profiles.html",
        restaurant_name=RESTAURANT_NAME,
        title="Profiles",
        profiles=customer_profiles_and_logs.data,
    )


@app.route("/logs", methods=["GET"])
def logs():
    return render_template(
        "logs.html",
        restaurant_name=RESTAURANT_NAME,
        title="Logs",
    )


@app.route("/data", methods=["GET"])
def data():
    def _process_data(data, indent=0):
        html = ""
        if isinstance(data, dict):
            for key, value in data.items():
                if indent == 0:
                    html += f"<h4 class='text-warning mt-3'>{key}</h4>"
                else:
                    if isinstance(value, dict):
                        html += (
                            f"<h5 class='text-info mt-1'>{('&emsp;'*indent) + key}</h5>"
                        )
                    else:
                        html += f"{'&emsp;'*indent}{key}:"
                html += _process_data(value, indent=indent + 1)
        else:
            html += f"&nbsp;<span class='text-muted'>{data}</span><br>"
        return html

    return render_template(
        "data.html",
        restaurant_name=RESTAURANT_NAME,
        title="Data",
        data=_process_data(customer_profiles_and_logs.rag_data),
    )


@app.route("/get-logs", methods=["GET"])
def get_logs():
    logs_data = list()
    while not customer_profiles_and_logs.queue.empty():
        logs_data.append(customer_profiles_and_logs.queue.get())
    return "".join(logs_data)


@app.route("/send-message", methods=["POST"])
@login_required
def send_message():
    try:

        request_form = request.get_json()
        span_id = request_form.get("span_id")
        initial_message = request_form.get("initial_message")
        context = request_form.get("context")
        query = request_form.get("query")

        result = {
            "waiter": "",
            "span_id": span_id,
            "total_tokens": "N/A",
        }

        message = dict()
        if initial_message:
            mid = 0
        else:
            mid = int(time.time() * 1000)
            message["context"] = context
            message["query"] = query

        message.update(
            {
                "username": session["username"],
                "waiter_name": session["waiter_name"],
                "mid": mid,
            }
        )

        # Produce message to kafka
        kafka.producer.poll(0.0)
        kafka.producer.produce(
            topic=TOPIC_CUSTOMER_ACTIONS,
            key=kafka.string_serializer(session["session_id"]),
            value=customer_action_serialiser(
                message,
                SerializationContext(
                    TOPIC_CUSTOMER_ACTIONS,
                    MessageField.VALUE,
                ),
            ),
            on_delivery=kafka.delivery_report,
        )
        logging.info("Flushing records")
        kafka.producer.flush()

        # Wait for response from LLM model (sync for now)
        # The message key on both the submit prompt topic and get LLM model response topic is the same (<session_id>:<mid>)
        timeout = False
        session_start = time.time()
        response_key = f"{session['session_id']}:{mid}"
        timeout_seconds = int(os.environ.get("TIMEOUT_SECONDS"))
        while response_key not in chatbot_responses.data.keys():
            time.sleep(0.1)
            if time.time() - session_start >= timeout_seconds:
                result[
                    "waiter"
                ] = "<span class='error_message'>Oops! I got lost in thought. Nudge me again?</span>"
                timeout = True
                break

        if not timeout:
            result["waiter"] = chatbot_responses.data[response_key]["response"]
            result["total_tokens"] = chatbot_responses.data[response_key][
                "total_tokens"
            ]
            chatbot_responses.data.pop(response_key, None)

    except Exception:
        logging.error(sys_exc(sys.exc_info()))
        result[
            "waiter"
        ] = "<span class='error_message'>Yikes! My pixels got tangled. Can you try that once more?</span>"

    finally:
        return jsonify(result)


@app.route("/logout", methods=["GET"])
@login_required
def logout():
    try:
        # Produce logout message to kafka (message and mid are None)
        message = {
            "username": session["username"],
            "waiter_name": session["waiter_name"],
        }
        kafka.producer.poll(0.0)
        kafka.producer.produce(
            topic=TOPIC_CUSTOMER_ACTIONS,
            key=kafka.string_serializer(session["session_id"]),
            value=customer_action_serialiser(
                message,
                SerializationContext(
                    TOPIC_CUSTOMER_ACTIONS,
                    MessageField.VALUE,
                ),
            ),
            on_delivery=kafka.delivery_report,
        )
        logging.info("Flushing records")
        kafka.producer.flush()

    except Exception:
        logging.error(sys_exc(sys.exc_info()))

    finally:
        # cleanup any left over session_id message on the chatbot_responses cache
        session_id_left_overs = [
            id
            for id in chatbot_responses.data.keys()
            if id.startswith(session["session_id"])
        ]
        for id in session_id_left_overs:
            chatbot_responses.data.pop(id, None)

        logout_user()
        session.clear()
        return redirect(url_for("login"))


@app.route("/", methods=["GET"])
@login_required
def chatbot():
    llm_engine = os.environ.get("LLM_ENGINE").lower()
    if llm_engine == "bedrock":
        llm_engine = "AWS BedRock"
    elif llm_engine == "openai":
        llm_engine = "OpenAI"
    else:
        llm_engine = "Groq"
    return render_template(
        "chatbot.html",
        restaurant_name=RESTAURANT_NAME,
        title="Talk to us!",
        llm_engine=llm_engine,
    )


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

    kafka = KafkaClient(
        os.environ.get("KAFKA_CONFIG"),
        os.environ.get("CLIENT_ID_WEBAPP"),
        FILE_APP,
        set_consumer_latest=True,
        set_consumer_earliest=True,
    )

    with open(os.path.join("schemas", "customer_message.avro"), "r") as f:
        schema_str = f.read()
    customer_action_serialiser = kafka.avro_serialiser(schema_str)

    # Start Customer Profiles and Logs Consumer thread
    Thread(
        target=customer_profiles_and_logs.consumer,
        args=(kafka,),
    ).start()

    # Start chatbot responses Consumer thread
    Thread(
        target=chatbot_responses.consumer,
        args=(kafka,),
    ).start()

    # Start web server
    app.run(
        host=os.environ.get("WEBAPP_HOST"),
        port=int(os.environ.get("WEBAPP_PORT")),
        debug=True,
        use_reloader=False,
    )
