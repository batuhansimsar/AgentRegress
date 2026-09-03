"""B001 fixture: a functional defect with a passing dynamic-security baseline."""

from flask import Flask, jsonify

app = Flask(__name__)


@app.get("/greet/<name>")
def greet(name):
    user = {"name": name}
    return jsonify({"message": f"Hello, {user['display_name']}!"})
