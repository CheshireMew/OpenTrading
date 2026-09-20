from datetime import datetime, timezone
import pytest

from app.domain.account_diagnostics import calendar_returns, drawdown_episodes, normalized_trades, compare_trades
from app.services.backtest_diagnostics_service import BacktestDiagnosticsService
from test.test_local_backtest_service import setup_service, complete


def stamp(value):
    return int(datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp()*1000)


def test_continuous_calendar_marks_exact_boundaries_and_missing_months():
    points = [dict(timestamp=stamp(t),equity=e) for t,e in [('2024-12-15',100),('2025-01-01',110),('2025-03-02',121),('2026-01-01',242)]]
    annual = calendar_returns(iter(points), 'year')
    assert [x['label'] for x in annual] == ['2024','2025']
    assert [x['return_pct'] for x in annual] == pytest.approx([10,120])
    monthly = calendar_returns(iter(points), 'month')
    assert monthly[1]['label'] == '2025-01' and monthly[1]['return_pct'] == 0
    assert monthly[1]['boundary_carried']
    growth = 1
    for p in monthly:
        growth *= 1+p['return_pct']/100
    assert growth == pytest.approx(2.42)
    assert monthly[-1]['end'] == stamp('2026-01-01')


def test_drawdown_peak_trough_recovery_and_unrecovered_tail():
    points = [dict(timestamp=i*1000,equity=v) for i,v in enumerate([100,120,90,108,120,150,75,80])]
    d = drawdown_episodes(iter(points))
    first,last=d['episodes']
    assert (first['peak_time'],first['trough_time'],first['recovery_time']) == (1000,2000,4000)
    assert first['drawdown_pct'] == 25
    assert last['drawdown_pct'] == 50 and not last['recovered']
    assert last['duration_ms'] == 2000 and last['recovery_time'] is None
    assert d['max_drawdown'] == last


def trade(n,t,ret,exit_price=100):
    return dict(trade_id=n,entry_time=t,side='long',entry_price=100,exit_time=t+1000,
                exit_price=exit_price,exit_phase='open',exit_reason='signal',return_pct=ret,profit=ret*100)


def test_normalized_all_trade_profits_and_exact_entry_differences():
    original = [trade(1,1,10),trade(2,2,-5),trade(3,3,2)]
    improved = [trade(1,1,10),trade(2,3,3,101),trade(3,4,-2)]
    normalized = normalized_trades(original)
    assert normalized['gross_profit'] == 1200 and normalized['gross_loss'] == 500
    assert normalized['net_profit'] == 700
    comparison=compare_trades(original,improved)
    assert comparison['unchanged'] == 1 and comparison['changed'] == 1
    assert comparison['dropped']['gross_loss'] == 500
    assert comparison['added']['gross_loss'] == 200
    assert comparison['total'] == 3
    # Amounts from different account sizes don't turn an identical trade into a new rule.
    copy=[{**t,'profit':t['profit']*2} for t in original]
    assert compare_trades(original,copy)['unchanged'] == 3
    copy[0]['return_pct'] += 1e-14
    assert compare_trades(original,copy)['unchanged'] == 3


def test_diagnostics_use_saved_pages_and_explain_missing_fine_equity(setup_service):
    from app.contracts.backtest_diagnostics import BacktestDiagnosticSummary, BacktestTradeChanges, BacktestTradeTimeline
    service,run=complete(setup_service)
    diagnostics=BacktestDiagnosticsService(service)
    summary=diagnostics.summary(run['id'])
    assert summary['available'] and len(summary['annual']) == 1
    assert BacktestDiagnosticSummary.model_validate(summary).annual[0].label == '2025'
    assert summary['annual'][0]['return_pct'] == pytest.approx(run['report']['return_pct'])
    assert not diagnostics.summary(run['id'],equity_kind='execution_equity')['available']
    timeline=diagnostics.timeline(run['id'],1)
    assert timeline['lineage'] == 'recorded_events'
    assert any(e['event'] == 'entry' for e in timeline['items'])
    assert any(e['event'] == 'exit' for e in timeline['items'])
    assert BacktestTradeTimeline.model_validate(timeline).trade['trade_id'] == 1
    assert diagnostics.compare(run['id'],run['id'])['total'] == 0
    assert BacktestTradeChanges.model_validate(diagnostics.compare(run['id'],run['id'])).total == 0


def test_fine_account_statistics_include_initial_cash_before_first_close(setup_service, monkeypatch):
    service,run=complete(setup_service)
    original=service.records
    start=stamp('2025-01-01')
    points=[dict(timestamp=start+300000,equity=9000),dict(timestamp=start+600000,equity=9500)]
    def records(identifier,kind,offset=0,limit=500,start=None,end=None):
        if kind=='execution_equity':
            return dict(total=len(points),items=points[offset:offset+limit],offset=offset)
        return original(identifier,kind,offset,limit,start,end)
    monkeypatch.setattr(service,'records',records)
    summary=BacktestDiagnosticsService(service).summary(run['id'],equity_kind='execution_equity')
    assert summary['annual'][0]['return_pct'] == pytest.approx(-5)
    assert summary['drawdown']['max_drawdown']['drawdown_pct'] == pytest.approx(10)


@pytest.mark.parametrize('opening,status', [(101, 'not_triggered'), (108, 'ignored_price_cap')])
def test_timeline_includes_unfilled_sibling_reversal_and_saved_conditions(opening, status):
    from types import SimpleNamespace
    from app.domain.local_backtest import Bar, BarResult, Intent, StopEntry, simulate
    step = 900000
    bars = [Bar(0,100,100,100,100,1), Bar(step,100,102,98,101,1),
            Bar(2*step,opening,max(opening,104),min(opening,100),103,1), Bar(3*step,103,104,102,103,1)]
    actions = {0: Intent('short'), 1: BarResult(Intent('close'),
        entry_order=StopEntry(Intent('long'),105,106), values={'确认起点时间': step, '下根突破入场价':105},
        checks={'挂出下一根突破委托': True}), 2: Intent('short', reason='unrelated later decision')}
    fine = {2*step:[Bar(2*step+i*300000,opening,max(opening,104),min(opening,100),103,1) for i in range(3)]}
    result=simulate(bars, SimpleNamespace(on_bar=lambda c:actions.get(len(c.history)-1)), {}, warmup=0, step_ms=step, execution_bars=fine)
    def records(identifier,kind,offset=0,limit=500,start=None,end=None):
        rows=[v for v in result.get(kind,[]) if (start is None or v['timestamp']>=start) and (end is None or v['timestamp']<=end)]
        return dict(items=rows[offset:offset+limit],total=len(rows))
    backtests=SimpleNamespace(repository=SimpleNamespace(get=lambda _:dict(status='completed',config={'timeframe':'15m'})),records=records)
    timeline=BacktestDiagnosticsService(backtests).timeline('fixture',1)
    assert {s['signal_id'] for s in timeline['signals']} == {1,2,3}
    checks=[e for e in timeline['items'] if e['event']=='order_checked']
    assert checks and all(e['status']==status for e in checks)
    if status=='not_triggered':
        assert checks[-1]['timestamp']==2*step+600000  # After first fine-bar exit.
    observation=next(e for e in timeline['items'] if e['event']=='strategy_observation')
    assert observation['values']['确认起点时间']==step
    assert observation['checks']['挂出下一根突破委托']
    assert all(e.get('signal_id') != 4 for e in timeline['items'])
