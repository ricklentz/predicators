"""An environment where a robot must touch points with its hand or a stick."""

from typing import ClassVar, Dict, List, Optional, Sequence, Set, Tuple

import matplotlib.pyplot as plt
import numpy as np
from gym.spaces import Box

from predicators.src import utils
from predicators.src.envs import BaseEnv
from predicators.src.settings import CFG
from predicators.src.structs import Action, Array, GroundAtom, Image, Object, \
    ParameterizedOption, Predicate, State, Task, Type
from predicators.src.utils import _Geom2D


class StickPointEnv(BaseEnv):
    """An environment where a robot must touch points with its hand or a
    stick."""
    x_lb: ClassVar[float] = 0.0
    y_lb: ClassVar[float] = 0.0
    theta_lb: ClassVar[float] = -np.pi  # radians
    x_ub: ClassVar[float] = 10.0
    y_ub: ClassVar[float] = 6.0
    theta_ub: ClassVar[float] = np.pi  # radians
    # Reachable zone boundaries.
    rz_x_lb: ClassVar[float] = x_lb
    rz_x_ub: ClassVar[float] = x_ub
    rz_y_lb: ClassVar[float] = y_lb
    rz_y_ub: ClassVar[float] = y_lb + 3.0
    max_speed: ClassVar[float] = 0.5  # shared by dx, dy
    max_angular_speed: ClassVar[float] = np.pi / 4
    robot_radius: ClassVar[float] = 0.1
    point_radius: ClassVar[float] = 0.1
    # Note that the stick_width is the longer dimension.
    stick_width: ClassVar[float] = 3.0
    stick_height: ClassVar[float] = 0.05
    stick_tip_width: ClassVar[float] = 0.05
    init_padding: ClassVar[float] = 0.5  # used to space objects in init states
    pick_grasp_tol: ClassVar[float] = 1e-3

    def __init__(self) -> None:
        super().__init__()
        # Types
        # The (x, y) is the center of the robot. Theta is only relevant when
        # the robot is holding the stick.
        self._robot_type = Type("robot", ["x", "y", "theta"])
        # The (x, y) is the center of the point.
        self._point_type = Type("point", ["x", "y", "touched"])
        # The (x, y) is the bottom left-hand corner of the stick, and theta
        # is CCW angle in radians, consistent with utils.Rectangle.
        self._stick_type = Type("stick", ["x", "y", "theta", "held"])
        # Predicates
        self._Touched = Predicate("Touched", [self._point_type],
                                  self._Touched_holds)
        self._InContactStickPoint = Predicate(
            "InContactStickPoint", [self._stick_type, self._point_type],
            self._InContact_holds)
        self._InContactRobotPoint = Predicate(
            "InContactRobotPoint", [self._robot_type, self._point_type],
            self._InContact_holds)
        self._InContactRobotStick = Predicate(
            "InContactRobotStick", [self._robot_type, self._stick_type],
            self._InContact_holds)
        self._Grasped = Predicate("Grasped",
                                  [self._robot_type, self._stick_type],
                                  self._Grasped_holds)
        self._HandEmpty = Predicate("HandEmpty", [self._robot_type],
                                    self._HandEmpty_holds)
        self._NoPointInContact = Predicate("NoPointInContact", [],
                                           self._NoPointInContact_holds)
        # Options
        self._RobotTouchPoint = ParameterizedOption(
            "RobotTouchPoint",
            types=[self._robot_type, self._point_type],
            params_space=Box(0, 1, (0, )),
            policy=self._RobotTouchPoint_policy,
            initiable=lambda s, m, o, p: True,
            terminal=self._RobotTouchPoint_terminal,
        )

        self._PickStick = ParameterizedOption(
            "PickStick",
            types=[self._robot_type, self._stick_type],
            params_space=Box(0, 1, (1, )),  # normalized w.r.t. stick width
            policy=self._PickStick_policy,
            initiable=lambda s, m, o, p: True,
            terminal=self._PickStick_terminal,
        )

        self._StickTouchPoint = ParameterizedOption(
            "StickTouchPoint",
            types=[self._robot_type, self._stick_type, self._point_type],
            params_space=Box(0, 1, (0, )),
            policy=self._StickTouchPoint_policy,
            initiable=lambda s, m, o, p: True,
            terminal=self._StickTouchPoint_terminal,
        )

        # Static objects (always exist no matter the settings).
        self._robot = Object("robby", self._robot_type)
        self._stick = Object("stick", self._stick_type)

    @classmethod
    def get_name(cls) -> str:
        return "stick_point"

    def simulate(self, state: State, action: Action) -> State:
        assert self.action_space.contains(action.arr)
        norm_dx, norm_dy, norm_dtheta, press = action.arr
        # Actions are normalized to [-1, 1]. Denormalize them here.
        dx = norm_dx * self.max_speed
        dy = norm_dy * self.max_speed
        dtheta = norm_dtheta * self.max_angular_speed
        # Update the robot state.
        rx = state.get(self._robot, "x")
        ry = state.get(self._robot, "y")
        rtheta = state.get(self._robot, "theta")
        new_rx = rx + dx
        new_ry = ry + dy
        new_rtheta = rtheta + dtheta
        # The robot cannot leave the reachable zone.
        rad = self.robot_radius
        new_rx = np.clip(new_rx, self.rz_x_lb + rad, self.rz_x_ub - rad)
        new_ry = np.clip(new_ry, self.rz_y_lb + rad, self.rz_y_ub - rad)
        # Recompute the dx and dy after clipping, since those values will be
        # reused by the stick.
        dx = new_rx - rx
        dy = new_ry - ry
        next_state = state.copy()
        next_state.set(self._robot, "x", new_rx)
        next_state.set(self._robot, "y", new_ry)
        next_state.set(self._robot, "theta", new_rtheta)
        robot_circ = self._object_to_geom(self._robot, next_state)

        # Check if the stick is held. If so, we need to move and rotate it.
        stick_rect = self._object_to_geom(self._stick, state)
        assert isinstance(stick_rect, utils.Rectangle)
        if state.get(self._stick, "held") > 0.5:
            stick_rect = stick_rect.rotate_about_point(rx, ry, dtheta)
            stick_rect = utils.Rectangle(x=(stick_rect.x + dx),
                                         y=(stick_rect.y + dy),
                                         width=stick_rect.width,
                                         height=stick_rect.height,
                                         theta=stick_rect.theta)
            next_state.set(self._stick, "x", stick_rect.x)
            next_state.set(self._stick, "y", stick_rect.y)
            next_state.set(self._stick, "theta", stick_rect.theta)

        if press > 0:
            # Check if the stick is now held for the first time.
            if state.get(self._stick, "held") <= 0.5 and \
                stick_rect.intersects(robot_circ):
                next_state.set(self._stick, "held", 1.0)

            # Check if any point is now touched.
            tip_rect = self._stick_rect_to_tip_rect(stick_rect)
            for point in state.get_objects(self._point_type):
                circ = self._object_to_geom(point, state)
                if circ.intersects(robot_circ) or circ.intersects(tip_rect):
                    next_state.set(point, "touched", 1.0)

        return next_state

    def _generate_train_tasks(self) -> List[Task]:
        return self._get_tasks(num=CFG.num_train_tasks,
                               num_point_lst=CFG.stick_point_num_points_train,
                               rng=self._train_rng)

    def _generate_test_tasks(self) -> List[Task]:
        return self._get_tasks(num=CFG.num_test_tasks,
                               num_point_lst=CFG.stick_point_num_points_test,
                               rng=self._test_rng)

    @property
    def predicates(self) -> Set[Predicate]:
        return {
            self._Touched, self._InContactRobotPoint,
            self._InContactRobotStick, self._InContactStickPoint,
            self._Grasped, self._HandEmpty, self._NoPointInContact
        }

    @property
    def goal_predicates(self) -> Set[Predicate]:
        return {self._Touched}

    @property
    def types(self) -> Set[Type]:
        return {self._robot_type, self._stick_type, self._point_type}

    @property
    def options(self) -> Set[ParameterizedOption]:
        return {self._RobotTouchPoint, self._PickStick, self._StickTouchPoint}

    @property
    def action_space(self) -> Box:
        # Normalized dx, dy, dtheta, press.
        return Box(low=-1., high=1., shape=(4, ), dtype=np.float32)

    def render_state(self,
                     state: State,
                     task: Task,
                     action: Optional[Action] = None,
                     caption: Optional[str] = None) -> List[Image]:
        figsize = (self.x_ub - self.x_lb, self.y_ub - self.y_lb)
        fig, ax = plt.subplots(1, 1, figsize=figsize)
        assert caption is None
        # Draw a light green rectangle for the reachable zone.
        reachable_zone = utils.Rectangle(x=self.rz_x_lb,
                                         y=self.rz_y_lb,
                                         width=(self.rz_x_ub - self.rz_x_lb),
                                         height=(self.rz_y_ub - self.rz_y_lb),
                                         theta=0)
        reachable_zone.plot(ax, color="lightgreen", alpha=0.25)
        # Draw the points.
        for point in state.get_objects(self._point_type):
            color = "blue" if state.get(point, "touched") > 0.5 else "yellow"
            circ = self._object_to_geom(point, state)
            circ.plot(ax, facecolor=color, edgecolor="black", alpha=0.75)
        # Draw the stick.
        stick, = state.get_objects(self._stick_type)
        rect = self._object_to_geom(stick, state)
        assert isinstance(rect, utils.Rectangle)
        color = "black" if state.get(stick, "held") > 0.5 else "white"
        rect.plot(ax, facecolor="firebrick", edgecolor=color)
        rect = self._stick_rect_to_tip_rect(rect)
        rect.plot(ax, facecolor="saddlebrown", edgecolor=color)
        # Uncomment for debugging.
        # tx, ty = self._get_stick_grasp_loc(state, stick, np.array([0.1]))
        # circ = utils.Circle(tx, ty, radius=0.025)
        # circ.plot(ax, color="black")
        # Draw the robot.
        robot, = state.get_objects(self._robot_type)
        circ = self._object_to_geom(robot, state)
        assert isinstance(circ, utils.Circle)
        circ.plot(ax, facecolor="red", edgecolor="black")
        # Show the direction that the robot is facing.
        theta = state.get(robot, "theta")
        l = 1.5 * self.robot_radius  # arrow length
        w = 0.1 * self.robot_radius  # arrow width
        ax.arrow(circ.x, circ.y, l * np.cos(theta), l * np.sin(theta), width=w)
        ax.set_xlim(self.x_lb, self.x_ub)
        ax.set_ylim(self.y_lb, self.y_ub)
        ax.axis("off")
        plt.tight_layout()
        img = utils.fig2data(fig)
        plt.close()
        return [img]

    def _get_tasks(self, num: int, num_point_lst: List[int],
                   rng: np.random.Generator) -> List[Task]:
        tasks = []
        for _ in range(num):
            state_dict = {}
            num_points = num_point_lst[rng.choice(len(num_point_lst))]
            points = [
                Object(f"point{i}", self._point_type)
                for i in range(num_points)
            ]
            goal = {GroundAtom(self._Touched, [p]) for p in points}
            # Sample initial positions for points, making sure to keep them
            # far enough apart from one another.
            collision_geoms: Set[utils.Circle] = set()
            radius = self.point_radius + self.init_padding
            for point in points:
                # Assuming that the dimensions are forgiving enough that
                # infinite loops are impossible.
                while True:
                    x = rng.uniform(self.x_lb + radius, self.x_ub - radius)
                    y = rng.uniform(self.y_lb + radius, self.y_ub - radius)
                    geom = utils.Circle(x, y, radius)
                    # Keep only if no intersections with existing objects.
                    if not any(geom.intersects(g) for g in collision_geoms):
                        break
                collision_geoms.add(geom)
                state_dict[point] = {"x": x, "y": y, "touched": 0.0}
            # Sample an initial position for the robot, making sure that it
            # doesn't collide with points and that it's in the reachable zone.
            radius = self.robot_radius + self.init_padding
            while True:
                x = rng.uniform(self.rz_x_lb + radius, self.rz_x_ub - radius)
                y = rng.uniform(self.rz_y_lb + radius, self.rz_y_ub - radius)
                geom = utils.Circle(x, y, radius)
                # Keep only if no intersections with existing objects.
                if not any(geom.intersects(g) for g in collision_geoms):
                    break
            collision_geoms.add(geom)
            theta = rng.uniform(self.theta_lb, self.theta_ub)
            state_dict[self._robot] = {"x": x, "y": y, "theta": theta}
            # Finally, sample the stick, making sure that the origin is in the
            # reachable zone, and that the stick doesn't collide with anything.
            radius = self.robot_radius + self.init_padding
            while True:
                # The radius here is to prevent the stick from being very
                # slightly in the reachable zone, but not grabbable.
                x = rng.uniform(self.rz_x_lb + radius, self.rz_x_ub - radius)
                y = rng.uniform(self.rz_y_lb + radius, self.rz_y_ub - radius)
                theta = rng.uniform(self.theta_lb, self.theta_ub)
                rect = utils.Rectangle(x, y, self.stick_width,
                                       self.stick_height, theta)
                # Keep only if no intersections with existing objects.
                if not any(rect.intersects(g) for g in collision_geoms):
                    break
            state_dict[self._stick] = {
                "x": x,
                "y": y,
                "theta": theta,
                "held": 0.0
            }
            init_state = utils.create_state_from_dict(state_dict)
            task = Task(init_state, goal)
            tasks.append(task)
        return tasks

    def _object_to_geom(self, obj: Object, state: State) -> _Geom2D:
        x = state.get(obj, "x")
        y = state.get(obj, "y")
        if obj.is_instance(self._robot_type):
            return utils.Circle(x, y, self.robot_radius)
        if obj.is_instance(self._point_type):
            return utils.Circle(x, y, self.point_radius)
        assert obj.is_instance(self._stick_type)
        theta = state.get(obj, "theta")
        return utils.Rectangle(x=x,
                               y=y,
                               width=self.stick_width,
                               height=self.stick_height,
                               theta=theta)

    def _stick_rect_to_tip_rect(
            self, stick_rect: utils.Rectangle) -> utils.Rectangle:
        theta = stick_rect.theta
        width = self.stick_tip_width
        scale = stick_rect.width - width
        return utils.Rectangle(x=(stick_rect.x + scale * np.cos(theta)),
                               y=(stick_rect.y + scale * np.sin(theta)),
                               width=self.stick_tip_width,
                               height=stick_rect.height,
                               theta=theta)

    def _get_stick_grasp_loc(self, state: State, stick: Object,
                             params: Array) -> Tuple[float, float]:
        stheta = state.get(stick, "theta")
        # We always aim for the center of the shorter dimension. The params
        # selects a position along the longer dimension.
        h = self.stick_height
        sx = state.get(stick, "x") + (h / 2) * np.cos(stheta + np.pi / 2)
        sy = state.get(stick, "y") + (h / 2) * np.sin(stheta + np.pi / 2)
        # Calculate the target point to reach based on the parameter.
        pick_param, = params
        scale = self.stick_width * pick_param
        tx = sx + scale * np.cos(stheta)
        ty = sy + scale * np.sin(stheta)
        return (tx, ty)

    def _RobotTouchPoint_policy(self, state: State, memory: Dict,
                                objects: Sequence[Object],
                                params: Array) -> Action:
        del memory, params  # unused
        # If the robot and point are already touching, press.
        if self._InContact_holds(state, objects):
            return Action(np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float32))
        # Otherwise, move toward the point.
        robot, point = objects
        rx = state.get(robot, "x")
        ry = state.get(robot, "y")
        px = state.get(point, "x")
        py = state.get(point, "y")
        dx = np.clip(px - rx, -self.max_speed, self.max_speed)
        dy = np.clip(py - ry, -self.max_speed, self.max_speed)
        # Normalize.
        dx = dx / self.max_speed
        dy = dy / self.max_speed
        # No need to rotate, and we don't want to press until we're there.
        return Action(np.array([dx, dy, 0.0, -1.0], dtype=np.float32))

    def _RobotTouchPoint_terminal(self, state: State, memory: Dict,
                                  objects: Sequence[Object],
                                  params: Array) -> bool:
        del memory, params  # unused
        _, point = objects
        return self._Touched_holds(state, [point])

    def _PickStick_policy(self, state: State, memory: Dict,
                          objects: Sequence[Object], params: Array) -> Action:
        del memory  # unused
        robot, stick = objects
        rx = state.get(robot, "x")
        ry = state.get(robot, "y")
        tx, ty = self._get_stick_grasp_loc(state, stick, params)
        # If we're close enough to the grasp point, press.
        if (tx - rx)**2 + (ty - ry)**2 < self.pick_grasp_tol:
            return Action(np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float32))
        # Move toward the target.
        dx = np.clip(tx - rx, -self.max_speed, self.max_speed)
        dy = np.clip(ty - ry, -self.max_speed, self.max_speed)
        # Normalize.
        dx = dx / self.max_speed
        dy = dy / self.max_speed
        # No need to rotate or press.
        return Action(np.array([dx, dy, 0.0, -1.0], dtype=np.float32))

    def _PickStick_terminal(self, state: State, memory: Dict,
                            objects: Sequence[Object], params: Array) -> bool:
        del memory, params  # unused
        return self._Grasped_holds(state, objects)

    def _StickTouchPoint_policy(self, state: State, memory: Dict,
                                objects: Sequence[Object],
                                params: Array) -> Action:
        del memory, params  # unused
        _, stick, point = objects
        point_circ = self._object_to_geom(point, state)
        stick_rect = self._object_to_geom(self._stick, state)
        assert isinstance(stick_rect, utils.Rectangle)
        tip_rect = self._stick_rect_to_tip_rect(stick_rect)
        # If the stick tip is touching the point, press.
        if tip_rect.intersects(point_circ):
            return Action(np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float32))
        # If the stick is vertical, move the tip toward the point.
        stheta = state.get(stick, "theta")
        desired_theta = np.pi / 2
        if abs(stheta - desired_theta) < 1e-3:
            tx = tip_rect.x
            ty = tip_rect.y
            px = state.get(point, "x")
            py = state.get(point, "y")
            dx = np.clip(px - tx, -self.max_speed, self.max_speed)
            dy = np.clip(py - ty, -self.max_speed, self.max_speed)
            # Normalize.
            dx = dx / self.max_speed
            dy = dy / self.max_speed
            # No need to rotate or press.
            return Action(np.array([dx, dy, 0.0, -1.0], dtype=np.float32))
        # Otherwise, rotate the stick.
        dtheta = np.clip(desired_theta - stheta, -self.max_angular_speed,
                         self.max_angular_speed)
        # Normalize.
        dtheta = dtheta / self.max_angular_speed
        return Action(np.array([0.0, 0.0, dtheta, -1.0], dtype=np.float32))

    def _StickTouchPoint_terminal(self, state: State, memory: Dict,
                                  objects: Sequence[Object],
                                  params: Array) -> bool:
        del memory, params  # unused
        _, _, point = objects
        return self._Touched_holds(state, [point])

    @staticmethod
    def _Touched_holds(state: State, objects: Sequence[Object]) -> bool:
        point, = objects
        return state.get(point, "touched") > 0.5

    def _InContact_holds(self, state: State,
                         objects: Sequence[Object]) -> bool:
        obj1, obj2 = objects
        geom1 = self._object_to_geom(obj1, state)
        geom2 = self._object_to_geom(obj2, state)
        return geom1.intersects(geom2)

    @staticmethod
    def _Grasped_holds(state: State, objects: Sequence[Object]) -> bool:
        _, stick = objects
        return state.get(stick, "held") > 0.5

    def _HandEmpty_holds(self, state: State,
                         objects: Sequence[Object]) -> bool:
        robot, = objects
        stick, = state.get_objects(self._stick_type)
        return not self._Grasped_holds(state, [robot, stick])

    def _NoPointInContact_holds(self, state: State,
                                objects: Sequence[Object]) -> bool:
        assert not objects
        robot, = state.get_objects(self._robot_type)
        stick, = state.get_objects(self._stick_type)
        for point in state.get_objects(self._point_type):
            if self._InContact_holds(state, [robot, point]):
                return False
            if self._InContact_holds(state, [stick, point]):
                return False
        return True
