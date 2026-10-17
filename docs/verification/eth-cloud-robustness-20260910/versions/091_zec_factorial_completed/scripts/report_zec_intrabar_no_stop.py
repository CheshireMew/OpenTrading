"""Readable results from the four saved ZEC runs; no new simulations."""
from scripts.zec_intrabar_no_stop_study import OUT, CASES
from app.infra.research_files import read_json
from scripts.cloud_width_reentry_study import keep


def main():
    data=read_json(OUT/'results.json'); r=data['results']; b=r['baseline']; e=r['entry_only']; s=r['no_stop_only']; c=r['combined']
    pct=lambda x:f'{x:+,.2f}%'
    conclusions={
        'entry':f"保留1%止损，只加第2或第3根盘中突破信号实体确认，七年收益从{pct(b['report']['return_pct'])}变为{pct(e['report']['return_pct'])}。交易从{b['report']['total_trades']}笔减少到{e['report']['total_trades']}笔，胜率从{b['report']['win_rate']:.2f}%提高到{e['report']['win_rate']:.2f}%。本次有帮助。",
        'stop':f"原入场不动，只取消固定止损，七年收益降到{pct(s['report']['return_pct'])}。胜率升到{s['report']['win_rate']:.2f}%，但平均亏损单从{pct(b['mean_loss_pct'])}扩大到{pct(s['mean_loss_pct'])}，最大回撤从{b['report']['max_drawdown_pct']:.2f}%扩大到{s['report']['max_drawdown_pct']:.2f}%。本次不应取消固定止损。",
        'combined':f"两项一起改的七年收益是{pct(c['report']['return_pct'])}，超过原版，低于只改入场。无论是否保留止损，盘中确认都提高本次收益；无论是否加确认，取消固定止损都降低本次收益。改善来自入场确认，取消固定止损拖累结果。",
        'execution':f"已核对两种确认版共{e['checked_entries']+c['checked_entries']}笔，每个原信号最多成交一次，且只在信号后的第1或第2根成交（把信号本身算第1根，就是第2或第3根）。两个取消止损版本的初始止损退出均为0，利润保护和反向退出仍实际发生。保留止损的盘中确认版有{e['entry_bar_ambiguous']}笔同根先后不明，全部按入场后再触发止损计入，未挑有利顺序。"
    }
    answers=[]
    for q,conclusion in conclusions.items():
        evidence=['artifact:results','case:baseline']
        evidence += ['case:'+x for x in {'entry':['entry_only'],'stop':['no_stop_only'],'combined':['entry_only','no_stop_only','combined'],'execution':['entry_only','combined']}[q]]
        answers.append(dict(question=q,conclusion=conclusion,evidence=evidence,
            scope='ZEC/USDT 30分钟，2019-09-10至2026-09-10，EMA144，固定四组比较。',
            limitation='已见历史，全仓复利且不计成本；有固定止损的盘中成交先后采用保守假设，旧行情缺失82根保持空档。不能推断实盘或其他币种表现。',
            decision='reject' if q=='stop' else 'keep'))
    keep(OUT/'answers.json',answers)
    text=['# ZEC 七年：入场确认有帮助，取消固定止损反而拖累',
        '本次改的是此前完整七年收益最高的原EMA通道版本：ZEC/USDT、30分钟、EMA144。最近两年收益最高的EMA55不是这一个：EMA55最近两年+1,056.97%，相同七年只有+15.64%；EMA144七年+125.86%。范围在本次运行前已按用户纠正，不再测试两年冠军。',
        '四组统一为2019年9月10日至2026年9月10日，使用同一份币安现货价格数据模拟多空，每笔当时全部资金复投，不加杠杆，不计手续费和滑点。',
        '| 版本 | 七年累计收益 | 总交易 | 赚钱 | 亏钱 | 持平 | 胜率 | 最大回撤 |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for cid,name,_,_ in CASES:
        v=r[cid]['report']
        text.append(f"| {name} | {pct(v['return_pct'])} | {v['total_trades']} | {v['wins']} | {v['losses']} | {v['breakeven']} | {v['win_rate']:.2f}% | {v['max_drawdown_pct']:.2f}% |")
    text += [conclusions[x] for x in ('entry','stop','combined')]
    text += ['原参数保持为：高低中价EMA144，振幅为每根高低差的EMA31，中心线±1.2倍振幅产生原入场信号，距离超过3倍振幅不追。浮盈达到1%开始保护，允许回吐最高浮盈35%。固定止损开关分别为1%或关闭。',
        '新确认规则：原信号所在K线算第1根，只允许第2或第3根盘中突破该信号实体。做多突破实体上沿，做空突破实体下沿，不用等收盘。未成交遇到反向信号就取消原等待，按新方向重新计数。持同向仓不重复开仓；反向平仓仍按原收盘信号、下一根开盘执行，不等待反向入场确认。确认还保留原通道方向和不追价限制，详细成交价规则见RULES.md。',
        '| 版本 | 平均盈利单 | 平均亏损单 | 最差单笔 | 平均持仓 | 持仓中位数 |',
        '|---|---:|---:|---:|---:|---:|']
    for cid,name,_,_ in CASES:
        v=r[cid];text.append(f"| {name} | {pct(v['mean_win_pct'])} | {pct(v['mean_loss_pct'])} | {pct(v['worst_trade']['return_pct'])} | {v['report']['average_duration_minutes']/60:.2f}小时 | {v['median_hold_hours']:.2f}小时 |")
    text += ['每年收益来自同一连续账户，年底不重置仓位。2019只含9月10日之后，2026截至9月10日；各年收益不能直接相加。',
             '| 年份 | 原版 | 只改入场 | 只取消止损 | 两项一起改 |','|---|---:|---:|---:|---:|']
    for i,year in enumerate(b['annual']):
        text.append('| '+year['label']+' | '+' | '.join(pct(r[cid]['annual'][i]['return_pct']) for cid,_,_,_ in CASES)+' |')
    text += [f"只改入场的版本在2026年仍亏{abs(e['annual'][-1]['return_pct']):.2f}%，不能把七年总收益改善说成每年稳定盈利。",
        conclusions['execution'],
        '原版与旧存档的4706笔交易、全部信号、逐根权益和汇总完全一致。新旧策略均保留；28项相关测试通过。为使用项目公开回测入口，将已有研究数据对应的ZEC/USDT补入币种目录；未改变数据源或下载新行情。',
        '数据和参数：[规则](RULES.md)、[原版选择](selection.json)、[原版重放核对](baseline-parity.json)、[四组结果](results.json)、[行情快照](data.json)、[有止损确认逐笔核对](entry_only-lineage.json)、[无止损确认逐笔核对](combined-lineage.json)。',
        '每次运行都保存完整strategy.py、engine.py、config.json、metadata.json、data.json、result.json和run.log；result.json包含逐笔交易、成交、信号、K线指标、权益和保护价，项目数据库也保留了这些记录。']
    for cid,name,_,_ in CASES:
        v=r[cid];text.append(f"- [{name}的项目图表]({v['chart']})；运行目录 `.heimdall_runtime/local_backtests/{v['run_id']}`。")
    blocks=[]
    for line in text:
        if blocks and ((line.startswith('|') and blocks[-1].startswith('|')) or
                       (line.startswith('- ') and blocks[-1].startswith('- '))):
            blocks[-1]+='\n'+line
        else:
            blocks.append(line)
    content='\n\n'.join(blocks)+'\n'
    path=OUT/'README.md'
    if path.exists() and path.read_text(encoding='utf8')!=content:
        previous=path.read_text(encoding='utf8')
        if ''.join(previous.split())!=''.join(content.split()):
            raise ValueError('不覆盖已有报告结论')
        archive=OUT/'README-before-table-format.md'
        if not archive.exists(): archive.write_text(previous,encoding='utf8')
    path.write_text(content,encoding='utf8')
    print('四个问题的结论与本地记录已整理')


if __name__=='__main__': main()
