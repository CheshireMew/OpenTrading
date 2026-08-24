from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path

from config import settings
from utils.logger import logger


class FreqtradeProcessRunner:
    def __init__(self, *, strategy_class_name: str) -> None:
        self.strategy_class_name = strategy_class_name

    def run_backtest(
        self,
        *,
        run_root: Path,
        config_path: Path,
        user_data_dir: Path,
        strategies_dir: Path,
        data_dir: Path,
        results_dir: Path,
        execution_symbols: list[str],
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
        fee_ratio: float,
        label: str,
    ) -> None:
        command = [
            sys.executable,
            "-m",
            "freqtrade",
            "backtesting",
            "--config",
            str(config_path),
            "--userdir",
            str(user_data_dir),
            "--strategy-path",
            str(strategies_dir),
            "--strategy",
            self.strategy_class_name,
            "--datadir",
            str(data_dir),
            "--timeframe",
            timeframe,
            "--timerange",
            self._build_timerange(start_date, end_date),
            "--data-format-ohlcv",
            "json",
            "--cache",
            "none",
            "--export",
            "trades",
            "--backtest-directory",
            str(results_dir),
            "--fee",
            str(fee_ratio),
            "--pairs",
            *execution_symbols,
            "--no-color",
        ]
        logger.info(
            f"启动 Freqtrade 回测: label={label}, pairs={','.join(execution_symbols)}, tf={timeframe}, "
            f"range={start_date.isoformat()}->{end_date.isoformat()}"
        )
        try:
            completed = subprocess.run(
                command,
                cwd=run_root,
                capture_output=True,
                text=True,
                timeout=settings.FREQTRADE_BACKTEST_TIMEOUT_SECONDS,
                check=True,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"Freqtrade 回测超时，当前超时阈值为 {settings.FREQTRADE_BACKTEST_TIMEOUT_SECONDS} 秒。"
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(self._format_process_error(exc.stdout, exc.stderr)) from exc

        if completed.stdout:
            logger.debug(completed.stdout.strip())
        if completed.stderr:
            logger.debug(completed.stderr.strip())

    @staticmethod
    def _build_timerange(start_date: datetime, end_date: datetime) -> str:
        return f"{int(start_date.timestamp() * 1000)}-{int(end_date.timestamp() * 1000)}"

    @staticmethod
    def _format_process_error(stdout: str, stderr: str) -> str:
        output = (stderr or stdout or "").strip()
        if not output:
            return "Freqtrade 回测执行失败"
        return "Freqtrade 回测执行失败。\n" + "\n".join(output.splitlines()[-20:])
