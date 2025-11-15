# meta_lite.py
"""
Meta-lite processor for Elastic ML results.

- Uses elasticsearch.helpers.scan to stream .ml-anomalies-* results safely.
- Processes documents in adaptive batches (by document count).
- Computes meta metrics per-batch and overall summary.
- Indexes per-batch results + overall summary into `meta_lite_result`.

Usage:
    python meta_lite.py            # run once (default)
    python meta_lite.py --loop     # run continuously every hour (requires `schedule` package)

Configuration: edit constants below or set env vars:
    ELASTIC_HOST, ELASTIC_USER, ELASTIC_PASS, CA_CERT
"""

import os
import time
import json
from datetime import datetime, timezone, timedelta
from elasticsearch import Elasticsearch, helpers
import numpy as np
import logging
import argparse

# --- CONFIG (change or set environment vars) ---
ELASTIC_HOST = os.environ.get("ELASTIC_HOST", "https://localhost:9200")
ELASTIC_USER = os.environ.get("ELASTIC_USER", "elastic")
ELASTIC_PASS = os.environ.get("ELASTIC_PASS", "3+xHEqNsZYJ*2CQoNAlG")
CA_CERT      = os.environ.get("CA_CERT", "http_ca.crt")   # set to None to skip verification
INDEX_INPUT  = os.environ.get("INDEX_INPUT", ".ml-anomalies-*")
INDEX_OUTPUT = os.environ.get("INDEX_OUTPUT", "meta_lite_result")

# ML job ids you want to include (optional) - set to None or [] to include all jobs
JOB_IDS = os.environ.get("JOB_IDS", "")   # comma separated, e.g. "prediksi_tds_jenuh,anomali_kekeruhan"
JOB_IDS = [j.strip() for j in JOB_IDS.split(",") if j.strip()] if JOB_IDS else None

# Adaptive batching: how many docs per batch processed
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "10000"))

# Safety cap: maximum docs to process in one run (set None to no cap)
MAX_DOCS  = int(os.environ.get("MAX_DOCS", "100000"))  # default 100k

# Time window to look back (in hours). Default 30 days = 720 hours
TIME_WINDOW_HOURS = int(os.environ.get("TIME_WINDOW_HOURS", str(24 * 30)))

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# --- Elasticsearch client ---
es_kwargs = {
    "hosts": [ELASTIC_HOST],
    "basic_auth": (ELASTIC_USER, ELASTIC_PASS),
}
if CA_CERT and CA_CERT.lower() != "none":
    es_kwargs["ca_certs"] = CA_CERT
else:
    # If CA_CERT is None/disabled, skip cert verification (not recommended for prod)
    es_kwargs["verify_certs"] = False

es = Elasticsearch(**es_kwargs)

# --- Utils: metric computation ---
def compute_batch_metrics(batch_docs):
    """
    batch_docs: list of dicts, each is an _source from ML index,
                containing at least 'actual' and 'model_forecast' optionally 'anomaly_score'
    returns dict of metrics
    """
    # Extract arrays safely
    actuals = np.array([d.get("actual") for d in batch_docs if d.get("actual") is not None], dtype=float) if batch_docs else np.array([])
    forecasts = np.array([d.get("model_forecast") for d in batch_docs if d.get("model_forecast") is not None], dtype=float) if batch_docs else np.array([])
    anomalies = np.array([d.get("anomaly_score", 0) for d in batch_docs if d.get("anomaly_score") is not None], dtype=float) if batch_docs else np.array([])

    # Align lengths by min length of actuals & forecasts for error calc
    min_len = min(len(actuals), len(forecasts))
    if min_len > 0:
        a = actuals[:min_len]
        f = forecasts[:min_len]
        errors = np.abs(a - f)
        avg_error = float(np.mean(errors))
        max_error = float(np.max(errors))
        median_error = float(np.median(errors))
        std_error = float(np.std(errors))
    else:
        errors = np.array([])
        avg_error = max_error = median_error = std_error = 0.0

    # anomaly density: proportion of docs where anomaly_score above threshold (threshold tunable)
    ANOMALY_THRESHOLD = 75.0
    if len(anomalies) > 0:
        anomaly_density = float(np.mean(anomalies >= ANOMALY_THRESHOLD))
        avg_anomaly_score = float(np.mean(anomalies))
    else:
        anomaly_density = 0.0
        avg_anomaly_score = 0.0

    metrics = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "count": len(batch_docs),
        "avg_forecast_error": avg_error,
        "max_forecast_error": max_error,
        "median_forecast_error": median_error,
        "std_forecast_error": std_error,
        "avg_anomaly_score": avg_anomaly_score,
        "anomaly_density": anomaly_density,
    }
    return metrics

# --- Save meta result to ES ---
def save_meta(index, doc):
    try:
        es.index(index=index, document=doc)
    except Exception as e:
        logging.error("Failed to index meta doc: %s", e)

# --- Streaming fetch & batch processing ---
def fetch_and_process(job_id=None, batch_size=BATCH_SIZE, max_docs=MAX_DOCS, hours_back=TIME_WINDOW_HOURS):
    """
    Streams ML results (from INDEX_INPUT) for the last `hours_back` hours.
    Processes in batches of size `batch_size`. Stops after `max_docs` if set.
    Optionally filters by job_id (or list of job ids) if provided.
    """
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=hours_back)
    ts_range = {"range": {"timestamp": {"gte": start.isoformat(), "lte": now.isoformat()}}}

    # Build query
    must_clauses = [ts_range]
    if job_id:
        must_clauses.append({"term": {"job_id": job_id}})
    if JOB_IDS and not job_id:
        # if global JOB_IDS is provided, filter by that list
        must_clauses.append({"terms": {"job_id": JOB_IDS}})

    query = {"query": {"bool": {"must": must_clauses}}}

    logging.info("Starting scan: index=%s job_id=%s window=%dh", INDEX_INPUT, job_id or "ALL", hours_back)

    # Use helpers.scan for efficient scrolling
    scan_iter = helpers.scan(client=es, index=INDEX_INPUT, query=query, size=batch_size, preserve_order=False, request_timeout=60)

    batch = []
    total = 0
    batch_index = 1
    batch_metrics_list = []

    for hit in scan_iter:
        batch.append(hit.get("_source", {}))
        total += 1

        if len(batch) >= batch_size:
            logging.info("Processing batch %d (docs=%d)...", batch_index, len(batch))
            metrics = compute_batch_metrics(batch)
            metrics.update({
                "batch_index": batch_index,
                "job_id": job_id or ("|".join(JOB_IDS) if JOB_IDS else "ALL"),
                "processed_total": total,
                "window_hours": hours_back,
            })
            # Save per-batch metrics
            save_meta(INDEX_OUTPUT, {"type": "batch", **metrics})
            batch_metrics_list.append(metrics)
            batch.clear()
            batch_index += 1

        if max_docs and total >= max_docs:
            logging.info("Reached max_docs limit (%d). Stopping scan.", max_docs)
            break

    # process remaining
    if batch:
        logging.info("Processing final batch %d (docs=%d)...", batch_index, len(batch))
        metrics = compute_batch_metrics(batch)
        metrics.update({
            "batch_index": batch_index,
            "job_id": job_id or ("|".join(JOB_IDS) if JOB_IDS else "ALL"),
            "processed_total": total,
            "window_hours": hours_back,
        })
        save_meta(INDEX_OUTPUT, {"type": "batch", **metrics})
        batch_metrics_list.append(metrics)

    # compute overall summary from batch_metrics_list
    if batch_metrics_list:
        avg_errs = [m["avg_forecast_error"] for m in batch_metrics_list]
        max_errs = [m["max_forecast_error"] for m in batch_metrics_list]
        densities = [m["anomaly_density"] for m in batch_metrics_list]
        summary = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "job_id": job_id or ("|".join(JOB_IDS) if JOB_IDS else "ALL"),
            "total_docs": total,
            "batches": len(batch_metrics_list),
            "avg_forecast_error_overall": float(np.mean(avg_errs)) if avg_errs else 0.0,
            "max_forecast_error_overall": float(np.max(max_errs)) if max_errs else 0.0,
            "avg_anomaly_density_overall": float(np.mean(densities)) if densities else 0.0,
            # drift proxy: std of batch avg errors
            "forecast_drift_proxy": float(np.std(avg_errs)) if len(avg_errs) > 1 else 0.0,
            "window_hours": hours_back
        }
        # add a simple status
        status = "stable"
        if summary["forecast_drift_proxy"] > 0.5 or summary["avg_anomaly_density_overall"] > 0.2:
            status = "warning"
        if summary["forecast_drift_proxy"] > 1.5 or summary["avg_forecast_error_overall"] > 50:
            status = "critical"
        summary["status"] = status

        save_meta(INDEX_OUTPUT, {"type": "summary", **summary})
        logging.info("Saved summary: %s", json.dumps(summary, indent=2))
        return summary
    else:
        logging.warning("No ML results found for the given query/time-window.")
        return None

# --- Main / optional scheduler ---
def run_once(args):
    return fetch_and_process(job_id=args.job_id, batch_size=args.batch_size, max_docs=args.max_docs, hours_back=args.hours)

def run_loop(args):
    # Simple schedule loop: run every `interval_minutes`
    interval_minutes = args.interval
    logging.info("Entering loop mode: run every %d minutes", interval_minutes)
    while True:
        try:
            fetch_and_process(job_id=args.job_id, batch_size=args.batch_size, max_docs=args.max_docs, hours_back=args.hours)
        except Exception as e:
            logging.exception("Error during fetch_and_process: %s", e)
        logging.info("Sleeping %d minutes...", interval_minutes)
        time.sleep(interval_minutes * 60)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Meta-lite processor for Elastic ML")
    parser.add_argument("--loop", action="store_true", help="Run continuously (every interval minutes)")
    parser.add_argument("--interval", type=int, default=60, help="Interval minutes when --loop (default 60)")
    parser.add_argument("--job-id", type=str, dest="job_id", default=None, help="Optional specific ML job id to filter")
    parser.add_argument("--batch-size", type=int, dest="batch_size", default=BATCH_SIZE, help="Docs per batch")
    parser.add_argument("--max-docs", type=int, dest="max_docs", default=MAX_DOCS, help="Max docs to process (per run)")
    parser.add_argument("--hours", type=int, dest="hours", default=TIME_WINDOW_HOURS, help="Time window in hours to look back")
    args = parser.parse_args()

    # quick check ES connectivity
    try:
        if not es.ping():
            logging.error("Cannot connect to Elasticsearch at %s", ELASTIC_HOST)
            raise SystemExit(1)
        logging.info("Connected to Elasticsearch at %s", ELASTIC_HOST)
    except Exception as e:
        logging.exception("Elasticsearch connectivity error: %s", e)
        raise SystemExit(1)

    if args.loop:
        run_loop(args)
    else:
        s = run_once(args)
        if s:
            logging.info("Meta-lite run completed. Summary status: %s", s.get("status"))
        else:
            logging.info("Meta-lite run completed. No summary (no data).")
