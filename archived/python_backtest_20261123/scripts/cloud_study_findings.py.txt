"""Answer the original indicator questions from the completed saved experiments.

Reporting only: no new simulation, selection or strategy modification.
"""
from html import escape
from scripts.profit_protection_study import ROOT, read, save
from app.services.local_backtest_strategies import digest
from strategies.trend_cloud_comparison import Calculation

DOCS=ROOT/'docs/verification/cloud-cross-asset-20260911'


def pct(x):return f'{x:+,.2f}%'


def build(r):
    def m(k,asset='eth',period='full'):return r['results'][asset]['initial__'+k][period]
    def returns(k):return f'ETH六年 {pct(m(k)["return_pct"])}，BTC同六年 {pct(m(k,"btc","same_six")["return_pct"])}，BTC八年 {pct(m(k,"btc")["return_pct"])}'
    p=lambda k:dict(variant=k,record_indicators=False,long_only=False)
    single,channel=Calculation(p('ema31_cross')),Calculation(p('ema31_atr'))
    assert (single.kind,single.source,single.n,single.width.n,single.cloud_mult)==(channel.kind,channel.source,channel.n,channel.width.n,channel.cloud_mult)
    assert single.trigger_mult==0 and channel.trigger_mult==.99
    facts=[]
    def add(question,answer,evidence,limit,keys):
        facts.append(dict(question=question,answer=answer,evidence=evidence,limit=limit,versions=['initial__'+k for k in keys]))
    add('加通道作为买卖门槛，到底有没有用？',
        '在最早这套EMA31规则上有改善：交易明显减少，胜率提高，ETH收益增加，BTC亏损减少；BTC仍然亏损。',
        '单EMA31穿越：'+returns('ema31_cross')+'。加0.99倍ATR作为上下门槛：'+returns('ema31_atr')+'。',
        '比较的是穿过中心线就交易，与越过中心线±0.99倍ATR才交易。显示绿色/红色色带本身不会产生收益；这里同时改变进场和反向退出门槛，不能单独归功于入场过滤。此结果还不能替代后期EMA55策略的有无通道对照。',
        ['ema31_cross','ema31_atr'])
    add('ATR比平滑后的最高价减最低价更有用吗？',
        '没有看到ATR的额外收益优势；这两个版本的交易和结果几乎一样。通道门槛有帮助，不等于必须使用ATR。',
        'EMA31＋ATR14：'+returns('ema31_atr')+'。只把真实波幅换成每根最高价减最低价、保持相同平滑方法：'+returns('ema31_range')+'。',
        '这是可以直接配对的改动。结论只适用于本次数据和策略；不能推断ATR在所有市场无用，也不能从截图确认原作者一定用了ATR。',
        ['ema31_atr','ema31_range'])
    add('原作者给的脚本，ATR乘数0.5或1.5是否有效？',
        '0.5版在这批长周期数据里没有交易，无法产生截图中的那些交易点；1.5版没有表现出跨时间、跨币种的稳定盈利。',
        '0.5版ETH六年、BTC八年均为0笔。1.5版：'+returns('original_15')+'。',
        'BTC只取六年时1.5版赚钱，但延长到八年又亏损，结论很依赖起止时间。原Pine的TP/SL是标签，这里的模拟按反向信号退出，没有把标签当成实际订单。',
        ['original_05','original_15'])
    add('EMA31、EMA30、EMA29中哪个周期最好？',
        '这几个已测版本中，EMA31＋ATR14在ETH六年表现最好；仍不足以证明31是长期最优周期。',
        'EMA31（最高＋最低＋收盘价的平均）：'+returns('ema31_atr')+'。EMA30同种价格输入：'+returns('ema30_hlc3')+'。EMA29收盘价：'+returns('ema29_close')+'。',
        '这些早期版本除了周期，还改过突破门槛，EMA29还改了价格输入。因此不能把收益差距全部归因于31、30、29这几个周期数字。',
        ['ema31_atr','ema30_hlc3','ema29_close'])
    add('计算均线时用哪种价格更好？',
        'EMA30使用最高价与最低价的平均值，在ETH六年更好，在BTC却更差，没有跨币种一致的赢家。',
        'EMA30用（最高＋最低＋收盘）÷3：'+returns('ema30_hlc3')+'。只改成（最高＋最低）÷2：'+returns('ema30_hl2')+'。',
        '这两项周期和门槛相同，可以比较价格输入的影响。不能由ETH一边更好就认定另一种输入一直更好。',
        ['ema30_hlc3','ema30_hl2'])
    add('高低价EMA31通道本身是不是更好的策略？',
        '原始版本在ETH赚钱、BTC亏损；在这两个长区间里，它没有超过EMA31＋ATR候选。后续优化的高收益不能算到这个原始版本头上。',
        '高低价EMA31通道：'+returns('high_low_ema')+'。EMA31＋ATR14：'+returns('ema31_atr')+'。',
        '两版同时有中心价格输入、宽度平滑方法的区别。这不是单独证明ATR好坏的对照；要判断ATR，应看上面的EMA31＋平滑高低差版本。',
        ['high_low_ema','ema31_atr'])
    add('换成WMA或SMA，是否更好？',
        '测试过的WMA41和SMA28，在ETH六年、BTC八年都没有超过EMA31＋ATR14版本。',
        'WMA41＋ATR16：'+returns('wma41_atr')+'。SMA28＋ATR16：'+returns('sma28_atr')+'。',
        '各版周期、价格输入等并未全部保持相同，只能说明这些具体版本的表现，不能证明WMA或SMA这种算法天生较差。',
        ['wma41_atr','sma28_atr','ema31_atr'])
    add('用EMA26／36两条均线的间距做通道宽度，是否更好？',
        '没有看到这版双均线通道的优势：它在ETH六年收益较低，在BTC八年亏得更多，交易次数也更多。',
        'EMA26／36双均线通道：'+returns('dual_ema')+'。ETH做了16,030笔，BTC八年22,232笔；EMA31＋ATR版分别为5,768笔和7,721笔。',
        '这个比较同时涉及中心线与宽度定义；它支持保留双均线版的实际结果，不能单独证明某一种宽度公式在所有策略上更差。',
        ['dual_ema','ema31_atr'])
    early=[k for k in r['plan']['variants'] if k.startswith('initial__') and not r['plan']['variants'][k]['benchmark']]
    assert len(early)==12 and set(early)=={k for f in facts for k in f['versions']}
    channel_rows=[]
    for asset,period,label in [('eth','full','ETH六年'),('btc','same_six','BTC相同六年'),('btc','full','BTC八年')]:
        before,after=m('ema31_cross',asset,period),m('ema31_atr',asset,period)
        channel_rows.append(dict(period=label,before=before,after=after,
                                 trade_reduction_pct=(1-after['total_trades']/before['total_trades'])*100))
    return dict(questions=facts,channel_comparison=channel_rows,versions_covered=early,
                evidence_hashes={name:digest((ROOT/name).read_bytes()) for name in ['docs/verification/cloud-cross-asset-20260911/results.json','strategies/trend_cloud_comparison.py']},
                accounting='15分钟，初始1万元，每笔用当时全部资金，不加杠杆，不计手续费滑点。ETH六年为2020-09-10至2026-09-10；BTC八年为2018-09-10至2026-09-10。横向比较币种时另看相同六年。')


def html_block(findings):
    cards=[]
    for item in findings['questions']:
        cards.append('<article style="border-top:1px solid #e1e7ee;padding:18px 0"><h3>'+escape(item['question'])+'</h3><p><b>'+escape(item['answer'])+'</b></p><p>'+escape(item['evidence'])+'</p><p class="muted">'+escape(item['limit'])+'</p></article>')
    return '<section id="question-findings"><h2>当时想验证的问题，现在逐项回答</h2><p>以下覆盖全部12个早期版本。收益排名与问题结论都保留；能单独比较的条件与同时改了多个条件的版本分别说明。</p><p><a href="btc-parameters.html">查看这次BTC表现较好的具体参数，以及三个版本的完整对照</a></p>'+''.join(cards)+'</section>'


def write_findings(r):
    f=build(r)
    save(DOCS/'findings.json',f)
    paragraphs=['# 早期12个策略：逐项结论',f['accounting']]
    for x in f['questions']:
        paragraphs.extend(['## '+x['question'],x['answer'],x['evidence'],x['limit']])
    (DOCS/'FINDINGS.md').write_text('\n\n'.join(paragraphs)+'\n',encoding='utf-8')
    return f


if __name__=='__main__':
    f=write_findings(read(DOCS/'results.json'))
    print(f'Answered {len(f["questions"])} questions, covering all {len(f["versions_covered"])} initial strategy versions; no new simulations.')
