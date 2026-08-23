from harness.agents.isaac import IsaacPlanarVelocityController
from harness.schemas import Observation


def test_isaac_planar_velocity_controller_aims_at_target():
    action = IsaacPlanarVelocityController(speed=2.0).act(
        Observation(
            simulation_time=0.0,
            state={"robot_position": [0.0, 0.0, 0.25], "target_position": [3.0, 4.0]},
        )
    )

    assert action.name == "set_planar_velocity"
    assert action.parameters == {"x": 1.2, "y": 1.6}
