"""Test cases for the base environment class.
"""

import pytest
from predicators.src.envs import BaseEnv
from predicators.src.structs import State, Type


def test_base_env():
    """Tests for BaseEnv class.
    """
    cup_type = Type("cup_type", ["feat1"])
    plate_type = Type("plate_type", ["feat1", "feat2"])
    cup = cup_type("cup")
    plate = plate_type("plate")
    state = State({cup: [0.5], plate: [1.0, 1.2]})
    env = BaseEnv()
    env.seed(123)
    # Check that methods are abstract.
    with pytest.raises(NotImplementedError):
        env.simulate(state, [1, 2])
    with pytest.raises(NotImplementedError):
        env.get_train_tasks()
    with pytest.raises(NotImplementedError):
        env.get_test_tasks()
    with pytest.raises(NotImplementedError):
        env.predicates()
    with pytest.raises(NotImplementedError):
        env.options()
    with pytest.raises(NotImplementedError):
        env.action_space()