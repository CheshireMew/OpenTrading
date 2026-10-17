# 用实际 K 线解释买卖门槛

展示 BTC 当前较好版本；不是原截图指标源码的确认。取已有回测最早一笔做多、最早一笔做空，以及最早一次空仓时因太远而放弃的突破。没有根据盈亏挑选。

数据、算法与成交核对记录：examples.json。交互页面：index.html。图：entry-explained.png。

复现：项目 Python 运行 `-m scripts.explain_cloud_entry extract`；安装有 Pillow 的 Python 运行 `scripts/explain_cloud_entry.py render`。原策略和回测结果未改。
