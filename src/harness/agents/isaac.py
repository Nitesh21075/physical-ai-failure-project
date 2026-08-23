"""Controller for the bounded Phase 2 Isaac Sim reference scene."""

from __future__ import annotations

from math import hypot

from harness.schemas import Action, Observation


class IsaacPlanarVelocityController:
    """Drives the Isaac rigid-body robot proxy straight toward its 2-D target."""

    def __init__(self, speed: float = 1.0) -> None:
        if speed <= 0:
            raise ValueError("speed must be positive")
        self.speed = speed

    def act(self, observation: Observation) -> Action:
        robot_x, robot_y, _ = observation.state["robot_position"]
        target_x, target_y = observation.state["target_position"]
        delta_x = float(target_x) - float(robot_x)
        delta_y = float(target_y) - float(robot_y)
        distance = hypot(delta_x, delta_y)
        if distance == 0:
            return Action("set_planar_velocity", {"x": 0.0, "y": 0.0})
        return Action(
            "set_planar_velocity",
            {"x": self.speed * delta_x / distance, "y": self.speed * delta_y / distance},
        )
