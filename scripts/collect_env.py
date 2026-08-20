"""Environment-side snapshot: sites, model endpoints, GPUs, driver liveness.

The canary is imported rather than shelled out to, so we get its structured
per-probe result (ok / fingerprint / detail) and its AFFECTED map -- the number
of the 812 tasks each probe gates. That mapping is the whole point: a red
homepage probe is cosmetic (0 tasks) while a red map:tile probe silently
zeroes 128.
"""
import json, os, re, subprocess, sys, time, urllib.request
from pathlib import Path

sys.path.insert(0, "/local3/yuhan/projects/webarena")
OUT = Path("/local3/yuhan/tmp/a3dash/env.json")
env = {"generated": time.time()}

import site_canary as sc
env["sites"] = {"probes": sc.run_once(), "affected": sc.AFFECTED,
                "frontend": sc.FRONTEND, "map_backend": sc.MAP_BACKEND}
try:
    env["sites"]["baseline"] = json.load(open("/local3/yuhan/projects/webarena/site_baseline.json"))
except Exception:
    env["sites"]["baseline"] = None

def probe_llm(port, label):
    d = {"port": port, "label": label, "ok": False}
    t = time.time()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/v1/models", timeout=10) as r:
            body = json.load(r)
        d["served_as"] = [m["id"] for m in body["data"]]
        # /v1/models answering is not evidence the model can decode -- a wedged
        # engine still serves it. Force one real completion.
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/v1/chat/completions",
            data=json.dumps({"model": d["served_as"][0],
                             "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
                             "max_tokens": 2048}).encode(),
            headers={"Content-Type": "application/json", "Authorization": "Bearer dummy"})
        with urllib.request.urlopen(req, timeout=90) as r:
            out = json.load(r)
        msg = out["choices"][0]["message"]
        d["reply"] = (msg.get("content") or msg.get("reasoning_content") or "")[:40]
        d["ok"] = bool(d["reply"])
        d["latency_s"] = round(time.time() - t, 2)
    except Exception as e:
        d["error"] = f"{type(e).__name__}: {e}"[:200]
    return d

env["llm"] = [probe_llm(21561, "agent - A3-Qwen3.5-9B"), probe_llm(8300, "judge - Qwen3-VL-8B")]

def sh(cmd, timeout=25):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True,
                              timeout=timeout).stdout.strip()
    except Exception as e:
        return f"ERR {e}"

_NVSMI = ("nvidia-smi --query-gpu=index,name,memory.used,memory.total,"
          "utilization.gpu --format=csv,noheader,nounits")
# The second box is named by $PEER_HOST rather than hardcoded: this file is
# published, and the hostname is not.
_peer = os.environ.get("PEER_HOST", "")
env["gpu_peer"] = (sh(f"ssh -o ConnectTimeout=10 -o BatchMode=yes {_peer} '{_NVSMI}'")
                   if _peer else "")
env["gpu_local"] = sh(_NVSMI)
env["tunnels"] = sh("ps -eo pid,etime,cmd | grep -E '[s]sh -N .*-L (21561|8300)'")
env["driver_alive"] = bool(sh("ps -eo cmd | grep -c '[r]esume_a3_full.py'").strip() not in ("", "0"))
env["ray_workers"] = sh("ps -eo pid,cmd | grep -cE '[r]ay::GenericAgent'")
env["chromium"] = sh("ps -eo pid | wc -l") and sh("pgrep -fc 'headless_shell|[c]hrome --type=renderer' || echo 0")

log = Path("/local3/yuhan/tmp/a3_resume.log")
if log.exists():
    txt = log.read_text(errors="replace")
    env["trials"] = re.findall(r"=== (trial \d+/\d+: launching \d+ experiments|after trial .*?) ===", txt)
    env["timeout_kills"] = re.findall(r"(hase been running for [\d.]+s.*)", txt)
    env["log_tail"] = "\n".join(l for l in txt.split("\n")[-400:]
                                if not l.startswith("\x1b[36m("))[-3000:]
    env["log_mtime"] = log.stat().st_mtime
    m = re.search(r"avg_step_timeout : (\d+)", txt)
    env["avg_step_timeout"] = int(m.group(1)) if m else None

json.dump(env, open(OUT, "w"), indent=1)
print("env ->", OUT, f"{OUT.stat().st_size/1e3:.1f} kB")
print("probes:", {k: v["ok"] for k, v in env["sites"]["probes"].items()})
print("llm:", [(d["label"], d["ok"], d.get("latency_s")) for d in env["llm"]])
print("driver_alive:", env["driver_alive"], "ray workers:", env["ray_workers"])
