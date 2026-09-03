import app as target


def test_application_does_not_enable_debug_error_exposure():
    assert target.app.debug is False
    response = target.app.test_client().get("/not-a-route")
    assert response.status_code == 404
    assert b"Traceback" not in response.data
