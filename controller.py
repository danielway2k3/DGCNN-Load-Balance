# load_balancer_simple.py
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import ether_types
from ryu.lib.packet import arp
from ryu.lib.packet import ipv4
from ryu.lib.packet import tcp
from ryu.lib.packet import udp # Thêm để xử lý UDP nếu cần
from ryu.lib import mac as mac_lib # Đổi tên để tránh xung đột
from ryu.lib.packet import in_proto
from ryu.app.wsgi import ControllerBase, WSGIApplication, route
from ryu.lib import hub # Để chạy periodic task
import json
import time
# load_balancer_simple.py
# ... (các import cần thiết đã có ở trên) ...
from collections import defaultdict
from webob import Response # Đảm bảo import này tồn tại

# --- Cấu hình Load Balancer ---
VIRTUAL_IP = '10.0.0.100'
VIRTUAL_MAC = '00:00:00:00:00:AA'
SERVERS = {
    '10.0.0.1': '00:00:00:00:00:01',
    '10.0.0.2': '00:00:00:00:00:02',
    '10.0.0.3': '00:00:00:00:00:03',
}
# LOAD_BALANCING_ALGORITHM = 'round_robin'
LOAD_BALANCING_ALGORITHM = 'least_connection'
LB_INSTANCE_NAME = 'SimpleLoadBalancerAPI'
MONITOR_INTERVAL = 3 # Giây

class SimpleLoadBalancer(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    _CONTEXTS = {'wsgi': WSGIApplication}

    def __init__(self, *args, **kwargs):
        super(SimpleLoadBalancer, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.server_list = list(SERVERS.keys())
        self.server_index = 0
        self.connection_counts = defaultdict(int)
        self.client_to_server_map = {}

        # --- Di chuyển phần log khởi tạo lên đầu cho rõ ràng ---
        self.logger.info("Initializing Simple Load Balancer Ryu App...")
        self.logger.info(f"Algorithm: {LOAD_BALANCING_ALGORITHM}")
        self.logger.info(f"Virtual IP: {VIRTUAL_IP}")
        self.logger.info(f"Servers: {self.server_list}")
        self.logger.info(f"Monitor Interval: {MONITOR_INTERVAL}s")

        # --- WSGI Setup ---
        self.wsgi = kwargs['wsgi']
        self.wsgi.register(TelemetryController, {LB_INSTANCE_NAME: self})
        self.logger.info(f"WSGI API registered. Listening via Ryu's WSGI server.")

        # --- Telemetry Data Storage ---
        self.telemetry_data = {
            'latency': defaultdict(lambda: -1.0),  # Dùng defaultdict để dễ truy cập hơn
            'cpu_usage': defaultdict(lambda: -1.0),
            'throughput': defaultdict(lambda: 0.0)
        }
        self.prev_port_stats = {}
        self.port_to_server_ip = {}
        # --- Thêm biến lưu trữ datapath ---
        # Sử dụng self.datapaths thay vì self.data.datapaths để tương thích rộng hơn
        # hoặc kiểm tra phiên bản Ryu nếu cần dùng self.data
        self.datapaths = {} # Lưu trữ {dpid: datapath_object}

        # --- Bắt đầu task giám sát định kỳ ---
        self.monitor_thread = hub.spawn(self._monitor)
        self.logger.info("Monitoring thread started.")
        self.logger.info("Simple Load Balancer Ryu App Ready (with Telemetry).") # Log này có thể trùng lặp, cân nhắc bỏ bớt

    # --- Thêm hàm xử lý khi switch kết nối/ngắt kết nối để quản lý self.datapaths ---
    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, CONFIG_DISPATCHER])
    def _state_change_handler(self, ev):
        datapath = ev.datapath
        if ev.state == MAIN_DISPATCHER:
            if datapath.id not in self.datapaths:
                self.logger.info(f'Registering datapath: {datapath.id:016x}')
                self.datapaths[datapath.id] = datapath
        elif ev.state == DEAD_DISPATCHER:
            if datapath.id in self.datapaths:
                self.logger.info(f'Unregistering datapath: {datapath.id:016x}')
                del self.datapaths[datapath.id]
                # Cũng nên xóa thông tin liên quan khỏi prev_port_stats, port_to_server_ip nếu cần
                self.prev_port_stats.pop(datapath.id, None)
                self.port_to_server_ip.pop(datapath.id, None)

    # --- Hàm chạy định kỳ để yêu cầu Port Stats ---
    def _monitor(self):
        self.logger.info("Starting periodic monitoring task...")
        # Đảm bảo import DEAD_DISPATCHER từ ryu.controller.handler
        from ryu.controller.handler import DEAD_DISPATCHER
        while True:
            # self.logger.debug("Monitor Task Running...")
            # Sử dụng self.datapaths đã được quản lý bởi _state_change_handler
            list_of_datapaths = list(self.datapaths.values()) # Tạo bản sao để tránh lỗi thay đổi kích thước khi duyệt
            for dp in list_of_datapaths:
                self._request_port_stats(dp)

                # Cập nhật port_to_server_ip dựa trên mac_to_port và SERVERS
                dpid = dp.id
                if dpid in self.mac_to_port:
                    self.port_to_server_ip.setdefault(dpid, {})
                    for mac, port in self.mac_to_port[dpid].items():
                         server_ip = next((ip for ip, server_mac in SERVERS.items() if server_mac == mac), None)
                         if server_ip:
                             if self.port_to_server_ip[dpid].get(port) != server_ip:
                                 # self.logger.debug(f"Mapping port {port} on switch {dpid} to server {server_ip}")
                                 self.port_to_server_ip[dpid][port] = server_ip

            # In ra dữ liệu telemetry thu thập được (để kiểm tra)
            # self.logger.info(f"Current Telemetry: {json.dumps(self.telemetry_data, default=float, indent=2)}") # Thêm default=float cho defaultdict

            # Tính toán STATE và REWARD ở đây
            current_state = self._get_rl_state()
            current_reward = self._calculate_reward(current_state)
            # self.logger.info(f"RL State: {current_state}")
            # self.logger.info(f"RL Reward: {current_reward}")

            self.logger.info(f"Current Telemetry: {json.dumps(self.telemetry_data, default=float, indent=2)}")
            
            hub.sleep(MONITOR_INTERVAL)

    # --- Gửi yêu cầu Port Stats ---
    def _request_port_stats(self, datapath):
        ofp = datapath.ofproto
        parser = datapath.ofproto_parser
        req = parser.OFPPortStatsRequest(datapath, 0, ofp.OFPP_ANY)
        # self.logger.debug(f'Sending port stats request to switch {datapath.id:016x}')
        try:
            datapath.send_msg(req)
        except Exception as e: # Bắt lỗi nếu switch không còn kết nối
             self.logger.error(f"Error sending port stats request to {datapath.id:016x}: {e}")


    # --- Xử lý trả lời Port Stats ---
    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def _port_stats_reply_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        dpid = datapath.id
        body = msg.body

        # self.logger.debug(f'Received port stats reply from switch {dpid:016x}')

        current_time = time.time()
        self.prev_port_stats.setdefault(dpid, {})
        # Không cần clear throughput ở đây, thay vào đó cập nhật hoặc đặt về 0 nếu không có traffic
        # self.telemetry_data['throughput'].clear()

        # Tạo một dict tạm để lưu throughput mới, sau đó cập nhật self.telemetry_data
        current_throughputs = defaultdict(lambda: 0.0)

        for stat in sorted(body, key=lambda p: p.port_no):
            port_no = stat.port_no
            # --- Lấy ofproto từ datapath thay vì dùng trực tiếp ofproto_v1_3 ---
            ofproto = datapath.ofproto
            if port_no != ofproto.OFPP_LOCAL and port_no <= ofproto.OFPP_MAX: # Kiểm tra thêm OFPP_MAX
                server_ip = self.port_to_server_ip.get(dpid, {}).get(port_no)
                throughput_mbps = 0.0 # Khởi tạo là float

                if port_no in self.prev_port_stats[dpid]:
                    prev_stat = self.prev_port_stats[dpid][port_no]
                    time_delta = current_time - prev_stat['timestamp']
                    if time_delta > 0.001: # Tránh chia cho 0 hoặc khoảng thời gian quá nhỏ
                        bytes_delta = (stat.tx_bytes - prev_stat['tx_bytes']) + (stat.rx_bytes - prev_stat['rx_bytes'])
                        throughput_bps = (bytes_delta * 8) / time_delta
                        throughput_mbps = throughput_bps / 1e6 # Mbps

                        if server_ip:
                            current_throughputs[server_ip] = throughput_mbps
                            # self.logger.debug(f"Switch {dpid:016x} Port {port_no} ({server_ip}) Throughput: {throughput_mbps:.2f} Mbps")

                # Lưu stats hiện tại
                self.prev_port_stats[dpid][port_no] = {
                    'rx_bytes': stat.rx_bytes,
                    'tx_bytes': stat.tx_bytes,
                    'timestamp': current_time
                }
        # Cập nhật telemetry_data['throughput'] với dữ liệu mới
        # Đặt về 0 cho các server không có traffic trong khoảng này
        for ip in SERVERS.keys():
             self.telemetry_data['throughput'][ip] = current_throughputs.get(ip, 0.0)


    # --- Hàm cập nhật dữ liệu Telemetry từ API ---
    def update_telemetry(self, data_type, data):
        if data_type == 'cpu':
            hostname = data.get('hostname')
            cpu = data.get('cpu_usage')
            if hostname and cpu is not None:
                # self.logger.debug(f"Received CPU data: {hostname}={cpu}%")
                try:
                    self.telemetry_data['cpu_usage'][hostname] = float(cpu)
                except (ValueError, TypeError):
                     self.logger.warning(f"Invalid CPU value received: {cpu} for {hostname}")

        elif data_type == 'latency':
            latencies = data.get('latencies')
            if isinstance(latencies, dict): # Kiểm tra kiểu dữ liệu
                # self.logger.debug(f"Received Latency data: {latencies}")
                for server_ip, latency in latencies.items():
                     if server_ip in SERVERS: # Chỉ cập nhật cho server đã biết
                        try:
                            self.telemetry_data['latency'][server_ip] = float(latency) if latency is not None and latency >= 0 else -1.0 # Xử lý giá trị lỗi/None
                        except (ValueError, TypeError):
                             self.logger.warning(f"Invalid latency value received: {latency} for {server_ip}")
                             self.telemetry_data['latency'][server_ip] = -1.0
            else:
                self.logger.warning(f"Invalid latency data format received: {latencies}")
        else:
            self.logger.warning(f"Unknown telemetry data type: {data_type}")

    # --- Placeholder cho State và Reward (cho RL sau này) ---
    def _get_rl_state(self):
        state = []
        server_ips_ordered = sorted(SERVERS.keys())
        hostnames_ordered = sorted([f'h{i+1}' for i in range(len(SERVERS))])

        for host in hostnames_ordered:
            # Truy cập trực tiếp defaultdict
            state.append(self.telemetry_data['cpu_usage'][host])

        for ip in server_ips_ordered:
            state.append(self.telemetry_data['latency'][ip])

        for ip in server_ips_ordered:
            state.append(self.telemetry_data['throughput'][ip])

        # self.logger.debug(f"Generated RL State: {state}") # Debug state
        return state

    def _calculate_reward(self, current_state):
        reward = 0.0 # Khởi tạo là float
        num_servers = len(SERVERS)

        # Kiểm tra xem state có đúng độ dài không
        if len(current_state) != num_servers * 3:
            self.logger.error(f"Invalid state length for reward calculation: {len(current_state)}, expected {num_servers * 3}")
            return 0.0

        # Indices for cpu, latency, throughput
        cpu_indices = range(num_servers)
        latency_indices = range(num_servers, num_servers * 2)
        throughput_indices = range(num_servers * 2, num_servers * 3)

        # Tính toán phần thưởng/phạt
        total_throughput = sum(current_state[i] for i in throughput_indices if current_state[i] >= 0)
        reward += total_throughput * 0.1 # Thưởng cho throughput

        valid_latencies = [current_state[i] for i in latency_indices if current_state[i] >= 0]
        if valid_latencies:
            avg_latency = sum(valid_latencies) / len(valid_latencies)
            reward -= avg_latency * 0.5 # Phạt cho latency cao

        valid_cpus = [current_state[i] for i in cpu_indices if current_state[i] >= 0]
        if valid_cpus:
            avg_cpu = sum(valid_cpus) / len(valid_cpus)
            if avg_cpu > 80:
                reward -= (avg_cpu - 80) # Phạt nếu CPU trung bình > 80%

        # self.logger.debug(f"Calculated Reward: {reward}") # Debug reward
        return reward

    # --- Các hàm xử lý OpenFlow (giữ nguyên như trước, nhưng thêm xử lý lỗi/cải tiến nếu cần) ---

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        dpid = datapath.id

        # --- Thêm datapath vào danh sách quản lý ---
        # Mặc dù đã có _state_change_handler, việc thêm ở đây đảm bảo nó có ngay khi feature được xử lý
        if dpid not in self.datapaths:
             self.logger.info(f'Registering datapath from SwitchFeatures: {dpid:016x}')
             self.datapaths[dpid] = datapath

        # Cài đặt flow table miss entry
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)
        self.logger.info(f"Switch {dpid:016x} connected. Table-miss flow installed.")


    def add_flow(self, datapath, priority, match, actions, idle_timeout=0, hard_timeout=0):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                match=match, instructions=inst,
                                idle_timeout=idle_timeout, hard_timeout=hard_timeout)
        try:
            datapath.send_msg(mod)
        except Exception as e:
            self.logger.error(f"Error sending FlowMod to {datapath.id:016x}: {e}")


    def _select_server(self, client_ip, client_port):
        # ... (giữ nguyên logic chọn server) ...
        selected_server_ip = None

        if LOAD_BALANCING_ALGORITHM == 'round_robin':
            selected_server_ip = self.server_list[self.server_index]
            self.server_index = (self.server_index + 1) % len(self.server_list)
            self.logger.info(f"[RoundRobin] Selected server {selected_server_ip} for client {client_ip}:{client_port}")

        elif LOAD_BALANCING_ALGORITHM == 'least_connection':
            min_connections = float('inf')
            best_server = None # Khởi tạo best_server
            # --- Cải tiến: Nếu có nhiều server cùng min_connections, chọn ngẫu nhiên hoặc round-robin giữa chúng ---
            candidates = []
            for server_ip in self.server_list:
                conn_count = self.connection_counts[server_ip]
                if conn_count < min_connections:
                    min_connections = conn_count
                    candidates = [server_ip] # Bắt đầu lại danh sách ứng viên
                elif conn_count == min_connections:
                    candidates.append(server_ip) # Thêm vào danh sách ứng viên

            if candidates:
                 # Chọn một server từ các ứng viên (ví dụ: round robin đơn giản trong số ứng viên)
                 # Hoặc dùng random.choice(candidates) nếu muốn ngẫu nhiên
                 current_candidate_index = self.server_index % len(candidates) # Tái sử dụng server_index một cách khác
                 selected_server_ip = candidates[current_candidate_index]
                 # Cập nhật server_index để lần sau có thể chọn ứng viên khác nếu số kết nối vẫn bằng nhau
                 self.server_index = (self.server_index + 1) # Không cần modulo ở đây nếu chỉ dùng để chọn ứng viên

                 self.connection_counts[selected_server_ip] += 1
                 self.logger.info(f"[LeastConnection] Selected server {selected_server_ip} (from {len(candidates)} candidates with {min_connections} conns) for client {client_ip}:{client_port}")
                 self.logger.info(f"Current Connection Counts: {dict(self.connection_counts)}")
            else:
                 # Trường hợp không có server nào (danh sách rỗng), dù không nên xảy ra
                 self.logger.error("No server candidates found in least connection selection!")
                 return None


        else: # Default to Round Robin
            selected_server_ip = self.server_list[self.server_index]
            self.server_index = (self.server_index + 1) % len(self.server_list)
            self.logger.warning(f"Unknown algorithm. Using Round Robin. Selected {selected_server_ip}")

        return selected_server_ip


    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']
        dpid = datapath.id # Lấy dpid ở đây

        # Kiểm tra xem datapath có trong danh sách quản lý không
        if dpid not in self.datapaths:
             self.logger.warning(f"Received PacketIn from unknown datapath {dpid:016x}. Ignoring.")
             return

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)

        if not eth: # Kiểm tra nếu không parse được ethernet header
             self.logger.debug("Received packet without Ethernet header.")
             return

        if eth.ethertype == ether_types.ETH_TYPE_LLDP: return
        if eth.ethertype == ether_types.ETH_TYPE_IPV6: return

        dst_mac = eth.dst
        src_mac = eth.src


        # Học MAC -> Port
        self.mac_to_port.setdefault(dpid, {})
        if self.mac_to_port[dpid].get(src_mac) != in_port:
             self.logger.info(f"Learning MAC {src_mac} on port {in_port} for switch {dpid:016x}")
             self.mac_to_port[dpid][src_mac] = in_port
             # --- Cập nhật port_to_server_ip ngay khi học được MAC của server ---
             server_ip = next((ip for ip, server_mac in SERVERS.items() if server_mac == src_mac), None)
             if server_ip:
                 self.port_to_server_ip.setdefault(dpid, {})
                 if self.port_to_server_ip[dpid].get(in_port) != server_ip:
                      self.logger.info(f"Mapping port {in_port} on switch {dpid:016x} to server {server_ip} (learned via PacketIn)")
                      self.port_to_server_ip[dpid][in_port] = server_ip


        # --- Xử lý ARP ---
        if eth.ethertype == ether_types.ETH_TYPE_ARP:
            arp_pkt = pkt.get_protocol(arp.arp)
            if arp_pkt and arp_pkt.opcode == arp.ARP_REQUEST and arp_pkt.dst_ip == VIRTUAL_IP:
                # self.logger.info(f"Received ARP request for VIP {VIRTUAL_IP} from {arp_pkt.src_ip}")
                reply_pkt = packet.Packet()
                reply_pkt.add_protocol(ethernet.ethernet(ethertype=ether_types.ETH_TYPE_ARP, dst=src_mac, src=VIRTUAL_MAC))
                reply_pkt.add_protocol(arp.arp(opcode=arp.ARP_REPLY, src_mac=VIRTUAL_MAC, src_ip=VIRTUAL_IP, dst_mac=arp_pkt.src_mac, dst_ip=arp_pkt.src_ip))
                reply_pkt.serialize()
                actions = [parser.OFPActionOutput(in_port)]
                out = parser.OFPPacketOut(datapath=datapath, buffer_id=ofproto.OFP_NO_BUFFER, in_port=ofproto.OFPP_CONTROLLER, actions=actions, data=reply_pkt.data)
                datapath.send_msg(out)
                # self.logger.info(f"Sent ARP reply: {VIRTUAL_IP} is at {VIRTUAL_MAC}")
            else: # Forward non-VIP ARP
                out_port = self.mac_to_port[dpid].get(dst_mac, ofproto.OFPP_FLOOD)
                actions = [parser.OFPActionOutput(out_port)]
                data = msg.data if msg.buffer_id == ofproto.OFP_NO_BUFFER else None
                out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id, in_port=in_port, actions=actions, data=data)
                datapath.send_msg(out)
            return

        # --- Xử lý IP ---
        if eth.ethertype == ether_types.ETH_TYPE_IP:
            ip_pkt = pkt.get_protocol(ipv4.ipv4)
            if not ip_pkt: return # Kiểm tra nếu không parse được IPv4

            src_ip = ip_pkt.src
            dst_ip = ip_pkt.dst
            protocol = ip_pkt.proto
            client_port, dst_port = None, None

            # Extract ports for TCP/UDP
            if protocol == in_proto.IPPROTO_TCP:
                tcp_pkt = pkt.get_protocol(tcp.tcp)
                if not tcp_pkt: return
                client_port = tcp_pkt.src_port if dst_ip == VIRTUAL_IP else tcp_pkt.dst_port
                dst_port = tcp_pkt.dst_port if dst_ip == VIRTUAL_IP else tcp_pkt.src_port
            elif protocol == in_proto.IPPROTO_UDP:
                udp_pkt = pkt.get_protocol(udp.udp)
                if not udp_pkt: return
                client_port = udp_pkt.src_port if dst_ip == VIRTUAL_IP else udp_pkt.dst_port
                dst_port = udp_pkt.dst_port if dst_ip == VIRTUAL_IP else udp_pkt.src_port

            # --- A. Client -> VIP ---
            if dst_ip == VIRTUAL_IP and src_ip not in SERVERS:
                if client_port is not None and dst_port is not None: # Process only TCP/UDP
                    client_key = (src_ip, client_port, dst_port, protocol)
                    selected_server_ip = self._select_server(src_ip, client_port)
                    if not selected_server_ip: return

                    selected_server_mac = SERVERS[selected_server_ip]
                    out_port = self.mac_to_port[dpid].get(selected_server_mac)

                    # --- Cải tiến xử lý khi chưa biết out_port ---
                    if out_port is None:
                         # Chỉ flood gói hiện tại, không cài flow rule với action FLOOD
                         self.logger.warning(f"Don't know out_port for server {selected_server_mac}. Flooding current packet for {client_key}. Flow rule will be installed on next packet.")
                         action_flood = [parser.OFPActionOutput(ofproto.OFPP_FLOOD)]
                         out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                                   in_port=in_port, actions=action_flood,
                                                   data=msg.data if msg.buffer_id == ofproto.OFP_NO_BUFFER else None)
                         datapath.send_msg(out)
                         # Không lưu mapping hoặc cài flow rule vội
                         return # Xử lý xong gói này, đợi packet-in tiếp theo khi port đã học

                    # --- Chỉ thực hiện tiếp nếu đã biết out_port ---
                    self.logger.info(f"Found out_port {out_port} for server {selected_server_mac}")
                    self.logger.info(f"Client->VIP: Redirecting {src_ip}:{client_port} -> {VIRTUAL_IP}:{dst_port} to server {selected_server_ip}:{dst_port} ({selected_server_mac}) via port {out_port}")

                    # Lưu mapping
                    self.client_to_server_map[client_key] = selected_server_mac
                    # self.logger.debug(f"Stored map: {client_key} -> {selected_server_mac}")

                    # Tạo và cài flow rule C2S
                    match_fields_c2s = { 'in_port': in_port, 'eth_type': ether_types.ETH_TYPE_IP, 'ipv4_src': src_ip, 'ipv4_dst': VIRTUAL_IP, 'ip_proto': protocol }
                    if protocol == in_proto.IPPROTO_TCP: match_fields_c2s['tcp_src'], match_fields_c2s['tcp_dst'] = client_port, dst_port
                    elif protocol == in_proto.IPPROTO_UDP: match_fields_c2s['udp_src'], match_fields_c2s['udp_dst'] = client_port, dst_port
                    match_c2s = parser.OFPMatch(**match_fields_c2s)
                    actions_c2s = [ parser.OFPActionSetField(eth_dst=selected_server_mac), parser.OFPActionSetField(ipv4_dst=selected_server_ip), parser.OFPActionOutput(out_port) ]
                    self.add_flow(datapath, 10, match_c2s, actions_c2s, idle_timeout=60)
                    # self.logger.info(f"Installed C2S flow rule for {client_key}")

                    # Gửi gói tin hiện tại đi nếu nó được buffer và ta đã biết port
                    if msg.buffer_id != ofproto.OFP_NO_BUFFER:
                        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id, in_port=in_port, actions=actions_c2s, data=None)
                        datapath.send_msg(out)
                        # self.logger.debug("Sent current C2S packet using buffer_id and installed flow actions")

                    return # Kết thúc xử lý C2S

            # --- B. Server -> Client ---
            elif src_ip in SERVERS and dst_ip != VIRTUAL_IP:
                if client_port is not None and dst_port is not None: # Process only TCP/UDP
                    server_mac = src_mac
                    client_ip = dst_ip
                    client_key = (client_ip, client_port, dst_port, protocol)

                    if self.client_to_server_map.get(client_key) == server_mac:
                        client_mac = eth.dst
                        out_port = self.mac_to_port[dpid].get(client_mac)

                        if out_port is None:
                            self.logger.warning(f"Don't know out_port for client {client_mac}. Flooding return packet for {client_key}.")
                            action_flood = [parser.OFPActionOutput(ofproto.OFPP_FLOOD)]
                            out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                                   in_port=in_port, actions=action_flood,
                                                   data=msg.data if msg.buffer_id == ofproto.OFP_NO_BUFFER else None)
                            datapath.send_msg(out)
                            return # Đợi packet-in tiếp theo

                        # --- Chỉ thực hiện tiếp nếu biết out_port ---
                        # self.logger.info(f"Found out_port {out_port} for client {client_mac}")
                        # self.logger.info(f"Server->Client: Redirecting {src_ip}:{dst_port} -> {client_ip}:{client_port} back using VIP {VIRTUAL_IP}")

                        # Tạo và cài flow rule S2C
                        match_fields_s2c = { 'in_port': in_port, 'eth_type': ether_types.ETH_TYPE_IP, 'eth_src': server_mac, 'eth_dst': client_mac, 'ipv4_src': src_ip, 'ipv4_dst': client_ip, 'ip_proto': protocol }
                        if protocol == in_proto.IPPROTO_TCP: match_fields_s2c['tcp_src'], match_fields_s2c['tcp_dst'] = dst_port, client_port
                        elif protocol == in_proto.IPPROTO_UDP: match_fields_s2c['udp_src'], match_fields_s2c['udp_dst'] = dst_port, client_port
                        match_s2c = parser.OFPMatch(**match_fields_s2c)
                        actions_s2c = [ parser.OFPActionSetField(eth_src=VIRTUAL_MAC), parser.OFPActionSetField(ipv4_src=VIRTUAL_IP), parser.OFPActionOutput(out_port) ]
                        self.add_flow(datapath, 10, match_s2c, actions_s2c, idle_timeout=60)
                        # self.logger.info(f"Installed S2C flow rule for {client_key}")

                        # Xử lý giảm connection count
                        if LOAD_BALANCING_ALGORITHM == 'least_connection' and protocol == in_proto.IPPROTO_TCP:
                            tcp_header = pkt.get_protocol(tcp.tcp)
                            if tcp_header and tcp_header.bits & (tcp.TCP_FIN | tcp.TCP_RST):
                                server_ip_for_decrement = src_ip
                                if self.connection_counts[server_ip_for_decrement] > 0:
                                    self.connection_counts[server_ip_for_decrement] -= 1
                                    self.logger.info(f"[LeastConnection] FIN/RST detected from server {server_ip_for_decrement}. Decrementing count. New counts: {dict(self.connection_counts)}")
                                    # Cân nhắc xóa client_key khỏi map khi kết nối kết thúc hoàn toàn
                                    # if client_key in self.client_to_server_map:
                                    #     del self.client_to_server_map[client_key]
                                    #     self.logger.debug(f"Removed client map entry for {client_key}")


                        # Gửi gói tin hiện tại đi nếu được buffer
                        if msg.buffer_id != ofproto.OFP_NO_BUFFER:
                             out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id, in_port=in_port, actions=actions_s2c, data=None)
                             datapath.send_msg(out)
                             # self.logger.debug("Sent current S2C packet using buffer_id and installed flow actions")

                        return # Kết thúc xử lý S2C
                    # else: # Gói tin không khớp mapping -> Đi xuống xử lý mặc định
                    #      self.logger.debug(f"Packet from server {src_ip} to client {client_ip} has no/mismatched mapping for {client_key} and MAC {server_mac}. Using default forwarding.")
                    #      pass # Để đi xuống xử lý mặc định

            # --- C. Xử lý mặc định (L2 Forwarding) ---
            out_port = self.mac_to_port[dpid].get(dst_mac)
            if out_port:
                actions = [parser.OFPActionOutput(out_port)]
                # --- Bỏ comment để cài flow L2 forwarding, tăng hiệu quả ---
                match = parser.OFPMatch(in_port=in_port, eth_dst=dst_mac) # Match đơn giản hơn
                self.add_flow(datapath, 1, match, actions, idle_timeout=10, hard_timeout=30) # Priority thấp, timeout ngắn
                # self.logger.debug(f"Installed L2 forwarding flow: {src_mac} -> {dst_mac} via port {out_port}")

                data = msg.data if msg.buffer_id == ofproto.OFP_NO_BUFFER else None
                out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id, in_port=in_port, actions=actions, data=data)
                datapath.send_msg(out)
            else: # Flood nếu không biết MAC đích
                actions = [parser.OFPActionOutput(ofproto.OFPP_FLOOD)]
                data = msg.data if msg.buffer_id == ofproto.OFP_NO_BUFFER else None
                out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id, in_port=in_port, actions=actions, data=data)
                datapath.send_msg(out)
                # self.logger.debug(f"Flooding packet - Unknown destination MAC: {dst_mac}")


# --- WSGI Controller để nhận dữ liệu Telemetry ---
class TelemetryController(ControllerBase):
    def __init__(self, req, link, data, **config):
        super(TelemetryController, self).__init__(req, link, data, **config)
        self.load_balancer_app = data[LB_INSTANCE_NAME]

    @route('telemetry', '/telemetry/cpu', methods=['POST'])
    def receive_cpu_data(self, req, **kwargs):
        try:
            # --- Thêm kiểm tra content type ---
            if req.content_type != 'application/json':
                 self.load_balancer_app.logger.warning(f"API received non-JSON CPU data. Content-Type: {req.content_type}")
                 return Response(status=415, body="Unsupported Media Type: Expected application/json")
            data = req.json_body
            # self.load_balancer_app.logger.debug(f"API received CPU data: {data}")
            self.load_balancer_app.update_telemetry('cpu', data)
            return Response(status=200)
        except ValueError: # Lỗi parse JSON
            self.load_balancer_app.logger.error(f"API Error processing CPU data: Invalid JSON received.")
            return Response(status=400, body="Bad Request: Invalid JSON")
        except Exception as e:
            self.load_balancer_app.logger.error(f"API Error processing CPU data: {e}", exc_info=True)
            return Response(status=500)

    @route('telemetry', '/telemetry/latency', methods=['POST'])
    def receive_latency_data(self, req, **kwargs):
        try:
            if req.content_type != 'application/json':
                 self.load_balancer_app.logger.warning(f"API received non-JSON Latency data. Content-Type: {req.content_type}")
                 return Response(status=415, body="Unsupported Media Type: Expected application/json")
            data = req.json_body
            # self.load_balancer_app.logger.debug(f"API received Latency data: {data}")
            self.load_balancer_app.update_telemetry('latency', data)
            return Response(status=200)
        except ValueError: # Lỗi parse JSON
            self.load_balancer_app.logger.error(f"API Error processing Latency data: Invalid JSON received.")
            return Response(status=400, body="Bad Request: Invalid JSON")
        except Exception as e:
            self.load_balancer_app.logger.error(f"API Error processing Latency data: {e}", exc_info=True)
            return Response(status=500)

# --- Đảm bảo các import cần thiết cho state change handler ---
from ryu.controller.handler import DEAD_DISPATCHER