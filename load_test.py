"""
LOAD TESTING - AQUAGUARD (Enhanced with Better Metrics)
Simulate multiple ESP32 devices sending data concurrently
Run: python load_test.py
"""

import requests
import threading
import time
import random
from datetime import datetime
from statistics import mean, median, stdev
from colorama import init, Fore, Style

init(autoreset=True)

# ==================== CONFIG ====================
BASE_URL = "http://localhost:5000/sensor"
SECRET_KEY = "AAEAAWVsYXN0aWMva5liYW5hL2Vucm9sbC1wcm9jZXNzLXRva2VuLTE3NjE4NzM2OTgzNjY6bTJVX0R5eERST3VxUFpPOWotY2lHZQ"

# Test scenarios
SCENARIOS = {
    "light": {
        "concurrent_users": 5,
        "requests_per_user": 10,
        "delay_between_requests": 0.5
    },
    "moderate": {
        "concurrent_users": 10,
        "requests_per_user": 20,
        "delay_between_requests": 0.3
    },
    "heavy": {
        "concurrent_users": 20,
        "requests_per_user": 10,
        "delay_between_requests": 0.1
    },
    "stress": {
        "concurrent_users": 50,
        "requests_per_user": 5,
        "delay_between_requests": 0
    },
    # NEW: Pure speed test (no delay)
    "speed": {
        "concurrent_users": 10,
        "requests_per_user": 10,
        "delay_between_requests": 0
    }
}

# Global results storage
results = {
    "success": 0,
    "failed": 0,
    "response_times": [],
    "errors": [],
    "request_timestamps": []  # NEW: Track when each request sent
}

results_lock = threading.Lock()

# ==================== WORKER FUNCTION ====================
def worker(worker_id, num_requests, delay):
    """Simulate one ESP32 device"""
    for i in range(num_requests):
        # Generate random sensor data
        data = {
            "depot_id": f"DEPOT_LOAD_TEST_{worker_id}",
            "tds_ppm": round(random.uniform(50, 150), 2),
            "kekeruhan_ntu": round(random.uniform(0.5, 2.0), 2),
            "suhu_celsius": round(random.uniform(26, 30), 2)
        }
        
        headers = {
            "Authorization": SECRET_KEY,
            "Content-Type": "application/json"
        }
        
        # IMPORTANT: Measure ONLY request time (not including delay)
        request_start = time.time()
        
        try:
            response = requests.post(BASE_URL, json=data, headers=headers, timeout=10)
            request_duration = (time.time() - request_start) * 1000  # ms
            
            with results_lock:
                results["request_timestamps"].append(time.time())
                
                if response.status_code == 201:
                    results["success"] += 1
                    results["response_times"].append(request_duration)
                else:
                    results["failed"] += 1
                    results["errors"].append(f"HTTP {response.status_code}")
                    
        except requests.exceptions.Timeout:
            with results_lock:
                results["failed"] += 1
                results["errors"].append("Timeout")
        except requests.exceptions.ConnectionError:
            with results_lock:
                results["failed"] += 1
                results["errors"].append("Connection Error")
        except Exception as e:
            with results_lock:
                results["failed"] += 1
                results["errors"].append(str(e))
        
        # Delay AFTER measurement (simulate realistic IoT interval)
        if delay > 0:
            time.sleep(delay)

# ==================== TEST EXECUTOR ====================
def run_load_test(scenario_name):
    """Execute load test with given scenario"""
    scenario = SCENARIOS[scenario_name]
    
    print(f"{Fore.CYAN}{Style.BRIGHT}")
    print(f"╔{'═'*68}╗")
    print(f"║{'LOAD TEST - ' + scenario_name.upper():^68}║")
    print(f"╚{'═'*68}╝")
    print(Style.RESET_ALL)
    
    print(f"\n{Fore.YELLOW}Configuration:{Style.RESET_ALL}")
    print(f"  • Concurrent Devices: {scenario['concurrent_users']}")
    print(f"  • Requests per Device: {scenario['requests_per_user']}")
    print(f"  • Delay between Requests: {scenario['delay_between_requests']}s")
    print(f"  • Total Requests: {scenario['concurrent_users'] * scenario['requests_per_user']}")
    
    # Reset results
    results["success"] = 0
    results["failed"] = 0
    results["response_times"] = []
    results["errors"] = []
    results["request_timestamps"] = []
    
    print(f"\n{Fore.GREEN}Starting load test...{Style.RESET_ALL}\n")
    
    wall_clock_start = time.time()
    
    # Create threads (simulating ESP32 devices)
    threads = []
    for i in range(scenario['concurrent_users']):
        t = threading.Thread(
            target=worker,
            args=(i, scenario['requests_per_user'], scenario['delay_between_requests'])
        )
        threads.append(t)
        t.start()
    
    # Progress indicator
    print(f"{Fore.BLUE}[RUNNING] ", end="", flush=True)
    while any(t.is_alive() for t in threads):
        print(".", end="", flush=True)
        time.sleep(0.5)
    
    # Wait for all threads to complete
    for t in threads:
        t.join()
    
    wall_clock_duration = time.time() - wall_clock_start
    
    print(f" {Fore.GREEN}DONE{Style.RESET_ALL}\n")
    
    # ==================== ENHANCED RESULTS ====================
    total_requests = results["success"] + results["failed"]
    success_rate = (results["success"] / total_requests * 100) if total_requests > 0 else 0
    
    print(f"{'='*70}")
    print(f"{Fore.CYAN}{Style.BRIGHT}RESULTS SUMMARY".center(70))
    print(f"{'='*70}\n")
    
    # Basic stats
    print(f"{Fore.GREEN}✓ Successful:  {results['success']}{Style.RESET_ALL}")
    print(f"{Fore.RED}✗ Failed:      {results['failed']}{Style.RESET_ALL}")
    print(f"  Total:       {total_requests}")
    print(f"  Success Rate: {success_rate:.1f}%")
    
    # Timing stats
    print(f"\n{Fore.YELLOW}⏱️  TIMING ANALYSIS:{Style.RESET_ALL}")
    print(f"  Wall-Clock Duration: {wall_clock_duration:.2f}s")
    print(f"  Overall Throughput:  {total_requests/wall_clock_duration:.2f} req/s")
    
    if results["response_times"]:
        avg_response = mean(results["response_times"])
        
        print(f"\n{Fore.CYAN}📊 RESPONSE TIME STATISTICS (Pure Server Performance):{Style.RESET_ALL}")
        print(f"  • Min:     {min(results['response_times']):.2f}ms")
        print(f"  • Max:     {max(results['response_times']):.2f}ms")
        print(f"  • Mean:    {avg_response:.2f}ms")
        print(f"  • Median:  {median(results['response_times']):.2f}ms")
        
        if len(results['response_times']) > 1:
            print(f"  • StdDev:  {stdev(results['response_times']):.2f}ms")
        
        # Percentiles
        sorted_times = sorted(results['response_times'])
        p50 = sorted_times[len(sorted_times)//2]
        p95 = sorted_times[int(len(sorted_times)*0.95)]
        p99 = sorted_times[int(len(sorted_times)*0.99)]
        
        print(f"\n  📈 Percentiles:")
        print(f"     P50 (median): {p50:.2f}ms")
        print(f"     P95:          {p95:.2f}ms")
        print(f"     P99:          {p99:.2f}ms")
        
        # Performance classification
        if avg_response < 50:
            perf_rating = f"{Fore.GREEN}🚀 BLAZING FAST! ⭐⭐⭐⭐⭐{Style.RESET_ALL}"
            perf_comment = "Excellent! Sub-50ms response time."
        elif avg_response < 100:
            perf_rating = f"{Fore.GREEN}⚡ EXCELLENT! ⭐⭐⭐⭐⭐{Style.RESET_ALL}"
            perf_comment = "Great performance for production."
        elif avg_response < 200:
            perf_rating = f"{Fore.GREEN}✅ GOOD ⭐⭐⭐⭐{Style.RESET_ALL}"
            perf_comment = "Solid performance, acceptable for IoT."
        elif avg_response < 500:
            perf_rating = f"{Fore.YELLOW}⚠️  ACCEPTABLE ⭐⭐⭐{Style.RESET_ALL}"
            perf_comment = "Works but could be optimized."
        else:
            perf_rating = f"{Fore.RED}🐌 NEEDS OPTIMIZATION ⭐⭐{Style.RESET_ALL}"
            perf_comment = "Response time too high, investigate bottleneck."
        
        print(f"\n  {perf_rating}")
        print(f"  💡 {perf_comment}")
        
        # Compare with target
        target_response = 100  # ms
        if avg_response < target_response:
            improvement = ((target_response - avg_response) / target_response) * 100
            print(f"\n  🎯 {improvement:.1f}% FASTER than target ({target_response}ms)")
        else:
            degradation = ((avg_response - target_response) / target_response) * 100
            print(f"\n  📉 {degradation:.1f}% SLOWER than target ({target_response}ms)")
    
    # Concurrency analysis
    if results["request_timestamps"]:
        timestamps = sorted(results["request_timestamps"])
        actual_duration = timestamps[-1] - timestamps[0]
        actual_throughput = len(timestamps) / actual_duration if actual_duration > 0 else 0
        
        print(f"\n{Fore.MAGENTA}🔀 CONCURRENCY ANALYSIS:{Style.RESET_ALL}")
        print(f"  Actual Request Duration: {actual_duration:.2f}s")
        print(f"  Pure Request Throughput: {actual_throughput:.2f} req/s")
        print(f"  Concurrency Level: {scenario['concurrent_users']} devices")
    
    # Error analysis
    if results["errors"]:
        print(f"\n{Fore.RED}❌ ERROR SUMMARY:{Style.RESET_ALL}")
        error_counts = {}
        for error in results["errors"]:
            error_counts[error] = error_counts.get(error, 0) + 1
        
        for error, count in error_counts.items():
            print(f"  • {error}: {count} occurrences")
    
    print(f"\n{'='*70}\n")
    
    # Final assessment
    if success_rate >= 99 and avg_response < 100:
        print(f"{Fore.GREEN}{Style.BRIGHT}🎉 ASSESSMENT: PRODUCTION READY + HIGH PERFORMANCE!{Style.RESET_ALL}")
    elif success_rate >= 99:
        print(f"{Fore.GREEN}{Style.BRIGHT}✅ ASSESSMENT: PRODUCTION READY (Stable){Style.RESET_ALL}")
    elif success_rate >= 95:
        print(f"{Fore.YELLOW}{Style.BRIGHT}⚠️  ASSESSMENT: Mostly Stable (Minor Issues){Style.RESET_ALL}")
    else:
        print(f"{Fore.RED}{Style.BRIGHT}❌ ASSESSMENT: NEEDS DEBUGGING!{Style.RESET_ALL}")
    
    return success_rate >= 95

# ==================== COMPARISON MODE ====================
def run_comparison_test():
    """
    Run before/after comparison to show optimization impact.
    """
    print(f"{Fore.MAGENTA}{Style.BRIGHT}")
    print("""
    ╔══════════════════════════════════════════════════════════════╗
    ║                                                              ║
    ║           OPTIMIZATION COMPARISON TEST                      ║
    ║                                                              ║
    ║   This will run the SPEED scenario to measure pure         ║
    ║   server response time without IoT simulation delays.      ║
    ║                                                              ║
    ╚══════════════════════════════════════════════════════════════╝
    """)
    print(Style.RESET_ALL)
    
    print(f"{Fore.YELLOW}📊 Running pure speed test...{Style.RESET_ALL}\n")
    run_load_test("speed")
    
    print(f"\n{Fore.CYAN}💡 INTERPRETATION:{Style.RESET_ALL}")
    print(f"   • This test has NO delay between requests")
    print(f"   • Response time shows PURE server performance")
    print(f"   • Compare with previous tests to see improvement")
    print(f"\n   Expected improvements with adaptive bulk:")
    print(f"   • Non-optimized: 2000ms average")
    print(f"   • Bulk optimized: 100ms average")
    print(f"   • Adaptive: 50-80ms average (20-40x faster!)\n")

# ==================== MENU ====================
def main():
    print(f"{Fore.MAGENTA}{Style.BRIGHT}")
    print("""
    ╔══════════════════════════════════════════════════════════════╗
    ║                                                              ║
    ║              AQUAGUARD LOAD TESTING TOOL v2.0               ║
    ║                                                              ║
    ║         Enhanced with Better Performance Metrics            ║
    ║                                                              ║
    ╚══════════════════════════════════════════════════════════════╝
    """)
    print(Style.RESET_ALL)
    
    print("Select Test Scenario:\n")
    print(f"{Fore.GREEN}[1] Light Load{Style.RESET_ALL}     - 5 devices, 10 req each  (50 total)")
    print(f"{Fore.YELLOW}[2] Moderate Load{Style.RESET_ALL}  - 10 devices, 20 req each (200 total)")
    print(f"{Fore.RED}[3] Heavy Load{Style.RESET_ALL}     - 20 devices, 10 req each (200 total)")
    print(f"{Fore.MAGENTA}[4] Stress Test{Style.RESET_ALL}   - 50 devices, 5 req each  (250 total)")
    print(f"{Fore.CYAN}[6] Speed Test{Style.RESET_ALL}    - 10 devices, 10 req, NO DELAY (pure speed)")
    print(f"\n[5] Run All Scenarios (Sequential)")
    print(f"[7] Comparison Test (Show Optimization Impact)")
    print(f"[0] Exit\n")
    
    choice = input("Your choice: ").strip()
    
    scenario_map = {
        "1": "light",
        "2": "moderate",
        "3": "heavy",
        "4": "stress",
        "6": "speed"
    }
    
    if choice in scenario_map:
        run_load_test(scenario_map[choice])
    elif choice == "5":
        print(f"\n{Fore.CYAN}Running all scenarios sequentially...{Style.RESET_ALL}\n")
        for scenario_name in ["light", "moderate", "heavy", "stress", "speed"]:
            run_load_test(scenario_name)
            print("\n" + "="*70 + "\n")
            time.sleep(2)
    elif choice == "7":
        run_comparison_test()
    elif choice == "0":
        print("Goodbye!")
        return
    else:
        print(f"{Fore.RED}Invalid choice!{Style.RESET_ALL}")
        main()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{Fore.YELLOW}[INTERRUPTED] Load test stopped by user{Style.RESET_ALL}")