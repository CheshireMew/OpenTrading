# ZEC 15分钟组合固定规则

四组全用同一份15分钟信号数据、5分钟成交数据。固定1%止损/1.5倍平滑振幅止损（限制0.5%—2%），分别配15分钟收盘/5分钟收盘更新保护，下一根生效。复用前一轮固定止损的两组，只新增振幅止损的两组。

参数完全继承指定版本：{"activation_pct": 1.0, "center_length": 144, "chase_mult": 3.0, "confirmation_level": 3, "direction_filter": false, "entry_bar_assumption": 0, "giveback_pct": 35.0, "initial_stop_pct": 1, "max_wait_bars": 2, "price_tick": 0.01, "stop_cap_pct": 2, "stop_floor_pct": 0.5, "stop_method": 0, "stop_mult": 1.5, "stop_reentry": false, "trigger_mult": 1.2, "width_length": 31}。仅stop_method在0/1切换、intrabar_profit_protection在false/true切换。ETH继续六年EMA55、2%启动/回吐50%；ZEC继续七年EMA144、1%启动/回吐35%。此次不是取消利润保护，不使用ETH另测的35%版本，不将ZEC改回30分钟。

无参数搜索，全部已见历史；全仓复利、不加杠杆、不计手续费和滑点。聚合细行情不匹配时四组均回退15分钟；5分钟内仍可能先后不明，最大回撤按15分钟收盘权益计算。按用户追加要求独立留档，原单因素结果不覆盖。
