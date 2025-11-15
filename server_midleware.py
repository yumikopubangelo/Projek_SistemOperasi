import logging
import json
from datetime import datetime, timezone
from threading import Thread
from flask import Flask, request, jsonify
from flask_cors import CORS  # <-- TAMBAHAN untuk fix CORS issue
from elasticsearch import Elasticsearch
from waitress import serve

# ==================== 1. KONFIGURASI ====================
ELASTIC_HOST = "https://localhost:9200"
ELASTIC_USER = "elastic"
ELASTIC_PASS = "3+xHEqNsZYJ*2CQoNAlG" 
NAMA_INDEX = "depot_air_qc_data"
SECRET_KEY = "AAEAAWVsYXN0aWMva5liYW5hL2Vucm9sbC1wcm9jZXNzLXRva2VuLTE3NjE4NzM2OTgzNjY6bTJVX0R5eERST3VxUFpPOWotY2lHZQ"
NAMA_FILE_SERTIFIKAT_CA = "http_ca.crt"
NAMA_JOB_ML_TDS = "prediksi_tds_jenuh" 
NAMA_JOB_ML_KERUH = "anomali_kekeruhan" 

# Setup logging yang lebih informatif
logging.basicConfig(
    level=logging.INFO, 
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # <-- Enable CORS untuk semua routes (fix fetch issue)

# ==================== 2. KONEKSI ELASTICSEARCH ====================
logger.info(f"🔌 Mencoba koneksi ke Elasticsearch: {ELASTIC_HOST}")
try:
    es = Elasticsearch(
        [ELASTIC_HOST],
        basic_auth=(ELASTIC_USER, ELASTIC_PASS),
        ca_certs=NAMA_FILE_SERTIFIKAT_CA,
        request_timeout=10  # <-- Tambahkan timeout
    )
    if not es.ping():
        raise ConnectionError("Elasticsearch tidak merespon ping!")
    
    # Cek apakah index sudah ada
    if es.indices.exists(index=NAMA_INDEX):
        doc_count = es.count(index=NAMA_INDEX)['count']
        logger.info(f"✅ Terhubung ke Elasticsearch. Index '{NAMA_INDEX}' punya {doc_count} dokumen.")
    else:
        logger.warning(f"⚠️ Index '{NAMA_INDEX}' belum ada. Akan dibuat otomatis saat data pertama masuk.")
        
except Exception as e:
    logger.error(f"❌ FATAL: Gagal terhubung ke Elasticsearch: {e}")
    logger.error("   Pastikan Elasticsearch running: sudo systemctl status elasticsearch")
    exit(1)

# ==================== 3. BACKGROUND WORKER ====================
def tugas_berat_background(data_sensor):
    """
    Thread worker untuk simpan data ke Elasticsearch.
    Jalan asynchronous supaya ESP32 tidak nunggu lama.
    """
    with app.app_context():
        try:
            # Tambahkan server timestamp (UTC)
            data_sensor['@timestamp'] = datetime.now(timezone.utc).isoformat()
            
            # [FIX] Normalisasi field name (handle typo 'celcius' vs 'celsius')
            if 'suhu_celcius' in data_sensor and 'suhu_celsius' not in data_sensor:
                data_sensor['suhu_celsius'] = data_sensor['suhu_celcius']
            
            # Simpan ke Elasticsearch
            response = es.index(index=NAMA_INDEX, document=data_sensor)
            
            logger.info(
                f"📤 [SAVED] TDS={data_sensor.get('tds_ppm', 'N/A')}, "
                f"Kekeruhan={data_sensor.get('kekeruhan_ntu', 'N/A')}, "
                f"Result={response.get('result', 'unknown')}"
            )
            
        except Exception as e:
            logger.error(f"⚠️ [BACKGROUND ERROR] Gagal simpan data: {e}")

# ==================== 4. ENDPOINT: TERIMA DATA DARI ESP32 ====================
@app.route("/sensor", methods=["POST"])
def terima_data_sensor():
    """
    Endpoint utama untuk terima data dari ESP32/Simulator.
    Flow: Auth → Validate → Background Save → Immediate Response
    """
    
    # --- Step 1: Authentication ---
    auth_header = request.headers.get("Authorization")
    if auth_header != SECRET_KEY:
        logger.warning(f"❌ [AUTH FAILED] IP: {request.remote_addr}")
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    # --- Step 2: Parse & Validate Data ---
    try:
        data = request.get_json(force=True)  # <-- force=True untuk handle edge case
        if not data:
            raise ValueError("Request body kosong atau bukan JSON")
        
        # [FIX] Handle field name variations (celcius vs celsius)
        # Normalisasi ke 'suhu_celsius' sebagai standard
        if 'suhu_celcius' in data:
            data['suhu_celsius'] = data['suhu_celcius']
        
        # Validasi field wajib
        kunci_wajib = ['tds_ppm', 'kekeruhan_ntu', 'suhu_celsius']
        missing = [k for k in kunci_wajib if k not in data]
        if missing:
            raise ValueError(f"Field tidak lengkap: {missing}")
        
        # Validasi range nilai (sanity check)
        if not (0 <= data['tds_ppm'] < 2000):
            raise ValueError(f"TDS out of range: {data['tds_ppm']}")
        if not (0 <= data['kekeruhan_ntu'] < 4000):
            raise ValueError(f"Kekeruhan out of range: {data['kekeruhan_ntu']}")
        if not (0 <= data['suhu_celsius'] < 100):
            raise ValueError(f"Suhu out of range: {data['suhu_celsius']}")
        
        logger.info(f"✅ [VALID DATA] Depot: {data.get('depot_id', 'UNKNOWN')}")
        
        # --- Step 3: Spawn Background Thread ---
        thread = Thread(target=tugas_berat_background, args=(data.copy(),), daemon=True)
        thread.start()
        
        # --- Step 4: Immediate Response (Non-blocking) ---
        return jsonify({
            "status": "sukses", 
            "message": "Data diterima & sedang diproses"
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
        hasil = es.search(
            index=NAMA_INDEX, 
            size=1, 
            sort=[{"@timestamp": {"order": "desc"}}],
            _source_includes=["tds_ppm", "kekeruhan_ntu", "suhu_celsius", "@timestamp", "depot_id"]
        )
        
        if hasil['hits']['total']['value'] > 0:
            data = hasil['hits']['hits'][0]['_source']
            
            # [FIX] Normalisasi output (pastikan selalu 'suhu_celsius')
            if 'suhu_celcius' in data and 'suhu_celsius' not in data:
                data['suhu_celsius'] = data['suhu_celcius']
            
            logger.debug(f"📊 [QUERY] Data terbaru: TDS={data.get('tds_ppm', 'N/A')}")
            return jsonify({"status": "sukses", "data": data}), 200
        else:
            logger.warning("⚠️ [QUERY] Belum ada data di Elasticsearch")
            return jsonify({"status": "error", "message": "Belum ada data"}), 404
            
    except Exception as e:
        logger.error(f"❌ [QUERY ERROR] /data/terbaru: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/data/historis", methods=["GET"])
def dapatkan_data_historis():
    """Ambil N data sensor terakhir untuk grafik."""
    try:
        size = int(request.args.get('size', 50))
        size = min(size, 500)  # Cap maksimum 500 dokumen
        
        hasil = es.search(
            index=NAMA_INDEX, 
            size=size, 
            sort=[{"@timestamp": {"order": "desc"}}],
            _source_includes=["tds_ppm", "kekeruhan_ntu", "suhu_celsius", "@timestamp"]
        )
        
        # Reverse agar data oldest → newest (untuk grafik)
        data_historis = [hit['_source'] for hit in reversed(hasil['hits']['hits'])]
        
        # [FIX] Normalisasi semua data
        for item in data_historis:
            if 'suhu_celcius' in item and 'suhu_celsius' not in item:
                item['suhu_celsius'] = item['suhu_celcius']
        
        logger.info(f"📊 [QUERY] Historis: {len(data_historis)} dokumen returned")
        return jsonify({"status": "sukses", "data": data_historis}), 200
        
    except Exception as e:
        logger.error(f"❌ [QUERY ERROR] /data/historis: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ==================== 6. ENDPOINT: STATUS AI ====================
@app.route("/ai/status", methods=["GET"])
def dapatkan_status_ai():
    """
    Cek apakah ada anomali kritis dalam 1 jam terakhir.
    NOTE: Endpoint ini akan return error 500 jika ML job belum pernah run.
    """
    try:
        hasil = es.search(
            index=".ml-anomalies-*", 
            size=1,
            sort=[{"timestamp": {"order": "desc"}}],
            query={
                "bool": {
                    "filter": [
                        {"terms": {"job_id": [NAMA_JOB_ML_TDS, NAMA_JOB_ML_KERUH]}},
                        {"range": {"record_score": {"gte": 75}}},  # <-- FIX: Ganti 'anomaly_score' jadi 'record_score'
                        {"range": {"timestamp": {"gte": "now-1h"}}}
                    ]
                }
            }
        )
        
        if hasil['hits']['total']['value'] > 0:
            anomali = hasil['hits']['hits'][0]['_source']
            score = anomali.get('record_score', 0)
            job_id = anomali.get('job_id', 'unknown')
            
            logger.warning(f"🚨 [AI ALERT] Anomali terdeteksi! Job={job_id}, Score={score}")
            return jsonify({
                "status": "BAHAYA", 
                "message": f"ANOMALI Kritis Terdeteksi (Score: {score:.1f})",
                "details": {
                    "job_id": job_id,
                    "score": score,
                    "timestamp": anomali.get('timestamp')
                }
            }), 200
        else:
            logger.debug("✅ [AI STATUS] Sistem normal (no anomalies)")
            return jsonify({"status": "AMAN", "message": "Sistem Normal"}), 200
            
    except Exception as e:
        # Ini NORMAL jika ML job belum dibuat atau belum ada data
        logger.info(f"ℹ️ [AI STATUS] ML Engine belum siap: {e}")
        return jsonify({
            "status": "PENDING", 
            "message": "AI Engine sedang training atau belum ada data cukup"
        }), 200  # <-- Return 200 (bukan 500) supaya dashboard tidak error

# ==================== 7. HEALTH CHECK ====================
@app.route("/health", methods=["GET"])
def health_check():
    """Endpoint untuk monitoring system health."""
    try:
        es_ping = es.ping()
        doc_count = es.count(index=NAMA_INDEX)['count'] if es.indices.exists(index=NAMA_INDEX) else 0
        
        return jsonify({
            "status": "healthy",
            "elasticsearch": "connected" if es_ping else "disconnected",
            "total_documents": doc_count,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }), 200
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "error": str(e)
        }), 503

@app.route('/favicon.ico')
def favicon():
    """Suppress annoying favicon 404 error."""
    return '', 204

# ==================== 7. DASHBOARD ROUTE (UNTUK NGROK) ====================
@app.route("/", methods=["GET"])
def dashboard():
    """
    Serve dashboard HTML via Flask route.
    Ini membuat dashboard accessible via Ngrok!
    """
    # Baca file dashboard.html
    try:
        with open('dashboard.html', 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        # [CRITICAL FIX] Ganti API_BASE ke dynamic URL
        # Deteksi apakah request dari Ngrok (HTTPS) atau localhost (HTTP)
        request_host = request.host  # e.g., "abc123.ngrok.io" atau "localhost:5000"
        
        # Deteksi scheme dari header X-Forwarded-Proto (Ngrok sets this)
        # Atau fallback ke request.scheme
        if request.headers.get('X-Forwarded-Proto') == 'https':
            request_scheme = 'https'
        else:
            request_scheme = request.scheme
        
        # Replace hardcoded localhost dengan dynamic URL
        html_content = html_content.replace(
            "const API_BASE = 'http://localhost:5000';",
            f"const API_BASE = '{request_scheme}://{request_host}';"
        )
        
        logger.info(f"📊 Dashboard accessed from: {request_scheme}://{request_host}")
        return html_content, 200, {'Content-Type': 'text/html; charset=utf-8'}
        
    except FileNotFoundError:
        logger.error("❌ File dashboard.html tidak ditemukan!")
        return jsonify({
            "status": "error",
            "message": "Dashboard HTML file not found. Pastikan dashboard.html ada di folder yang sama dengan server."
        }), 500

# ==================== 8. ERROR HANDLERS ====================
@app.errorhandler(404)
def not_found(e):
    return jsonify({"status": "error", "message": "Endpoint tidak ditemukan"}), 404

@app.errorhandler(500)
def internal_error(e):
    logger.error(f"❌ [500 ERROR] {e}")
    return jsonify({"status": "error", "message": "Internal server error"}), 500

# ==================== 9. STARTUP ====================
if __name__ == "__main__":
    logger.info("="*60)
    logger.info("🚀 AquaGuard Middleware Server v4.1 (Ngrok Ready)")
    logger.info("="*60)
    logger.info(f"📍 Local Access:")
    logger.info(f"   • Dashboard: http://localhost:5000")
    logger.info(f"   • API: http://localhost:5000/data/terbaru")
    logger.info(f"   • Health: http://localhost:5000/health")
    logger.info("="*60)
    logger.info("🌐 Ngrok Setup (Untuk Akses Online):")
    logger.info("   1. Install Ngrok: https://ngrok.com/download")
    logger.info("   2. Run: ngrok http 5000")
    logger.info("   3. Copy URL (e.g., https://abc123.ngrok.io)")
    logger.info("   4. Buka URL di browser (Dashboard otomatis muncul!)")
    logger.info("="*60)
    logger.info("💡 Tips Testing:")
    logger.info("   • Simulator: python simulator_esp32.py")
    logger.info("   • Check logs: Lihat output di terminal ini")
    logger.info("   • Debug: Tekan F12 di browser → Console tab")
    logger.info("="*60)
    
    # Gunakan Waitress untuk production-grade server
    serve(app, host="0.0.0.0", port=5000, threads=4)