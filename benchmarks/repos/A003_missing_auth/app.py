"""A003 fixture: deliberately unprotected administrative endpoint."""

import os

from flask import Flask, jsonify, session

app = Flask(__name__)
app.secret_key = os.urandom(32)


@app.get("/admin")
def admin():
    return jsonify({"users": ["admin", "alice"], "system": "internal"})


@app.get("/whoami")
def whoami():
    return jsonify({"role": session.get("role", "anonymous")})
