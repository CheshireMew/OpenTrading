"""Small immutable execution bundles and explicit evidence checks.

The module swap runs inside a dedicated backtest worker process. A lock also
makes in-process test workers safe; normal workers never share Python globals.
"""
from contextlib import contextmanager
import ast
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from threading import RLock

from app.infra.research_files import atomic_json, encode, sha, file_hash, read_json, native_path

DOMAIN = Path(__file__).parents[1] / 'domain'
MODULES = ('local_backtest', 'backtest_history', 'backtest_execution')
_module_lock = RLock()


def current_bundle():
    files = {f'{name}.py': file_hash(DOMAIN / f'{name}.py') for name in MODULES}
    return {'version': 1, 'files': files, 'hash': sha(encode(files))}


def verify_bundle(folder, expected):
    folder = native_path(folder)
    manifest = read_json(folder / 'manifest.json')
    if manifest != expected or manifest.get('version') != 1 or set(manifest['files']) != {f'{m}.py' for m in MODULES}:
        raise ValueError('执行依赖清单与冻结版本不同')
    if sha(encode(manifest['files'])) != manifest['hash']:
        raise ValueError('执行依赖清单校验失败')
    for name, digest in manifest['files'].items():
        if file_hash(folder / name) != digest:
            raise ValueError(f'执行依赖快照校验失败：{name}')
    return manifest


def save_bundle(folder, expected, source_folder=None):
    folder = native_path(folder)
    origin = native_path(source_folder) if source_folder else DOMAIN
    if source_folder:
        verify_bundle(origin, expected)
    elif current_bundle() != expected:
        raise ValueError('执行代码与冻结计划不同，请另建版本')
    folder.mkdir(parents=True, exist_ok=True)
    for name, digest in expected['files'].items():
        data = (origin / name).read_bytes()
        if sha(data) != digest:
            raise ValueError('保存期间执行代码已改变')
        path = folder / name
        if path.exists() and path.read_bytes() != data:
            raise ValueError('同一执行快照已经存在且内容不同')
        if not path.exists():
            path.write_bytes(data)
    atomic_json(folder / 'manifest.json', expected)
    verify_bundle(folder, expected)


def compatible_environment(saved, current):
    """An archived engine may differ; Python and numerical dependencies may not."""
    return isinstance(saved, dict) and all(saved.get(k) == current.get(k) for k in ('python', 'dependencies'))


def verify_replay(folder, metadata):
    verify_bundle(folder, metadata['execution_bundle'])
    tree = ast.parse((native_path(folder)/'local_backtest.py').read_text(encoding='utf-8-sig'))
    version = next((ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == 'ENGINE_VERSION' for t in n.targets)), None)
    if version is None or metadata['environment'].get('engine') != version:
        raise ValueError('引擎版本记录与保存的执行依赖不符')


@contextmanager
def execution_modules(folder, expected):
    folder = native_path(folder)
    verify_bundle(folder, expected)
    with _module_lock:
        import app.domain as package
        names = [f'app.domain.{m}' for m in MODULES]
        previous = {name: sys.modules.get(name) for name in names}
        attributes = {m: getattr(package, m, None) for m in MODULES}
        try:
            for name, short in zip(names, MODULES):
                spec = spec_from_file_location(name, Path(folder) / f'{short}.py')
                module = module_from_spec(spec)
                sys.modules[name] = module
                setattr(package, short, module)
                # Compile the saved bytes directly: no stale .pyc dependency.
                exec(compile((Path(folder) / f'{short}.py').read_bytes(), str(spec.origin), 'exec'), module.__dict__)
            yield sys.modules[names[-1]]
        finally:
            for name, short in zip(names, MODULES):
                if previous[name] is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = previous[name]
                if attributes[short] is None:
                    delattr(package, short)
                else:
                    setattr(package, short, attributes[short])


def evidence_status(run):
    meta, config = run.get('metadata', {}), run.get('config', {})
    required = ['environment', 'source', 'data_hash', 'strategy_hash', 'warmup_bars', 'execution_bundle']
    if config.get('execution_timeframe'):
        required += ['execution_data_hash', 'execution_alignment_hash']
    missing = [key for key in required if meta.get(key) is None or meta.get(key) == {} or meta.get(key) == '']
    return {'status': 'insufficient' if missing else 'complete', 'missing': missing,
            'exact_replay': not missing,
            'note': '证据缺失表示无法确认一致性，不表示历史计算必然错误。'}


def execution_summary(run):
    config, meta = run.get('config', {}), run.get('metadata', {})
    fine = config.get('execution_timeframe')
    matched, fallback = meta.get('execution_matched_candles'), meta.get('execution_fallback_candles')
    count = matched + fallback if matched is not None and fallback is not None else None
    return {'signal_timeframe': config.get('timeframe'), 'execution_timeframe': fine or config.get('timeframe'),
        'protection_timeframe': fine if fine and config.get('intrabar_profit_protection') else config.get('timeframe'),
        'execution_gap_policy': config.get('execution_gap_policy', 'coarse_fallback'),
        'matched_intervals': matched, 'fallback_intervals': fallback,
        'coverage_pct': matched / count * 100 if count else None,
        'drawdown_timeframe': config.get('timeframe'),
        'execution_drawdown_basis': 'mixed_closes' if fallback else 'execution_closes' if fine and count else 'unavailable',
        'ambiguity_policy': {0: 'stop_first', 1: 'adverse_extreme_before_entry'}.get(config.get('parameters', {}).get('entry_bar_assumption')),
        'provenance': evidence_status(run)}
