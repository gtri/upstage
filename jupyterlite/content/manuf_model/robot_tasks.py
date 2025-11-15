"""Tasks for robot motion."""
from actors import ManufacturingShop, ManufacturingStation
from inputs import ManufacturingItemData

import upstage_des.api as UP
from upstage_des.type_help import TASK_GEN

### Robot tasks

class MoveProducts(UP.Task):
    """A task to handle sending robots to move a product."""
    def task(self, *, actor: ManufacturingShop) -> TASK_GEN:
        """Go robot, go!"""
        name = self._network_name
        station: ManufacturingStation
        output: list[ManufacturingItemData]
        station, output = self.get_and_clear_actor_knowledge(
            actor,
            f"{name}_station",
        )
        output_weight = sum(o.amount for o in output)
        robot_counts = actor.robot_counts(output_weight)
        # See if we can get any of the combinations, sorted by fewest
        # number of robots
        for comb in sorted(robot_counts, key=sum):
            ...

mover_factory = UP.TaskNetworkFactory.from_single_terminating(
    "do robot things",
    MoveProducts,
)
