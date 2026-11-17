"""Generate docs/business/QUESTIONNAIRE_BG.md (Bulgarian, for management) from the questionnaire YAML.

    python scripts/generate_questionnaire_doc.py            # latest version -> docs/business/QUESTIONNAIRE_BG.md
    python scripts/generate_questionnaire_doc.py --check    # exit 1 if the committed file is out of date

Edit the YAML (as a new version), not the generated file.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import questionnaire  # noqa: E402

OUT = ROOT / "docs" / "business" / "QUESTIONNAIRE_BG.md"

TYPE_BG = {"text": "кратък текст", "textarea": "свободен текст", "multi_choice": "избор от списък, възможни са няколко отговора"}


def render(d: dict) -> str:
    name = d["respondent"]["name"]
    lines = [
        "# Дневник на работните дейности – предложен въпросник",
        "",
        f"> **Статус: ЧЕРНОВА, чака одобрение от ръководството.** Версия на въпросника: {d['version']}. "
        "Този документ се генерира автоматично от конфигурацията на платформата "
        "(`questionnaire/daily_report.v%d.yaml`) и винаги съответства на това, което служителите ще виждат." % d["version"],
        "",
        "## 1. Накратко за инициативата",
        "",
        "**MIK | Process Insights** е малък вътрешен уебсайт, в който служителите отделят около "
        f"{d.get('estimated_minutes', 5)} минути в края на работния ден, за да опишат **свои думи** какво са работили, "
        "кои дейности се повтарят и отнемат време и с какви затруднения са се сблъскали.",
        "",
        "**Защо:** за да разберем реалната картина на ежедневната работа – кои дейности отнемат най-много време, "
        "къде се дублира информация и къде се изчакват данни, решения или одобрение – преди да предлагаме каквато и да е автоматизация.",
        "",
        "**Какво това не е:** не е оценка на представянето на служителите и не е система за контрол. "
        "Целта е да се подобрят процесите, а не да се оценяват хора.",
        "",
        "**Три източника на информация (според решението на ръководството):** дневните отчети на служителите, "
        "кратки разговори с ключови служители и проследяване на реална производствена поръчка. "
        "Резултатът е предварителен анализ и практически план за действие, а не само уебсайт.",
        "",
        "## 2. Предложен въпросник",
        "",
        "Попълва се за един работен ден, на български език, в свободен текст с малко структура. Работната дата по подразбиране е днешната.",
        "",
        "### Данни за попълващия",
        "",
        "| Поле | Задължително | Забележка |",
        "|---|---|---|",
        f"| {name['label']} | {'да' if name.get('required', True) else 'не'} | "
        "Дали името да е задължително, е за решение от ръководството (може да се смени чрез настройка). |",
        f"| {d['respondent']['department']['label']} | {'да' if d['respondent']['department'].get('required', True) else 'не'} | Избор от списък (виж т. 3). |",
        "| Дата на отчета | да | Календар; по подразбиране днешната дата; бъдещи дати не се допускат. |",
        "",
    ]
    section = None
    n = 0
    for q in d["questions"]:
        if q.get("section") and q["section"] != section:
            section = q["section"]
            lines += [f"### {section}", ""]
        n += 1
        req = "задължителен" if q.get("required") else "по желание"
        lines.append(f"**{n}. {q['label']}** _({req}; {TYPE_BG[q['type']]})_")
        if q.get("help"):
            lines.append(f"  \n_Пояснение към служителя: {q['help']}_")
        lines.append("")
        if q["type"] == "multi_choice":
            for o in q["options"]:
                extra = ""
                if o.get("allows_text"):
                    extra = " – с поле за кратко уточнение"
                if o.get("exclusive"):
                    extra = " – не се комбинира с другите отговори"
                lines.append(f"- {o['label']}{extra}")
            lines.append("")
    lines += [
        "## 3. Отдели",
        "",
    ]
    if d["departments"].get("placeholder"):
        lines += ["> **Списъкът по-долу е примерен.** Действителните отдели трябва да бъдат уточнени с ръководството.", ""]
    lines += [f"- {o['label']}" for o in d["departments"]["options"]] + [""]
    lines += [
        "## 4. Предложен списък с участници (за попълване)",
        "",
        "Преди старта ръководството ще получи въпросника и предложения списък с участници. "
        "Таблицата по-долу е **празен шаблон** – не съдържа предположения за конкретни хора.",
        "",
        "| № | Име / длъжност | Отдел | Причина за участие | Метод (дневник / разговор / и двете) | Потвърдено от |",
        "|---|---|---|---|---|---|",
        "| 1 | | | | | |",
        "| 2 | | | | | |",
        "| 3 | | | | | |",
        "| 4 | | | | | |",
        "| 5 | | | | | |",
        "",
        "_Съвет при избора:_ добре е да са покрити всички отдели, през които минава една поръчка, "
        "и да се включат хора, които имат пряк поглед върху ежедневната работа. Кой реално има достъп до устройство за попълване – да се уточни.",
        "",
        "## 5. За решение от ръководството",
        "",
        "- [ ] Одобрение на въпросите (или бележки за промени).",
        "- [ ] Окончателен списък с отдели и участници.",
        "- [ ] Задължително ли е името (или анонимно попълване)?",
        "- [ ] Текст на уведомлението към служителите (виж `EMPLOYEE_NOTICE_BG.md`).",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    d = questionnaire.load_directory(ROOT / "questionnaire")
    text = render(d[max(d)])
    if args.check:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
            sys.exit("docs/business/QUESTIONNAIRE_BG.md is out of date - run scripts/generate_questionnaire_doc.py")
        return
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} (questionnaire v{max(d)})")


if __name__ == "__main__":
    main()
