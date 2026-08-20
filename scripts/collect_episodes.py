"""Pick a representative set of episodes and inline their screenshots.

Images are resized + JPEG-compressed before base64. Embedding the raw PNGs is
what turns a report like this into a 200 MB file: these screenshots are
1280x720 PNGs, ~180 kB each, and there are 4300 of them.
"""
import base64, io, json, re, sys
from collections import defaultdict
from pathlib import Path

import PIL.Image

STUDY = Path("/local3/yuhan/projects/agent-as-annotators/results/"
             "2026-08-17_17-01-11_genericagent-mcgill-nlp-a3-qwen3-5-9b-on-webarena-full")
DATA = json.load(open("/local3/yuhan/tmp/a3dash/data.json"))
OUT = Path("/local3/yuhan/tmp/a3dash/episodes.json")
MAXW, QUALITY, MAX_STEPS = 880, 70, 10

def thumb(p):
    try:
        im = PIL.Image.open(p).convert("RGB")
    except Exception:
        return None
    if im.width > MAXW:
        im = im.resize((MAXW, round(im.height * MAXW / im.width)), PIL.Image.LANCZOS)
    b = io.BytesIO()
    im.save(b, "JPEG", quality=QUALITY, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()

rows = {(r["task_id"], r["archived"]): r for r in DATA["rows"]}
vis = [r for r in DATA["rows"] if not r["archived"]]

picked, seen = [], set()
def take(r, why):
    if r is None or (r["task_id"], r["archived"]) in seen:
        return
    seen.add((r["task_id"], r["archived"]))
    picked.append((r, why))

by_site = defaultdict(list)
for r in vis:
    if r["status"] in ("done", "error"):
        by_site["+".join(sorted(r["sites"]))].append(r)
for site, rs in sorted(by_site.items(), key=lambda kv: -len(kv[1])):
    solved = sorted([x for x in rs if (x.get("reward") or 0) > 0], key=lambda x: x.get("n_steps") or 0)
    failed = sorted([x for x in rs if not (x.get("reward") or 0)],
                    key=lambda x: -(x.get("n_steps") or 0))
    for r in solved[:1] + solved[-1:] if len(solved) > 1 else solved[:1]:
        take(r, "solved")
    for r in failed[:1]:
        take(r, "failed at the step cap" if (r.get("n_steps") or 0) >= 30 else "failed")

# The two incident episodes, from the archived copies of the original run.
take(rows.get((106, True)), "INCIDENT: renderer wedged inside frame.evaluate; killed at 2181 s, took 298 tasks with it")
take(rows.get((131, True)), "INCIDENT: killed on step 29 of 30, ~30 s from finishing; took 147 tasks with it")
# and whatever is executing right now
for r in vis:
    if r["status"] == "running":
        take(r, "running right now")

eps = []
for r, why in picked:
    d = STUDY / r["dir"]
    shots = sorted(d.glob("screenshot_step_*.png"),
                   key=lambda p: int(re.search(r"_(\d+)\.png$", p.name).group(1)))
    if len(shots) > MAX_STEPS:
        keep = set(range(MAX_STEPS - 3)) | {len(shots) - 3, len(shots) - 2, len(shots) - 1}
        shots = [s for i, s in enumerate(shots) if i in keep]
    steps = {s["i"]: s for s in r.get("steps", [])}
    acts = r.get("actions", [])
    frames = []
    for p in shots:
        i = int(re.search(r"_(\d+)\.png$", p.name).group(1))
        st = steps.get(i, {})
        frames.append({"i": i, "img": thumb(p),
                       "action": acts[i] if i < len(acts) else None,
                       "agent": st.get("agent"), "env": st.get("env")})
    eps.append({
        "task_id": r["task_id"], "why": why, "sites": r["sites"], "intent": r["intent"],
        "reward": r.get("reward"), "n_steps": r.get("n_steps"), "status": r["status"],
        "archived": r["archived"], "fuzzy": r["fuzzy"], "eval_types": r["eval_types"],
        "err_msg": r.get("err_msg", ""), "errs": r.get("errs", {}),
        "cum_agent_elapsed": r.get("cum_agent_elapsed"),
        "cum_step_elapsed": r.get("cum_step_elapsed"),
        "max_output_tokens": r.get("max_output_tokens"),
        "n_shots_total": r["n_screens"], "frames": frames,
        "all_actions": acts,
    })

json.dump({"episodes": eps}, open(OUT, "w"))
print(f"{len(eps)} episodes, {sum(len(e['frames']) for e in eps)} frames "
      f"-> {OUT.stat().st_size/1e6:.1f} MB")
for e in eps:
    print(f"  webarena.{e['task_id']:<4} {'+'.join(e['sites']):<20} r={e['reward']} "
          f"steps={e['n_steps']} frames={len(e['frames'])}  {e['why'][:60]}")
