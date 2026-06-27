#!/usr/bin/env python3
"""
Verify the mathematical calculations in Presek marketing system.
"""

import math

# Constants from the code (updated for exact 50% savings)
MKD_PER_EUR = 61.5
CPM_RATES_EUR = {
    'top_banner': 0.9756,    # 60 MKD exactly (50% of 120 MKD)
    'sidebar': 1.2207,     # 75 MKD exactly (50% of 150 MKD)
    'mobile_content': 2.00  # 125 MKD (50% of 250 MKD)
}

print('=== CPM Rate Verification ===')
print(f'Exchange rate: 1 EUR = {MKD_PER_EUR} MKD')
print()

for slot, eur_rate in CPM_RATES_EUR.items():
    mkd_rate = round(eur_rate * MKD_PER_EUR)
    print(f'{slot.replace("_", " ").title()}:')
    print(f'  EUR: {eur_rate:.2f} €')
    print(f'  MKD: {mkd_rate} MKD (calculated: {eur_rate * MKD_PER_EUR:.0f})')
    print(f'  Per 1,000 impressions: {eur_rate:.2f} € / {mkd_rate} MKD')
    print()

# Test calculation for 10,000 impressions
print('=== Sample Calculation: 10,000 impressions ===')
for slot, eur_rate in CPM_RATES_EUR.items():
    impressions = 10000
    total_eur = round((impressions / 1000.0) * eur_rate, 2)
    total_mkd = round(total_eur * MKD_PER_EUR)
    
    print(f'{slot}:')
    print(f'  {impressions:,} impressions × {eur_rate:.2f} € CPM = {total_eur:.2f} €')
    print(f'  {impressions:,} impressions × {round(eur_rate * MKD_PER_EUR)} MKD CPM = {total_mkd} MKD')
    print()

# Verify minimum charge logic
print('=== Minimum Charge Verification ===')
print('Stripe minimum charge: €0.50')
print('Minimum impressions: 1,000')
print()

for slot, eur_rate in CPM_RATES_EUR.items():
    min_impressions = 1000
    calculated = (min_impressions / 1000.0) * eur_rate
    actual = max(calculated, 0.50)  # Stripe minimum
    
    print(f'{slot}:')
    print(f'  Calculated: {calculated:.2f} €')
    print(f'  Actual (with min): {actual:.2f} €')
    print(f'  Minimum enforced: {"YES" if calculated < 0.50 else "NO"}')
    print()

# Verify the pricing claims in the marketing pages
print('=== Marketing Claims Verification ===')
print('Claim: "50% lower prices than traditional media"')
print()

# Traditional media prices from the marketing pages
traditional_prices_mkd = {
    'top_banner': 120,
    'sidebar': 150,
    'mobile_content': 250
}

print('Price Comparison:')
for slot, eur_rate in CPM_RATES_EUR.items():
    presek_mkd = round(eur_rate * MKD_PER_EUR)
    traditional_mkd = traditional_prices_mkd[slot]
    savings = traditional_mkd - presek_mkd
    savings_pct = (savings / traditional_mkd) * 100
    
    print(f'{slot.replace("_", " ").title()}:')
    print(f'  Traditional: {traditional_mkd} MKD')
    print(f'  Presek:      {presek_mkd} MKD')
    print(f'  Savings:     {savings} MKD ({savings_pct:.1f}%)')
    print(f'  Claim Valid: {"✓" if savings_pct >= 50 else "✗"}')
    print()

print('=== Math Verification Complete ===')
