from sqlalchemy import text
from app.infra.db import build_database_runtime
from config.settings import settings

runtime = build_database_runtime(settings)

with runtime.engine.connect() as conn:
    # Get unique indicator_id and their latest timestamp
    result = conn.execute(text("""
        SELECT
            indicator_id,
            COUNT(*) as total_records,
            MAX(timestamp) as latest_timestamp,
            MAX(value) as latest_value
        FROM market_indicator_data
        GROUP BY indicator_id
        ORDER BY indicator_id
    """))

    print("\n=== Market Indicators in Database ===\n")
    for row in result:
        print(f"{row.indicator_id:20} | Records: {row.total_records:4} | Latest: {row.latest_timestamp} | Value: {row.latest_value}")
    print()

runtime.dispose()
