"""Insert SYNTHETIC submissions for local development. Never use real data.

    python scripts/seed_synthetic.py --count 30
"""
import argparse
import random
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import questionnaire  # noqa: E402
from app.config import Settings  # noqa: E402
from app.db import make_engine, make_session_factory  # noqa: E402
from app.models import Submission  # noqa: E402

TASKS = ["Синтетична задача А", "Синтетична задача Б", "Тестово описание на дейност"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=30)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    settings = Settings.from_env()
    if "prod" in settings.database_url.lower():
        sys.exit("Refusing to seed a database whose URL contains 'prod'.")
    session = make_session_factory(make_engine(settings.database_url))()
    questionnaire.sync_versions(session, settings.questionnaire_dir)
    d = questionnaire.get_active(session, settings.active_questionnaire_version)
    depts = [o["code"] for o in d["departments"]["options"]]
    obstacle_q = next(q for q in d["questions"] if q["type"] == "multi_choice")
    codes = [o["code"] for o in obstacle_q["options"] if not o.get("exclusive") and not o.get("allows_text")]
    for i in range(args.count):
        picked = [] if rng.random() < .2 else rng.sample(codes, rng.randint(1, 2))
        answers = {
            "tasks": rng.choice(TASKS), "recurring": f"{rng.choice(TASKS)}, ~{rng.choice([15, 30, 60])} мин.",
            obstacle_q["id"]: {"selected": picked or ["none"], "texts": {}},
            "obstacles_detail": "", "suggestions": "",
        }
        session.add(Submission(
            questionnaire_version=d["version"], work_date=date.today() - timedelta(days=rng.randint(0, 4)),
            submitted_at=datetime.now(timezone.utc), respondent_name=f"Тест Потребител {i + 1:02d} (синтетичен)",
            department_code=rng.choice(depts), answers=answers,
        ))
    session.commit()
    print(f"Inserted {args.count} synthetic submissions.")


if __name__ == "__main__":
    main()
