from __future__ import annotations

import csv
import io
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from app.infra.research_files import atomic_json, file_hash, native_path
from app.services.backtest_provenance import current_bundle, save_bundle, verify_bundle, verify_replay, compatible_environment, execution_summary
from app.services.backtest_datasets import BacktestDatasets
from app.services.backtest_record_store import BacktestRecordStore, computation_fingerprint

from app.contracts.local_backtest import LocalBacktestCommand
from app.domain.local_backtest import DISCLAIMER
from app.infra.persistence.local_backtest_repository import LocalBacktestRepository, ACTIVE, TERMINAL
from app.services.local_backtest_strategies import (
    STRATEGIES_DIR, digest, environment, inspect_strategy, strategy_path, validate_parameters, resolve_warmup, rules_summary,
)
from app.services.market.symbol_catalog import get_market_symbol_source, get_supported_crypto_symbols
from app.services.market.exchange_gateway import ExchangeGateway
from app.domain.market.constants import timeframe_to_milliseconds
from config import settings

TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]
KINDS = {"trades", "signals", "fills", "equity", "levels", "candles", "indicators", "events", "execution_equity"}


def write_json(path, value):
    atomic_json(path, value)


class LocalBacktestService:
    def __init__(self, database, root=None):
        self.repository = LocalBacktestRepository(database)
        self.root = Path(root or settings.RUNTIME_ROOT_DIR / "local_backtests")
        self.datasets = BacktestDatasets(self.root.parent/'backtest_datasets')
        self.record_store = BacktestRecordStore(self.root.parent/'backtest_records')
        self._exchange_timeframes = {}

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
        config, source, metadata = self.prepare(command)
        return self._create(config, source, metadata)

    def prepare(self, command: LocalBacktestCommand):
        """Validate without queueing or downloading; used when freezing study plans."""
        path = strategy_path(command.strategy)
        source_bytes = path.read_bytes()
        metadata = inspect_strategy(source_bytes, path.name)
        if metadata.id != command.strategy:
            raise ValueError("策略标识与文件名不一致")
        values = validate_parameters(metadata, command.parameters)
        warmup_bars, warmup_explanation = resolve_warmup(metadata, values)
        source = get_market_symbol_source(command.symbol)
        if source is None or ":" in command.symbol:
            raise ValueError("仅支持现有目录中的加密货币现货交易对")
        if source.exchange_id not in self._exchange_timeframes:
            self._exchange_timeframes[source.exchange_id] = ExchangeGateway(source.exchange_id).exchange.timeframes or {}
        supported = self._exchange_timeframes[source.exchange_id]
        if command.timeframe not in supported:
            raise ValueError("数据源不支持该周期")
        step = timeframe_to_milliseconds(command.timeframe)
        start, end = int(command.start.timestamp() * 1000), int(command.end.timestamp() * 1000)
        if start % step or end % step or command.start.microsecond or command.end.microsecond:
            raise ValueError("起止时间必须对齐所选周期")
        if end > int(datetime.now(timezone.utc).timestamp() * 1000):
            raise ValueError("不能包含未收盘 K 线，请调整结束时间")
        config = command.model_dump(mode="json")
        if command.execution_timeframe is None:
            config.pop('execution_timeframe')
            config.pop('intrabar_profit_protection')
        config.update(parameters=values, symbol=source.symbol)
        recipe = dict(start_ms=start, end_ms=end, step_ms=step, warmup_bars=warmup_bars,
            execution_step_ms=timeframe_to_milliseconds(command.execution_timeframe) if command.execution_timeframe else None,
            initial_cash=command.initial_cash, position_pct=command.position_pct, data_gap_policy=command.data_gap_policy,
            execution_gap_policy=command.execution_gap_policy, intrabar_profit_protection=command.intrabar_profit_protection)
        return config, source_bytes, {
            "strategy": metadata.model_dump(), "environment": environment(),
            "execution_bundle": current_bundle(), "execution_recipe": recipe, "warmup_bars": warmup_bars,
            "warmup_explanation": warmup_explanation, "rules_summary": rules_summary(metadata, values),
            "engine_code_hash": file_hash(Path(__file__).parents[1] / 'domain/local_backtest.py'), "source": {
                "exchange": source.exchange_id, "symbol": source.symbol, "storage_symbol": source.storage_symbol,
                "price_type": "spot"}, "disclaimer": DISCLAIMER,
        }

    def preview(self, command):
        from app.services.backtest_preflight import preview_prepared
        config, _, metadata = self.prepare(command)
        return preview_prepared(self.repository.database, config, metadata)

    def _create(self, config, source, metadata, parent_id=None, data=None, identifier=None, *, execution_data=None, execution_source=None):
        identifier = identifier or uuid4().hex
        if len(identifier) != 32 or any(c not in '0123456789abcdef' for c in identifier):
            raise ValueError('无效回测标识')
        folder = self.root / identifier
        metadata = {**metadata, "strategy_hash": digest(source)}
        engine = ((native_path(execution_source) if execution_source else Path(__file__).parents[1] / 'domain') / 'local_backtest.py').read_bytes()
        if metadata.get('engine_code_hash') and digest(engine) != metadata['engine_code_hash']:
            raise ValueError('引擎源码与冻结计划不同，请另建版本')
        # Study callers hold their study lock. A deterministic ID also recovers a
        # submission killed between persisting its files and recording its run ID.
        if folder.exists():
            for name, value in [('config.json', config), ('metadata.json', metadata)]:
                path = folder / name
                if path.exists():
                    saved = json.loads(path.read_text(encoding='utf-8'))
                    if any(saved.get(k) != v for k, v in value.items()):
                        raise ValueError('同一回测标识的快照不一致')
            path = folder / 'strategy.py'
            if path.exists() and path.read_bytes() != source:
                raise ValueError('同一回测标识的策略不一致')
            try:
                existing = self.repository.get(identifier)
            except ValueError:
                existing = None
            if existing is not None:
                return existing
        folder.mkdir(parents=True, exist_ok=True)
        if metadata.get('execution_bundle'):
            save_bundle(folder/'execution', metadata['execution_bundle'], execution_source)
        (folder / "strategy.py").write_bytes(source)
        if metadata.get('engine_code_hash'):
            (folder / 'engine.py').write_bytes(engine)
        if data is not None:
            self.datasets.install(folder, 'data.json', data, metadata.get('data_hash'))
        if execution_data is not None:
            self.datasets.install(folder, 'execution_data.json', execution_data, metadata.get('execution_data_hash'))
        write_json(folder / "config.json", config)
        write_json(folder / "metadata.json", metadata)
        return self.repository.create({"id": identifier, "status": "queued", "progress": 0.,
            "created_at": datetime.now(timezone.utc).isoformat(), "parent_id": parent_id,
            "archived": False, "error": None, "config": config, "metadata": metadata, "report": None})

    def rerun(self, identifier):
        run = self.repository.get(identifier)
        folder = self.directory(identifier)
        metadata = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
        data_path = self.datasets.resolve(folder, 'data.json')
        if not data_path.exists() or not metadata.get("data_hash"):
            raise ValueError("本次未完成数据准备，没有可重跑的完整快照；请重新创建任务")
        if not metadata.get('execution_bundle'):
            raise ValueError('旧记录缺少完整执行依赖，无法证明精确重跑；请使用 migrate 显式创建当前引擎对照')
        if not compatible_environment(metadata['environment'], environment()):
            raise ValueError('Python 或数值依赖与原运行不一致，不能进行一致性重跑；可使用 migrate 创建对照')
        verify_replay(folder/'execution', metadata)
        source, data = (folder / "strategy.py").read_bytes(), data_path
        if digest(source) != metadata["strategy_hash"] or file_hash(data) != metadata["data_hash"]:
            raise ValueError("策略或数据快照校验失败")
        execution_data=None
        if run['config'].get('execution_timeframe'):
            execution_data=self.datasets.resolve(folder, 'execution_data.json')
            if file_hash(execution_data)!=metadata.get('execution_data_hash'):
                raise ValueError('细周期行情快照校验失败')
        return self._create(run["config"], source, metadata, identifier, data, execution_data=execution_data,
                            execution_source=folder/'execution')

    def migrate(self, identifier):
        """Explicitly reuse saved strategy and prices with today's execution code."""
        run = self.repository.get(identifier)
        folder = self.directory(identifier)
        original = json.loads((folder/'metadata.json').read_text(encoding='utf-8'))
        source, data = (folder/'strategy.py').read_bytes(), self.datasets.resolve(folder, 'data.json')
        if digest(source) != original.get('strategy_hash') or file_hash(data) != original.get('data_hash'):
            raise ValueError('原策略或行情快照校验失败，不能迁移')
        spec = inspect_strategy(source, 'strategy.py')
        command = LocalBacktestCommand.model_validate(run['config'])
        step = timeframe_to_milliseconds(command.timeframe)
        warmup = original.get('warmup_bars', spec.warmup_bars)
        fine = self.datasets.resolve(folder, 'execution_data.json') if command.execution_timeframe else None
        if fine is not None and file_hash(fine) != original.get('execution_data_hash'):
            raise ValueError('细周期行情快照校验失败')
        meta = {key: original[key] for key in ('source', 'data_hash', 'execution_data_hash') if key in original}
        meta.update(strategy=spec.model_dump(), warmup_bars=warmup, environment=environment(),
            rules_summary=rules_summary(spec, validate_parameters(spec, command.parameters)),
            warmup_explanation='显式迁移沿用原运行保存的预热根数，不重新计算或移动起点。',
            engine_code_hash=file_hash(Path(__file__).parents[1]/'domain/local_backtest.py'), execution_bundle=current_bundle(),
            migration_from=identifier, migration_note='保留原策略、参数、行情与预热，使用当前引擎；这不是原版本精确重跑。',
            execution_recipe=dict(start_ms=int(command.start.timestamp()*1000), end_ms=int(command.end.timestamp()*1000),
                step_ms=step, warmup_bars=warmup, initial_cash=command.initial_cash, position_pct=command.position_pct,
                execution_step_ms=timeframe_to_milliseconds(command.execution_timeframe) if command.execution_timeframe else None,
                data_gap_policy=command.data_gap_policy, execution_gap_policy=command.execution_gap_policy,
                intrabar_profit_protection=command.intrabar_profit_protection))
        return self._create(run['config'], source, meta, identifier, data, execution_data=fine)

    def get(self, identifier):
        run = self.repository.get(identifier)
        return {**run, 'execution_summary': execution_summary(run),
                'resume_available': run['status'] in {'failed', 'cancelled', 'interrupted'} and (self.directory(identifier)/'computed.json').exists()}

    def data_path(self, identifier, name='data.json'):
        if name not in {'data.json', 'execution_data.json'}:
            raise ValueError('未知行情快照')
        return self.datasets.resolve(self.directory(identifier), name)

    def artifacts(self, identifier):
        run, folder = self.repository.get(identifier), self.directory(identifier)
        result = {'run_id': identifier, 'strategy': str((folder/'strategy.py').resolve()),
            'metadata': str((folder/'metadata.json').resolve()), 'datasets': {},
            'result_format': run['metadata'].get('result_storage', 'legacy-json'),
            'result': str((folder/('computed.json' if (folder/'computed.json').exists() else 'result.json')).resolve())}
        for name, key in [('data.json', 'data_hash'), ('execution_data.json', 'execution_data_hash')]:
            path = self.datasets.resolve(folder, name)
            if path.exists():
                result['datasets'][name] = {'path': str(path.resolve()), 'sha256': run['metadata'].get(key)}
        return result

    def resume(self, identifier, *, new_identifier=None):
        run = self.repository.get(identifier)
        if run['status'] not in {'failed', 'cancelled', 'interrupted'}:
            raise ValueError('只能恢复失败、取消或中断的计算结果')
        folder = self.directory(identifier)
        manifest = self.record_store.manifest(folder)
        if manifest['fingerprint'] != computation_fingerprint(run):
            raise ValueError('已算结果与原输入不一致，不能恢复保存')
        metadata = {**run['metadata'], 'resume_result_from': identifier}
        return self._create(run['config'], (folder/'strategy.py').read_bytes(), metadata,
            parent_id=identifier, data=self.data_path(identifier), identifier=new_identifier,
            execution_data=self.data_path(identifier, 'execution_data.json') if run['config'].get('execution_timeframe') else None,
            execution_source=folder/'execution' if metadata.get('execution_bundle') else None)

    def publish_computed(self, identifier, origin=None):
        run, folder = self.repository.get(identifier), self.directory(identifier)
        source = self.directory(origin) if origin else folder
        manifest = self.record_store.manifest(source)
        if manifest['fingerprint'] != computation_fingerprint(run):
            raise ValueError('已算结果与冻结输入不符')
        if source != folder:
            write_json(folder/'computed.json', manifest)
            if (source/'execution_alignment.json').exists():
                write_json(folder/'execution_alignment.json', json.loads((source/'execution_alignment.json').read_text(encoding='utf8')))
        metadata = {**run['metadata'], 'result_storage': 'record-pages-v1', 'result_hash': file_hash(folder/'computed.json')}
        write_json(folder/'metadata.json', metadata)
        total = sum(len(a['parts']) for a in manifest['arrays'].values())
        if not self.repository.patch(identifier, allowed=ACTIVE, status='saving', progress=.82, metadata=metadata,
            progress_detail={'phase': 'saving', 'unit': 'chunks', 'done': 0, 'total': total}):
            raise InterruptedError('保存已取消，已计算结果可恢复')
        last = [0.]
        def verify_progress(value):
            now = time.monotonic()
            if now-last[0] >= .2 or value == 1:
                last[0] = now
                if not self.repository.patch(identifier, allowed={'saving'}, progress=.82+.17*value,
                    progress_detail={'phase': 'saving', 'unit': 'chunks', 'done': round(total*value), 'total': total}):
                    raise InterruptedError('保存已取消，已计算结果可恢复')
        self.record_store.verify(manifest, verify_progress)
        if not self.repository.patch(identifier, allowed={'saving'}, status='completed', progress=1.,
            report=manifest['extra']['report'], metadata=metadata, progress_detail={'phase': 'completed', 'unit': 'chunks', 'done': total, 'total': total}):
            raise InterruptedError('保存已取消，已计算结果可恢复')
        self.register_result(identifier)
        return self.get(identifier)

    def register_result(self, identifier):
        # The result is authoritative; a rebuildable index outage must not undo it.
        from app.services.research_results_catalog import ResearchResultsCatalog
        try:
            ResearchResultsCatalog(self).register(self.repository.get(identifier))
        except Exception:
            import logging
            logging.getLogger(__name__).exception('结果已保存；目录登记失败，下次查询将重新同步：%s', identifier)

    def result(self, identifier):
        run = self.repository.get(identifier)
        if run['metadata'].get('result_storage') == 'record-pages-v1':
            return self.record_store.result(self.record_store.manifest(self.directory(identifier), run['metadata'].get('result_hash')))
        return json.loads((self.directory(identifier)/'result.json').read_text(encoding='utf8'))

    def verify_result(self, run):
        if run['metadata'].get('result_storage') == 'record-pages-v1':
            folder = self.directory(run['id'])
            manifest = self.record_store.manifest(folder, run['metadata'].get('result_hash'))
            if manifest['fingerprint'] != computation_fingerprint(run) or manifest['extra']['report'] != run['report']:
                raise ValueError('保存结果与运行摘要或输入不一致')
            self.record_store.verify(manifest)
            return file_hash(folder/'computed.json')
        path = self.directory(run['id'])/'result.json'
        if not path.exists():
            raise ValueError('缺少完整逐笔结果文件')
        digest = file_hash(path)
        if run['metadata'].get('result_hash') and digest != run['metadata']['result_hash']:
            raise ValueError('结果快照校验失败')
        return digest

    def listing(self, offset=0, limit=50, archived=False):
        page = self.repository.list(offset, limit, archived)
        return {**page, 'items': [{**r, 'execution_summary': execution_summary(r)} for r in page['items']]}

    def cancel(self, identifier):
        self.repository.patch(identifier, allowed=ACTIVE | {"queued"}, status="cancelled")
        return self.repository.get(identifier)

    def archive(self, identifier):
        if self.repository.get(identifier)["status"] not in TERMINAL:
            raise ValueError("请先取消运行，再归档")
        self.repository.patch(identifier, archived=True)
        self.register_result(identifier)
        return self.repository.get(identifier)

    def records(self, identifier, kind, offset=0, limit=500, start=None, end=None):
        run = self.repository.get(identifier)
        if kind not in KINDS:
            raise ValueError("未知回测记录类型")
        if run['metadata'].get('result_storage') == 'record-pages-v1':
            if run['status'] != 'completed':
                return {'items': [], 'total': 0, 'offset': offset}
            return self.record_store.records(self.record_store.manifest(self.directory(identifier), run['metadata'].get('result_hash')), kind, offset, limit, start, end)
        return self.repository.records(identifier, kind, offset, limit, start, end)

    def sampled_equity(self, identifier, limit=1000, kind='equity'):
        self.repository.get(identifier)
        if kind not in {'equity', 'execution_equity'}:
            raise ValueError('只能采样主周期或成交周期权益')
        # Stream DB pages; preserve both equity and drawdown extrema per bucket.
        total = self.records(identifier, kind, 0, 1)["total"]
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
            for item in self.records(identifier, kind, offset, 2000)["items"]:
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
            result = self.result(identifier)
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
