"""Report export for the admin panel: Excel (.xlsx), PDF and CSV, all with Bulgarian headings.

Who may download which format is decided in app/routes/admin.py (server side). This module only builds the files.
Spreadsheet formula injection is neutralised in every format: a cell that would start with = + - @ is stored as text.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import QuestionnaireVersion, ReportAttachment, Submission

FONT_DIR = Path(__file__).resolve().parent / "fonts"
MAX_EXPORT_ROWS = 5000  # a single export larger than this must be narrowed with the filters
FIXED_HEADERS = ["Дата на отчета", "Подаден (Европа/София)", "Име и фамилия", "Отдел", "Версия на въпросника",
                 "Брой файлове", "Имена на файловете"]


class ExportTooLarge(Exception):
    pass


@dataclass
class Table:
    headers: list[str]
    rows: list[list[str]]
    filters: str  # human-readable description of the applied filters


def _safe(value: str) -> str:
    """Prefix risky leading characters so Excel/LibreOffice never evaluate a cell as a formula."""
    return "'" + value if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


def _answer_text(qdef: dict, value) -> str:
    if qdef.get("type") == "multi_choice":
        options = {o["code"]: o for o in qdef.get("options", [])}
        selected = (value or {}).get("selected", []) if isinstance(value, dict) else []
        texts = (value or {}).get("texts", {}) if isinstance(value, dict) else {}
        parts = []
        for code in selected:
            label = options.get(code, {}).get("label", code)
            parts.append(f"{label}: {texts[code]}" if texts.get(code) else label)
        return "; ".join(parts)
    return value if isinstance(value, str) else ""


def build_table(db: Session, stmt, tz: str, filters_text: str) -> Table:
    submissions = db.scalars(stmt.order_by(Submission.work_date.desc(), Submission.submitted_at.desc())
                             .limit(MAX_EXPORT_ROWS + 1)).all()
    if len(submissions) > MAX_EXPORT_ROWS:
        raise ExportTooLarge
    definitions: dict[int, dict] = {}
    depts: dict[str, str] = {}
    questions: dict[str, str] = {}  # question id -> newest label, in order of first appearance
    for qv in db.scalars(select(QuestionnaireVersion).order_by(QuestionnaireVersion.version)):
        definitions[qv.version] = qv.definition
        for o in qv.definition.get("departments", {}).get("options", []):
            depts[o["code"]] = o["label"]
        for q in qv.definition.get("questions", []):
            questions[q["id"]] = q["label"]
    files: dict[str, list[str]] = {}
    if submissions:
        ids = [s.id for s in submissions]
        for sid, name in db.execute(select(ReportAttachment.submission_id, ReportAttachment.filename)
                                    .where(ReportAttachment.submission_id.in_(ids))
                                    .order_by(ReportAttachment.filename)):
            files.setdefault(sid, []).append(name)

    zone = ZoneInfo(tz)
    rows = []
    for s in submissions:
        qdefs = {q["id"]: q for q in definitions.get(s.questionnaire_version, {}).get("questions", [])}
        answers = s.answers if isinstance(s.answers, dict) else {}
        submitted = s.submitted_at if s.submitted_at.tzinfo else s.submitted_at.replace(tzinfo=ZoneInfo("UTC"))
        names = files.get(s.id, [])
        rows.append([
            s.work_date.strftime("%d.%m.%Y"), submitted.astimezone(zone).strftime("%d.%m.%Y %H:%M"),
            s.respondent_name or "", depts.get(s.department_code, s.department_code), f"v{s.questionnaire_version}",
            str(len(names)), "; ".join(names),
            *[_answer_text(qdefs[qid], answers.get(qid)) if qid in qdefs else "" for qid in questions],
        ])
    return Table(FIXED_HEADERS + list(questions.values()), rows, filters_text)


# ---- Excel ------------------------------------------------------------------------------------------------------

def to_xlsx(table: Table, generated: str) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Отчети"
    ws.append(table.headers)
    for row in table.rows:
        ws.append(row)
    head_fill = PatternFill("solid", fgColor="14253D")
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = head_fill
        cell.alignment = Alignment(wrap_text=True, vertical="center")
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.data_type = "s"  # always text: never a formula, even if the answer starts with "="
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    for i, header in enumerate(table.headers, start=1):
        longest = max([len(header)] + [len(r[i - 1]) for r in table.rows[:200]])
        ws.column_dimensions[get_column_letter(i)].width = min(60, max(12, longest + 2))
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(table.headers))}{max(1, len(table.rows) + 1)}"  # filterable rows
    info = wb.create_sheet("Информация")
    info.append(["Изготвено", generated])
    info.append(["Филтри", table.filters or "няма (всички отчети)"])
    info.append(["Брой отчети", str(len(table.rows))])
    info.append(["Забележка", "Файл с лични данни на служители. Пазете го само в одобрено фирмено хранилище."])
    info.column_dimensions["A"].width = 16
    info.column_dimensions["B"].width = 90
    for row in info.iter_rows():
        for cell in row:
            cell.data_type = "s"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---- CSV --------------------------------------------------------------------------------------------------------

def to_csv(table: Table) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";", lineterminator="\r\n")  # ';' opens correctly in Bulgarian-locale Excel
    writer.writerow(table.headers)
    for row in table.rows:
        writer.writerow([_safe(cell) for cell in row])
    return b"\xef\xbb\xbf" + out.getvalue().encode("utf-8")  # BOM so Excel reads UTF-8 (Cyrillic) correctly


# ---- PDF --------------------------------------------------------------------------------------------------------

def to_pdf(table: Table, generated: str) -> bytes:
    from fpdf import FPDF

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_font("DejaVu", "", str(FONT_DIR / "DejaVuSans.ttf"))
    pdf.add_font("DejaVu", "B", str(FONT_DIR / "DejaVuSans-Bold.ttf"))
    pdf.set_title("Отчети - MIK | Process Insights")
    pdf.add_page()
    pdf.set_font("DejaVu", "B", 16)
    pdf.cell(0, 9, "Дневни отчети - MIK | Process Insights", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("DejaVu", "", 9)
    pdf.multi_cell(0, 5, f"Изготвено: {generated}\nФилтри: {table.filters or 'няма (всички отчети)'}\n"
                         f"Брой отчети: {len(table.rows)}\nСъдържа лични данни на служители - пазете само в одобрено хранилище.",
                   new_x="LMARGIN", new_y="NEXT")
    answer_headers = table.headers[len(FIXED_HEADERS):]
    for n, row in enumerate(table.rows, start=1):
        if n > 1:
            pdf.add_page()
        else:
            pdf.ln(4)
        pdf.set_font("DejaVu", "B", 12)
        pdf.multi_cell(0, 7, f"{n}. {row[2] or '(без име)'} - {row[3]}", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("DejaVu", "", 9)
        pdf.multi_cell(0, 5, f"Дата на отчета: {row[0]}    Подаден: {row[1]}    Версия: {row[4]}",
                       new_x="LMARGIN", new_y="NEXT")
        if row[5] != "0":
            pdf.multi_cell(0, 5, f"Файлове ({row[5]}): {row[6]}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
        for header, value in zip(answer_headers, row[len(FIXED_HEADERS):]):
            if not value:
                continue
            pdf.set_font("DejaVu", "B", 10)
            pdf.multi_cell(0, 5.5, header, new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("DejaVu", "", 10)
            pdf.multi_cell(0, 5.5, value, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1.5)
    return bytes(pdf.output())
