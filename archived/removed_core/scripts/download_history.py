import sys
from datetime import datetime

from app.runtime_builder import build_app_runtime_services
from app.runtime_refs import INFRA_DATABASE_RUNTIME, MARKET_MARKET_DATA_SERVICE
from utils.logger import logger


def download_history(symbol, timeframe, start_year=None):
    runtime_services = build_app_runtime_services("api")
    provider = runtime_services.require_service(MARKET_MARKET_DATA_SERVICE)

    end_date = datetime.now()
    start_date = datetime(year=start_year or 2017, month=1, day=1)

    print(f"[START] Downloading history: {symbol} {timeframe}")
    print(f"[DATE] Range: {start_date} -> {end_date}")

    try:
        result = provider.load_ohlcv_range(symbol, timeframe, start_date, end_date)
        data = result.rows

        if data:
            print(f"[OK] Downloaded {len(data)} candles")
            print(
                "[DATA] Actual coverage: "
                f"{datetime.fromtimestamp(data[0][0] / 1000)} -> "
                f"{datetime.fromtimestamp(data[-1][0] / 1000)}"
            )
            if not result.complete:
                print(f"[WARN] Incomplete coverage: {result.missing_ranges}")
        else:
            print("[ERROR] No data returned")
    except Exception as exc:
        print(f"[ERROR] Download failed: {exc}")
        logger.error(f"History download failed: {exc}")
    finally:
        database_runtime = runtime_services.get_service(INFRA_DATABASE_RUNTIME)
        if database_runtime is not None:
            database_runtime.dispose()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python download_history.py <SYMBOL> <TIMEFRAME> [START_YEAR]")
        print("Example: python download_history.py BTC/USDT 5m 2020")
        print("Example: python download_history.py BTC/USDT 5m")
        sys.exit(1)

    symbol = sys.argv[1]
    timeframe = sys.argv[2]
    start_year = int(sys.argv[3]) if len(sys.argv) > 3 else 2017

    download_history(symbol, timeframe, start_year)
