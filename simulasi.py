# =================================================================
# SCRIPT DUMMY (VERSI 2 - HISTORIS / RENTANG 4 HARI)
# Tujuan: Mengisi database dengan data historis yang "panjang"
# agar lolos validasi ML Job (Time range too short).
# =================================================================
import time
import random
from datetime import datetime, timezone, timedelta
from elasticsearch import Elasticsearch

# --- 1. KONFIGURASI ---
ELASTIC_HOST = "http://localhost:9200" # <-- PENTING: Sesuaikan ini jika Flask-mu pakai https
NAMA_INDEX = "depot_air_qc_data" 
JUMLAH_DATA = 100 # Kita akan buat 100 data point (100 jam)

# --- KONFIGURASI KONEKSI ELASTIC ---
# (Sesuaikan ini dengan setup Elastic-mu)
# Jika Elastic-mu (seperti di Flask) pakai HTTPS & Password, pakai ini:
ES_HOST_URL = "https://localhost:9200"
ES_USER = "elastic"
ES_PASS = "3+xHEqNsZYJ*2CQoNAlG" # <-- Ganti passwordmu
CA_CERT_PATH = "http_ca.crt" # <-- Pastikan file ini ada

# ========================================

def kirim_data_dummy_historis():
    print("=" * 40)
    print(f"Mencoba terhubung ke Elasticsearch di {ES_HOST_URL}...")
    try:
        # Gunakan koneksi AMAN (HTTPS)
        es = Elasticsearch(
            [ES_HOST_URL],
            basic_auth=(ES_USER, ES_PASS),
            ca_certs=CA_CERT_PATH
        )
        if not es.ping():
            raise ValueError("Koneksi ditolak. Ping gagal.")
        print("KONEKSI BERHASIL!")
    except Exception as e:
        print(f"\n[!!! GAGAL KONEKSI !!!]")
        print("Pastikan Elastic-mu berjalan di Docker.")
        print("Pastikan user, pass, dan file http_ca.crt sudah benar.")
        print(f"Detail Error: {e}")
        return

    # --- 2. Inilah Triknya! (Membuat Rentang Waktu Palsu) ---
    print(f"Akan mengirim {JUMLAH_DATA} data (rentang waktu ~4 hari) ke '{NAMA_INDEX}'...")
    print("=" * 40)
    
    # Kita mulai dari 100 jam yang lalu
    waktu_sekarang = datetime.now(timezone.utc)
    waktu_mulai = waktu_sekarang - timedelta(hours=JUMLAH_DATA)

    try:
        for i in range(JUMLAH_DATA):
            # Buat data palsu (Simulasi filter sehat)
            data_tds = random.uniform(5.0, 15.0)       
            data_kekeruhan = random.uniform(0.1, 0.8)  
            
            # --- 3. Sengaja Buat ANOMALI (Data Jelek) ---
            # Setiap 25 data (tiap 25 jam), buat 1 data anomali
            if i % 25 == 0:
                print(f"!!! MEMASUKKAN ANOMALI (Data Latihan) !!!")
                data_tds = random.uniform(50.0, 60.0) # TDS tiba-tiba tinggi
                data_kekeruhan = random.uniform(5.0, 8.0) # Kekeruhan tinggi
            # -----------------------------------------------

            # Buat stempel waktu palsu, maju 1 jam setiap data
            waktu_data = waktu_mulai + timedelta(hours=i)

            # [PENTING] Pastikan field ini SAMA PERSIS dengan MAPPING-mu
            doc = {
                'depot_id': 'D001_HISTORIS',
                '@timestamp': waktu_data, # <-- INI KUNCINYA
                'tds_ppm': round(data_tds, 2),
                'kekeruhan_ntu': round(data_kekeruhan, 2),
                'suhu_celsius': random.uniform(25.0, 28.0)
            }

            # Kirim langsung ke Elastic (bukan lewat Flask)
            # Ini lebih cepat untuk mengisi data latihan
            es.index(index=NAMA_INDEX, document=doc)
            print(f"Data ke-{i+1} terkirim: TDS={doc['tds_ppm']} ppm (@ {waktu_data.isoformat()})")
            
    except Exception as e:
        print(f"\n[!!! ERROR SAAT MENGIRIM DATA !!!]\n{e}")

    print("=" * 40)
    print(f"PENGIRIMAN DATA (RENTANG 4 HARI) SELESAI.")
    print("SEKARANG, buka Kibana dan buat ulang ML Job-mu!")
    print("=" * 40)

if __name__ == "__main__":
    kirim_data_dummy_historis()