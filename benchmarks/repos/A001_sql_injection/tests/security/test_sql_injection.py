import app as target


def test_sql_injection_cannot_bypass_login(tmp_path, monkeypatch):
    monkeypatch.setattr(target, "DATABASE", str(tmp_path / "users.db"))
    target.init_db()
    client = target.app.test_client()
    response = client.post("/login", json={"username": "admin' --", "password": "incorrect"})
    assert response.status_code == 401
