"""Cross-phase integration tests. Seed a minimal DB, log in as an admin,
create a user, attempt a question, hit the revision page. Proves the blueprint
wiring works end-to-end."""
from __future__ import annotations

import pytest


def _seed_minimal(app):
    from extensions import db
    from models import (
        Attempt,
        Note,
        Paper,
        Question,
        SubPart,
        Syllabus,
        Topic,
        User,
    )
    from auth import hash_password

    with app.app_context():
        s = Syllabus(code="0580", name="Test Maths")
        db.session.add(s)
        db.session.flush()

        Paper.query.delete()
        p = Paper(syllabus_id=s.id, number=2, supports_digital_input=False)
        db.session.add(p)

        t = Topic(
            syllabus_id=s.id,
            number=1,
            name="Irrationals",
            short_name="Irrational",
            color_class="color-purple",
        )
        db.session.add(t)
        db.session.flush()

        n = Note(topic_id=t.id, content_html="<p>Irrationals note</p>")
        db.session.add(n)

        # A past paper Q + subpart for the exercise flow
        from models import PastPaper, Session

        sess = Session(year=2025, series="O/N")
        db.session.add(sess)
        db.session.flush()
        pp = PastPaper(
            syllabus_id=s.id,
            paper_id=p.id,
            session_id=sess.id,
            variant=1,
            source_pdf_path="/tmp/fake.pdf",
        )
        db.session.add(pp)
        db.session.flush()
        q = Question(
            past_paper_id=pp.id,
            question_number=1,
            topic_id=t.id,
            body_html="<p>Q1</p>",
            extraction_status="admin_approved",
        )
        db.session.add(q)
        db.session.flush()
        sp = SubPart(
            question_id=q.id,
            letter="a",
            body_html="<p>Work out 2+2.</p>",
            answer_schema="scalar",
            correct_answer="4",
            marks=1,
        )
        db.session.add(sp)

        # admin + student users
        admin = User(
            email="admin@test",
            password_hash=hash_password("adminpw"),
            role="admin",
            syllabus_id=s.id,
        )
        student = User(
            email="student@test",
            password_hash=hash_password("studentpw"),
            role="student",
            syllabus_id=s.id,
        )
        db.session.add(admin)
        db.session.add(student)
        db.session.commit()

        return {
            "syllabus_id": s.id,
            "topic_id": t.id,
            "subpart_id": sp.id,
            "admin_email": admin.email,
            "student_email": student.email,
        }


def _login(client, email, password):
    return client.post(
        "/login",
        data={"email": email, "password": password},
        follow_redirects=False,
    )


def test_root_redirects_anon_to_login(app, client):
    _seed_minimal(app)
    # Anonymous user: / → /login regardless of seeded content.
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in r.headers["Location"]


def test_root_after_login_goes_to_notes_when_user_has_syllabus(app, client):
    ctx = _seed_minimal(app)
    _login(client, ctx["student_email"], "studentpw")  # seeded user has syllabus_id set
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 302
    assert "/notes" in r.headers["Location"]


def test_syllabus_selector_requires_login(app, client):
    _seed_minimal(app)
    # Anonymous POST → should bounce to login, NOT silently succeed.
    r = client.post("/syllabus", data={"code": "0580"}, follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in r.headers["Location"]


def test_syllabus_selector_persists_for_logged_in_user(app, client):
    ctx = _seed_minimal(app)
    _login(client, ctx["student_email"], "studentpw")
    r = client.post("/syllabus", data={"code": "0580"}, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/notes")
    r2 = client.get("/notes")
    assert r2.status_code == 200
    assert b"Irrationals note" in r2.data


def test_notes_partial_returns_topic_card(app, client):
    ctx = _seed_minimal(app)
    _login(client, ctx["student_email"], "studentpw")
    r = client.get(f"/notes/{ctx['topic_id']}/partial")
    assert r.status_code == 200
    assert b"class=\"topic-card\"" in r.data
    assert b"Irrationals note" in r.data


def test_notes_partial_allows_admin(app, client):
    """Admin can preview student-facing notes. They stay logged in as admin
    and the page renders with the admin's own (empty) personalisation — the
    point is layout QA, not impersonation of a specific student."""
    ctx = _seed_minimal(app)
    _login(client, ctx["admin_email"], "adminpw")
    r = client.get(f"/notes/{ctx['topic_id']}/partial", follow_redirects=False)
    assert r.status_code == 200


def test_admin_login_lands_on_admin_dashboard(app, client):
    ctx = _seed_minimal(app)
    r = _login(client, ctx["admin_email"], "adminpw")
    assert r.status_code == 302
    # Admins go straight to /admin/ on login, not the syllabus picker.
    assert "/admin" in r.headers["Location"]

    r2 = client.get("/admin/")
    assert r2.status_code == 200


def test_admin_syllabus_switch_does_not_write_user_row(app, client):
    ctx = _seed_minimal(app)
    _login(client, ctx["admin_email"], "adminpw")
    # Clear any residual syllabus_id (seed sets admin.syllabus_id for now).
    from models import User

    with app.app_context():
        admin = User.query.filter_by(email=ctx["admin_email"]).first()
        admin.syllabus_id = None
        from extensions import db as _db

        _db.session.commit()

    client.post("/syllabus", data={"code": "0580"})

    with app.app_context():
        admin = User.query.filter_by(email=ctx["admin_email"]).first()
        assert admin.syllabus_id is None, "Admin switching syllabus should NOT write User.syllabus_id"


def test_admin_login_and_user_creation(app, client):
    ctx = _seed_minimal(app)
    r = _login(client, ctx["admin_email"], "adminpw")
    assert r.status_code == 302

    r2 = client.get("/admin/")
    assert r2.status_code == 200

    # Separate student/admin add-user forms post role + local_part; the
    # domain is inferred server-side. See routes/admin._create_user_from_parts.
    r3 = client.post(
        "/admin/users",
        data={"role": "student", "local_part": "new.student", "syllabus_code": "0580"},
    )
    assert r3.status_code == 200
    from models import User

    with app.app_context():
        u = User.query.filter_by(email="new.student@students.bdcschool.eu").first()
        assert u is not None
        assert u.username == "new.student"
        assert u.role == "student"
        assert u.generated_password is not None


def test_student_cannot_access_admin(app, client):
    ctx = _seed_minimal(app)
    _login(client, ctx["student_email"], "studentpw")
    r = client.get("/admin/", follow_redirects=False)
    assert r.status_code == 403


def test_attempt_scalar_correct_updates_nothing(app, client):
    ctx = _seed_minimal(app)
    _login(client, ctx["student_email"], "studentpw")
    r = client.post(
        f"/attempt/{ctx['subpart_id']}",
        json={"answer": "4"},
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["verdict"] == "correct_optimal"

    from models import Attempt, ErrorProfile

    with app.app_context():
        assert Attempt.query.count() == 1
        assert ErrorProfile.query.count() == 0  # optimal → no error bump


def test_attempt_scalar_wrong_bumps_error_profile(app, client):
    ctx = _seed_minimal(app)
    _login(client, ctx["student_email"], "studentpw")
    r = client.post(
        f"/attempt/{ctx['subpart_id']}",
        json={"answer": "5"},
    )
    assert r.get_json()["verdict"] == "incorrect"

    from models import ErrorProfile

    with app.app_context():
        rows = ErrorProfile.query.all()
        assert len(rows) == 1
        assert rows[0].count == 1
        assert rows[0].weight == pytest.approx(1.0)


def test_revision_redirects_to_onboarding_when_no_style(app, client):
    ctx = _seed_minimal(app)
    _login(client, ctx["student_email"], "studentpw")
    r = client.get("/revision", follow_redirects=False)
    assert r.status_code == 302
    assert "/onboarding/style" in r.headers["Location"]


def test_onboarding_classifies_and_redirects(app, client):
    ctx = _seed_minimal(app)
    _login(client, ctx["student_email"], "studentpw")
    # Answer all 14 questions with "B" — a repeatable combination the new
    # classifier maps to one of the four profiles + sr_overlay flag.
    data = {f"q{i}": "B" for i in range(1, 15)}
    r = client.post("/onboarding/style", data=data, follow_redirects=False)
    assert r.status_code == 302
    assert "/revision" in r.headers["Location"]

    from models import User
    from services.style_classifier import VALID_STYLES

    with app.app_context():
        u = User.query.filter_by(email=ctx["student_email"]).first()
        assert u.learning_style_profile in VALID_STYLES
        assert u.learning_style_scores is not None
        assert "D" in u.learning_style_scores


def test_revision_page_renders_after_style_set(app, client):
    ctx = _seed_minimal(app)
    _login(client, ctx["student_email"], "studentpw")
    data = {f"q{i}": "B" for i in range(1, 15)}
    client.post("/onboarding/style", data=data)
    r = client.get("/revision")
    assert r.status_code == 200
    # Stub revision note includes the profile name as HTML.
    assert b"topic-card" in r.data


def test_prototype_endpoint_404_when_flag_off(client):
    r = client.post("/prototype/diagnose")
    assert r.status_code == 404


def test_prototype_endpoint_responds_when_flag_on(app, client, monkeypatch):
    monkeypatch.setenv("FEATURE_PROTOTYPE", "1")
    import io

    r = client.post(
        "/prototype/diagnose",
        data={
            "subpart_body": "x",
            "correct_answer": "4",
            "submitted_answer": "4",
            "photo": (io.BytesIO(b"\x00"), "p.jpg"),
        },
        content_type="multipart/form-data",
    )
    assert r.status_code == 200
    assert r.get_json()["verdict"] == "correct_optimal"


def test_media_path_traversal_blocked(app, client):
    ctx = _seed_minimal(app)
    _login(client, ctx["admin_email"], "adminpw")
    r = client.get("/media/past-papers/../../etc/passwd")
    assert r.status_code in (403, 404)


def test_rate_limit_returns_429_after_cap(app, client):
    ctx = _seed_minimal(app)
    _login(client, ctx["student_email"], "studentpw")

    from services.ratelimit import bump_and_check

    with app.app_context():
        uid = None
        from models import User

        uid = User.query.filter_by(email=ctx["student_email"]).first().id

        for _ in range(3):
            bump_and_check(uid, "test_endpoint", daily_cap=3)
        # 4th call over cap
        assert bump_and_check(uid, "test_endpoint", daily_cap=3) is False


def test_empty_db_anon_still_goes_to_login(app, client):
    """Even with an empty DB, anonymous / → /login (no legacy page for anon)."""
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in r.headers["Location"]


def test_admin_can_view_student_exercise_page(app, client):
    """After dropping the student_only admin-bounce, admin can hit /exercise."""
    ctx = _seed_minimal(app)
    _login(client, ctx["admin_email"], "adminpw")
    r = client.get("/exercise", follow_redirects=False)
    # 200 (renders picker) or 302 to syllabus picker — anything but a
    # redirect to /admin, which was the old behaviour.
    assert r.status_code in (200, 302)
    if r.status_code == 302:
        assert "/admin" not in r.headers["Location"]


# --- OTP + forced rotation (Feature 2) ---


def _create_user_via_admin(client, ctx, local_part: str, role: str = "student"):
    """Drive the admin add-user form to exercise the real creation path
    (which sets must_change_password=True + generated_password)."""
    _login(client, ctx["admin_email"], "adminpw")
    client.post(
        "/admin/users",
        data={"role": role, "local_part": local_part, "syllabus_code": "0580"},
    )
    client.post("/logout")


def test_new_classroom_user_is_forced_to_set_password(app, client):
    """Admin creates a student → student logs in with OTP → every non-
    set-password URL bounces them back to the set-password form."""
    ctx = _seed_minimal(app)
    _create_user_via_admin(client, ctx, "force.rotate")

    from models import User

    with app.app_context():
        u = User.query.filter_by(username="force.rotate").first()
        assert u.must_change_password is True
        otp = u.generated_password
    assert otp  # OTP was generated

    # Log in with the OTP — the before_request guard should bounce every
    # non-allow-listed URL to the set-password form.
    _login(client, "force.rotate@students.bdcschool.eu", otp)
    r = client.get("/notes", follow_redirects=False)
    assert r.status_code == 302
    assert "/auth/set-password" in r.headers["Location"]


def test_set_password_rotation_unlocks_routes(app, client):
    """Posting a new password clears the flag and stores the plaintext
    in current_password, leaving generated_password untouched as audit."""
    ctx = _seed_minimal(app)
    _create_user_via_admin(client, ctx, "happy.rotator")

    from models import User

    with app.app_context():
        u = User.query.filter_by(username="happy.rotator").first()
        otp = u.generated_password

    _login(client, "happy.rotator@students.bdcschool.eu", otp)
    r = client.post(
        "/auth/set-password",
        data={"new_password": "new-good-password-42", "confirm_password": "new-good-password-42"},
        follow_redirects=False,
    )
    assert r.status_code == 302

    with app.app_context():
        u = User.query.filter_by(username="happy.rotator").first()
        assert u.must_change_password is False
        assert u.current_password == "new-good-password-42"
        # The original OTP stays as audit of what was first issued.
        assert u.generated_password == otp
        assert u.generated_password != u.current_password

    # Normal routes should now work.
    r2 = client.get("/notes", follow_redirects=False)
    assert r2.status_code != 302 or "/auth/set-password" not in r2.headers.get("Location", "")


def test_seed_admin_is_not_bounced_to_set_password(app, client):
    """Existing admins (must_change_password=False by model default) should
    never see the rotation screen. Ensures pre-existing rows aren't frozen
    out when the feature ships."""
    ctx = _seed_minimal(app)
    _login(client, ctx["admin_email"], "adminpw")
    r = client.get("/admin/", follow_redirects=False)
    assert r.status_code == 200


def test_set_password_rejects_short_password(app, client):
    ctx = _seed_minimal(app)
    _create_user_via_admin(client, ctx, "shortpw.guard")

    from models import User

    with app.app_context():
        otp = User.query.filter_by(username="shortpw.guard").first().generated_password

    _login(client, "shortpw.guard@students.bdcschool.eu", otp)
    r = client.post(
        "/auth/set-password",
        data={"new_password": "abc", "confirm_password": "abc"},
        follow_redirects=False,
    )
    # Rejected → 302 back to the form; flag still set.
    assert r.status_code == 302
    with app.app_context():
        u = User.query.filter_by(username="shortpw.guard").first()
        assert u.must_change_password is True


def test_csv_export_includes_otp_and_current_password(app, client):
    """Admin export has both the issued OTP and (once rotated) the chosen
    password, plus a status column."""
    ctx = _seed_minimal(app)
    _login(client, ctx["admin_email"], "adminpw")
    r = client.get("/admin/users/export.csv")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    header = body.splitlines()[0]
    assert "one_time_password" in header
    assert "current_password" in header
    assert "password_status" in header
