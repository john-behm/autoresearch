"""
Email Experiment Definition — the agent modifies this file each iteration.

Usage: uv run experiment.py

This file defines one hypothesis and the BigQuery queries that gather
evidence for it. Running this script queries Mozart data, computes an
opportunity_score, and prints results in the standard format.

Rules (from program.md):
- SEGMENT_QUERY must filter `created_at` (partition column).
- SEGMENT_QUERY must include `unique_shops` and `total_sends` columns.
- SEGMENT_QUERY must include the column named in PRIMARY_METRIC.
- DIRECTION must be 'higher' or 'lower'.
"""

from prepare import run_query, load_baseline, score_opportunity, print_results

# ---------------------------------------------------------------------------
# Experiment definition — agent modifies everything below this line
# ---------------------------------------------------------------------------

TITLE = "Baseline — overall journey email performance"

HYPOTHESIS = (
    "Establish baseline open rate, click rate, and unsubscribe rate "
    "across all active journey emails in English-speaking markets. "
    "This is the reference point for all subsequent experiments."
)

# BigQuery SQL to gather segment evidence.
# Must include: unique_shops, total_sends, and the PRIMARY_METRIC column.
# Must filter created_at for partition pruning.
SEGMENT_QUERY = """
SELECT
  COUNT(DISTINCT e.recipient_id)                                                  AS unique_shops,
  COUNT(*)                                                                        AS total_sends,
  ROUND(SAFE_DIVIDE(
    COUNTIF(e.opened_at IS NOT NULL),
    COUNTIF(e.delivered_at IS NOT NULL)) * 100, 2)                                AS open_rate_pct,
  ROUND(SAFE_DIVIDE(
    COUNTIF(e.number_of_clicks > 0),
    COUNTIF(e.delivered_at IS NOT NULL)) * 100, 2)                                AS click_rate_pct,
  ROUND(SAFE_DIVIDE(
    COUNTIF(e.first_unsubscribe_event_at IS NOT NULL),
    COUNTIF(e.delivered_at IS NOT NULL)) * 100, 2)                                AS unsub_rate_pct
FROM `shopify-dw.marketing.mozart_emails` e
WHERE e.created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
  AND e.campaign_type = 'Journey'
  AND e.recipient_type = 'shop'
"""

# Which column in SEGMENT_QUERY is the primary metric to optimize?
PRIMARY_METRIC = "open_rate_pct"

# What direction is "better" for this metric?
DIRECTION = "higher"  # 'higher' or 'lower'

# ---------------------------------------------------------------------------
# Run (do not modify below)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"[experiment] Running: {TITLE}")
    print(f"[experiment] Hypothesis: {HYPOTHESIS[:100]}...")
    print()

    baseline = load_baseline()
    results = run_query(SEGMENT_QUERY)
    scored = score_opportunity(results, PRIMARY_METRIC, DIRECTION, baseline)
    print_results(scored, TITLE)
