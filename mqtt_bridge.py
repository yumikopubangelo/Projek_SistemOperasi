import paho.mqtt.client as mqtt
import requests
import json
import time

# --- KONFIGURASI ---
# 1. Broker Gratisan (Public)
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
# GANTI TOPIK INI AGAR UNIK! (Misal: namamu/depot/data)
MQTT_TOPIC = "vanguard/depot/sensor" 

# 2. Alamat Server Flask Utama Kamu (Lokal)
FLASK_URL = "http://localhost:5000/sensor"
SECRET_KEY = "AAEAAWVsYXN0aWMva5liYW5hL2Vucm9sbC1wcm9jZXNzLXRva2VuLTE3NjE4NzM2OTgzNjY6bTJVX0R5eERST3VxUFpPOWotY2lHZQ"

# --- FUNGSI SAAT TERHUBUNG ---
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"✅ Terhubung ke MQTT Broker! ({MQTT_BROKER})")
        # Subscribe ke topik
        client.subscribe(MQTT_TOPIC)
        print(f"👂 Mendengarkan topik: {MQTT_TOPIC}")
    else:
        print(f"❌ Gagal konek, kode: {rc}")

# --- FUNGSI SAAT ADA PESAN MASUK ---
def on_message(client, userdata, msg):
    try:
        print("\n[MQTT] 📩 Pesan diterima!")
        payload_str = msg.payload.decode()
        print(f"Isi: {payload_str}")
        
        # 1. Parsing JSON
        data_json = json.loads(payload_str)
        
        # 2. Teruskan ke Server Flask (HTTP POST)
        # Kita pura-pura jadi ESP32 yang kirim lewat HTTP
        headers = {"Authorization": SECRET_KEY, "Content-Type": "application/json"}
        
        print("[BRIDGE] 🚀 Meneruskan ke Flask...")
        response = requests.post(FLASK_URL, json=data_json, headers=headers)
        
        if response.status_code == 201:
            print("✅ Sukses disimpan di Elastic!")
        else:
            print(f"⚠️ Gagal di Flask: {response.status_code} - {response.text}")
            
    except Exception as e:
        print(f"❌ Error memproses data: {e}")

# --- MAIN LOOP ---
client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

print("Menghubungkan ke Broker...")
client.connect(MQTT_BROKER, MQTT_PORT, 60)

# Loop selamanya
client.loop_forever()
