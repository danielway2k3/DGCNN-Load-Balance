from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import RemoteController
from mininet.cli import CLI
from mininet.log import setLogLevel

class SimpleTestTopo(Topo):
    def build(self):
        # Add 2 switches
        s1 = self.addSwitch('s1')
        s2 = self.addSwitch('s2')
        
        # Add 4 hosts
        h1 = self.addHost('h1')
        h2 = self.addHost('h2')
        h3 = self.addHost('h3')
        h4 = self.addHost('h4')
        
        # Connect hosts to switches
        self.addLink(h1, s1)
        self.addLink(h2, s1)
        self.addLink(h3, s2)
        self.addLink(h4, s2)
        
        # Connect switches
        self.addLink(s1, s2)

def run():
    topo = SimpleTestTopo()
    controller = lambda name: RemoteController(name, ip='127.0.0.1')
    net = Mininet(topo=topo, controller=controller)
    
    try:
        # Start network
        net.start()
        
        # Print host connections
        print("\n*** Hosts connections:")
        for h in net.hosts:
            print(f"{h.name} {h.MAC()} {h.IP()}")
        
        # Run a ping test
        print("\n*** Testing ping connectivity")
        
        h1, h2 = net.get('h1', 'h2')
        print(f"Pinging {h2.name} from {h1.name}:")
        print(h1.cmd(f'ping -c 3 {h2.IP()}'))
        
        h1, h3 = net.get('h1', 'h3')
        print(f"Pinging {h3.name} from {h1.name}:")
        print(h1.cmd(f'ping -c 3 {h3.IP()}'))
        
        # Enter CLI mode
        print("\n*** Starting CLI")
        CLI(net)
    finally:
        # Clean up
        net.stop()

if __name__ == '__main__':
    setLogLevel('info')
    run()