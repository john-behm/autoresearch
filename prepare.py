"""
Fixed utilities for autoresearch-email. Do not modify.

Fetches baseline Mozart metrics from BigQuery and provides the opportunity
scoring function used by experiment.py.

Usage:
    uv run prepare.py        # fetch and cache baseline, print summary
    uv run prepare.py --force  # re-fetch even if cache exists
"""

import os
import sys
import json
import math
import argparse
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants (fixed — do not modify)
# ---------------------------------------------------------------------------

MOZART_TABLE = "shopify-dw.marketing.mozart_emails"
SHOP_PROFILE_TABLE = "shopify-dw.accounts_and_administration.shop_profile_current"
ENGLISH_MARKETS = "('US', 'GB', 'AU', 'CA', 'IE', 'NZ')"
BASELINE_WINDOW_DAYS = 30

# These filters must appear in every SEGMENT_QUERY in experiment.py.
# Import them so the constraints are enforced in code, not just docs.
#
# MERCHANT_ONLY_FILTER: excludes Shop Buyer (consumer) emails. All ideation is
# scoped to merchant (shop) recipients only. Never remove this filter.
MERCHANT_ONLY_FILTER = "e.recipient_type = 'shop'"
JOURNEY_TYPE_FILTER  = "e.campaign_type = 'Journey'"

CACHE_DIR = Path.home() / ".cache" / "autoresearch-email"
BASELINE_FILE = CACHE_DIR / "baseline.json"

BASELINE_QUERY = f"""
SELECT
  COUNT(DISTINCT e.recipient_id)                                                  AS unique_shops,
  COUNT(*)                                                                        AS total_sends,
  COUNTIF(e.delivered_at IS NOT NULL)                                             AS delivered,
  COUNTIF(e.opened_at IS NOT NULL)                                                AS opened,
  COUNTIF(e.number_of_clicks > 0)                                                 AS clicked,
  COUNTIF(e.first_unsubscribe_event_at IS NOT NULL)                               AS unsubscribed,
  ROUND(SAFE_DIVIDE(
    COUNTIF(e.opened_at IS NOT NULL),
    COUNTIF(e.delivered_at IS NOT NULL)) * 100, 2)                                AS open_rate_pct,
  ROUND(SAFE_DIVIDE(
    COUNTIF(e.number_of_clicks > 0),
    COUNTIF(e.delivered_at IS NOT NULL)) * 100, 2)                                AS click_rate_pct,
  ROUND(SAFE_DIVIDE(
    COUNTIF(e.first_unsubscribe_event_at IS NOT NULL),
    COUNTIF(e.delivered_at IS NOT NULL)) * 100, 2)                                AS unsub_rate_pct
FROM `{MOZART_TABLE}` e
WHERE e.created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {BASELINE_WINDOW_DAYS} DAY)
  AND e.campaign_type = 'Journey'
  AND e.recipient_type = 'shop'
"""

# ---------------------------------------------------------------------------
# BigQuery utilities
# ---------------------------------------------------------------------------

def get_bq_client():
    try:
        from google.cloud import bigquery
    except ImportError:
        print("ERROR: google-cloud-bigquery not installed. Run: uv sync", file=sys.stderr)
        sys.exit(1)

    # Shopify's data lives in shopify-dw, but BQ jobs must be billed to a project
    # where you have bigquery.jobs.create permission. Set BQ_PROJECT to override.
    # If unset, we set shopify-dw as the quota project, which works for most
    # Shopify employees with standard data warehouse access.
    project = os.environ.get("BQ_PROJECT", "shopify-dw")

    try:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            client = bigquery.Client(project=project)
        return client
    except Exception as e:
        print(f"ERROR: Could not create BigQuery client: {e}", file=sys.stderr)
        print("\nTo fix, try one of:", file=sys.stderr)
        print("  gcloud auth application-default login", file=sys.stderr)
        print("  gcloud auth application-default set-quota-project shopify-dw", file=sys.stderr)
        print("  BQ_PROJECT=<your-project> uv run prepare.py", file=sys.stderr)
        sys.exit(1)


def run_query(sql: str) -> list[dict]:
    """Run a BigQuery SQL query and return results as a list of dicts."""
    client = get_bq_client()
    try:
        job = client.query(sql)
        rows = list(job.result())
        return [dict(row) for row in rows]
    except Exception as e:
        raise RuntimeError(f"BigQuery error: {e}") from e


# ---------------------------------------------------------------------------
# Baseline fetch and cache
# ---------------------------------------------------------------------------

def fetch_baseline(force: bool = False) -> dict:
    """Fetch baseline metrics from BigQuery and cache locally."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if BASELINE_FILE.exists() and not force:
        with open(BASELINE_FILE) as f:
            baseline = json.load(f)
        age_days = (
            __import__("time").time() - os.path.getmtime(BASELINE_FILE)
        ) / 86400
        print(f"[prepare] Loaded cached baseline ({age_days:.1f} days old).")
        return baseline

    print(f"[prepare] Fetching baseline from BigQuery (last {BASELINE_WINDOW_DAYS} days)...")
    rows = run_query(BASELINE_QUERY)
    if not rows:
        print("ERROR: Baseline query returned no rows.", file=sys.stderr)
        sys.exit(1)

    baseline = {k: float(v) if isinstance(v, (int, float)) else v for k, v in rows[0].items()}
    with open(BASELINE_FILE, "w") as f:
        json.dump(baseline, f, indent=2)
    print(f"[prepare] Baseline cached to {BASELINE_FILE}")
    return baseline


def load_baseline() -> dict:
    """Load cached baseline, fetching if missing."""
    if not BASELINE_FILE.exists():
        print("[prepare] No cached baseline found — fetching now...")
        return fetch_baseline()
    with open(BASELINE_FILE) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Opportunity scoring (fixed — do not modify)
# ---------------------------------------------------------------------------

def score_opportunity(
    results: list[dict],
    primary_metric: str,
    direction: str,
    baseline: dict,
) -> dict:
    """
    Compute opportunity_score from experiment query results.

    Args:
        results: list of dicts from run_query()
        primary_metric: column name of the metric to optimize (e.g. 'open_rate_pct')
        direction: 'higher' or 'lower' (what is better for this metric)
        baseline: baseline dict from load_baseline()

    Returns:
        dict with opportunity_score and supporting fields
    """
    if not results:
        return {
            "opportunity_score": 0.0,
            "unique_shops": 0,
            "total_sends": 0,
            primary_metric: 0.0,
            f"{primary_metric}_baseline": baseline.get(primary_metric, 0.0),
            "lift_pct": 0.0,
            "confidence": 0.0,
            "error": "No results returned",
        }

    row = results[0]
    unique_shops = float(row.get("unique_shops", 0))
    total_sends = float(row.get("total_sends", 0))
    segment_value = float(row.get(primary_metric, 0.0))
    baseline_value = float(baseline.get(primary_metric, 0.0))

    # Reach score: log-scaled unique shops (500 shops → ~2.7, 100k shops → 10)
    reach_score = min(10.0, math.log10(max(1, unique_shops)) * 10.0 / 5.0)

    # Signal score: relative lift vs baseline in the right direction
    lift_pct = segment_value - baseline_value
    if direction == "lower":
        # lower is better (e.g. unsub rate): negative lift = good
        directed_lift = -lift_pct
    else:
        directed_lift = lift_pct

    if baseline_value > 0:
        relative_lift = directed_lift / baseline_value
    else:
        relative_lift = 0.0

    # Scale: 20% relative lift → signal_score = 10
    signal_score = min(10.0, max(0.0, relative_lift * 50.0))

    # Confidence multiplier: based on send volume (1k sends → 0.75, 10k → 1.0)
    confidence = min(1.0, math.log10(max(1, total_sends)) / 4.0)

    # Composite score
    raw = (reach_score * 0.3 + signal_score * 0.5) * confidence
    opportunity_score = round(min(10.0, max(0.0, raw)), 3)

    return {
        "opportunity_score": opportunity_score,
        "unique_shops": int(unique_shops),
        "total_sends": int(total_sends),
        primary_metric: segment_value,
        f"{primary_metric}_baseline": baseline_value,
        "lift_pct": round(lift_pct, 2),
        "confidence": round(confidence, 2),
    }


def print_results(scored: dict, title: str) -> None:
    """Print results in the standardized format that the agent reads."""
    print("---")
    print(f"opportunity_score:   {scored['opportunity_score']:.3f}")
    print(f"unique_shops:        {scored['unique_shops']:,}")
    print(f"total_sends:         {scored['total_sends']:,}")
    # Print all numeric fields
    for k, v in scored.items():
        if k not in ("opportunity_score", "unique_shops", "total_sends", "error"):
            if isinstance(v, float):
                print(f"{k:<20} {v:.2f}")
    if "error" in scored:
        print(f"error:               {scored['error']}")
    print(f"title:               {title}")


# ---------------------------------------------------------------------------
# Main: fetch and display baseline
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch and cache Mozart baseline metrics.")
    parser.add_argument("--force", action="store_true", help="Re-fetch even if cache exists.")
    args = parser.parse_args()

    baseline = fetch_baseline(force=args.force)

    print("\n=== Mozart Email Baseline ===")
    print(f"  Window:         last {BASELINE_WINDOW_DAYS} days")
    print(f"  Journey type:   Journey emails only")
    print(f"  Recipient type: shop")
    print()
    print(f"  Unique shops:   {int(baseline['unique_shops']):,}")
    print(f"  Total sends:    {int(baseline['total_sends']):,}")
    print(f"  Open rate:      {baseline['open_rate_pct']:.2f}%")
    print(f"  Click rate:     {baseline['click_rate_pct']:.2f}%")
    print(f"  Unsub rate:     {baseline['unsub_rate_pct']:.2f}%")
    print()
    print(f"Cached to: {BASELINE_FILE}")
    print("\nReady. Run `uv run experiment.py` to start the first experiment.")
