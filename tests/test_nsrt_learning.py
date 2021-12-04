"""Tests for NSRT learning.
"""

import time
from gym.spaces import Box
import numpy as np
from predicators.src.nsrt_learning import learn_nsrts_from_data, \
    unify_effects_and_options, segment_trajectory, learn_strips_operators
from predicators.src.structs import Type, Predicate, State, Action, \
    ParameterizedOption
from predicators.src import utils


def test_segment_trajectory():
    """Tests for segment_trajectory().
    """
    cup_type = Type("cup_type", ["feat1"])
    cup0 = cup_type("cup0")
    cup1 = cup_type("cup1")
    cup2 = cup_type("cup2")
    pred0 = Predicate("Pred0", [cup_type],
                      lambda s, o: s[o[0]][0] > 0.5)
    pred1 = Predicate("Pred1", [cup_type, cup_type],
                      lambda s, o: s[o[0]][0] > 0.5)
    pred2 = Predicate("Pred2", [cup_type],
                      lambda s, o: s[o[0]][0] > 0.5)
    preds = {pred0, pred1, pred2}
    state0 = State({cup0: [0.4], cup1: [0.7], cup2: [0.1]})
    atoms0 = utils.abstract(state0, preds)
    state1 = State({cup0: [0.8], cup1: [0.3], cup2: [1.0]})
    atoms1 = utils.abstract(state1, preds)
    # Tests with known options.
    param_option = ParameterizedOption(
        "dummy", [cup_type], Box(0.1, 1, (1,)), lambda s, m, o, p: Action(p),
        lambda s, m, o, p: False, lambda s, m, o, p: False)
    option0 = param_option.ground([cup0], np.array([0.2]))
    action0 = option0.policy(state0)
    # Even though the option changes, the option spec stays the same, so we do
    # not want to segment. This is because we are segmenting based on symbolic
    # aspects only, because the strips operators can only depend on symbols.
    option1 = param_option.ground([cup0], np.array([0.1]))
    action1 = option1.policy(state0)
    option2 = param_option.ground([cup1], np.array([0.1]))
    action2 = option2.policy(state0)
    trajectory = ([state0, state0, state0, state0, state0],
                  [action0, action1, action2, action0],
                  [atoms0, atoms0, atoms0, atoms0, atoms0])
    known_option_segments = segment_trajectory(trajectory)
    # Note that there are only two segments because the final segment is never
    # included in the result of segment_trajectory (because we don't know if
    # the option finished executing or not).
    assert len(known_option_segments) == 2
    assert len(known_option_segments[0].actions) == 2
    assert len(known_option_segments[1].actions) == 1
    # Tests without known options.
    action0 = option0.policy(state0)
    action0.unset_option()
    action1 = option0.policy(state0)
    action1.unset_option()
    action2 = option1.policy(state0)
    action2.unset_option()
    trajectory = ([state0, state0, state0, state0, state0],
                  [action0, action1, action2, action0],
                  [atoms0, atoms0, atoms0, atoms0, atoms0])
    assert len(segment_trajectory(trajectory)) == 0
    trajectory = ([state0, state0, state0, state0, state0, state1],
                  [action0, action1, action2, action0, action1],
                  [atoms0, atoms0, atoms0, atoms0, atoms0, atoms1])
    unknown_option_segments = segment_trajectory(trajectory)
    assert len(unknown_option_segments) == 1
    assert len(unknown_option_segments[0].actions) == 5
    return known_option_segments, unknown_option_segments


def test_learn_strips_operators():
    """Tests for learn_strips_operators().
    """
    utils.update_config({"min_data_for_nsrt": 0})
    known_option_segments, unknown_option_segments = test_segment_trajectory()
    known_option_ops, _ = learn_strips_operators(known_option_segments)
    assert len(known_option_ops) == 1
    assert str((known_option_ops[0])) == """STRIPS-Op0:
    Parameters: [?x0:cup_type]
    Preconditions: []
    Add Effects: []
    Delete Effects: []"""
    unknown_option_ops, _ = learn_strips_operators(unknown_option_segments)
    assert len(unknown_option_ops) == 1
    assert str(unknown_option_ops[0]) == """STRIPS-Op0:
    Parameters: [?x0:cup_type, ?x1:cup_type, ?x2:cup_type]
    Preconditions: [Pred0(?x1:cup_type), Pred1(?x1:cup_type, ?x0:cup_type), Pred1(?x1:cup_type, ?x1:cup_type), Pred1(?x1:cup_type, ?x2:cup_type), Pred2(?x1:cup_type)]
    Add Effects: [Pred0(?x0:cup_type), Pred0(?x2:cup_type), Pred1(?x0:cup_type, ?x0:cup_type), Pred1(?x0:cup_type, ?x1:cup_type), Pred1(?x0:cup_type, ?x2:cup_type), Pred1(?x2:cup_type, ?x0:cup_type), Pred1(?x2:cup_type, ?x1:cup_type), Pred1(?x2:cup_type, ?x2:cup_type), Pred2(?x0:cup_type), Pred2(?x2:cup_type)]
    Delete Effects: [Pred0(?x1:cup_type), Pred1(?x1:cup_type, ?x0:cup_type), Pred1(?x1:cup_type, ?x1:cup_type), Pred1(?x1:cup_type, ?x2:cup_type), Pred2(?x1:cup_type)]"""  # pylint: disable=line-too-long


def test_nsrt_learning_specific_nsrts():
    """Tests with a specific desired set of NSRTs.
    """
    utils.update_config({"min_data_for_nsrt": 0, "seed": 123,
                         "classifier_max_itr_sampler": 1000,
                         "regressor_max_itr": 1000})
    cup_type = Type("cup_type", ["feat1"])
    cup0 = cup_type("cup0")
    cup1 = cup_type("cup1")
    cup2 = cup_type("cup2")
    cup3 = cup_type("cup3")
    cup4 = cup_type("cup4")
    cup5 = cup_type("cup5")
    pred0 = Predicate("Pred0", [cup_type],
                      lambda s, o: s[o[0]][0] > 0.5)
    pred1 = Predicate("Pred1", [cup_type, cup_type],
                      lambda s, o: s[o[0]][0] > 0.5)
    pred2 = Predicate("Pred2", [cup_type],
                      lambda s, o: s[o[0]][0] > 0.5)
    preds = {pred0, pred1, pred2}
    state1 = State({cup0: [0.4], cup1: [0.7], cup2: [0.1]})
    option1 = ParameterizedOption(
        "dummy", [], Box(0.1, 1, (1,)), lambda s, m, o, p: Action(p),
        lambda s, m, o, p: False, lambda s, m, o, p: False).ground(
            [], np.array([0.2]))
    action1 = option1.policy(state1)
    action1.set_option(option1)
    next_state1 = State({cup0: [0.8], cup1: [0.3], cup2: [1.0]})
    dataset = [([state1, next_state1], [action1])]
    nsrts = learn_nsrts_from_data(dataset, preds, do_sampler_learning=True)
    assert len(nsrts) == 1
    nsrt = nsrts.pop()
    assert str(nsrt) == """NSRT-Op0:
    Parameters: [?x0:cup_type, ?x1:cup_type, ?x2:cup_type]
    Preconditions: [Pred0(?x1:cup_type), Pred1(?x1:cup_type, ?x0:cup_type), Pred1(?x1:cup_type, ?x1:cup_type), Pred1(?x1:cup_type, ?x2:cup_type), Pred2(?x1:cup_type)]
    Add Effects: [Pred0(?x0:cup_type), Pred0(?x2:cup_type), Pred1(?x0:cup_type, ?x0:cup_type), Pred1(?x0:cup_type, ?x1:cup_type), Pred1(?x0:cup_type, ?x2:cup_type), Pred1(?x2:cup_type, ?x0:cup_type), Pred1(?x2:cup_type, ?x1:cup_type), Pred1(?x2:cup_type, ?x2:cup_type), Pred2(?x0:cup_type), Pred2(?x2:cup_type)]
    Delete Effects: [Pred0(?x1:cup_type), Pred1(?x1:cup_type, ?x0:cup_type), Pred1(?x1:cup_type, ?x1:cup_type), Pred1(?x1:cup_type, ?x2:cup_type), Pred2(?x1:cup_type)]
    Option: ParameterizedOption(name='dummy', types=[])
    Option Variables: []"""
    # Test the learned samplers
    for _ in range(10):
        assert abs(nsrt.ground([cup0, cup1, cup2]).sample_option(
            state1, np.random.default_rng(123)).params - 0.2) < 0.01
    # The following test was used to manually check that unify caches correctly.
    pred0 = Predicate("Pred0", [cup_type],
                      lambda s, o: s[o[0]][0] > 0.5)
    pred1 = Predicate("Pred1", [cup_type, cup_type],
                      lambda s, o: s[o[0]][0] > 0.5)
    pred2 = Predicate("Pred2", [cup_type],
                      lambda s, o: s[o[0]][0] > 0.5)
    preds = {pred0, pred1, pred2}
    state1 = State({cup0: [0.4], cup1: [0.7], cup2: [0.1]})
    action1 = option1.policy(state1)
    action1.set_option(option1)
    next_state1 = State({cup0: [0.8], cup1: [0.3], cup2: [1.0]})
    state2 = State({cup3: [0.4], cup4: [0.7], cup5: [0.1]})
    action2 = option1.policy(state2)
    action2.set_option(option1)
    next_state2 = State({cup3: [0.8], cup4: [0.3], cup5: [1.0]})
    dataset = [([state1, next_state1], [action1]),
               ([state2, next_state2], [action2])]
    nsrts = learn_nsrts_from_data(dataset, preds, do_sampler_learning=True)
    assert len(nsrts) == 1
    nsrt = nsrts.pop()
    assert str(nsrt) == """NSRT-Op0:
    Parameters: [?x0:cup_type, ?x1:cup_type, ?x2:cup_type]
    Preconditions: [Pred0(?x1:cup_type), Pred1(?x1:cup_type, ?x0:cup_type), Pred1(?x1:cup_type, ?x1:cup_type), Pred1(?x1:cup_type, ?x2:cup_type), Pred2(?x1:cup_type)]
    Add Effects: [Pred0(?x0:cup_type), Pred0(?x2:cup_type), Pred1(?x0:cup_type, ?x0:cup_type), Pred1(?x0:cup_type, ?x1:cup_type), Pred1(?x0:cup_type, ?x2:cup_type), Pred1(?x2:cup_type, ?x0:cup_type), Pred1(?x2:cup_type, ?x1:cup_type), Pred1(?x2:cup_type, ?x2:cup_type), Pred2(?x0:cup_type), Pred2(?x2:cup_type)]
    Delete Effects: [Pred0(?x1:cup_type), Pred1(?x1:cup_type, ?x0:cup_type), Pred1(?x1:cup_type, ?x1:cup_type), Pred1(?x1:cup_type, ?x2:cup_type), Pred2(?x1:cup_type)]
    Option: ParameterizedOption(name='dummy', types=[])
    Option Variables: []"""
    # The following two tests check edge cases of unification with respect to
    # the split between add and delete effects. Specifically, it's important
    # to unify both of them together, not separately, which requires changing
    # the predicates so that unification does not try to unify add ones with
    # delete ones.
    pred0 = Predicate("Pred0", [cup_type, cup_type],
                      lambda s, o: s[o[0]][0] > 0.7 and s[o[1]][0] < 0.3)
    preds = {pred0}
    state1 = State({cup0: [0.4], cup1: [0.8], cup2: [0.1]})
    option1 = ParameterizedOption(
        "dummy", [], Box(0.1, 1, (1,)), lambda s, m, o, p: Action(p),
        lambda s, m, o, p: False, lambda s, m, o, p: False).ground(
            [], np.array([0.3]))
    action1 = option1.policy(state1)
    action1.set_option(option1)
    next_state1 = State({cup0: [0.9], cup1: [0.2], cup2: [0.5]})
    state2 = State({cup4: [0.9], cup5: [0.2], cup2: [0.5], cup3: [0.5]})
    option2 = ParameterizedOption(
        "dummy", [], Box(0.1, 1, (1,)), lambda s, m, o, p: Action(p),
        lambda s, m, o, p: False, lambda s, m, o, p: False).ground(
            [], np.array([0.7]))
    action2 = option2.policy(state2)
    action2.set_option(option2)
    next_state2 = State({cup4: [0.5], cup5: [0.5], cup2: [1.0], cup3: [0.1]})
    dataset = [([state1, next_state1], [action1]),
               ([state2, next_state2], [action2])]
    nsrts = learn_nsrts_from_data(dataset, preds, do_sampler_learning=True)
    assert len(nsrts) == 2
    expected = {"Op0": """NSRT-Op0:
    Parameters: [?x0:cup_type, ?x1:cup_type, ?x2:cup_type]
    Preconditions: [Pred0(?x1:cup_type, ?x2:cup_type)]
    Add Effects: [Pred0(?x0:cup_type, ?x1:cup_type)]
    Delete Effects: [Pred0(?x1:cup_type, ?x2:cup_type)]
    Option: ParameterizedOption(name='dummy', types=[])
    Option Variables: []""", "Op1": """NSRT-Op1:
    Parameters: [?x0:cup_type, ?x1:cup_type, ?x2:cup_type, ?x3:cup_type]
    Preconditions: [Pred0(?x2:cup_type, ?x3:cup_type)]
    Add Effects: [Pred0(?x0:cup_type, ?x1:cup_type)]
    Delete Effects: [Pred0(?x2:cup_type, ?x3:cup_type)]
    Option: ParameterizedOption(name='dummy', types=[])
    Option Variables: []"""}
    for nsrt in nsrts:
        assert str(nsrt) == expected[nsrt.name]
        # Test the learned samplers
        if nsrt.name == "Op0":
            for _ in range(10):
                assert abs(nsrt.ground([cup0, cup1, cup2]).sample_option(
                    state1, np.random.default_rng(123)).params - 0.3) < 0.01
        if nsrt.name == "Op1":
            for _ in range(10):
                assert abs(nsrt.ground([cup2, cup3, cup4, cup5]).sample_option(
                    state2, np.random.default_rng(123)).params - 0.7) < 0.01
    pred0 = Predicate("Pred0", [cup_type, cup_type],
                      lambda s, o: s[o[0]][0] > 0.7 and s[o[1]][0] < 0.3)
    preds = {pred0}
    state1 = State({cup0: [0.5], cup1: [0.5]})
    action1 = option2.policy(state1)
    action1.set_option(option2)
    next_state1 = State({cup0: [0.9], cup1: [0.1],})
    state2 = State({cup4: [0.9], cup5: [0.1]})
    action2 = option2.policy(state2)
    action2.set_option(option2)
    next_state2 = State({cup4: [0.5], cup5: [0.5]})
    dataset = [([state1, next_state1], [action1]),
               ([state2, next_state2], [action2])]
    nsrts = learn_nsrts_from_data(dataset, preds, do_sampler_learning=True)
    assert len(nsrts) == 2
    expected = {"Op0": """NSRT-Op0:
    Parameters: [?x0:cup_type, ?x1:cup_type]
    Preconditions: []
    Add Effects: [Pred0(?x0:cup_type, ?x1:cup_type)]
    Delete Effects: []
    Option: ParameterizedOption(name='dummy', types=[])
    Option Variables: []""", "Op1": """NSRT-Op1:
    Parameters: [?x0:cup_type, ?x1:cup_type]
    Preconditions: [Pred0(?x0:cup_type, ?x1:cup_type)]
    Add Effects: []
    Delete Effects: [Pred0(?x0:cup_type, ?x1:cup_type)]
    Option: ParameterizedOption(name='dummy', types=[])
    Option Variables: []"""}
    for nsrt in nsrts:
        assert str(nsrt) == expected[nsrt.name]
    # Test minimum number of examples parameter
    utils.update_config({"min_data_for_nsrt": 3})
    nsrts = learn_nsrts_from_data(dataset, preds, do_sampler_learning=True)
    assert len(nsrts) == 0
    # Test sampler giving out-of-bounds outputs
    utils.update_config({"min_data_for_nsrt": 0, "seed": 123,
                         "classifier_max_itr_sampler": 1,
                         "regressor_max_itr": 1})
    nsrts = learn_nsrts_from_data(dataset, preds, do_sampler_learning=True)
    assert len(nsrts) == 2
    for nsrt in nsrts:
        for _ in range(10):
            assert option1.parent.params_space.contains(
                nsrt.ground([cup0, cup1]).sample_option(
                    state1, np.random.default_rng(123)).params)
    # Test max_rejection_sampling_tries = 0
    utils.update_config({"max_rejection_sampling_tries": 0, "seed": 1234})
    nsrts = learn_nsrts_from_data(dataset, preds, do_sampler_learning=True)
    assert len(nsrts) == 2
    for nsrt in nsrts:
        for _ in range(10):
            assert option1.parent.params_space.contains(
                nsrt.ground([cup0, cup1]).sample_option(
                    state1, np.random.default_rng(123)).params)
    # Test do_sampler_learning = False
    utils.update_config({"seed": 123, "classifier_max_itr_sampler": 100000,
                         "regressor_max_itr": 100000})
    start_time = time.time()
    nsrts = learn_nsrts_from_data(dataset, preds, do_sampler_learning=False)
    assert time.time()-start_time < 0.1  # should be lightning fast
    assert len(nsrts) == 2
    for nsrt in nsrts:
        for _ in range(10):
            # Will just return random parameters
            assert option1.parent.params_space.contains(
                nsrt.ground([cup0, cup1]).sample_option(
                    state1, np.random.default_rng(123)).params)


def test_unify_effects_and_options():
    """Tests for unify_effects_and_options().
    """
    # The following test checks edge cases of unification with respect to
    # the split between effects and option variables.
    # The case is basically this:
    # Add set 1: P(a, b)
    # Option 1: A(b, c)
    # Add set 2: P(w, x)
    # Option 2: A(y, z)
    cup_type = Type("cup_type", ["feat1"])
    cup0 = cup_type("cup0")
    cup1 = cup_type("cup1")
    cup2 = cup_type("cup2")
    w = cup_type("?w")
    x = cup_type("?x")
    y = cup_type("?y")
    z = cup_type("?z")
    pred0 = Predicate("Pred0", [cup_type, cup_type], lambda s, o: False)
    param_option0 = ParameterizedOption(
        "dummy0", [cup_type], Box(0.1, 1, (1,)), lambda s, m, o, p: Action(p),
        lambda s, m, o, p: False, lambda s, m, o, p: False)
    # Option0(cup0, cup1)
    ground_option_args = (cup0, cup1)
    # Pred0(cup1, cup2) true
    ground_add_effects = frozenset({pred0([cup1, cup2])})
    ground_delete_effects = frozenset()
    # Option0(w, x)
    lifted_option_args = (w, x)
    # Pred0(y, z) True
    lifted_add_effects = frozenset({pred0([y, z])})
    lifted_delete_effects = frozenset()
    suc, sub = unify_effects_and_options(
        ground_add_effects,
        lifted_add_effects,
        ground_delete_effects,
        lifted_delete_effects,
        param_option0,
        param_option0,
        ground_option_args,
        lifted_option_args)
    assert not suc
    assert not sub
    # The following test is for an edge case where everything is identical
    # except for the name of the parameterized option. We do not want to
    # unify in this case.
    # First, a unify that should succeed.
    suc, sub = unify_effects_and_options(
        frozenset(),
        frozenset(),
        frozenset(),
        frozenset(),
        param_option0,
        param_option0,
        (cup0, cup1),
        (cup0, cup1))
    assert suc
    assert sub == {cup0: cup0, cup1: cup1}
    # Now, a unify that should fail because of different parameterized options.
    param_option1 = ParameterizedOption(
        "dummy1", [cup_type], Box(0.1, 1, (1,)), lambda s, m, o, p: Action(p),
        lambda s, m, o, p: False, lambda s, m, o, p: False)
    suc, sub = unify_effects_and_options(
        frozenset(),
        frozenset(),
        frozenset(),
        frozenset(),
        param_option0,
        param_option1,
        (cup0, cup1),
        (cup0, cup1))
    assert not suc
    assert not sub
