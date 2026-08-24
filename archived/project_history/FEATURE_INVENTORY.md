## Core Features

- [x] DCACalculator: Basic DCA (Standard)
- [x] DCACalculator: Value Averaging (Fixed Market Value)
- [ ] DCACalculator: Advanced Strategies (RSI, FearGreed)
- [ ] MarketIndicators: Macro Data & Crypto Metrics (Yields, On-chain, Mining, Sentiment)

## Known Issues

- [x] `dca_calculator.py`: ZeroDivisionError when `total_invested` is 0 (Value Averaging strategy).
- [x] `dca_calculator.py`: Negative ROI calculation when `total_invested` < 0.
