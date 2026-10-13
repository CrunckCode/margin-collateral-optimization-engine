"""
Margin and Collateral Optimization Engine (SIMM-style Initial Margin)
==========================================================================
Computes a simplified ISDA SIMM-style initial margin for a multi-counterparty derivatives
book using REAL market sensitivities (real equity deltas, real FX spot, real rate-driven
GIRR sensitivity - same real-data discipline as the FRTB project), then optimizes which
real-haircut-schedule collateral to post across counterparties to minimize funding cost.
"""
import numpy as np
import pandas as pd
import yfinance as yf
import pandas_datareader.data as web
import datetime
from scipy.optimize import linprog

TODAY = datetime.date.today()

# ===========================================================================
# 1. Real market data for 2 counterparty netting sets' risk sensitivities
# ===========================================================================
eq_prices = yf.download(["AAPL", "JPM", "XOM"], period="5d", progress=False,
                          auto_adjust=True)["Close"].iloc[-1]
fx_spot = yf.download(["EURUSD=X"], period="5d", progress=False, auto_adjust=True)["Close"].iloc[-1]
y10 = web.DataReader("DGS10", "fred", start=TODAY - datetime.timedelta(days=10)).iloc[-1, 0] / 100
print(f"Real data: AAPL ${eq_prices['AAPL']:.2f}, JPM ${eq_prices['JPM']:.2f}, "
      f"XOM ${eq_prices['XOM']:.2f}, EURUSD {float(fx_spot.iloc[0]):.4f}, "
      f"10Y yield {y10:.2%}")

# Counterparty A: equity-heavy book (real spot-based deltas)
cpty_a_deltas = {"equity": 3000 * eq_prices["AAPL"] + 2000 * eq_prices["JPM"],
                  "fx": 5_000_000 * float(fx_spot.iloc[0]),
                  "rate": 30_000_000 * (10 / (1 + y10)) * 0.0001 * 10000}  # rate delta scaled to notional-equivalent
# Counterparty B: rates-heavy book
cpty_b_deltas = {"equity": 500 * eq_prices["XOM"],
                  "fx": 1_000_000 * float(fx_spot.iloc[0]),
                  "rate": 80_000_000 * (10 / (1 + y10)) * 0.0001 * 10000}

# Real ISDA SIMM-style risk weights (simplified illustrative values consistent with the
# real published SIMM methodology's risk-weight magnitudes by product class)
SIMM_RW = {"equity": 0.24, "fx": 0.155, "rate": 0.019}
SIMM_CONCENTRATION_THRESHOLD_MULT = 1.0  # simplified: no concentration add-on applied

def compute_simm_im(deltas, risk_weights, correlation=0.3):
    weighted = {k: abs(v) * risk_weights[k] for k, v in deltas.items()}
    values = list(weighted.values())
    im = np.sqrt(sum(v**2 for v in values) +
                 sum(correlation * values[i] * values[j]
                     for i in range(len(values)) for j in range(len(values)) if i != j))
    return im, weighted

im_a, wc_a = compute_simm_im(cpty_a_deltas, SIMM_RW)
im_b, wc_b = compute_simm_im(cpty_b_deltas, SIMM_RW)

print("\n" + "=" * 70)
print("SIMM-STYLE INITIAL MARGIN BY COUNTERPARTY")
print("=" * 70)
print(f"Counterparty A (equity-heavy): deltas {cpty_a_deltas}")
print(f"  Weighted sensitivities: {wc_a}")
print(f"  Initial Margin: ${im_a:,.0f}")
print(f"\nCounterparty B (rates-heavy): deltas {cpty_b_deltas}")
print(f"  Weighted sensitivities: {wc_b}")
print(f"  Initial Margin: ${im_b:,.0f}")
print(f"\nTotal IM required across both counterparties: ${im_a + im_b:,.0f}")

# ===========================================================================
# 2. Collateral inventory with REAL ISDA-standard haircut schedule
# ===========================================================================
# Real, standard regulatory-margin-rule haircuts (BCBS-IOSCO uncleared margin rules,
# published standard schedule). Opportunity cost is framed correctly here: CASH is the
# MOST expensive collateral to post (you give up the real funding/repo rate you'd
# otherwise earn on it, ~450bps at the current real SOFR level), while posting an
# already-held Treasury the firm holds anyway costs only a small incremental
# liquidity/repo-spread charge - an earlier version of this had cash at 0 opportunity
# cost, which trivially made the optimizer post cash for everything and defeated the
# entire point of collateral optimization (freeing cash for its opportunity cost).
collateral_inventory = pd.DataFrame([
    {"asset": "Cash (USD)", "market_value": 15_000_000, "haircut": 0.00,
     "opportunity_cost_bps": 450, "eligible_A": True, "eligible_B": True},
    {"asset": "US Treasury <1Y", "market_value": 20_000_000, "haircut": 0.005,
     "opportunity_cost_bps": 15, "eligible_A": True, "eligible_B": True},
    {"asset": "US Treasury 1-5Y", "market_value": 25_000_000, "haircut": 0.02,
     "opportunity_cost_bps": 25, "eligible_A": True, "eligible_B": True},
    {"asset": "US Treasury 5-10Y", "market_value": 15_000_000, "haircut": 0.04,
     "opportunity_cost_bps": 35, "eligible_A": True, "eligible_B": True},
    {"asset": "IG Corporate Bonds", "market_value": 10_000_000, "haircut": 0.08,
     "opportunity_cost_bps": 55, "eligible_A": True, "eligible_B": False},
    {"asset": "Equities (large-cap)", "market_value": 8_000_000, "haircut": 0.15,
     "opportunity_cost_bps": 80, "eligible_A": False, "eligible_B": False},
])
print("\n" + "=" * 70)
print("COLLATERAL INVENTORY (real ISDA-standard haircut schedule)")
print("=" * 70)
print(collateral_inventory.to_string(index=False))
collateral_inventory["post_value"] = collateral_inventory["market_value"] * (1 - collateral_inventory["haircut"])

# ===========================================================================
# 3. Optimize: minimize total opportunity cost of posted collateral subject to
#    meeting each counterparty's IM requirement (post-haircut value), eligibility,
#    and not exceeding available market value per asset
# ===========================================================================
assets = collateral_inventory["asset"].tolist()
n = len(assets)
# Decision variables: amount of each asset (market value terms) posted to A, then to B
# x = [a_1..a_n, b_1..b_n]
c = np.concatenate([
    collateral_inventory["opportunity_cost_bps"].values / 10000,
    collateral_inventory["opportunity_cost_bps"].values / 10000,
])

# Constraint 1: sum of post-haircut value posted to A >= IM_a
post_factors = (1 - collateral_inventory["haircut"].values)
A_ub = []
b_ub = []
# -sum(post_factor * a_i) <= -IM_a  ->  sum(post_factor*a_i) >= IM_a
row = np.concatenate([-post_factors, np.zeros(n)])
A_ub.append(row); b_ub.append(-im_a)
row = np.concatenate([np.zeros(n), -post_factors])
A_ub.append(row); b_ub.append(-im_b)

# Constraint 2: eligibility - ineligible assets get an upper bound of 0 (handled via bounds)
# Constraint 3: total posted per asset (a_i + b_i) <= market value
for i in range(n):
    row = np.zeros(2 * n)
    row[i] = 1
    row[n + i] = 1
    A_ub.append(row)
    b_ub.append(collateral_inventory["market_value"].values[i])

bounds = []
for i in range(n):
    bounds.append((0, collateral_inventory["market_value"].values[i] if collateral_inventory["eligible_A"].values[i] else 0))
for i in range(n):
    bounds.append((0, collateral_inventory["market_value"].values[i] if collateral_inventory["eligible_B"].values[i] else 0))

result = linprog(c, A_ub=A_ub, b_ub=b_ub, bounds=bounds, method="highs")

print("\n" + "=" * 70)
print("OPTIMIZED COLLATERAL ALLOCATION (minimize opportunity cost)")
print("=" * 70)
if result.success:
    alloc_a = result.x[:n]
    alloc_b = result.x[n:]
    for i, asset in enumerate(assets):
        if alloc_a[i] > 1000 or alloc_b[i] > 1000:
            print(f"  {asset}: ${alloc_a[i]:,.0f} to Cpty A, ${alloc_b[i]:,.0f} to Cpty B")
    total_opt_cost = result.fun * 10000  # back to dollar-equivalent-ish (annualized bps-based cost)
    print(f"\nTotal annualized opportunity cost (optimized): ${(c @ result.x):,.0f}")
else:
    print("Optimization failed:", result.message)

# ===========================================================================
# 4. Naive cash-only comparison
# ===========================================================================
print("\n" + "=" * 70)
print("NAIVE (CASH-ONLY) COMPARISON")
print("=" * 70)
naive_cash_needed = im_a + im_b  # cash has 0 haircut, so post exactly IM in cash
naive_cost = naive_cash_needed * 450 / 10000
print(f"Cash needed to cover both IMs at 0% haircut: ${naive_cash_needed:,.0f}")
print(f"Naive (cash-only) annualized opportunity cost: ${naive_cost:,.0f}")
