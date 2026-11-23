"""Recheck observed native/15m disagreements, preserve evidence, repair confirmed cache rows."""
import argparse
from datetime import datetime, timezone
from math import isclose

from scripts.cross_market_trend_study import ROOT, read, save, utc
from app.infra.db import build_database_runtime
from app.infra.persistence.market.kline_store import KlineStore
from app.services.market.exchange_gateway import ExchangeGateway
from app.services.market.market_data_service import MarketDataService
from config import settings

DOCS = ROOT/'docs/verification/cross-market-trend-20260911'
RECEIPT = DOCS/'native-live-recheck-complete.json'


def same(a, b):
    return len(a) == len(b) and all(isclose(x, y, rel_tol=1e-10, abs_tol=1e-8) for x, y in zip(a, b))


def main(apply=False):
    plan = read(DOCS/'plan.json')
    db = build_database_runtime(settings)
    market = MarketDataService(exchange_gateway=ExchangeGateway('binance'), kline_store=KlineStore(database_runtime=db))
    try:
        if RECEIPT.exists():
            receipt = read(RECEIPT)
        else:
            records = [dict(asset=r['asset'], symbol=plan['old_data'][r['asset']]['symbol'], timeframe='1d',
                            timestamp=int(r['stored_daily'][0]), before=r['stored_daily'], live=r['live_daily'][0],
                            changed=not r['same'], prior_receipt='native-daily-live-recheck.json')
                       for r in read(DOCS/'native-daily-live-recheck.json')]
            for tf, filename, step in [('4h', 'native4h-vs-15m-data-check.json', 14400000)]:
                for asset, check in read(DOCS/filename).items():
                    for item in check['mismatches']:
                        before = item.get('native', item.get('daily'))
                        if before is None:
                            raise ValueError(f'Unknown receipt format: {item.keys()}')
                        t = int(before[0]); symbol = plan['old_data'][asset]['symbol']
                        to_dt = lambda x: datetime.fromtimestamp(x/1000, timezone.utc)
                        rows = market.load_live_ohlcv_range(symbol, tf, to_dt(t), to_dt(t+step-1)).rows
                        exact = [row for row in rows if int(row[0]) == t]
                        assert len(exact) == 1, (asset, tf, t, rows)
                        records.append(dict(asset=asset, symbol=symbol, timeframe=tf, timestamp=t, before=before,
                                            live=exact[0], changed=not same(before, exact[0]), checked_at=utc()))
                        print('RECHECK', asset, tf, t, 'changed' if records[-1]['changed'] else 'same', flush=True)
            receipt = dict(created_at=utc(), records=records)
            save(RECEIPT, receipt)
        changed = [r for r in receipt['records'] if r['changed']]
        print('CONFIRMED', len(changed), 'changed cache candles', flush=True)
        if apply:
            applied = []
            for r in changed:
                storage = market.symbol_routing.storage_symbol(r['symbol'])
                prior = market.kline_store.get_range(storage, r['timeframe'], r['timestamp'], r['timestamp'])
                assert len(prior) == 1 and (same(prior[0], r['before']) or same(prior[0], r['live']))
                # Evidence above is saved before every database change.
                market.kline_store.save(storage, r['timeframe'], [r['live']])
                after = market.kline_store.get_range(storage, r['timeframe'], r['timestamp'], r['timestamp'])
                assert len(after) == 1 and same(after[0], r['live'])
                applied.append(dict(**r, storage_symbol=storage, verified=after[0]))
            dest = DOCS/'native-cache-correction-applied.json'
            if not dest.exists():
                save(dest, dict(applied_at=utc(), evidence=str(RECEIPT.relative_to(ROOT)), corrections=applied))
            print('SAVED_AND_READ_BACK', len(applied), flush=True)
    finally:
        db.dispose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    main(parser.parse_args().apply)
