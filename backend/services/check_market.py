"""
Check what BTC 5-min markets are currently active on Polymarket.
Run this to see the market structure.

Usage: python check_polymarket.py
"""

import urllib.request
import json
import time
import math

def check_markets():
    url = "https://gamma-api.polymarket.com/events"
    
    now_ts = time.time()
    window_seconds = 300
    
    # Check current, next, and previous 5-min windows
    timestamps = [
        int(math.floor(now_ts / window_seconds) * window_seconds),       # Current
        int(math.ceil(now_ts / window_seconds) * window_seconds),        # Next
        int(math.floor(now_ts / window_seconds) * window_seconds) - window_seconds,  # Previous
    ]
    
    print("=" * 80)
    print("CHECKING POLYMARKET BTC 5-MIN MARKETS")
    print("=" * 80)
    print()
    
    markets_found = 0
    
    for ts in timestamps:
        slug = f"btc-updown-5m-{ts}"
        
        try:
            params = f"?slug={slug}"
            full_url = url + params
            
            print(f"Checking: {slug}")
            print(f"  URL: {full_url}")
            
            with urllib.request.urlopen(full_url, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))
            
            # Handle both list and dict responses
            events = data if isinstance(data, list) else [data] if isinstance(data, dict) else []
            
            if not events:
                print(f"  ✗ No events found\n")
                continue
            
            print(f"  ✓ Found {len(events)} event(s)\n")
            
            for event in events:
                title = event.get('title', 'N/A')
                active = event.get('active', False)
                accepting = event.get('acceptingOrders', False)
                end_date = event.get('endDate', 'N/A')
                
                print(f"  Event: {title}")
                print(f"    Active: {active}")
                print(f"    Accepting orders: {accepting}")
                print(f"    End date: {end_date}")
                
                markets = event.get('markets', [])
                print(f"    Markets: {len(markets)}")
                
                for m in markets:
                    m_title = m.get('title', 'N/A')
                    m_id = m.get('id', 'N/A')[:16]
                    outcome_prices = m.get('outcomePrices', [])
                    
                    print(f"      └─ {m_title}")
                    print(f"         ID: {m_id}...")
                    print(f"         Outcome prices: {outcome_prices}")
                    
                    markets_found += 1
                
                print()
        
        except urllib.error.URLError as e:
            print(f"  ✗ Connection error: {e}\n")
        except json.JSONDecodeError as e:
            print(f"  ✗ JSON error: {e}\n")
        except Exception as e:
            print(f"  ✗ Error: {e}\n")
    
    print("=" * 80)
    print(f"SUMMARY: Found {markets_found} active market(s)")
    print("=" * 80)
    print()
    print("KEY INSIGHTS:")
    print("  - Each 5-min window is ONE market")
    print("  - Markets expire after 5 minutes")
    print("  - New windows open automatically")
    print("  - outcomePrices shows current odds")
    print("    Example: [0.52, 0.48] = 52% UP, 48% DOWN")
    print()

if __name__ == "__main__":
    check_markets()