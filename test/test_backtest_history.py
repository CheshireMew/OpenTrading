import pytest
from app.domain.local_backtest import validate_bars
from app.domain.backtest_history import validate_observed_bars
from test.test_local_backtest_service import setup_service
from scripts.local_backtest_worker import execute
from app.services.market.history_range_coordinator import OhlcvRangeResult
from types import SimpleNamespace


def rows():
    return [[i*900000, 100, 101, 99, 100, 1] for i in range(12)]


def test_contiguous_observed_history_is_exactly_the_strict_history():
    bars, gaps = validate_observed_bars(rows(), 2*900000, 12*900000, 900000, 2, 20*900000)
    assert not gaps
    assert bars == validate_bars(rows(), 2*900000, 12*900000, 900000, 2, 20*900000)


def test_gap_is_reported_and_not_filled():
    data = rows()[:4]+rows()[7:]
    bars, gaps = validate_observed_bars(data, 2*900000, 12*900000, 900000, 2, 20*900000)
    assert len(bars) == 9 and [b.timestamp for b in bars] == [r[0] for r in data]
    assert gaps == [dict(start=4*900000, end=7*900000, missing_bars=3)]
    with pytest.raises(ValueError):
        validate_bars(data, 2*900000, 12*900000, 900000, 2, 20*900000)


@pytest.mark.parametrize('kind', ['duplicate', 'unordered', 'unaligned', 'invalid_ohlc', 'warmup_gap', 'head', 'tail', 'future'])
def test_observed_policy_still_rejects_invalid_data(kind):
    data = rows()
    now = 20*900000
    if kind == 'duplicate': data.insert(4, list(data[3]))
    if kind == 'unordered': data[3], data[4] = data[4], data[3]
    if kind == 'unaligned': data[4][0] += 1
    if kind == 'invalid_ohlc': data[4][2] = 98
    if kind == 'warmup_gap': data.pop(1)
    if kind == 'head': data = data[1:]
    if kind == 'tail': data = data[:-1]
    if kind == 'future': now = 10*900000
    with pytest.raises(ValueError):
        validate_observed_bars(data, 2*900000, 12*900000, 900000, 2, now)


def test_worker_records_gap_and_replays_exact_snapshot(setup_service):
    service, command, market = setup_service
    original = market.load_ohlcv_range()
    data = original.rows[:2]+original.rows[3:]
    gap = (original.rows[2][0], original.rows[3][0])
    market = SimpleNamespace(load_ohlcv_range=lambda *a: OhlcvRangeResult(data, [gap]))
    command = command.model_copy(update={'data_gap_policy': 'observed_bars'})
    run = service.create(command)
    assert service.repository.claim() == run['id']
    execute(service, run['id'], market)
    done = service.repository.get(run['id'])
    assert done['status'] == 'completed'
    assert done['metadata']['history_gaps'] == [dict(start=gap[0], end=gap[1], missing_bars=1)]
    assert service.records(run['id'], 'candles')['total'] == 4
    again = service.rerun(run['id'])
    assert service.repository.claim() == again['id']
    execute(service, again['id'])
    assert service.repository.get(again['id'])['report'] == done['report']


def test_worker_rejects_gap_by_default(setup_service):
    service, command, market = setup_service
    original = market.load_ohlcv_range()
    data = original.rows[:2]+original.rows[3:]
    market = SimpleNamespace(load_ohlcv_range=lambda *a: OhlcvRangeResult(data, [(original.rows[2][0], original.rows[3][0])]))
    run = service.create(command)
    assert service.repository.claim() == run['id']
    with pytest.raises(RuntimeError, match='Incomplete'):
        execute(service, run['id'], market)
