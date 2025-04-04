#!/usr/bin/env python

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import OVSKernelSwitch, RemoteController
from mininet.cli import CLI
from mininet.log import setLogLevel, info
from mininet.link import TCLink
import time # Đảm bảo import time

class LoadBalancerTopo(Topo):
    "Topology for Load Balancer Experiment"

    def build(self, **_opts):
        # --- Thêm Switches ---
        s1 = self.addSwitch('s1', cls=OVSKernelSwitch, protocols='OpenFlow13')

        # --- Thêm Hosts (Servers) ---
        h1 = self.addHost('h1', ip='10.0.0.1/24', mac='00:00:00:00:00:01')
        h2 = self.addHost('h2', ip='10.0.0.2/24', mac='00:00:00:00:00:02')
        h3 = self.addHost('h3', ip='10.0.0.3/24', mac='00:00:00:00:00:03')

        # --- Thêm Host (Client) ---
        h_client = self.addHost('h_client', ip='10.0.0.4/24', mac='00:00:00:00:00:04')

        # --- Thêm Links với thông số ---
        self.addLink(h_client, s1, bw=10, delay='10ms')
        self.addLink(h1, s1, bw=10, delay='50ms')
        self.addLink(h2, s1, bw=10, delay='100ms')
        self.addLink(h3, s1, bw=10, delay='150ms')


def run():
    """Tạo và chạy mạng Mininet với topology đã định nghĩa"""
    # 1. Tạo đối tượng topology
    topo = LoadBalancerTopo()

    # 2. Tạo đối tượng Mininet
    net = Mininet(
        topo=topo,
        controller=RemoteController('c0', ip='127.0.0.1', port=6653),
        link=TCLink,
        switch=OVSKernelSwitch,
        autoSetMacs=True,
        build=True
    )

    # 3. Khởi động mạng
    info('*** Starting network\n')
    net.start()

    # --- Lấy đối tượng host SAU KHI net.start() ---
    h1 = net.get('h1')
    h2 = net.get('h2')
    h3 = net.get('h3')
    h_client = net.get('h_client')

    # --- Đảm bảo các host sẵn sàng một chút (tùy chọn nhưng có thể hữu ích) ---
    # time.sleep(1)

    # --- Chạy các script monitor và traffic generator TRONG NỀN ---
    # Đảm bảo đường dẫn đến các script là chính xác
    info('*** Starting monitoring and traffic generation scripts...\n')

    # Chạy CPU monitor trên các server
    cpu_script_path = 'cpu_monitor.py'
    h1.cmd(f'python3 {cpu_script_path} h1 > /tmp/cpu_h1.log 2>&1 &')
    h2.cmd(f'python3 {cpu_script_path} h2 > /tmp/cpu_h2.log 2>&1 &')
    h3.cmd(f'python3 {cpu_script_path} h3 > /tmp/cpu_h3.log 2>&1 &')
    info('--- CPU monitors started.\n')

    # Chạy Latency monitor trên client
    latency_script_path = 'latency_monitor.py'
    h_client.cmd(f'python3 {latency_script_path} > /tmp/latency_h_client.log 2>&1 &')
    info('--- Latency monitor started.\n')

    # Chạy Traffic generator trên client
    virtual_ip = '10.0.0.100'
    target_port = 8080
    target_service = f"{virtual_ip}:{target_port}"
    traffic_script_path = 'traffic_generator.py'
    h_client.cmd(f'python3 {traffic_script_path} {target_service} > /tmp/traffic_gen_h_client.log 2>&1 &')
    info(f'--- Traffic generator started on h_client targeting {target_service}.\n')

    # --- Đợi một chút để switch kết nối và các script ổn định ---
    info('*** Waiting a few seconds for controller connection and scripts...\n')
    time.sleep(5) # Tăng thời gian chờ lên một chút

    # 4. Chạy Mininet Command Line Interface (CLI)
    info('*** Running CLI (Type "exit" or Ctrl+D to quit)\n')
    CLI(net)

    # --- Dừng các script monitor và traffic generator TRƯỚC KHI net.stop() ---
    info('*** Stopping monitoring and traffic generation scripts...\n')
    # Gửi tín hiệu SIGTERM (mặc định của kill) đến tất cả tiến trình python3 trên các host
    h1.cmd('kill %python3')
    h2.cmd('kill %python3')
    h3.cmd('kill %python3')
    h_client.cmd('kill %python3')
    info('--- Scripts potentially stopped.\n')
    # Chờ một chút để các tiến trình có thời gian dừng
    # time.sleep(1)

    # 5. Dừng mạng khi thoát CLI
    info('*** Stopping network\n')
    net.stop()

if __name__ == '__main__':
    setLogLevel('info')
    run()