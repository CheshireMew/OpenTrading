from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from config.settings import AppSettings

TIINGO_TOKEN_ENV = "TIINGO_API_TOKEN"
FRED_KEY_ENV = "FRED_API_KEY"


class ConfigurationError(ValueError):
    """Raised when a command requires configuration that is not available."""


@dataclass(frozen=True, slots=True)
class MarketDataConfig:
    """Market-service values derived from the application's validated settings."""

    data_dir: Path
    tiingo_api_token: str
    fred_api_key: str
    max_managed_bytes: int
    min_free_bytes: int

    @classmethod
    def from_settings(cls, settings: AppSettings) -> MarketDataConfig:
        return cls(
            data_dir=settings.MARKET_DATA_DIR.expanduser().resolve(),
            tiingo_api_token=settings.TIINGO_API_TOKEN,
            fred_api_key=settings.FRED_API_KEY,
            max_managed_bytes=settings.MARKET_DATA_MAX_MANAGED_BYTES,
            min_free_bytes=settings.MARKET_DATA_MIN_FREE_BYTES,
        )

    @classmethod
    def load(cls) -> MarketDataConfig:
        from config import settings

        return cls.from_settings(settings)

    def resolve_data_dir(self, override: Path | None) -> Path:
        """Resolve a command-level data directory override."""

        return (override or self.data_dir).expanduser().resolve()

    def require_tiingo_api_token(self) -> str:
        if not self.tiingo_api_token:
            raise ConfigurationError(f"{TIINGO_TOKEN_ENV} is required; set it in .env or the process environment")
        return self.tiingo_api_token

    def require_fred_api_key(self) -> str:
        if not self.fred_api_key:
            raise ConfigurationError(f"{FRED_KEY_ENV} is required; set it in .env or the process environment")
        return self.fred_api_key
