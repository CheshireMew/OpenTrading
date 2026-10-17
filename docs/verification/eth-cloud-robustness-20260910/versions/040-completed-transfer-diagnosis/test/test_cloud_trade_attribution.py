from datetime import datetime, timezone
from types import SimpleNamespace
from math import isclose
import numpy as np
from app.domain.cloud_trade_attribution import compound, summary, calendar_returns, features, annotate
from app.domain.local_backtest import Intent
from scripts.cloud_transfer_diagnosis import direction_strategy
from scripts.alt_cloud_parameter_study import ETH_PARAMETERS


def test_compounded_side_groups_multiply_instead_of_adding():
    def t(r):return dict(return_pct=r,profit=r,duration_minutes=60)
    long=summary([t(10),t(-5)]);short=summary([t(-3)])
    assert isclose(compound([10,-5,-3]),1.365)
    assert isclose((1+long['compound_return_pct']/100)*(1+short['compound_return_pct']/100)-1,.01365)
    assert long['wins']==1 and long['losses']==1


def test_calendar_uses_open_position_equity_at_boundary_not_trade_close_year():
    start=int(datetime(2024,12,31,23,45,tzinfo=timezone.utc).timestamp()*1000)
    eq=[dict(timestamp=start,equity=10000),dict(timestamp=start+900000,equity=11000),dict(timestamp=start+1800000,equity=9900)]
    rows=[[start,100,111,99,110,1],[start+900000,110,111,98,99,1]]
    result=calendar_returns(eq,rows,[('2024',start,start+900000),('2025',start+900000,start+1800000)])
    assert isclose(result[0]['return_pct'],10)
    assert isclose(result[1]['return_pct'],-10)
    assert isclose(compound(x['return_pct'] for x in result),-1)


def test_features_do_not_see_entry_candle_or_future_spike():
    rows=[[i*900000,100,101,99,100+i*.001,10] for i in range(110)]
    trade=dict(entry_time=100*900000,return_pct=-1,profit=-100,duration_minutes=0,profit_peak_pct=0)
    before=annotate([trade],features(rows,ETH_PARAMETERS),ETH_PARAMETERS)[0]
    rows[100]=[100*900000,100,900,1,800,100000]
    after=annotate([trade],features(rows,ETH_PARAMETERS),ETH_PARAMETERS)[0]
    for f in ('width_pct','entry_efficiency96','entry_distance','activation_widths','body'):
        assert before[f]==after[f]
    assert after['recorded_peak_bucket']=='under_05'


def test_direction_gate_keeps_opposite_exit_and_does_not_reverse():
    module=SimpleNamespace(on_bar=lambda c:Intent('short',stop_loss_pct=1))
    strategy=direction_strategy(module,'long')
    assert strategy.on_bar(SimpleNamespace(position=None)) is None
    assert strategy.on_bar(SimpleNamespace(position={'side':'long'})).action=='close'


def test_direction_gate_preserves_allowed_entry_protection():
    intent=Intent('long',stop_loss_pct=2)
    strategy=direction_strategy(SimpleNamespace(on_bar=lambda c:intent),'long')
    assert strategy.on_bar(SimpleNamespace(position=None)) is intent


def test_volume_feature_uses_preceding_twenty_bars():
    rows=[[i*900000,100,101,99,100,10] for i in range(100)]
    rows[50][-1]=100
    f=features(rows,ETH_PARAMETERS)
    assert f['volume_ratio'][50]==10
    assert np.isclose(f['volume_ratio'][51],10/14.5)
