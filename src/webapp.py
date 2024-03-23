import os
import sys
import json
import time
import uuid
import logging
import argparse
import datetime

from threading import Thread
from dotenv import load_dotenv

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
    TOPIC_CHATBOT_RESPONSES,
    TOPIC_CUSTOMER_PROFILES,
    TOPIC_CUSTOMER_ACTIONS,
    KafkaClient,
    SerializationContext,
    MessageField,
    CustomerProfiles,
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
log.setLevel(logging.INFO)


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
            for topic, headers, key, value in kafka.avro_string_consumer(
                kafka.consumer_latest,
                self.topics,
            ):
                logging.info(f"Message received for session_id {key}: {value}")
                response_key = f"{key}:{value['mid']}"
                self.data[response_key] = value["response"]


####################
# Global Variables #
####################
kafka = None
customer_action_serialiser = None
customer_profiles = CustomerProfiles(topics=[TOPIC_CUSTOMER_PROFILES])
chatbot_responses = ChatbotResponses(topics=[TOPIC_CHATBOT_RESPONSES])

# Restaurant name
with open(os.path.join("rag", "restaurant.json"), "r") as f:
    restaurant_data = json.loads(f.read())
RESTAURANT_NAME = restaurant_data["name"]


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


@app.route("/profiles", methods=["GET"])
def profiles():
    return render_template(
        "profiles.html",
        restaurant_name=RESTAURANT_NAME,
        title="Profiles",
        profiles=customer_profiles.data,
    )


@app.route("/login", methods=["POST"])
def do_login():
    request_form = dict(request.form)
    username = request_form["username"]
    password = request_form["password"]

    if username in customer_profiles.data.keys():
        password_salt = os.environ.get("PASSWORD_SALT")
        hashed_password = customer_profiles.data[username]["hashed_password"]
        if assess_password(
            password_salt,
            hashed_password,
            password,
        ):
            # Login user
            fake = Faker()
            session["waiter_name"] = fake.name()
            session["session_id"] = uuid.uuid4().hex
            session["restaurant_name"] = RESTAURANT_NAME
            session["customer_name"] = customer_profiles.data[username]["full_name"]
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


@app.route("/send-message", methods=["POST"])
@login_required
def send_message():
    try:

        request_form = request.get_json()
        span_id = request_form.get("span_id")
        initial_message = request_form.get("initial_message")
        customer_message = request_form.get("customer_message")

        result = {
            "waiter": "",
            "span_id": span_id,
        }

        message = dict()
        if initial_message:
            mid = 0
        else:
            mid = int(time.time() * 1000)
            message["message"] = customer_message

        message.update({
            "username": session["username"],
            "waiter_name": session["waiter_name"],
            "mid": mid,
        })

        # Produce message to kafka
        kafka.producer.poll(0.0)
        kafka.producer.produce(
            topic=TOPIC_CUSTOMER_ACTIONS,
            key=kafka.string_serializer(session['session_id']),
            value=customer_action_serialiser(
                message,
                SerializationContext(
                    TOPIC_CUSTOMER_ACTIONS,
                    MessageField.VALUE,
                ),
            ),
            on_delivery=kafka.delivery_report,
        )
        logging.info("Flushing records...")
        kafka.producer.flush()

        # Wait for response from LLM model (sync for now)
        # The message key on both the submit prompt topic and get LLM model response topic is the same (<session_id>:<counter>)
        response_key = f"{session['session_id']}:{mid}"
        while response_key not in chatbot_responses.data.keys():
            time.sleep(3)

        result["waiter"] = chatbot_responses.data[response_key]
        chatbot_responses.data.pop(response_key)

    except Exception:
        logging.error(sys_exc(sys.exc_info()))
        result[
            "waiter"
        ] = "<span class='error_message'>Sorry, something went wrong on the front-end! Please try again</span>"

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
            key=kafka.string_serializer(session['session_id']),
            value=customer_action_serialiser(
                message,
                SerializationContext(
                    TOPIC_CUSTOMER_ACTIONS,
                    MessageField.VALUE,
                ),
            ),
            on_delivery=kafka.delivery_report,
        )
        logging.info("Flushing records...")
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
    return render_template(
        "chatbot.html",
        restaurant_name=RESTAURANT_NAME,
        title="Talk to us!",
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

    parser = argparse.ArgumentParser(description="Chatbot - Web Application")
    parser.add_argument(
        "--config",
        dest="config",
        type=str,
        help="Enter config filename (default: config/localhost.ini)",
        default=os.path.join("config", "localhost.ini"),
    )
    parser.add_argument(
        "--host",
        dest="host",
        type=str,
        help="Hostname to listen on (default: 0.0.0.0)",
        default="0.0.0.0",
    )
    parser.add_argument(
        "--port",
        dest="port",
        type=int,
        help="Port of the webserver (default: 8888)",
        default=8888,
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
        help="Producer/Consumer's Group/Client ID prefix (default: chatbot-webapp)",
        default="chatbot-webapp",
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

    with open(os.path.join("schemas", "customer_message.avro"), "r") as f:
        schema_str = f.read()
    customer_action_serialiser = kafka.avro_serialiser(schema_str)

    # Start Customer Profiles Consumer thread
    Thread(
        target=customer_profiles.consumer,
        args=(kafka,),
    ).start()

    # Start chatbot responses Consumer thread
    Thread(
        target=chatbot_responses.consumer,
        args=(kafka,),
    ).start()

    # Start web server
    app.run(
        host=args.host,
        port=args.port,
        debug=True,
        use_reloader=False,
    )
