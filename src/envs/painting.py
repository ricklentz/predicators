"""Painting domain, which allows for two different grasps on an object
(side or top). Side grasping allows for placing into the shelf, and top
grasping allows for placing into the box. The box has a lid which
may need to be opened; this lid is NOT modeled by any of the given
predicates, but could be modeled by a learned predicate.
"""

from typing import List, Set, Sequence, Dict, Tuple, Optional
import numpy as np
from gym.spaces import Box
from matplotlib import pyplot as plt
from matplotlib import patches
from predicators.src.envs import BaseEnv
from predicators.src.structs import Type, Predicate, State, Task, \
    ParameterizedOption, Object, Action, GroundAtom, Image, Array
from predicators.src.settings import CFG
from predicators.src import utils


class PaintingEnv(BaseEnv):
    """Painting domain.
    """
    # Parameters that aren't important enough to need to clog up settings.py
    table_lb = -10.1
    table_ub = -0.2
    table_height = 0.2
    shelf_l = 2.0 # shelf length
    shelf_lb = 1.
    shelf_ub = shelf_lb + shelf_l - 0.05
    box_s = 0.8  # side length
    box_y = 0.5  # y coordinate
    box_lb = box_y - box_s/10
    box_ub = box_y + box_s/10
    obj_height = 0.13
    obj_radius = 0.03
    obj_x = 1.65
    obj_z = table_height + obj_height/2
    pick_tol = 1e-1
    color_tol = 1e-2
    wetness_tol = 0.5
    dirtiness_tol = 0.5
    open_fingers = 0.8
    top_grasp_thresh = 0.5 + 1e-5
    side_grasp_thresh = 0.5 - 1e-5
    held_tol = 0.5
    num_objs_train = [3, 4]
    num_objs_test = [5, 6]

    def __init__(self) -> None:
        super().__init__()
        # Types
        self._obj_type = Type("obj", ["pose_x", "pose_y", "pose_z", "color",
                                      "wetness", "dirtiness", "held"])
        self._box_type = Type("box", ["color"])
        self._lid_type = Type("lid", ["open"])
        self._shelf_type = Type("shelf", ["color"])
        self._robot_type = Type("robot", ["gripper_rot", "fingers"])
        # Predicates
        self._InBox = Predicate(
            "InBox", [self._obj_type, self._box_type], self._InBox_holds)
        self._InShelf = Predicate(
            "InShelf", [self._obj_type, self._shelf_type], self._InShelf_holds)
        self._IsBoxColor = Predicate(
            "IsBoxColor", [self._obj_type, self._box_type],
            self._IsBoxColor_holds)
        self._IsShelfColor = Predicate(
            "IsShelfColor", [self._obj_type, self._shelf_type],
            self._IsShelfColor_holds)
        self._GripperOpen = Predicate(
            "GripperOpen", [self._robot_type], self._GripperOpen_holds)
        self._OnTable = Predicate(
            "OnTable", [self._obj_type], self._OnTable_holds)
        self._HoldingTop = Predicate(
            "HoldingTop", [self._obj_type, self._robot_type],
            self._HoldingTop_holds)
        self._HoldingSide = Predicate(
            "HoldingSide", [self._obj_type, self._robot_type],
            self._HoldingSide_holds)
        self._Holding = Predicate(
            "Holding", [self._obj_type], self._Holding_holds)
        self._IsWet = Predicate(
            "IsWet", [self._obj_type], self._IsWet_holds)
        self._IsDry = Predicate(
            "IsDry", [self._obj_type], self._IsDry_holds)
        self._IsDirty = Predicate(
            "IsDirty", [self._obj_type], self._IsDirty_holds)
        self._IsClean = Predicate(
            "IsClean", [self._obj_type], self._IsClean_holds)
        # Options
        self._Pick = ParameterizedOption(
            # variables: [robot, object to pick]
            # params: [delta x, delta y, delta z, grasp rotation]
            "Pick", types=[self._robot_type, self._obj_type],
            params_space=Box(
                np.array([-1.0, -1.0, -1.0, 0.0], dtype=np.float32),
                np.array([1.0, 1.0, 1.0, 1.0], dtype=np.float32)),
            _policy=self._Pick_policy,
            # to initiate, must be holding nothing
            _initiable=lambda s, m, o, p: self._get_held_object(s) is None,
            _terminal=lambda s, m, o, p: True)  # always 1 timestep
        self._Wash = ParameterizedOption(
            # variables: [robot]
            # params: [water level]
            "Wash", types=[self._robot_type],
            params_space=Box(0, 1, (1,)),
            _policy=self._Wash_policy,
            # to initiate, must be holding an object
            _initiable=lambda s, m, o, p: self._get_held_object(s) is not None,
            _terminal=lambda s, m, o, p: True)  # always 1 timestep
        self._Dry = ParameterizedOption(
            # variables: [robot]
            # params: [heat level]
            "Dry", types=[self._robot_type],
            params_space=Box(0, 1, (1,)),
            _policy=self._Dry_policy,
            # to initiate, must be holding an object
            _initiable=lambda s, m, o, p: self._get_held_object(s) is not None,
            _terminal=lambda s, m, o, p: True)  # always 1 timestep
        self._Paint = ParameterizedOption(
            # variables: [robot]
            # params: [new color]
            "Paint", types=[self._robot_type],
            params_space=Box(0, 1, (1,)),
            _policy=self._Paint_policy,
            # to initiate, must be holding an object
            _initiable=lambda s, m, o, p: self._get_held_object(s) is not None,
            _terminal=lambda s, m, o, p: True)  # always 1 timestep
        self._Place = ParameterizedOption(
            # variables: [robot]
            # params: [absolute x, absolute y, absolute z]
            "Place", types=[self._robot_type],
            params_space=Box(
                np.array([self.obj_x - 1e-2, self.table_lb, self.obj_z - 1e-2],
                         dtype=np.float32),
                np.array([self.obj_x + 1e-2, self.table_ub, self.obj_z + 1e-2],
                         dtype=np.float32)),
            _policy=self._Place_policy,
            # to initiate, must be holding an object
            _initiable=lambda s, m, o, p: self._get_held_object(s) is not None,
            _terminal=lambda s, m, o, p: True)  # always 1 timestep
        self._OpenLid = ParameterizedOption(
            # variables: [robot, lid]
            # params: []
            "OpenLid", types=[self._robot_type, self._lid_type],
            params_space=Box(0, 1, (0,)),  # no parameters
            _policy=self._OpenLid_policy,
            # to initiate, must be holding nothing
            _initiable=lambda s, m, o, p: self._get_held_object(s) is None,
            _terminal=lambda s, m, o, p: True)  # always 1 timestep
        # Objects
        self._box = Object("receptacle_box", self._box_type)
        self._lid = Object("box_lid", self._lid_type)
        self._shelf = Object("receptacle_shelf", self._shelf_type)
        self._robot = Object("robby", self._robot_type)

    def simulate(self, state: State, action: Action) -> State:
        assert self.action_space.contains(action.arr)
        raise NotImplementedError

    def get_train_tasks(self) -> List[Task]:
        raise NotImplementedError

    def get_test_tasks(self) -> List[Task]:
        raise NotImplementedError

    @property
    def predicates(self) -> Set[Predicate]:
        return {self._InBox, self._InShelf, self._IsBoxColor,
                self._IsShelfColor, self._GripperOpen, self._OnTable,
                self._HoldingTop, self._HoldingSide, self._Holding,
                self._IsWet, self._IsDry, self._IsDirty, self._IsClean}

    @property
    def goal_predicates(self) -> Set[Predicate]:
        return {self._InBox, self._InShelf, self._IsBoxColor,
                self._IsShelfColor}

    @property
    def types(self) -> Set[Type]:
        return {self._obj_type, self._box_type, self._lid_type,
                self._shelf_type, self._robot_type}

    @property
    def options(self) -> Set[ParameterizedOption]:
        return {self._Pick, self._Wash, self._Dry, self._Paint,
                self._Place, self._OpenLid}

    @property
    def action_space(self) -> Box:
        # Actions are 8-dimensional vectors:
        # [x, y, z, rot, pickplace, water level, heat level, color]
        # Note that pickplace is 1 for pick, -1 for place, and 0 otherwise,
        # while rot, water level, heat level, and color are in [0, 1].
        lowers = np.array([self.obj_x - 1e-2, self.table_lb,
                           self.obj_z - 1e-2, 0.0, -1.0, 0.0, 0.0, 0.0],
                          dtype=np.float32)
        uppers = np.array([self.obj_x + 1e-2, self.table_ub,
                           self.obj_z + 1e-2, 1.0, 1.0, 1.0, 1.0, 1.0],
                          dtype=np.float32)
        return Box(lowers, uppers)

    def render(self, state: State, task: Task,
               action: Optional[Action] = None) -> List[Image]:
        raise NotImplementedError  # TODO

    def _Pick_policy(self, state: State, memory: Dict,
                     objects: Sequence[Object], params: Array) -> Action:
        del memory  # unused
        _, obj = objects
        obj_x = state.get(obj, "pose_x")
        obj_y = state.get(obj, "pose_y")
        obj_z = state.get(obj, "pose_z")
        dx, dy, dz, rot = params
        arr = np.array([obj_x + dx, obj_y + dy, obj_z + dz, rot,
                        1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        arr = np.clip(arr, self.action_space.low, self.action_space.high)
        return Action(arr)

    @staticmethod
    def _Wash_policy(state: State, memory: Dict,
                     objects: Sequence[Object], params: Array) -> Action:
        del state, memory, objects  # unused
        arr = np.zeros(8, dtype=np.float32)
        water_level, = params
        arr[5] = water_level
        return Action(arr)

    @staticmethod
    def _Dry_policy(state: State, memory: Dict,
                    objects: Sequence[Object], params: Array) -> Action:
        del state, memory, objects  # unused
        arr = np.zeros(8, dtype=np.float32)
        heat_level, = params
        arr[6] = heat_level
        return Action(arr)

    @staticmethod
    def _Paint_policy(state: State, memory: Dict,
                      objects: Sequence[Object], params: Array) -> Action:
        del state, memory, objects  # unused
        arr = np.zeros(8, dtype=np.float32)
        new_color, = params
        arr[7] = new_color
        return Action(arr)

    @staticmethod
    def _Place_policy(state: State, memory: Dict,
                      objects: Sequence[Object], params: Array) -> Action:
        del state, memory, objects  # unused
        x, y, z = params
        arr = np.array([x, y, z, 0.0, -1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        return Action(arr)

    def _OpenLid_policy(self, state: State, memory: Dict,
                        objects: Sequence[Object], params: Array) -> Action:
        del state, memory, objects, params  # unused
        arr = np.array([self.obj_x, (self.box_lb + self.box_ub) / 2, self.obj_z,
                        0.0, 1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        return Action(arr)

    def _InBox_holds(self, state: State, objects: Sequence[Object]) -> bool:
        obj, _ = objects
        # If the object is held, not yet in box
        if state.get(obj, "held") > 0.5:
            return False
        # Check pose of object
        obj_y = state.get(obj, "pose_y")
        return self.box_lb < obj_y < self.box_ub

    def _InShelf_holds(self, state: State, objects: Sequence[Object]) -> bool:
        obj, _ = objects
        # If the object is held, not yet in shelf
        if state.get(obj, "held") > 0.5:
            return False
        # Check pose of object
        obj_y = state.get(obj, "pose_y")
        return self.shelf_lb < obj_y < self.shelf_ub

    def _IsBoxColor_holds(self, state: State, objects: Sequence[Object]
                          ) -> bool:
        obj, box = objects
        return abs(state.get(obj, "color") -
                   state.get(box, "color")) < self.color_tol

    def _IsShelfColor_holds(self, state: State, objects: Sequence[Object]
                            ) -> bool:
        obj, shelf = objects
        return abs(state.get(obj, "color") -
                   state.get(shelf, "color")) < self.color_tol

    def _GripperOpen_holds(self, state: State, objects: Sequence[Object]
                           ) -> bool:
        robot, = objects
        fingers = state.get(robot, "fingers")
        return fingers >= self.open_fingers

    def _OnTable_holds(self, state: State, objects: Sequence[Object]) -> bool:
        obj, = objects
        obj_y = state.get(obj, "pose_y")
        return self.table_lb < obj_y < self.table_ub

    def _HoldingTop_holds(self, state: State, objects: Sequence[Object]
                          ) -> bool:
        obj, robot = objects
        rot = state.get(robot, "gripper_rot")
        if rot < self.top_grasp_thresh:
            return False
        return self._Holding_holds(state, obj)

    def _HoldingSide_holds(self, state: State, objects: Sequence[Object]
                           ) -> bool:
        obj, robot = objects
        rot = state.get(robot, "gripper_rot")
        if rot > self.side_grasp_thresh:
            return False
        return self._Holding_holds(state, obj)

    def _Holding_holds(self, state: State, objects: Sequence[Object]) -> bool:
        obj, = objects
        return self._get_held_object(state) == obj

    def _IsWet_holds(self, state: State, objects: Sequence[Object]) -> bool:
        obj, = objects
        return state.get(obj, "wetness") > self.wetness_tol

    def _IsDry_holds(self, state: State, objects: Sequence[Object]) -> bool:
        obj, = objects
        return not self._IsWet_holds(state, obj)

    def _IsDirty_holds(self, state: State, objects: Sequence[Object]) -> bool:
        obj, = objects
        return state.get(obj, "dirtiness") > self.dirtiness_tol

    def _IsClean_holds(self, state: State, objects: Sequence[Object]) -> bool:
        obj, = objects
        return not self._IsDirty_holds(state, obj)

    def _get_held_object(self, state: State) -> Optional[Object]:
        for obj in state:
            if obj.var_type != self._obj_type:
                continue
            if state.get(obj, "held") >= self.held_tol:
                return obj
        return None
