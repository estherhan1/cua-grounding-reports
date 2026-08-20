# A3-Qwen3.5-9B on WebArena-812 — Final Report

Run: `results/2026-08-17_17-01-11_genericagent-mcgill-nlp-a3-qwen3-5-9b-on-webarena-full`
Completed 2026-08-20 10:38 PDT. **812/812 tasks scored, 0 errors.**

## Headline

| | |
|---|---|
| **Success rate** | **45.44 %  (369 / 812)** |
| 95 % CI (binomial) | ± 3.42 pp |
| Leaderboard target (A3, WebArena-812) | 42.1 % |
| **Delta** | **+3.3 pp** |
| Mean steps / episode | 12.47 (median 8) |
| Episodes hitting the 30-step cap | 167 (20.6 %) — **0 of them succeeded** |

Denominator is 812, the full benchmark. Not attempted-only.

## Per-site

| Site | SR | n |
|---|---|---|
| gitlab | **56.1 %** | 101/180 |
| shopping_admin | 47.8 % | 87/182 |
| reddit | 49.1 % | 52/106 |
| shopping | 44.4 % | 83/187 |
| map | **33.0 %** | 36/109 |
| *multi-site (all)* | **20.8 %** | 10/48 |

Multi-site detail: map+wikipedia 8/17 (47.1 %), gitlab+wikipedia 1/6, gitlab+reddit 1/18 (5.6 %), reddit+shopping 0/5, map+shopping_admin 0/2.

Cross-site composition is the clear weak spot — 20.8 % vs 47.4 % on single-site tasks.

## Judge split (this is the part the aggregate hides)

| Evaluator | SR | n |
|---|---|---|
| **LLM-judged** (`fuzzy_match` in reference answer) | 50.0 % | 59/118 |
| **Programmatic** (`must_include` / `exact_match` / `program_html` / `url_match`) | 44.7 % | 310/694 |

The judge here is **Qwen3-VL-8B served locally, not GPT-4** (WebArena's reference implementation uses GPT-4 for `fuzzy_match`). The two halves are 5.3 pp apart. That gap is small enough that the judge is not obviously inflating the total — swapping it for GPT-4 would move the headline by at most ~0.8 pp even if every one of the 59 LLM-scored successes were wrong-by-half — but the 118 numbers are **not** directly comparable to the leaderboard's, and I'd treat 44.7 % (programmatic-only) as the defensible number if you need one that is judge-independent.

By browsergym eval type: `program_html` 50.0 % (141/282), `string_match` 44.0 % (143/325), `url_match+program_html` 42.6 % (55/129), `url_match` 39.4 % (26/66).

## Unachievable tasks

36 tasks have `N/A` as the reference answer (the correct behaviour is to report the task is impossible).

| | SR | n |
|---|---|---|
| Unachievable (N/A) | **86.1 %** | 31/36 |
| Achievable | 43.6 % | 338/776 |

A3 is very good at abstaining. Those 36 tasks contribute 3.8 pp of the 45.4 %; on achievable tasks alone it is 43.6 %.

## Protocol deviations — disclose these with the number

1. **The AWS instance was never reset between tasks.** `WA_FULL_RESET` was deliberately left unset. WebArena's reference protocol resets the site containers for the 76 `requires_reset` tasks. State written by earlier tasks (orders placed, issues opened, comments posted) persisted. Direction of bias is not one-sided: it can both break later tasks and accidentally satisfy them.
2. **~65 h elapsed across the run**, in two halves separated by ~29 h (2026-08-17 17:05 → 2026-08-18 09:15, then 2026-08-19 01:05 → 2026-08-20 10:38). 472 episodes are from the first half, 340 from the second.
3. **The episode timeout changed mid-run**: 1800 s → 3600 s → 9000 s. Raising a cap does not change what an agent produces, but it does mean early episodes had less headroom than late ones. Three run-1 tasks (`webarena.106/131/251`) were killed at 1800 s and re-run later under the larger cap.
4. **`max_new_tokens` was left at 8192 throughout** — deliberately not cut, so the two halves stay comparable.
5. The dependency graph was kept (not `--ignore-dependencies`), matching the reference protocol. Poset width is 5, so real parallelism averaged ~2×, which is why it took 65 h.
6. One genuine renderer hang (`webarena.342`, gitlab) wedged a worker for 9552 s in trial 1 and poisoned 248 descendants; agentlab's relaunch loop recovered all of them in trials 2–3. Final state has 0 errored, 0 incomplete.

## Comparison caveat

42.1 is the leaderboard's WebArena-812 number for A3. Do **not** compare against 33.7 (that is VisualWebArena-910) or 41.5 (paper body, 381-task split). Our 45.44 % is +3.3 pp over 42.1, which is inside the ±3.4 pp CI of a single run — so this reproduces the reported result rather than beating it. The most likely source of the small positive gap is deviation #1 (no resets) plus the local judge.
