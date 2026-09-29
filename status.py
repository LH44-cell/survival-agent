"""Snabb översikt: python status.py"""
import json, os, config
for name in config.AGENTS:
    p = os.path.join("state", f"{name}.json")
    if not os.path.exists(p):
        print(f"{name}: inte startad"); continue
    s = json.load(open(p))
    eq = s["history"][-1]["equity"] if s["history"] else s["cash"]
    print(f"{name:6} | {'ALIVE' if s['alive'] else 'DEAD '} | runs {s['runs']:4} | equity {eq:8.4f} | "
          f"cash {s['cash']:8.4f} | compute {s['compute_spent']:.4f} | trades {len(s['trades'])} | pos {s['positions']}")
