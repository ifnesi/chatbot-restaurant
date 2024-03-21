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
    KafkaClient,
    SerializationContext,
    MessageField,
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

class CustomerProfiles:
    def __init__(self, topics) -> None:
        self.data = dict()
        self.topics = topics

    def consumer(self, kafka) -> None:
        while True:
            for _, _, key, value in kafka.avro_consumer(kafka.consumer_earliest, self.topics):
                self.data[key] = value
                logging.info(f"Loaded profile for {key}: {json.dumps(value)}")

class ChatbotResponses:
    def __init__(self, topics) -> None:
        self.data = dict()
        self.topics = topics

    def consumer(self, kafka) -> None:
        while True:
            for _, _, key, value in kafka.avro_consumer(kafka.consumer_latest, self.topics):
                logging.info(f"Message received for session_id {key}: {json.dumps(value)}")
                counter = value["counter"]
                value.pop("counter")
                self.data[f"{key}-{counter}"] = value


####################
# Global Variables #
####################
kafka = None
customer_action_serialiser = None

TOPIC_CUSTOMER_PROFILES = "chatbot-restaurant-customer_profiles"
customer_profiles = CustomerProfiles(topics=[TOPIC_CUSTOMER_PROFILES])

TOPIC_CHATBOT_RESPONSES = "chatbot-restaurant-chatbot_responses"
chatbot_responses = ChatbotResponses(topics=[TOPIC_CHATBOT_RESPONSES])

TOPIC_CUSTOMER_ACTIONS = "chatbot-restaurant-customer_actions"

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
            session["counter"] = 0
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
                    error_message="Invalid password (as this is a demo, the password is the username &#128521;)",
                ),
                401,
            )

    else:
        return (
            render_template(
                "login.html",
                restaurant_name=RESTAURANT_NAME,
                title="Login",
                error_message="Invalid Username",
            ),
            401,
        )


@app.route("/send-message", methods=["POST"])
@login_required
def send_message():
    result = {
        "waiter": "",
    }
    try:
        request_form = request.get_json()
        initial_message = request_form.get("initial_message")
        customer_message = request_form.get("customer_message")
        if initial_message:
            message = {
                "username": session["username"],
                "counter": session["counter"],
            }
        elif customer_message:
            message = {
                "username": session["username"],
                "counter": session["counter"],
                "message": customer_message,
            }

        session["counter"] += 1

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
        logging.info("Flushing records...")
        kafka.producer.flush()

        # Wait for response (sync for now)
        response_key = f"{session['session_id']}-{session['counter']-1}"
        start_timer = time.time()
        timed_out = False
        while response_key not in chatbot_responses.data.keys():
            time.sleep(0.1)
            if time.time() - start_timer > 25:
                result["waiter"] = "<span class='error_message'>Sorry, your message timed out! Please try again</span>"
                timed_out = True
                break

        if not timed_out:
            result["waiter"] = chatbot_responses.data[response_key]["message"]
            chatbot_responses.data.pop(response_key)

    except Exception:
        logging.error(sys_exc(sys.exc_info()))
        result["waiter"] = "<span class='error_message'>Sorry, something went wrong! Please try again</span>"

    return jsonify(result)


@app.route("/logout", methods=["GET"])
@login_required
def logout():
    try:
        # Produce logout message to kafka
        message = {
            "username": session["username"],
            "counter": -1,
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
        logging.info("Flushing records...")
        kafka.producer.flush()

    except Exception:
        logging.error(sys_exc(sys.exc_info()))

    finally:
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
    logging.basicConfig(
        format="%(asctime)s.%(msecs)03d [%(levelname)s]: %(message)s",
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
        help="Hostname to listen on (default: 127.0.0.1)",
        default="127.0.0.1",
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

    # Create customer actions topic
    try:
        kafka.create_topic(
            TOPIC_CUSTOMER_ACTIONS,
            cleanup_policy="delete",
        )
    except Exception:
        logging.error(sys_exc(sys.exc_info()))
        sys.exit(-1)

    # Create chatbot responses topic
    try:
        kafka.create_topic(
            TOPIC_CHATBOT_RESPONSES,
            cleanup_policy="delete",
        )
    except Exception:
        logging.error(sys_exc(sys.exc_info()))
        sys.exit(-1)

    # Start Customer Profiles Consumer thread
    Thread(
        target=customer_profiles.consumer,
        args=(kafka,),
        daemon=False,
    ).start()

    # Start chatbot responses Consumer thread
    Thread(
        target=chatbot_responses.consumer,
        args=(kafka,),
        daemon=False,
    ).start()

    # Start web server
    app.run(
        host=args.host,
        port=args.port,
        debug=True,
        use_reloader=False,
    )

