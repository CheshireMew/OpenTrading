"""Render saved results; never rerun or select extra parameters."""
import json
from pathlib import Path

OUT=Path(__file__).resolve().parent
data=json.loads((OUT/'results.json').read_text(encoding='utf-8'))
rows=data['rows']
best=max(rows,key=lambda r:r['report']['return_pct'])
baseline=rows[0]
text=['# ETH：5分钟利润保护与止损确认','',
      f"9组完成。本轮历史累计收益最高：{best['name']}，{best['report']['return_pct']:+,.2f}%。所有结果完整保留，未替换 Pine。",'',
      'ETH/USDT，Binance现货价格；15分钟产生原入场/反向信号，利润保护每5分钟收盘更新、下一根生效。初始止损延后版本也按下一根5分钟K线判断。止损后区域限制仍按止损所在15分钟K线范围，与上一轮一致。固定止损阈值和止损方式各组与上一轮相同。','',
      '六年区间为2020-09-10至2026-09-18 UTC，最近两年为2024-09-18至2026-09-18的连续账户权益切片；全仓、不加杠杆、盈亏计入下笔本金，不计手续费和滑点。','',
      '## 与上一轮逐组比较','',
      '|规则|原15分钟处理：全期收益|本轮5分钟处理：全期收益|本轮近两年收益|本轮胜率|本轮最大回撤|本轮最差单笔|',
      '|---|---:|---:|---:|---:|---:|---:|']
for r in rows:
    a=r['report'];prior=r['prior_15m']['report']
    text.append(f"|{r['name']}|{prior['return_pct']:+,.2f}%|{a['return_pct']:+,.2f}%|{r['recent_two_years']['return_pct']:+,.2f}%|{a['win_rate']:.2f}%|{a['max_drawdown_pct']:.2f}%|{r['worst_trade']['return_pct']:.2f}%|")
text+=['','上表最大回撤统一使用15分钟收盘权益，便于与上一轮比较；结果文件另外保存5分钟收盘回撤。最近两年已被研究过，不称为未见样本验证。','',
       '## 交易次数与截图段','',
       '|规则|盈利笔数|亏损笔数|保本|最长连续亏损|持仓≤15分钟的亏损单|截图段权益变化|','|---|---:|---:|---:|---:|---:|---:|']
for r in rows:
    a=r['report']
    text.append(f"|{r['name']}|{a['wins']}|{a['losses']}|{a['breakeven']}|{r['trade_statistics']['max_consecutive_losses']}|{r['short_losing_trades_15m_or_less']}|{r['screenshot_period']['return_pct']:+.2f}%|")
text+=['','截图段统一为2026-09-16 12:00至09-17 21:00 UTC+8，按连续账户权益，包含区间开始已有仓位的浮盈变化，不是仅把某几笔交易相乘。','',
       '## 核对与保存','',
       '旧版固定止损本来就按5分钟数据检查触价。这次“触及即止损”组实际只改变利润保护更新频率；延后版本同时把等待时间从15分钟改为5分钟。因此延后版本相对上一轮的变化不能全部归因于其中一个因素。',
       '从上一轮原版的冻结行情建立本批次，主周期和细周期数据哈希逐组核对一致。211,007根15分钟K线有匹配的5分钟数据，3根继续按原约定回退并保留标记；不能把这3根或5分钟内部未决先后说成精确到tick的成交。',
       '110项相关检查通过，覆盖默认15分钟行为、5分钟确认、跨15分钟边界等待、细周期收盘退出时间和金额、利润保护先后与旧策略一致性。旧策略v1保留，新规则由项目公开引擎v11与策略trend_cloud_stop_confirmation_v2提供，批量参数服务实际运行；分析文件只读取保存结果。',
       '本目录的plan.json、请求、批次编号、before/、frozen/、逐笔文件、results.json和源码哈希保存版本与证据。results.json还包含逐年、原版逐项比较、最差交易、成交数据覆盖与原始结果路径。','']
batches=json.loads((OUT/'batches.json').read_text())
text.append(f"项目页面：[8组1%对照](http://127.0.0.1:4173/research/parameter-sweeps?sweep={batches['matrix']})、[2%对照](http://127.0.0.1:4173/research/parameter-sweeps?sweep={batches['fixed2']})。")
(OUT/'README.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
print('Report saved:',OUT/'README.md')
