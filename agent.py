import torch
import torch.nn as nn
import torch.nn.functional as F
from config import AGENT_PARAMS

class Encoder(nn.Module):
    def __init__(self, input_dim, hidden_dims):
        super(Encoder, self).__init__()
        layers = []
        in_dim = input_dim
        for h in hidden_dims:
            layers.append(nn.Linear(in_dim, h))
            layers.append(nn.ReLU())
            in_dim = h
        self.encoder = nn.Sequential(*layers)
    
    def forward(self, x):
        return self.encoder(x)

class GraphConvLayer(nn.Module):
    def __init__(self, in_dim, out_dim, num_heads):
        super(GraphConvLayer, self).__init__()
        self.num_heads = num_heads
        self.attention = nn.MultiheadAttention(embed_dim=in_dim, num_heads=num_heads)
        self.linear = nn.Linear(in_dim, out_dim)
    
    def forward(self, x, neighbor_features):
        # x: feature of the current agent, neighbor_features: features from neighbors
        
        # Ensure proper dimensions for attention mechanism
        # Required shape for attention: (seq_len, batch, feature_dim)
        
        # Process x (current agent features)
        if len(x.shape) == 1:  # [feature_dim]
            x = x.unsqueeze(0).unsqueeze(0)  # [1, 1, feature_dim]
        elif len(x.shape) == 2:  # [batch, feature_dim]
            x = x.unsqueeze(0)  # [1, batch, feature_dim]
        
        # Process neighbor_features
        if len(neighbor_features.shape) == 2:  # [num_neighbors, feature_dim]
            neighbor_features = neighbor_features.unsqueeze(1)  # [num_neighbors, 1, feature_dim]
        
        # Concatenate without additional unsqueeze - THIS IS THE KEY FIX
        features = torch.cat([x, neighbor_features], dim=0)
        
        attn_output, _ = self.attention(features, features, features)
        # Get the first sequence element (corresponds to current agent)
        out = self.linear(attn_output[0])
        return out

class QNetwork(nn.Module):
    def __init__(self, feature_dim, action_dim):
        super(QNetwork, self).__init__()
        self.fc1 = nn.Linear(feature_dim, 128)
        self.fc2 = nn.Linear(128, action_dim)
    
    def forward(self, features):
        x = F.relu(self.fc1(features))
        return self.fc2(x)

class DGNAgent(nn.Module):
    def __init__(self, input_dim, action_dim):
        super(DGNAgent, self).__init__()
        self.encoder = Encoder(input_dim, AGENT_PARAMS["encoder_layers"])
        # For simplicity, assume one graph conv layer. You can stack more.
        self.graph_conv = GraphConvLayer(AGENT_PARAMS["encoder_layers"][-1],
                                        AGENT_PARAMS["encoder_layers"][-1],
                                        AGENT_PARAMS["attention_heads"])
        self.q_network = QNetwork(AGENT_PARAMS["encoder_layers"][-1], action_dim)
    
    def forward(self, obs, neighbor_obs):
        # obs: observation of the current agent, neighbor_obs: list/tensor of neighbors' observations
        encoded = self.encoder(obs)
        # Assume neighbor_obs is a tensor of shape [num_neighbors, feature_dim]
        encoded_neighbors = self.encoder(neighbor_obs)
        features = self.graph_conv(encoded, encoded_neighbors)
        q_values = self.q_network(features)
        return q_values
