import logging
import json
import os
from datetime import datetime, timezone
from threading import Thread, Lock
from collections import deque
import time
from flask import Flask, request, jsonify
from flask_cors import CORS
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk
from waitress import serve

# ==================== 1. KONFIGURASI ====================
ELASTIC_HOST = "https://localhost:9200"
ELASTIC_USER = "elastic"
ELASTIC_PASS = "3+xHEqNsZYJ*2CQoNAlG" 
NAMA_INDEX = "depot_air_qc_data"
SECRET_KEY = "AAEAAWVsYXN0aWMva5liYW5hL2Vucm9sbC1wcm9jZXNzLXRva2VuLTE3NjE4NzM2OTgzNjY6bTJVX0R5eERST3VxUFpPOWotY2lHZQ"

# [FIX] Gunakan absolute path untuk certificate
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
NAMA_FILE_SERTIFIKAT_CA = os.path.join(SCRIPT_DIR, "http_ca.crt")

NAMA_JOB_ML_TDS = "prediksi_tds_jenuh" 
NAMA_JOB_ML_KERUH = "anomali_kekeruhan"

# ==================== ADAPTIVE BULK CONFIG ====================
ADAPTIVE_MIN_BUFFER = 5
ADAPTIVE_MAX_BUFFER = 100
ADAPTIVE_MIN_INTERVAL = 0.5
ADAPTIVE_MAX_INTERVAL = 5.0

# Setup logging
logging.basicConfig(
    level=logging.INFO, 
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# ==================== 2. KONEKSI ELASTICSEARCH ====================
logger.info(f"🔌 Mencoba koneksi ke Elasticsearch: {ELASTIC_HOST}")
logger.info(f"📜 Menggunakan CA certificate: {NAMA_FILE_SERTIFIKAT_CA}")

# Verify certificate file exists
if not os.path.exists(NAMA_FILE_SERTIFIKAT_CA):
    logger.error(f"❌ FATAL: File certificate tidak ditemukan: {NAMA_FILE_SERTIFIKAT_CA}")
    logger.error(f"   Current directory: {os.getcwd()}")
    logger.error(f"   Files in directory: {os.listdir(SCRIPT_DIR)}")
    exit(1)

try:
    # [FIX] Explicitly set API compatibility
    es = Elasticsearch(
        [ELASTIC_HOST],
        basic_auth=(ELASTIC_USER, ELASTIC_PASS),
        ca_certs=NAMA_FILE_SERTIFIKAT_CA,
        verify_certs=True,
        ssl_show_warn=False,
        request_timeout=10,
        # Force API version compatibility
        meta_header=False  # Disable version negotiation
    )
    
    if not es.ping():
        raise ConnectionError("Elasticsearch tidak merespon ping!")
    
    if es.indices.exists(index=NAMA_INDEX):
        doc_count = es.count(index=NAMA_INDEX)['count']
        logger.info(f"✅ Terhubung ke Elasticsearch. Index '{NAMA_INDEX}' punya {doc_count} dokumen.")
    else:
        logger.warning(f"⚠️ Index '{NAMA_INDEX}' belum ada. Akan dibuat otomatis.")
        
except Exception as e:
    logger.error(f"❌ FATAL: Gagal terhubung ke Elasticsearch: {e}")
    logger.error(f"   Troubleshooting:")
    logger.error(f"   1. Cek Elasticsearch running: docker ps")
    logger.error(f"   2. Test manual: curl -k -u elastic:PASSWORD https://localhost:9200")
    logger.error(f"   3. Verify certificate: type {NAMA_FILE_SERTIFIKAT_CA}")
    exit(1)

# ==================== 3. ADAPTIVE BULK BUFFER MANAGER ====================
class AdaptiveBulkBufferManager:
    """
    Self-tuning bulk buffer manager yang automatically adjust parameters
    berdasarkan traffic pattern dan system performance.
    """
    
    def __init__(self):
        self.buffer = deque()
        self.lock = Lock()
        
        # Adaptive parameters (will be auto-adjusted)
        self.buffer_size = 10
        self.flush_interval = 2.0
        
        # Performance tracking
        self.request_timestamps = deque(maxlen=100)
        self.flush_times = deque(maxlen=20)
        
        self.last_flush_time = time.time()
        self.total_flushed = 0
        self.total_received = 0
        self.adaptation_count = 0
        
        # Start background threads
        self.flush_thread = Thread(target=self._periodic_flush, daemon=True)
        self.flush_thread.start()
        
        self.adapt_thread = Thread(target=self._adaptive_tuning, daemon=True)
        self.adapt_thread.start()
        
        logger.info(f"🧠 Adaptive Bulk Buffer Manager started")
        logger.info(f"   Initial: buffer_size={self.buffer_size}, flush_interval={self.flush_interval}s")
    
    def add(self, document):
        """Add document to buffer with automatic flushing."""
        with self.lock:
            # Track request timing
            current_time = time.time()
            self.request_timestamps.append(current_time)
            self.total_received += 1
            
            # Prepare document
            document['@timestamp'] = datetime.now(timezone.utc).isoformat()
            if 'suhu_celcius' in document and 'suhu_celsius' not in document:
                document['suhu_celsius'] = document['suhu_celcius']
            
            self.buffer.append(document)
            
            # Auto-flush if buffer exceeds dynamic size
            if len(self.buffer) >= self.buffer_size:
                logger.debug(f"📦 Buffer full ({len(self.buffer)}/{self.buffer_size}), flushing...")
                self._flush()
    
    def _calculate_traffic_rate(self):
        """Calculate current traffic rate (requests per minute)."""
        if len(self.request_timestamps) < 2:
            return 0.0
        
        time_span = self.request_timestamps[-1] - self.request_timestamps[0]
        if time_span == 0:
            return 0.0
        
        rpm = (len(self.request_timestamps) / time_span) * 60
        return rpm
    
    def _calculate_avg_flush_time(self):
        """Calculate average flush time."""
        if not self.flush_times:
            return 0.5
        return sum(self.flush_times) / len(self.flush_times)
    
    def _adaptive_tuning(self):
        """Background thread untuk adaptive parameter tuning."""
        while True:
            time.sleep(10)
            
            with self.lock:
                traffic_rpm = self._calculate_traffic_rate()
                avg_flush_time = self._calculate_avg_flush_time()
                
                old_buffer_size = self.buffer_size
                old_flush_interval = self.flush_interval
                
                # Strategy based on traffic
                if traffic_rpm < 5:
                    target_buffer = ADAPTIVE_MIN_BUFFER
                    target_interval = ADAPTIVE_MIN_INTERVAL
                    strategy = "LOW_TRAFFIC"
                elif traffic_rpm < 30:
                    ratio = (traffic_rpm - 5) / 25
                    target_buffer = int(ADAPTIVE_MIN_BUFFER + (20 - ADAPTIVE_MIN_BUFFER) * ratio)
                    target_interval = ADAPTIVE_MIN_INTERVAL + (2.0 - ADAPTIVE_MIN_INTERVAL) * ratio
                    strategy = "MODERATE_TRAFFIC"
                elif traffic_rpm < 100:
                    ratio = (traffic_rpm - 30) / 70
                    target_buffer = int(20 + (50 - 20) * ratio)
                    target_interval = 2.0 + (3.0 - 2.0) * ratio
                    strategy = "HIGH_TRAFFIC"
                else:
                    target_buffer = ADAPTIVE_MAX_BUFFER
                    target_interval = ADAPTIVE_MAX_INTERVAL
                    strategy = "BURST_TRAFFIC"
                
                # Adjust based on flush performance
                if avg_flush_time > 1.0:
                    target_buffer = min(target_buffer * 1.2, ADAPTIVE_MAX_BUFFER)
                
                # Smooth adjustment
                self.buffer_size = int(self.buffer_size * 0.7 + target_buffer * 0.3)
                self.flush_interval = self.flush_interval * 0.7 + target_interval * 0.3
                
                # Clamp to min/max
                self.buffer_size = max(ADAPTIVE_MIN_BUFFER, min(ADAPTIVE_MAX_BUFFER, self.buffer_size))
                self.flush_interval = max(ADAPTIVE_MIN_INTERVAL, min(ADAPTIVE_MAX_INTERVAL, self.flush_interval))
                
                # Log adaptation if significant change
                if abs(old_buffer_size - self.buffer_size) > 2 or abs(old_flush_interval - self.flush_interval) > 0.5:
                    self.adaptation_count += 1
                    logger.info(
                        f"🧠 [ADAPT #{self.adaptation_count}] Strategy: {strategy} | "
                        f"Traffic: {traffic_rpm:.1f} req/min | "
                        f"Buffer: {old_buffer_size}→{self.buffer_size} | "
                        f"Interval: {old_flush_interval:.1f}s→{self.flush_interval:.1f}s"
                    )
    
    def _flush(self):
        """Flush buffer to Elasticsearch using bulk API."""
        if not self.buffer:
            return
        
        flush_start_time = time.time()
        
        # Prepare bulk actions
        actions = []
        for doc in self.buffer:
            actions.append({
                '_index': NAMA_INDEX,
                '_source': doc
            })
        
        buffer_size = len(actions)
        
        try:
            # Bulk insert
            success, failed = bulk(es, actions, raise_on_error=False)
            
            self.total_flushed += success
            
            # Track flush performance
            flush_duration = time.time() - flush_start_time
            self.flush_times.append(flush_duration)
            
            if failed:
                logger.warning(f"⚠️ [BULK] {failed} dokumen gagal")
            
            logger.info(
                f"📤 [BULK] Flushed {success} docs in {flush_duration:.3f}s "
                f"(total: {self.total_flushed}, buffer: {self.buffer_size})"
            )
            
            # Clear buffer
            self.buffer.clear()
            self.last_flush_time = time.time()
            
        except Exception as e:
            logger.error(f"❌ [BULK ERROR] {e}")
    
    def _periodic_flush(self):
        """Background thread untuk periodic flush."""
        while True:
            time.sleep(0.5)
            
            with self.lock:
                time_since_last_flush = time.time() - self.last_flush_time
                
                if self.buffer and time_since_last_flush >= self.flush_interval:
                    logger.debug(f"⏰ Periodic flush ({len(self.buffer)} docs, interval={self.flush_interval:.1f}s)")
                    self._flush()
    
    def force_flush(self):
        """Force flush all pending documents."""
        with self.lock:
            if self.buffer:
                logger.info(f"🔄 Force flushing {len(self.buffer)} pending docs...")
                self._flush()
    
    def get_stats(self):
        """Get current buffer statistics."""
        with self.lock:
            return {
                "current_buffer_size": len(self.buffer),
                "configured_buffer_size": self.buffer_size,
                "configured_flush_interval": round(self.flush_interval, 2),
                "total_received": self.total_received,
                "total_flushed": self.total_flushed,
                "pending": self.total_received - self.total_flushed,
                "traffic_rpm": round(self._calculate_traffic_rate(), 2),
                "avg_flush_time": round(self._calculate_avg_flush_time(), 3),
                "adaptation_count": self.adaptation_count,
                "last_flush": datetime.fromtimestamp(self.last_flush_time).isoformat()
            }

# Initialize adaptive buffer manager
buffer_manager = AdaptiveBulkBufferManager()

# ==================== 4. ENDPOINT: TERIMA DATA ====================
@app.route("/sensor", methods=["POST"])
def terima_data_sensor():
    """Endpoint dengan adaptive bulk optimization."""
    
    # Authentication
    auth_header = request.headers.get("Authorization")
    if auth_header != SECRET_KEY:
        logger.warning(f"❌ [AUTH FAILED] IP: {request.remote_addr}")
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    # Parse & Validate
    try:
        data = request.get_json(force=True)
        if not data:
            raise ValueError("Request body kosong atau bukan JSON")
        
        if 'suhu_celcius' in data:
            data['suhu_celsius'] = data['suhu_celcius']
        
        kunci_wajib = ['tds_ppm', 'kekeruhan_ntu', 'suhu_celsius']
        missing = [k for k in kunci_wajib if k not in data]
        if missing:
            raise ValueError(f"Field tidak lengkap: {missing}")
        
        if not (0 <= data['tds_ppm'] < 2000):
            raise ValueError(f"TDS out of range: {data['tds_ppm']}")
        if not (0 <= data['kekeruhan_ntu'] < 4000):
            raise ValueError(f"Kekeruhan out of range: {data['kekeruhan_ntu']}")
        if not (0 <= data['suhu_celsius'] < 100):
            raise ValueError(f"Suhu out of range: {data['suhu_celsius']}")
        
        logger.debug(f"✅ [VALID DATA] Depot: {data.get('depot_id', 'UNKNOWN')}")
        
        # Add to adaptive buffer
        buffer_manager.add(data.copy())
        
        # Immediate response
        return jsonify({
            "status": "sukses", 
            "message": "Data buffered (adaptive bulk insert active)"
        }), 201

    except ValueError as ve:
        logger.warning(f"⚠️ [VALIDATION ERROR] {ve}")
        return jsonify({"status": "error", "message": str(ve)}), 400
    except Exception as e:
        logger.error(f"❌ [UNEXPECTED ERROR] {e}")
        return jsonify({"status": "error", "message": "Internal server error"}), 500

# ==================== 5. ENDPOINT: QUERY DATA ====================
@app.route("/data/terbaru", methods=["GET"])
def dapatkan_data_terbaru():
    """Ambil 1 data sensor paling baru."""
    try:
        buffer_manager.force_flush()
        time.sleep(0.1)
        
        hasil = es.search(
            index=NAMA_INDEX, 
            size=1, 
            sort=[{"@timestamp": {"order": "desc"}}],
            _source_includes=["tds_ppm", "kekeruhan_ntu", "suhu_celsius", "@timestamp", "depot_id"]
        )
        
        if hasil['hits']['total']['value'] > 0:
            data = hasil['hits']['hits'][0]['_source']
            if 'suhu_celcius' in data and 'suhu_celsius' not in data:
                data['suhu_celsius'] = data['suhu_celcius']
            
            logger.debug(f"📊 [QUERY] Data terbaru: TDS={data.get('tds_ppm', 'N/A')}")
            return jsonify({"status": "sukses", "data": data}), 200
        else:
            logger.warning("⚠️ [QUERY] Belum ada data")
            return jsonify({"status": "error", "message": "Belum ada data"}), 404
            
    except Exception as e:
        logger.error(f"❌ [QUERY ERROR] /data/terbaru: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/data/historis", methods=["GET"])
def dapatkan_data_historis():
    """Ambil N data sensor terakhir untuk grafik."""
    try:
        size = int(request.args.get('size', 50))
        size = min(size, 500)
        
        hasil = es.search(
            index=NAMA_INDEX, 
            size=size, 
            sort=[{"@timestamp": {"order": "desc"}}],
            _source_includes=["tds_ppm", "kekeruhan_ntu", "suhu_celsius", "@timestamp"]
        )
        
        data_historis = [hit['_source'] for hit in reversed(hasil['hits']['hits'])]
        
        for item in data_historis:
            if 'suhu_celcius' in item and 'suhu_celsius' not in item:
                item['suhu_celsius'] = item['suhu_celcius']
        
        logger.info(f"📊 [QUERY] Historis: {len(data_historis)} dokumen")
        return jsonify({"status": "sukses", "data": data_historis}), 200
        
    except Exception as e:
        logger.error(f"❌ [QUERY ERROR] /data/historis: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ==================== 6. ENDPOINT: ADAPTIVE STATS ====================
@app.route("/adaptive/stats", methods=["GET"])
def adaptive_stats():
    """Get adaptive buffer statistics."""
    stats = buffer_manager.get_stats()
    
    # Add interpretation
    traffic_rpm = stats['traffic_rpm']
    if traffic_rpm < 5:
        traffic_level = "LOW"
        strategy = "Small buffer, fast flush for minimal latency"
    elif traffic_rpm < 30:
        traffic_level = "MODERATE"
        strategy = "Balanced buffer and flush interval"
    elif traffic_rpm < 100:
        traffic_level = "HIGH"
        strategy = "Large buffer for maximum throughput"
    else:
        traffic_level = "BURST"
        strategy = "Maximum buffer, optimized for extreme load"
    
    stats['traffic_level'] = traffic_level
    stats['current_strategy'] = strategy
    
    return jsonify(stats), 200

# ==================== 7. ENDPOINT: AI STATUS ====================
@app.route("/ai/status", methods=["GET"])
def dapatkan_status_ai():
    """Cek anomali kritis."""
    try:
        hasil = es.search(
            index=".ml-anomalies-*", 
            size=1,
            sort=[{"timestamp": {"order": "desc"}}],
            query={
                "bool": {
                    "filter": [
                        {"terms": {"job_id": [NAMA_JOB_ML_TDS, NAMA_JOB_ML_KERUH]}},
                        {"range": {"record_score": {"gte": 75}}},
                        {"range": {"timestamp": {"gte": "now-1h"}}}
                    ]
                }
            }
        )
        
        if hasil['hits']['total']['value'] > 0:
            anomali = hasil['hits']['hits'][0]['_source']
            score = anomali.get('record_score', 0)
            job_id = anomali.get('job_id', 'unknown')
            
            logger.warning(f"🚨 [AI ALERT] Anomali! Job={job_id}, Score={score}")
            return jsonify({
                "status": "BAHAYA", 
                "message": f"ANOMALI Kritis (Score: {score:.1f})",
                "details": {"job_id": job_id, "score": score, "timestamp": anomali.get('timestamp')}
            }), 200
        else:
            return jsonify({"status": "AMAN", "message": "Sistem Normal"}), 200
            
    except Exception as e:
        logger.info(f"ℹ️ [AI STATUS] ML Engine belum siap: {e}")
        return jsonify({"status": "PENDING", "message": "AI Engine training"}), 200

# ==================== 8. HEALTH CHECK ====================
@app.route("/health", methods=["GET"])
def health_check():
    """System health check dengan adaptive stats."""
    try:
        es_ping = es.ping()
        doc_count = es.count(index=NAMA_INDEX)['count'] if es.indices.exists(index=NAMA_INDEX) else 0
        
        stats = buffer_manager.get_stats()
        
        return jsonify({
            "status": "healthy",
            "elasticsearch": "connected" if es_ping else "disconnected",
            "total_documents": doc_count,
            "adaptive_buffer": {
                "pending": stats['pending'],
                "buffer_size": stats['configured_buffer_size'],
                "flush_interval": stats['configured_flush_interval'],
                "traffic_rpm": stats['traffic_rpm']
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }), 200
    except Exception as e:
        return jsonify({"status": "unhealthy", "error": str(e)}), 503

@app.route('/favicon.ico')
def favicon():
    return '', 204

# ==================== 9. DASHBOARD ROUTE ====================
@app.route("/", methods=["GET"])
def dashboard():
    """Serve dashboard HTML."""
    try:
        # [FIX] Gunakan absolute path untuk dashboard.html
        dashboard_path = os.path.join(SCRIPT_DIR, 'dashboard.html')
        
        # Check if file exists
        if not os.path.exists(dashboard_path):
            logger.error(f"❌ File tidak ditemukan: {dashboard_path}")
            logger.error(f"   Files in directory: {os.listdir(SCRIPT_DIR)}")
            return jsonify({
                "status": "error", 
                "message": "Dashboard not found",
                "expected_path": dashboard_path,
                "files_in_directory": os.listdir(SCRIPT_DIR)
            }), 404
        
        with open(dashboard_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        # Auto-detect request scheme (ngrok uses X-Forwarded-Proto header)
        request_host = request.host
        request_scheme = request.headers.get('X-Forwarded-Proto', request.scheme)
        
        # Replace API_BASE in dashboard
        html_content = html_content.replace(
            "const API_BASE = 'http://localhost:5000';",
            f"const API_BASE = '{request_scheme}://{request_host}';"
        )
        
        logger.info(f"📊 Dashboard accessed from: {request_scheme}://{request_host}")
        return html_content, 200, {'Content-Type': 'text/html; charset=utf-8'}
        
    except Exception as e:
        logger.error(f"❌ Dashboard error: {e}")
        return jsonify({
            "status": "error", 
            "message": str(e),
            "working_directory": os.getcwd(),
            "script_directory": SCRIPT_DIR
        }), 500

# ==================== 10. ERROR HANDLERS ====================
@app.errorhandler(404)
def not_found(e):
    return jsonify({"status": "error", "message": "Endpoint tidak ditemukan"}), 404

@app.errorhandler(500)
def internal_error(e):
    logger.error(f"❌ [500 ERROR] {e}")
    return jsonify({"status": "error", "message": "Internal server error"}), 500

# ==================== 11. GRACEFUL SHUTDOWN ====================
import signal
import sys

def graceful_shutdown(signum, frame):
    """Graceful shutdown dengan flush buffer."""
    logger.info("\n🛑 Shutdown signal received...")
    logger.info("📤 Flushing pending buffer...")
    
    buffer_manager.force_flush()
    time.sleep(1)
    
    # Print final stats
    stats = buffer_manager.get_stats()
    logger.info(f"📊 Final Stats:")
    logger.info(f"   Total Received: {stats['total_received']}")
    logger.info(f"   Total Flushed: {stats['total_flushed']}")
    logger.info(f"   Adaptations: {stats['adaptation_count']}")
    
    logger.info("✅ Graceful shutdown complete. Goodbye!")
    sys.exit(0)

signal.signal(signal.SIGINT, graceful_shutdown)
signal.signal(signal.SIGTERM, graceful_shutdown)

# ==================== 12. STARTUP ====================
if __name__ == "__main__":
    logger.info("="*70)
    logger.info("🚀 AquaGuard Middleware Server v6.0 (ADAPTIVE INTELLIGENCE)")
    logger.info("="*70)
    logger.info(f"📍 Endpoints:")
    logger.info(f"   • Dashboard: http://localhost:5000")
    logger.info(f"   • Health: http://localhost:5000/health")
    logger.info(f"   • Adaptive Stats: http://localhost:5000/adaptive/stats")
    logger.info("="*70)
    logger.info("🧠 ADAPTIVE BULK INSERT:")
    logger.info(f"   • Auto-adjusts based on traffic pattern")
    logger.info(f"   • Buffer range: {ADAPTIVE_MIN_BUFFER}-{ADAPTIVE_MAX_BUFFER} docs")
    logger.info(f"   • Interval range: {ADAPTIVE_MIN_INTERVAL}-{ADAPTIVE_MAX_INTERVAL}s")
    logger.info(f"   • No manual tuning required! 🎯")
    logger.info("="*70)
    logger.info("📊 Monitoring:")
    logger.info("   • Watch logs untuk see real-time adaptations")
    logger.info("   • curl http://localhost:5000/adaptive/stats")
    logger.info("="*70)
    
    serve(app, host="0.0.0.0", port=5000, threads=4)