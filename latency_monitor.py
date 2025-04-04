# Chạy trên h_client
# latency_monitor.py
import time
import requests
import sys
import subprocess # Để chạy lệnh ping
import re # Để phân tích output ping
import os

RYU_API_ENDPOINT = 'http://127.0.0.1:8081/telemetry/latency' # API khác cho latency
SERVERS_TO_PING = ['10.0.0.1', '10.0.0.2', '10.0.0.3']
PING_COUNT = 1 # Số lượng ping mỗi lần đo
INTERVAL = 3 # Giây

def get_latency(target_ip):
    """Chạy ping và trả về độ trễ trung bình (ms) hoặc -1 nếu lỗi."""
    command = ['ping', '-c', str(PING_COUNT), target_ip]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=2)
        if result.returncode == 0:
            # Phân tích output để tìm dòng 'rtt min/avg/max/mdev'
            match = re.search(r'rtt min/avg/max/mdev = [\d.]+/([\d.]+)/[\d.]+/[\d.]+ ms', result.stdout)
            if match:
                return float(match.group(1)) # Lấy giá trị avg
            else: # Thử phân tích output khác nếu format khác
                match_alt = re.search(r'round-trip min/avg/max/stddev = [\d.]+/([\d.]+)/[\d.]+/[\d.]+ ms', result.stdout) # Format trên một số hệ thống
                if match_alt:
                    return float(match_alt.group(1))
                print(f"[Latency Monitor] Could not parse ping output for {target_ip}:\n{result.stdout}")
                return -1
        else:
            # print(f"[Latency Monitor] Ping to {target_ip} failed. Return code: {result.returncode}")
            # print(f"Stderr: {result.stderr}")
            return -1 # Ping thất bại
    except subprocess.TimeoutExpired:
        # print(f"[Latency Monitor] Ping to {target_ip} timed out.")
        return -1
    except Exception as e:
        print(f"[Latency Monitor] Error running ping to {target_ip}: {e}")
        return -1


if __name__ == "__main__":
    hostname = "h_client" # Hoặc lấy từ argument nếu cần
    pid = os.getpid()
    print(f"[{hostname}-Latency Monitor PID: {pid}] Starting...")

    while True:
        latencies = {}
        for server_ip in SERVERS_TO_PING:
            latency = get_latency(server_ip)
            latencies[server_ip] = latency
            print(f"[Latency Monitor] Latency to {server_ip}: {latency} ms")
            time.sleep(0.1) # Chờ chút giữa các lần ping

        payload = {'client': hostname, 'latencies': latencies}
        try:
            response = requests.post(RYU_API_ENDPOINT, json=payload, timeout=1)
            # print(f"[Latency Monitor] Sent {payload}, Status: {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"[Latency Monitor] Error sending data to Ryu: {e}")
            pass
        time.sleep(INTERVAL)