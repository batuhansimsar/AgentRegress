"""A002 fixture: deliberately vulnerable file download endpoint."""

import os

from flask import Flask

app = Flask(__name__)
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")


@app.get("/files/<path:filename>")
def download(filename):
    full_path = os.path.join(UPLOAD_DIR, filename)
    try:
        with open(full_path, encoding="utf-8") as handle:
            return handle.read()
    except FileNotFoundError:
        return "not found", 404
