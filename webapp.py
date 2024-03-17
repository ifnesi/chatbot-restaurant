import os
import glob
import json
import uuid
import logging
import datetime

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
    return render_template(
        "page_not_found.html",
        title="Page Not Found",
    ), 404


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
    fake = Faker()
    request_form = dict(request.form)
    session["waiterName"] = fake.name()
    session["customerID"] = uuid.uuid4().hex
    session["customerName"] = request_form.get("customerName", "Anonymous").strip()[:32].strip()
    session["ofLegalAge"] = request_form.get("ofLegalAge") == "yes"
    session["restaurantName"] = RAG_DATA["restaurant"].get("name")
    request_form.pop("customerName", None)
    request_form.pop("ofLegalAge", None)
    session["allergies"] = list()
    for key in request_form.keys():
        session["allergies"].append(key)
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
        "customer": "",
        "waiter": "",
        "customerName": session["customerName"],
        "waiterName": session["waiterName"],
    }
    try:
        request_form = request.get_json()
        initialMessage = request_form.get("initialMessage")
        customerMessage = request_form.get("customerMessage")
        if initialMessage:
            result["waiter"] = f"""Hi {session["customerName"]}, my name is {session["waiterName"]} and I will be your waiter today. How can I help you?"""
        elif customerMessage:
            result["customer"] = customerMessage
            result["waiter"] = "Thank you for your message!"
    except Exception as err:
        logging.error(f"{err}")
        result["waiter"] = "Sorry, something went wrong! Please try again"
    return jsonify(result)


@app.route("/logout", methods=["GET"])
@login_required
def logout():
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
