"""Compare native larger candles with complete native5m buckets, repair only live-confirmed stale rows."""
from math import isclose
from bisect import bisect_left
from scripts.cloud_timeframe_study import *


def same(a,b):return len(a)==len(b) and all(isclose(x,y,rel_tol=1e-10,abs_tol=1e-8) for x,y in zip(a,b))


def main():
    if (DOCS/'data-verification.json').exists():print('Data already checked');return
    plan=read(DOCS/'plan.json');data=read(DOCS/'data.json');records=[];counts={};corrections=[]
    db=build_database_runtime(settings);market=MarketDataService(exchange_gateway=ExchangeGateway('binance'),kline_store=KlineStore(database_runtime=db))
    try:
        for a in ASSETS:
            raw=read(ROOT/data[a]['5m']['path']);times=[x[0] for x in raw];counts[a]={}
            for tf in ('30m','1h','1d'):
                larger=read(ROOT/data[a][tf]['path']);step=STEPS[tf];checked=0
                for row in larger:
                    t=int(row[0]);i,j=bisect_left(times,t),bisect_left(times,t+step)
                    if j-i!=step//STEPS['5m'] or i>=len(raw) or raw[i][0]!=t:continue
                    bucket=raw[i:j]
                    # Native exchange candles use actual trades. An empty5m candle
                    # repeats an earlier price, which is not a trade in this interval.
                    active=[x for x in bucket if x[5]>0] or bucket
                    ohlc=[active[0][1],max(x[2] for x in active),min(x[3] for x in active),active[-1][4]];checked+=1
                    if same(row[1:5],ohlc):continue
                    symbol=plan['old_data'][a]['symbol'];dt=lambda x:datetime.fromtimestamp(x/1000,timezone.utc)
                    live=market.load_live_ohlcv_range(symbol,tf,dt(t),dt(t+step-1)).rows
                    live=[x for x in live if int(x[0])==t];assert len(live)==1
                    record=dict(asset=a,timeframe=tf,timestamp=t,before=row,aggregate_5m=ohlc,live=live[0],changed=not same(row,live[0]))
                    records.append(record)
                    if record['changed']:corrections.append(record)
                    print('CHECK',a,tf,date(t)[:16],'stale' if record['changed'] else 'native agrees with live source',flush=True)
                counts[a][tf]=checked
        # Persist every original value before any database or study manifest write.
        evidence=dict(created_at=utc(),complete_buckets_checked=counts,mismatches=records,corrections=corrections)
        save(DOCS/'native-timeframe-live-recheck.json',evidence)
        if corrections:
            initial=(DOCS/'data.json').read_bytes()
            backup=DOCS/'data-before-cache-correction.json'
            if not backup.exists():backup.write_bytes(initial)
            for a in ASSETS:
                for tf in ('30m','1h','1d'):
                    changes=[r for r in corrections if r['asset']==a and r['timeframe']==tf]
                    if not changes:continue
                    old=data[a][tf];values={int(x[0]):x for x in read(ROOT/old['path'])}
                    for r in changes:
                        values[r['timestamp']]=r['live'];storage=market.symbol_routing.storage_symbol(plan['old_data'][a]['symbol'])
                        market.kline_store.save(storage,tf,[r['live']])
                        got=market.kline_store.get_range(storage,tf,r['timestamp'],r['timestamp']);assert len(got)==1 and same(got[0],r['live'])
                    path=RUNTIME/'data'/f'{a}-{tf}-corrected.json';freeze(path,sorted(values.values(),key=lambda x:x[0]))
                    data[a][tf]=dict(old,uncorrected_path=old['path'],uncorrected_data_hash=old['data_hash'],path=path.relative_to(ROOT).as_posix(),data_hash=digest(path.read_bytes()),corrections=len(changes))
            # Original manifest and every original data file remain available.
            save(DOCS/'data.json',data)
        save(DOCS/'data-verification.json',dict(status='passed',checked_at=utc(),complete_buckets_checked=counts,live_rechecked=len(records),corrected=len(corrections),data_hash=digest((DOCS/'data.json').read_bytes())))
        print('DATA VERIFIED',sum(sum(v.values()) for v in counts.values()),'complete buckets;',len(corrections),'live-confirmed corrections',flush=True)
    finally:db.dispose()


if __name__=='__main__':main()
