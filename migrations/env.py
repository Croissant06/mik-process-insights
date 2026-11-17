from alembic import context

from app.config import Settings
from app.db import Base, make_engine
import app.models  # noqa: F401

target_metadata = Base.metadata


def run_migrations_online() -> None:
    engine = make_engine(Settings.from_env().database_url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
