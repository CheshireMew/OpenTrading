"""Finish the cause audit without touching frozen labels or original strategies."""
from bisect import bisect_left
from copy import deepcopy
from scripts.cloud_entry_cause_audit import (DOCS,ROOT,START,SPLIT,END,STEP,stamp,read,read_zip,freeze,feature_compare)


def main():
    d=read(DOCS/'results.json');f=deepcopy(d);checks={}
    for a,x in f['assets'].items():
        data=read(ROOT/d['plan']['inputs'][a]['data']['path']);times=[r[0] for r in data]
        rs=read_zip(ROOT/x['records_path'])['records'];valid=[];omitted=[]
        for r in rs:
            i=bisect_left(times,r['signal_time'])
            # Raw crossing audit begins at START, whereas price warmup begins
            # earlier. Exclude this short boundary from flip counts instead of
            # silently assigning zero missing warmup crossings. Also exclude gaps.
            if r['signal_time']<stamp(START)+15*STEP or i<15 or times[i]-times[i-15]!=15*STEP:
                omitted.append(r['trade_id'])
            else:valid.append(r)
        feat='flips_good';es=feature_compare(valid,feat,stamp(START),stamp(SPLIT));ls=feature_compare(valid,feat,stamp(SPLIT),stamp(END))
        ys={str(y):feature_compare(valid,feat,stamp(f'{y}-01-01T00:00:00Z'),stamp(f'{y+1}-01-01T00:00:00Z')) for y in range(2021,2026)}
        yy=sum(z['good_positive'] and z['good_better'] for z in ys.values())
        qualifies=all(z['sample_sufficient'] and z['good_positive'] and z['good_better'] for z in (es,ls)) and yy>=4
        x['features'][feat]=dict(early=es,later=ls,years=ys,positive_and_better_years=yy,passes_consistency_gate=qualifies,lookback_excluded=len(omitted))
        checks[a]=dict(original_trades=len(rs),valid_flip_history=len(valid),excluded_flip_history=omitted)
        m=x['full']['stats'];x['payoff_per_100']=dict(winning_contribution=m['sum_positive_pct']/m['trades']*100,
            losing_contribution=m['sum_negative_pct']/m['trades']*100,net=m['mean_return_pct']*100)
    f['lookback_checks']=checks
    f['presentation_notes']='Only flip-feature comparisons exclude initial15-bar crossing-audit warmup and gapped lookbacks. Original frozen path labels and trades unchanged; excluded IDs recorded.'
    freeze(DOCS/'presentation.json',f);freeze(DOCS/'feature-lookback-verification.json',checks)
    print('Finalized lookback checks',[(a,len(v['excluded_flip_history'])) for a,v in checks.items()])


if __name__=='__main__':main()
