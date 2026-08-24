from __future__ import annotations

import logging

from app.infra.db import build_database_runtime
from app.infra.db.schema_runtime import prepare_db
from config.settings import settings


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    runtime = build_database_runtime(settings)
    try:
        prepare_db(runtime)
    finally:
        runtime.dispose()


if __name__ == "__main__":
    main()
