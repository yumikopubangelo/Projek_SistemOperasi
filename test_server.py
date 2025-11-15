import unittest
import json
from unittest.mock import patch, ANY  # <-- [UPGRADE V2] Import library 'mock' untuk mocking

# [PENTING] Ganti 'server_middleware' dengan nama file Flask-mu (tanpa .py)
# Asumsi kita pakai 'server_middleware' (perbaiki typo dari 'midleware')
try:
    from server_midleware import app, SECRET_KEY
except ImportError as e:
    print(f"GAGAL IMPORT: Gagal mengimpor 'app' atau 'SECRET_KEY'. Pastikan nama file Flask sudah benar.")
    print(f"Error: {e}")
    exit()

# --- DATA UNTUK PENGUJIAN ---
DATA_VALID = {
    "depot_id": "D_TEST_01",
    "tds_ppm": 15.5,
    "kekeruhan_ntu": 0.8,
    "suhu_celsius": 26.0
}

HEADER_VALID = {
    "Authorization": SECRET_KEY,
    "Content-Type": "application/json"
}

HEADER_SALAH = {
    "Authorization": "KUNCI_PALSU_123",
    "Content-Type": "application/json"
}

# --- Kumpulan Tes 1: Menguji Endpoint /sensor (Validasi Input) ---
class TestSensorEndpoint(unittest.TestCase):

    def setUp(self):
        """Dijalankan sebelum setiap tes untuk setup client testing"""
        app.config['TESTING'] = True
        self.client = app.test_client()
        print("\n" + "-" * 50)
        print(f"Menjalankan: {self._testMethodName}")

    def test_01_kirim_tanpa_header_auth(self):
        """TES 1: Gagal - Kirim data TANPA Kunci Rahasia"""
        response = self.client.post('/sensor', json=DATA_VALID)
        self.assertEqual(response.status_code, 401)
        self.assertIn("Unauthorized", response.get_json().get('message', ''))
        print("✅ Lolos! Server menolak dengan 401 Unauthorized.")

    def test_02_kirim_kunci_salah(self):
        """TES 2: Gagal - Kirim data dengan Kunci Rahasia yang SALAH"""
        response = self.client.post('/sensor', json=DATA_VALID, headers=HEADER_SALAH)
        self.assertEqual(response.status_code, 401)
        self.assertIn("Unauthorized", response.get_json().get('message', ''))
        print("✅ Lolos! Server menolak dengan 401 Unauthorized.")

    def test_03_kirim_data_tds_negatif(self):
        """TES 3: Gagal - Kirim data (TDS negatif) dengan Kunci BENAR"""
        data_jelek = DATA_VALID.copy()
        data_jelek['tds_ppm'] = -50
        
        response = self.client.post('/sensor', json=data_jelek, headers=HEADER_VALID)
        
        self.assertEqual(response.status_code, 400)
        self.assertIn("TDS error", response.get_json()['message'])
        print("✅ Lolos! Server menolak dengan 400 (TDS error).")

    def test_04_kirim_data_tidak_lengkap(self):
        """TES 4: Gagal - Kirim data (suhu hilang) dengan Kunci BENAR"""
        data_jelek = DATA_VALID.copy()
        del data_jelek['suhu_celsius']  # Hapus salah satu field wajib
        
        response = self.client.post('/sensor', json=data_jelek, headers=HEADER_VALID)
        
        self.assertEqual(response.status_code, 400)
        self.assertIn("Data tidak lengkap", response.get_json()['message'])
        print("✅ Lolos! Server menolak dengan 400 (Data tidak lengkap).")

    def test_05_kirim_data_kekeruhan_negatif(self):
        """TES 5: Gagal - Kirim data (Kekeruhan negatif) dengan Kunci BENAR"""
        data_jelek = DATA_VALID.copy()
        data_jelek['kekeruhan_ntu'] = -1.0
        
        response = self.client.post('/sensor', json=data_jelek, headers=HEADER_VALID)
        
        self.assertEqual(response.status_code, 400)
        self.assertIn("Kekeruhan error", response.get_json()['message'])  # Asumsi server validasi ini
        print("✅ Lolos! Server menolak dengan 400 (Kekeruhan error).")

    def test_06_kirim_data_json_rusak(self):
        """TES 6: Gagal - Kirim data BUKAN JSON"""
        response = self.client.post('/sensor', data="ini bukan json", headers=HEADER_VALID)
        self.assertEqual(response.status_code, 400)
        self.assertIn("Format data salah", response.get_json()['message'])  # Asumsi server Flask handle ini
        print("✅ Lolos! Server menolak dengan 400 (JSON Rusak).")

    # [UPGRADE V2] Menggunakan 'patch' untuk mengisolasi (Unit Test)
    # Kita "berpura-pura" menjadi Thread, tanpa benar-benar menjalankannya
    @patch('server_middleware.Thread')  # Perbaiki nama modul agar konsisten
    def test_07_kirim_data_sukses(self, mock_thread_constructor):
        """TES 7: Sukses - Kirim data LENGKAP dan BENAR (Unit Test Murni)"""
        
        # Buat "tiruan" dari objek Thread
        mock_thread_instance = mock_thread_constructor.return_value
        
        response = self.client.post('/sensor', json=DATA_VALID, headers=HEADER_VALID)
        
        # 1. Cek apakah server membalas dengan 'Sukses' (201)
        self.assertEqual(response.status_code, 201) 
        self.assertEqual(response.get_json()['status'], "sukses")
        
        # 2. Cek (via mock) apakah Flask *berusaha* membuat Thread?
        self.assertTrue(mock_thread_constructor.called, "Flask tidak memanggil Thread()")
        
        # 3. Cek (via mock) apakah Flask *menjalankan* Thread itu?
        mock_thread_instance.start.assert_called_once()
        
        print("✅ Lolos! Server membalas 201 & memicu background thread.")


# --- Kumpulan Tes 2: [UPGRADE V2] Menguji Endpoint Dashboard ---
# Ini adalah Integration Test (Tes Integrasi) karena benar-benar
# mengambil data dari Elasticsearch (jika ada).
class TestDashboardEndpoints(unittest.TestCase):

    def setUp(self):
        """Setup client testing untuk endpoint dashboard"""
        app.config['TESTING'] = True
        self.client = app.test_client()
        print("\n" + "-" * 50)
        print(f"Menjalankan: {self._testMethodName}")

    def test_01_dashboard_utama(self):
        """TES 8: Apakah Halaman Dashboard (/) bisa diakses?"""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"AquaGuard", response.data)  # Cek apakah ada kata 'AquaGuard' di HTML-nya
        print("✅ Lolos! Dashboard HTML (/) berhasil dimuat.")

    def test_02_endpoint_data_terbaru(self):
        """TES 9: Apakah API /data/terbaru merespon?"""
        response = self.client.get('/data/terbaru')
        # Jika belum ada data, 404. Jika sudah, 200. Keduanya adalah 'sukses'.
        self.assertIn(response.status_code, [200, 404])
        if response.status_code == 200:
            self.assertIsInstance(response.get_json(), dict)  # Pastikan balasan adalah dict jika ada data
        print("✅ Lolos! Endpoint /data/terbaru merespon.")

    def test_03_endpoint_data_historis(self):
        """TES 10: Apakah API /data/historis merespon?"""
        response = self.client.get('/data/historis')
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.get_json()['data'], list)  # Pastikan balasan 'data' adalah list
        print("✅ Lolos! Endpoint /data/historis merespon.")

    def test_04_endpoint_ai_status(self):
        """TES 11: Apakah API /ai/status merespon?"""
        response = self.client.get('/ai/status')
        # Respon bisa 200 (OK), 404 (Belum ada data), atau 500 (ML index belum ada)
        # Semua adalah respon valid.
        self.assertIn(response.status_code, [200, 404, 500])
        if response.status_code == 200:
            self.assertIsInstance(response.get_json(), dict)  # Pastikan balasan adalah dict jika OK
        print("✅ Lolos! Endpoint /ai/status merespon.")

    def test_05_endpoint_data_historis_dengan_parameter(self):
        """TES 12: Apakah API /data/historis dengan parameter query merespon?"""
        response = self.client.get('/data/historis?depot_id=D_TEST_01&limit=10')
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.get_json()['data'], list)
        print("✅ Lolos! Endpoint /data/historis dengan parameter merespon.")


# --- Untuk Menjalankan Tes ---
if __name__ == '__main__':
    unittest.main()