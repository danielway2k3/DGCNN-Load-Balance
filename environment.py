import numpy as np
import networkx as nx
from config import NETWORK_TOPOLOGY, TRAFFIC_PARAMS

class NetworkEnv:
    def __init__(self):
        self.topology = nx.Graph()
        self.topology.add_nodes_from(range(NETWORK_TOPOLOGY["nodes"]))
        self.topology.add_edges_from(NETWORK_TOPOLOGY["edges"])
        self.reset()

    def reset(self):
        # Reset network state (queues, load, delays, etc.)
        self.state = {node: {"throughput": np.random.uniform(1000, 2000),
                              "delay": np.random.uniform(0.1, 0.3)} for node in self.topology.nodes}
        return self.get_observations()

    def get_observations(self):
        # Return a dict of observations for each node/agent.
        observations = {}
        for node in self.topology.nodes:
            obs = [self.state[node]["throughput"], self.state[node]["delay"]]
            # Expand observations based on flow classes if needed.
            observations[node] = np.array(obs, dtype=np.float32)
        return observations

    def step(self, actions):
        # actions: a dict mapping node/agent to its action (load balancing weight adjustments, etc.)
        rewards = {}
        # Update network state based on actions
        for node, action in actions.items():
            self.state[node]["throughput"] += np.random.uniform(-50, 50)
            self.state[node]["delay"] += np.random.uniform(-0.01, 0.01)
            # Calculate a simple reward (throughput minus penalty on delay deviation)
            desired_delay = 0.5  # Example reference delay
            delay_penalty = abs(desired_delay - self.state[node]["delay"])
            rewards[node] = self.state[node]["throughput"] - 100 * delay_penalty

        next_obs = self.get_observations()
        done = False  # You can define a termination condition
        return next_obs, rewards, done