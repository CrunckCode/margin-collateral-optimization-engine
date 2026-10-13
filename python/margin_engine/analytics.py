"""Scenario analysis around the base allocation."""
import pandas as pd

from . import config as C
from .collateral import build_inventory
from .optimizer import naive_cash_cost, optimize


def funding_sweep(im_a, im_b, bps_grid=None):
    rows = []
    for bps in bps_grid or C.FUNDING_SWEEP_BPS:
        alloc = optimize(build_inventory(cash_opp_cost_bps=bps), im_a, im_b)
        naive = naive_cash_cost(im_a, im_b, bps)
        rows.append({"cash_cost_bps": bps, "naive_cost": naive, "optimized_cost": alloc.cost,
                     "saving": naive - alloc.cost, "saving_pct": 1 - alloc.cost / naive})
    return pd.DataFrame(rows)


def haircut_stress(im_a, im_b, multipliers=None):
    rows = []
    for m in multipliers or C.HAIRCUT_MULTIPLIERS:
        alloc = optimize(build_inventory(haircut_multiplier=m), im_a, im_b)
        posted = alloc.table["posted"].sum() if alloc.success else float("nan")
        rows.append({"haircut_multiplier": m, "optimized_cost": alloc.cost, "market_value_posted": posted,
                     "overcollateral_pct": posted / (im_a + im_b) - 1 if alloc.success else float("nan")})
    return pd.DataFrame(rows)


def im_scaling(im_a, im_b, scales=None):
    rows = []
    for s in scales or C.IM_SCALES:
        alloc = optimize(build_inventory(), im_a * s, im_b * s)
        rows.append({"im_scale": s, "total_im": (im_a + im_b) * s, "feasible": alloc.success,
                     "optimized_cost": alloc.cost, "shadow_price_a": alloc.shadow_price_a,
                     "shadow_price_b": alloc.shadow_price_b})
    return pd.DataFrame(rows)


def treasury_scarcity(im_a, im_b, levels=None):
    rows = []
    for lvl in levels or C.TREASURY_AVAILABILITY:
        inv = build_inventory(availability={"US Treasury": lvl})
        alloc = optimize(inv, im_a, im_b)
        cash_posted = alloc.table.loc[alloc.table[C.ASSET_COL].str.startswith("Cash"), "posted"].sum() if alloc.success else float("nan")
        rows.append({"treasury_availability": lvl, "feasible": alloc.success, "optimized_cost": alloc.cost, "cash_posted": cash_posted})
    return pd.DataFrame(rows)


def eligibility_cases(im_a, im_b):
    """Eligibility rules are a real constraint: a counterparty may refuse the cheapest collateral."""
    base = optimize(build_inventory(), im_a, im_b)
    no_bill_b = build_inventory()
    no_bill_b.loc[no_bill_b[C.ASSET_COL] == "US Treasury <1Y", C.ELIG_B_COL] = False
    no_bill_any = build_inventory()
    no_bill_any.loc[no_bill_any[C.ASSET_COL] == "US Treasury <1Y", [C.ELIG_A_COL, C.ELIG_B_COL]] = False
    rows = [("Base (Treasuries <1Y eligible for both)", base.cost),
            ("Treasuries <1Y ineligible for B", optimize(no_bill_b, im_a, im_b).cost),
            ("Treasuries <1Y ineligible for both", optimize(no_bill_any, im_a, im_b).cost)]
    return pd.DataFrame(rows, columns=["case", "optimized_cost"])


def cash_bug_demo(im_a, im_b):
    """The original error: cash opportunity cost of zero makes the optimizer post only cash."""
    alloc = optimize(build_inventory(cash_opp_cost_bps=0), im_a, im_b)
    cash_row = alloc.table[alloc.table[C.ASSET_COL].str.startswith("Cash")]
    return {"cash_posted": float(cash_row["posted"].sum()), "total_posted": float(alloc.table["posted"].sum()), "cost": alloc.cost}
