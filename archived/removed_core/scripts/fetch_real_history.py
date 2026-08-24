import ccxt
import json
import time
from datetime import datetime

def fetch_real_history():
    # Bitstamp is a good source for early data (2011+)
    exchange = ccxt.bitstamp({'enableRateLimit': True})
    symbol = 'BTC/USD' # Bitstamp uses USD
    timeframe = '1d'
    
    # Start from 2011-08-18 (Bitstamp launch approx)
    # or even earlier if possible, but let's try 2011-01-01
    start_ts = int(datetime(2011, 8, 18).timestamp() * 1000)
    end_ts = int(datetime(2017, 8, 17).timestamp() * 1000)
    
    all_ohlcv = []
    current_since = start_ts
    
    print(f"Fetching data from {exchange.id} for {symbol}...")
    
    while current_since < end_ts:
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=current_since, limit=1000)
            if not ohlcv:
                print("No more data received.")
                break
            
            all_ohlcv.extend(ohlcv)
            current_since = ohlcv[-1][0] + 1
            
            date_str = datetime.fromtimestamp(ohlcv[-1][0]/1000).strftime('%Y-%m-%d')
            print(f"Fetched up to {date_str}, Total: {len(all_ohlcv)}")
            
            if ohlcv[-1][0] >= end_ts:
                break
                
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)
            
    # Filter strictly < 2017-08-17 (Binance start)
    final_data = [x for x in all_ohlcv if x[0] < end_ts]
    
    # Save
    import os
    os.makedirs("data", exist_ok=True)
    with open("data/btc_history_early.json", "w") as f:
        json.dump(final_data, f)
        
    print(f"[OK] Successfully saved {len(final_data)} real historical records to data/btc_history_early.json")

if __name__ == "__main__":
    fetch_real_history()
