# Does giving a GUI-grounding agent tools help?

Per-example results for a controlled tools-vs-no-tools experiment on
**ScreenSpot-Pro** (all 1581 examples), base model **Qwen3-VL-8B-Instruct**.

**→ [Browse the report](https://estherhan1.github.io/cua-grounding-reports/)**

**→ [Browse the complete OSWorld, OSWorld-G, and ScreenSpot-Pro experiment archive](https://estherhan1.github.io/cua-grounding-reports/all-experiments/)**

## Result

Handing the agent a 10-tool kit (including the specialist grounder GTA1-7B, an
instruction-rewriting stage, screenshot cropping/zooming, OCR, search) costs
**76 net rows** — 133 examples fixed, 209 broken; McNemar with continuity
correction, **p = 5.0e-05**.

| configuration | strict accuracy |
| --- | --- |
| dataset's own baseline prompt | 54.71% |
| **no tools**, new prompt core | **54.40%** |
| **tools**, same prompt core | **49.59%** |
| GTA1-7B alone, raw instruction | 49.72% |

The two bolded rows are the controlled pair: identical prompt core, tools on
vs off.

Decomposing the loss:

- **−74 of the −76 is the handoff itself.** The agent delegates grounding to
  GTA1-7B, which is simply a weaker grounder than the base model it replaces
  (49.72% alone, vs 54.40% for the base model).
- **Everything the tool loop adds on top is worth net −2 rows, p = 0.95** —
  multi-call reasoning, the instruction-rewriting stage, an 8152-character tool
  policy. 98% of GTA1 calls are issued *before* the agent has looked at the
  screenshot, so the rewrites it produces are guesswork.

Of the 209 regressions, 182 (87.1%) are the agent faithfully relaying a wrong
answer from the grounder. Only 18 are a harness defect (the agent zooms into a
crop, re-grounds inside it, then reports the crop's coordinates instead of the
full image's) and 4 are the agent ignoring the grounder and answering itself.
All 133 fixes are faithful transcriptions too.

## Reading the pages

One page per benchmark category. Each card is one example and shows:

- the screenshot, with the **ground-truth box in green** (small targets also get
  a locator ring), the **tool arm's click in red**, the **no-tools arm's in blue**
- all six runs' raw predictions, marked hit/miss
- a diagnosis of what the tool agent actually did on that example
- the tool arm's full trajectory: every tool call, every tool result, and the
  system prompt

The badge is the **tool** arm's outcome, so the All/Correct/Wrong filter reads
as "did tools get this right". Search `broken_by_tools`, `fixed_by_tools`,
`crop-frame`, or an application name to filter.

## Caveats

- **Scoring** uses the dataset's own strict parser, `x=([\d.]+), y=([\d.]+)`.
  It returns a guaranteed-miss `[0, 0]` on any syntax it doesn't match, so a
  legible near-miss scores as a miss. Under a lenient parser the two arms move
  by +0.06pp and +0.00pp respectively — this comparison is not a format artifact.
  (An earlier prompt revision *was*: it lost 3.5pp purely to output syntax,
  which is why the parser is stated here.)
- `ARM_A v2 old core+tools` was killed at 1385/1581 examples. Its accuracy is
  computed over the examples it actually ran and labelled as partial; it is not
  part of any headline claim.
- The crop-frame bug is known and deliberately unfixed in this run, and is
  reported as its own line rather than folded into the headline.

Pages are single self-contained HTML files with screenshots embedded as JPEG
data URIs (re-encoded to 1000px / q55 to fit under GitHub's 100 MB blob limit;
a higher-quality single-file build exists locally).


---

## Also here: WebArena-812 (a different benchmark)

`webarena-a3.html` + [`REPORT.md`](REPORT.md) are a separate line of work, kept in
this repo because they share the harness. **A3-Qwen3.5-9B** run on all 812 WebArena
tasks against a self-hosted site stack: **45.44% (369/812), ±3.42pp**, against the
leaderboard's **42.1** for the same model on the same split. Inside the interval, so
**reproduced, not beaten**.

Nothing on that page is comparable to the ScreenSpot-Pro numbers above — it measures
task completion, not pointing accuracy.

Three splits the aggregate hides:

- **Cross-site 20.8% (10/48) vs single-site 47.4%.** gitlab+reddit is 1/18. Composing
  across two apps is the failure mode, not any individual site.
- **The 36 unachievable (`N/A`) tasks score 86.1%; the 776 achievable ones score
  43.6%.** Abstaining and doing are different skills, and those 36 add 3.8pp to the
  headline.
- **167 episodes (20.6%) hit the 30-step cap and none of them succeeded** — the cap
  truncates already-lost episodes, so raising `max_steps` would buy nothing.

The 118 `fuzzy_match` tasks are graded by a **local Qwen3-VL-8B, not the GPT-4 that
upstream hardcodes**; quote the programmatic-only **44.7%** if you need a
judge-independent number. Protocol deviations that must be quoted with the result —
no inter-task resets, a 29 h gap mid-run, an episode timeout raised twice while
running — are in [`REPORT.md`](REPORT.md).

Host addresses in the page are redacted (`scripts/sanitize.py`); the embedded
screenshots are page viewports with no browser chrome.
