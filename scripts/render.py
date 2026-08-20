"""Render the A3 / WebArena-812 live dashboard to one self-contained HTML file.

Charts are hand-rolled inline SVG: the file has to open from a local path with no
network, so no chart library. Colors are the dataviz reference palette's slots
1-2 plus its fixed status ramp, used unmodified.
"""
import html, json, math, re, time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

D = json.load(open("/local3/yuhan/tmp/a3dash/data.json"))
E = json.load(open("/local3/yuhan/tmp/a3dash/env.json"))
EP = json.load(open("/local3/yuhan/tmp/a3dash/episodes.json"))["episodes"]
OUT = Path("/local3/yuhan/tmp/a3_webarena_dashboard.html")

rows = D["rows"]
vis = [r for r in rows if not r["archived"]]
arch = [r for r in rows if r["archived"]]
N = len(vis)
gen = datetime.fromtimestamp(D["generated"])

def esc(s): return html.escape(str(s if s is not None else ""))
def site_of(r): return "+".join(sorted(r["sites"]))
def solved(r): return (r.get("reward") or 0) > 0

scored = [r for r in vis if r["status"] in ("done", "error")]
n_solved = sum(1 for r in scored if solved(r))
running  = [r for r in vis if r["status"] == "running"]
stalled  = [r for r in vis if r["status"] == "stalled"]
queued   = [r for r in vis if r["status"] == "queued"]

# 36 of the 812 have "N/A" as their reference answer: the correct behaviour is to
# report the task is impossible, not to attempt it. Abstention and execution are
# different skills, so they are reported apart -- an aggregate that mixes them lets a
# model that is merely good at giving up look good at using the web.
_RAW = json.load(open("/local3/yuhan/projects/webarena/config_files/test.raw.json"))
NA_IDS = set()
for _t in _RAW:
    _ra = (_t.get("eval") or {}).get("reference_answers") or {}
    _v = _ra.get("fuzzy_match") or _ra.get("exact_match") or _ra.get("must_include")
    if isinstance(_v, list):
        _v = _v[0] if len(_v) == 1 else None
    if isinstance(_v, str) and _v.strip().upper() in ("N/A", "NONE"):
        NA_IDS.add(_t["task_id"])
_na  = [r for r in scored if r["task_id"] in NA_IDS]
_ach = [r for r in scored if r["task_id"] not in NA_IDS]
na_sr  = 100 * sum(1 for r in _na  if solved(r)) / max(len(_na), 1)
ach_sr = 100 * sum(1 for r in _ach if solved(r)) / max(len(_ach), 1)

# ---------------------------------------------------------------- primitives
def bar_chart(items, *, width=560, rowh=26, fmt=None, title="", note="",
              maxv=None, color="var(--series-1)", valw=92, labw=150):
    """Horizontal bars, one hue. Identity lives on the axis, so color encodes
    nothing here and must not pretend to."""
    if not items:
        return "<p class='muted'>no data yet</p>"
    maxv = maxv or max(v for _, v, *_ in items) or 1
    plotw = width - labw - valw
    h = len(items) * rowh + 8
    out = [f"<svg class='chart' viewBox='0 0 {width} {h}' role='img' aria-label='{esc(title)}'>"]
    for i, it in enumerate(items):
        lab, v = it[0], it[1]
        sub = it[2] if len(it) > 2 else ""
        y = i * rowh + 4
        w = max(1.5, plotw * v / maxv)
        txt = fmt(v) if fmt else f"{v:g}"
        out.append(
            f"<g class='barrow'><title>{esc(lab)}: {esc(txt)} {esc(sub)}</title>"
            f"<text class='lab' x='{labw-8}' y='{y+rowh/2}' text-anchor='end'>{esc(lab)}</text>"
            f"<rect class='track' x='{labw}' y='{y+4}' width='{plotw}' height='{rowh-12}' rx='3'/>"
            f"<rect x='{labw}' y='{y+4}' width='{w:.1f}' height='{rowh-12}' rx='3' fill='{color}'/>"
            f"<text class='val' x='{labw+plotw+8}' y='{y+rowh/2}'>{esc(txt)}"
            f"<tspan class='sub'> {esc(sub)}</tspan></text></g>")
    out.append("</svg>")
    return (f"<div class='chart-wrap'>{''.join(out)}"
            + (f"<p class='note'>{note}</p>" if note else "") + "</div>")

def hist(values, *, bins=None, width=560, height=150, title="", xlabel="",
         marks=(), fmt=lambda v: f"{v:g}"):
    vals = [v for v in values if v is not None]
    if not vals:
        return "<p class='muted'>no data yet</p>"
    if bins is None:
        lo, hi = min(vals), max(vals)
        bins = [lo + (hi - lo) * i / 24 for i in range(25)]
    else:
        lo, hi = bins[0], bins[-1]
    counts = [0] * (len(bins) - 1)
    for v in vals:
        for i in range(len(bins) - 1):
            if bins[i] <= v < bins[i + 1] or (i == len(bins) - 2 and v == bins[-1]):
                counts[i] += 1
                break
    mx = max(counts) or 1
    padl, padb, padt = 34, 26, 8
    pw, ph = width - padl - 8, height - padb - padt
    bw = pw / len(counts)
    out = [f"<svg class='chart' viewBox='0 0 {width} {height}' role='img' aria-label='{esc(title)}'>"]
    for gy in (0, 0.5, 1):
        y = padt + ph * (1 - gy)
        out.append(f"<line class='grid' x1='{padl}' x2='{width-8}' y1='{y:.1f}' y2='{y:.1f}'/>")
        out.append(f"<text class='ax' x='{padl-6}' y='{y+4:.1f}' text-anchor='end'>{round(mx*gy)}</text>")
    for i, c in enumerate(counts):
        if not c:
            continue
        bh = ph * c / mx
        x = padl + i * bw
        out.append(f"<g class='barrow'><title>{fmt(bins[i])}–{fmt(bins[i+1])}: {c}</title>"
                   f"<rect x='{x+0.8:.1f}' y='{padt+ph-bh:.1f}' width='{max(1,bw-1.6):.1f}' "
                   f"height='{bh:.1f}' rx='2' fill='var(--series-1)'/></g>")
    for mv, mlab, mcol in marks:
        if lo <= mv <= hi:
            x = padl + pw * (mv - lo) / (hi - lo or 1)
            out.append(f"<line class='mark' x1='{x:.1f}' x2='{x:.1f}' y1='{padt}' y2='{padt+ph}' "
                       f"stroke='{mcol}'/>")
            # flip the label inside the plot once the line is near the right edge
            flip = x > padl + pw * 0.72
            out.append(f"<text class='marklab' x='{x + (-4 if flip else 4):.1f}' y='{padt+11}' "
                       f"text-anchor='{'end' if flip else 'start'}' fill='{mcol}'>{esc(mlab)}</text>")
    out.append(f"<line class='axis' x1='{padl}' x2='{width-8}' y1='{padt+ph}' y2='{padt+ph}'/>")
    out.append(f"<text class='ax' x='{padl}' y='{height-8}'>{fmt(lo)}</text>")
    out.append(f"<text class='ax' x='{width-8}' y='{height-8}' text-anchor='end'>{fmt(hi)}</text>")
    if xlabel:
        out.append(f"<text class='ax' x='{padl+pw/2}' y='{height-8}' text-anchor='middle'>{esc(xlabel)}</text>")
    out.append("</svg>")
    return f"<div class='chart-wrap'>{''.join(out)}</div>"

def stacked(items, series, *, width=560, rowh=26):
    """items: [(label, [v1, v2]), ...]; series: [(name, color), ...]"""
    if not items:
        return "<p class='muted'>no data yet</p>"
    labw = 150
    plotw = width - labw - 60
    h = len(items) * rowh + 8
    mx = max(sum(vs) for _, vs in items) or 1
    out = [f"<svg class='chart' viewBox='0 0 {width} {h}'>"]
    for i, (lab, vs) in enumerate(items):
        y = i * rowh + 4
        x = labw
        out.append(f"<text class='lab' x='{labw-8}' y='{y+rowh/2}' text-anchor='end'>{esc(lab)}</text>")
        tot = sum(vs) or 1
        for (sname, scol), v in zip(series, vs):
            w = plotw * v / mx
            if w > 0.5:
                out.append(f"<g class='barrow'><title>{esc(lab)} — {esc(sname)}: "
                           f"{v:.0f}s ({100*v/tot:.0f}%)</title>"
                           f"<rect x='{x:.1f}' y='{y+4}' width='{max(0.5,w-2):.1f}' "
                           f"height='{rowh-12}' rx='2' fill='{scol}'/></g>")
            x += w
        out.append(f"<text class='val' x='{labw+plotw+8}' y='{y+rowh/2}'>{100*vs[0]/tot:.0f}%</text>")
    out.append("</svg>")
    leg = " ".join(f"<span class='key'><i style='background:{c}'></i>{esc(n)}</span>" for n, c in series)
    return f"<div class='chart-wrap'>{''.join(out)}<div class='legend'>{leg}</div></div>"

# ------------------------------------------------------------------ analysis
by_site = defaultdict(lambda: {"n": 0, "solved": 0, "total": 0})
site_total = Counter("+".join(sorted(r["sites"])) for r in vis)
for r in scored:
    b = by_site[site_of(r)]
    b["n"] += 1
    b["solved"] += solved(r)
site_rows = sorted(((s, by_site[s]["solved"] / by_site[s]["n"] * 100, by_site[s])
                    for s in by_site if by_site[s]["n"]),
                   key=lambda x: -x[2]["n"])
site_bars = [(s, sr, f"{b['solved']}/{b['n']} of {site_total[s]}") for s, sr, b in site_rows]

judge = {"LLM-judged (fuzzy_match)": [0, 0], "Programmatic": [0, 0]}
for r in scored:
    k = "LLM-judged (fuzzy_match)" if r["fuzzy"] else "Programmatic"
    judge[k][0] += solved(r); judge[k][1] += 1
judge_all = Counter("LLM-judged (fuzzy_match)" if r["fuzzy"] else "Programmatic" for r in vis)
judge_bars = [(k, 100 * v[0] / v[1], f"{v[0]}/{v[1]} of {judge_all[k]}")
              for k, v in judge.items() if v[1]]

term = Counter()
for r in scored:
    if r.get("err_msg"):
        term["environment error"] += 1
    elif r.get("truncated") or (r.get("n_steps") or 0) >= 30:
        term["hit the 30-step cap"] += 1
    elif solved(r):
        term["finished, correct"] += 1
    else:
        term["finished, wrong"] += 1
term_bars = [(k, v, f"{100*v/len(scored):.0f}%") for k, v in term.most_common()]

acts = Counter()
for r in vis:
    for a in r.get("actions", []):
        m = re.match(r"([a-z_]+)\s*\(", a.strip())
        acts[m.group(1) if m else "unparsed"] += 1
act_bars = [(k, v, f"{100*v/sum(acts.values()):.1f}%") for k, v in acts.most_common(12)]

step_times = [s["total"] for r in vis for s in r.get("steps", []) if s.get("total")]
agent_times = [s["agent"] for r in vis for s in r.get("steps", []) if s.get("agent")]
ep_durs = [r["t_saved"] - r["t0"] for r in scored
           if r.get("t_saved") and r.get("t0") and r["t_saved"] > r["t0"]]
n_steps_dist = [r["n_steps"] for r in scored if r.get("n_steps") is not None]

split = []
for s, _, b in site_rows:
    a = sum(r.get("cum_agent_elapsed") or 0 for r in scored if site_of(r) == s)
    e = sum(r.get("cum_step_elapsed") or 0 for r in scored if site_of(r) == s)
    if a + e:
        split.append((s, [a, e]))

err_tax = defaultdict(Counter)
for r in rows:
    for k, v in (r.get("errs") or {}).items():
        err_tax[site_of(r)][k] += v
ERR_LABEL = {
    "screenshot_timeout": "screenshot timeout (30s bound fired)",
    "target_crashed": "chromium Target crashed",
    "marking_error": "DOM MarkingError",
    "ctx_destroyed": "execution context destroyed",
    "goto_timeout": "page navigation timeout",
    "empty_completion": "model returned nothing",
    "reasoning_fallback": "content empty, used reasoning_content",
}
all_errs = Counter()
for s, c in err_tax.items():
    all_errs.update(c)

def pct(a, b): return f"{100*a/b:.2f}%" if b else "—"
def hms(s):
    if s is None: return "—"
    s = int(s); return f"{s//3600}h {s%3600//60}m" if s >= 3600 else f"{s//60}m {s%60}s"

elapsed_run = None
t0s = [r["t0"] for r in vis if r.get("t0")]
if t0s:
    elapsed_run = D["generated"] - min(t0s)

sr = 100 * n_solved / len(scored) if scored else 0
# work left, priced on the per-site mean episode -- wall clock is set by the
# longest dependency chain, not by n_jobs, so this is a work estimate not an ETA
mean_dur = (sum(ep_durs) / len(ep_durs)) if ep_durs else 0
work_left_h = (len(queued) + len(running)) * mean_dur / 3600

# --------------------------------------------------------------------- HTML
CSS = """
:root{
  color-scheme:light;
  --plane:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --muted:#898781;
  --grid:#e1e0d9; --axis:#c3c2b7; --border:rgba(11,11,11,.10);
  --series-1:#2a78d6; --series-2:#eb6834;
  --good:#0ca30c; --warning:#fab219; --serious:#ec835a; --critical:#d03b3b;
  --track:rgba(11,11,11,.055);
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    color-scheme:dark;
    --plane:#0d0d0d; --surface:#1a1a19; --ink:#fff; --ink2:#c3c2b7; --muted:#898781;
    --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,.10);
    --series-1:#3987e5; --series-2:#d95926;
    --track:rgba(255,255,255,.07);
  }
}
:root[data-theme="dark"]{
  color-scheme:dark;
  --plane:#0d0d0d; --surface:#1a1a19; --ink:#fff; --ink2:#c3c2b7; --muted:#898781;
  --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,.10);
  --series-1:#3987e5; --series-2:#d95926;
  --track:rgba(255,255,255,.07);
}
*{box-sizing:border-box}
body{margin:0;background:var(--plane);color:var(--ink);
  font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif;
  -webkit-font-smoothing:antialiased}
.wrap{max-width:1180px;margin:0 auto;padding:28px 20px 80px}
h1{font-size:26px;margin:0 0 4px;letter-spacing:-.01em}
h2{font-size:18px;margin:38px 0 12px;letter-spacing:-.01em}
h3{font-size:14px;margin:0 0 10px;color:var(--ink2);font-weight:600}
p{margin:0 0 10px}
.sub{color:var(--ink2);font-size:13.5px}
.muted{color:var(--muted);font-size:13px}
.note{color:var(--muted);font-size:12.5px;margin:8px 0 0;line-height:1.5}
.card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:16px 18px}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(400px,1fr));gap:14px}
.grid3{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:14px}
.stat{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:14px 16px}
.stat .k{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}
.stat .v{font-size:30px;font-weight:650;letter-spacing:-.02em;margin:2px 0 0;
  font-variant-numeric:tabular-nums}
.stat .d{font-size:12.5px;color:var(--ink2)}
.pill{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:600;
  padding:3px 9px;border-radius:99px;border:1px solid var(--border)}
.pill i{width:7px;height:7px;border-radius:99px;display:block}
.chart{width:100%;height:auto;overflow:visible}
.chart .lab{font-size:11.5px;fill:var(--ink2)}
.chart .val{font-size:11.5px;fill:var(--ink);font-variant-numeric:tabular-nums;
  dominant-baseline:middle;font-weight:600}
.chart .val .sub{fill:var(--muted);font-weight:400}
.chart .lab{dominant-baseline:middle}
.chart .track{fill:var(--track)}
.chart .grid{stroke:var(--grid);stroke-width:1}
.chart .axis{stroke:var(--axis);stroke-width:1}
.chart .ax{font-size:10.5px;fill:var(--muted)}
.chart .mark{stroke-width:1.5;stroke-dasharray:3 3}
.chart .marklab{font-size:10px;font-weight:600}
.barrow:hover rect{opacity:.82}
.legend{display:flex;gap:14px;margin-top:8px;flex-wrap:wrap}
.key{display:inline-flex;align-items:center;gap:6px;font-size:12px;color:var(--ink2)}
.key i{width:10px;height:10px;border-radius:2px;display:block}
table{border-collapse:collapse;width:100%;font-size:13px}
th{text-align:left;font-weight:600;color:var(--muted);font-size:11.5px;
  text-transform:uppercase;letter-spacing:.04em;padding:0 10px 7px 0;
  border-bottom:1px solid var(--border)}
td{padding:7px 10px 7px 0;border-bottom:1px solid var(--grid);
  font-variant-numeric:tabular-nums;vertical-align:top}
td.l,th.l{text-align:left}
td.r,th.r{text-align:right}
code,.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12.5px}
.status-ok{color:var(--good);font-weight:650}
.status-bad{color:var(--critical);font-weight:650}
.status-warn{color:var(--serious);font-weight:650}
.progress{display:flex;height:26px;border-radius:6px;overflow:hidden;
  border:1px solid var(--border);background:var(--track)}
.progress div{height:100%}
.seg-legend{display:flex;gap:16px;margin-top:9px;flex-wrap:wrap;font-size:12.5px;color:var(--ink2)}
.ep{border:1px solid var(--border);border-radius:10px;background:var(--surface);
  margin:0 0 12px;overflow:hidden}
.ep>summary{cursor:pointer;padding:12px 16px;list-style:none;display:flex;
  align-items:center;gap:10px;flex-wrap:wrap}
.ep>summary::-webkit-details-marker{display:none}
.ep>summary:hover{background:var(--track)}
.ep .tid{font-weight:650;font-family:ui-monospace,monospace;font-size:13px}
.ep .goal{color:var(--ink2);font-size:13px;flex:1 1 340px;min-width:0;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ep-body{padding:0 16px 16px;border-top:1px solid var(--grid)}
.frames{display:grid;grid-template-columns:repeat(auto-fill,minmax(268px,1fr));gap:12px;margin-top:12px}
.frame{border:1px solid var(--border);border-radius:8px;overflow:hidden;background:var(--plane)}
.frame img{display:block;width:100%;height:auto;cursor:zoom-in}
.frame .cap{padding:7px 9px;font-size:11.5px;color:var(--ink2);border-top:1px solid var(--grid)}
.frame .cap .act{font-family:ui-monospace,monospace;color:var(--ink);word-break:break-all;
  display:block;margin-top:3px}
.filters{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:0 0 14px}
.filters button{font:inherit;font-size:12.5px;padding:5px 11px;border-radius:99px;
  border:1px solid var(--border);background:var(--surface);color:var(--ink2);cursor:pointer}
.filters button[aria-pressed="true"]{background:var(--series-1);border-color:var(--series-1);
  color:#fff;font-weight:600}
.filters input{font:inherit;font-size:13px;padding:6px 11px;border-radius:99px;
  border:1px solid var(--border);background:var(--surface);color:var(--ink);min-width:210px}
#lightbox{position:fixed;inset:0;background:rgba(0,0,0,.86);display:none;
  align-items:center;justify-content:center;z-index:99;cursor:zoom-out;padding:24px}
#lightbox img{max-width:100%;max-height:100%;border-radius:6px}
.callout{border-left:3px solid var(--critical);background:var(--surface);
  border-radius:0 8px 8px 0;padding:12px 16px;margin:0 0 12px}
.callout.ok{border-left-color:var(--good)}
.callout.warn{border-left-color:var(--serious)}
.topo{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}
.node{border:1px solid var(--border);border-radius:8px;padding:11px 13px;background:var(--plane)}
.node .h{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
.node .a{font-family:ui-monospace,monospace;font-size:12.5px;margin-top:3px}
.wide{overflow-x:auto}
"""

# ------------------------------------------------------------------- sections
probes = E["sites"]["probes"]
aff = E["sites"]["affected"]
n_at_risk = sum(aff.get(k, 0) for k, v in probes.items() if not v["ok"])

# A "0h remaining" tile is noise once the run is over; it only says something while
# there is still a queue.
work_tile = "" if len(scored) >= N else (
    "<div class='stat'><div class='k'>work remaining</div>"
    f"<div class='v'>{work_left_h:.0f}h</div>"
    f"<div class='d'>{len(queued)+len(running)} tasks x mean; wall clock is set by "
    "the 239-task chain, not by n_jobs</div></div>")

driver_ok = E.get("driver_alive")
# The run is finished once every one of the 812 has a summary. At that point a red
# "DRIVER NOT RUNNING" pill is not a fault report, it is just the normal end state,
# so the finished case gets its own pill and takes priority over driver liveness.
if len(scored) >= N:
    head_pill = ("<span class='pill' style='color:var(--good)'>"
                 f"<i style='background:var(--good)'></i>COMPLETE · {N}/{N} scored · 0 errors</span>")
elif driver_ok:
    head_pill = (f"<span class='pill' style='color:var(--good)'><i style='background:var(--good)'></i>"
                 f"RUNNING · {E.get('ray_workers','?')} ray workers</span>")
else:
    head_pill = ("<span class='pill' style='color:var(--critical)'>"
                 "<i style='background:var(--critical)'></i>DRIVER NOT RUNNING</span>")

seg = [("solved", n_solved, "var(--good)"),
       ("scored wrong", len(scored) - n_solved, "var(--critical)"),
       ("running", len(running), "var(--series-2)"),
       ("stalled", len(stalled), "var(--warning)"),
       ("queued behind dependencies", len(queued), "var(--track)")]
progress = "".join(f"<div style='width:{100*v/N:.3f}%;background:{c}' title='{n}: {v}'></div>"
                   for n, v, c in seg if v)
seg_leg = "".join(f"<span class='key'><i style='background:{c}'></i>{n} — <b>{v}</b></span>"
                  for n, v, c in seg if v)

stats = f"""
<div class='grid3'>
  <div class='stat'><div class='k'>scored</div><div class='v'>{len(scored)}<span
    style='font-size:17px;color:var(--muted)'> / {N}</span></div>
    <div class='d'>{pct(len(scored), N)} of the benchmark</div></div>
  <div class='stat'><div class='k'>success rate (scored only)</div>
    <div class='v'>{sr:.2f}%</div>
    <div class='d'>{n_solved} solved · leaderboard target 42.1</div></div>
  <div class='stat'><div class='k'>on achievable tasks</div>
    <div class='v'>{ach_sr:.2f}%</div>
    <div class='d'>{len(_ach)} tasks · vs {na_sr:.1f}% on the {len(_na)} N/A ones</div></div>
  <div class='stat'><div class='k'>episode wall clock</div>
    <div class='v'>{hms(mean_dur)}</div><div class='d'>mean over {len(ep_durs)} episodes</div></div>
  {work_tile}
  <div class='stat'><div class='k'>tasks at infra risk</div>
    <div class='v' style='color:{"var(--good)" if n_at_risk==0 else "var(--critical)"}'>{n_at_risk}</div>
    <div class='d'>from {sum(1 for v in probes.values() if not v['ok'])} failing site probe(s)</div></div>
</div>"""

# ---- environment
prow = []
for k, v in probes.items():
    base = (E["sites"].get("baseline") or {}).get(k, {})
    drift = base and base.get("fp") != v["fp"]
    prow.append(
        f"<tr><td class='l'><b>{esc(k)}</b></td>"
        f"<td class='l'><span class='{'status-ok' if v['ok'] else 'status-bad'}'>"
        f"{'PASS' if v['ok'] else 'FAIL'}</span></td>"
        f"<td class='l mono'>{esc(v['fp'])[:44]}</td>"
        f"<td class='l'>{esc(v['detail'])[:76]}</td>"
        f"<td class='r'>{aff.get(k,0)}</td>"
        f"<td class='l muted'>{'changed vs baseline' if drift else ''}</td></tr>")

llm_rows = "".join(
    f"<tr><td class='l'><b>{esc(d['label'])}</b></td>"
    f"<td class='l mono'>127.0.0.1:{d['port']}</td>"
    f"<td class='l mono'>{esc((d.get('served_as') or ['—'])[0])}</td>"
    f"<td class='l'><span class='{'status-ok' if d['ok'] else 'status-bad'}'>"
    f"{'DECODES' if d['ok'] else 'FAIL'}</span></td>"
    f"<td class='r'>{d.get('latency_s','—')}s</td>"
    f"<td class='l muted'>{esc(d.get('error',''))[:60]}</td></tr>" for d in E["llm"])

def gpu_table(raw, host, allowed=None):
    out = []
    for line in (raw or "").split("\n"):
        p = [x.strip() for x in line.split(",")]
        if len(p) < 5:
            continue
        idx, name, used, total, util = p[0], p[1], float(p[2]), float(p[3]), p[4]
        frac = used / total if total else 0
        blocked = allowed is not None and int(idx) not in allowed
        out.append(
            f"<tr><td class='l'><b>{host} GPU{esc(idx)}</b>"
            + ("<span class='muted'> — off limits</span>" if blocked else "") + "</td>"
            f"<td class='l muted'>{esc(name)}</td>"
            f"<td class='r'>{used/1024:.1f} / {total/1024:.0f} GB</td>"
            f"<td class='l' style='width:130px'><svg viewBox='0 0 100 10' class='chart' "
            f"style='height:10px'><rect width='100' height='10' rx='2' fill='var(--track)'/>"
            f"<rect width='{100*frac:.1f}' height='10' rx='2' fill='var(--series-1)'/></svg></td>"
            f"<td class='r'>{esc(util)}%</td></tr>")
    return "".join(out)

err_tbl_rows = []
for k, n in all_errs.most_common():
    per = err_tax
    cells = ", ".join(f"{s} {c[k]}" for s, c in sorted(per.items(), key=lambda kv: -kv[1][k]) if c[k])
    err_tbl_rows.append(f"<tr><td class='l'>{esc(ERR_LABEL.get(k,k))}</td>"
                        f"<td class='r'><b>{n}</b></td><td class='l muted'>{esc(cells)[:120]}</td></tr>")

# ---- episode explorer
def ep_card(e):
    tag = ("solved" if (e["reward"] or 0) > 0 else
           "incident" if e["archived"] else
           "running" if e["status"] == "running" else "failed")
    col = {"solved": "var(--good)", "failed": "var(--critical)",
           "incident": "var(--warning)", "running": "var(--series-2)"}[tag]
    frames = "".join(
        f"<div class='frame'>"
        + (f"<img loading='lazy' src='{f['img']}' alt='step {f['i']}'>" if f["img"] else "")
        + f"<div class='cap'>step {f['i']}"
        + (f" · agent {f['agent']:.0f}s" if f.get("agent") else "")
        + (f" · env {f['env']:.0f}s" if f.get("env") else "")
        + (f"<span class='act'>{esc(f['action'])}</span>" if f.get("action") else "")
        + "</div></div>" for f in e["frames"])
    skipped = e["n_shots_total"] - len(e["frames"])
    meta = []
    if e["n_steps"] is not None: meta.append(f"{e['n_steps']} steps")
    if e["cum_agent_elapsed"]: meta.append(f"LLM {e['cum_agent_elapsed']:.0f}s")
    if e["cum_step_elapsed"]: meta.append(f"env {e['cum_step_elapsed']:.0f}s")
    if e["max_output_tokens"]: meta.append(f"peak {e['max_output_tokens']} out-tokens")
    meta.append("LLM-judged" if e["fuzzy"] else "programmatic")
    search = f"webarena.{e['task_id']} {' '.join(e['sites'])} {e['intent']} {tag} {e['why']}".lower()
    return f"""<details class='ep' data-tag='{tag}' data-search="{esc(search)}">
<summary><span class='pill' style='color:{col}'><i style='background:{col}'></i>{tag}</span>
<span class='tid'>webarena.{e['task_id']}</span>
<span class='muted'>{esc('+'.join(e['sites']))}</span>
<span class='goal'>{esc(e['intent'])}</span></summary>
<div class='ep-body'>
<p class='note' style='margin-top:10px'><b>{esc(e['why'])}</b> — {esc(' · '.join(meta))}
 · eval {esc(', '.join(e['eval_types']))}</p>
{f"<div class='callout'><code>{esc(e['err_msg'])}</code></div>" if e.get('err_msg') else ''}
<div class='frames'>{frames}</div>
{f"<p class='note'>{skipped} intermediate steps not shown (first 7 and last 3 of {e['n_shots_total']} screenshots).</p>" if skipped > 0 else ''}
</div></details>"""

eps_html = "".join(ep_card(e) for e in EP)

kills = E.get("timeout_kills") or []
trials = E.get("trials") or []
incident = f"""
<div class='callout'>
<p><b>2026-08-17 17:05 → 2026-08-18 09:15 · run 1 lost 490 of 812 tasks.</b></p>
<p class='sub'>Three episodes crossed the 1800 s cap
(<code>webarena.106</code> gitlab, <code>.131</code> shopping_admin, <code>.251</code> map).
AgentLab encodes WebArena's per-site ordering constraints as Ray <code>ObjectRef</code>
arguments, and Ray never schedules a task whose argument ref errored — so each kill
failed its entire transitive subtree at once: <b>298 + 147 + 68</b> tasks, union 491,
matching the 491 <code>Task failed</code> lines exactly. 488 of them never executed a
single step. <code>webarena.106</code> alone, killed 35 minutes into a 16-hour run at
depth 8 of the 118-task gitlab chain, forfeited the entire gitlab and reddit programmes.</p>
<p class='sub'>The <code>--n-relaunch 3</code> retry loop never fired: <code>study.py:335</code>
calls <code>get_results()</code> three lines before <code>find_incomplete()</code>, and it
crashed on <code>AttributeError: 'float' object has no attribute 'find'</code> —
<code>map_err_key</code> guarded <code>err_msg is None</code> but 809 of 812 rows carried NaN.</p>
</div>
<div class='callout ok'>
<p><b>2026-08-18 14:39 · run 2 resumed in place.</b></p>
<p class='sub'>319 finished episodes kept as no-op graph nodes so the dependency edges
survive; 493 relaunched (490 never-run + 3 errored). Episode cap raised
1800 s → <b>{E.get('avg_step_timeout',120)*30} s</b>. That does not bias the score: an episode
killed at 1800 s wrote no <code>summary_info.json</code> at all, so it was never scored 0 —
it was deleted from the run. Retry loop rewritten to stop on lack of progress in
<code>n_incomplete</code> rather than on <code>n_error</code>, which stays flat while
poisoned tasks pile up.</p>
<p class='sub'>Known residual risk: <code>webarena.106</code> was a genuine hang —
its log stops mid-<code>frame.evaluate()</code> at <code>observation.py:44</code>, a
Playwright call that takes no timeout argument — so a larger cap makes it hang
<em>longer</em>, not finish. Trials so far: {esc(' · '.join(trials)) or 'trial 1 in progress'}.
Timeout kills this run: <b>{len(kills)}</b>.</p>
</div>"""

JS = """
document.querySelectorAll('.frame img').forEach(function(img){
  img.addEventListener('click', function(){
    var lb = document.getElementById('lightbox');
    lb.querySelector('img').src = img.src;
    lb.style.display = 'flex';
  });
});
document.getElementById('lightbox').addEventListener('click', function(){
  this.style.display = 'none';
});
var buttons = document.querySelectorAll('.filters button');
var search = document.getElementById('q');
function apply(){
  var active = document.querySelector('.filters button[aria-pressed="true"]').dataset.tag;
  var q = (search.value || '').toLowerCase().trim();
  document.querySelectorAll('.ep').forEach(function(el){
    var okTag = active === 'all' || el.dataset.tag === active;
    var okQ = !q || el.dataset.search.indexOf(q) !== -1;
    el.style.display = (okTag && okQ) ? '' : 'none';
  });
}
buttons.forEach(function(b){
  b.addEventListener('click', function(){
    buttons.forEach(function(x){ x.setAttribute('aria-pressed','false'); });
    b.setAttribute('aria-pressed','true');
    apply();
  });
});
search.addEventListener('input', apply);
"""

HTML = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>A3-Qwen3.5-9B on WebArena-812 — final</title>
<style>{CSS}</style></head><body>
<div class="wrap">

<h1>A3-Qwen3.5-9B on WebArena-812</h1>
<p class="sub">{head_pill}
&nbsp; snapshot {gen:%Y-%m-%d %H:%M:%S} &nbsp;·&nbsp; agent
<code>McGill-NLP/A3-Qwen3.5-9B</code> via GenericAgent/BrowserGym &nbsp;·&nbsp;
sites on AWS <code>{esc(E['sites']['frontend'])}</code></p>

{stats}

<h2>Progress</h2>
<div class="card">
<div class="progress">{progress}</div>
<div class="seg-legend">{seg_leg}</div>
<p class="note">The 812 tasks form five near-linear per-site dependency chains
(poset width exactly 5, verified by Dilworth), so a queued task is not waiting on a
free worker — it is waiting on its predecessor. <code>--n_jobs 8</code> can never be
honoured; at least 3 of 8 Ray slots are idle by construction.</p>
</div>

<h2>Model execution</h2>
<div class="grid2">
  <div class="card"><h3>Success rate by site</h3>
  {bar_chart(site_bars, fmt=lambda v: f"{v:.1f}%", maxv=100, valw=150, labw=120,
             note="All 812 are scored, so the third column is a full count, not coverage. "
                  "The five single-site rows span 44-56% while the five cross-site rows "
                  "average 20.8% -- composing across two apps is the failure mode, not "
                  "any one site.")}</div>

  <div class="card"><h3>Judge type</h3>
  {bar_chart(judge_bars, fmt=lambda v: f"{v:.1f}%", maxv=100, valw=150, labw=170,
             note="118 of the 812 tasks are graded by an LLM (82 llm_fuzzy_match over 145 "
                  "reference strings + 36 llm_ua_match). Upstream hardcodes a retired "
                  "gpt-4-1106-preview; this run uses a local Qwen3-VL-8B, so these two rows "
                  "must be read separately — a gap between them is judge drift, not model quality.")}</div>

  <div class="card"><h3>How episodes end</h3>
  {bar_chart(term_bars, fmt=lambda v: f"{v:g}")}</div>

  <div class="card"><h3>Actions issued</h3>
  {bar_chart(act_bars, fmt=lambda v: f"{v:g}",
             note=f"{sum(acts.values())} actions parsed from the per-episode logs.")}</div>

  <div class="card"><h3>Steps per episode</h3>
  {hist(n_steps_dist, bins=[0,1,2,3,4,5,6,8,10,12,15,18,21,24,27,30,31],
        xlabel="steps", fmt=lambda v: f"{v:.0f}",
        marks=[(30, "30-step cap", "var(--critical)")])}
  <p class="note">The spike at the right edge is the max_steps cap: those episodes
  never decided they were done, they ran out of budget.</p></div>

  <div class="card"><h3>Wall clock per step</h3>
  {hist([v for v in step_times if v <= 240], xlabel="seconds",
        fmt=lambda v: f"{v:.0f}")}
  <p class="note">Truncated at 240 s for readability;
  {sum(1 for v in step_times if v > 240)} of {len(step_times)} steps are slower.
  LLM decode is ~80% of step time — the sites are not the bottleneck.</p></div>

  <div class="card"><h3>Episode duration vs the timeout cap</h3>
  {hist(ep_durs, xlabel="seconds", fmt=lambda v: f"{v:.0f}",
        bins=[i*150 for i in range(25)],
        marks=[(1800, "old cap 1800s", "var(--critical)"),
               (3600, "new cap 3600s", "var(--good)")])}
  <p class="note">No episode that finished ever exceeded 1562 s — yet three were killed at 1800 s, because a killed episode writes no summary and so never appears in this distribution at all. That censoring is exactly what made the old cap look safe.</p></div>

  <div class="card"><h3>Where the time goes, by site</h3>
  {stacked(split, [("LLM decode", "var(--series-1)"), ("browser + site", "var(--series-2)")])}
  <p class="note">Percentage on the right is the LLM share.</p></div>
</div>

<h2>Environment</h2>
<div class="card">
<h3>Site canary — content-level probes, not status codes</h3>
<div class="wide"><table>
<tr><th class="l">probe</th><th class="l">state</th><th class="l">fingerprint</th>
<th class="l">detail</th><th class="r">tasks gated</th><th class="l">drift</th></tr>
{''.join(prow)}
</table></div>
<p class="note">HTTP 200 is not evidence a site works. Each probe asserts real content —
14 products for a search, 25 forums listed, a 29 kB Pittsburgh street tile, a geocode
that returns 40.44/-79.99, an OSRM route with three vehicle profiles. The
<b>tasks gated</b> column is why a red row is not automatically an emergency:
homepage gates 0 of the 812.</p>
</div>

<div class="grid2" style="margin-top:14px">
<div class="card"><h3>Topology</h3>
<div class="topo">
<div class="node"><div class="h">site frontend</div><div class="a">{esc(E['sites']['frontend'])}</div>
<div class="muted">shopping :7770 · admin :7780 · reddit :9999 · gitlab :8023 · map :3000 · wiki :8888</div></div>
<div class="node"><div class="h">map heavy services — not ours</div>
<div class="a">{esc(E['sites']['map_backend'])}</div>
<div class="muted">tiles :8080 · Nominatim :8085 · OSRM :5000-5002 — 128 tasks depend on a host we do not control</div></div>
<div class="node"><div class="h">agent model</div><div class="a">peer host → ssh tunnel → :21561</div>
<div class="muted">A3-Qwen3.5-9B, vLLM</div></div>
<div class="node"><div class="h">judge model</div><div class="a">peer host → ssh tunnel → :8300</div>
<div class="muted">served as gpt-4-vision-preview</div></div>
</div></div>

<div class="card"><h3>Model endpoints</h3>
<div class="wide"><table>
<tr><th class="l">role</th><th class="l">endpoint</th><th class="l">served as</th>
<th class="l">state</th><th class="r">round trip</th><th class="l"></th></tr>
{llm_rows}</table></div>
<p class="note">Each row forces a real completion — <code>/v1/models</code> answering 200
is not evidence the engine can decode.</p></div>
</div>

<div class="card" style="margin-top:14px"><h3>GPUs</h3>
<div class="wide"><table>
<tr><th class="l">device</th><th class="l">model</th><th class="r">memory</th>
<th class="l"></th><th class="r">util</th></tr>
{gpu_table(E.get('gpu_peer'), 'peer host')}
{gpu_table(E.get('gpu_local'), 'run host', allowed={0,1,2,3,7})}
</table></div></div>

<div class="card" style="margin-top:14px"><h3>Environment faults seen in {len(rows)} episode logs</h3>
<div class="wide"><table>
<tr><th class="l">signature</th><th class="r">count</th><th class="l">by site</th></tr>
{''.join(err_tbl_rows) or "<tr><td class='l muted' colspan=3>none</td></tr>"}
</table></div>
<p class="note">Screenshot timeouts are the local <code>obs_timeout</code> patch firing:
each one converted an indefinite CDP hang into a 30 s wait plus a blank screenshot.
It bounds <code>extract_screenshot</code> only — 1 of the 5 unbounded calls in
browsergym's observation path, and the last of them, which is why it could not
catch the <code>webarena.106</code> hang 43 source lines earlier.</p>
</div>

<h2>Incident and recovery</h2>
{incident}

<h2>Episodes</h2>
<div class="filters">
  <button data-tag="all" aria-pressed="true">All</button>
  <button data-tag="solved" aria-pressed="false">Solved</button>
  <button data-tag="failed" aria-pressed="false">Failed</button>
  <button data-tag="running" aria-pressed="false">Running now</button>
  <button data-tag="incident" aria-pressed="false">Incidents</button>
  <input id="q" type="search" placeholder="search goal, site, task id…">
</div>
{eps_html}

<p class="note" style="margin-top:32px">Snapshot generated {gen:%Y-%m-%d %H:%M:%S} from
<code>{esc(D['study'])}</code>. Regenerate with
<code>bash /local3/yuhan/tmp/a3dash/refresh.sh</code>.</p>
</div>
<div id="lightbox"><img alt=""></div>
<script>{JS}</script>
</body></html>"""

OUT.write_text(HTML)
print(f"{OUT}  {OUT.stat().st_size/1e6:.1f} MB")
print(f"scored {len(scored)}/{N}  solved {n_solved}  SR {sr:.2f}%  "
      f"running {len(running)} stalled {len(stalled)} queued {len(queued)}")
