# autoresearch — Email Edition

A fork of [karpathy/autoresearch](https://github.com/karpathy/autoresearch) adapted for autonomous
email experiment idea generation using Shopify's Mozart email data.

Instead of iterating on ML training code to minimize `val_bpb`, an AI agent iterates on
`experiment.py` — modifying hypotheses and BigQuery queries against Mozart data — to maximize
`opportunity_score`: a composite signal of segment reach, performance gap vs. baseline, and
statistical confidence.

## How it works

| Original autoresearch | Email autoresearch |
|---|---|
| `train.py` — agent modifies | `experiment.py` — agent modifies |
| `prepare.py` — fixed data + eval | `prepare.py` — fixed Mozart utils + scoring |
| `val_bpb` — minimize | `opportunity_score` — maximize |
| 5-min GPU training run | BigQuery query (~seconds) |
| Overnight → 100 model variants | Overnight → 100 experiment hypotheses |
| `program.md` — research strategy | `program.md` — email research strategy |

## Quick start

**Requirements:** Python 3.10+, `uv`, GCP credentials with BigQuery access to `shopify-dw`.

```bash
# 1. Install uv (if needed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Install dependencies
uv sync

# 3. Authenticate with GCP
gcloud auth application-default login

# 4. Fetch and cache baseline Mozart metrics (one-time, ~30 seconds)
uv run prepare.py

# 5. Run the baseline experiment to confirm everything works
uv run experiment.py
```

## Running the agent

Open this repo in Cursor, then prompt:

```
Have a look at program.md and let's kick off a new research session.
```

The agent will:
1. Create a dated branch (e.g. `autoresearch/mar26`)
2. Read `prepare.py` and `experiment.py` for context
3. Verify baseline data exists
4. Initialize `results.tsv`
5. Start the autonomous loop — iterating on `experiment.py`, running queries, logging results

## Project structure

```
prepare.py      — constants, BigQuery utilities, baseline fetch, scoring (do not modify)
experiment.py   — current hypothesis + queries (agent modifies this)
program.md      — agent instructions and research strategy
pyproject.toml  — dependencies
results.tsv     — experiment log (untracked by git, written by agent)
```

## The scoring formula

`opportunity_score` (0–10, higher is better):

```
reach_score    = log10(unique_shops) * 2        # scale: 500 shops → ~2.7, 100k → 10
signal_score   = relative_lift_vs_baseline * 50  # scale: 20% relative lift → 10
confidence     = log10(total_sends) / 4          # scale: 1k sends → 0.75, 10k → 1.0

opportunity_score = (reach * 0.3 + signal * 0.5) * confidence
```

## License

MIT — fork of [karpathy/autoresearch](https://github.com/karpathy/autoresearch)
