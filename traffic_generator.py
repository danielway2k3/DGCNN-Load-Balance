#!/usr/bin/env python
# traffic_generator.py
import subprocess
import time
import random
import sys
import os
import signal # Để xử lý tín hiệu dừng
import math

# --- Cấu hình ---
DEFAULT_TARGET = "10.0.0.100:8080" # IP ảo và Port của dịch vụ
WGET_TIMEOUT = 2 # Giây timeout cho mỗi request wget
WGET_TRIES = 1 # Số lần thử lại của wget

# Các chế độ Traffic và tham số của chúng
TRAFFIC_MODES = {
    "NORMAL": {
        "duration_range": (30, 60), # Thời gian chạy chế độ (giây)
        "delay_avg": 1.5,          # Thời gian nghỉ trung bình giữa các request (giây)
        "delay_variation": 0.8     # Độ biến thiên ngẫu nhiên của delay (+/-)
    },
    "SPIKE": {
        "duration_range": (5, 15),
        "delay_avg": 0.1,          # Delay rất thấp để tạo spike
        "delay_variation": 0.05
    },
    "LOW": {
        "duration_range": (20, 40),
        "delay_avg": 4.0,          # Delay cao cho giai đoạn ít traffic
        "delay_variation": 1.0
    },
    "RAMP_UP": {
        "duration_range": (15, 25),
        "start_delay": 3.0,        # Delay ban đầu (cao)
        "end_delay": 0.3           # Delay cuối cùng (thấp)
    },
     "RAMP_DOWN": {
        "duration_range": (15, 25),
        "start_delay": 0.3,        # Delay ban đầu (thấp)
        "end_delay": 3.0           # Delay cuối cùng (cao)
    }
}

# --- Biến toàn cục để xử lý dừng ---
running = True

def signal_handler(sig, frame):
    """Hàm xử lý tín hiệu dừng (Ctrl+C hoặc kill)."""
    global running
    print(f"\n[TrafficGen PID: {os.getpid()}] Signal {sig} received, stopping traffic generation...")
    running = False

def send_request(target_url, hostname):
    """Gửi một request wget và ghi log."""
    command = [
        'wget',
        '-q',                 # Chế độ quiet
        '-O', '-',            # Xuất output ra stdout (để không lưu file)
        f'--timeout={WGET_TIMEOUT}', # Đặt timeout
        f'--tries={WGET_TRIES}',     # Chỉ thử lại 1 lần
        f'http://{target_url}' # Thêm http://
    ]
    # print(f"[{hostname} PID: {os.getpid()}] Sending request to {target_url}") # Log chi tiết nếu cần
    try:
        # Chạy wget và đợi nó hoàn thành hoặc timeout
        result = subprocess.run(command, capture_output=True, text=True, timeout=WGET_TIMEOUT + 1) # Timeout của run lớn hơn wget một chút
        # if result.returncode != 0:
            # print(f"[{hostname} PID: {os.getpid()}] wget failed for {target_url}. Code: {result.returncode}, Error: {result.stderr.strip()}")
            # pass # Không dừng script nếu wget lỗi
        # else:
             # print(f"[{hostname} PID: {os.getpid()}] wget success for {target_url}") # Log thành công nếu cần
             # pass
    except subprocess.TimeoutExpired:
        print(f"[{hostname} PID: {os.getpid()}] wget command timed out for {target_url}")
        pass
    except Exception as e:
        print(f"[{hostname} PID: {os.getpid()}] Error running wget for {target_url}: {e}")
        pass

def get_delay(avg, variation):
    """Tính toán delay ngẫu nhiên."""
    delay = avg + random.uniform(-variation, variation)
    return max(0.01, delay) # Đảm bảo delay luôn dương và tối thiểu nhỏ

def get_ramp_delay(start_delay, end_delay, duration, elapsed_time):
    """Tính delay trong giai đoạn ramp."""
    if duration <= 0: return end_delay
    progress = min(1.0, elapsed_time / duration) # Tiến độ từ 0.0 đến 1.0
    delay = start_delay + (end_delay - start_delay) * progress
    return max(0.01, delay)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        target_url = DEFAULT_TARGET
        print(f"Usage: python traffic_generator.py <target_ip:port>")
        print(f"No target specified, using default: {DEFAULT_TARGET}")
        # sys.exit(1) # Thoát nếu bắt buộc phải có target
    else:
        target_url = sys.argv[1]

    hostname = "h_client" # Có thể lấy từ biến môi trường hoặc tham số khác nếu cần
    pid = os.getpid()
    print(f"[{hostname}-TrafficGen PID: {pid}] Starting traffic generation towards {target_url}...")

    # Đăng ký signal handler
    signal.signal(signal.SIGINT, signal_handler)  # Xử lý Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler) # Xử lý kill

    current_mode = "NORMAL"
    mode_end_time = time.time() + random.uniform(*TRAFFIC_MODES[current_mode]["duration_range"])
    mode_start_time = time.time()
    print(f"[{hostname}-TrafficGen PID: {pid}] Initial mode: {current_mode} until ~{time.strftime('%H:%M:%S', time.localtime(mode_end_time))}")

    while running:
        now = time.time()

        # --- Chuyển đổi Mode nếu hết thời gian ---
        if now >= mode_end_time:
            available_modes = list(TRAFFIC_MODES.keys())
            # Có thể thêm logic để tránh chuyển về mode cũ ngay lập tức nếu muốn
            # available_modes.remove(current_mode)
            # if not available_modes: available_modes = list(TRAFFIC_MODES.keys()) # Nếu chỉ còn 1 mode
            current_mode = random.choice(available_modes)
            mode_duration = random.uniform(*TRAFFIC_MODES[current_mode]["duration_range"])
            mode_end_time = now + mode_duration
            mode_start_time = now
            print(f"[{hostname}-TrafficGen PID: {pid}] Switching to mode: {current_mode} for ~{mode_duration:.1f}s (until ~{time.strftime('%H:%M:%S', time.localtime(mode_end_time))})")


        # --- Tính toán delay dựa trên mode hiện tại ---
        delay = 0.1 # Giá trị mặc định rất nhỏ
        mode_params = TRAFFIC_MODES[current_mode]

        if current_mode in ["NORMAL", "SPIKE", "LOW"]:
            delay = get_delay(mode_params["delay_avg"], mode_params["delay_variation"])
        elif current_mode == "RAMP_UP":
            elapsed = now - mode_start_time
            duration = mode_end_time - mode_start_time
            delay = get_ramp_delay(mode_params["start_delay"], mode_params["end_delay"], duration, elapsed)
        elif current_mode == "RAMP_DOWN":
            elapsed = now - mode_start_time
            duration = mode_end_time - mode_start_time
            delay = get_ramp_delay(mode_params["start_delay"], mode_params["end_delay"], duration, elapsed)

        # --- Gửi Request ---
        send_request(target_url, hostname)

        # --- Nghỉ theo delay đã tính ---
        # print(f"Sleeping for {delay:.3f} seconds...") # Log delay nếu cần debug
        # Tạm dừng một cách linh hoạt để có thể dừng ngay lập tức
        sleep_end = time.time() + delay
        while running and time.time() < sleep_end:
            time.sleep(0.05) # Ngủ một khoảng ngắn để kiểm tra cờ `running`

    print(f"[{hostname}-TrafficGen PID: {pid}] Traffic generation stopped.")