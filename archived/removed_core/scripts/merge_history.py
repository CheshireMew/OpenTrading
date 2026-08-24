import json
import math
from datetime import datetime
import random
import os

def merge_history():
    print("Starting History Merge...")
    
    # 1. Load Real Data (2011-08-18 -> 2017)
    real_data = []
    if os.path.exists("data/btc_history_early.json"):
        with open("data/btc_history_early.json", "r") as f:
            real_data = json.load(f)
            print(f"Loaded {len(real_data)} real records.")
            
    # Find start of real data
    real_start_ts = real_data[0][0] if real_data else int(datetime(2011, 8, 18).timestamp() * 1000)
    real_start_price = real_data[0][4] if real_data else 10.0 # fallback
    
    print(f"Real data starts at: {datetime.fromtimestamp(real_start_ts/1000)}")

    # 2. Generate Synthetic Data (2010-07-17 -> Real Start)
    print("Generating synthetic data (2010-2011)...")
    
    points = [
        ("2010-07-17", 0.05),
        ("2010-10-01", 0.06),
        ("2011-02-09", 1.00),
        ("2011-04-16", 1.00),
        ("2011-06-08", 29.60), # Bubble
        ("2011-08-17", real_start_price) # Connect to real data
    ]
    
    parsed_points = []
    for d, p in points:
        ts = int(datetime.strptime(d, "%Y-%m-%d").timestamp() * 1000)
        parsed_points.append((ts, p))
        
    synthetic_data = []
    
    for i in range(len(parsed_points) - 1):
        start_ts, start_price = parsed_points[i]
        end_ts, end_price = parsed_points[i+1]
        
        # Stop if we overlap with real data
        if start_ts >= real_start_ts:
            break
            
        end_ts = min(end_ts, real_start_ts)
        
        days_diff = (end_ts - start_ts) / (1000 * 3600 * 24)
        if days_diff <= 0: continue
            
        try:
            rate = math.pow(end_price / max(start_price, 0.01), 1/days_diff)
        except:
            rate = 1
            
        current_ts = start_ts
        current_price = max(start_price, 0.01)
        
        while current_ts < end_ts:
            # Volatility
            noise = random.uniform(0.95, 1.05)
            close_p = current_price * noise
            
            synthetic_data.append([
                current_ts,
                close_p, # O
                close_p * 1.02, # H
                close_p * 0.98, # L
                close_p, # C
                10000.0 # V
            ])
            
            current_ts += 24 * 3600 * 1000
            current_price *= rate
            
    print(f"Generated {len(synthetic_data)} synthetic records.")
    
    # 3. Merge
    final_data = synthetic_data + real_data
    final_data.sort(key=lambda x: x[0])
    
    # Save
    with open("data/btc_history_early.json", "w") as f:
        json.dump(final_data, f)
        
    print(f"[OK] Total records saved: {len(final_data)}")

if __name__ == "__main__":
    merge_history()
