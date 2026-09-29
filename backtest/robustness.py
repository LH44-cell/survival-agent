"""Känslighetsanalys för den långsamma trendregeln: grannparametrar och parkombinationer.
Skriver results/robustness.csv.

    python backtest/robustness.py
"""

import json
import os

import pandas as pd

from common import DATA_DIR, RESULTS_DIR
import engine  # noqa: E402
from run_backtest import WARMUP, load, normalized  # noqa: E402
from strategies import buy_hold, ew_trend  # noqa: E402

COMBOS = {
    "BTC+ETH": ["BTC/USD", "ETH/USD"],
    "bas": ["BTC/USD", "ETH/USD", "SOL/USD"],
    "bas+LINK+XRP": ["BTC/USD", "ETH/USD", "SOL/USD", "LINK/USD", "XRP/USD"],
    "mellan": ["DOGE/USD", "AVAX/USD", "LINK/USD", "XRP/USD"],
    "bas+mellan": ["BTC/USD", "ETH/USD", "SOL/USD", "DOGE/USD", "AVAX/USD", "LINK/USD", "XRP/USD"],
    "alla8": ["BTC/USD", "ETH/USD", "SOL/USD", "DOGE/USD", "AVAX/USD", "LINK/USD", "XRP/USD", "SUI/USD"],
}
PARAMS = [(720, 0.03), (960, 0.03), (1200, 0.02), (1200, 0.03), (1200, 0.05), (1440, 0.03)]


def main():
    opens, closes = load()
    spreads = {p: v["mean_spread"] for p, v in
               json.load(open(os.path.join(DATA_DIR, "kraken_spreads.json")))["pairs"].items()}
    t0 = closes.index[WARMUP]
    split = t0 + (closes.index[-1] - t0) / 2
    periods = {"ar1": (t0, split), "ar2": (split, None), "hela": (t0, None)}
    rows = []
    for name, pairs in COMBOS.items():
        strats = [("buy_hold", normalized(buy_hold))] + [
            (f"ew_sma{n}_b{b * 100:.0f}", normalized(ew_trend(n, b))) for n, b in PARAMS]
        for label, s in strats:
            r = {"combo": name, "strategy": label}
            for per, (a, b) in periods.items():
                _, st = engine.run(opens[pairs], closes[pairs], s, spreads, start=a, end=b, warmup=WARMUP)
                r[per] = st["ret"]
                if per == "hela":
                    r.update(maxdd=st["maxdd"], trades=st["trades"], costs=st["costs"], sharpe=st["sharpe"])
            rows.append(r)
            print(f"{name:14} {label:14} år1 {r['ar1']:+.1%}  år2 {r['ar2']:+.1%}  hela {r['hela']:+.1%}  "
                  f"DD {r['maxdd']:+.1%}  trades {r['trades']}")
    pd.DataFrame(rows).to_csv(os.path.join(RESULTS_DIR, "robustness.csv"), index=False)


if __name__ == "__main__":
    main()
