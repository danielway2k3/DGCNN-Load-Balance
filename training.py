import numpy as np
import torch
import torch.optim as optim
from agent import DGNAgent
from replay_buffer import ReplayBuffer
from config import AGENT_PARAMS, TRAINING_PARAMS
import csv
import os
from datetime import datetime

def train_agent(env, num_agents, input_dim, action_dim):
    agents = {i: DGNAgent(input_dim, action_dim) for i in range(num_agents)}
    target_agents = {i: DGNAgent(input_dim, action_dim) for i in range(num_agents)}
    # Copy initial parameters from agents to target networks.
    for i in range(num_agents):
        target_agents[i].load_state_dict(agents[i].state_dict())

    optimizers = {i: optim.Adam(agents[i].parameters(), lr=TRAINING_PARAMS["learning_rate"]) for i in range(num_agents)}
    replay_buffer = ReplayBuffer()
    
    # Create metrics tracking containers
    metrics = {
        'episode': [],
        'step': [],
        'avg_reward': [],
        'avg_loss': [],
        'min_reward': [],
        'max_reward': []
    }
    
    for episode in range(TRAINING_PARAMS["max_episodes"]):
        state = env.reset()  # state is a dict: node -> observation
        episode_rewards = []
        episode_losses = []
        
        for step in range(TRAINING_PARAMS["max_steps"]):
            actions = {}
            for i in range(num_agents):
                # Example: select action randomly or via ε-greedy from Q-network
                obs = torch.tensor(state[i]).float().unsqueeze(0)
                # In a full implementation, get neighbor observations from env.
                neighbor_obs = torch.tensor(np.array([state[j] for j in range(num_agents) if j != i])).float()
                q_values = agents[i](obs, neighbor_obs)
                # Select action (here simply argmax for demonstration)
                action = q_values.argmax().item()
                actions[i] = action

            next_state, rewards, done = env.step(actions)
            
            # Track rewards
            episode_rewards.append(sum(rewards.values()) / len(rewards))
            
            # Here, create an adjacency matrix (or neighbor list) for the graph convolution.
            # For simplicity, we use an identity matrix (or any fixed structure).
            adj_matrix = None  # Replace with actual neighbor relationships.
            
            for i in range(num_agents):
                replay_buffer.push(state[i], actions[i], rewards[i], next_state[i], adj_matrix)
            
            state = next_state
            
            # Train if buffer is large enough.
            if len(replay_buffer) >= AGENT_PARAMS["batch_size"]:
                states, actions_batch, rewards_batch, next_states, adjs = replay_buffer.sample(AGENT_PARAMS["batch_size"])
                # Convert these into tensors and compute loss for each agent.
                # Here, a loop for each agent is shown. In practice, you might vectorize the operations.
                step_losses = []
                for i in range(num_agents):
                    # This is a simplified loss computation (MSE between target and Q-value)
                    obs_tensor = torch.tensor(states[i]).float().unsqueeze(0)
                    neighbor_tensor = torch.tensor(np.array([states[j] for j in range(len(states)) if j != i])).float()
                    q_val = agents[i](obs_tensor, neighbor_tensor)  # Replace neighbor input appropriately
                    target = rewards_batch[i]  # Replace with proper target calculation using target_agents
                    loss = (q_val[0, actions_batch[i]] - target) ** 2
                    optimizers[i].zero_grad()
                    loss.backward()
                    optimizers[i].step()
                    
                    step_losses.append(loss.item())
                    
                    # Soft update target network
                    for target_param, param in zip(target_agents[i].parameters(), agents[i].parameters()):
                        target_param.data.copy_(AGENT_PARAMS["target_update_rate"] * param.data + 
                                                (1 - AGENT_PARAMS["target_update_rate"]) * target_param.data)
                
                # Track average loss for this step
                episode_losses.append(sum(step_losses) / len(step_losses))
            
            # Record metrics for this step
            metrics['episode'].append(episode)
            metrics['step'].append(step)
            metrics['avg_reward'].append(episode_rewards[-1])
            metrics['avg_loss'].append(episode_losses[-1] if episode_losses else 0)
            metrics['min_reward'].append(min(rewards.values()))
            metrics['max_reward'].append(max(rewards.values()))
            
            if done:
                break

        # Print episode summary
        avg_episode_reward = sum(episode_rewards) / len(episode_rewards)
        avg_episode_loss = sum(episode_losses) / len(episode_losses) if episode_losses else 0
        print(f"Episode {episode}: Avg Reward = {avg_episode_reward:.2f}, Avg Loss = {avg_episode_loss:.4f}")

    # Save metrics to CSV
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f'training_metrics_{timestamp}.csv')
    
    with open(csv_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=metrics.keys())
        writer.writeheader()
        for i in range(len(metrics['episode'])):
            writer.writerow({k: metrics[k][i] for k in metrics.keys()})
    
    print(f"Training metrics saved to {csv_path}")
    
    return agents, target_agents, csv_path