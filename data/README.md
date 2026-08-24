# Bundled data provenance

## `btc_history_early.json`

This file contains 2,587 daily OHLCV rows used to bridge the period before Binance BTC/USDT history is available. It is a mixed-quality proxy dataset, not a single observed BTC/USDT exchange series.

- Rows dated 2010-07-16 through 2011-08-15 (396 rows) are synthetic. Historical price waypoints were interpolated and random noise was added; OHLC and volume were fabricated for simulation. The original generator did not record a random seed, so this exact segment cannot be regenerated deterministically.
- Rows dated 2011-08-18 through 2017-08-16 were downloaded from Bitstamp's BTC/USD daily OHLCV endpoint through CCXT. They are a USD proxy used by the BTC/USDT path, not observations from Binance.
- The file first entered repository history in commit `fcabd21be87b82867616948bca1cc3f122d367e8` on 2026-03-25. The historical generator, Bitstamp downloader, and merge script are retained in that commit's Git history.
- Current file Git object ID: `67f38589f0f5700eafef5ba035ab94dc379b1e7e`; SHA-256: `ac1863899df2bd52b6791d8de4423eca504adb9a430011cfa33eaa3f430fa11d`.

The synthetic segment is suitable only for rough interface demonstrations and exploratory simulations. It must not be described as measured market history or used to support factual performance claims. DCA responses identify when a requested result includes this segment, and the UI displays a warning.
