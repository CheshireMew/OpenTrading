"""Publish the fixed comparison and explicit question answers, no new runs."""
from app.infra.research_files import read_json
from app.infra.db import build_database_runtime
from app.services.local_backtest_service import LocalBacktestService
from app.services.research_study_service import ResearchStudyService
from config import settings
from scripts.cloud_width_reentry_study import OUT, keep


def percent(v):
    return f'{v:+,.2f}%'


def main():
    data, answers = read_json(OUT/'results.json'), read_json(OUT/'answers.json')
    results, identifier = data['results'], data['study_id']
    ordered = sorted(results.values(), key=lambda v: v['report']['return_pct'], reverse=True)
    lines = ['# ETH 通道入场、止损与补仓：固定规则对照', '', data['note'], '',
        '所有参数在计算前固定；没有搜索新参数。原版完整逐笔、信号和资金曲线重算一致。', '',
        '| 版本 | 六年累计收益 | 交易数 | 赚钱次数 | 亏钱次数 | 胜率 | 最大回撤 |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for row in ordered:
        r = row['report']
        lines.append(f'| [{row["name"]}]({row["chart"]}) | {percent(r["return_pct"])} | {r["total_trades"]} | '
            f'{r["wins"]} | {r["losses"]} | {r["win_rate"]:.2f}% | {r["max_drawdown_pct"]:.2f}% |')
    lines += ['', '原版另有 1 笔持平。收益采用全仓复利，百分比差值不能简单解释成新增交易赚了多少钱。', '', '## 每个问题的结论', '']
    for answer in answers:
        lines += [answer['conclusion'], '']
    lines += ['## 每年收益', '', '2020 年从 9 月 10 日起，2026 年截至 9 月 10 日；其余为完整自然年。按照连续账户的年末权益计算。', '',
        '| 版本 | 2020（部分） | 2021 | 2022 | 2023 | 2024 | 2025 | 2026（部分） |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for row in ordered:
        lines.append('| '+row['name']+' | '+' | '.join(percent(x['return_pct']) for x in row['annual'])+' |')
    lines += ['', '## 少了哪些原版交易，以及新增了哪些交易', '',
        '按入场时间和方向配对。未出现的原版交易可能被过滤、推迟到另一根入场，或改版当时仍在持仓；不能把这些数量当成真正漏掉的整段行情。同一入场的退出时机也可能改变，下面两组不能直接相减代替完整回测。', '',
        '| 版本 | 未出现的原版赚单 | 未出现的原版亏单 | 新增交易赚单 | 新增交易亏单 | 相同入场但退出改变 |',
        '|---|---:|---:|---:|---:|---:|']
    for key, row in results.items():
        if key == 'baseline':
            continue
        a, b = row['omitted_baseline'], row['added_actual']
        lines.append(f'| {row["name"]} | {a["wins"]} | {a["losses"]} | {b["wins"]} | {b["losses"]} | {row["same_entry_changed_exit"]} |')
    lines += ['', '## 补仓和随宽度止损', '',
        '| 版本 | 补仓次数 | 补仓赚单 | 补仓亏单 | 补仓平均每笔收益 | 初始止损范围 | 平均初始止损 |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for key in ('retry', 'width_stop', 'width_stop_retry', 'all_combined'):
        row = results[key]
        retry, stop = row['retries'], row['entry_stop_pct']
        mean = percent(retry['mean_return_pct']) if retry['trades'] else '—'
        lines.append(f'| {row["name"]} | {retry["trades"]} | {retry["wins"]} | {retry["losses"]} | {mean} | '
            f'{stop["min"]:.2f}%～{stop["max"]:.2f}% | {stop["mean"]:.2f}% |')
    lines += ['', '全部补仓逐笔检查了真实初始止损、方向、收盘外线条件及下一根成交。持仓期间不重复发送同向开仓；反向新突破会重置补仓额度。同一方向的新普通突破不重置额度。', '',
        '9 月 11 日的示例：20:30 多单仍止损 −1%；只加补仓的版本于 20:45 以 2493.97 再次做多，23:45 利润保护在约 2579.98 平仓，补仓收益 +3.45%。这是北京时间，数据为 Binance 现货；示例在六年比较结束日期之后，不参与排名。', '',
        '随宽度止损使用相对最近一天的宽度，限制为 0.5%～2%；持续高波动很多天后，参照也升高。它不代表已经验证了所有波动止损或 ATR 止损方法。', '',
        '## 本地复查', '',
        '[完整规则](RULES.md)、[固定参数计划](plan.json)、[统计数据](results.json)、[原版一致性核查](baseline-parity.json)、[9 月 11 日补仓示例](sept11-reentry-example.json)。', '',
        f'研究 ID：`{identifier}`。每个表格版本名可以打开项目原有 K 线图。所有行情、策略、引擎、逐笔交易及日志分别存放在 `.opentrading_runtime/local_backtests/<run_id>/`；结果 JSON 保存 run_id 和校验哈希。', '',
        '这是已经看过的 ETH 历史对照，不能据此声称未来或其他交易对仍有效。此轮到此停止，不继续细调参数追求新冠军。', '']
    path = OUT/'README.md'
    content = '\n'.join(lines)
    if path.exists() and path.read_text(encoding='utf-8') != content:
        raise ValueError('已有结论不可覆盖，请另建修订')
    if not path.exists():
        path.write_text(content, encoding='utf-8')
    db = build_database_runtime(settings)
    studies = ResearchStudyService(LocalBacktestService(db))
    try:
        if studies.state(identifier)[4] == 'completed':
            print('研究已经完成')
            return
        for name, file in [('rules', 'RULES.md'), ('results', 'results.json'), ('baseline-parity', 'baseline-parity.json'),
                           ('sept11-example', 'sept11-reentry-example.json'), ('conclusions', 'README.md')]:
            if name not in studies.state(identifier)[2]:
                studies.attach(identifier, name, OUT/file, name)
        for answer in answers:
            if answer['question'] not in studies.state(identifier)[1]:
                studies.answer(identifier, answer)
        summary = studies.complete(identifier)
        keep(OUT/'completion.json', summary)
        print(summary['status'], summary['cases'], '未答问题', len(summary['unanswered']))
    finally:
        db.dispose()


if __name__ == '__main__':
    main()
