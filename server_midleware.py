from flask import Flask, request, jsonify
from elasticsearch import Elasticsearch
from datetime import datetime, timezone

# --- KONFIGURASI ---
ELASTIC_HOST = "https://localhost:9200"
ELASTIC_USER = "elastic"
ELASTIC_PASS = "3+xHEqNsZYJ*2CQoNAlG"  # Ganti sesuai password kamu
NAMA_INDEX = "depot_air_qc_data"
# Kunci rahasia ini HARUS SAMA dengan yang di ESP32-mu
SECRET_KEY = "AAEAAWVsYXN0aWMva5liYW5hL2Vucm9sbC1wcm9jZXNzLXRva2VuLTE3NjE4NzM2OTgzNjY6bTJVX0R5eERST3VxUFpPOWotY2lHZQ" 
# --------------------

# Tentukan nama file sertifikat yang Anda salin
NAMA_FILE_SERTIFIKAT_CA = "http_ca.crt" # Ganti jika nama file Anda beda (misal: "http_ca.crt")

app = Flask(__name__)

# --- KONEKSI ELASTICSEARCH YANG AMAN DENGAN VERIFIKASI ---
print("Mencoba terhubung ke Elasticsearch di", ELASTIC_HOST)
try:
    es = Elasticsearch(
        [ELASTIC_HOST],
        basic_auth=(ELASTIC_USER, ELASTIC_PASS),
        
        # --- PERUBAHAN DI SINI ---
        # 1. Hapus 'verify_certs=False' dan 'ssl_show_warn=False'
        # 2. Tentukan path ke file sertifikat CA Anda
        #    Ini akan otomatis mengaktifkan verifikasi SSL (verify_certs=True)
        ca_certs=NAMA_FILE_SERTIFIKAT_CA
        # ---------------------------
    )

    # Cek koneksi ke Elastic saat startup
    if not es.ping():
        raise ValueError("Koneksi ke Elastic gagal! Cek host, user, password, dan file ca_certs.")
    
    print("Berhasil terhubung ke Elasticsearch (DENGAN VERIFIKASI SSL AKTIF).")

except FileNotFoundError:
    print(f"GAGAL: File sertifikat '{NAMA_FILE_SERTIFIKAT_CA}' tidak ditemukan.")
    print("Pastikan Anda sudah menyalin file CA dari folder Elasticsearch")
    print("ke folder yang sama dengan app.py")
    exit()
except Exception as e:
    # Ini mungkin terjadi jika password salah, host salah, ATAU sertifikat tidak cocok
    print(f"GAGAL terhubung ke Elastic: {e}")
    print("Pastikan user, password, dan file sertifikat CA sudah benar.")
    exit()

# Ini adalah "pintu masuk" yang akan dipanggil ESP32
@app.route("/sensor", methods=["POST"])
def terima_data_sensor():
    
    # --- 1. Validasi Pengirim (Autentikasi) ---
    # Cek apakah ESP32 mengirim kunci rahasia yang benar?
    kunci_dari_esp = request.headers.get("Authorization")
    if kunci_dari_esp != SECRET_KEY:
        print(f"GAGAL: Pengirim tidak sah! Kunci salah: {kunci_dari_esp}")
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    # --- 2. Validasi Isi Data ---
    try:
        data = request.json # Ambil data JSON dari ESP32
        
        # Cek apakah data penting ada?
        if 'tds_ppm' not in data or 'kekeruhan_ntu' not in data:
            raise ValueError("Data tidak lengkap, TDS atau Kekeruhan hilang.")
            
        # Cek apakah datanya masuk akal?
        if not (0 < data['tds_ppm'] < 2000):
            raise ValueError(f"Data TDS tidak masuk akal: {data['tds_ppm']}")

        print(f"DATA VALID DITERIMA: {data}")

        # --- 3. Proses & Kirim ke Elastic ---
        # Tambahkan timestamp server (lebih akurat daripada timestamp ESP32)
        data['@timestamp'] = datetime.now(timezone.utc)
        
        # Kirim ke Elasticsearch
        es.index(index=NAMA_INDEX, document=data)
        
        return jsonify({"status": "sukses", "message": "Data diterima"}), 201

    except Exception as e:
        print(f"GAGAL: Format data salah atau error. Detail: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400

# Jalankan server Flask di port 5000
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)