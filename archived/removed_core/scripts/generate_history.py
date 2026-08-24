import json
import math
from datetime import datetime, timedelta
import random

def generate_btc_history():
    # Key historical price points (Approximate)
    # Date, Price
    points = [
        ("2010-07-17", 0.05),
        ("2010-10-01", 0.06),
        ("2011-02-09", 1.00),
        ("2011-04-15", 1.00),
        ("2011-06-08", 29.60), # 2011 Local Top
        ("2011-11-18", 2.05),  # 2011 Bottom
        ("2012-11-28", 12.25), # Halving 1
        ("2013-02-28", 32.00),
        ("2013-04-09", 230.00),# 2013 Double Bubble 1
        ("2013-07-05", 68.00),
        ("2013-12-04", 1135.00),# 2013 Double Bubble 2
        ("2014-04-10", 380.00),
        ("2014-06-01", 650.00),
        ("2015-01-14", 170.00), # Cycle Bottom
        ("2015-10-01", 240.00),
        ("2016-07-09", 650.00), # Halving 2
        ("2017-01-01", 960.00),
        ("2017-06-01", 2400.00),
        ("2017-08-16", 4200.00) # Connect to Binance Start
    ]

    # Convert to timestamps and values
    parsed_points = []
    for d, p in points:
        ts = int(datetime.strptime(d, "%Y-%m-%d").timestamp() * 1000)
        parsed_points.append((ts, p))

    full_data = [] # [ts, o, h, l, c, v]

    # Interpolate daily
    for i in range(len(parsed_points) - 1):
        start_ts, start_price = parsed_points[i]
        end_ts, end_price = parsed_points[i+1]
        
        days_diff = (end_ts - start_ts) / (1000 * 3600 * 24)
        price_diff = end_price - start_price
        
        # Logarithmic interpolation usually fits asset prices better, but linear is safer for simple connectivity
        # Let's use simple exponential interpolation P(t) = P0 * (r)^t
        # r = (Pend/Pstart)^(1/days)
        
        # Handle 0 or near 0 issues
        s_p = max(start_price, 0.01)
        e_p = max(end_price, 0.01)
        
        try:
            rate = math.pow(e_p / s_p, 1/days_diff)
        except:
            rate = 1

        current_ts = start_ts
        current_price = s_p
        
        while current_ts < end_ts:
            dt_obj = datetime.fromtimestamp(current_ts / 1000)
            
            # Add some random noise/volatility
            volatility = 0.03 # 3% daily swing
            noise = random.uniform(1-volatility, 1+volatility)
            
            close_p = current_price * noise
            
            # OHLC simulation
            open_p = current_price
            high_p = max(open_p, close_p) * random.uniform(1.0, 1.02)
            low_p = min(open_p, close_p) * random.uniform(0.98, 1.0)
            
            # Volume simulation (super rough)
            volume = close_p * 1000 * random.uniform(0.5, 2.0)
            
            full_data.append([
                current_ts,
                float(f"{open_p:.4f}"),
                float(f"{high_p:.4f}"),
                float(f"{low_p:.4f}"),
                float(f"{close_p:.4f}"),
                float(f"{volume:.2f}")
            ])
            
            # Next day
            current_ts += 24 * 3600 * 1000
            current_price *= rate

    # Ensure output dir
    import os
    os.makedirs("data", exist_ok=True)
    
    with open("data/btc_history_early.json", "w") as f:
        json.dump(full_data, f)
    
    print(f"Generated {len(full_data)} historical days.")

if __name__ == "__main__":
    generate_btc_history()
