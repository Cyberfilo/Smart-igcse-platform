def test_app_factory_creates(app):
    assert app is not None
    assert app.url_map is not None


def test_index_redirects_anon_to_login(client):
    """Auth-first flow: anonymous user hitting / bounces to /login."""
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_login_page_renders(client):
    response = client.get("/login")
    assert response.status_code == 200
    assert b"Sign in" in response.data
    assert b'name="email"' in response.data
    assert b'name="password"' in response.data


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
