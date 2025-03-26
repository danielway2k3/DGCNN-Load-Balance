import pandas as pd
import matplotlib.pyplot as plt
import os
import seaborn as sns

def plot_training_metrics(csv_path, save_dir=None):
    """
    Generate visualizations for training metrics.
    
    Args:
        csv_path (str): Path to the CSV file containing training metrics
        save_dir (str, optional): Directory to save the plots. If None, plots are shown.
    """
    # Set plot style
    sns.set_theme(style="darkgrid")
    
    # Read the CSV file
    df = pd.read_csv(csv_path)
    
    # Create a figure with multiple subplots
    fig, axes = plt.subplots(2, 1, figsize=(12, 12), sharex=True)
    
    # Plot 1: Average Reward per Episode
    df_rewards = df.groupby('episode')['avg_reward'].mean().reset_index()
    sns.lineplot(data=df_rewards, x='episode', y='avg_reward', ax=axes[0], color='blue', linewidth=2)
    axes[0].set_title('Average Reward per Episode')
    axes[0].set_ylabel('Reward')
    axes[0].grid(True)
    
    # Add min-max rewards as shaded region
    df_rewards_min = df.groupby('episode')['min_reward'].min().reset_index()
    df_rewards_max = df.groupby('episode')['max_reward'].max().reset_index()
    axes[0].fill_between(df_rewards_min['episode'], df_rewards_min['min_reward'], 
                         df_rewards_max['max_reward'], alpha=0.2, color='blue')
    
    # Plot 2: Average Loss per Episode
    df_loss = df.groupby('episode')['avg_loss'].mean().reset_index()
    sns.lineplot(data=df_loss, x='episode', y='avg_loss', ax=axes[1], color='red', linewidth=2)
    axes[1].set_title('Average Loss per Episode')
    axes[1].set_xlabel('Episode')
    axes[1].set_ylabel('Loss')
    axes[1].grid(True)
    
    # Set tight layout
    plt.tight_layout()
    
    # Save or show the plots
    if save_dir:
        os.makedirs(save_dir, exist_ok=True)
        plot_path = os.path.join(save_dir, f"training_plots_{os.path.basename(csv_path).split('.')[0]}.png")
        plt.savefig(plot_path, dpi=300, bbox_inches='tight')
        print(f"Plots saved to {plot_path}")
        return plot_path
    else:
        plt.show()
        return None

def plot_reward_distribution(csv_path, save_dir=None):
    """
    Generate a histogram of rewards distribution.
    
    Args:
        csv_path (str): Path to the CSV file containing training metrics
        save_dir (str, optional): Directory to save the plots. If None, plots are shown.
    """
    # Set plot style
    sns.set_theme(style="darkgrid")
    
    # Read the CSV file
    df = pd.read_csv(csv_path)
    
    # Create a figure
    plt.figure(figsize=(10, 6))
    
    # Plot reward distribution
    sns.histplot(data=df, x='avg_reward', kde=True)
    plt.title('Distribution of Average Rewards')
    plt.xlabel('Average Reward')
    plt.ylabel('Frequency')
    plt.grid(True)
    
    # Save or show the plot
    if save_dir:
        os.makedirs(save_dir, exist_ok=True)
        plot_path = os.path.join(save_dir, f"reward_distribution_{os.path.basename(csv_path).split('.')[0]}.png")
        plt.savefig(plot_path, dpi=300, bbox_inches='tight')
        print(f"Plot saved to {plot_path}")
        return plot_path
    else:
        plt.show()
        return None