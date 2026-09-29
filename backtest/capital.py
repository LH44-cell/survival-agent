"""Hur stort startkapital behövs för att minsta ordervärde inte ska stoppa strategierna?
Kör playbooken och några strategier på basnivån med verkliga minsta ordervärden per plats och
olika startkapital, utan compute-kostnad. Jämför mot samma körning med minsta order 0,50 USD
(Krakens costmin, i praktiken obegränsat).

    python backtest/capital.py

Skriver results/capital.csv. Krakens minsta order per par tas från data/venues.json
(ordermin × pris, uppmätt av venue_check.py). Hyperliquid: 10 USD per order enligt deras
dokumentation – kunde inte verifieras live härifrån (nätverkspolicyn blockerar api.hyperliquid.xyz).
"""

import json
import os

import pandas as pd

from common import DATA_DIR, RESULTS_DIR, TIERS
import engine  # noqa: E402
from run_backtest import WARMUP, load, normalized  # noqa: E402
from strategies import ew_trend, trend_sma  # noqa: E402

PAIRS = TIERS["bas"]
CAPITALS = [20, 35, 50, 100, 200, 500]
HL_MIN_ORDER = 10.0


def playbook(c):
    return trend_sma(1200, band=0.03)(c) * 0.30


def main():
    opens, closes = load()
    spreads = {p: v["mean_spread"] for p, v in
               json.load(open(os.path.join(DATA_DIR, "kraken_spreads.json")))["pairs"].items()}
    venues = json.load(open(os.path.join(DATA_DIR, "venues.json")))["venues"]
    kraken_min = {p: max(venues["kraken"]["pairs"][p]["min_amount_usd"], 0.5) for p in PAIRS}
    setups = {
        "kraken": (0.0040, kraken_min),
        "hyperliquid": (0.0007, {p: HL_MIN_ORDER for p in PAIRS}),
    }
    strats = {
        "playbook": (playbook, 0.25),
        "ew_trend_sma1200": (normalized(ew_trend(1200)), engine.REBALANCE_BAND),
        "ew_trend_sma200": (normalized(ew_trend(200, 0.01)), engine.REBALANCE_BAND),
    }
    o, c = opens[PAIRS], closes[PAIRS]
    t0 = c.index[WARMUP]
    rows = []
    for sname, (strat, band) in strats.items():
        sig = strat(c)
        for venue, (fee, mins) in setups.items():
            _, ref = engine.run(o, c, None, spreads, start=t0, warmup=WARMUP, fee=fee, signals=sig,
                                rebalance_band=band, min_order=0.5, start_equity=100.0)
            for cap in CAPITALS:
                _, st = engine.run(o, c, None, spreads, start=t0, warmup=WARMUP, fee=fee, signals=sig,
                                   rebalance_band=band, min_order=mins, start_equity=float(cap))
                rows.append({"strategy": sname, "venue": venue, "fee": fee, "capital": cap,
                             "ret": st["ret"], "ret_unconstrained": ref["ret"], "trades": st["trades"],
                             "trades_unconstrained": ref["trades"], "blocked": st["blocked"],
                             "maxdd": st["maxdd"]})
                print(f"{sname:17} {venue:11} {cap:4} USD: avk {st['ret']:+.1%} (fritt {ref['ret']:+.1%}) "
                      f"trades {st['trades']}/{ref['trades']} blockerade {st['blocked']}")
    pd.DataFrame(rows).to_csv(os.path.join(RESULTS_DIR, "capital.csv"), index=False)
    print("kraken min per par (USD):", {p: round(v, 2) for p, v in kraken_min.items()})


if __name__ == "__main__":
    main()
