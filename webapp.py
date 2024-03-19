import os
import glob
import json
import uuid
import logging
import datetime

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.schema import SystemMessage, HumanMessage

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

from utils import initial_prompt

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

# Load env variables
load_dotenv('./.env_api_keys')

# Global variables
chatSessions = dict()
chatMessages = dict()
RAG_DATA = dict()
for file in glob.glob(os.path.join("rag", "*.json")):
    with open(file, "r") as f:
        key = os.path.splitext(os.path.split(file)[-1])[0]
        RAG_DATA[key] = json.loads(f.read())


###########
# Classes #
###########
class User(UserMixin):
    def __init__(self, id: str) -> None:
        super().__init__()
        self.id = id


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
            restaurantName=RAG_DATA["restaurant"].get("name"),
            title="Login",
        )


@app.route("/login", methods=["POST"])
def do_login():
    # Session variables
    fake = Faker()
    request_form = dict(request.form)
    session["waiterName"] = fake.name()
    session["customerID"] = uuid.uuid4().hex
    session["customerName"] = (
        request_form.get("customerName", "Anonymous").strip()[:32].strip()
    )
    session["ofLegalAge"] = request_form.get("ofLegalAge") == "yes"
    session["restaurantName"] = RAG_DATA["restaurant"].get("name")
    request_form.pop("customerName", None)
    request_form.pop("ofLegalAge", None)
    session["allergens"] = list()
    for key in request_form.keys():
        session["allergens"].append(key)
    if len(session["allergens"]) == 0:
        session["allergens"].append("Nothing")

    # LLM Session
    chatSessions[session["customerID"]] = ChatOpenAI(
        model="gpt-3.5-turbo-16k",
    )

    # Login user
    login_user(
        User(session["customerID"]),
        duration=datetime.timedelta(hours=1),
        force=True,
    )
    return redirect(url_for("chatbot"))


@app.route("/send-message", methods=["POST"])
@login_required
def send_message():
    result = {
        "waiter": "",
    }
    try:
        request_form = request.get_json()
        initialMessage = request_form.get("initialMessage")
        customerMessage = request_form.get("customerMessage")
        if initialMessage:
            chatMessages[session["customerID"]] = [
                SystemMessage(content=initial_prompt(RAG_DATA, session["waiterName"])),
                HumanMessage(content=f"""Please greet this new customer and show the main menu. Customer name is {session["customerName"]}, customer is {"on or above 21 years old" if session["ofLegalAge"] else "under 21 years old"} and is allergic to: {", ".join(session["allergens"])}"""),
            ]
        elif customerMessage:
            chatMessages[session["customerID"]].append(HumanMessage(customerMessage))
        response = chatSessions[session["customerID"]].invoke(chatMessages[session["customerID"]])
        result["waiter"] = response.content
        chatMessages[session["customerID"]].append(response)
    except Exception as err:
        logging.error(f"{err}")
        result["waiter"] = "Sorry, something went wrong! Please try again"
    return jsonify(result)


@app.route("/logout", methods=["GET"])
@login_required
def logout():
    chatSessions.pop(session["customerID"], None)
    chatMessages.pop(session["customerID"], None)
    logout_user()
    session.clear()
    return redirect(url_for("login"))


@app.route("/", methods=["GET"])
@login_required
def chatbot():
    return render_template(
        "chatbot.html",
        restaurantName=RAG_DATA["restaurant"].get("name"),
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

    # Start http server
    app.run(
        host="127.0.0.1",
        port=8888,
        debug=True,
    )
