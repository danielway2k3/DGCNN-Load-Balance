import random
from collections import deque

class ReplayBuffer:
    def __init__(self, capacity=10000):
        self.capacity = capacity
        self.buffer = deque(maxlen=capacity)

    def push(self, state, action, reward, next_state, adj_matrix):
        self.buffer.append((state, action, reward, next_state, adj_matrix))

    def sample(self, batch_size):
        batch = random.sample(self.buffer, batch_size)
        state, action, reward, next_state, adj = map(list, zip(*batch))
        return state, action, reward, next_state, adj

    def __len__(self):
        return len(self.buffer)