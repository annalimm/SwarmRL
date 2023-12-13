"""
Module for the EpisodicTrainer
"""

from typing import TYPE_CHECKING

import numpy as np
from rich.progress import BarColumn, Progress, TimeRemainingColumn

from swarmrl.trainers.trainer import Trainer

if TYPE_CHECKING:
    from espressomd import System


class EpisodicTrainer(Trainer):
    """
    Class for the simple MLP RL implementation.

    Attributes
    ----------
    rl_protocols : list(protocol)
            A list of RL protocols to use in the simulation.
    loss : Loss
            An optimization method to compute the loss and update the model.
    """

    _engine = None

    @property
    def engine(self):
        """
        Runner engine property.
        """
        return self._engine

    @engine.setter
    def engine(self, value):
        """
        Set the engine value.
        """
        self._engine = value

    def perform_rl_training(
        self,
        get_engine: callable,
        system: "System",
        n_episodes: int,
        episode_length: int,
        reset_frequency: int = 1,
        load_bar: bool = True,
    ):
        """
        Perform the RL training.

        Parameters
        ----------
        get_engine : callable
                Function to get the engine for the simulation.
        system_runner : espressomd.System
                Engine used to perform steps for each agent.
        n_episodes : int
                Number of episodes to use in the training.
        episode_length : int
                Number of time steps in one episode.
        reset_frequency : int (default=1)
                After how many episodes is the simulation reset.
        load_bar : bool (default=True)
                If true, show a progress bar.

        Notes
        -----
        If you are using semi-episodic training but your task kills the
        simulation, the system will be reset.
        """
        system_killed = False
        rewards = [0.0]
        current_reward = 0.0
        force_fn = self.initialize_training()

        progress = Progress(
            "Episode: {task.fields[Episode]}",
            BarColumn(),
            "Episode reward: {task.fields[current_reward]} Running Reward:"
            " {task.fields[running_reward]}",
            TimeRemainingColumn(),
        )

        with progress:
            task = progress.add_task(
                "Episodic Training",
                total=n_episodes,
                Episode=0,
                current_reward=current_reward,
                running_reward=np.mean(rewards),
                visible=load_bar,
            )
            for episode in range(n_episodes):

                # Check if the system should be reset.
                if episode % reset_frequency == 0 or system_killed:
                    self.engine = None
                    self.engine = get_engine(system)

                    # Initialize the tasks and observables.
                    for _, val in self.rl_protocols.items():
                        val.observable.initialize(self.engine.colloids)
                        val.task.initialize(self.engine.colloids)

                self.engine.integrate(episode_length, force_fn)

                trajectory_data = force_fn.trajectory_data
                switches = [item.killed for item in trajectory_data.values()]
                if any(switches):
                    system_killed = True
                else:
                    system_killed = False
                force_fn, current_reward = self.update_rl(
                    trajectory_data=trajectory_data
                )
                rewards.append(current_reward)

                episode += 1
                progress.update(
                    task,
                    advance=1,
                    Episode=episode,
                    current_reward=np.round(current_reward, 2),
                    running_reward=np.round(np.mean(rewards[-10:]), 2),
                )
                self.engine.finalize()

        return np.array(rewards)
