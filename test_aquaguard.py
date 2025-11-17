"""
AUTOMATED TESTING SUITE - AQUAGUARD
Run: python test_aquaguard.py
"""

import requests
import time
import json
from datetime import datetime
from colorama import init, Fore, Style

# Initialize colorama for colored output
init(autoreset=True)

# ==================== CONFIGURATION ====================
BASE_URL = "http://localhost:5000"
SECRET_KEY = "AAEAAWVsYXN0aWMva5liYW5hL2Vucm9sbC1wcm9jZXNzLXRva2VuLTE3NjE4NzM2OTgzNjY6bTJVX0R5eERST3VxUFpPOWotY2lHZQ"
TIMEOUT = 10

# Test counters
tests_run = 0
tests_passed = 0
tests_failed = 0

# ==================== UTILITY FUNCTIONS ====================
def print_header(title):
    """Print section header"""
    print(f"\n{'='*70}")
    print(f"{Fore.CYAN}{Style.BRIGHT}{title.center(70)}")
    print(f"{'='*70}\n")

def print_test(test_name):
    """Print test name"""
    print(f"{Fore.YELLOW}[TEST] {test_name}...", end=" ")

def print_pass(message=""):
    """Print pass result"""
    global tests_passed
    tests_passed += 1
    print(f"{Fore.GREEN}✓ PASS{Style.RESET_ALL} {message}")

def print_fail(message=""):
    """Print fail result"""
    global tests_failed
    tests_failed += 1
    print(f"{Fore.RED}✗ FAIL{Style.RESET_ALL} {message}")

def print_info(message):
    """Print info message"""
    print(f"{Fore.BLUE}[INFO] {message}{Style.RESET_ALL}")

def run_test(test_func):
    """Decorator to track test execution"""
    global tests_run
    tests_run += 1
    try:
        test_func()
    except Exception as e:
        print_fail(f"Exception: {str(e)}")

# ==================== TEST CASES ====================

def test_server_running():
    """Test 1: Server is running and accessible"""
    print_test("Server Running Check")
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=TIMEOUT)
        if response.status_code == 200:
            print_pass(f"Server accessible at {BASE_URL}")
        else:
            print_fail(f"Server returned status {response.status_code}")
    except requests.exceptions.ConnectionError:
        print_fail("Cannot connect to server. Is Flask running?")
    except Exception as e:
        print_fail(f"Error: {str(e)}")

def test_health_endpoint():
    """Test 2: Health endpoint returns correct structure"""
    print_test("Health Endpoint Structure")
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=TIMEOUT)
        data = response.json()
        
        required_fields = ['status', 'elasticsearch', 'total_documents']
        missing_fields = [f for f in required_fields if f not in data]
        
        if not missing_fields and data['status'] == 'healthy':
            print_pass(f"Health check OK. Total docs: {data.get('total_documents', 0)}")
        else:
            print_fail(f"Missing fields: {missing_fields}")
    except Exception as e:
        print_fail(f"Error: {str(e)}")

def test_send_valid_data():
    """Test 3: Send valid sensor data"""
    print_test("Send Valid Data")
    
    data = {
        "depot_id": "TEST_DEPOT_01",
        "tds_ppm": 75.5,
        "kekeruhan_ntu": 1.2,
        "suhu_celsius": 28.3
    }
    
    headers = {
        "Authorization": SECRET_KEY,
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/sensor", json=data, headers=headers, timeout=TIMEOUT)
        
        if response.status_code == 201:
            print_pass("Data accepted. Status: 201 Created")
        else:
            print_fail(f"Status: {response.status_code}, Response: {response.text}")
    except Exception as e:
        print_fail(f"Error: {str(e)}")

def test_unauthorized_access():
    """Test 4: Reject unauthorized requests"""
    print_test("Unauthorized Access Rejection")
    
    data = {
        "depot_id": "HACKER",
        "tds_ppm": 100,
        "kekeruhan_ntu": 1.0,
        "suhu_celsius": 30
    }
    
    headers = {
        "Authorization": "WRONG_KEY",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/sensor", json=data, headers=headers, timeout=TIMEOUT)
        
        if response.status_code == 401:
            print_pass("Unauthorized request rejected. Status: 401")
        else:
            print_fail(f"Expected 401, got {response.status_code}")
    except Exception as e:
        print_fail(f"Error: {str(e)}")

def test_missing_field():
    """Test 5: Reject data with missing required field"""
    print_test("Missing Field Validation")
    
    data = {
        "depot_id": "TEST_DEPOT_02",
        "tds_ppm": 80.0
        # Missing: kekeruhan_ntu and suhu_celsius
    }
    
    headers = {
        "Authorization": SECRET_KEY,
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/sensor", json=data, headers=headers, timeout=TIMEOUT)
        
        if response.status_code == 400:
            print_pass("Missing field rejected. Status: 400")
        else:
            print_fail(f"Expected 400, got {response.status_code}")
    except Exception as e:
        print_fail(f"Error: {str(e)}")

def test_out_of_range_tds():
    """Test 6: Reject TDS value out of range"""
    print_test("TDS Out of Range Validation")
    
    data = {
        "depot_id": "TEST_DEPOT_03",
        "tds_ppm": 3000,  # Out of range (max 2000)
        "kekeruhan_ntu": 1.0,
        "suhu_celsius": 28.0
    }
    
    headers = {
        "Authorization": SECRET_KEY,
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/sensor", json=data, headers=headers, timeout=TIMEOUT)
        
        if response.status_code == 400:
            print_pass("Out of range rejected. Status: 400")
        else:
            print_fail(f"Expected 400, got {response.status_code}")
    except Exception as e:
        print_fail(f"Error: {str(e)}")

def test_data_terbaru_endpoint():
    """Test 7: Fetch latest data"""
    print_test("Fetch Latest Data")
    
    try:
        response = requests.get(f"{BASE_URL}/data/terbaru", timeout=TIMEOUT)
        
        if response.status_code == 200:
            data = response.json()
            if data['status'] == 'sukses' and 'data' in data:
                sensor_data = data['data']
                print_pass(f"Got latest data: TDS={sensor_data.get('tds_ppm', 'N/A')}")
            else:
                print_fail("Invalid response structure")
        elif response.status_code == 404:
            print_info("No data in database yet (404) - This is OK for first run")
            print_pass("Endpoint works (no data yet)")
        else:
            print_fail(f"Status: {response.status_code}")
    except Exception as e:
        print_fail(f"Error: {str(e)}")

def test_data_historis_endpoint():
    """Test 8: Fetch historical data"""
    print_test("Fetch Historical Data (size=10)")
    
    try:
        response = requests.get(f"{BASE_URL}/data/historis?size=10", timeout=TIMEOUT)
        data = response.json()
        
        if response.status_code == 200 and data['status'] == 'sukses':
            count = len(data['data'])
            print_pass(f"Got {count} historical records")
        else:
            print_fail(f"Status: {response.status_code}")
    except Exception as e:
        print_fail(f"Error: {str(e)}")

def test_ai_status_endpoint():
    """Test 9: Check AI status endpoint"""
    print_test("AI Status Check")
    
    try:
        response = requests.get(f"{BASE_URL}/ai/status", timeout=TIMEOUT)
        
        if response.status_code == 200:
            data = response.json()
            status = data.get('status', 'UNKNOWN')
            message = data.get('message', '')
            
            if status in ['AMAN', 'BAHAYA', 'PENDING']:
                print_pass(f"AI Status: {status} - {message}")
            else:
                print_fail(f"Unknown status: {status}")
        else:
            print_fail(f"Status: {response.status_code}")
    except Exception as e:
        print_fail(f"Error: {str(e)}")

def test_concurrent_requests():
    """Test 10: Handle concurrent requests"""
    print_test("Concurrent Requests (10 simultaneous)")
    
    import threading
    
    results = []
    
    def send_request(thread_id):
        data = {
            "depot_id": f"TEST_CONCURRENT_{thread_id}",
            "tds_ppm": 75.0 + thread_id,
            "kekeruhan_ntu": 1.0,
            "suhu_celsius": 28.0
        }
        headers = {
            "Authorization": SECRET_KEY,
            "Content-Type": "application/json"
        }
        
        try:
            start_time = time.time()
            response = requests.post(f"{BASE_URL}/sensor", json=data, headers=headers, timeout=TIMEOUT)
            duration = time.time() - start_time
            results.append({
                'thread_id': thread_id,
                'status': response.status_code,
                'duration': duration
            })
        except Exception as e:
            results.append({
                'thread_id': thread_id,
                'status': 'ERROR',
                'error': str(e)
            })
    
    threads = []
    for i in range(10):
        t = threading.Thread(target=send_request, args=(i,))
        threads.append(t)
        t.start()
    
    for t in threads:
        t.join()
    
    success_count = sum(1 for r in results if r['status'] == 201)
    avg_duration = sum(r['duration'] for r in results if 'duration' in r) / len(results)
    
    if success_count == 10:
        print_pass(f"All 10 requests successful. Avg time: {avg_duration:.3f}s")
    else:
        print_fail(f"Only {success_count}/10 requests successful")

def test_response_time():
    """Test 11: Check response time performance"""
    print_test("Response Time Performance")
    
    data = {
        "depot_id": "TEST_PERFORMANCE",
        "tds_ppm": 75.0,
        "kekeruhan_ntu": 1.2,
        "suhu_celsius": 28.5
    }
    
    headers = {
        "Authorization": SECRET_KEY,
        "Content-Type": "application/json"
    }
    
    try:
        start_time = time.time()
        response = requests.post(f"{BASE_URL}/sensor", json=data, headers=headers, timeout=TIMEOUT)
        duration = (time.time() - start_time) * 1000  # Convert to ms
        
        if response.status_code == 201:
            if duration < 200:
                print_pass(f"Response time: {duration:.1f}ms (Excellent!)")
            elif duration < 500:
                print_pass(f"Response time: {duration:.1f}ms (Good)")
            else:
                print_info(f"Response time: {duration:.1f}ms (Acceptable but slow)")
        else:
            print_fail(f"Request failed with status {response.status_code}")
    except Exception as e:
        print_fail(f"Error: {str(e)}")

def test_dashboard_accessible():
    """Test 12: Dashboard HTML is accessible"""
    print_test("Dashboard Accessibility")
    
    try:
        response = requests.get(f"{BASE_URL}/", timeout=TIMEOUT)
        
        if response.status_code == 200:
            html_content = response.text
            
            # Check if HTML contains key elements
            checks = [
                ('AquaGuard' in html_content, "Title present"),
                ('chart' in html_content.lower(), "Chart.js present"),
                ('tds' in html_content.lower(), "TDS element present"),
                ('kekeruhan' in html_content.lower(), "Kekeruhan element present")
            ]
            
            passed_checks = sum(1 for check, _ in checks if check)
            
            if passed_checks == len(checks):
                print_pass(f"Dashboard HTML valid ({passed_checks}/{len(checks)} checks)")
            else:
                print_fail(f"Some checks failed ({passed_checks}/{len(checks)})")
        else:
            print_fail(f"Status: {response.status_code}")
    except Exception as e:
        print_fail(f"Error: {str(e)}")

# ==================== TEST EXECUTION ====================

def run_all_tests():
    """Execute all tests"""
    print(f"{Fore.MAGENTA}{Style.BRIGHT}")
    print("""
    ╔══════════════════════════════════════════════════════════════╗
    ║                                                              ║
    ║              AQUAGUARD AUTOMATED TEST SUITE                 ║
    ║                                                              ║
    ║              Testing System Functionality                   ║
    ║                                                              ║
    ╚══════════════════════════════════════════════════════════════╝
    """)
    print(Style.RESET_ALL)
    
    start_time = time.time()
    
    # Phase 1: Basic Connectivity
    print_header("PHASE 1: BASIC CONNECTIVITY")
    run_test(test_server_running)
    run_test(test_health_endpoint)
    
    # Phase 2: Data Ingestion & Validation
    print_header("PHASE 2: DATA INGESTION & VALIDATION")
    run_test(test_send_valid_data)
    run_test(test_unauthorized_access)
    run_test(test_missing_field)
    run_test(test_out_of_range_tds)
    
    # Phase 3: Data Retrieval
    print_header("PHASE 3: DATA RETRIEVAL")
    run_test(test_data_terbaru_endpoint)
    run_test(test_data_historis_endpoint)
    run_test(test_ai_status_endpoint)
    
    # Phase 4: Performance & Stress
    print_header("PHASE 4: PERFORMANCE & STRESS")
    run_test(test_concurrent_requests)
    run_test(test_response_time)
    
    # Phase 5: Dashboard
    print_header("PHASE 5: DASHBOARD")
    run_test(test_dashboard_accessible)
    
    # Summary
    duration = time.time() - start_time
    
    print(f"\n{'='*70}")
    print(f"{Fore.CYAN}{Style.BRIGHT}TEST SUMMARY".center(70))
    print(f"{'='*70}\n")
    
    print(f"Total Tests Run:    {tests_run}")
    print(f"{Fore.GREEN}Tests Passed:       {tests_passed} ({tests_passed/tests_run*100:.1f}%){Style.RESET_ALL}")
    print(f"{Fore.RED}Tests Failed:       {tests_failed} ({tests_failed/tests_run*100:.1f}%){Style.RESET_ALL}")
    print(f"Execution Time:     {duration:.2f} seconds")
    
    print(f"\n{'='*70}\n")
    
    if tests_failed == 0:
        print(f"{Fore.GREEN}{Style.BRIGHT}🎉 ALL TESTS PASSED! System is ready for demo!{Style.RESET_ALL}")
        return 0
    else:
        print(f"{Fore.YELLOW}{Style.BRIGHT}⚠️ Some tests failed. Please check and fix issues.{Style.RESET_ALL}")
        return 1

# ==================== MAIN ====================

if __name__ == "__main__":
    try:
        exit_code = run_all_tests()
        exit(exit_code)
    except KeyboardInterrupt:
        print(f"\n\n{Fore.YELLOW}[INTERRUPTED] Testing stopped by user{Style.RESET_ALL}")
        exit(1)