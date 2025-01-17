"""
Test the ML based interaction model.
"""

import flax.linen as nn
import numpy as np
import optax
from numpy.testing import assert_array_almost_equal, assert_array_equal

import swarmrl as srl
from swarmrl.actions import Action
from swarmrl.agents import ActorCriticAgent
from swarmrl.components import Colloid
from swarmrl.force_functions import ForceFunction
from swarmrl.networks.flax_network import FlaxModel
from swarmrl.sampling_strategies.categorical_distribution import CategoricalDistribution


def _action_to_index(action):
    """
    Convert an action to an index for this test.
    """
    if action.force != 0.0:
        return 0
    elif action.torque[-1] == 0.1:
        return 1
    elif action.torque[-1] == -0.1:
        return 2
    else:
        return 3


class FlaxNet(nn.Module):
    """A simple dense model."""

    @nn.compact
    def __call__(self, x):
        x = nn.Dense(features=12)(x)
        x = nn.relu(x)
        x = nn.Dense(features=12)(x)
        x = nn.relu(x)
        x = nn.Dense(features=12)(x)
        x = nn.relu(x)
        y = nn.Dense(features=1)(x)
        x = nn.Dense(features=4)(x)
        return x, y


class DummyTask(srl.tasks.Task):
    """
    Dummy task for the test
    """

    def __call__(self, data):
        """
        Dummy call method.
        """
        return [1.0 for item in data if item.type == 1]


class SecondDummyTask(srl.tasks.Task):
    """
    Dummy task for the test
    """

    def __call__(self, data):
        """
        Dummy call method.
        """
        return [5.0 for item in data if item.type == 1]


class TestMLModel:
    """
    Test the ML interaction model to ensure it is functioning correctly.
    """

    @classmethod
    def setup_class(cls):
        """
        Prepare the test suite.
        """
        observable = srl.observables.PositionObservable(
            box_length=np.array([1000, 1000, 1000])
        )
        network = FlaxModel(
            flax_model=FlaxNet(),
            input_shape=(3,),
            optimizer=optax.sgd(0.001),
            rng_key=6862168,
            exploration_policy=srl.exploration_policies.RandomExploration(
                probability=0.0
            ),
            sampling_strategy=CategoricalDistribution(),
        )
        second_network = FlaxModel(
            flax_model=FlaxNet(),
            input_shape=(3,),
            optimizer=optax.sgd(0.001),
            rng_key=6862168,
            exploration_policy=srl.exploration_policies.RandomExploration(
                probability=0.0
            ),
            sampling_strategy=CategoricalDistribution(),
        )
        translate = Action(force=10.0)
        rotate_clockwise = Action(torque=np.array([0.0, 0.0, 15.0]))
        rotate_counter_clockwise = Action(torque=np.array([0.0, 0.0, -15.0]))
        do_nothing = Action()

        cls.action_space = {
            "RotateClockwise": rotate_clockwise,
            "Translate": translate,
            "RotateCounterClockwise": rotate_counter_clockwise,
            "DoNothing": do_nothing,
        }
        agent_1 = ActorCriticAgent(
            particle_type=0,
            network=network,
            actions=cls.action_space,
            task=DummyTask(),
            observable=observable,
        )
        agent_2 = ActorCriticAgent(
            particle_type=1,
            network=second_network,
            actions=cls.action_space,
            task=SecondDummyTask(),
            observable=observable,
        )

        cls.interaction = ForceFunction(
            agents={
                "0": agent_1,
            },
        )

        cls.multi_interaction = ForceFunction(
            agents={
                "0": agent_1,
                "2": agent_2,
            },
        )

    def test_species_and_order_handling(self):
        """
        Test species and paricle actions are returned correctly.
        """
        for agent in self.interaction.agents.values():
            agent.reset_trajectory()
        for agent in self.multi_interaction.agents.values():
            agent.reset_trajectory()

        colloid_1 = Colloid(
            np.array([3, 7, 1]), np.array([0, 0, 1]), 0, np.array([0, 0, 0]), 1
        )
        colloid_2 = Colloid(
            np.array([1, 1, 0]), np.array([0, 0, -1]), 1, np.array([0, 0, 0]), 0
        )
        colloid_3 = Colloid(
            np.array([100, 27, 0.222]), np.array([0, 0, 1]), 2, np.array([0, 0, 0]), 2
        )

        actions = self.multi_interaction.calc_action(
            [colloid_1, colloid_2, colloid_3],
        )

        # Check that the second action is correct
        actions[1].force == 0.0
        assert_array_equal(actions[0].torque, np.array([0.0, 0.0, 0.0]))

        # Check reward data
        loaded_data_0 = self.multi_interaction.agents["0"].trajectory
        loaded_data_2 = self.multi_interaction.agents["2"].trajectory

        loaded_data_0 = loaded_data_0.rewards[0][0]
        loaded_data_2 = loaded_data_2.rewards[0][0]
        assert loaded_data_2 == 5.0
        assert loaded_data_0 == 1.0

    def test_file_saving(self):
        """
        Test that classes are saved correctly.
        """
        for agent in self.interaction.agents.values():
            agent.reset_trajectory()
        for agent in self.multi_interaction.agents.values():
            agent.reset_trajectory()

        colloid_1 = Colloid(
            np.array([3, 7, 1]), np.array([0, 0, 1]), 0, np.array([0, 0, 0]), 0
        )
        colloid_2 = Colloid(
            np.array([1, 1, 0]), np.array([0, 0, -1]), 1, np.array([0, 0, 0]), 0
        )
        colloid_3 = Colloid(
            np.array([100, 27, 0.222]), np.array([0, 0, 1]), 2, np.array([0, 0, 0]), 0
        )

        self.interaction.record_traj = True
        self.interaction.calc_action([colloid_1, colloid_2, colloid_3])

        # Check that data is stored correctly
        data = self.interaction.agents["0"].trajectory
        data = data.features

        # Colloid 1
        assert_array_almost_equal(data[0][0], colloid_1.pos / 1000.0)

        # Colloid 2
        assert_array_almost_equal(data[0][1], colloid_2.pos / 1000.0)

        # Colloid 3
        assert_array_almost_equal(data[0][2], colloid_3.pos / 1000.0)

        # Check for additional colloid addition
        colloid_1 = Colloid(
            np.array([9, 1, 6]), np.array([0, 0, -1.0]), 0, np.array([0, 0, 0]), 0
        )
        colloid_2 = Colloid(
            np.array([8, 8, 8]), np.array([0, 0, 1.0]), 1, np.array([0, 0, 0]), 0
        )
        colloid_3 = Colloid(
            np.array([-4.7, 3, -0.222]),
            np.array([0, 0, -1.0]),
            2,
            np.array([0, 0, 0]),
            0,
        )

        self.interaction.calc_action([colloid_1, colloid_2, colloid_3])

        # Check that data is stored correctly
        data = self.interaction.agents["0"].trajectory
        data = data.features

        # Colloid 1
        assert_array_almost_equal(data[1][0], colloid_1.pos / 1000.0)

        # Colloid 2
        assert_array_almost_equal(data[1][1], colloid_2.pos / 1000.0)

        # Colloid 3
        assert_array_almost_equal(data[1][2], colloid_3.pos / 1000.0)
