# meta_lite_enhanced.py
"""
Enhanced Meta-lite with Alerting & Better Error Handling
"""

import os
import time
import json
import requests
from datetime import datetime, timezone, timedelta
from elasticsearch import Elasticsearch, helpers
import numpy as np
import logging
import argparse

# --- ENHANCED CONFIG ---
ELASTIC_HOST = os.environ.get("ELASTIC_HOST", "https://localhost:9200")
ELASTIC_USER = os.environ.get("ELASTIC_USER", "elastic")
ELASTIC_PASS = os.environ.get("ELASTIC_PASS", "3+xHEqNsZYJ*2CQoNAlG")
CA_CERT = os.environ.get("CA_CERT", "http_ca.crt")
INDEX_INPUT = os.environ.get("INDEX_INPUT", ".ml-anomalies-*")
INDEX_OUTPUT = os.environ.get("INDEX_OUTPUT", "meta_lite_result")

JOB_IDS = os.environ.get("JOB_IDS", "")
JOB_IDS = [j.strip() for j in JOB_IDS.split(",") if j.strip()] if JOB_IDS else None

BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "10000"))
MAX_DOCS = int(os.environ.get("MAX_DOCS", "100000"))
TIME_WINDOW_HOURS = int(os.environ.get("TIME_WINDOW_HOURS", str(24 * 30)))

# NEW: Adaptive thresholds
ANOMALY_THRESHOLD = float(os.environ.get("ANOMALY_THRESHOLD", "75.0"))
DRIFT_WARNING = float(os.environ.get("DRIFT_WARNING", "0.5"))
DRIFT_CRITICAL = float(os.environ.get("DRIFT_CRITICAL", "1.5"))

# NEW: Alerting config
ENABLE_ALERTS = os.environ.get("ENABLE_ALERTS", "false").lower() == "true"
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")  # Slack/Discord/Custom webhook

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

# --- Elasticsearch client ---
es_kwargs = {
    "hosts": [ELASTIC_HOST],
    "basic_auth": (ELASTIC_USER, ELASTIC_PASS),
}
if CA_CERT and CA_CERT.lower() != "none":
    es_kwargs["ca_certs"] = CA_CERT
else:
    es_kwargs["verify_certs"] = False

es = Elasticsearch(**es_kwargs)

# --- NEW: Safe data conversion ---
def safe_float_array(values, field_name="unknown"):
    """
    Convert values to float array, skip invalid/corrupt data.
    Returns numpy array.
    """
    result = []
    skipped = 0
    
    for v in values:
        try:
            if v is not None:
                result.append(float(v))
        except (ValueError, TypeError) as e:
            skipped += 1
            if skipped <= 3:  # Log first 3 errors only
                logger.debug(f"Skipped invalid {field_name} value: {v} ({e})")
    
    if skipped > 0:
        logger.warning(f"Skipped {skipped} invalid {field_name} values")
    
    return np.array(result) if result else np.array([])

# --- Enhanced metric computation ---
def compute_batch_metrics(batch_docs):
    """
    Compute metrics with better error handling and data validation.
    """
    if not batch_docs:
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "count": 0,
            "avg_forecast_error": 0.0,
            "max_forecast_error": 0.0,
            "median_forecast_error": 0.0,
            "std_forecast_error": 0.0,
            "avg_anomaly_score": 0.0,
            "anomaly_density": 0.0,
        }
    
    # Safe extraction
    actuals = safe_float_array(
        [d.get("actual") for d in batch_docs if d.get("actual") is not None],
        "actual"
    )
    forecasts = safe_float_array(
        [d.get("model_forecast") for d in batch_docs if d.get("model_forecast") is not None],
        "forecast"
    )
    anomalies = safe_float_array(
        [d.get("anomaly_score", 0) for d in batch_docs],
        "anomaly_score"
    )
    
    # Compute errors
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
        avg_error = max_error = median_error = std_error = 0.0
    
    # Anomaly metrics
    if len(anomalies) > 0:
        anomaly_density = float(np.mean(anomalies >= ANOMALY_THRESHOLD))
        avg_anomaly_score = float(np.mean(anomalies))
    else:
        anomaly_density = 0.0
        avg_anomaly_score = 0.0
    
    metrics = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "count": len(batch_docs),
        "valid_data_points": min_len,
        "avg_forecast_error": avg_error,
        "max_forecast_error": max_error,
        "median_forecast_error": median_error,
        "std_forecast_error": std_error,
        "avg_anomaly_score": avg_anomaly_score,
        "anomaly_density": anomaly_density,
    }
    
    return metrics

# --- NEW: Alerting system ---
def send_alert(summary, severity="warning"):
    """
    Send alert to webhook (Slack/Discord/Custom).
    """
    if not ENABLE_ALERTS or not WEBHOOK_URL:
        return
    
    # Prepare message
    emoji = {"stable": "✅", "warning": "⚠️", "critical": "🚨"}
    color = {"stable": "#28a745", "warning": "#ffc107", "critical": "#dc3545"}
    
    status = summary.get("status", "unknown")
    
    message = {
        "text": f"{emoji.get(status, '⚠️')} Meta-Lite Alert: {status.upper()}",
        "attachments": [{
            "color": color.get(status, "#999999"),
            "fields": [
                {"title": "Status", "value": status, "short": True},
                {"title": "Total Docs", "value": f"{summary.get('total_docs', 0):,}", "short": True},
                {"title": "Avg Forecast Error", "value": f"{summary.get('avg_forecast_error_overall', 0):.2f}", "short": True},
                {"title": "Drift Proxy", "value": f"{summary.get('forecast_drift_proxy', 0):.3f}", "short": True},
                {"title": "Anomaly Density", "value": f"{summary.get('avg_anomaly_density_overall', 0):.1%}", "short": True},
                {"title": "Timestamp", "value": summary.get('timestamp', 'N/A'), "short": False}
            ]
        }]
    }
    
    try:
        response = requests.post(WEBHOOK_URL, json=message, timeout=10)
        if response.status_code == 200:
            logger.info(f"Alert sent successfully ({status})")
        else:
            logger.warning(f"Alert failed: HTTP {response.status_code}")
    except Exception as e:
        logger.error(f"Failed to send alert: {e}")

# --- Enhanced save with retry ---
def save_meta(index, doc, max_retries=3):
    """
    Save document to Elasticsearch with retry logic.
    """
    for attempt in range(max_retries):
        try:
            result = es.index(index=index, document=doc)
            logger.debug(f"Saved doc to {index}: {result.get('_id')}")
            return True
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff
                logger.warning(f"Save failed (attempt {attempt+1}/{max_retries}), retrying in {wait_time}s: {e}")
                time.sleep(wait_time)
            else:
                logger.error(f"Failed to save after {max_retries} attempts: {e}")
                return False

# --- Memory-efficient streaming processor ---
def fetch_and_process(job_id=None, batch_size=BATCH_SIZE, max_docs=MAX_DOCS, hours_back=TIME_WINDOW_HOURS):
    """
    Stream and process ML results with memory-efficient accumulation.
    """
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=hours_back)
    ts_range = {"range": {"timestamp": {"gte": start.isoformat(), "lte": now.isoformat()}}}
    
    # Build query
    must_clauses = [ts_range]
    if job_id:
        must_clauses.append({"term": {"job_id": job_id}})
    if JOB_IDS and not job_id:
        must_clauses.append({"terms": {"job_id": JOB_IDS}})
    
    query = {"query": {"bool": {"must": must_clauses}}}
    
    logger.info(f"Starting scan: index={INDEX_INPUT}, job_id={job_id or 'ALL'}, window={hours_back}h")
    
    # Scan
    scan_iter = helpers.scan(
        client=es,
        index=INDEX_INPUT,
        query=query,
        size=batch_size,
        preserve_order=False,
        request_timeout=60
    )
    
    # Memory-efficient accumulators (don't store all batch_metrics_list)
    batch = []
    total = 0
    batch_index = 1
    
    # Running statistics for summary
    running_sum_error = 0.0
    running_max_error = 0.0
    running_sum_density = 0.0
    batch_errors = []  # For drift calculation (only store averages)
    
    # Process stream
    for hit in scan_iter:
        batch.append(hit.get("_source", {}))
        total += 1
        
        # Progress indicator
        if total % 1000 == 0:
            logger.info(f"Progress: {total:,} docs processed...")
        
        if len(batch) >= batch_size:
            logger.info(f"Processing batch {batch_index} ({len(batch)} docs)...")
            
            metrics = compute_batch_metrics(batch)
            metrics.update({
                "batch_index": batch_index,
                "job_id": job_id or ("|".join(JOB_IDS) if JOB_IDS else "ALL"),
                "processed_total": total,
                "window_hours": hours_back,
            })
            
            # Save batch
            save_meta(INDEX_OUTPUT, {"type": "batch", **metrics})
            
            # Accumulate for summary (memory-efficient)
            running_sum_error += metrics["avg_forecast_error"]
            running_max_error = max(running_max_error, metrics["max_forecast_error"])
            running_sum_density += metrics["anomaly_density"]
            batch_errors.append(metrics["avg_forecast_error"])
            
            batch.clear()
            batch_index += 1
        
        if max_docs and total >= max_docs:
            logger.info(f"Reached max_docs limit ({max_docs}). Stopping.")
            break
    
    # Final batch
    if batch:
        logger.info(f"Processing final batch {batch_index} ({len(batch)} docs)...")
        metrics = compute_batch_metrics(batch)
        metrics.update({
            "batch_index": batch_index,
            "job_id": job_id or ("|".join(JOB_IDS) if JOB_IDS else "ALL"),
            "processed_total": total,
            "window_hours": hours_back,
        })
        save_meta(INDEX_OUTPUT, {"type": "batch", **metrics})
        
        running_sum_error += metrics["avg_forecast_error"]
        running_max_error = max(running_max_error, metrics["max_forecast_error"])
        running_sum_density += metrics["anomaly_density"]
        batch_errors.append(metrics["avg_forecast_error"])
    
    # Compute summary
    if batch_index > 1 or batch:
        num_batches = batch_index if not batch else batch_index - 1
        
        summary = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "job_id": job_id or ("|".join(JOB_IDS) if JOB_IDS else "ALL"),
            "total_docs": total,
            "batches": num_batches,
            "avg_forecast_error_overall": running_sum_error / num_batches if num_batches > 0 else 0.0,
            "max_forecast_error_overall": running_max_error,
            "avg_anomaly_density_overall": running_sum_density / num_batches if num_batches > 0 else 0.0,
            "forecast_drift_proxy": float(np.std(batch_errors)) if len(batch_errors) > 1 else 0.0,
            "window_hours": hours_back
        }
        
        # Enhanced status with configurable thresholds
        drift = summary["forecast_drift_proxy"]
        density = summary["avg_anomaly_density_overall"]
        avg_error = summary["avg_forecast_error_overall"]
        
        if drift > DRIFT_CRITICAL or density > 0.3 or avg_error > 100:
            status = "critical"
        elif drift > DRIFT_WARNING or density > 0.2 or avg_error > 50:
            status = "warning"
        else:
            status = "stable"
        
        summary["status"] = status
        
        # Save summary
        save_meta(INDEX_OUTPUT, {"type": "summary", **summary})
        logger.info(f"Summary: status={status}, docs={total:,}, drift={drift:.3f}")
        
        # Send alert if not stable
        if status != "stable":
            send_alert(summary, severity=status)
        
        return summary
    else:
        logger.warning("No ML results found for the given query/time-window.")
        return None

# --- Main ---
def run_once(args):
    return fetch_and_process(
        job_id=args.job_id,
        batch_size=args.batch_size,
        max_docs=args.max_docs,
        hours_back=args.hours
    )

def run_loop(args):
    interval_minutes = args.interval
    logger.info(f"Loop mode: running every {interval_minutes} minutes")
    
    while True:
        try:
            summary = fetch_and_process(
                job_id=args.job_id,
                batch_size=args.batch_size,
                max_docs=args.max_docs,
                hours_back=args.hours
            )
            
            if summary:
                logger.info(f"Run completed. Status: {summary.get('status')}")
        except Exception as e:
            logger.exception(f"Error during run: {e}")
        
        logger.info(f"Sleeping {interval_minutes} minutes...")
        time.sleep(interval_minutes * 60)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Enhanced Meta-lite processor")
    parser.add_argument("--loop", action="store_true", help="Run continuously")
    parser.add_argument("--interval", type=int, default=60, help="Loop interval (minutes)")
    parser.add_argument("--job-id", type=str, dest="job_id", default=None, help="Filter by ML job ID")
    parser.add_argument("--batch-size", type=int, dest="batch_size", default=BATCH_SIZE, help="Docs per batch")
    parser.add_argument("--max-docs", type=int, dest="max_docs", default=MAX_DOCS, help="Max docs per run")
    parser.add_argument("--hours", type=int, dest="hours", default=TIME_WINDOW_HOURS, help="Time window (hours)")
    args = parser.parse_args()
    
    # Test connection
    try:
        if not es.ping():
            logger.error(f"Cannot connect to Elasticsearch at {ELASTIC_HOST}")
            raise SystemExit(1)
        logger.info(f"✅ Connected to Elasticsearch at {ELASTIC_HOST}")
    except Exception as e:
        logger.exception(f"Elasticsearch error: {e}")
        raise SystemExit(1)
    
    if args.loop:
        run_loop(args)
    else:
        s = run_once(args)
        if s:
            logger.info(f"Completed. Status: {s.get('status')}")
        else:
            logger.info("Completed. No data found.")