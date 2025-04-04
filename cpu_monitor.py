# Chạy trên h1, h2, h3 
# cpu_monitor.py
import time
import requests # Để gửi HTTP request
import sys
import psutil 
import os

RYU_API_ENDPOINT = 'http://127.0.0.1:8081/telemetry/cpu' # Địa chỉ API của Ryu (sẽ tạo sau)
INTERVAL = 3  # Giây

def get_cpu_usage():
    """Lấy phần trăm sử dụng CPU."""
    
    # Hoặc dùng lệnh top/vmstat nếu không có psutil
    # import subprocess
    # try:
    #     # Lấy dòng thứ 3 của vmstat 1 2 (chạy 1 lần sau 1 giây)
    #     output = subprocess.check_output("vmstat 1 2 | tail -n 1", shell=True).decode('utf-8')
    #     parts = output.split()
    #     idle_cpu = int(parts[14]) # Cột % idle
    #     return 100 - idle_cpu
    # except Exception as e:
    #     print(f"Error getting CPU via vmstat: {e}")
    #     return -1 # Giá trị lỗi
    try:
        return psutil.cpu_percent(interval=None) # Lấy ngay lập tức
    except Exception as e:
        print(f"Error getting CPU via psutil: {e}")
        return -1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python cpu_monitor.py <hostname>")
        sys.exit(1)
    hostname = sys.argv[1]
    pid = os.getpid()
    print(f"[{hostname}-CPU Monitor PID: {pid}] Starting...")

    while True:
        try:
            cpu_usage = get_cpu_usage()
            if cpu_usage != -1:
                payload = {'hostname': hostname, 'cpu_usage': cpu_usage}
                print(f"[{hostname}-CPU Monitor] Attempting to send: {payload}")
                try:
                    response = requests.post(RYU_API_ENDPOINT, json=payload, timeout=1)
                    print(f"[{hostname}-CPU Monitor] Send Status: {response.status_code}")
                except requests.exceptions.RequestException as e:
                    print(f"[{hostname}-CPU Monitor] Error sending data to Ryu: {e}")
                    pass # Bỏ qua lỗi nếu Ryu chưa sẵn sàng hoặc có vấn đề mạng
            time.sleep(INTERVAL)
        except KeyboardInterrupt:
            print(f"[{hostname}-CPU Monitor] Stopping...")
            break
        except Exception as e:
            print(f"[{hostname}-CPU Monitor] An error occurred: {e}")
            time.sleep(INTERVAL) # Chờ trước khi thử lại