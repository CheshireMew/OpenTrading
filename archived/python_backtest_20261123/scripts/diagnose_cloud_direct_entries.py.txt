"""Attribute entry-gate changes to removed, retained and newly timed trades.
This analysis never chooses a rule. All comparisons reuse frozen replays.
"""
from math import isclose
from app.domain.cloud_trade_attribution import summary
from scripts.cloud_direct_adaptation_study import DOCS,RUNTIME,ASSETS,TFS,read_zip,freeze


def run():
    out={}
    for a in ASSETS:
        out[a]={}
        for tf in TFS:
            base=read_zip(RUNTIME/'traces'/a/f'{tf}-c0r0t0.json.gz')['trades']
            gated=read_zip(RUNTIME/'traces'/a/f'{tf}-base_gate.json.gz')['trades']
            key=lambda t:(t['entry_time'],t['side'])
            bm={key(t):t for t in base};gm={key(t):t for t in gated};shared=bm.keys()&gm.keys()
            assert all((bm[k]['exit_time'],bm[k]['exit_price'])==(gm[k]['exit_time'],gm[k]['exit_price']) for k in shared)
            removed=[v for k,v in bm.items() if k not in shared];added=[v for k,v in gm.items() if k not in shared]
            keep=[gm[k] for k in sorted(shared)]
            b,g,rr,aa,kk=[summary(ts) for ts in (base,gated,removed,added,keep)]
            assert isclose(g['log_growth']-b['log_growth'],aa['log_growth']-rr['log_growth'],abs_tol=1e-10)
            examples=[]
            for t in sorted(added,key=lambda t:t['return_pct'],reverse=True)[:3]:
                active=[u for u in base if u['entry_time']<t['entry_time']<=u['exit_time']]
                examples.append(dict(new_trade=t,baseline_active_trades=active))
            out[a][tf]=dict(original=b,filtered=g,retained=kk,removed=rr,new_entries=aa,
                shared_exit_exact=True,new_entry_examples=examples)
    freeze(DOCS/'entry-gate-attribution.json',out)
    print('Gate attribution complete; shared entry prices and exits exactly match')


if __name__=='__main__':run()
