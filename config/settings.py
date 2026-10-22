from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"


def _default_runtime_root() -> Path:
    return BASE_DIR / ".opentrading_runtime"


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    EXCHANGE_ID: str = "binance"
    SYMBOLS: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["BTC/USDT", "ETH/USDT", "SOL/USDT", "DOGE/USDT"]
    )
    TIMEFRAME: str = "1h"
    LIMIT: int = 1000

    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    AI_MODEL: str = "deepseek-chat"

    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str = ""
    REDIS_CONNECT_TIMEOUT: float = 0.5
    REDIS_SOCKET_TIMEOUT: float = 1.0
    REDIS_RETRY_INTERVAL: float = 30.0
    CACHE_MEMORY_MAX_ENTRIES: int = 512
    CACHE_MEMORY_MAX_BYTES: int = 64 * 1024 * 1024
    CACHE_MEMORY_DEFAULT_TTL: int = 120

    DATABASE_URL: str = ""
    DATABASE_CONNECT_TIMEOUT: int = 3

    EMA_PERIOD: int = 20
    RSI_PERIOD: int = 14
    MACD_FAST: int = 12
    MACD_SLOW: int = 26
    MACD_SIGNAL: int = 9

    CORS_ORIGINS: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "http://localhost:4173",
            "http://127.0.0.1:4173",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ]
    )

    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    FRONTEND_DEV_PORT: int = 4173
    APP_RUNTIME_ROLE: str = "api"

    RATE_LIMIT_DEFAULT: str = "60/minute"
    RATE_LIMIT_HEAVY: str = "10/minute"
    RATE_LIMIT_HISTORY: str = "60/minute"

    EXCHANGE_MAX_RETRIES: int = 3
    EXCHANGE_RETRY_DELAY: int = 2
    EXCHANGE_REQUEST_TIMEOUT_MS: int = 5000
    EXCHANGE_TAIL_MAX_RETRIES: int = 1
    EXCHANGE_TASK_TIMEOUT: int = 90
    EXCHANGE_FETCH_LIMIT: int = 1000
    KLINE_UPSERT_BATCH_SIZE: int = 1000

    REDIS_KLINE_TTL: int = 300
    WS_UPDATE_INTERVAL: int = 5

    API_MAX_LIMIT: int = 2000
    FULL_HISTORY_MAX_POINTS: int = 10000
    HISTORY_BATCH_MAX_SYMBOLS: int = 10
    HISTORY_BATCH_CONCURRENCY: int = 4
    PRICE_BATCH_MAX_SYMBOLS: int = 50
    PRICE_BATCH_CONCURRENCY: int = 8
    HISTORY_DEFAULT_LIMIT: int = 500
    INDICATORS_DEFAULT_DAYS: int = 30

    DCA_INDICATOR_BUFFER_DAYS: int = 200
    DCA_MA_PERIOD: int = 200
    DCA_DEFAULT_MULTIPLIER: float = 3.0
    DCA_MULTIPLIER_MIN: float = 0.01
    DCA_MULTIPLIER_MAX: float = 100.0
    DCA_VA_MAX_MULTIPLE: int = 10
    DCA_STANDARD_MAX_MULTIPLE: int = 5
    DCA_COIN_PRECISION: float = 1e-8
    DCA_CACHE_TTL: int = 600
    PORTFOLIO_CHANGE_MAX_BYTES: int = 6 * 1024 * 1024
    PORTFOLIO_SIMULATION_MAX_BYTES: int = 4 * 1024 * 1024
    PORTFOLIO_IMPORT_MAX_BYTES: int = 128 * 1024 * 1024
    PORTFOLIO_TRANSACTION_IMPORT_MAX_BYTES: int = 32 * 1024 * 1024

    PAIR_COMPARE_BASE_TIMEFRAME: str = "5m"

    BTC_GENESIS_DATE: str = "2009-01-03"
    BTC_EARLY_HISTORY_CUTOFF_TS: int = 1502928000000
    BTC_SYNTHETIC_HISTORY_CUTOFF_TS: int = 1313625600000
    AHR999_COEFF_A: float = 5.84
    AHR999_COEFF_B: float = 17.01

    LLM_TEMPERATURE: float = 0.1
    LLM_REQUEST_TIMEOUT: float = 30.0
    LLM_RESPONSE_MAX_BYTES: int = 131_072
    LLM_TRACE_CONTENT: bool = False

    MARKET_CRON_INTERVAL_HOURS: int = 4
    BACKGROUND_HEARTBEAT_INTERVAL_SECONDS: int = 10
    BACKGROUND_HEARTBEAT_STALE_SECONDS: int = 45
    MARKET_EXPENSIVE_INDICATOR_TTL: int = 86400

    SENTIMENT_API_URL: str = "https://api.alternative.me/fng/"
    MEMPOOL_API_URL: str = "https://mempool.space/api/v1/mining/hashrate/3d"
    STABLECOIN_CHART_API_URL: str = "https://stablecoins.llama.fi/stablecoincharts/all"
    STABLECOIN_LIST_API_URL: str = "https://stablecoins.llama.fi/stablecoins?includePrices=false"
    BINANCE_PUBLIC_BASE_URL: str = "https://api.binance.com"
    BINANCE_FUTURES_USDM_BASE_URL: str = "https://fapi.binance.com"
    BINANCE_WEB3_BASE_URL: str = "https://web3.binance.com"
    BINANCE_WEB3_KLINE_BASE_URL: str = "https://dquery.sintral.io"
    BINANCE_PUBLIC_TIMEOUT: float = 20.0
    BINANCE_PUBLIC_CACHE_TTL: int = 120
    BINANCE_PUBLIC_MAX_RETRIES: int = 2
    BINANCE_PUBLIC_RETRY_DELAY: float = 1.0
    BINANCE_PUBLIC_MAX_CONNECTIONS: int = 32
    BINANCE_PUBLIC_MAX_KEEPALIVE_CONNECTIONS: int = 16
    BINANCE_SPOT_WS_URL: str = "wss://stream.binance.com:9443/ws/!ticker@arr"
    BINANCE_FUTURES_USDM_TICKER_WS_URL: str = "wss://fstream.binance.com/ws/!ticker@arr"
    BINANCE_FUTURES_USDM_MARK_WS_URL: str = "wss://fstream.binance.com/ws/!markPrice@arr"
    BINANCE_MARKET_SNAPSHOT_RECONNECT_DELAY: float = 3.0
    BINANCE_MARKET_PAGE_REFRESH_INTERVAL: float = 60.0
    RESEARCH_ALERT_INTERVAL_SECONDS: int = 60
    TRADE_SIGNAL_EVALUATION_INTERVAL_SECONDS: int = 300
    BINANCE_MARKET_PAGE_MAX_CONFIGS: int = 8
    BINANCE_MARKET_PAGE_CONFIG_TTL: float = 600.0
    BINANCE_BREAKOUT_MAX_CONCURRENCY: int = 8
    BINANCE_CONTRACT_OI_CANDIDATE_LIMIT: int = 30
    INDEX_HISTORY_REQUEST_TIMEOUT: int = 15

    CURRENCY_RATES_URL: str = "https://open.er-api.com/v6/latest/USD"
    CURRENCY_RATES_TIMEOUT: float = 5.0
    CURRENCY_RATES_TTL: int = 3600
    DISPLAY_CURRENCIES: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["USD", "CNY", "EUR", "GBP", "JPY", "HKD", "SGD", "AUD"]
    )

    MINING_ELECTRICITY_COST_KWH: float = 0.08
    BTC_BLOCK_REWARD: float = 3.125
    BTC_BLOCKS_PER_DAY: int = 144
    MINER_EFFICIENCY_JTH: dict[str, float] = Field(
        default_factory=lambda: {"S19 Pro": 29.5, "S21": 17.5, "S23": 10.0}
    )

    LOG_LEVEL: str = "INFO"

    KLINE_RETENTION_DAYS: int = 365
    KLINE_RETENTION_BATCH_SIZE: int = 5000

    RUNTIME_ROOT_DIR: Path = Field(default_factory=_default_runtime_root)
    LOG_DIR: Path = Field(default_factory=lambda: _default_runtime_root() / "logs")
    TEMP_DIR: Path = Field(default_factory=lambda: _default_runtime_root() / "tmp")
    BACKGROUND_RUNTIME_LOCK_PATH: Path = Field(default_factory=lambda: _default_runtime_root() / "runtime" / "background.lock")
    LLM_CONFIG_PATH: Path = Field(default_factory=lambda: _default_runtime_root() / "config" / "llm_provider_config.json")
    BLOCKING_DATABASE_MAX_WORKERS: int = 8
    BLOCKING_COMPUTE_MAX_WORKERS: int = 2
    BLOCKING_EXTERNAL_IO_MAX_WORKERS: int = 8
    BLOCKING_BACKGROUND_MAX_WORKERS: int = 4
    BLOCKING_TOOL_MAX_WORKERS: int = 4

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("SYMBOLS", mode="before")
    @classmethod
    def parse_symbols(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            return [symbol.strip() for symbol in value.split(",") if symbol.strip()]
        return value

    @field_validator("DISPLAY_CURRENCIES", mode="before")
    @classmethod
    def parse_display_currencies(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            return [currency.strip().upper() for currency in value.split(",") if currency.strip()]
        return value

    @field_validator("APP_RUNTIME_ROLE", mode="before")
    @classmethod
    def parse_app_runtime_role(cls, value: Any) -> str:
        normalized = str(value or "all").strip().lower()
        if normalized not in {"all", "api", "background"}:
            raise ValueError("APP_RUNTIME_ROLE 只支持 all、api、background")
        return normalized


settings = AppSettings()

__all__ = ["AppSettings", "settings", "BASE_DIR", "DATA_DIR"]
