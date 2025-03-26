# Network Environment Parameters
NETWORK_TOPOLOGY = {
    "nodes": 12,
    "edges": [(0,1), (1,2), (2,3), (3,4), (4,5), (5,0)],
    # Add more detailed topology configurations as needed
}

TRAFFIC_PARAMS = {
    "flow_classes": {"gold": {"throughput": 3000, "delay": 0.2},
                     "silver": {"throughput": 1200, "delay": 0.5},
                     "bronze": {"throughput": 500, "delay": 1.0}},
    "packet_rate": [900, 1200],  # packets per second range
    "packet_size": 512,          # in bytes
}

# Agent Parameters
AGENT_PARAMS = {
    "encoder_layers": [128, 128],
    "conv_layers": 2,
    "attention_heads": 8,
    "target_update_rate": 0.01,
    "discount_factor": 0.99,
    "batch_size": 32,
    "epsilon": 0.1,  # exploration rate
    "policy_refresh_period": 10  # seconds per decision
}

# Training Parameters
TRAINING_PARAMS = {
    "max_episodes": 100,
    "max_steps": 100,  # steps per episode
    "learning_rate": 0.001,
}
