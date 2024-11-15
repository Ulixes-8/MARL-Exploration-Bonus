from collections import defaultdict
import math
import random
from copy import deepcopy

from agent import Agent
from hyperparameters import ucb_marl_hyperparameters, agent_hyperparameters

from time import sleep 

class MARL_Comm(Agent):

    """The original algorithm with communication"""

    def __init__(self, agent_name, num_of_agents, num_of_episodes, length_of_episode, gamma_hop):


        """
        Creates the agent
        
        agent_name - The name of the agent
        
        num_of_agents - The number of agents being created
        
        num_of_episodes - The number of episodes to be trained on

        length_of_episode - The length of one episode

        gamma_hop - The gamma_hop distance for the agent
        """
        self.exploration_bonuses = []
        self.exploration_bonuses_detailed = []

        # The set of H number of Q-Tables.
        self.qTables = {i+1: defaultdict(lambda: defaultdict(lambda: length_of_episode)) for i in range(length_of_episode)}

        # This will contain the number of times each state action has been seen for each timestep
        self.nTables = {i+1: defaultdict(lambda: defaultdict(lambda: 0)) for i in range(length_of_episode)}

        # The u set (episode number is indexed from 0 whilst the timestep is indexed from 1)
        self.uSet = {i: {i+1: defaultdict(lambda: defaultdict(lambda: set())) for i in range(length_of_episode +gamma_hop+1)} for i in range(num_of_episodes)} 

        # The v set (episode number is indexed from 0 whilst the timestep is indexed from 1)
        self.vSet = {i: {i+1: defaultdict(lambda: defaultdict(lambda: set())) for i in range(length_of_episode+gamma_hop+1)} for i in range(-length_of_episode-1, num_of_episodes+round(gamma_hop%length_of_episode)+1)}

        self.next_add = set()

        # Of form agent_name, distance = 0 if no connection
        self._neighbours = {f'agent_{i}': 0 for i in range(num_of_agents)}   
        self._num_neighbours = 1
        super().__init__(agent_name)


        self.H = length_of_episode
        self.episodes = num_of_episodes
        
        # A constant which means bm,t can be solved
        self.c = ucb_marl_hyperparameters['c'] 
        
        # This corresponds to A 
        num_of_actions = 5 

        # This corresponds to S
        num_of_states = agent_hyperparameters['size_of_state_space']

        # This corresponds to T
        T = num_of_episodes*length_of_episode

        # The probablity of failure I believe
        small_prob = ucb_marl_hyperparameters['probability']           

        # This is a value used to control the bm,t value.  Actually small iota in paper
        self.l = math.log((num_of_states * num_of_actions * T * num_of_agents)/small_prob)  
        
        # The v-table values.  Set to H as this corresponds to the q tables currently.
        self.vTable = {j+1: defaultdict(lambda: self.H) for j in range(length_of_episode+1)}


    def get_exploration_bonuses_for_episode(self, episode_num, timesteps):
        bonuses = []
        if episode_num in self.exploration_bonuses_detailed:
            for timestep in timesteps:
                if timestep in self.exploration_bonuses_detailed[episode_num]:
                    bonuses.append(self.exploration_bonuses_detailed[episode_num][timestep])
        return bonuses    
    
    def update_neighbour(self, agent_to_update, connection_quality):

        """
        This updates the connection value in the neighbours dictionary.
        
        agent_to_update - The agent with a new connection to be updated to
        
        connection_quality - How long the distance is between agents
        """

        if self._neighbours[agent_to_update] == 0 and connection_quality != 0:
            self._num_neighbours +=1
        elif self._neighbours[agent_to_update] != 0 and connection_quality == 0:
            self._num_neighbours -= 1

        self._neighbours[agent_to_update] = connection_quality

    def policy(self, state, time_step):

        """
        This gets the next move to be played
        
        state - The current state we are in
        
        time_step - The time step in the episode

        Return
        The action to be taken
        """

        # Choose the largest value
        max_value = float('-inf')
        move = -1
        q_table = self.qTables[time_step]
        values = [0,1,2,3,4]
        random.shuffle(values) # Shuffled to get randomness at start
        for i in values:        
            if q_table[state][i] > max_value:
                max_value = q_table[state][i]
                move = i 
        return move

    
    def play_normal(self, state, time_step, *args):

        """
        Plays the episode for showing.  Plays the best action in the q-table
        
        state - The current state we are in
        
        time_step - The time step in the episode

        *args - Spare arguments.

        Return 
        The action to be taken
        """

        q_table = self.qTables[time_step]
        max_value = float('-inf')
        move = -1
        values = [0,1,2,3,4]
        random.shuffle(values)
        for i in values:        
            if q_table[state][i] > max_value:
                max_value = q_table[state][i]
                move = i 
        return move


    def choose_smallest_value(self, state, time_step):

        """
        This chooses the smallest value - either from the max value from the Q-Table or H

        state - The current state we are in
        
        time_step - The time step in the episode

        Return
        The smaller value
        """

        max_value = float('-inf')
        values = [0,1,2,3,4]
        random.shuffle(values)
        for i in values:
            if self.qTables[time_step][state][i] > max_value:
                max_value = self.qTables[time_step][state][i]
        return min(self.H, max_value)

    def message_passing(self, episode_num, time_step, old_state, action, current_state, reward, agents_dict):

        """
        This passes messages to other agents which this agent can communicate to.

        episode_num - The episode number the agent is in

        time_step - The time step the agent is in

        old_state - The state the agent was in

        action - The action taken

        current_state - The new state after the agent has taken

        reward - The reward for the agents move
        
        agents_dict - The agents dictionary
        """

        for agent in self._neighbours.keys():
            if self._neighbours[agent] != 0:
                agent_obj = agents_dict[agent]
                self.send_message(episode_num, time_step, old_state, action, current_state, reward, agent_obj, self._neighbours[agent])

        
    def update(self, episode_num, time_step, old_state, current_state, action, reward):

        """
        This updates the u set and v set using the set update rules

        episode_num - The episode number the agent is one

        time_step - The time step the agent is on

        old_state - The previous state the agent was on

        current_state - The state the agent is currently on

        action - The action the agent has taken

        reward - The reward gained by the action taken from the old_state
        """

        # Update the uset to contain the latest reward and current state
        old_set = self.uSet[episode_num][time_step][old_state][action]
        old_set.add((reward, current_state))
        self.uSet[episode_num][time_step][old_state][action] = old_set

        new_set = set()
        
        # Add the new data from other agents into vSet.  Only added in the vSet when it 'reaches' the agent (dis == 0).  Added into the vset at the episode and timestep of when the message was sent
        for message_data in self.next_add:
            time_step_other, episode_num_other, agent_name_other, current_state_other, action_other, next_state_other, reward_other, dis = message_data
            
            if dis == 0:

                old_set = self.vSet[episode_num_other][time_step_other][current_state_other][action_other]
                old_set.add((reward_other, next_state_other))
                self.vSet[episode_num_other][time_step_other][current_state_other][action_other] = old_set
            else:
                dis -= 1
                new_set.add(tuple([time_step_other, episode_num_other, agent_name_other, current_state_other, action_other, next_state_other, reward_other, dis]))

        self.next_add = new_set
        
        # Add everything into the vSet for the current episode and timestep
        for state in self.uSet[episode_num][time_step]:
            for act in self.uSet[episode_num][time_step][state]:
                for element in self.uSet[episode_num][time_step][state][act]:
                        reward_new, next_state = element
                        self.vSet[episode_num][time_step][state][action].add((reward_new, next_state))

        
    def update_values(self, episode_num_max, time_step_max):

        """
        This updates the q_table and the vTable

        episode_num_max - The episode the agent is on

        time_step_max - The time step the agent is on.  Not currently needed
        """


        # This will go over the previous and current episode number in the vSet.  This is because the message should reach the agent within one episode
        for episode_num in range(episode_num_max-1, episode_num_max+1):
            # Go over every timestep
            for time_step in range(1,self.H+1):
                # Go through the vSet
                for state in self.vSet[episode_num][time_step].keys():
                    for action in self.vSet[episode_num][time_step][state].keys():
                        # Updates as specified in the paper
                        for reward, next_state in self.vSet[episode_num][time_step][state][action]:
                            
                            self.nTables[time_step][state][action] = self.nTables[time_step][state][action] + 1

                            t = self.nTables[time_step][state][action]
                        
                            clique_size = self._num_neighbours
                            b = self.c * math.sqrt(((self.H**3) * self.l) / (clique_size*t))
                            
                            
                            self.exploration_bonuses.append(b)
                            alpha = (self.H+1)/(self.H+t) 
                            initial =(1-alpha) * self.qTables[time_step][state][action]
                            expected_future = alpha * (reward + self.vTable[time_step+1][next_state] + b)                            
                            new_score = initial + expected_future
                            self.qTables[time_step][state][action] = new_score

                            self.vTable[time_step][state] = self.choose_smallest_value(state, time_step)
                # Assume we have gone through all the data in the vSet at this episode and time step.  Means we can add new data (from other agents) but not reuse old data
                self.vSet[episode_num][time_step] = defaultdict(lambda: defaultdict(lambda: set()))

    def receive_message(self, message, dis):

        """
        This is how the agent should receive a message

        message - The tuple containing the message

        dis - How far away the agent sending the message is
        """

        # message is [time_step, episode_num, self.agent_name, current_state, action, next_state, reward]
        message_list = list(message)
        message_list.append(dis)
        self.next_add.add(tuple(message_list))

    def send_message(self, episode_num, time_step, current_state, action, next_state, reward, agent_obj, distance):

        """
        How an agent sends a message
        
        episode_num - The episode number

        time_step - The time step

        current_state - The old state the agent was on

        action - The action taken

        next_state - The state to be seen after the action is taken

        reward - The reward given

        agent_obj - The agent to send the message to

        distance - How far away the agent it

        """

        message_tuple = tuple([time_step, episode_num, self.agent_name(), current_state, action, next_state, reward])
        agent_obj.receive_message(message_tuple, distance)
