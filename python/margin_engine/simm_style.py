"""SIMM-style initial margin: the v1 headline method and a v2 structured cross-check."""
import math
from itertools import combinations

from . import config as C

RISK_CLASSES = ("equity", "fx", "rate")


def netting_set_deltas(spec, prices=None, eurusd=None, y10=None, duration=None):
    """Delta exposures in USD for one netting set. Rate exposure is a duration-style notional equivalent."""
    prices = prices or C.PRICES
    eurusd = eurusd if eurusd is not None else C.EURUSD
    y10 = y10 if y10 is not None else C.US10Y_YIELD
    duration = duration if duration is not None else C.RATE_DURATION_YEARS
    equity = sum(qty * prices[name] for name, qty in spec["shares"].items())
    fx = spec["eur_notional"] * eurusd
    rate = spec["rate_notional"] * duration / (1.0 + y10)
    return {"equity": equity, "fx": fx, "rate": rate}


def aggregate(weighted, correlation):
    """sqrt( sum WS_i^2 + sum_{i != j} rho * WS_i * WS_j ). Same shape as the SIMM cross-risk-class aggregation."""
    values = list(weighted.values())
    total = sum(v * v for v in values)
    for i, j in combinations(range(len(values)), 2):
        total += 2.0 * correlation * values[i] * values[j]
    return math.sqrt(total)


def compute_im_v1(deltas, risk_weights=None, correlation=None):
    """Headline method: |delta| times a risk weight per class, then one correlation across classes."""
    risk_weights = risk_weights or C.RISK_WEIGHTS
    correlation = C.CROSS_CLASS_CORRELATION if correlation is None else correlation
    weighted = {k: abs(deltas[k]) * risk_weights[k] for k in RISK_CLASSES}
    return aggregate(weighted, correlation), weighted


def headline_im(netting_sets=None, **kwargs):
    """Initial margin by netting set for the headline method."""
    netting_sets = netting_sets or C.NETTING_SETS
    out = {}
    for name, spec in netting_sets.items():
        deltas = netting_set_deltas(spec, **kwargs)
        im, weighted = compute_im_v1(deltas)
        out[name] = {"deltas": deltas, "weighted": weighted, "im": im}
    return out


# ---------- v2 structured cross-check ----------
def _equity_class_im(spec, prices):
    ws = [qty * prices[name] * C.RISK_WEIGHTS["equity"] for name, qty in spec["shares"].items()]
    rho = C.EQUITY_INTRA_BUCKET_CORR
    total = sum(w * w for w in ws)
    for i, j in combinations(range(len(ws)), 2):
        total += 2.0 * rho * ws[i] * ws[j]
    return math.sqrt(total)


def _rate_class_im(spec, y10, duration):
    """PV01 in USD per bp for a 10Y exposure times a risk weight in bp. Single tenor bucket in this dataset."""
    pv01 = spec["rate_notional"] * (duration / (1.0 + y10)) * 1e-4
    return abs(pv01) * C.RATE_RISK_WEIGHT_BP_10Y


def structured_im(netting_sets=None, prices=None, eurusd=None, y10=None, duration=None):
    """Cross-check: per-name equity buckets, PV01-based rates, same cross-class correlation."""
    netting_sets = netting_sets or C.NETTING_SETS
    prices = prices or C.PRICES
    eurusd = eurusd if eurusd is not None else C.EURUSD
    y10 = y10 if y10 is not None else C.US10Y_YIELD
    duration = duration if duration is not None else C.RATE_DURATION_YEARS
    out = {}
    for name, spec in netting_sets.items():
        per_class = {
            "equity": _equity_class_im(spec, prices),
            "fx": abs(spec["eur_notional"] * eurusd) * C.RISK_WEIGHTS["fx"],
            "rate": _rate_class_im(spec, y10, duration),
        }
        out[name] = {"per_class": per_class, "im": aggregate(per_class, C.CROSS_CLASS_CORRELATION)}
    return out
