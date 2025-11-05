import time
import random
from datetime import datetime, timezone
from elasticsearch import Elasticsearch

# --- 1. KONFIGURASI ---
ELASTIC_HOST = "https://localhost:9200"
ELASTIC_USER = "elastic"
ELASTIC_PASS = "3+xHEqNsZYJ*2CQoNAlG"  # Ganti sesuai password kamu
NAMA_INDEX = "depot_air_qc_data"
JUMLAH_DATA = 100
JEDA_WAKTU = 0.2
# -----------------------

def kirim_data_dummy():
    print("=" * 40)
    print(f"Mencoba terhubung ke Elasticsearch di {ELASTIC_HOST}...")
    try:
        es = Elasticsearch(
            ELASTIC_HOST,
            basic_auth=(ELASTIC_USER, ELASTIC_PASS),
            verify_certs=False  # kalau pakai HTTPS self-signed
        )
        if not es.ping():
            raise ValueError("Ping gagal. Elasticsearch tidak merespon.")
        print("KONEKSI BERHASIL!")
    except Exception as e:
        print("\n[!!! GAGAL KONEKSI !!!]")
        print("Pastikan Elasticsearch container sedang RUNNING.")
        print(f"Detail Error: {e}")
        return

    print(f"Akan mengirim {JUMLAH_DATA} data dummy ke index '{NAMA_INDEX}'...")
    print("=" * 40)

    for i in range(JUMLAH_DATA):
        try:
            doc = {
                'depot_id': 'D001',
                '@timestamp': datetime.now(timezone.utc),
                'tds_ppm': round(random.uniform(5.0, 15.0), 2),
                'kekeruhan_ntu': round(random.uniform(0.1, 0.8), 2),
                'suhu_c': round(random.uniform(25.0, 28.0), 2)
            }

            es.index(index=NAMA_INDEX, document=doc)
            print(f"Data ke-{i+1} terkirim: {doc}")
            time.sleep(JEDA_WAKTU)

        except Exception as e:
            print(f"[!] Gagal kirim data ke-{i+1}: {e}")

    print("=" * 40)
    print("PENGIRIMAN SELESAI ✅")
    print("Langkah berikut:")
    print("1. Buka Kibana (http://localhost:5601)")
    print(f"2. Buat Data View untuk index: {NAMA_INDEX}*")
    print("3. Lihat data di Discover dan uji Machine Learning Anomaly Detection!")
    print("=" * 40)

if __name__ == "__main__":
    kirim_data_dummy()
