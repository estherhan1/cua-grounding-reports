#!/usr/bin/env /local3/yuhan/envs/a3/bin/python
"""Finish the 490 WebArena tasks that never ran in the 2026-08-17_17-01-11 study,
without disturbing the 322 that did.

Why this exists instead of `cli/eval.py --relaunch`:

  1. `eval.py:324-327` only overrides `avg_step_timeout` for workarena/assistantbench,
     so WebArena is stuck at the 60 that produced the 1800s episode cap. That cap is
     what killed run #1: three tasks (webarena.106/131/251) crossed it and, because
     agentlab encodes WebArena's ordering constraints as Ray ObjectRef *arguments*
     (graph_execution_ray.py:23-27), every task downstream of them was failed with
     "At least one of the input arguments for this task could not be computed" --
     298 + 147 + 68 = 490 experiments, 488 of which never executed a single step.

  2. Study.run() calls get_results() once per trial (study.py:335), three lines
     BEFORE find_incomplete() at study.py:338. That call is what actually crashed
     run #1 (NaN err_msg -> inspect_results.py map_err_key). It is pure bookkeeping.
     The installed agentlab is patched now, but the retry loop should not depend on
     a hand-patched site-package to survive, so this loop skips it entirely and
     aggregates once at the end.

Everything else is Study.run() verbatim, including the dependency graph: it is NOT
disabled. find_incomplete() keeps all 812 nodes and turns the finished ones into
no-op dummies (launch_exp.py:169-200), which is precisely the mechanism that lets
the 490 resume in correct per-site order.

Usage:
    cd /local3/yuhan/projects/agent-as-annotators
    source scripts/env.sh
    /local3/yuhan/envs/a3/bin/python scripts/resume_a3_full.py         # plan only
    /local3/yuhan/envs/a3/bin/python scripts/resume_a3_full.py --go    # launch
"""

import logging
import os
import sys
import tempfile
import urllib.request
from pathlib import Path

PROJECT = Path("/local3/yuhan/projects/agent-as-annotators")
STUDY_DIR = (PROJECT / "results" /
             "2026-08-17_17-01-11_genericagent-mcgill-nlp-a3-qwen3-5-9b-on-webarena-full")
MODEL_SHORTHAND = "A3-qwen3.5-9b"
N_JOBS = 8
N_TRIALS = 4

# Episode cap = 30 * this. History:
#   60  (1800s) -- killed webarena.106/131/251 in run 1 and cost 490 tasks.
#   120 (3600s) -- killed webarena.251 again 62 minutes in, on step 24 of 30.
#
# The 3600s failure is NOT the .106 hang class. .251 was stepping normally when it
# died; its median agent time is 43s, but 5 of its 24 steps took 404/430/488/772/870s.
# Those are runaway generations against the qwen3 group's max_new_tokens of 8192,
# amplified by modeling.py's up-to-4 retry loop when no <action> is emitted -- one
# episode in 33 puts a generation at the 8192 ceiling. So the tail is decode length,
# not a wedged renderer, and it is bounded: 30 steps at that distribution lands near
# 4600-7000s.
#
# 300 -> 9000s covers it with ~1.3-2x margin. The alternative -- cutting
# max_new_tokens -- is rejected on purpose: the 322 episodes already scored used
# 8192, and truncating generations would change what the agent produces, making the
# two halves of the run incomparable. Raising a cap changes nothing an agent does.
# Price of the larger cap: a genuine hang now holds a worker for 1.2*9000+60 = 3.0h
# instead of 1.2h. Observed hang rate is ~1 per 324 episodes, so ~1.5 hangs over the
# remaining work, i.e. ~4.5h -- against 69 tasks lost every trial if .251 keeps dying.
AVG_STEP_TIMEOUT = 300

REQUIRED = [
    "SHOPPING", "SHOPPING_ADMIN", "REDDIT", "GITLAB", "MAP", "WIKIPEDIA", "HOMEPAGE",
    "WA_SHOPPING", "WA_SHOPPING_ADMIN", "WA_REDDIT", "WA_GITLAB", "WA_MAP",
    "WA_WIKIPEDIA", "WA_HOMEPAGE", "AGENTLAB_EXP_ROOT", "OPENAI_API_KEY",
    "OPENAI_BASE_URL", "VLLM_API_KEY", "WA_JUDGE_MODEL",
    "PLAYWRIGHT_BROWSERS_PATH", "HF_HOME", "NLTK_DATA",
]
missing = [v for v in REQUIRED if not os.environ.get(v)]
if missing:
    sys.exit(f"env not sourced (missing {missing}). Run: source {PROJECT}/scripts/env.sh")
# A mid-study reset would invalidate the preconditions the 322 completed episodes
# were scored under, which is strictly worse than the drift it would fix.
if os.environ.get("WA_FULL_RESET"):
    sys.exit("WA_FULL_RESET is set -- unset it before resuming.")

sys.path.insert(0, str(PROJECT))

# Same two local monkey-patches as cli/eval.py:8-9, same order. They chain by
# wrapping exp_utils.run_exp and re-wrapping graph_execution_ray.run_exp with
# ray.remote(), which is how they reach the ray workers at all.
import agent_as_annotators.browser_stealth  # noqa: F401,E402
import agent_as_annotators.obs_timeout      # noqa: F401,E402

import ray  # noqa: E402

_original_ray_init = ray.init


def _isolated_ray_init(*args, **kwargs):
    """cli/eval.py:13-21 -- keep ray's temp dir off the shared default."""
    if "_temp_dir" not in kwargs:
        root = "/tmp/ray_scratch" if os.path.isdir("/tmp/ray_scratch") else tempfile.gettempdir()
        kwargs["_temp_dir"] = tempfile.mkdtemp(prefix="ray_wa_", dir=root)
    return _original_ray_init(*args, **kwargs)


ray.init = _isolated_ray_init

import agent_as_annotators.modeling as lam   # noqa: E402  (every exp_args.pkl needs it)
import agent_as_annotators.utils as aau      # noqa: E402
from agentlab.analyze import inspect_results  # noqa: E402
from agentlab.experiments.study import Study  # noqa: E402

logging.getLogger().setLevel(logging.INFO)

for port, what in ((21561, "agent A3-Qwen3.5-9B"), (8300, "judge Qwen3-VL")):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/v1/models", timeout=10) as r:
            assert r.status == 200
    except Exception as e:
        sys.exit(f"endpoint :{port} ({what}) unreachable: {e}")

# Absolute path matters: Study.load does `study.dir = dir` verbatim (study.py:430),
# so a relative path here would resolve against whatever cwd ray workers inherit.
study = Study.load(STUDY_DIR)
study.dir = STUDY_DIR
assert Path(study.dir).resolve() == STUDY_DIR.resolve(), study.dir
study.avg_step_timeout = AVG_STEP_TIMEOUT

# Rebuild the agent only to diff it against the pickled one. We do NOT install it:
# each experiment carries its own agent_args in its exp_args.pkl, and swapping the
# agent halfway would make the two halves of the run incomparable.
cfg = aau.load_all_model_configs(PROJECT / "configs" / "model_configs.json")[MODEL_SHORTHAND]
base_url = os.getenv("VLLM_BASE_URL") or f"http://localhost:{cfg['port']}/v1"
fresh = lam.prepare_vllm_model(**cfg["kwargs"], base_url=base_url)
pickled = study.agent_args[0]
if pickled.agent_name != fresh.agent_name:
    sys.exit(f"agent name drift: pickled={pickled.agent_name} fresh={fresh.agent_name}")
for field in ("model_name", "max_total_tokens", "max_input_tokens", "max_new_tokens",
              "temperature", "vision_support", "base_url"):
    old_v = getattr(pickled.chat_model_args, field, None)
    new_v = getattr(fresh.chat_model_args, field, None)
    if old_v != new_v:
        print(f"WARNING  agent config drift on {field}: pickled={old_v!r} fresh={new_v!r}")

n_exp = len(study.exp_args_list)
n_incomplete, n_error = study.find_incomplete(include_errors=True)
todo = [e.env_args.task_name for e in study.exp_args_list if not e.is_dummy]
print(f"study dir        : {study.dir}")
print(f"total exps       : {n_exp}")
print(f"to relaunch      : {n_incomplete}  ({n_error} of them previously errored)")
print(f"kept as-is       : {n_exp - n_incomplete}")
print(f"avg_step_timeout : {study.avg_step_timeout}  -> episode cap "
      f"{30 * study.avg_step_timeout}s (was 1800s)")
print(f"first 10 to run  : {todo[:10]}")
# If find_incomplete ever failed to hide the finished ones, running would mint a
# second set of dirs and duplicate every row in result_df. Refuse instead.
if n_incomplete > 520:
    sys.exit(f"refusing: {n_incomplete} non-dummy experiments, expected ~493.")

if "--go" not in sys.argv:
    print("\nplan only. re-run with --go to launch.")
    raise SystemExit(0)

# Study.run's trial loop (study.py:330-352) minus save() and get_results().
#
# The stopping rule is deliberately NOT agentlab's. Theirs compares n_error across
# trials, but a poisoned task has no summary_info.json and therefore counts as
# "incomplete", not "error" -- n_error stays ~flat while hundreds of tasks are still
# missing, so that rule can stop early with the job undone. (It is dead code upstream
# anyway: last_error_count is assigned at study.py:328 and never reassigned.)
# Progress on n_incomplete is the criterion that actually tracks the work.
last_incomplete = None
for i in range(N_TRIALS):
    print(f"=== trial {i + 1}/{N_TRIALS}: launching {n_incomplete} experiments ===", flush=True)
    study._run(n_jobs=N_JOBS, parallel_backend="ray", strict_reproducibility=False)

    n_incomplete, n_error = study.find_incomplete(include_errors=True)
    print(f"=== after trial {i + 1}: {n_incomplete} incomplete, {n_error} errored ===", flush=True)

    if n_incomplete == 0:
        print("study finished")
        break
    if n_error / n_exp > 0.3:
        print("more than 30% of the experiments errored, stopping the retries")
        break
    if last_incomplete is not None and n_incomplete >= last_incomplete:
        print(f"trial made no progress ({last_incomplete} -> {n_incomplete}), stopping")
        break
    last_incomplete = n_incomplete

result_df = inspect_results.load_result_df(study.dir, progress_fn=None)
result_df["err_msg"] = result_df["err_msg"].astype(object).where(
    result_df["err_msg"].notna(), None)
result_df.to_csv(study.dir / "result_df_resumed.csv")
summary_df = inspect_results.summarize_study(result_df)
summary_df.to_csv(study.dir / "summary_df_resumed.csv")
(study.dir / "error_report_resumed.md").write_text(
    inspect_results.error_report(result_df, max_stack_trace=3, use_log=True))
print(summary_df.to_string())
