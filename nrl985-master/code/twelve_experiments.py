import numpy as np
from copy import deepcopy
from hyperparameters import evaluation_hyperparameters, train_hyperparameters, agent_hyperparameters, AgentType
from train import _set_up
from show import episode_play_normal_marl
from file_management import save
import matplotlib.pyplot as plt
import numpy as np
from hyperparameters import train_hyperparameters, agent_hyperparameters, dynamic_hyperparameters, AgentType
from env import create_env
from create_agents import create_agents
from utils import encode_state
from file_management import save
from reward_functions import final_reward
import numpy as np
import math
from adjacency import convert_adj_to_power_graph
from ucb_marl_agent import MARL_Comm

NUMBER_OF_TRIALS = evaluation_hyperparameters['num_of_trials']
NUM_EVALUATION_EPISODES = evaluation_hyperparameters['num_evaluation_episodes']
EVALUATION_INTERVAL = evaluation_hyperparameters['evaluation_interval']
NUM_OF_EPISODES = train_hyperparameters['num_of_episodes']
NUM_OF_AGENTS = agent_hyperparameters['num_of_agents']
LOCAL_RATIO = train_hyperparameters['local_ratio']
NUM_OF_CYCLES = train_hyperparameters['num_of_cycles']

def _episode_original_multiple(env, agents, episode_num, oracle=None):

    """
    This trains the original Lidard algorithm for MARL agents for one episode

    env - The parallel environment to be used

    agents - A dict containing the agents to be used

    episode_num - The episode number

    Return 
    The reward for that episode
    """
    
    agent_old_state = {agent: -1 for agent in agents.keys()}
    observations = env.reset()    

    t = 0
    while env.agents:
        t = t+1
        actions = {}
        for agent_name in agents.keys():        # Take action
            real_state = observations[agent_name]
            agent_old_state[agent_name] = encode_state(observations[agent_name], NUM_OF_AGENTS)
            action = _policy(agent_name, agents, observations[agent_name], False, t, episode_num)
            actions[agent_name] = action
            if oracle is not None: 
                oracle.update(agent_old_state[agent_name], action) #Update the oracle with the state-action pair
                oracle.update_real_state_map(agent_old_state[agent_name], real_state) # Update the oracle with the real state
            
            
        observations, rewards, terminations, truncations, infos = env.step(actions)
  
        for agent_name in agents.keys():        # Send messages
            agent_obj = agents[agent_name]
            agent_obj.message_passing(episode_num, t, agent_old_state[agent_name], actions[agent_name], 
                encode_state(observations[agent_name], NUM_OF_AGENTS), rewards[agent_name], agents)

        for agent_name in agents.keys():        # Update u and v
            agent_obj = agents[agent_name]
            agent_obj.update(episode_num, t, agent_old_state[agent_name], encode_state(observations[agent_name], NUM_OF_AGENTS),
                actions[agent_name], rewards[agent_name])
            
        for agent_name in agents.keys():       # Update the values
            agent_obj = agents[agent_name]
            agent_obj.update_values(episode_num, t)
    
    return final_reward(rewards)

def _set_up(experiment):

    """
    Sets up the environments and agents

    choice - The type of Agent to use

    Return
    The agent_type
    The environment set up
    Dictionary of agents
    The function to train the agents on
    """

    train_choice = _episode_original_multiple
    agent_type = AgentType.ORIGINAL
    multiple=True
    adj_table =  experiment['graph']
    
        
    
    env = create_env(NUM_OF_AGENTS, NUM_OF_CYCLES, LOCAL_RATIO, multiple)
    # agents = create_agents(NUM_OF_AGENTS, agent_type, num_of_episodes=NUM_OF_EPISODES, length_of_episode=NUM_OF_CYCLES)
    agents = create_exp_marl_agents(NUM_OF_AGENTS, NUM_OF_EPISODES, NUM_OF_CYCLES, 
        experiment['gamma_hop'], adj_table, experiment['connection_slow'])
    return agent_type, env, agents, train_choice


def create_exp_marl_agents(num_of_agents, num_of_episodes, length_of_episode, gamma_hop, adjacency_table, connection_slow):

    """
    Creates the MARL agents

    num_of_agents - The Number of agents to be created

    num_of_episodes - The number of episodes to play

    length_of_episode - The length of the episode

    gamma_hop - The gamma hop distance

    adjacency_table - The graph to be used

    connection_slow - Whether we want the connections to be instantaneous or whether a time delay should be incurred

    """

    agents = {f'agent_{i}': MARL_Comm(f'agent_{i}', num_of_agents, num_of_episodes, length_of_episode, gamma_hop) for i in range(num_of_agents)}

    
    power_graph = convert_adj_to_power_graph(adjacency_table, gamma_hop, connection_slow)
    if dynamic_hyperparameters['dynamic']:
        return agents
    
    print(power_graph)
    for i, row in enumerate(power_graph):
        for j, col in enumerate(row):
            if col != 0:
                agent_obj = agents[f'agent_{i}']
                agent_obj.update_neighbour(f'agent_{j}', col)

    return agents


def twelve_experiments(experiment, choice):
    # This is the reward from each episode
    reward_array_cumulative = np.array([np.zeros(6) for i in range(NUM_OF_EPISODES)])

    # This is the reward from evaluation runs
    reward_list_evaluation = np.array([np.zeros(6) for i in range(NUM_OF_EPISODES//EVALUATION_INTERVAL)])

    # This contains all the evaluation episodes
    reward_array_episode_num = np.array([episode_num for episode_num in range(1,NUM_OF_EPISODES+1) if episode_num % EVALUATION_INTERVAL == 0 ])
    # episodes_array = np.array([i+1 for i in range(NUM_OF_EPISODES)])
    
    # best_joint_policy = {}
    # best_mean = -1000

    print(f'TOPOLOGY EXPERIMENTS: Training {NUM_OF_AGENTS} agents of type {choice} over {NUM_OF_EPISODES} episodes with trials {NUMBER_OF_TRIALS}')
    for trials_num in range(NUMBER_OF_TRIALS):
        agent_type, env, agents, train_choice = _set_up(experiment) #All we need is a custom set-up function
        evaluation_pos = 0
        for episode_num in range(1, NUM_OF_EPISODES+1):
            reward = train_choice(env, agents, episode_num-1, oracle=None)
            reward_array_cumulative[episode_num-1] = reward
            if episode_num % 100 == 0:
                print(trials_num, episode_num)

            # Evaluate how good the agents are every EVALUATION_INTERVAL
            if episode_num % EVALUATION_INTERVAL == 0:
                # print(f"Evaluating at episode number {episode_num}")
                cumulative_reward = reward_list_evaluation[evaluation_pos]
                reward_here = 0
                for episode in range(NUM_EVALUATION_EPISODES):
                    reward = episode_play_normal_marl(env, agents, NUM_OF_CYCLES, NUM_OF_AGENTS, render=False )
                    reward_here += reward
                    
                cumulative_reward += (reward_here/NUM_EVALUATION_EPISODES)
                reward_list_evaluation[evaluation_pos] = cumulative_reward
                evaluation_pos += 1

        
        # After each trial we get a mean reward for the set of agents
        cumulative_reward = 0
        for run in range(NUM_EVALUATION_EPISODES *10):
            reward = episode_play_normal_marl(env, agents, NUM_OF_CYCLES, NUM_OF_AGENTS, render=False )
            cumulative_reward += reward
        # mean_reward = cumulative_reward/(NUM_EVALUATION_EPISODES*10)

        # if sum(mean_reward)/6 > best_mean:
        #     best_joint_policy = deepcopy(agents)
        #     best_mean = sum(mean_reward)/6
            
        # if mean_reward/6 > best_mean:
        #     best_joint_policy = deepcopy(agents)
        #     best_mean = mean_reward/6

                
    # reward_array = reward_array_cumulative/NUMBER_OF_TRIALS
    reward_array_evaluation = reward_list_evaluation / NUMBER_OF_TRIALS

    return [reward_array_evaluation, reward_array_episode_num]
    # # Save all data
    # save(best_joint_policy, episodes_array, [reward_array, reward_array_evaluation, reward_array_episode_num], agent_type, NUM_OF_AGENTS, NUM_OF_CYCLES, NUM_OF_EPISODES, LOCAL_RATIO)
    
    # print(f'The Mean Reward is: {best_mean}')
    # return best_mean 

def _policy(agent_name, agents, observation, done, time_step, episode_num=0):

    """
    Chooses the action for the agent

    agent_name - The agent names
    
    agents - The dictionary of agents

    observations - What the agent can see

    done - Whether the agent is finished

    time_step - The timestep on

    episode_num=0 - The episode number.  Not used

    returns - The action for the agent to run"""

    if time_step > NUM_OF_CYCLES:
        return None
    if done:
        return None
    agent = agents[agent_name]
    #print(f'observation: {observation}')
    return agent.policy(encode_state(observation, NUM_OF_AGENTS), time_step)


import numpy as np
import matplotlib.pyplot as plt
import random


def experiment_pipeline(experiments, choice):
    experiment_rewards = []
    
    for experiment in experiments: 
        print(experiment['experiment_name'])
        experiment_reward = twelve_experiments(experiment, choice)
        experiment_rewards.append(experiment_reward)

    # Plot the results
    fig, ax = plt.subplots()
    ax.set_xlabel('Episode Number')
    ax.set_ylabel('Reward')
    ax.set_title('Test-time Rewards Over Episodes')
    ax.grid(True)

    for i, experiment in enumerate(experiments):
        rewards_array, episode_nums = experiment_rewards[i]
        average_rewards = np.mean(rewards_array, axis=1)  # Compute average reward across all columns for each row
        ax.plot(episode_nums, average_rewards, label=experiment['experiment_name'])

    ax.legend()
    
    random_number = random.randint(0, 999999999)

    # Append the random number to the filename
    filename = f'saved_data/figs/test_time_rewards_{random_number}.png'
    print(f"Figure saved as {filename}")
    # Save the plot with the new filename
    plt.savefig(filename)