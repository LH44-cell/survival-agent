"""Delade hjälpfunktioner för backtest-skripten."""

import os
import sys

import ccxt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))  # så att repots config.py går att importera
DATA_DIR = os.path.join(HERE, "data")
RESULTS_DIR = os.path.join(HERE, "results")

# Universum i tre nivåer. Alla par handlas på Kraken mot USD.
TIERS = {
    "bas": ["BTC/USD", "ETH/USD", "SOL/USD"],
    "mellan": ["DOGE/USD", "AVAX/USD", "LINK/USD", "XRP/USD"],
    "hogvolatil": ["SUI/USD"],
}
ALL_PAIRS = [p for pairs in TIERS.values() for p in pairs]


def exchange(name):
    """ccxt-klient som går via miljöns HTTPS-proxy om en sådan finns."""
    opts = {"enableRateLimit": True}
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if proxy:
        opts["httpsProxy"] = proxy
    return getattr(ccxt, name)(opts)


def data_path(pair):
    return os.path.join(DATA_DIR, pair.replace("/", "_") + "_1h.csv")
