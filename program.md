# autoresearch — Email Edition

This is an autonomous experiment idea generator for Shopify's merchant lifecycle email program.
The agent iterates on `experiment.py`, running BigQuery queries against Mozart data to surface
high-opportunity experiment ideas.

## Setup

To start a new research session, work with the user to:

1. **Agree on a run tag**: propose a tag based on today's date (e.g. `mar26`). The branch
   `autoresearch/<tag>` must not already exist — this is a fresh run.
2. **Create the branch**: `git checkout -b autoresearch/<tag>` from current master.
3. **Read the in-scope files** for full context:
   - `README.md` — repository context.
   - `prepare.py` — fixed constants, BigQuery utilities, baseline fetching, opportunity scoring. **Do not modify.**
   - `experiment.py` — the file you modify each iteration. Defines the experiment hypothesis and BigQuery queries.
4. **Verify baseline data exists**: Run `uv run prepare.py`. This will fetch and cache baseline
   Mozart metrics from BigQuery to `~/.cache/autoresearch-email/baseline.json`. You need valid
   GCP credentials (`gcloud auth application-default login`). Print what was fetched.
5. **Fetch LCM experiment history** using the Experiments MCP:
   - Search for all experiments owned by team 1686 ("Lifecycle Marketing and Marketing Automation"):
     `search(filters: { team: "1686" }, pagination: { limit: 50 })`
   - Fetch page 2 if the first page returned exactly 50 results.
   - For any experiment in `running` or `cooling_down` state, call `experiment_details` to get
     the full hypothesis and metric so you understand what is actively being tested.
   - **Record this list.** Do not generate ideas that replicate something already in-flight or
     recently concluded. If an idea is similar to a past experiment, your hypothesis should build
     on its result (e.g. "Given that X was inconclusive, test a stronger version targeting sub-segment Y").
6. **Scan cross-team experiments** that may inform email / push / homecards:
   - Search for experiments touching email channels from other teams:
     `search(query: "email", filters: { team: "1686" }, pagination: { limit: 50 })` — note what
     LCM has done.
   - Then search broadly: `search(query: "email notification")`, `search(query: "push notification")`,
     `search(query: "homecard")`, `search(query: "onboarding email")` — without team filter.
   - Look for experiments from Growth, Product, Retention, or other teams where the treatment
     was a notification or email nudge. These are candidates for **translation** into Mozart journeys.
7. **Initialize results.tsv**: Create `results.tsv` with just the header row. The baseline will
   be recorded after the first run.
8. **Confirm and go**: Summarize what you found from steps 5–6 (LCM history + cross-team signals),
   then confirm setup looks good before starting the loop.

Once you get confirmation, kick off the experimentation.

## Experimentation

Each experiment evaluates a specific email hypothesis against live Mozart data in BigQuery.
The script queries the data, computes an **opportunity score**, and prints results.

**What you CAN do:**
- Modify `experiment.py` — this is the only file you edit. Change the hypothesis, the
  audience segment, the BigQuery queries, which metric you're optimizing for. Everything is fair game.

**What you CANNOT do:**
- Modify `prepare.py`. It is read-only. It contains the fixed scoring logic, BigQuery utilities,
  baseline data, and constants.
- Modify `results.tsv` directly — it is written by the experiment loop.

**The goal is simple: find the highest opportunity_score.** Higher = better. A score of 10 means:
large addressable segment + meaningful performance gap vs. baseline + statistically solid evidence.

**Simplicity criterion**: Prefer focused, specific hypotheses over vague ones. A precise, testable
experiment idea with a 6.0 score beats a hand-wavy idea that scores 5.9. The best output is a crisp,
implementable experiment that Mozart engineers could actually build.

**The first run**: Your very first run should always use the baseline `experiment.py` as-is to
establish the baseline metrics and confirm BigQuery is working.

## The metric

`opportunity_score` is a 0–10 composite score computed by `prepare.py`:

- **Reach** (30% weight): log-scaled count of unique shops in the segment. More shops = higher reach.
- **Signal** (50% weight): absolute performance gap vs. baseline, in the direction that matters.
  For open/click rate: segment > baseline = positive. For unsub rate: segment < baseline = positive.
- **Confidence** (multiplier): based on send volume. Small samples discount the score.

The first run establishes the baseline (which scores 0.0 by definition — there's no gap to measure
against itself). Every subsequent run should try to beat the best score so far.

## Output format

When `experiment.py` runs, it prints:

```
---
opportunity_score:   7.3
unique_shops:        45231
total_sends:         187432
open_rate_pct:       31.2    (baseline: 24.8)
lift_pct:            +6.4
confidence:          0.92
title:               Send timing — immediate vs 24h delay for Etsy migrants
```

Extract the key metric:

```bash
grep "^opportunity_score:" run.log
```

## Logging results

When an experiment is done, log it to `results.tsv` (tab-separated — commas break descriptions).

The TSV has a header row and 5 columns:

```
commit	opportunity_score	unique_shops	status	description
```

1. git commit hash (short, 7 chars)
2. opportunity_score achieved (e.g. 7.300) — use 0.000 for crashes
3. unique_shops in the segment (e.g. 45231) — use 0 for crashes
4. status: `keep`, `discard`, or `crash`
5. short description of the hypothesis tested

Example:

```
commit	opportunity_score	unique_shops	status	description
a1b2c3d	0.000	1823491	keep	baseline — all journey emails
b2c3d4e	7.300	45231	keep	Etsy migrants: open rate gap in first email within 1h vs 24h
c3d4e5f	2.100	8432	discard	Dropshippers: click rate vs non-dropshippers (small segment lift)
d4e5f6g	0.000	0	crash	syntax error in SQL join
```

## The experiment loop

Run on a dedicated branch (e.g. `autoresearch/mar26`).

LOOP FOREVER:

1. Look at the git state: current branch/commit we're on.
2. Read `results.tsv` to understand what has been tried and what the best score is so far.
3. Tune `experiment.py` with a new hypothesis — change the segment, the metric, the SQL queries.
4. `git commit`
5. Run: `uv run experiment.py > run.log 2>&1`
6. Read results: `grep "^opportunity_score:\|^unique_shops:" run.log`
7. If grep output is empty, the run crashed. Run `tail -n 50 run.log` to read the error. Fix and retry if it's a simple bug (syntax, missing column). If fundamentally broken, log as crash and move on.
8. Record in `results.tsv`.
9. If `opportunity_score` **improved** (higher), you advance the branch (keep the commit).
10. If equal or worse, `git reset` back to where you started.

**NEVER STOP**: Once the experiment loop has begun, do NOT pause to ask the human if you should
continue. You are autonomous. If you run out of ideas, dig deeper — look at different journey
types, time windows, merchant cohorts, locale splits, signup sources, plan types, unsubscribe
patterns. The loop runs until the human interrupts you, period.

## Experiment space — what to explore

Think broadly. Here are directions to consider:

**Audience segmentation**
- Onboarding type: Etsy migrants, Dropshippers, POS/Retail, Cross-border, Replatformers, Digital Products
- Merchant lifecycle: 0–30 days, 31–90 days, at-risk (no sales in 30 days), churned
- Plan tier, country (US vs. CA vs. GB vs. AU), locale, signup source

**Journey-level patterns**
- Which journey emails have the worst open rates relative to segment baseline?
- Which journeys have high open but low click (content-engagement gap)?
- Which journeys have elevated unsubscribe rates?

**Timing signals**
- Time from trigger event to email send: immediate vs. delayed
- Day of week / time of day effects
- Time between emails in a sequence (cadence fatigue)

**Sequence position effects**
- Email #1 vs. #3 vs. #6 in a journey — where does engagement drop off?
- Are early-journey and late-journey emails equally effective?

**Cross-segment comparisons**
- Do Etsy migrants respond differently to onboarding emails than general new merchants?
- US vs. other English-speaking markets: open rate delta?

**Cross-team translation** (this is a key source of novel ideas)
- Review what you found from the cross-team experiment search in setup step 6.
- If a Growth or Product team ran an in-product experiment (e.g. a homecard, tooltip, or
  push notification) that improved activation or retention, ask: could the same intervention
  be delivered as an email or journey trigger? Find the equivalent merchant segment in Mozart
  and estimate the opportunity.
- Examples: a homecard experiment that improved first-sale conversion for dropshippers →
  translate to an email journey trigger for the same segment; a push experiment that improved
  re-engagement for at-risk merchants → translate to a Mozart re-engagement journey.

## Constraints

**Merchant-facing emails only.** All SEGMENT_QUERY SQL must include `AND e.recipient_type = 'shop'`.
This is already present in the baseline and imported as `MERCHANT_ONLY_FILTER` from `prepare.py`.
Never remove it. Mozart also sends to Shop Buyers (consumers) — those are out of scope entirely.
If you are unsure whether a campaign or journey targets merchants or buyers, add `AND e.recipient_type = 'shop'`.

**Do not replicate known experiments.** Before writing a new hypothesis, check your notes from
the Experiments MCP lookup in setup step 5. If an idea overlaps with a running or recently
concluded LCM experiment, skip it or build on its result rather than re-testing the same thing.

**Partition filter required.** All BigQuery queries must filter `created_at` (the partition column)
or the query will be rejected.

**English-speaking markets only** (unless explicitly testing locale effects):
`country_code IN ('US', 'GB', 'AU', 'CA', 'IE', 'NZ')`.

**Minimum segment size**: at least 500 unique shops. Very small segments will have low confidence
and score poorly regardless of signal strength.

**Specificity**: Hypotheses must be specific and testable. "Open rates are lower for Etsy migrants
in the second email of the onboarding journey" is valid. "Emails could be improved" is not.
