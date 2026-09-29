"""Jämför handelsplatser via ccxt:s publika endpoints (inga nycklar): vilka av våra par som
finns som spot, minsta ordervärde, 24h-volym, spread och djup i orderboken.

    python backtest/venue_check.py [--venues kraken hyperliquid]

Skriver data/venues.json. En plats som inte går att nå (t.ex. nätverkspolicy) noteras med felet.
På Hyperliquid heter de överbryggade spot-tillgångarna ofta U-prefix (UBTC, UETH, USOL) och
kvoteras i USDC; skriptet provar båda namnformerna.
"""

import argparse
import json
import os
from datetime import datetime, timezone

from common import ALL_PAIRS, DATA_DIR, exchange

DEPTH_BAND = 0.005  # djup inom ±0,5 % från mitten


def candidates(ex, pair):
    base = pair.split("/")[0]
    names = []
    for b in (base, "U" + base, base.replace("BTC", "UBTC")):
        for q in ("USD", "USDC", "USDT"):
            names.append(f"{b}/{q}")
    return [s for s in dict.fromkeys(names) if s in ex.markets and ex.markets[s].get("spot")]


def book_stats(ex, symbol):
    ob = ex.fetch_order_book(symbol, limit=100)
    bid, ask = ob["bids"][0][0], ob["asks"][0][0]
    mid = (bid + ask) / 2
    depth_bid = sum(b[0] * b[1] for b in ob["bids"] if b[0] >= mid * (1 - DEPTH_BAND))
    depth_ask = sum(a[0] * a[1] for a in ob["asks"] if a[0] <= mid * (1 + DEPTH_BAND))
    return {"spread_bps": (ask - bid) / mid * 1e4, "depth_usd_0.5pct": min(depth_bid, depth_ask)}


def check(name):
    ex = exchange(name)
    try:
        ex.load_markets()
    except Exception as e:  # t.ex. 403 från nätverkspolicyn
        return {"reachable": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}
    out = {"reachable": True, "pairs": {}}
    for pair in ALL_PAIRS:
        syms = candidates(ex, pair)
        if not syms:
            out["pairs"][pair] = {"listed": False}
            continue
        sym = syms[0]
        m = ex.markets[sym]
        t = ex.fetch_ticker(sym)
        qv = t.get("quoteVolume") or ((t.get("baseVolume") or 0) * (t.get("last") or 0))
        limits = m.get("limits") or {}
        out["pairs"][pair] = {
            "listed": True, "symbol": sym,
            "min_cost": (limits.get("cost") or {}).get("min"),
            "min_amount": (limits.get("amount") or {}).get("min"),
            "min_amount_usd": ((limits.get("amount") or {}).get("min") or 0) * (t.get("last") or 0),
            "volume_24h_usd": qv,
            **book_stats(ex, sym),
        }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--venues", nargs="+", default=["kraken", "hyperliquid"])
    args = ap.parse_args()
    res = {"checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "venues": {}}
    for v in args.venues:
        res["venues"][v] = check(v)
        print(v, json.dumps(res["venues"][v], indent=1)[:3000])
    with open(os.path.join(DATA_DIR, "venues.json"), "w") as f:
        json.dump(res, f, indent=2)


if __name__ == "__main__":
    main()
