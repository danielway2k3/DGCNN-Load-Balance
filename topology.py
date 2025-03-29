from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import RemoteController
from mininet.link import TCLink
from mininet.util import dumpNodeConnections
from mininet.log import setLogLevel
from mininet.cli import CLI
import time
import os
import signal
import subprocess

class LoadBalanceTopo(Topo):
    def build(self):
        # Add switches
        s1 = self.addSwitch('s1')
        s2 = self.addSwitch('s2')
        s3 = self.addSwitch('s3')
        s4 = self.addSwitch('s4')
        
        # Add hosts
        h1 = self.addHost('h1')
        h2 = self.addHost('h2')
        h3 = self.addHost('h3')
        h4 = self.addHost('h4')
        h5 = self.addHost('h5')
        h6 = self.addHost('h6')
        
        # Add links between switches
        self.addLink(s1, s2, bw=100, delay='5ms', use_htb=True)
        self.addLink(s1, s3, bw=100, delay='5ms', use_htb=True)
        self.addLink(s1, s4, bw=100, delay='5ms', use_htb=True)
        self.addLink(s2, s3, bw=50, delay='5ms', use_htb=True)  # New link to improve connectivity
        self.addLink(s3, s4, bw=50, delay='5ms', use_htb=True)
        
        # Connect hosts to switches
        self.addLink(h1, s2, bw=10, delay='1ms', use_htb=True)
        self.addLink(h2, s2, bw=10, delay='1ms', use_htb=True)
        self.addLink(h3, s3, bw=10, delay='1ms', use_htb=True)
        self.addLink(h4, s4, bw=10, delay='1ms', use_htb=True)
        self.addLink(h5, s4, bw=10, delay='1ms', use_htb=True)
        self.addLink(h6, s4, bw=10, delay='1ms', use_htb=True)


def run():
    
    # Create topology
    topo = LoadBalanceTopo()
    
    # Create Mininet network with remote controller
    net = Mininet(topo=topo, controller=lambda name: RemoteController(name, ip='127.0.0.1', port=6653), link=TCLink)
    
    try:
        # Start network
        net.start()
        dumpNodeConnections(net.hosts)
        
        # Wait for network to initialize
        print("Waiting for network initialization...")
        time.sleep(10)  # Increase time to allow controller to process initial packets
        
        # Test connectivity
        print("Testing connectivity...")
        net.pingAll(timeout='1')
        
        # Interactive CLI for debugging
        print("\nEntering CLI mode for troubleshooting. Type 'exit' to proceed with data collection.")
        CLI(net)
        
        # Only continue if the network is working
        print("Checking if network is ready for data collection...")
        if net.pingAll(timeout='1') > 50:  # If more than 50% packet loss
            print("ERROR: Network connectivity is poor. Aborting data collection.")
            return
        
        # Proceed with data collection
        print("Beginning data collection...")
        collect_network_data(net)
        
    finally:
        # Stop network
        print("Stopping network...")
        net.stop()
        


def collect_network_data(net):
    """Collect network data and save to CSV"""
    with open('data_plane.csv', 'w') as f:
        f.write('timestamp,src,dst,throughput_mbps,latency_ms\n')
        hosts = net.hosts
        
        for src in hosts:
            for dst in hosts:
                if src != dst:
                    try:
                        print(f"Collecting data between {src.name} and {dst.name}...")
                        
                        # Kill any existing iperf servers
                        dst.cmd('pkill -f "iperf -s"')
                        
                        # Start iperf server on destination
                        dst.cmd(f'iperf -s > /dev/null 2>&1 &')
                        time.sleep(1)  # Wait for server to start
                        
                        # Measure latency
                        ping_output = src.cmd(f'ping -c 5 {dst.IP()}')
                        latency = -1
                        if 'min/avg/max/mdev' in ping_output:
                            latency_parts = ping_output.split('min/avg/max/mdev = ')[1].split('/')[1]
                            latency = float(latency_parts)
                        
                        # Measure throughput
                        iperf_output = src.cmd(f'iperf -c {dst.IP()} -t 2')
                        throughput = -1
                        if 'Mbits/sec' in iperf_output:
                            throughput_lines = [line for line in iperf_output.split('\n') if 'Mbits/sec' in line]
                            if throughput_lines:
                                last_line = throughput_lines[-1]
                                parts = last_line.split()
                                for i in range(len(parts) - 1):
                                    if parts[i+1] == 'Mbits/sec':
                                        throughput = float(parts[i])
                                        break
                        
                        # Write data to file
                        f.write(f'{time.time()},{src.name},{dst.name},{throughput},{latency}\n')
                        f.flush()
                        
                        # Stop iperf server
                        dst.cmd('pkill -f "iperf -s"')
                        
                    except Exception as e:
                        print(f"Error collecting data between {src.name} and {dst.name}: {e}")
                        f.write(f'{time.time()},{src.name},{dst.name},-1,-1\n')
                        f.flush()
    
    print("Data collection completed.")

if __name__ == '__main__':
    setLogLevel('info')
    run()