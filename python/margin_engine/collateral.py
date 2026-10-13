"""Collateral inventory and helpers."""
import pandas as pd

from . import config as C


def build_inventory(rows=None, cash_opp_cost_bps=None, haircut_multiplier=1.0, availability=None):
    """Inventory DataFrame. availability maps asset-name prefixes to a market-value scale (for scarcity tests)."""
    inv = pd.DataFrame(rows if rows is not None else C.COLLATERAL_ROWS).copy()
    if cash_opp_cost_bps is not None:
        inv.loc[inv[C.ASSET_COL].str.startswith("Cash"), C.OPP_COST_COL] = cash_opp_cost_bps
    inv[C.HAIRCUT_COL] = (inv[C.HAIRCUT_COL] * haircut_multiplier).clip(upper=0.95)
    for prefix, scale in (availability or {}).items():
        mask = inv[C.ASSET_COL].str.startswith(prefix)
        inv.loc[mask, C.MARKET_VALUE_COL] = inv.loc[mask, C.MARKET_VALUE_COL] * scale
    inv[C.POST_VALUE_COL] = inv[C.MARKET_VALUE_COL] * (1.0 - inv[C.HAIRCUT_COL])
    return inv
