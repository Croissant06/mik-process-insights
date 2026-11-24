"""Admin accounts, login, sessions, throttling, audit, read-only views."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app import admin_auth as auth
from app.models import AdminAudit, AdminSession, AdminUser, Submission

PW = "correct horse battery"
JSON = {"content-type": "application/json"}


def sf(client):
    return client.app.state.session_factory


def make_admin(client, login="martin", name="Мартин Тест", password=PW):
    with sf(client)() as db:
        return auth.create_admin(db, login, name, password).id


@pytest.fixture(autouse=True)
def fast_scrypt(monkeypatch):
    """Tests use a cheap scrypt cost; test_production_scrypt_cost pins the real one."""
    monkeypatch.setattr(auth, "_N", 2**10)


def login_token(client):
    """GET the login page like a browser: returns the double-submit CSRF token (also set as a cookie)."""
    import re
    page = client.get("/admin/login")
    assert page.status_code == 200
    return re.search(r'name="csrf" value="([^"]+)"', page.text).group(1)


def login(client, user="martin", password=PW, token=None, **kw):
    token = token or login_token(client)
    return client.post("/admin/login", content=f"csrf={token}&login={user}&password={password}", follow_redirects=False,
                       headers={"content-type": "application/x-www-form-urlencoded", "cookie": f"mik_login_csrf={token}"}, **kw)


def audit_actions(client):
    with sf(client)() as db:
        return [a.action for a in db.scalars(select(AdminAudit).order_by(AdminAudit.id))]


def submit(client, valid_payload, **over):
    p = valid_payload(client)
    p.update(over)
    r = client.post("/api/submissions", json=p)
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ---- passwords -------------------------------------------------------------------------------------------------

def test_hash_roundtrip_and_format():
    h = auth.hash_password(PW)
    assert h.startswith("scrypt$") and PW not in h
    assert auth.verify_password(PW, h) and not auth.verify_password(PW + "x", h)
    assert auth.hash_password(PW) != h  # salted


@pytest.mark.parametrize("bad", ["", "x", "scrypt$1$2", "md5$a$b$c$d$e", "scrypt$a$b$c$d$e"])
def test_malformed_stored_hash_never_raises(bad):
    assert auth.verify_password(PW, bad) is False


def test_weak_passwords_and_bad_logins_are_refused(client):
    with sf(client)() as db:
        for pw in ["short", "aaaaaaaaaaaaaaaa"]:
            with pytest.raises(auth.AdminError):
                auth.create_admin(db, "anna", "Анна", pw)
        for lg in ["", "A B", "x", "../etc", "ab"]:
            with pytest.raises(auth.AdminError):
                auth.create_admin(db, lg, "Анна", PW)


def test_at_most_four_active_admins(client):
    with sf(client)() as db:
        for i in range(4):
            auth.create_admin(db, f"admin{i}", f"Админ {i}", PW)
        with pytest.raises(auth.AdminError):
            auth.create_admin(db, "fifth", "Пети", PW)
        # deactivating one frees a place
        u = auth.get_by_login(db, "admin0")
        u.is_active = False
        db.commit()
        auth.create_admin(db, "fifth", "Пети", PW)


def test_duplicate_login_refused_case_insensitively(client):
    make_admin(client)
    with sf(client)() as db:
        with pytest.raises(auth.AdminError):
            auth.create_admin(db, "MARTIN", "Друг", PW)


# ---- login / session -------------------------------------------------------------------------------------------

def test_pages_require_login(client, valid_payload):
    sid = submit(client, valid_payload)
    for path in ["/admin", "/admin/", f"/admin/reports/{sid}"]:
        r = client.get(path, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/admin/login"


def test_login_sets_a_hardened_cookie_and_opens_the_list(client, valid_payload):
    make_admin(client)
    submit(client, valid_payload)
    r = login(client)
    assert r.status_code == 303 and r.headers["location"] == "/admin"
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "path=/admin" in cookie
    assert PW not in r.headers["set-cookie"]
    page = client.get("/admin")
    assert page.status_code == 200 and "Подадени отчети" in page.text and "Мартин Тест" in page.text
    for h, v in [("cache-control", "no-store"), ("x-robots-tag", "noindex, nofollow"), ("x-frame-options", "DENY")]:
        assert page.headers[h] == v


def test_admin_pages_never_use_no_referrer(client):
    """Regression (found in a real browser): Referrer-Policy no-referrer makes Chrome send 'Origin: null' on form posts."""
    make_admin(client)
    assert client.get("/admin/login").headers["referrer-policy"] == "same-origin"
    login(client)
    assert client.get("/admin").headers["referrer-policy"] == "same-origin"


def test_origin_null_is_still_refused(client):
    make_admin(client)
    r = client.post("/admin/login", content=f"login=martin&password={PW}", follow_redirects=False,
                    headers={"content-type": "application/x-www-form-urlencoded", "origin": "null"})
    assert r.status_code == 403


def test_secure_flag_follows_setting(make_client):
    c = make_client(cookie_secure=True)
    make_admin(c)
    assert "secure" in login(c).headers["set-cookie"].lower()


def test_wrong_password_and_unknown_user_look_identical(client):
    make_admin(client)
    a = login(client, password="wrong password here")
    b = login(client, user="nobody", password="wrong password here")
    assert a.status_code == b.status_code == 401
    strip = lambda r: __import__("re").sub(r'name="csrf" value="[^"]+"', "", r.text)  # noqa: E731
    assert strip(a) == strip(b) and "Грешно потребителско име или парола." in a.text
    assert "mik_admin" not in a.headers.get("set-cookie", "")


def test_inactive_admin_cannot_login_and_live_session_dies(client):
    uid = make_admin(client)
    assert login(client).status_code == 303 and client.get("/admin").status_code == 200
    with sf(client)() as db:
        db.get(AdminUser, uid).is_active = False
        db.commit()
    assert client.get("/admin", follow_redirects=False).status_code == 303
    assert login(client).status_code == 401


def test_session_expires_idle_and_absolute(client):
    make_admin(client)
    login(client)
    with sf(client)() as db:
        s = db.scalar(select(AdminSession))
        s.last_seen_at = datetime.now(timezone.utc) - auth.SESSION_IDLE - timedelta(minutes=1)
        db.commit()
    assert client.get("/admin", follow_redirects=False).status_code == 303
    with sf(client)() as db:
        assert db.scalar(select(func.count()).select_from(AdminSession)) == 0  # deleted, not just ignored
    login(client)
    with sf(client)() as db:
        s = db.scalar(select(AdminSession))
        s.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    assert client.get("/admin", follow_redirects=False).status_code == 303


def test_session_token_is_not_stored_in_clear(client):
    make_admin(client)
    token = login(client).cookies.get("mik_admin") or client.cookies.get("mik_admin")
    with sf(client)() as db:
        s = db.scalar(select(AdminSession))
        assert token and s.id != token and len(s.id) == 64


def test_garbage_cookie_is_just_logged_out(client):
    client.cookies.set("mik_admin", "x" * 500, path="/admin")
    assert client.get("/admin", follow_redirects=False).status_code == 303


def test_logout_needs_the_csrf_token_and_kills_the_session(client):
    make_admin(client)
    login(client)
    html = client.get("/admin").text
    csrf = html.split('name="csrf" value="')[1].split('"')[0]
    form = {"content-type": "application/x-www-form-urlencoded"}
    assert client.post("/admin/logout", content="csrf=wrong", headers=form, follow_redirects=False).status_code == 403
    assert client.get("/admin").status_code == 200  # still signed in
    r = client.post("/admin/logout", content=f"csrf={csrf}", headers=form, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/admin/login"
    assert client.get("/admin", follow_redirects=False).status_code == 303


def test_cross_site_login_post_is_rejected(client):
    make_admin(client)
    r = client.post("/admin/login", content=f"login=martin&password={PW}", follow_redirects=False,
                    headers={"content-type": "application/x-www-form-urlencoded", "origin": "http://evil.example"})
    assert r.status_code == 403 and "set-cookie" not in r.headers


def test_login_is_throttled_after_repeated_failures(client):
    make_admin(client)
    for _ in range(5):
        assert login(client, password="wrong password here").status_code == 401
    r = login(client)  # even the right password is refused while locked
    assert r.status_code == 429 and "mik_admin" not in r.headers.get("set-cookie", "")


def test_throttle_unit():
    t = [0.0]
    th = auth.LoginThrottle(limit=3, window=100, lock_seconds=50, clock=lambda: t[0])
    for _ in range(3):
        th.failure("k")
    assert th.locked_for("k") > 0
    t[0] = 60
    assert th.locked_for("k") == 0


# ---- audit ------------------------------------------------------------------------------------------------------

def test_audit_log_records_actions_without_secrets(client, valid_payload):
    uid = make_admin(client)
    login(client, password="wrong password here")
    login(client)
    sid = submit(client, valid_payload)
    client.get("/admin")
    client.get(f"/admin/reports/{sid}")
    acts = audit_actions(client)
    assert acts == ["admin_created", "login_failed", "login_ok", "list_reports", "view_report"]
    with sf(client)() as db:
        blob = " ".join(f"{a.action} {a.detail}" for a in db.scalars(select(AdminAudit)))
        assert PW not in blob and "wrong password" not in blob
        assert db.scalar(select(AdminAudit).where(AdminAudit.action == "view_report")).user_id == uid


# ---- views ------------------------------------------------------------------------------------------------------

def test_list_filters_and_pagination(client, valid_payload):
    make_admin(client)
    for i in range(27):
        submit(client, valid_payload, department="dept_1" if i % 3 else "dept_2")
    login(client)
    p1 = client.get("/admin").text
    assert "Общо: 27" in p1 and "Страница 1 от 2" in p1 and "Следваща" in p1
    p2 = client.get("/admin?page=2").text
    assert "Страница 2 от 2" in p2 and "Предишна" in p2
    d2 = client.get("/admin?department=dept_2").text
    assert "Общо: 9" in d2
    assert "Общо: 0" in client.get("/admin?from=2999-01-01").text
    assert "Общо: 27" in client.get("/admin?version=1").text
    assert "Общо: 0" in client.get("/admin?version=99").text
    # junk in filters must not crash
    for q in ["page=abc", "from=x", "to=2026-13-45", "version=%27", "department=%27%3Bdrop", "page=-5", "page=999"]:
        assert client.get(f"/admin?{q}").status_code == 200


def test_detail_shows_answers_and_escapes_html(client, valid_payload):
    make_admin(client)
    evil = '<script>alert(1)</script> & "кавички"'
    p = valid_payload(client)
    p["answers"]["tasks"] = evil
    p["answers"]["obstacles"] = {"selected": ["other", "waiting"], "texts": {"other": "<b>друго</b>"}}
    sid = client.post("/api/submissions", json=p).json()["id"]
    login(client)
    html = client.get(f"/admin/reports/{sid}").text
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html
    assert "<b>друго</b>" not in html and "&lt;b&gt;друго&lt;/b&gt;" in html
    assert "Тест Потребител" in html and "Основни задачи през деня" in html and "Изчакване на информация" in html


def test_detail_unknown_or_odd_id_is_404_not_500(client):
    make_admin(client)
    login(client)
    for sid in ["nope", "0" * 36, "%27%20OR%201=1", "a" * 200]:
        assert client.get(f"/admin/reports/{sid}").status_code == 404


def test_employee_form_is_unchanged_by_admin_css(client):
    html = client.get("/").text
    assert "admin.css" not in html


def test_admin_user_cli(make_client, db_url, monkeypatch, capsys):
    """scripts/admin_users.py end to end against the test database (passwords via the hidden prompt, mocked)."""
    import importlib.util
    from pathlib import Path

    c = make_client()  # creates the schema
    monkeypatch.setenv("DATABASE_URL", db_url)
    spec = importlib.util.spec_from_file_location("admin_users", Path(__file__).resolve().parent.parent / "scripts" / "admin_users.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt="": PW)
    assert cli.main(["create", "--login", "rosica", "--name", "Росица Тест"]) == 0
    assert cli.main(["create", "--login", "rosica", "--name", "Друга"]) == 1  # duplicate
    assert cli.main(["list"]) == 0
    out = capsys.readouterr()
    assert "rosica" in out.out and PW not in out.out + out.err
    assert login(c, user="rosica").status_code == 303
    assert cli.main(["deactivate", "--login", "rosica"]) == 0
    assert c.get("/admin", follow_redirects=False).status_code == 303  # signed out everywhere
    assert cli.main(["set-password", "--login", "nobody"]) == 1


# ---- hardening after ChatGPT's review of ef17c3e ----------------------------------------------------------------

def test_production_scrypt_cost_is_owasp_minimum(monkeypatch):
    monkeypatch.undo()
    assert (auth._N, auth._R, auth._P) == (2**17, 8, 1)
    h = auth.hash_password(PW)
    assert h.split("$")[1:4] == [str(2**17), "8", "1"] and auth.verify_password(PW, h)


def test_weaker_hash_is_upgraded_at_next_good_login(client, monkeypatch):
    make_admin(client)
    old = auth.hash_password(PW)  # cost 2**10 (test cost)
    with sf(client)() as db:
        auth.get_by_login(db, "martin").password_hash = old
        db.commit()
    monkeypatch.setattr(auth, "_N", 2**11)  # pretend the policy was raised
    assert auth.needs_rehash(old) and login(client).status_code == 303
    with sf(client)() as db:
        new = auth.get_by_login(db, "martin").password_hash
    assert new != old and new.split("$")[1] == str(2**11) and auth.verify_password(PW, new)
    assert not auth.needs_rehash(new)


def test_login_requires_matching_csrf_token(client):
    make_admin(client)
    token = login_token(client)
    form = {"content-type": "application/x-www-form-urlencoded"}
    body = f"login=martin&password={PW}"
    assert client.post("/admin/login", content=body, headers=form, follow_redirects=False).status_code == 403  # none
    r = client.post("/admin/login", content=f"csrf=wrong&{body}", headers={**form, "cookie": f"mik_login_csrf={token}"},
                    follow_redirects=False)
    assert r.status_code == 403 and "mik_admin" not in r.headers.get("set-cookie", "").split(";")[0]
    assert login(client, token=token).status_code == 303


def test_login_cookie_flags(make_client):
    c = make_client(cookie_secure=True)
    ck = c.get("/admin/login").headers["set-cookie"].lower()
    assert "httponly" in ck and "samesite=strict" in ck and "secure" in ck and "path=/admin" in ck


def test_admin_forms_have_small_body_cap(client):
    r = client.post("/admin/login", content="x=" + "a" * 5000, follow_redirects=False,
                    headers={"content-type": "application/x-www-form-urlencoded"})
    assert r.status_code == 413
    assert client.post("/api/submissions", content=b"{}" + b" " * 5000, headers=JSON).status_code != 413  # API keeps 256 KB


def test_throttle_memory_is_bounded():
    t = auth.LoginThrottle(limit=3, max_keys=50)
    for i in range(500):
        t.failure(f"login:{i}")
    assert len(t._fails) + len(t._locked) <= 50 + 1
    assert t.failure("ip:1") is False and t.failure("ip:1") is False and t.failure("ip:1") is True
    assert t.locked_for("ip:1") > 0


def test_lockout_is_audited_once_and_unknown_names_are_not(client):
    make_admin(client)
    for _ in range(12):
        login(client, user="nobody", password="wrong-wrong-wrong")
    acts = audit_actions(client)
    assert "login_failed" not in acts and acts.count("login_throttled") == 1
    assert login(client, user="martin").status_code == 429  # same IP is locked


def test_old_noise_in_audit_log_is_purged_but_history_kept(client):
    uid = make_admin(client)
    old = datetime.now(timezone.utc) - timedelta(days=120)
    with sf(client)() as db:
        db.add_all([AdminAudit(action="login_failed", user_id=uid, at=old), AdminAudit(action="login_ok", user_id=uid, at=old)])
        db.commit()
        assert auth.purge_old_audit(db) == 1
    assert audit_actions(client).count("login_ok") == 1


def test_login_semaphore_limits_concurrent_hashing():
    from app.routes import admin
    assert admin._HASH_SLOTS._value == 2


# ---- own password change ---------------------------------------------------------------------------------------

FORM = {"content-type": "application/x-www-form-urlencoded"}
NEW_PW = "brand new staple 42"


def _csrf(html):
    return html.split('name="csrf" value="')[1].split('"')[0]


def change_pw(client, current=PW, new=NEW_PW, repeat=None, csrf=None):
    csrf = csrf or _csrf(client.get("/admin/password").text)
    from urllib.parse import urlencode
    body = urlencode({"csrf": csrf, "current": current, "new": new, "repeat": new if repeat is None else repeat})
    return client.post("/admin/password", content=body, headers=FORM, follow_redirects=False)


def test_password_page_requires_login(client):
    assert client.get("/admin/password", follow_redirects=False).headers["location"] == "/admin/login"
    r = client.post("/admin/password", content="csrf=x", headers=FORM, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/admin/login"


def test_admin_pages_link_to_password_change(client):
    make_admin(client)
    login(client)
    page = client.get("/admin/password")
    assert page.status_code == 200 and "Смяна на парола" in page.text
    assert page.headers["cache-control"] == "no-store"
    assert 'href="/admin/password"' in client.get("/admin").text


def test_change_password_success_rotates_sessions(make_client):
    a, b = make_client(), None
    make_admin(a)
    login(a)
    # a second browser signed in to the same account
    from fastapi.testclient import TestClient
    b = TestClient(a.app)
    login(b)
    assert b.get("/admin", follow_redirects=False).status_code == 200
    old_cookie = a.cookies.get("mik_admin")
    r = change_pw(a)
    assert r.status_code == 303 and r.headers["location"] == "/admin/password?done=1"
    assert a.cookies.get("mik_admin") != old_cookie
    assert "Паролата е сменена" in a.get("/admin/password?done=1").text
    assert a.get("/admin", follow_redirects=False).status_code == 200  # this browser stays signed in
    assert b.get("/admin", follow_redirects=False).status_code == 303  # the other one is signed out
    a.cookies.clear()
    assert login(a).status_code == 401  # old password no longer works
    assert login(a, password=NEW_PW).status_code == 303
    assert "password_changed" in audit_actions(a)
    with sf(a)() as db:
        assert NEW_PW not in auth.get_by_login(db, "martin").password_hash


@pytest.mark.parametrize("kw,msg,status", [
    ({"current": "wrong password here"}, "Текущата парола е грешна", 401),
    ({"repeat": "something else entirely"}, "не съвпадат", 422),
    ({"new": "short1", "repeat": "short1"}, "поне 12 знака", 422),
    ({"new": "aaaaaaaaaaaaaaaa", "repeat": "aaaaaaaaaaaaaaaa"}, "еднообразна", 422),
    ({"new": PW, "repeat": PW}, "различна от текущата", 422),
])
def test_change_password_rejections_keep_old_password(client, kw, msg, status):
    make_admin(client)
    login(client)
    r = change_pw(client, **kw)
    assert r.status_code == status and msg in r.text
    client.cookies.clear()
    assert login(client).status_code == 303  # unchanged


def test_change_password_needs_session_csrf(client):
    make_admin(client)
    login(client)
    r = change_pw(client, csrf="wrong")
    assert r.status_code == 403
    client.cookies.clear()
    assert login(client).status_code == 303


def test_change_password_cross_site_is_refused(client):
    make_admin(client)
    login(client)
    r = client.post("/admin/password", content="csrf=x&current=a&new=b&repeat=b", follow_redirects=False,
                    headers={**FORM, "origin": "http://evil.example"})
    assert r.status_code == 403


def test_change_password_is_throttled(client):
    make_admin(client)
    login(client)
    for _ in range(5):
        assert change_pw(client, current="wrong password here").status_code == 401
    r = change_pw(client)  # right password is refused while locked
    assert r.status_code == 429
    actions = audit_actions(client)
    assert actions.count("password_change_failed") == 5 and "password_change_throttled" in actions
    assert "password_changed" not in actions
