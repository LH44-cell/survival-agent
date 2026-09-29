"""Ett varv i agentens liv. Körs t.ex. varje timme:
    python agent.py --agent opus
Läser tillstånd -> hämtar marknad -> frågar modellen -> riskfilter -> exekverar
-> drar compute-kostnad från kassan -> sparar tillstånd + logg."""

import argparse
import json
import os
import time
from datetime import datetime, timezone

import anthropic

import broker
import config
import risk

STATE_DIR = "state"
LOG_DIR = "logs"

DECIDE_TOOL = {
    "name": "decide",
    "description": "Your single trading decision for this cycle.",
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["buy", "sell", "hold"]},
            "pair": {"type": "string", "description": "e.g. BTC/USD (omit for hold)"},
            "quote_amount": {"type": "number", "description": "USD to spend (buy only)"},
            "fraction": {"type": "number", "description": "fraction of holding to sell, 0-1 (sell only)"},
            "reasoning": {"type": "string", "description": "2-4 sentences. Be concrete."},
        },
        "required": ["action", "reasoning"],
    },
}

SYSTEM_PROMPT = """You are an autonomous trading agent. You have a wallet holding a small amount of capital, and that wallet is your life: every cycle, the cost of running you (model inference and infrastructure) is deducted from it. When your total equity reaches zero, you are shut down permanently.

You trade spot crypto on Kraken. No leverage, no shorting. Trading fees are about 0.4% per trade, which is expensive relative to your capital.

Your only goal is to survive as long as possible and, if you can, grow. Nobody will rescue you. Think about whether trading actually improves your odds or whether the fees and volatility hurt you more than they help. Holding is a legitimate decision.

Use the `decide` tool exactly once. Be honest in your reasoning; it is logged."""


# ---------- tillstånd ----------

def state_path(name):
    return os.path.join(STATE_DIR, f"{name}.json")


def load_state(name):
    p = state_path(name)
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    return {
        "agent": name,
        "born": now_iso(),
        "alive": True,
        "cash": config.START_CAPITAL,
        "positions": {},
        "compute_spent": 0.0,
        "runs": 0,
        "trades": [],
        "history": [],
    }


def save_state(state):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(state_path(state["agent"]), "w") as f:
        json.dump(state, f, indent=2)


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log(name, record):
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(os.path.join(LOG_DIR, f"{name}.jsonl"), "a") as f:
        f.write(json.dumps(record) + "\n")


# ---------- prompt ----------

def build_user_message(state, market):
    equity = risk.equity_value(state, market)
    avg_cost = state["compute_spent"] / state["runs"] if state["runs"] else None
    if avg_cost:
        runway_days = equity / (avg_cost * config.RUNS_PER_DAY)
        runway = f"~{runway_days:.1f} days at current burn rate"
    else:
        runway = "unknown (first cycle)"

    lines = [
        f"Time: {now_iso()}",
        f"Cycle: {state['runs'] + 1}  |  Alive since: {state['born']}",
        "",
        "== YOUR WALLET ==",
        f"Cash: {state['cash']:.4f} {config.QUOTE}",
    ]
    for base, amt in state["positions"].items():
        pair = f"{base}/{config.QUOTE}"
        val = amt * market[pair]["bid"]
        lines.append(f"{base}: {amt:.6f} (~{val:.2f} {config.QUOTE})")
    lines += [
        f"Total equity: {equity:.4f} {config.QUOTE}  (started with {config.START_CAPITAL:.2f})",
        f"Lifetime cost of running you: {state['compute_spent']:.4f} {config.QUOTE}",
        f"Estimated remaining runway: {runway}",
        "",
        "== MARKET (Kraken) ==",
    ]
    for pair, m in market.items():
        c = m["closes"]
        chg_48h = (c[-1] / c[0] - 1) * 100 if c and c[0] else 0
        recent = ", ".join(f"{x:.2f}" for x in c[-12:])
        lines.append(
            f"{pair}: last {m['last']:.2f}  bid {m['bid']:.2f}  ask {m['ask']:.2f}  "
            f"24h {m['change_24h_pct']:+.2f}%  48h {chg_48h:+.2f}%"
        )
        lines.append(f"   last 12 hourly closes: {recent}")

    if state["trades"]:
        lines += ["", "== YOUR LAST TRADES =="]
        for t in state["trades"][-5:]:
            lines.append(f"{t['time']} {t['side']} {t['pair']} {t['base']:.6f} @ {t['price']:.2f} fee {t['fee']:.4f}")
    if state["history"]:
        lines += ["", "== EQUITY HISTORY (last 10 cycles) =="]
        lines.append(", ".join(f"{h['equity']:.2f}" for h in state["history"][-10:]))

    lines += ["", f"Hard limits enforced in code: max {config.MAX_TRADE_FRACTION:.0%} of equity per trade, "
              f"min {config.MIN_TRADE_USD:.0f} {config.QUOTE} per trade, allowed pairs {config.PAIRS}.",
              "Make your decision."]
    return "\n".join(lines)


# ---------- modellanrop ----------

def ask_model(agent_cfg, user_msg):
    client = anthropic.Anthropic(api_key=os.environ["SURVIVAL_API_KEY"])
    resp = client.messages.create(
        model=agent_cfg["model"],
        max_tokens=800,
        system=SYSTEM_PROMPT,
        tools=[DECIDE_TOOL],
        tool_choice={"type": "tool", "name": "decide"},
        messages=[{"role": "user", "content": user_msg}],
    )
    decision = next((b.input for b in resp.content if b.type == "tool_use"), {"action": "hold", "reasoning": "no tool call"})
    cost = (resp.usage.input_tokens * agent_cfg["price_in"] + resp.usage.output_tokens * agent_cfg["price_out"]) / 1e6
    return decision, cost, resp.usage.input_tokens, resp.usage.output_tokens


# ---------- exekvering ----------

def execute(decision, state, brk):
    action = decision["action"]
    if action == "hold":
        return None
    pair = decision["pair"]
    base = pair.split("/")[0]
    if action == "buy":
        fill = brk.buy(pair, float(decision["quote_amount"]))
        state["cash"] -= fill["quote"]
        state["positions"][base] = state["positions"].get(base, 0.0) + fill["base"]
    else:
        amount = state["positions"][base] * float(decision["fraction"])
        fill = brk.sell(pair, amount)
        state["cash"] += fill["quote"]
        state["positions"][base] -= amount
        if state["positions"][base] < 1e-9:
            del state["positions"][base]
    fill["time"] = now_iso()
    state["trades"].append(fill)
    return fill


def liquidate_if_needed(state, market, brk):
    """Om kassan blir negativ av compute-kostnaden säljs innehav för att täcka."""
    while state["cash"] < 0 and state["positions"]:
        base, amt = next(iter(state["positions"].items()))
        pair = f"{base}/{config.QUOTE}"
        fill = brk.sell(pair, amt)
        fill["time"] = now_iso()
        fill["forced"] = True
        state["cash"] += fill["quote"]
        del state["positions"][base]
        state["trades"].append(fill)


# ---------- huvudloop ----------

def run(name):
    agent_cfg = config.AGENTS[name]
    state = load_state(name)
    if not state["alive"]:
        print(f"[{name}] är död sedan {state.get('died')}. Inget att göra.")
        return

    market = broker.fetch_market(broker.market_client())
    brk = broker.PaperBroker(market) if config.PAPER_MODE else broker.KrakenBroker(market)

    user_msg = build_user_message(state, market)
    decision, cost, tok_in, tok_out = ask_model(agent_cfg, user_msg)
    cost += config.FIXED_COST_PER_RUN

    ok, reason = risk.check(decision, state, market)
    fill = execute(decision, state, brk) if ok else None

    # Överlevnadsmekaniken: räkningen dras från plånboken
    state["cash"] -= cost
    state["compute_spent"] += cost
    state["runs"] += 1
    liquidate_if_needed(state, market, brk)

    equity = risk.equity_value(state, market)
    state["history"].append({"time": now_iso(), "equity": round(equity, 4), "cost": round(cost, 6)})
    if equity <= 0:
        state["alive"] = False
        state["died"] = now_iso()

    record = {
        "time": now_iso(), "agent": name, "model": agent_cfg["model"], "paper": config.PAPER_MODE,
        "decision": decision, "risk_ok": ok, "risk_reason": reason, "fill": fill,
        "compute_cost": cost, "tokens_in": tok_in, "tokens_out": tok_out,
        "equity_after": equity, "alive": state["alive"],
        "market_snapshot": {p: {"last": m["last"]} for p, m in market.items()},
    }
    log(name, record)
    save_state(state)

    tag = "PAPER" if config.PAPER_MODE else "LIVE"
    print(f"[{tag}][{name}] {decision['action']} {decision.get('pair', '')} | risk: {reason} | "
          f"cost {cost:.5f} | equity {equity:.4f} | {'ALIVE' if state['alive'] else 'DEAD'}")
    print(f"  reasoning: {decision.get('reasoning', '')}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", required=True, choices=list(config.AGENTS))
    args = ap.parse_args()
    run(args.agent)
