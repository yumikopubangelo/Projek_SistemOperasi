# load_test.py
import requests
import threading
import time

def send_request(thread_id):
    data = {"tds_ppm": 75, "kekeruhan_ntu": 1.2, "suhu_celsius": 28}
    headers = {"Authorization": "AAEAAWVsYXN0aWMva5liYW5hL2Vucm9sbC1wcm9jZXNzLXRva2VuLTE3NjE4NzM2OTgzNjY6bTJVX0R5eERST3VxUFpPOWotY2lHZQ"}
    
    start = time.time()
    response = requests.post("http://localhost:5000/sensor", json=data, headers=headers)
    duration = time.time() - start
    
    print(f"Thread {thread_id}: {response.status_code} in {duration:.3f}s")

# Test dengan 20 concurrent requests
threads = []
for i in range(20):
    t = threading.Thread(target=send_request, args=(i,))
    threads.append(t)
    t.start()

for t in threads:
    t.join()