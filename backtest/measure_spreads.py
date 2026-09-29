"""Mäter faktisk genomsnittlig spread per par i Krakens orderbok.
Tar ett ögonblicksfoto av toppen av boken för alla par var --interval sekund
under --samples varv. Resultat (relativ spread = (ask - bid) / mid) sparas i
data/kraken_spreads.json och används som slippage i backtesten.

    python backtest/measure_spreads.py [--samples 60 --interval 30]
"""

import argparse
import json
import os
import statistics
import time
from datetime import datetime, timezone

from common import ALL_PAIRS, DATA_DIR, exchange


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", type=int, default=60)
    ap.add_argument("--interval", type=float, default=30.0)
    args = ap.parse_args()

    kraken = exchange("kraken")
    obs = {p: [] for p in ALL_PAIRS}
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for i in range(args.samples):
        t0 = time.time()
        for pair in ALL_PAIRS:
            try:
                ob = kraken.fetch_order_book(pair, limit=10)
            except Exception as e:  # enstaka nätverksfel ska inte fälla mätningen
                print(f"  {pair}: {e}")
                continue
            bid, ask = ob["bids"][0][0], ob["asks"][0][0]
            obs[pair].append((ask - bid) / ((ask + bid) / 2))
        print(f"varv {i + 1}/{args.samples}")
        time.sleep(max(0.0, args.interval - (time.time() - t0)))

    out = {"measured_from": started,
           "measured_to": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "samples": args.samples, "interval_s": args.interval, "pairs": {}}
    for pair, xs in obs.items():
        out["pairs"][pair] = {
            "mean_spread": statistics.fmean(xs),
            "median_spread": statistics.median(xs),
            "max_spread": max(xs),
            "n": len(xs),
        }
        print(f"{pair:10} medel {statistics.fmean(xs) * 1e4:6.2f} bps  median {statistics.median(xs) * 1e4:6.2f} bps")
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, "kraken_spreads.json"), "w") as f:
        json.dump(out, f, indent=2)


if __name__ == "__main__":
    main()
