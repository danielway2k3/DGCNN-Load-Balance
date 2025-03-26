from environment import NetworkEnv
from training import train_agent
from visualization import plot_training_metrics, plot_reward_distribution
from config import TRAFFIC_PARAMS
import os

def main():
    # Create results directory
    results_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results')
    os.makedirs(results_dir, exist_ok=True)
    
    # Initialize environment and train agent
    env = NetworkEnv()
    num_agents = env.topology.number_of_nodes()  # One agent per node.
    input_dim = 2  # Example: [throughput, delay]
    action_dim = 8  # Example: 8 discrete actions (e.g., for adjusting weights)
    
    print(f"Starting training with {num_agents} agents...")
    trained_agents, target_agents, metrics_csv = train_agent(env, num_agents, input_dim, action_dim)
    print("Training complete.")
    
    # Generate visualizations
    print("Generating training visualizations...")
    plot_path = plot_training_metrics(metrics_csv, results_dir)
    dist_path = plot_reward_distribution(metrics_csv, results_dir)
    
    print(f"Results saved to {results_dir}")
    print(f"Training metrics: {metrics_csv}")
    print(f"Training plots: {plot_path}")
    print(f"Reward distribution: {dist_path}")

if __name__ == '__main__':
    main()