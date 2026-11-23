from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import dotenv_values

from signal_lab.storage.paths import default_data_dir


DATA_DIR_ENV = "SIGNAL_LAB_DATA_DIR"
TIINGO_TOKEN_ENV = "TIINGO_API_TOKEN"
FRED_KEY_ENV = "FRED_API_KEY"
MAX_MANAGED_BYTES_ENV = "SIGNAL_LAB_MAX_MANAGED_BYTES"
MIN_FREE_BYTES_ENV = "SIGNAL_LAB_MIN_FREE_BYTES"
DEFAULT_MAX_MANAGED_BYTES = 50 * 1024**3
DEFAULT_MIN_FREE_BYTES = 5 * 1024**3


class ConfigurationError(ValueError):
    """Raised when a command requires configuration that is not available."""


@dataclass(frozen=True, slots=True)
class SignalLabConfig:
    """Validated runtime configuration loaded from one canonical boundary."""

    data_dir: Path
    tiingo_api_token: str = ""
    fred_api_key: str = ""
    max_managed_bytes: int = DEFAULT_MAX_MANAGED_BYTES
    min_free_bytes: int = DEFAULT_MIN_FREE_BYTES

    @classmethod
    def load(
        cls,
        *,
        environ: Mapping[str, str] | None = None,
        dotenv_path: Path | None = None,
        fallback_data_dir: Path | None = None,
    ) -> SignalLabConfig:
        """Load process environment over an optional ``.env`` file.

        Process environment values have priority over file values. Loading is
        side-effect free: the process environment is never mutated.
        """

        process_values = dict(os.environ if environ is None else environ)
        from config.settings import BASE_DIR

        source = (dotenv_path or (BASE_DIR / ".env")).expanduser()
        file_values = dotenv_values(source) if source.is_file() else {}

        def value(name: str) -> str:
            raw = process_values[name] if name in process_values else file_values.get(name, "")
            return str(raw or "").strip()

        def byte_budget(name: str, default: int) -> int:
            raw = value(name)
            if not raw:
                return default
            try:
                parsed = int(raw)
            except ValueError as exc:
                raise ConfigurationError(f"{name} must be a positive integer byte count") from exc
            if parsed < 1:
                raise ConfigurationError(f"{name} must be a positive integer byte count")
            return parsed

        configured_data_dir = value(DATA_DIR_ENV)
        resolved_data_dir = (
            Path(configured_data_dir).expanduser().resolve()
            if configured_data_dir
            else (fallback_data_dir or default_data_dir()).expanduser().resolve()
        )
        return cls(
            data_dir=resolved_data_dir,
            tiingo_api_token=value(TIINGO_TOKEN_ENV),
            fred_api_key=value(FRED_KEY_ENV),
            max_managed_bytes=byte_budget(MAX_MANAGED_BYTES_ENV, DEFAULT_MAX_MANAGED_BYTES),
            min_free_bytes=byte_budget(MIN_FREE_BYTES_ENV, DEFAULT_MIN_FREE_BYTES),
        )

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
