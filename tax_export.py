"""Skatteunderlag (K4 avsnitt D) från RIKTIGA trades, med genomsnittsmetoden.
Papperstrades ignoreras. Kursen USD/EUR -> SEK hämtas per handelsdag från ECB
via frankfurter.app.

    python tax_export.py --year 2026

Ger k4_<year>.csv. Detta är ett underlag, inte skatterådgivning – kontrollera
mot Skatteverkets vägledning om kryptotillgångar innan du deklarerar."""

import argparse
import csv
import json
import os
from datetime import datetime, timezone
from functools import lru_cache

import requests

import config


@lru_cache(maxsize=None)
def sek_rate(date_str):
    """Kurs för 1 QUOTE (USD/EUR) i SEK på given dag (ECB, senaste bankdag)."""
    r = requests.get(f"https://api.frankfurter.app/{date_str}",
                     params={"from": config.QUOTE, "to": "SEK"}, timeout=20)
    r.raise_for_status()
    return r.json()["rates"]["SEK"]


def all_live_trades():
    trades = []
    for name in config.AGENTS:
        p = os.path.join("state", f"{name}.json")
        if not os.path.exists(p):
            continue
        with open(p) as f:
            for t in json.load(f)["trades"]:
                if not t.get("paper"):
                    t["agent"] = name
                    trades.append(t)
    return sorted(trades, key=lambda t: t["ts"])


def build_k4(year):
    holdings = {}  # base -> {"amount": x, "cost_sek": y}
    rows = []
    for t in all_live_trades():
        day = datetime.fromtimestamp(t["ts"], tz=timezone.utc).strftime("%Y-%m-%d")
        rate = sek_rate(day)
        base = t["pair"].split("/")[0]
        h = holdings.setdefault(base, {"amount": 0.0, "cost_sek": 0.0})

        if t["side"] == "buy":
            # Omkostnadsbelopp = betalt belopp inkl. avgift, i SEK
            h["amount"] += t["base"]
            h["cost_sek"] += t["quote"] * rate
        else:
            if h["amount"] <= 0:
                continue
            avg = h["cost_sek"] / h["amount"]
            omkostnad = avg * t["base"]
            forsaljning = t["quote"] * rate  # netto efter avgift
            h["amount"] -= t["base"]
            h["cost_sek"] -= omkostnad
            if day.startswith(str(year)):
                rows.append({
                    "datum": day, "agent": t["agent"], "beteckning": base,
                    "antal": round(t["base"], 8),
                    "forsaljningspris_sek": round(forsaljning, 2),
                    "omkostnadsbelopp_sek": round(omkostnad, 2),
                    "vinst_forlust_sek": round(forsaljning - omkostnad, 2),
                })
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=datetime.now().year)
    args = ap.parse_args()
    rows = build_k4(args.year)
    out = f"k4_{args.year}.csv"
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["datum", "agent", "beteckning", "antal",
                                          "forsaljningspris_sek", "omkostnadsbelopp_sek", "vinst_forlust_sek"])
        w.writeheader()
        w.writerows(rows)
    vinst = sum(r["vinst_forlust_sek"] for r in rows if r["vinst_forlust_sek"] > 0)
    forlust = -sum(r["vinst_forlust_sek"] for r in rows if r["vinst_forlust_sek"] < 0)
    print(f"{len(rows)} avyttringar {args.year} -> {out}")
    print(f"Summa vinster: {vinst:.2f} SEK | Summa förluster: {forlust:.2f} SEK (avdragsgilla till 70 %)")
