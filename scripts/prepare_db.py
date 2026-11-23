from __future__ import annotations

import logging

from app.infra.db import build_database_runtime
from app.infra.db.schema_runtime import prepare_db
from config.settings import settings


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    runtime = None
    try:
        runtime = build_database_runtime(settings)
        prepare_db(runtime)
        return 0
    except Exception as exc:
        # Driver exceptions may embed the connection URL. Keep diagnostic class,
        # never put the raw exception/traceback in launcher-captured output.
        logging.getLogger(__name__).error("数据库准备失败 (%s)，请核对连接配置及迁移状态", type(exc).__name__)
        return 1
    finally:
        if runtime is not None:
            runtime.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
