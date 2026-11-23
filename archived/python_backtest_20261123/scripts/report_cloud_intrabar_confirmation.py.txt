"""Short comparison from frozen intrabar results, with all assumptions visible."""
from app.infra.research_files import read_json
from scripts.cloud_intrabar_confirmation_study import OUT, VARIANTS


def pct(value):return f'{value:+,.2f}%'


def main():
    data=read_json(OUT/'results.json');r=data['results'];answers=read_json(OUT/'answers.json')
    text=['# ETH 六年：盘中突破与收盘确认', '',data['note'],'',
          '2020-09-10 至 2026-09-10 UTC；中心 EMA55、振幅平滑31、内线0.4倍、追价上限2倍；1%初始止损、2%启动／回吐50%的利润保护。', '',
          f'原版直接入场：**{pct(r["baseline"]["report"]["return_pct"])}**，{r["baseline"]["report"]["total_trades"]:,}笔。', '',
          '| 记住的突破价位 | 等收盘后入场 | 盘中入场：先后不明算止损 | 盘中入场：不利极值算入场前 |',
          '|---|---:|---:|---:|']
    for k,label,*_ in VARIANTS:
        text.append(f'| {label} | {pct(r[k+"_at_close"]["report"]["return_pct"])} | {pct(r[k+"_touch_0"]["report"]["return_pct"])} | {pct(r[k+"_touch_1"]["report"]["return_pct"])} |')
    text+=['', '## 结论','']
    for answer in answers:text+=[answer['conclusion'],'']
    text+=['## 逐笔统计','',
           '以下先列“先后不明也算止损”的结果。另一假设的完整统计保存在 results.json。','',
           '| 盘中入场版本 | 笔数 | 赚钱次数 | 亏钱次数 | 胜率 | 最大回撤 | 入场与止损先后不明的笔数 |',
           '|---|---:|---:|---:|---:|---:|---:|']
    for k,label,*_ in VARIANTS:
        v=r[k+'_touch_0'];t=v['report']
        text.append(f'| [{label}]({v["chart"]}) | {t["total_trades"]:,} | {t["wins"]:,} | {t["losses"]:,} | {t["win_rate"]:.2f}% | {t["max_drawdown_pct"]:.2f}% | {v["entry_bar_ambiguous"]} |')
    text+=['','原版及上表三个盘中版本各有1笔持平。两个执行假设不是收益严格上下界，也不是逐笔行情核实过的成交顺序。价格在开盘就越过触发线时按开盘价；不能回填更好的触发价。止损价格以实际入场价格计算。', '',
           '## 本地记录','',
           '[固定规则](RULES.md)、[计划](plan.json)、[统计与年度收益](results.json)、[原版完整重放核对](baseline-parity.json)、[同一信号的交易配对](attribution.json)。', '',
           '每个盘中版本有 `*-lineage.json`，保存原信号、挂单、成交时间和价格、入场根收盘是否还确认、同根止损先后是否不明、原版对应交易。项目运行目录保存完整代码、参数、行情、成交、资金曲线和日志。', '',
           f'研究 ID：`{data["study_id"]}`。原版与上轮三个收盘版本复用，新增六次是三个价位分别检查两种执行假设；没有按收益继续调参。','']
    content='\n'.join(text);path=OUT/'README.md'
    if path.exists() and path.read_text(encoding='utf-8')!=content:raise ValueError('旧报告保留，修改另存')
    if not path.exists():path.write_text(content,encoding='utf-8')
    print(path)


if __name__=='__main__':main()
