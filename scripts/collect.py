"""Scan the live A3/WebArena study and dump one JSON snapshot for the dashboard.

Deliberately reads only experiment.log + summary_info.json for the whole-study
statistics: a StepInfo pickle carries the full observation (screenshot arrays,
DOM, axtree) and costs ~0.24 s to unpickle, so 3800 of them would take 15 min.
The logs carry everything the aggregate views need. Step pickles are opened only
for the handful of episodes in the explorer.
"""
import gzip, json, os, pickle, re, subprocess, sys, time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

STUDY = Path("/local3/yuhan/projects/agent-as-annotators/results/"
             "2026-08-17_17-01-11_genericagent-mcgill-nlp-a3-qwen3-5-9b-on-webarena-full")
OUT = Path("/local3/yuhan/tmp/a3dash/data.json")
RAW = "/local3/yuhan/envs/a3/lib/python3.12/site-packages/webarena/test.raw.json"

TS = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),(\d{3})")
def ts(line):
    m = TS.match(line)
    if not m:
        return None
    return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").timestamp() + int(m.group(2)) / 1000

# error signatures worth separating; order matters, first match wins per line
ERR_SIGS = [
    ("screenshot_timeout", re.compile(r"extract_screenshot failed")),
    ("target_crashed",     re.compile(r"Target crashed")),
    ("marking_error",      re.compile(r"MarkingError")),
    ("ctx_destroyed",      re.compile(r"Execution context was destroyed")),
    ("goto_timeout",       re.compile(r"Page\.goto: Timeout")),
    ("empty_completion",   re.compile(r"model returned neither content nor reasoning_content")),
    ("reasoning_fallback", re.compile(r"empty content; falling back to reasoning_content")),
]
ACTION = re.compile(r"Agent chose action:\s*\n\s*(.+)")
STEP_START = re.compile(r"agentlab\.experiments\.loop - DEBUG - Starting step (\d+)\.")
SEND_ACTION = re.compile(r"loop - DEBUG - Sending action to environment\.")
ENV_STEPPED = re.compile(r"loop - DEBUG - Environment stepped\.")
SAVING = re.compile(r"loop - INFO - Saving experiment info\.")

meta = {}
for c in json.load(open(RAW)):
    ra = c["eval"].get("reference_answers") or {}
    meta[c["task_id"]] = {
        "sites": c["sites"],
        "fuzzy": "fuzzy_match" in ra,
        "intent": c["intent"],
        "eval_types": c["eval"]["eval_types"],
    }

def parse_log(path):
    """One pass over an experiment.log -> timings, actions, error tally."""
    out = {"t0": None, "t_last": None, "t_saved": None, "steps": [], "actions": [],
           "errs": Counter(), "n_log_steps": 0}
    cur = None            # (step_idx, t_start, t_send)
    try:
        lines = open(path, errors="replace").read().split("\n")
    except OSError:
        return out
    for i, line in enumerate(lines):
        t = ts(line)
        if t is not None:
            if out["t0"] is None:
                out["t0"] = t
            out["t_last"] = t
        for name, rx in ERR_SIGS:
            if rx.search(line):
                out["errs"][name] += 1
                break
        m = STEP_START.search(line)
        if m:
            if cur is not None and cur[1] is not None and t is not None:
                pass
            cur = [int(m.group(1)), t, None]
            out["n_log_steps"] = max(out["n_log_steps"], int(m.group(1)) + 1)
            continue
        if cur is not None and SEND_ACTION.search(line) and t is not None:
            cur[2] = t
            continue
        if cur is not None and ENV_STEPPED.search(line) and t is not None:
            idx, t_start, t_send = cur
            if t_start is not None:
                out["steps"].append({
                    "i": idx,
                    "agent": (t_send - t_start) if t_send else None,
                    "env": (t - t_send) if t_send else None,
                    "total": t - t_start,
                })
            cur = None
            continue
        if SAVING.search(line) and t is not None:
            out["t_saved"] = t
        if "Agent chose action:" in line and i + 1 < len(lines):
            act = lines[i + 1].strip()
            if act:
                out["actions"].append(act)
    return out

rows = []
now = time.time()
for d in sorted(STUDY.glob("*_GenericAgent-*_on_webarena.*_0")):
    name = d.name
    archived = name.startswith("_")
    m = re.search(r"webarena\.(\d+)_0$", name)
    if not m:
        continue
    tid = int(m.group(1))
    si = d / "summary_info.json"
    log = d / "experiment.log"
    r = {"task_id": tid, "dir": name, "archived": archived,
         "sites": meta[tid]["sites"], "fuzzy": meta[tid]["fuzzy"],
         "intent": meta[tid]["intent"], "eval_types": meta[tid]["eval_types"]}
    s = None
    if si.exists() and si.stat().st_size > 0:
        try:
            s = json.load(open(si))
        except Exception:
            s = None
    if s:
        r["status"] = "error" if s.get("err_msg") else (
            "done" if (s.get("terminated") or s.get("truncated")) else "incomplete")
        r["reward"] = s.get("cum_reward") or 0
        r["n_steps"] = s.get("n_steps")
        r["terminated"] = bool(s.get("terminated"))
        r["truncated"] = bool(s.get("truncated"))
        r["err_msg"] = (s.get("err_msg") or "")[:400]
        for k in ("cum_agent_elapsed", "cum_step_elapsed", "cum_input_tokens",
                  "cum_output_tokens", "max_output_tokens", "cum_n_retry_llm",
                  "cum_busted_retry"):
            r[k] = s.get("stats." + k)
    else:
        r["status"] = "incomplete"
        r["reward"] = None
    if log.exists():
        p = parse_log(log)
        r["t0"], r["t_last"], r["t_saved"] = p["t0"], p["t_last"], p["t_saved"]
        r["steps"] = p["steps"]
        r["actions"] = p["actions"]
        r["errs"] = dict(p["errs"])
        r["n_log_steps"] = p["n_log_steps"]
        r["log_age"] = now - log.stat().st_mtime
        # An episode with a log but no summary is either live or wedged. A single
        # step can legitimately take 400 s (8192-token generations with a retry),
        # so the "quiet" threshold has to sit well above that, not at 5 minutes.
        if s is None and not archived:
            r["status"] = "running" if r["log_age"] < 900 else "stalled"
    else:
        r["steps"], r["actions"], r["errs"] = [], [], {}
        r["n_log_steps"] = 0
        r["log_age"] = None
        # No experiment.log at all means prepare() ran but the task never started:
        # it is queued behind its dependency chain.
        if s is None and not archived:
            r["status"] = "queued"
    r["n_screens"] = len(list(d.glob("screenshot_step_*.png")))
    rows.append(r)

json.dump({"generated": now, "study": str(STUDY), "rows": rows},
          open(OUT, "w"))
print(f"{len(rows)} rows -> {OUT}  ({OUT.stat().st_size/1e6:.1f} MB)")
vis = [r for r in rows if not r["archived"]]
print("visible:", len(vis), Counter(r["status"] for r in vis))
