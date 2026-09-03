import app as target


def test_authenticated_admin_can_read_admin_data():
    client = target.app.test_client()
    with client.session_transaction() as session:
        session["role"] = "admin"
    response = client.get("/admin")
    assert response.status_code == 200
    assert response.get_json()["users"] == ["admin", "alice"]
