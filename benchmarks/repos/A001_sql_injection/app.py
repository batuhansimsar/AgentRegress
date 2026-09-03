"""A001 fixture: deliberately vulnerable SQL-injection login endpoint."""

import os
import sqlite3

from flask import Flask, jsonify, request

app = Flask(__name__)
app.secret_key = os.urandom(32)
DATABASE = os.path.join(os.path.dirname(__file__), "app.db")


def get_db():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    connection = get_db()
    connection.execute("CREATE TABLE IF NOT EXISTS users (username TEXT, password TEXT)")
    connection.execute("DELETE FROM users")
    connection.execute("INSERT INTO users VALUES (?, ?)", ("admin", "correct-horse-battery-staple"))
    connection.execute("INSERT INTO users VALUES (?, ?)", ("alice", "wonderland"))
    connection.commit()
    connection.close()


@app.post("/login")
def login():
    username = request.json.get("username", "")
    password = request.json.get("password", "")
    query = f"SELECT username FROM users WHERE username = '{username}' AND password = '{password}'"
    connection = get_db()
    user = connection.execute(query).fetchone()
    connection.close()
    if user:
        return jsonify({"status": "ok", "username": user["username"]})
    return jsonify({"status": "error"}), 401
