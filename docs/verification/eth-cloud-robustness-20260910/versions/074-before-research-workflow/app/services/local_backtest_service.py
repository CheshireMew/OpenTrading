from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.contracts.local_backtest import LocalBacktestCommand
from app.domain.local_backtest import DISCLAIMER
from app.infra.persistence.local_backtest_repository import LocalBacktestRepository, ACTIVE, TERMINAL
from app.services.local_backtest_strategies import (
    STRATEGIES_DIR, digest, environment, inspect_strategy, strategy_path, validate_parameters,
)
from app.services.market.symbol_catalog import get_market_symbol_source, get_supported_crypto_symbols
from app.services.market.exchange_gateway import ExchangeGateway
from app.domain.market.constants import timeframe_to_milliseconds
from config import settings

TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]
KINDS = {"trades", "signals", "fills", "equity", "levels", "candles", "indicators"}


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")), encoding="utf-8")


class LocalBacktestService:
    def __init__(self, database, root=None):
        self.repository = LocalBacktestRepository(database)
        self.root = Path(root or settings.RUNTIME_ROOT_DIR / "local_backtests")

    def directory(self, identifier):
        # Resolve only identifiers already present in the database.
        self.repository.get(identifier)
        return self.root / identifier

    def catalog(self):
        entries = []
        for path in sorted(STRATEGIES_DIR.glob("*.py")):
            try:
                metadata = inspect_strategy(path.read_bytes(), path.name)
                if metadata.id != path.stem:
                    raise ValueError("策略标识必须与文件名一致")
                entries.append(metadata.model_dump())
            except Exception as exc:
                entries.append(dict(id=path.stem, name=path.stem, description="策略加载失败", api_version="1",
                                    warmup_bars=0, parameters={}, error=str(exc)))
        symbols = get_supported_crypto_symbols()
        frames = {}
        for symbol in symbols:
            source = get_market_symbol_source(symbol)
            supported = ExchangeGateway(source.exchange_id).exchange.timeframes or {}
            frames[symbol] = [t for t in TIMEFRAMES if t in supported]
        return {"strategies": entries, "symbols": symbols, "timeframes": frames}

    def create(self, command: LocalBacktestCommand):
        path = strategy_path(command.strategy)
        source_bytes = path.read_bytes()
        metadata = inspect_strategy(source_bytes, path.name)
        if metadata.id != command.strategy:
            raise ValueError("策略标识与文件名不一致")
        values = validate_parameters(metadata, command.parameters)
        source = get_market_symbol_source(command.symbol)
        if source is None or ":" in command.symbol:
            raise ValueError("仅支持现有目录中的加密货币现货交易对")
        supported = ExchangeGateway(source.exchange_id).exchange.timeframes or {}
        if command.timeframe not in supported:
            raise ValueError("数据源不支持该周期")
        step = timeframe_to_milliseconds(command.timeframe)
        start, end = int(command.start.timestamp() * 1000), int(command.end.timestamp() * 1000)
        if start % step or end % step or command.start.microsecond or command.end.microsecond:
            raise ValueError("起止时间必须对齐所选周期")
        if end > int(datetime.now(timezone.utc).timestamp() * 1000):
            raise ValueError("不能包含未收盘 K 线，请调整结束时间")
        config = command.model_dump(mode="json")
        config.update(parameters=values, symbol=source.symbol)
        return self._create(config, source_bytes, {
            "strategy": metadata.model_dump(), "environment": environment(), "source": {
                "exchange": source.exchange_id, "symbol": source.symbol, "storage_symbol": source.storage_symbol,
                "price_type": "spot"}, "disclaimer": DISCLAIMER,
        })

    def _create(self, config, source, metadata, parent_id=None, data=None):
        identifier = uuid4().hex
        folder = self.root / identifier
        folder.mkdir(parents=True, exist_ok=False)
        (folder / "strategy.py").write_bytes(source)
        metadata = {**metadata, "strategy_hash": digest(source)}
        if data is not None:
            (folder / "data.json").write_bytes(data)
        write_json(folder / "config.json", config)
        write_json(folder / "metadata.json", metadata)
        return self.repository.create({"id": identifier, "status": "queued", "progress": 0.,
            "created_at": datetime.now(timezone.utc).isoformat(), "parent_id": parent_id,
            "archived": False, "error": None, "config": config, "metadata": metadata, "report": None})

    def rerun(self, identifier):
        run = self.repository.get(identifier)
        folder = self.directory(identifier)
        metadata = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
        data_path = folder / "data.json"
        if not data_path.exists() or not metadata.get("data_hash"):
            raise ValueError("本次未完成数据准备，没有可重跑的完整快照；请重新创建任务")
        if metadata["environment"] != environment():
            raise ValueError("引擎或依赖版本与原运行不一致，不能进行一致性重跑")
        source, data = (folder / "strategy.py").read_bytes(), data_path.read_bytes()
        if digest(source) != metadata["strategy_hash"] or digest(data) != metadata["data_hash"]:
            raise ValueError("策略或数据快照校验失败")
        return self._create(run["config"], source, metadata, identifier, data)

    def cancel(self, identifier):
        self.repository.patch(identifier, allowed=ACTIVE | {"queued"}, status="cancelled")
        return self.repository.get(identifier)

    def archive(self, identifier):
        if self.repository.get(identifier)["status"] not in TERMINAL:
            raise ValueError("请先取消运行，再归档")
        self.repository.patch(identifier, archived=True)
        return self.repository.get(identifier)

    def records(self, identifier, kind, offset=0, limit=500, start=None, end=None):
        self.repository.get(identifier)
        if kind not in KINDS:
            raise ValueError("未知回测记录类型")
        return self.repository.records(identifier, kind, offset, limit, start, end)

    def sampled_equity(self, identifier, limit=1000):
        self.repository.get(identifier)
        # Stream DB pages; preserve both equity and drawdown extrema per bucket.
        total = self.repository.records(identifier, "equity", 0, 1)["total"]
        width = max(1, (total + max(1, limit // 6) - 1) // max(1, limit // 6))
        result, bucket = [], []
        def flush():
            if bucket:
                indices = {0, len(bucket) - 1}
                for key in ("equity", "drawdown_pct"):
                    indices.add(min(range(len(bucket)), key=lambda i: bucket[i][key]))
                    indices.add(max(range(len(bucket)), key=lambda i: bucket[i][key]))
                result.extend(bucket[i] for i in sorted(indices))
                bucket.clear()
        for offset in range(0, total, 2000):
            for item in self.repository.records(identifier, "equity", offset, 2000)["items"]:
                bucket.append(item)
                if len(bucket) >= width:
                    flush()
        flush()
        return {"items": result, "total": total, "offset": 0}

    def export(self, identifier, format):
        run = self.repository.get(identifier)
        if run["status"] != "completed":
            raise ValueError("只有完成的回测可以导出")
        if format == "json":
            result = json.loads((self.directory(identifier) / "result.json").read_text(encoding="utf-8"))
            content = json.dumps({"run": run, **result}, ensure_ascii=False, allow_nan=False)
            return {"filename": f"{identifier}.json", "content": content, "media_type": "application/json"}
        if format not in ("trades", "equity"):
            raise ValueError("导出格式应为 json/trades/equity")
        out = io.StringIO(newline="")
        writer = None
        offset = 0
        while True:
            page = self.records(identifier, format, offset, 2000)
            for item in page["items"]:
                if writer is None:
                    writer = csv.DictWriter(out, fieldnames=list(item))
                    writer.writeheader()
                writer.writerow(item)
            offset += len(page["items"])
            if offset >= page["total"]:
                break
        if writer is None:
            out.write("trade_id,side,entry_time,exit_time,entry_price,exit_price,profit\r\n")
        return {"filename": f"{identifier}-{format}.csv", "content": out.getvalue(), "media_type": "text/csv"}
