from mininet.net import Mininet
from mininet.node import RemoteController
from mininet.topo import Topo
from mininet.link import TCLink
from mininet.log import setLogLevel

class SDWAN_Topology(Topo):
    def build(self):
        # Add Hosts (HQ + Branches)
        hq = self.addHost('hq')
        branch1 = self.addHost('b1')
        branch2 = self.addHost('b2')
        branch3 = self.addHost('b3')

        # Add OpenFlow Switches
        s1 = self.addSwitch('s1')
        s2 = self.addSwitch('s2')
        s3 = self.addSwitch('s3')
        s4 = self.addSwitch('s4')

        # Add Links (with bandwidth constraints)
        self.addLink(hq, s1, cls=TCLink, bw=50)   # HQ to Switch1
        self.addLink(hq, s3, cls=TCLink, bw=40)   # HQ to Switch3
        self.addLink(s1, s2, cls=TCLink, bw=30)   # Switch1 to Switch2
        self.addLink(s1, s3, cls=TCLink, bw=25)   # Switch1 to Switch3
        self.addLink(s2, s4, cls=TCLink, bw=20)   # Switch2 to Switch4
        self.addLink(s3, s4, cls=TCLink, bw=35)   # Switch3 to Switch4

        # Connect branches
        self.addLink(s2, branch1, cls=TCLink, bw=10)
        self.addLink(s4, branch2, cls=TCLink, bw=15)
        self.addLink(s4, branch3, cls=TCLink, bw=12)

if __name__ == '__main__':
    setLogLevel('info')
    topo = SDWAN_Topology()
    net = Mininet(topo=topo, controller=RemoteController)
    net.start()
    net.pingAll()
    net.stop()
