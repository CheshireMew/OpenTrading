"""Preserve every new full-history variant as a normal project backtest."""
from app.contracts.local_backtest import LocalBacktestCommand
from app.infra.db import build_database_runtime
from app.services.local_backtest_service import LocalBacktestService
from app.services.local_backtest_strategies import digest
from config import settings
from scripts.cloud_robustness_study import DOCS, RUNTIME, SOURCE
from scripts.profit_protection_study import read, save


def main():
    output = read(DOCS/'results.json')
    assert output['status'] == 'completed'
    assert digest(SOURCE.read_bytes()) == output['provenance']['files']['strategies/trend_cloud_robustness_v1.py']
    path = DOCS/'project-runs.json'
    receipt = read(path) if path.exists() else {'provenance':output['provenance'],'runs':{}}
    assert receipt['provenance'] == output['provenance']
    database = build_database_runtime(settings)
    service = LocalBacktestService(database)
    try:
        for key,v in output['plan']['variants'].items():
            if key not in receipt['runs']:
                plan = output['plan']
                cmd = {k:plan[k] for k in ('symbol','timeframe','start','end','initial_cash','position_pct')}
                cmd.update(strategy='trend_cloud_robustness_v1',parameters={**v['parameters'],'record_indicators':True})
                run = service.create(LocalBacktestCommand.model_validate(cmd))
                receipt['runs'][key] = dict(run_id=run['id'],verified=False)
                save(path,receipt)
            run = service.repository.get(receipt['runs'][key]['run_id'])
            if run['status'] == 'completed' and not receipt['runs'][key]['verified']:
                actual = read(service.directory(run['id'])/'result.json')
                expected = read(RUNTIME/f'{key}-full.json')
                assert run['metadata']['data_hash'] == output['provenance']['data_hash']
                assert run['metadata']['strategy_hash'] == digest(SOURCE.read_bytes())
                assert actual['report'] == expected['report']
                assert actual['trades'] == expected['trades'] and actual['signals'] == expected['signals']
                receipt['runs'][key]['verified'] = True
                save(path,receipt)
            print(f'{key}: {run["id"]} {run["status"]} verified={receipt["runs"][key]["verified"]} {run.get("error") or ""}',flush=True)
    finally:
        database.dispose()


if __name__ == '__main__':
    main()
