"""
Integration test for the genetic algorithm training.
"""

import tempfile
import unittest as ut

import flax.linen as nn
import numpy as np
import optax
import pint

import swarmrl as srl
from swarmrl.actions import Action


# Helper definitions.
def get_simulation_runner():
    """
    Collect a simulation runner.
    """
    simulation_name = "training"
    seed = int(np.random.uniform(1, 100))

    temperature = 297.15
    n_colloids = 3

    ureg = pint.UnitRegistry()
    md_params = srl.espresso.MDParams(
        ureg=ureg,
        fluid_dyn_viscosity=ureg.Quantity(8.9e-4, "pascal * second"),
        WCA_epsilon=ureg.Quantity(temperature, "kelvin") * ureg.boltzmann_constant,
        temperature=ureg.Quantity(300.0, "kelvin"),
        box_length=ureg.Quantity(1000, "micrometer"),
        time_slice=ureg.Quantity(0.5, "second"),  # model timestep
        time_step=ureg.Quantity(0.5, "second") / 5,  # integrator timestep
        write_interval=ureg.Quantity(2, "second"),
    )

    system_runner = srl.espresso.EspressoMD(
        md_params=md_params,
        n_dims=2,
        seed=seed,
        out_folder=simulation_name,
        write_chunk_size=100,
    )

    coll_type = 0
    system_runner.add_colloids(
        n_colloids,
        ureg.Quantity(2.14, "micrometer"),
        ureg.Quantity(np.array([500, 500, 0]), "micrometer"),
        ureg.Quantity(400, "micrometer"),
        type_colloid=coll_type,
    )

    return system_runner


class Network(nn.Module):
    """A simple dense model."""

    @nn.compact
    def __call__(self, x):
        x = nn.Dense(features=128)(x)
        x = nn.relu(x)
        y = nn.Dense(features=1)(x)
        x = nn.Dense(features=4)(x)
        return x, y


def scale_function(distance: float):
    """
    Scaling function for the task
    """
    return 1 - distance


class TestGeneticTraining(ut.TestCase):
    """
    Test suite for the genetic training.
    """

    def test_run(self):
        """
        Prepare the test.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            # Exploration policy
            exploration_policy = srl.exploration_policies.RandomExploration(
                probability=0.0
            )

            # Sampling strategy
            sampling_strategy = srl.sampling_strategies.GumbelDistribution()

            # Set the task
            task = srl.tasks.searching.GradientSensing(
                source=np.array([500.0, 500.0, 0.0]),
                decay_function=scale_function,
                reward_scale_factor=10,
                box_length=np.array([1000.0, 1000.0, 1000]),
            )
            observable = srl.observables.ConcentrationField(
                source=np.array([500.0, 500.0, 0.0]),
                decay_fn=scale_function,
                scale_factor=10,
                box_length=np.array([1000.0, 1000.0, 1000]),
            )

            # Define the loss model
            loss = srl.losses.ProximalPolicyLoss(n_epochs=2)

            network = srl.networks.FlaxModel(
                flax_model=Network(),
                optimizer=optax.adam(learning_rate=0.001),
                input_shape=(1,),
                sampling_strategy=sampling_strategy,
                exploration_policy=exploration_policy,
            )

            translate = Action(force=10.0)
            rotate_clockwise = Action(torque=np.array([0.0, 0.0, 10.0]))
            rotate_counter_clockwise = Action(torque=np.array([0.0, 0.0, -10.0]))
            do_nothing = Action()

            actions = {
                "RotateClockwise": rotate_clockwise,
                "Translate": translate,
                "RotateCounterClockwise": rotate_counter_clockwise,
                "DoNothing": do_nothing,
            }

            protocol = srl.agents.ActorCriticAgent(
                particle_type=0,
                network=network,
                task=task,
                observable=observable,
                actions=actions,
            )

            rl_trainer = srl.trainers.ContinuousTrainer(
                [protocol],
                loss,
            )
            self.training_routine = srl.training_routines.GeneticTraining(
                rl_trainer,
                get_simulation_runner,
                n_episodes=5,
                output_directory=temp_dir,
                episode_length=5,
                number_of_generations=3,
                population_size=4,
                number_of_parents=3,
                parallel_jobs=1,
            )

            self.training_routine.train_model()


if __name__ == "__main__":
    ut.main()
