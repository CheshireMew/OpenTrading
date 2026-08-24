from app.infra.persistence.market.kline_store import KlineStore
from app.services.market.market_data_service import MarketDataService


class DeterministicExchangeGateway:
    exchange_id = "binance"
    max_task_seconds = 10

    def __init__(self) -> None:
        self.calls = 0

    def fetch_ohlcv(self, symbol, timeframe, since=None, limit=None, max_retries=None):
        self.calls += 1
        rows = [
            [1_700_000_000_000 + index * 3_600_000, 100 + index, 102 + index, 99 + index, 101 + index, 1_000 + index]
            for index in range(limit or 5)
        ]
        return rows, 1

    def sleep_for_rate_limit(self):
        return None


def test_fetch_data_uses_injected_gateway_and_returns_ohlcv(installed_database_runtime):
    gateway = DeterministicExchangeGateway()
    service = MarketDataService(
        exchange_gateway=gateway,
        kline_store=KlineStore(database_runtime=installed_database_runtime),
    )

    data = service.get_kline_data("BTC/USDT", limit=5)

    assert gateway.calls == 1
    assert len(data) == 5
    assert all(len(row) == 6 for row in data)
    assert data[-1][4] == 105
