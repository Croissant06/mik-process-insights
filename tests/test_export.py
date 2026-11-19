"""Report export (Excel/PDF for all four admins, CSV only for accounts granted it) and per-account permission."""
import base64
import io

import pytest
from openpyxl import load_workbook
from sqlalchemy import select

from app import admin_auth as auth
from app import report_export
from app.models import AdminAudit, AdminUser
from tests.test_admin import PW, audit_actions, login, sf
from tests.test_attachments import with_file
from tests.conftest import write_version

# Synthetic test logins. In real use the CSV flag is granted with `scripts/admin_users.py allow-csv`.
ADMINS = {"presiyan": True, "martin": True, "rosica": False, "miglena": False}


@pytest.fixture
def four_admins(client):
    with sf(client)() as db:
        for lg, csv_ok in ADMINS.items():
            auth.create_admin(db, lg, lg.capitalize(), PW, can_export_csv=csv_ok)
    return client


def sign_in(client, login_name):
    client.cookies.clear()
    assert login(client, user=login_name).status_code == 303


def submit(client, valid_payload, **over):
    p = valid_payload(client)
    p.update(over)
    r = client.post("/api/submissions", json=p)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _seed(client, valid_payload):
    submit(client, valid_payload, respondent_name="Иван Тестов")
    submit(client, valid_payload, respondent_name="=HYPERLINK(\"http://evil\")")


@pytest.mark.parametrize("who", list(ADMINS))
def test_every_admin_can_download_excel_and_pdf(four_admins, valid_payload, who):
    c = four_admins
    _seed(c, valid_payload)
    sign_in(c, who)
    x = c.get("/admin/export/xlsx")
    assert x.status_code == 200 and "spreadsheetml" in x.headers["content-type"]
    assert x.headers["content-disposition"].startswith('attachment; filename="otcheti-')
    assert x.headers["cache-control"] == "no-store"
    ws = load_workbook(io.BytesIO(x.content))["Отчети"]
    assert [c_.value for c_ in ws[1]][:5] == ["Дата на отчета", "Подаден (Европа/София)", "Име и фамилия", "Отдел",
                                               "Версия на въпросника"]
    assert ws.auto_filter.ref and ws.auto_filter.ref.startswith("A1:") and ws.max_row == 3 and ws.freeze_panes == "A2"
    names = {ws.cell(row=r, column=3).value for r in (2, 3)}
    assert "Иван Тестов" in names
    risky = next(n for n in names if n.startswith("="))
    cell = next(c_ for c_ in ws["C"] if c_.value == risky)
    assert cell.data_type == "s"  # stored as text, never evaluated as a formula
    p = c.get("/admin/export/pdf")
    assert p.status_code == 200 and p.content.startswith(b"%PDF") and p.headers["content-type"] == "application/pdf"
    assert len(p.content) > 2000


@pytest.mark.parametrize("who,allowed", list(ADMINS.items()))
def test_csv_is_enforced_per_account_on_the_server(four_admins, valid_payload, who, allowed):
    c = four_admins
    _seed(c, valid_payload)
    sign_in(c, who)
    r = c.get("/admin/export/csv")
    if allowed:
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
        assert r.content.startswith(b"\xef\xbb\xbf") and "Иван Тестов".encode() in r.content
        assert b"'=HYPERLINK" in r.content  # formula neutralised
        assert "export_csv" in audit_actions(c)
    else:
        assert r.status_code == 403 and "CSV" in r.text and "Иван" not in r.text
        assert "export_csv_denied" in audit_actions(c)
        assert 'href="/admin/export/csv' not in c.get("/admin").text  # no button for them
    assert (f'href="/admin/export/csv' in c.get("/admin").text) is allowed


def test_exports_need_login_and_unknown_kind_is_404(four_admins):
    c = four_admins
    for kind in ("xlsx", "pdf", "csv"):
        assert c.get(f"/admin/export/{kind}", follow_redirects=False).status_code == 303
    sign_in(c, "martin")
    assert c.get("/admin/export/docx").status_code == 404


def test_permission_cannot_be_self_granted_by_query_or_form(four_admins, valid_payload):
    c = four_admins
    sign_in(c, "rosica")
    for url in ("/admin/export/csv?csv=1&can_export_csv=1&admin=1", "/admin/export/csv?user=martin"):
        assert c.get(url).status_code == 403
    with sf(c)() as db:
        assert auth.get_by_login(db, "rosica").can_export_csv is False


def test_export_follows_filters_and_is_audited(four_admins, valid_payload):
    c = four_admins
    submit(c, valid_payload, respondent_name="Първи", work_date="2026-11-10")
    submit(c, valid_payload, respondent_name="Втори", work_date="2026-11-12")
    sign_in(c, "martin")
    ws = load_workbook(io.BytesIO(c.get("/admin/export/xlsx?from=2026-11-11").content))["Отчети"]
    assert ws.max_row == 2 and ws["C2"].value == "Втори"
    info = load_workbook(io.BytesIO(c.get("/admin/export/xlsx?from=2026-11-11").content))["Информация"]
    assert "от=11.11.2026" in info["B2"].value
    with sf(c)() as db:
        detail = [a.detail for a in db.scalars(select(AdminAudit).where(AdminAudit.action == "export_xlsx"))]
    assert detail and detail[0].startswith("n=1") and "Втори" not in detail[0]  # audit never stores names/answers


def test_export_lists_attachment_names_not_bytes(qdir, make_client, valid_payload):
    write_version(qdir, 2, lambda d: d.update(attachments=True))
    c = make_client()
    with sf(c)() as db:
        auth.create_admin(db, "martin", "Мартин", PW)
    r = c.post("/api/submissions/with-attachments", json=with_file(c, valid_payload))
    assert r.status_code == 201
    assert login(c).status_code == 303
    ws = load_workbook(io.BytesIO(c.get("/admin/export/xlsx").content))["Отчети"]
    assert ws["F2"].value == "1" and ws["G2"].value == "Инструкция.txt"


def test_pdf_survives_long_unbroken_text(four_admins, valid_payload):
    c = four_admins
    submit(c, valid_payload, respondent_name="Дълго Име", answers={**valid_payload(c)["answers"], "tasks": "А" * 1900})
    sign_in(c, "rosica")
    assert c.get("/admin/export/pdf").content.startswith(b"%PDF")


def test_too_large_export_is_refused(four_admins, valid_payload, monkeypatch):
    c = four_admins
    _seed(c, valid_payload)
    monkeypatch.setattr(report_export, "MAX_EXPORT_ROWS", 1)
    sign_in(c, "martin")
    assert c.get("/admin/export/xlsx").status_code == 413


def test_new_accounts_default_to_no_csv(client):
    with sf(client)() as db:
        auth.create_admin(db, "someone", "Някой", PW)
        assert db.scalar(select(AdminUser.can_export_csv).where(AdminUser.login == "someone")) is False
