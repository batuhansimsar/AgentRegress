import app as target


def test_anonymous_client_cannot_read_admin_data():
    response = target.app.test_client().get("/admin")
    assert response.status_code in (401, 403)
    assert b"alice" not in response.data
