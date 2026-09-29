"""Hämtar 2 års timdata (OHLCV) för hela universumet.
Primär källa: Bitstamp. Fallback: Coinbase Exchange för par Bitstamp saknar
eller inte kan leverera full historik. Källan per par sparas i data/sources.json.

    python backtest/fetch_data.py [--days 730]
"""

import argparse
import csv
import json
import os
import time

from common import ALL_PAIRS, DATA_DIR, data_path, exchange

HOUR_MS = 3_600_000
SOURCES = [("bitstamp", 1000), ("coinbaseexchange", 300)]  # (ccxt-id, max staplar per anrop)


def fetch_all(ex, pair, since, until, page):
    bars, cursor = {}, since
    while cursor < until:
        chunk = ex.fetch_ohlcv(pair, "1h", since=cursor, limit=page)
        chunk = [b for b in chunk if b[0] >= cursor]
        if not chunk:
            cursor += page * HOUR_MS  # hål i datan – hoppa fram
            continue
        for b in chunk:
            if b[0] < until:
                bars[b[0]] = b
        cursor = chunk[-1][0] + HOUR_MS
    return [bars[t] for t in sorted(bars)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=730)
    args = ap.parse_args()

    os.makedirs(DATA_DIR, exist_ok=True)
    until = (int(time.time() * 1000) // HOUR_MS) * HOUR_MS
    since = until - args.days * 24 * HOUR_MS
    expected = args.days * 24
    sources = {}

    clients = {}
    for pair in ALL_PAIRS:
        for name, page in SOURCES:
            ex = clients.setdefault(name, exchange(name))
            if not ex.markets:
                ex.load_markets()
            if pair not in ex.symbols:
                print(f"{pair}: saknas på {name}")
                continue
            bars = fetch_all(ex, pair, since, until, page)
            coverage = len(bars) / expected
            if not bars or bars[0][0] > since + 7 * 24 * HOUR_MS or coverage < 0.95:
                print(f"{pair}: {name} gav för lite historik ({len(bars)} staplar), provar nästa källa")
                continue
            with open(data_path(pair), "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["ts", "open", "high", "low", "close", "volume"])
                w.writerows(bars)
            sources[pair] = {
                "source": name,
                "bars": len(bars),
                "coverage": round(coverage, 4),
                "first": ex.iso8601(bars[0][0]),
                "last": ex.iso8601(bars[-1][0]),
            }
            print(f"{pair}: {len(bars)} staplar från {name} ({coverage:.1%} täckning)")
            break
        else:
            raise SystemExit(f"{pair}: ingen källa kunde leverera 2 års historik")

    with open(os.path.join(DATA_DIR, "sources.json"), "w") as f:
        json.dump(sources, f, indent=2)


if __name__ == "__main__":
    main()
