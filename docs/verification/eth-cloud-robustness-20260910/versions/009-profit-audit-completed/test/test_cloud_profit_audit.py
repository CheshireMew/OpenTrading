import pytest
from scripts.cloud_profit_audit import compounded, inspect_trades


def test_compounding_uses_trade_returns_not_dollar_profit():
    assert compounded([{'return_pct':10,'profit':100},{'return_pct':-10,'profit':-100}]) == pytest.approx(-1)


def test_winner_removal_is_ranked_by_percentage_and_retains_losses():
    trades=[]
    capital=10000
    daily=[]
    for i,r in enumerate([20,5,-10]):
        profit=capital*r/100
        trades.append(dict(return_pct=r,profit=profit,side='long',entry_time=i*86400000,exit_time=(i+1)*86400000,
                           entry_price=100,exit_price=100+r,duration_minutes=30,exit_reason='signal'))
        capital+=profit
        daily.append(dict(date=f'2026-01-0{i+1}',equity=capital))
    result=inspect_trades(trades,daily,13.4)
    assert result['stress'][0]['remaining_compounded_return_pct']==pytest.approx(-5.5)
    assert result['minimum_best_winners_zeroed_to_remove_net_profit']==1
    assert result['summary']['losses']==1
    assert result['duration']['up_to_1h']['trades']==3


def test_audit_rejects_mismatched_original_return():
    with pytest.raises(AssertionError):
        inspect_trades([{'return_pct':1,'profit':100}],[],20)
