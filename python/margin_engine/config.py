"""All user-facing inputs live here. Change numbers here, never inside the logic modules."""
from pathlib import Path

# ===== CONFIG (user inputs) =====
PROJECT_DIR = Path(__file__).resolve().parents[2]
OUTPUT_DIR = PROJECT_DIR / "outputs"
FIGURE_DIR = OUTPUT_DIR / "figures"

# Market snapshot used for the headline run (prices rounded to cents; the original live run used unrounded prices)
PRICES = {"AAPL": 341.07, "JPM": 343.06, "XOM": 160.59}
EURUSD = 1.1401
US10Y_YIELD = 0.0518
RATE_DURATION_YEARS = 10.0  # duration proxy used by the v1 headline exposure

# Two counterparty netting sets (shares, EUR notional, USD rate notional)
NETTING_SETS = {
    "Counterparty A (equity-heavy)": {"shares": {"AAPL": 3000, "JPM": 2000}, "eur_notional": 5_000_000, "rate_notional": 30_000_000},
    "Counterparty B (rates-heavy)": {"shares": {"XOM": 500}, "eur_notional": 1_000_000, "rate_notional": 80_000_000},
}

# v1 SIMM-style parameters (simplified, illustrative, not ISDA calibrated)
RISK_WEIGHTS = {"equity": 0.24, "fx": 0.155, "rate": 0.019}
CROSS_CLASS_CORRELATION = 0.30

# v2 structured cross-check parameters (illustrative approximations, not ISDA calibrated)
EQUITY_INTRA_BUCKET_CORR = 0.15
RATE_RISK_WEIGHT_BP_10Y = 60.0
RATE_TENOR_DECAY = 0.03

# Funding rate used as the opportunity cost of posting cash (annual, in bps)
CASH_OPPORTUNITY_COST_BPS = 450

# Collateral inventory. Haircuts follow the BCBS-IOSCO uncleared margin standard schedule by asset type.
COLLATERAL_ROWS = [
    {"asset": "Cash (USD)", "market_value": 15_000_000, "haircut": 0.000, "opp_cost_bps": CASH_OPPORTUNITY_COST_BPS, "elig_A": True, "elig_B": True},
    {"asset": "US Treasury <1Y", "market_value": 20_000_000, "haircut": 0.005, "opp_cost_bps": 15, "elig_A": True, "elig_B": True},
    {"asset": "US Treasury 1-5Y", "market_value": 25_000_000, "haircut": 0.020, "opp_cost_bps": 25, "elig_A": True, "elig_B": True},
    {"asset": "US Treasury 5-10Y", "market_value": 15_000_000, "haircut": 0.040, "opp_cost_bps": 35, "elig_A": True, "elig_B": True},
    {"asset": "IG Corporate Bonds", "market_value": 10_000_000, "haircut": 0.080, "opp_cost_bps": 55, "elig_A": True, "elig_B": False},
    {"asset": "Equities (large-cap)", "market_value": 8_000_000, "haircut": 0.150, "opp_cost_bps": 80, "elig_A": False, "elig_B": False},
]

# Scenario grids
FUNDING_SWEEP_BPS = [50, 100, 200, 300, 450, 600]
HAIRCUT_MULTIPLIERS = [1.0, 1.5, 2.0, 3.0]
IM_SCALES = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
TREASURY_AVAILABILITY = [1.0, 0.75, 0.5, 0.25, 0.1]

# Pinned headline values used by the regression test (this snapshot, rounded prices)
EXPECTED_TOTAL_IM = 20_405_490
EXPECTED_NAIVE_COST = 918_247
EXPECTED_OPTIMIZED_COST = 31_290
IM_TOLERANCE = 50  # dollars
# ===== END CONFIG =====

# Column name constants (never address DataFrame columns by literal strings elsewhere)
ASSET_COL = "asset"
MARKET_VALUE_COL = "market_value"
HAIRCUT_COL = "haircut"
OPP_COST_COL = "opp_cost_bps"
ELIG_A_COL = "elig_A"
ELIG_B_COL = "elig_B"
POST_VALUE_COL = "post_value"
