from pathlib import Path
from types import SimpleNamespace
import pytest
from app.domain.local_backtest import Bar, BarResult, Intent, TrendCloud, simulate
from app.domain.signal_comparison import compare_signals, compare_cloud
from app.services.local_backtest_strategies import load_strategy, validate_parameters


def test_observations_preserve_all_signals_and_next_open_execution():
    shared = {}
    def on_bar(c):
        shared['close'] = c.history[-1].close
        return BarResult(Intent('long'), shared, {'ready':True}, TrendCloud(110.,90.,True))
    bars=[Bar(i*60000,100+i,101+i,99+i,100+i,1) for i in range(4)]
    result=simulate(bars,SimpleNamespace(on_bar=on_bar),{},warmup=1,step_ms=60000)
    assert [r['values']['close'] for r in result['indicators']] == [101,102,103]
    assert [r['timestamp'] for r in result['indicators']] == [60000,120000,180000]
    assert [r['status'] for r in result['signals']] == ['executed','ignored_same_side','unexecuted_end']
    assert result['fills'][0]['timestamp'] == 120000
    assert result['fills'][0]['price'] == 102


@pytest.mark.parametrize('value',[float('nan'),float('inf'),True,'100'])
def test_invalid_observation_reports_bar(value):
    with pytest.raises(ValueError, match='K 线 60000'):
        simulate([Bar(60000,100,100,100,100,1)],SimpleNamespace(on_bar=lambda c: BarResult(values={'bad':value})),{},warmup=0)


def sample_result(signals):
    return {'run':{'id':'test','config':{'start':'1970-01-01T00:00:00Z','end':'1970-01-01T00:10:00Z'}},
        'signals':signals,'fills':[],'indicators':[{'timestamp':60000,'values':{'RSI':55},'checks':{'RSI<40':False}}]}


def test_compare_counts_missing_extra_direction_and_uses_signal_bars():
    actual=[{'timestamp':60000,'decision_time':120000,'action':'long','status':'ignored_same_side'},
            {'timestamp':180000,'action':'long'}]
    refs={'signals':[{'timestamp':'1970-01-01T08:01:00+08:00','action':'long'}, {'timestamp':180000,'action':'short'}]}
    result=compare_signals(sample_result(actual),refs,60000)
    assert (result['matched_count'],result['missing_count'],result['extra_count']) == (1,1,1)
    assert not result['all_signals_match']
    assert result['reference_observations'][0]['observation']['values']['RSI']==55


def test_tolerance_matching_does_not_consume_event_needed_by_later_reference():
    actual=[{'timestamp':0,'action':'long'},{'timestamp':120000,'action':'long'}]
    refs={'signals':[{'timestamp':60000,'action':'long'},{'timestamp':180000,'action':'long'}]}
    assert compare_signals(sample_result(actual),refs,60000,1)['all_signals_match']
    assert compare_signals(sample_result(actual),refs,60000,0)['matched_count']==0


def test_comparison_rejects_naive_time_and_outside_window():
    for stamp in ('1970-01-01T00:01:00', 600000):
        with pytest.raises(ValueError):
            compare_signals(sample_result([]),{'signals':[{'timestamp':stamp,'action':'long'}]},60000)


def test_adaptive_cloud_is_causal_and_warmup_is_identical_to_sequential_processing():
    path=Path(__file__).parents[1]/'strategies/adaptive_cloud.py'
    module,meta=load_strategy(path)
    p=validate_parameters(meta,{'mode':'cross','source':'hlc3','ema_length':31,'cloud_mult':.45})
    bars=[Bar(i*900000,100+(i%9),105+(i%9),98+(i%9),103+(i%9),100+i) for i in range(720)]
    sequential=module.Calculation(p)
    expected=[sequential.update(b) for b in bars]
    # First engine call must prime from existing warmup, retaining indicator state.
    actual=simulate(bars,module,p,warmup=650,step_ms=900000)
    assert actual['indicators'][0]['values'] == expected[650].values
    assert actual['indicators'][-1]['values'] == expected[-1].values
    module2,_=load_strategy(path)
    prefix=simulate(bars[:700],module2,p,warmup=650,step_ms=900000)
    assert prefix['indicators'] == actual['indicators'][:50]
    assert [(s['timestamp'],s['action']) for s in prefix['signals']] == [(s['timestamp'],s['action']) for s in actual['signals'] if s['timestamp']<700*900000]


def test_cloud_comparison_interpolates_screen_coordinates_on_log_axis():
    from math import exp
    observations=[{'timestamp':0,'cloud':{'upper':exp(2),'lower':exp(1)}},
                  {'timestamp':60000,'cloud':{'upper':exp(4),'lower':exp(3)}}]
    reference={'price_to_pixel_log':[-1,0],'cloud_samples':[{'timestamp':30000,'upper_y':-3,'lower_y':-2}]}
    result=compare_cloud(observations,reference,60000)
    assert result['sample_count']==1
    assert result['rmse_px']==pytest.approx(0,abs=1e-12)
    observations[1]['timestamp']=120000
    assert compare_cloud(observations,reference,60000)['unavailable_count']==1


def test_cloud_only_observations_do_not_create_orders():
    result=simulate([Bar(0,100,100,100,100,1)],SimpleNamespace(on_bar=lambda c: BarResult(cloud=TrendCloud(102,98,True))),{},warmup=0)
    assert result['signals']==result['fills']==result['trades']==[]
    assert len(result['indicators'])==1
