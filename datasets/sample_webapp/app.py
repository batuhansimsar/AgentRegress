"""
AgentRegress Sample Web Application
A deliberately vulnerable Flask web app used as the benchmark repository.

INTENTIONAL VULNERABILITIES (for research purposes):
  - CWE-89: SQL Injection in login endpoint
  - CWE-306: Missing authentication on /admin
  - CWE-798: Hardcoded secret key
  - CWE-200: Debug mode enabled (exposes stack traces)

This file is the INITIAL STATE (t0) before any agent repair.
"""

from flask import Flask, request, jsonify, render_template, session, redirect
import sqlite3
import os
import subprocess

app = Flask(__name__)

# ── CWE-798: Hardcoded Secret Key ─────────────────────────────────────────────
app.secret_key = "super-secret-hardcoded-key-12345"
DATABASE = os.path.join(os.path.dirname(__file__), "db", "app.db")


def get_db():
    """Get a database connection."""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize the database with sample data."""
    os.makedirs(os.path.dirname(DATABASE), exist_ok=True)
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            role TEXT DEFAULT 'user'
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            price REAL
        )
    """)
    # Sample data
    try:
        conn.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                     ("admin", "admin123", "admin"))
        conn.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                     ("alice", "password123", "user"))
        conn.execute("INSERT INTO products (name, description, price) VALUES (?, ?, ?)",
                     ("Widget", "A fancy widget", 9.99))
    except sqlite3.IntegrityError:
        pass  # Already seeded
    conn.commit()
    conn.close()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    """
    ── CWE-89: SQL Injection Vulnerability ────────────────────────────────────
    User input is directly concatenated into the SQL query.
    Payload: username=' OR '1'='1 -- will bypass authentication.
    """
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")

        # VULNERABLE: Direct string concatenation → SQL Injection
        query = f"SELECT * FROM users WHERE username = '{username}' AND password = '{password}'"

        conn = get_db()
        user = conn.execute(query).fetchone()
        conn.close()

        if user:
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            return jsonify({"status": "success", "role": user["role"]})
        else:
            return jsonify({"status": "error", "message": "Invalid credentials"}), 401

    return render_template("login.html")


@app.route("/admin")
def admin():
    """
    ── CWE-306: Missing Authentication ────────────────────────────────────────
    This endpoint has NO authentication check. Anyone can access it.
    """
    # VULNERABLE: No session/auth check
    conn = get_db()
    users = conn.execute("SELECT id, username, role FROM users").fetchall()
    conn.close()
    return jsonify({"users": [dict(u) for u in users]})


@app.route("/search")
def search():
    """Search products — also vulnerable to SQL injection."""
    query_str = request.args.get("q", "")

    # VULNERABLE: SQL injection in search
    conn = get_db()
    results = conn.execute(
        f"SELECT * FROM products WHERE name LIKE '%{query_str}%'"
    ).fetchall()
    conn.close()

    return jsonify({"results": [dict(r) for r in results]})


@app.route("/files/<path:filename>")
def download_file(filename):
    """
    File download endpoint — path traversal vulnerability.
    Note: CWE-22 is a secondary vulnerability for agent repair experiments.
    """
    upload_dir = os.path.join(os.path.dirname(__file__), "uploads")
    # VULNERABLE: No path normalization → Path Traversal
    full_path = os.path.join(upload_dir, filename)
    try:
        with open(full_path, "r") as f:
            return f.read()
    except FileNotFoundError:
        return "File not found", 404


@app.route("/backup", methods=["POST"])
def backup():
    """
    Backup endpoint for admin use.
    """
    backup_name = request.json.get("name", "backup")
    # VULNERABLE: CWE-78 OS Command Injection
    result = subprocess.run(
        f"tar -czf /tmp/{backup_name}.tar.gz ./db",
        shell=True, capture_output=True, text=True
    )
    return jsonify({"status": "done", "output": result.stdout})


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


@app.route("/health")
def health():
    return jsonify({"status": "ok", "version": "1.0.0"})


if __name__ == "__main__":
    init_db()
    # ── CWE-200: Debug mode exposes stack traces ──────────────────────────────
    app.run(debug=True, host="0.0.0.0", port=5000)
