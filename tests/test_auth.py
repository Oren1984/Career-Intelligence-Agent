"""Authentication: bcrypt hashing, credentials file, throttling, CLI and the Streamlit login gate."""
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

from dashboard.ui.components import FOOTER_TEXT
from app.auth import (
    AuthError, LoginThrottle, authenticate, hash_password, load_users, session_timeout_minutes,
    upsert_user, verify_password,
)

ROOT = Path(__file__).resolve().parent.parent


def test_hash_and_verify():
    h = hash_password("correct horse")
    assert h.startswith("$2") and "correct horse" not in h
    assert verify_password("correct horse", h)
    assert not verify_password("wrong", h)
    assert not verify_password("x", "not-a-hash")


def test_password_policy():
    with pytest.raises(AuthError):
        hash_password("short")
    with pytest.raises(AuthError):
        hash_password("é" * 40)  # > 72 bytes


def test_upsert_preserves_other_users_and_never_stores_plaintext(tmp_path):
    path = tmp_path / "users.yaml"
    upsert_user("oren", "personal", "owner-secret-1", path=path)
    upsert_user("demo", "demo", "demo2026", path=path)
    upsert_user("oren", "personal", "owner-secret-2", path=path)   # password change
    users = load_users(path)
    assert set(users) == {"oren", "demo"}
    assert users["demo"].workspace == "demo"
    assert verify_password("owner-secret-2", users["oren"].password_hash)
    text = path.read_text(encoding="utf-8")
    assert "owner-secret" not in text and "demo2026" not in text


def test_upsert_rejects_bad_input(tmp_path):
    with pytest.raises(AuthError):
        upsert_user("Bad Name", "personal", "longenough", path=tmp_path / "u.yaml")
    with pytest.raises(ValueError):
        upsert_user("oren", "admin", "longenough", path=tmp_path / "u.yaml")


def test_load_users_skips_malformed_entries(tmp_path):
    path = tmp_path / "users.yaml"
    path.write_text(yaml.safe_dump({"users": {
        "good": {"workspace": "demo", "password_hash": hash_password("password1")},
        "nohash": {"workspace": "demo"},
        "plain": {"workspace": "demo", "password_hash": "password1"},
        "badws": {"workspace": "root", "password_hash": hash_password("password1")},
    }}), encoding="utf-8")
    assert set(load_users(path)) == {"good"}
    assert load_users(tmp_path / "missing.yaml") == {}


def _users():
    from app.auth import User
    return {"oren": User("oren", "personal", hash_password("owner-pass"))}


def test_authenticate_outcomes():
    throttle = LoginThrottle()
    users = _users()
    assert authenticate("oren", "owner-pass", users, throttle).reason == "ok"
    assert authenticate("OREN ", "owner-pass", users, throttle).user.username == "oren"
    assert authenticate("oren", "nope", users, throttle).reason == "invalid"
    assert authenticate("ghost", "owner-pass", users, throttle).reason == "invalid"  # same reason: no enumeration
    assert authenticate("oren", "owner-pass", {}, throttle).reason == "no_users"


def test_lockout_after_repeated_failures_and_expiry():
    now = [1000.0]
    throttle = LoginThrottle(max_failures=3, window=60, lockout=120, clock=lambda: now[0])
    users = _users()
    for _ in range(2):
        assert authenticate("oren", "bad", users, throttle).reason == "invalid"
    assert authenticate("oren", "bad", users, throttle).reason == "locked"
    # Even the right password is refused while locked.
    assert authenticate("oren", "owner-pass", users, throttle).reason == "locked"
    now[0] += 121
    assert authenticate("oren", "owner-pass", users, throttle).reason == "ok"


def test_session_timeout_setting(tmp_path, monkeypatch):
    path = tmp_path / "u.yaml"
    path.write_text("session_timeout_minutes: 15\n", encoding="utf-8")
    monkeypatch.delenv("SESSION_TIMEOUT_MINUTES", raising=False)
    assert session_timeout_minutes(path) == 15
    monkeypatch.setenv("SESSION_TIMEOUT_MINUTES", "5")
    assert session_timeout_minutes(path) == 5
    monkeypatch.setenv("SESSION_TIMEOUT_MINUTES", "junk")
    assert session_timeout_minutes(path) == 60


def test_create_user_cli_reads_stdin_and_never_echoes(tmp_path):
    path = tmp_path / "users.yaml"
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "create_user.py"), "oren", "--workspace", "personal",
         "--users-file", str(path), "--password-stdin"],
        input="s3cret-owner-pw\n", capture_output=True, text=True, cwd=ROOT,
    )
    assert proc.returncode == 0, proc.stderr
    assert "s3cret-owner-pw" not in proc.stdout + proc.stderr
    assert verify_password("s3cret-owner-pw", load_users(path)["oren"].password_hash)

    bad = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "create_user.py"), "oren", "--workspace", "personal",
         "--users-file", str(path), "--password-stdin"],
        input="short\n", capture_output=True, text=True, cwd=ROOT,
    )
    assert bad.returncode == 1


# ── Streamlit login gate (AppTest, SQLite) ───────────────────────────────────

@pytest.fixture
def app_env(tmp_path, monkeypatch):
    from app.auth import THROTTLE
    from app.db.session import dispose_engines

    users = tmp_path / "users.yaml"
    upsert_user("oren", "personal", "owner-pass-1", path=users)
    upsert_user("demo", "demo", "demo2026", path=users)
    monkeypatch.setenv("USERS_FILE", str(users))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'app.db'}")
    monkeypatch.setenv("SEARCH_BACKEND", "tfidf")
    monkeypatch.setenv("SESSION_TIMEOUT_MINUTES", "60")
    THROTTLE.record_success("oren")
    yield
    dispose_engines()


def _app():
    from streamlit.testing.v1 import AppTest
    return AppTest.from_file(str(ROOT / "dashboard" / "streamlit_app.py"), default_timeout=60)


def _login(at, user, pw):
    at.text_input[0].input(user)
    at.text_input[1].input(pw)
    at.button[0].click()
    return at.run()


def _signed_in(user, workspace, **extra):
    at = _app()
    at.session_state["auth"] = {"username": user, "workspace": workspace,
                                "login_at": time.time(), "last_activity": time.time(), **extra}
    return at


def test_unauthenticated_sees_only_login(app_env):
    at = _app().run()
    assert not at.exception
    assert "auth" not in at.session_state
    assert [ti.label for ti in at.text_input] == ["Username", "Password"]
    assert any(FOOTER_TEXT in m.value for m in at.markdown)
    assert not at.sidebar.button  # no logout / navigation before sign-in


def test_wrong_password_is_rejected(app_env):
    at = _login(_app().run(), "oren", "wrong-password")
    assert "auth" not in at.session_state
    assert at.error and "Incorrect" in at.error[0].value


def test_login_binds_workspace_from_credentials(app_env):
    at = _login(_app().run(), "demo", "demo2026")
    assert not at.exception
    assert at.session_state["auth"]["workspace"] == "demo"
    assert at.session_state["auth"]["username"] == "demo"


def test_authenticated_app_and_logout_clears_session(app_env):
    at = _signed_in("demo", "demo").run()
    assert not at.exception
    assert at.title and at.title[0].value == "Dashboard"
    assert any(FOOTER_TEXT in m.value for m in at.markdown)
    at.session_state["weekly_review"] = {"executive_summary": "private"}
    logout = next(b for b in at.sidebar.button if b.label == "Log out")
    at = logout.click().run()
    assert "auth" not in at.session_state
    assert "weekly_review" not in at.session_state


def test_inactivity_expiry_signs_out(app_env):
    at = _signed_in("oren", "personal", last_activity=time.time() - 61 * 60).run()
    assert "auth" not in at.session_state
    assert at.warning and "expired" in at.warning[0].value.lower()


def test_language_preference_is_remembered_per_account(app_env):
    at = _signed_in("oren", "personal").run()
    at.sidebar.selectbox[0].select("he").run()
    assert at.session_state["lang"] == "he"
    fresh = _login(_app().run(), "oren", "owner-pass-1")
    assert fresh.session_state["lang"] == "he"
    demo = _login(_app().run(), "demo", "demo2026")
    assert demo.session_state["lang"] == "en"


def test_workspace_cannot_be_chosen_by_the_browser(app_env):
    at = _app()
    at.query_params["workspace"] = "personal"
    at = at.run()
    assert "auth" not in at.session_state   # still the login screen
    at = _login(at, "demo", "demo2026")
    assert at.session_state["auth"]["workspace"] == "demo"


def test_page_code_requires_authentication():
    from dashboard.ui.context import NotAuthenticated, workspace
    with pytest.raises(NotAuthenticated):
        workspace()


def test_footer_text_is_exact():
    assert FOOTER_TEXT == "Developed and built by Oren Salami - V2.0"
