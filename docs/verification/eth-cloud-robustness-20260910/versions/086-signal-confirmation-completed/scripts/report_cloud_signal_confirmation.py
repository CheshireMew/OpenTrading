"""Render saved confirmation comparison and user-facing explanations."""
from app.infra.research_files import read_json
from scripts.cloud_signal_confirmation_study import OUT


def pct(x):
    return f'{x:+,.2f}%'


def main():
    data=read_json(OUT/'results.json'); answers=read_json(OUT/'answers.json')
    results=data['results']; order=['baseline','close_unlimited','wick_unlimited','body_two_bars']
    text=['# ETH：先积累信号，再等 K 线确认', '', data['note'], '',
        '这是在原版上单独增加确认，没有叠加宽窄切换、波动止损或止损后补仓。1% 初始止损、2% 启动／回吐 50% 的利润保护和原反向平仓继续生效。', '',
        '| 版本 | 六年累计收益 | 笔数 | 赚钱次数 | 亏钱次数 | 胜率 | 最大回撤 |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for key in order:
        v=results[key];r=v['report']
        text.append(f'| [{v["name"]}]({v["chart"]}) | {pct(r["return_pct"])} | {r["total_trades"]} | {r["wins"]} | {r["losses"]} | {r["win_rate"]:.2f}% | {r["max_drawdown_pct"]:.2f}% |')
    text+=['', '原版另有 1 笔持平。', '', '## 结论', '']
    for a in answers: text += [a['conclusion'], '']
    text += ['按相同原信号配对，收盘确认版有 6,761 笔可比较，其中 6,746 笔入场价更不利（做多更高、做空更低）。平均价差约 0.291%；这批交易原本平均每笔赚 0.310%，延后入场后平均赚 0.068%。这不是手续费，而是等待价格确认付出的成交价差；退出时机、止损和利润保护也会随入场改变，不能把全部收益差直接归因于这个价差。全仓复利进一步放大了长期累计结果的差距。[配对记录](entry-price-attribution.json)。', '']
    text+=['## 每年收益', '', '2020 年从 9 月 10 日起，2026 年截至 9 月 10 日；其他为完整自然年。按连续账户年末权益计算。', '',
        '| 版本 | 2020（部分） | 2021 | 2022 | 2023 | 2024 | 2025 | 2026（部分） |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for key in order:
        v=results[key]; text.append('| '+v['name']+' | '+' | '.join(pct(y['return_pct']) for y in v['annual'])+' |')
    text+=['', '## 等待与原信号去向', '',
        '等待根数从信号 K 线之后算：等 1 根，即第 2 根收盘确认，然后下一根开盘交易。历史时间缺口按实际观测 K 线计数。', '',
        '| 版本 | 平均等几根 | 中位数 | 最长等待 | 等超过2根才入场 | 旧亏单确认后赚 | 旧赚单确认后亏 |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for key in order[1:]:
        v=results[key]; lineage=v['lineage_summary']
        text.append(f'| {v["name"]} | {v["mean_wait_bars"]:.2f} | {v["median_wait_bars"]:.0f} | {v["max_wait_bars"]} | {v["wait_over_2_bars"]} | {lineage["original_loser_now_wins"]} | {lineage["original_winner_now_loses"]} |')
    text += ['', '上表后两列只比较来自同一原始信号的实际交易，未确认、不合格或持仓冲突的信号不在这两列中。延后入场改变了成交价、止损价和盈利保护的启动位置，不能沿用原单盈亏，也不能把未使用信号都当成成功过滤。', '',
        '| 版本 | 未使用的原版盈利信号 | 未使用的原版亏损信号 | 因反向信号取消等待次数 | 到期次数 |',
        '|---|---:|---:|---:|---:|']
    for key in order[1:]:
        v=results[key]; old=v['unmatched_original']; c=v['event_counts']
        text.append(f'| {v["name"]} | {old["wins"]} | {old["losses"]} | {c.get("反向取消旧等待",0)} | {c.get("等待过期",0)} |')
    text += ['', '## 保存与复核', '',
        '[固定规则](RULES.md)、[完整参数计划](plan.json)、[完整统计](results.json)、[原版逐笔一致性](baseline-parity.json)。', '',
        '每个确认版本另有 `*-lineage.json`：每笔交易关联原信号时间、确认时间、确认价、等待根数、实际入场价、原版对应交易及盈亏。`*-events.json` 保存积累、取消、过期和确认事件。逐笔检查了下一开盘成交、单次消费、没有跨过相反信号、确认价正确、有限版本未超期。', '',
        f'研究 ID：`{data["study_id"]}`。行情、代码、引擎、完整逐笔和运行日志均在 `.heimdall_runtime/local_backtests/<run_id>/`，表内名称可打开项目图表。', '',
        '有限版本同时使用实体价位和两根期限；与另两个版本的差异不能全部归因于期限。这轮没有搜索新参数，没有改现有 Pine，不保证历史表现延续。', '']
    path=OUT/'README.md';content='\n'.join(text)
    if path.exists() and path.read_text(encoding='utf-8')!=content:
        raise ValueError('旧报告保留，修改应另存修订')
    if not path.exists(): path.write_text(content,encoding='utf-8')
    print(path)


if __name__=='__main__': main()
