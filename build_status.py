"""Bygger docs/index.html (statussidan) från state/ och logs/: python build_status.py

Allt bakas in i en enda HTML-fil – ingen server, inga externa beroenden.
"""
import html
import json
import os
from datetime import datetime, timezone

import config

STATE_DIR = "state"
LOG_DIR = "logs"
OUT = os.path.join("docs", "index.html")
RECENT_DECISIONS = 5


def load_state(name):
    p = os.path.join(STATE_DIR, f"{name}.json")
    if not os.path.exists(p):
        return None
    with open(p) as f:
        return json.load(f)


def load_log(name):
    p = os.path.join(LOG_DIR, f"{name}.jsonl")
    if not os.path.exists(p):
        return []
    out = []
    with open(p) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass  # en halvskriven rad ska inte sänka hela sidan
    return out


def esc(x):
    return html.escape(str(x), quote=True)


def fmt_time(iso):
    try:
        return datetime.fromisoformat(iso).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return str(iso or "")


def runway_days(state, equity):
    """Samma beräkning som agenten själv ser i sin prompt."""
    if not state["alive"]:
        return None
    if not state["runs"] or not state["compute_spent"]:
        return None
    avg_cost = state["compute_spent"] / state["runs"]
    return equity / (avg_cost * config.RUNS_PER_DAY)


def agent_summary(name, state, log):
    last_prices = {p: m.get("last") for p, m in (log[-1].get("market_snapshot") or {}).items()} if log else {}
    positions = []
    pos_value = 0.0
    for base, amt in state["positions"].items():
        price = last_prices.get(f"{base}/{config.QUOTE}")
        val = amt * price if price else None
        if val:
            pos_value += val
        positions.append((base, amt, val))
    equity = state["history"][-1]["equity"] if state["history"] else state["cash"] + pos_value
    return {
        "name": name,
        "model": config.AGENTS.get(name, {}).get("model", ""),
        "alive": state["alive"],
        "died": state.get("died"),
        "equity": equity,
        "cash": state["cash"],
        "positions": positions,
        "compute": state["compute_spent"],
        "trades": len(state["trades"]),
        "runs": state["runs"],
        "runway": runway_days(state, equity),
    }


def series_for(name, state):
    pts = [{"t": state["born"], "v": config.START_CAPITAL}]
    pts += [{"t": h["time"], "v": h["equity"]} for h in state["history"]]
    return {"name": name, "points": pts}


# ---------- HTML-delar ----------

def render_table(summaries):
    rows = []
    for s in summaries:
        if s["alive"]:
            status = '<span class="status">● Lever</span>'
        else:
            status = f'<span class="status dead">✕ Död {esc(fmt_time(s["died"]))}</span>'
        if s["positions"]:
            pos = "<br>".join(
                f'<span class="nowrap">{esc(b)} {a:.6f}</span>' + (f' <span class="muted">(~{v:.2f})</span>' if v is not None else "")
                for b, a, v in s["positions"]
            )
        else:
            pos = '<span class="muted">inga</span>'
        if s["runway"] is None:
            runway = "–" if not s["alive"] else '<span class="muted">okänd</span>'
        else:
            runway = f"~{s['runway']:.0f} dagar" if s["runway"] >= 10 else f"~{s['runway']:.1f} dagar"
        rows.append(
            "<tr>"
            f'<th scope="row" class="nowrap"><span class="key key-{esc(s["name"])}"></span>{esc(s["name"])}'
            f'<div class="muted small">{esc(s["model"])}</div></th>'
            f"<td>{status}</td>"
            f'<td class="num strong">{s["equity"]:.4f}</td>'
            f'<td class="num">{s["cash"]:.4f}</td>'
            f"<td>{pos}</td>"
            f'<td class="num">{s["compute"]:.4f}</td>'
            f'<td class="num">{s["trades"]}</td>'
            f'<td class="num">{s["runs"]}</td>'
            f'<td class="num">{runway}</td>'
            "</tr>"
        )
    q = esc(config.QUOTE)
    return (
        '<div class="table-wrap"><table>'
        "<thead><tr>"
        f'<th scope="col">Agent</th><th scope="col">Status</th><th scope="col" class="num">Eget kapital ({q})</th>'
        f'<th scope="col" class="num">Kassa ({q})</th><th scope="col">Innehav</th>'
        f'<th scope="col" class="num">Compute hittills ({q})</th><th scope="col" class="num">Trades</th>'
        '<th scope="col" class="num">Varv</th><th scope="col" class="num">Beräknad livslängd</th>'
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
    )


def render_decision(rec):
    d = rec.get("decision") or {}
    action = str(d.get("action", "?"))
    detail = []
    if d.get("pair"):
        detail.append(esc(d["pair"]))
    if action == "buy" and d.get("quote_amount") is not None:
        detail.append(f"{float(d['quote_amount']):.2f} {esc(config.QUOTE)}")
    if action == "sell" and d.get("fraction") is not None:
        detail.append(f"{float(d['fraction']):.0%}")
    risk = "" if rec.get("risk_ok", True) else f'<span class="blocked">⚠ Stoppad av riskfiltret: {esc(rec.get("risk_reason", ""))}</span>'
    return (
        '<li class="decision">'
        '<div class="decision-head">'
        f'<span class="action action-{esc(action)}">{esc(action.upper())}</span>'
        f'<span>{" · ".join(detail)}</span>'
        f'<time class="muted small">{esc(fmt_time(rec.get("time")))} UTC</time>'
        "</div>"
        f'<p>{esc(d.get("reasoning", ""))}</p>'
        f'<div class="muted small">kostnad {float(rec.get("compute_cost", 0)):.5f} {esc(config.QUOTE)} · '
        f'{rec.get("tokens_in", "?")} in / {rec.get("tokens_out", "?")} ut tokens · '
        f'eget kapital efter {float(rec.get("equity_after", 0)):.4f}</div>'
        f"{risk}"
        "</li>"
    )


def render_decisions(name, log):
    recent = list(reversed(log[-RECENT_DECISIONS:]))
    body = "".join(render_decision(r) for r in recent) if recent else '<li class="muted">Inga beslut ännu.</li>'
    return (
        f'<section class="card"><h3><span class="key key-{esc(name)}"></span>{esc(name)}</h3>'
        f'<ol class="decisions">{body}</ol></section>'
    )


def render_history_table(series):
    rows = []
    for s in series:
        for p in s["points"]:
            rows.append(f'<tr><td>{esc(s["name"])}</td><td>{esc(fmt_time(p["t"]))}</td><td class="num">{p["v"]:.4f}</td></tr>')
    return (
        '<details><summary>Visa som tabell</summary><div class="table-wrap"><table>'
        f'<thead><tr><th scope="col">Agent</th><th scope="col">Tid (UTC)</th><th scope="col" class="num">Eget kapital ({esc(config.QUOTE)})</th></tr></thead>'
        "<tbody>" + "".join(rows) + "</tbody></table></div></details>"
    )


PAGE = """<!doctype html>
<html lang="sv">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Survival Agents</title>
<style>
:root {
  color-scheme: light;
  --surface-0: #f5f5f3;
  --surface-1: #fcfcfb;
  --border: #e3e2de;
  --grid: #ebeae6;
  --text-primary: #0b0b0b;
  --text-secondary: #52514e;
  --text-muted: #75746f;
  --series-opus: #2a78d6;
  --series-fable: #eb6834;
  --warn: #9a5b00;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --surface-0: #111110;
    --surface-1: #1a1a19;
    --border: #2f2f2d;
    --grid: #262624;
    --text-primary: #ffffff;
    --text-secondary: #c3c2b7;
    --text-muted: #9a998f;
    --series-opus: #3987e5;
    --series-fable: #d95926;
    --warn: #eda100;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --surface-0: #111110;
  --surface-1: #1a1a19;
  --border: #2f2f2d;
  --grid: #262624;
  --text-primary: #ffffff;
  --text-secondary: #c3c2b7;
  --text-muted: #9a998f;
  --series-opus: #3987e5;
  --series-fable: #d95926;
  --warn: #eda100;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--surface-0); color: var(--text-primary);
  font: 15px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
}
main { max-width: 1100px; margin: 0 auto; padding: 24px 16px 48px; }
h1 { font-size: 1.6rem; margin: 0 0 4px; }
h2 { font-size: 1.15rem; margin: 32px 0 12px; }
h3 { font-size: 1rem; margin: 0 0 12px; display: flex; align-items: center; }
p.lead { color: var(--text-secondary); margin: 0; max-width: 70ch; }
.muted { color: var(--text-muted); }
.small { font-size: .82rem; }
.strong { font-weight: 600; }
.card { background: var(--surface-1); border: 1px solid var(--border); border-radius: 12px; padding: 16px; }
.table-wrap { overflow-x: auto; }
table { border-collapse: collapse; width: 100%%; font-variant-numeric: tabular-nums; }
th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--border); vertical-align: top; }
thead th { font-size: .8rem; font-weight: 600; color: var(--text-secondary); }
.nowrap { white-space: nowrap; }
tbody tr:last-child th, tbody tr:last-child td { border-bottom: 0; }
.num { text-align: right; white-space: nowrap; }
.key { display: inline-block; width: 14px; height: 3px; border-radius: 2px; margin-right: 8px; vertical-align: middle; }
.key-opus { background: var(--series-opus); }
.key-fable { background: var(--series-fable); }
.status { white-space: nowrap; }
.status.dead { color: var(--text-muted); }
.legend { display: flex; gap: 16px; font-size: .85rem; color: var(--text-secondary); margin-bottom: 8px; }
.legend span { display: inline-flex; align-items: center; }
#chart { position: relative; }
#chart svg { display: block; width: 100%%; height: 300px; overflow: visible; }
#chart .axis text { fill: var(--text-muted); font-size: 11px; }
#chart .grid line { stroke: var(--grid); }
#chart .ref { stroke: var(--text-muted); stroke-dasharray: 4 4; }
#chart .line { fill: none; stroke-width: 2; stroke-linejoin: round; stroke-linecap: round; }
#chart .dot { stroke: var(--surface-1); stroke-width: 2; }
#chart .endlabel { font-size: 12px; fill: var(--text-secondary); }
#chart .cross { stroke: var(--text-muted); }
.tip {
  position: absolute; pointer-events: none; background: var(--surface-1); border: 1px solid var(--border);
  border-radius: 8px; padding: 8px 10px; font-size: .82rem; box-shadow: 0 4px 16px rgb(0 0 0 / .12);
  white-space: nowrap; display: none; font-variant-numeric: tabular-nums;
}
.tip .row { display: flex; align-items: center; gap: 6px; }
.tip .val { font-weight: 600; color: var(--text-primary); }
.tip .lbl { color: var(--text-secondary); }
details { margin-top: 12px; }
summary { cursor: pointer; color: var(--text-secondary); font-size: .85rem; }
.grid-2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; }
ol.decisions { list-style: none; margin: 0; padding: 0; }
.decision { padding: 12px 0; border-top: 1px solid var(--border); }
.decision:first-child { border-top: 0; padding-top: 0; }
.decision p { margin: 6px 0; white-space: pre-wrap; overflow-wrap: anywhere; }
.decision-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 8px; }
.decision-head time { margin-left: auto; }
.action { font-size: .75rem; font-weight: 700; letter-spacing: .04em; padding: 1px 6px; border-radius: 4px; border: 1px solid var(--border); }
.blocked { display: block; margin-top: 4px; font-size: .85rem; color: var(--warn); }
footer { margin-top: 32px; font-size: .8rem; color: var(--text-muted); }
</style>
</head>
<body>
<main>
<header>
<h1>Survival Agents</h1>
<p class="lead">Två Claude-modeller fick %(start).2f %(quote)s var. Varje varv dras kostnaden för att köra dem från plånboken. Når eget kapital noll stängs de av för gott.</p>
<p class="muted small">%(mode)s · uppdaterad %(updated)s UTC</p>
</header>

<h2>Eget kapital över tid</h2>
<section class="card">
<div class="legend">%(legend)s<span><span class="key" style="background:none;border-top:1px dashed var(--text-muted);height:0"></span>startkapital</span></div>
<div id="chart"><noscript><p class="muted">Grafen kräver JavaScript – se tabellen nedan.</p></noscript></div>
%(history_table)s
</section>

<h2>Läge just nu</h2>
<section class="card">%(table)s</section>
<p class="muted small">Beräknad livslängd = eget kapital ÷ (snittkostnad per varv × %(runs_per_day)d varv/dag), samma uppskattning som agenten själv ser.</p>

<h2>Senaste besluten</h2>
<div class="grid-2">%(decisions)s</div>

<footer>Genereras av build_status.py efter varje varv.</footer>
</main>

<script type="application/json" id="data">%(data)s</script>
<script>
(function () {
  var data = JSON.parse(document.getElementById("data").textContent);
  var root = document.getElementById("chart");
  var NS = "http://www.w3.org/2000/svg";
  var series = data.series.filter(function (s) { return s.points.length; });
  if (!series.length) { root.textContent = "Ingen data ännu."; return; }
  series.forEach(function (s) { s.points.forEach(function (p) { p.ts = Date.parse(p.t); }); });

  function el(name, attrs, parent) {
    var e = document.createElementNS(NS, name);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }
  function color(name) { return "var(--series-" + name + ", var(--text-secondary))"; }
  function fmtT(ts) {
    var d = new Date(ts);
    return d.toISOString().slice(5, 16).replace("T", " ");
  }

  var tip = document.createElement("div");
  tip.className = "tip";

  function draw() {
    root.querySelectorAll("svg").forEach(function (n) { n.remove(); });
    var W = root.clientWidth || 600, H = 300;
    var m = { l: 48, r: 64, t: 12, b: 28 };
    var all = [];
    series.forEach(function (s) { all = all.concat(s.points); });
    var t0 = Math.min.apply(null, all.map(function (p) { return p.ts; }));
    var t1 = Math.max.apply(null, all.map(function (p) { return p.ts; }));
    var minSpan = 6 * 3600e3;  // korta förlopp: visa minst 6 h så att tidsaxeln går att läsa
    if (t1 - t0 < minSpan) { t1 = t0 + minSpan; }
    var vals = all.map(function (p) { return p.v; }).concat([data.start]);
    var v0 = Math.min.apply(null, vals), v1 = Math.max.apply(null, vals);
    var pad = Math.max((v1 - v0) * 0.15, 0.05);
    v0 = Math.max(0, v0 - pad); v1 += pad;
    var x = function (t) { return m.l + (t - t0) / (t1 - t0) * (W - m.l - m.r); };
    var y = function (v) { return m.t + (v1 - v) / (v1 - v0) * (H - m.t - m.b); };

    var svg = el("svg", { viewBox: "0 0 " + W + " " + H, role: "img",
      "aria-label": "Eget kapital över tid per agent" });
    var grid = el("g", { "class": "grid" }, svg), axis = el("g", { "class": "axis" }, svg);
    for (var i = 0; i <= 4; i++) {
      var v = v0 + (v1 - v0) * i / 4, yy = y(v);
      el("line", { x1: m.l, x2: W - m.r, y1: yy, y2: yy }, grid);
      el("text", { x: m.l - 8, y: yy + 4, "text-anchor": "end" }, axis).textContent = v.toFixed(2);
    }
    var nt = Math.max(2, Math.min(6, Math.floor((W - m.l - m.r) / 110)));
    for (var j = 0; j <= nt; j++) {
      var t = t0 + (t1 - t0) * j / nt;
      el("text", { x: x(t), y: H - 8, "text-anchor": j === 0 ? "start" : j === nt ? "end" : "middle" }, axis)
        .textContent = fmtT(t);
    }
    el("line", { "class": "ref", x1: m.l, x2: W - m.r, y1: y(data.start), y2: y(data.start) }, svg);

    series.forEach(function (s) {
      var d = s.points.map(function (p, k) { return (k ? "L" : "M") + x(p.ts).toFixed(1) + " " + y(p.v).toFixed(1); }).join("");
      el("path", { "class": "line", d: d, stroke: color(s.name) }, svg);
      var last = s.points[s.points.length - 1];
      el("circle", { "class": "dot", cx: x(last.ts), cy: y(last.v), r: 4, fill: color(s.name) }, svg);
      el("text", { "class": "endlabel", x: x(last.ts) + 8, y: y(last.v) + 4 }, svg).textContent = s.name;
    });

    var cross = el("line", { "class": "cross", y1: m.t, y2: H - m.b, visibility: "hidden" }, svg);
    var marks = series.map(function (s) {
      return el("circle", { "class": "dot", r: 4, fill: color(s.name), visibility: "hidden" }, svg);
    });
    var hit = el("rect", { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: "transparent" }, svg);

    function nearest(s, ts) {
      var best = null;
      s.points.forEach(function (p) { if (!best || Math.abs(p.ts - ts) < Math.abs(best.ts - ts)) best = p; });
      return best;
    }
    function show(evt) {
      var r = svg.getBoundingClientRect();
      var px = (evt.clientX - r.left) * W / r.width;
      var ts = t0 + (px - m.l) / (W - m.l - m.r) * (t1 - t0);
      var ref = null;
      series.forEach(function (s) { var p = nearest(s, ts); if (!ref || Math.abs(p.ts - ts) < Math.abs(ref.ts - ts)) ref = p; });
      cross.setAttribute("x1", x(ref.ts)); cross.setAttribute("x2", x(ref.ts));
      cross.setAttribute("visibility", "visible");
      tip.replaceChildren();
      var head = document.createElement("div");
      head.className = "lbl"; head.textContent = fmtT(ref.ts) + " UTC";
      tip.appendChild(head);
      series.forEach(function (s, k) {
        var p = nearest(s, ref.ts);
        marks[k].setAttribute("cx", x(p.ts)); marks[k].setAttribute("cy", y(p.v));
        marks[k].setAttribute("visibility", "visible");
        var row = document.createElement("div"); row.className = "row";
        var key = document.createElement("span"); key.className = "key key-" + s.name; key.style.marginRight = "0";
        var val = document.createElement("span"); val.className = "val"; val.textContent = p.v.toFixed(4);
        var lbl = document.createElement("span"); lbl.className = "lbl"; lbl.textContent = s.name;
        row.appendChild(key); row.appendChild(val); row.appendChild(lbl);
        tip.appendChild(row);
      });
      tip.style.display = "block";
      var left = x(ref.ts) * r.width / W + 12;
      if (left + tip.offsetWidth > root.clientWidth) left -= tip.offsetWidth + 24;
      tip.style.left = left + "px"; tip.style.top = "8px";
    }
    function hide() {
      cross.setAttribute("visibility", "hidden");
      marks.forEach(function (c) { c.setAttribute("visibility", "hidden"); });
      tip.style.display = "none";
    }
    hit.addEventListener("pointermove", show);
    hit.addEventListener("pointerleave", hide);
    root.insertBefore(svg, root.firstChild);
    root.appendChild(tip);
  }
  draw();
  var rt;
  window.addEventListener("resize", function () { clearTimeout(rt); rt = setTimeout(draw, 100); });
})();
</script>
</body>
</html>
"""


def build():
    summaries, series, decisions, legend = [], [], [], []
    for name in config.AGENTS:
        state = load_state(name)
        log = load_log(name)
        legend.append(f'<span><span class="key key-{esc(name)}"></span>{esc(name)}</span>')
        if state is None:
            decisions.append(render_decisions(name, []))
            continue
        summaries.append(agent_summary(name, state, log))
        series.append(series_for(name, state))
        decisions.append(render_decisions(name, log))

    data = json.dumps({"start": config.START_CAPITAL, "series": series})
    data = data.replace("<", "\\u003c")  # så att "</script>" aldrig kan bryta ut ur taggen

    page = PAGE % {
        "start": config.START_CAPITAL,
        "quote": esc(config.QUOTE),
        "mode": "Pappersläge (simulerade affärer på riktiga priser)" if config.PAPER_MODE else "LIVE – riktiga pengar på Kraken",
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        "legend": "".join(legend),
        "history_table": render_history_table(series),
        "table": render_table(summaries) if summaries else '<p class="muted">Inga agenter har körts ännu.</p>',
        "runs_per_day": config.RUNS_PER_DAY,
        "decisions": "".join(decisions),
        "data": data,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        f.write(page)
    print(f"skrev {OUT}")


if __name__ == "__main__":
    build()
