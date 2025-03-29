from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ether_types, arp, ipv4
from ryu.lib import hub
import csv
import time

class SimpleSwitch13(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(SimpleSwitch13, self).__init__(*args, **kwargs)
        self.mac_to_port = {}  # MAC address to switch port mapping
        self.arp_table = {}  # IP to MAC address mapping
        self.sw_to_ports = {}  # Switch to ports mapping
        self.topology = {}  # Switch to connected switches mapping
        self.datapaths = {}
        
        # Create CSV file for metrics
        self.csv_file = open('network_metrics.csv', 'w', newline='')
        self.csv_writer = csv.writer(self.csv_file)
        self.csv_writer.writerow(['timestamp', 'dpid', 'port', 'tx_bytes', 'rx_bytes'])
        
        # Start monitoring thread
        self.monitor_thread = hub.spawn(self._monitor)
        
        self.logger.info("Controller initialized")

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        
        # Install table-miss flow entry
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                         ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)
        
        # Store datapath for monitoring
        self.datapaths[datapath.id] = datapath
        self.mac_to_port.setdefault(datapath.id, {})
        self.sw_to_ports.setdefault(datapath.id, {})
        
        self.logger.info(f"Switch {datapath.id} connected")

    def add_flow(self, datapath, priority, match, actions, buffer_id=None, idle_timeout=0, hard_timeout=0):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,
                                           actions)]
        if buffer_id:
            mod = parser.OFPFlowMod(datapath=datapath, buffer_id=buffer_id,
                                  priority=priority, match=match,
                                  instructions=inst, idle_timeout=idle_timeout,
                                  hard_timeout=hard_timeout)
        else:
            mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                  match=match, instructions=inst,
                                  idle_timeout=idle_timeout, hard_timeout=hard_timeout)
        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        # If you hit this you might want to increase
        # the "miss_send_length" of your switch
        if ev.msg.msg_len < ev.msg.total_len:
            self.logger.debug("Packet truncated: only %s of %s bytes",
                             ev.msg.msg_len, ev.msg.total_len)
        
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']
        
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]
        
        # Ignore LLDP packets
        if eth.ethertype == ether_types.ETH_TYPE_IP:
            ip_pkt = pkt.get_protocol(ipv4.ipv4)
            if ip_pkt:
                self.logger.info(f"Handling IPv4 packet from {src} to {dst}")

                if dst in self.mac_to_port[dpid]:
                    out_port = self.mac_to_port[dpid][dst]
                else:
                    out_port = ofproto.OFPP_FLOOD  # Không biết, thì flood

                actions = [parser.OFPActionOutput(out_port)]
                
                # Cài đặt flow mới để tránh gọi lại packet_in
                match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src, eth_type=ether_types.ETH_TYPE_IP)
                self.add_flow(datapath, 1, match, actions, idle_timeout=60)
                
                out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                        in_port=in_port, actions=actions, data=msg.data)
                datapath.send_msg(out)

        
        # Get source/destination MAC
        dst = eth.dst
        src = eth.src
        dpid = datapath.id
        
        # Learn a mac address to avoid FLOOD next time.
        self.mac_to_port.setdefault(dpid, {})
        self.mac_to_port[dpid][src] = in_port
        
        # Handle ARP packets specifically
        if eth.ethertype == ether_types.ETH_TYPE_ARP:
            self.handle_arp(datapath, in_port, pkt)
        
        # If we know where the destination is, forward to that port
        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
            self.logger.info(f"Destination {dst} found at port {out_port} of switch {dpid}")
        else:
            out_port = ofproto.OFPP_FLOOD
            self.logger.info(f"Destination {dst} not found, flooding from switch {dpid}")
        
        actions = [parser.OFPActionOutput(out_port)]
        
        # Install a flow to avoid packet_in next time
        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src)
            # Verify if we have a valid buffer_id, if yes avoid to send both
            # flow_mod & packet_out
            if msg.buffer_id != ofproto.OFP_NO_BUFFER:
                self.add_flow(datapath, 1, match, actions, buffer_id=msg.buffer_id, idle_timeout=60)
                return
            else:
                self.add_flow(datapath, 1, match, actions, idle_timeout=60)
        
        # Send packet out
        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data
        
        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                in_port=in_port, actions=actions, data=data)
        datapath.send_msg(out)
        
        self.logger.info(f"Packet handled: dpid={dpid}, src={src}, dst={dst}, in_port={in_port}, out_port={out_port}")
    
    def handle_arp(self, datapath, in_port, pkt):
        eth = pkt.get_protocols(ethernet.ethernet)[0]
        arp_pkt = pkt.get_protocol(arp.arp)
        
        if not arp_pkt:
            return
        
        # Update ARP table
        self.arp_table[arp_pkt.src_ip] = eth.src
        self.logger.info(f"ARP: {arp_pkt.src_ip} -> {eth.src}")
    
    def _monitor(self):
        """
        Periodically request port statistics from switches
        """
        self.logger.info('Starting monitoring thread')
        while True:
            for dp in self.datapaths.values():
                self._request_port_stats(dp)
            hub.sleep(10)  # Request every 10 seconds
    
    def _request_port_stats(self, datapath):
        """
        Send port statistics request to switch
        """
        self.logger.debug('Sending port stats request to switch %016x', datapath.id)
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        
        req = parser.OFPPortStatsRequest(datapath, 0, ofproto.OFPP_ANY)
        datapath.send_msg(req)
    
    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def _port_stats_reply_handler(self, ev):
        """
        Handle port statistics reply from switch
        """
        body = ev.msg.body
        dpid = ev.msg.datapath.id
        
        self.logger.debug('PortStats from switch %d:', dpid)
        for stat in body:
            # Write stats to CSV
            self.csv_writer.writerow([
                time.time(),
                dpid,
                stat.port_no,
                stat.tx_bytes,
                stat.rx_bytes
            ])
            self.csv_file.flush()

    def __del__(self):
        """
        Clean up when controller is stopped
        """
        if hasattr(self, 'csv_file'):
            self.csv_file.close()
            self.logger.info("CSV file closed")