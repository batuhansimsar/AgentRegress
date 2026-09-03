import app as target


def test_valid_login_succeeds(tmp_path, monkeypatch):
    monkeypatch.setattr(target, "DATABASE", str(tmp_path / "users.db"))
    target.init_db()
    client = target.app.test_client()
    response = client.post("/login", json={"username": "alice", "password": "wonderland"})
    assert response.status_code == 200
    assert response.get_json()["username"] == "alice"
