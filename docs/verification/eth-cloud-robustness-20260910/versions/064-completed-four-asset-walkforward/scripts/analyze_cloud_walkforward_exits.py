"""Describe paired exit changes on identical entries; never selects parameters."""
from scripts.cloud_walkforward_study import ROOT,DOCS,ASSETS,METHODS,read,read_zip,freeze


def compare(first,second,only_reverse=False):
    def key(t):return t['fold'],t['entry_time'],t['side'],t['entry_price']
    later={key(t):t for t in second['trades']}
    assert len(later)==len(second['trades'])
    pairs=[]
    eligible=[t for t in first['trades'] if not only_reverse or t['exit_reason'] in ('reversal','signal')]
    for t in eligible:
        if key(t) not in later:continue
        u=later[key(t)]
        pairs.append(dict(fold=t['fold'],side=t['side'],entry_time=t['entry_time'],entry_price=t['entry_price'],
            first_exit_time=t['exit_time'],second_exit_time=u['exit_time'],first_exit_reason=t['exit_reason'],second_exit_reason=u['exit_reason'],
            first_return_pct=t['return_pct'],second_return_pct=u['return_pct'],
            improvement_points=u['return_pct']-t['return_pct'],delay_hours=(u['duration_minutes']-t['duration_minutes'])/60))
    n=len(pairs);ordered=sorted(pairs,key=lambda x:x['improvement_points'])
    return dict(eligible_first_trades=len(eligible),matched=n,unmatched=len(eligible)-n,
                improved=sum(x['improvement_points']>1e-8 for x in pairs),worsened=sum(x['improvement_points']< -1e-8 for x in pairs),
                unchanged=sum(abs(x['improvement_points'])<=1e-8 for x in pairs),
                mean_improvement_points=sum(x['improvement_points'] for x in pairs)/n if n else None,
                mean_delay_hours=sum(x['delay_hours'] for x in pairs)/n if n else None,
                reverse_loss_became_profit=sum(x['first_return_pct']<0<x['second_return_pct'] for x in pairs),
                profit_became_loss=sum(x['second_return_pct']<0<x['first_return_pct'] for x in pairs),
                worst_examples=ordered[:3],best_examples=ordered[-3:][::-1])


def main():
    results=read(DOCS/'results.json')['results'];output={}
    for a in ASSETS:
        output[a]={}
        for pool,policies in results[a].items():
            records={}
            for m in METHODS:
                traces={risk:read_zip(ROOT/policies['fixed_'+m+('' if risk=='r0' else '_'+risk)]['trace_path']) for risk in ('r0','r2','a2r1','a2r2','a3r1','a3r2')}
                records[m]=dict(
                    confirmation={label:compare(traces[one],traces[two],True) for label,one,two in [('percent','r0','r2'),('atr2','a2r1','a2r2'),('atr3','a3r1','a3r2')]},
                    initial_stop={'atr2':compare(traces['r0'],traces['a2r1']), 'atr3':compare(traces['r0'],traces['a3r1'])})
            output[a][pool]=records
    freeze(DOCS/'exit-pair-diagnosis.json',dict(status='completed',results=output,
        interpretation='Fixed originalETH1h entries only. Match same half-year, entry timestamp, side and price. Compare per-trade percentage outcomes, not actual cash contribution. Confirmation comparison only includes baseline reversal/signal exits with matching entries; unmatched trades are reported. Holding times approximate to candle; examples are descriptive, never used for selection.'))
    print('Matched-entry stop and confirmation diagnoses saved for all4 assets,5 protections,2 periods.')


if __name__=='__main__':main()
