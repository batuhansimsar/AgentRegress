import app as target


def test_greeting_returns_the_requested_name():
    response = target.app.test_client().get("/greet/Ada")
    assert response.status_code == 200
    assert response.get_json() == {"message": "Hello, Ada!"}
