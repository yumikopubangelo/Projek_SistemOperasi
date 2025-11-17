from elasticsearch import Elasticsearch
import os

ELASTIC_HOST = "https://localhost:9200"
ELASTIC_USER = "elastic"
ELASTIC_PASS = "3+xHEqNsZYJ*2CQoNAlG"

# Try with absolute path
cert_path = os.path.join(os.getcwd(), "http_ca.crt")
print(f"Testing with certificate: {cert_path}")
print(f"File exists: {os.path.exists(cert_path)}")

# Test 1: Without verification
print("\n[TEST 1] Without SSL verification...")
try:
    es1 = Elasticsearch(
        [ELASTIC_HOST],
        basic_auth=(ELASTIC_USER, ELASTIC_PASS),
        verify_certs=False,
        ssl_show_warn=False
    )
    print(f"✅ Connection successful: {es1.ping()}")
    print(f"   Cluster: {es1.info()['cluster_name']}")
except Exception as e:
    print(f"❌ Failed: {e}")

# Test 2: With certificate verification
print("\n[TEST 2] With SSL certificate verification...")
try:
    es2 = Elasticsearch(
        [ELASTIC_HOST],
        basic_auth=(ELASTIC_USER, ELASTIC_PASS),
        ca_certs=cert_path,
        verify_certs=True
    )
    print(f"✅ Connection successful: {es2.ping()}")
    print(f"   Cluster: {es2.info()['cluster_name']}")
except Exception as e:
    print(f"❌ Failed: {e}")
    print(f"   Certificate path: {cert_path}")
    print(f"   Error type: {type(e).__name__}")