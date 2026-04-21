def test_app_factory_creates(app):
    assert app is not None
    assert app.url_map is not None


def test_index_serves_homepage(client):
    response = client.get("/")
    assert response.status_code == 200
    body = response.data
    assert b"IGCSE 0580 Mathematics" in body
    assert body.count(b'class="topic-card"') == 7
    assert b"29 Apr 2026" in body


def test_static_css_served(client):
    response = client.get("/static/css/style.css")
    assert response.status_code == 200
    assert b"--color-background-primary" in response.data


def test_static_js_served(client):
    response = client.get("/static/js/app.js")
    assert response.status_code == 200
    assert b"igcse-theme" in response.data


def test_health_endpoint_reports_healthy(client):
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["db"] == "connected"
    assert payload["volume"] == "writable"
