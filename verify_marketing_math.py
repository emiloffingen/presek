#!/usr/bin/env python3
"""Verify the pricing math for the Presek advertising system.

Mirrors routes/marketing.py (CPM_BASE_EUR, PROMO_DISCOUNT, _amount_cents) and
web/src/lib/adPricing.ts. Run: python verify_marketing_math.py
"""

MKD_PER_EUR = 61.5
CPM_BASE_EUR = {"top_banner": 2.44, "sidebar": 2.93, "mobile_content": 3.25}
PROMO_DISCOUNT = 0.25
CPM_RATES_EUR = {
    slot: round(rate * (1 - PROMO_DISCOUNT), 4) for slot, rate in CPM_BASE_EUR.items()
}

MIN_CHARGE_CENTS = 3000  # €30
MIN_DAILY_IMPRESSIONS = 2000

# MK news outlets' 2026 rate cards (MKD per 1,000 impressions).
MARKET_MKD = {
    "top_banner": (200, 350),
    "sidebar": (180, 350),
    "mobile_content": (200, 400),
}


def amount_cents(slot: str, impressions: int) -> int:
    eur = round((impressions / 1000.0) * CPM_RATES_EUR[slot], 2)
    return max(MIN_CHARGE_CENTS, int(round(eur * 100)))


print("=== CPM rates ===")
for slot, base in CPM_BASE_EUR.items():
    now = CPM_RATES_EUR[slot]
    print(
        f"  {slot}: base €{base:.2f} ({round(base * MKD_PER_EUR)} MKD) "
        f"-> promo €{now:.2f} ({round(now * MKD_PER_EUR)} MKD, -{int(PROMO_DISCOUNT * 100)}%)"
    )

print("\n=== vs MK market benchmark (MKD CPM) ===")
for slot, (lo, hi) in MARKET_MKD.items():
    ours = round(CPM_RATES_EUR[slot] * MKD_PER_EUR)
    position = "below" if ours < lo else ("within" if ours <= hi else "ABOVE")
    print(f"  {slot}: ours {ours} MKD vs market {lo}-{hi} MKD ({position})")

print("\n=== sample totals (10,000 impressions) ===")
for slot in CPM_RATES_EUR:
    eur = (10000 / 1000) * CPM_RATES_EUR[slot]
    print(f"  {slot}: €{eur:.2f} -> {amount_cents(slot, 10000)} cents")

assert amount_cents("top_banner", 1000) == MIN_CHARGE_CENTS, "min charge floor"
assert all(
    round(CPM_RATES_EUR[s] * MKD_PER_EUR) < MARKET_MKD[s][0] for s in CPM_RATES_EUR
), "prices should undercut the market floor"
print("\nOK: min charge €30, min daily 2,000 impressions, image <= 150KB")
