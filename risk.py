"""Säkerhetslagret. Modellen kan ignorera instruktioner, men inte en if-sats.
Returnerar (ok, reason). Om ok=False exekveras inget."""

import os
import config


def check(decision, state, market):
    action = decision.get("action")
    pair = decision.get("pair")

    if os.path.exists("KILL_SWITCH"):
        return False, "KILL_SWITCH-filen finns – all handel stoppad"

    if action == "hold":
        return True, "hold"

    if action not in ("buy", "sell"):
        return False, f"okänd action: {action}"

    if pair not in config.PAIRS:
        return False, f"otillåtet par: {pair}"

    equity = equity_value(state, market)

    if action == "buy":
        amt = float(decision.get("quote_amount") or 0)
        if amt < config.MIN_TRADE_USD:
            return False, f"för litet köp ({amt:.2f} < {config.MIN_TRADE_USD})"
        if amt > equity * config.MAX_TRADE_FRACTION:
            return False, f"köp {amt:.2f} överstiger {config.MAX_TRADE_FRACTION:.0%} av eget kapital"
        if amt > state["cash"]:
            return False, f"otillräcklig kassa ({state['cash']:.2f} < {amt:.2f})"
        return True, "ok"

    if action == "sell":
        base = pair.split("/")[0]
        held = state["positions"].get(base, 0.0)
        frac = float(decision.get("fraction") or 0)
        if held <= 0:
            return False, f"inget innehav i {base}"
        if not 0 < frac <= 1:
            return False, f"ogiltig andel att sälja: {frac}"
        if held * frac * market[pair]["bid"] < config.MIN_TRADE_USD:
            return False, "försäljningen är under minsta ordervärde"
        return True, "ok"

    return False, "oväntat tillstånd"


def equity_value(state, market):
    total = state["cash"]
    for base, amt in state["positions"].items():
        pair = f"{base}/{config.QUOTE}"
        if pair in market and amt > 0:
            total += amt * market[pair]["bid"]
    return total
