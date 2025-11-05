import requests
import json
import time

# --- KONFIGURASI SIMULATOR ---

# 1. GANTI DENGAN URL NGROK ANDA! (dapatkan dari terminal Ngrok)
NGROK_URL = "https://hallucinative-emma-astronautically.ngrok-free.dev"  # Contoh, ganti ini

# 2. Kunci rahasia ini HARUS SAMA dengan yang di server Flask
SECRET_KEY = "AAEAAWVsYXN0aWMva5liYW5hL2Vucm9sbC1wcm9jZXNzLXRva2VuLTE3NjE4NzM2OTgzNjY6bTJVX0R5eERST3VxUFpPOWotY2lHZQ"
# ---------------------------------

# Ini adalah data sensor palsu yang ingin kita kirim
data_sensor_palsu = {
    "device_id": "simulator_01",
    "tds_ppm": 140.2,
    "kekeruhan_ntu": 4.2
}

# Tentukan URL lengkap + endpoint
url_tujuan = NGROK_URL + "/sensor"

# Siapkan headers, terutama 'Authorization'
headers = {
    "Authorization": SECRET_KEY,
    "Content-Type": "application/json" 
}

print(f"Mengirim data simulasi ke: {url_tujuan}")
print(f"Data: {data_sensor_palsu}")

try:
    # Kirim request POST dengan data JSON dan headers
    # Kita menggunakan json=data_sensor_palsu agar requests otomatis 
    # mengubah dict Python menjadi string JSON dan mengatur header Content-Type
    # Tapi karena kita butuh header Authorization, kita atur manual:
    
    respons = requests.post(
        url_tujuan, 
        data=json.dumps(data_sensor_palsu), # Ubah dict ke string JSON
        headers=headers,
        timeout=10 # Batas waktu 10 detik
    )
    
    # Tampilkan respons dari server Flask Anda
    print("\n--- HASIL ---")
    print(f"Status Code: {respons.status_code}")
    print(f"Respons Server: {respons.json()}") # Tampilkan balasan JSON dari Flask

except requests.exceptions.ConnectionError:
    print("\nGAGAL: Tidak bisa terhubung ke URL Ngrok.")
    print("Pastikan Ngrok berjalan dan URL-nya sudah benar.")
except Exception as e:
    print(f"\nGAGAL: Terjadi error. Detail: {e}")