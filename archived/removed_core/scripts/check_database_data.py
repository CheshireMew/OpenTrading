from __future__ import annotations

from sqlalchemy import inspect, text

from app.infra.db import build_database_runtime
from config.settings import settings


def check_database_data() -> None:
    runtime = build_database_runtime(settings)
    try:
        print(f"[DATA] Checking database: {runtime.database_url}")
        inspector = inspect(runtime.engine)
        tables = [
            table
            for table in inspector.get_table_names()
            if not table.startswith("sqlite_")
        ]
        print(f"[DATA] Found {len(tables)} tables:")

        total_rows = 0
        with runtime.engine.connect() as connection:
            dialect = runtime.engine.dialect.identifier_preparer
            for table in sorted(tables):
                quoted_table = dialect.quote(table)
                count = connection.execute(
                    text(f"SELECT COUNT(*) FROM {quoted_table}")
                ).scalar_one()
                print(f"  - {table}: {count} rows")
                total_rows += int(count)

        print(f"\n[DATA] Total rows across all tables: {total_rows}")
    finally:
        runtime.dispose()


if __name__ == "__main__":
    check_database_data()
