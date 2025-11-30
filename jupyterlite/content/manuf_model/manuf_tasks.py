"""Tasks for shop floor machines and planning."""
from collections import defaultdict
from dataclasses import replace
from itertools import chain

from manuf_model.actors import ManufacturingShop, ManufacturingStation
from manuf_model.inputs import ManufacturingItemData
from manuf_model.utils import assign_work, solve_for_inputs

import upstage_des.api as UP
from upstage_des.type_help import TASK_GEN

### Station tasks


class StationHold(UP.Task):
    """Wait for a job to be assigned."""
    def task(self, *, actor: ManufacturingStation) -> TASK_GEN:
        """Infinite hold until a variable being set kicks us out."""
        if actor.job_list is None:
            yield UP.Event

    def on_interrupt(
        self,
        *,
        actor: ManufacturingStation,
        cause: UP.NucleusInterrupt,
    ) -> UP.InterruptStates:
        """Interrupt - expecting nucleus."""
        assert cause.state_name == "current_job"
        return UP.InterruptStates.END


class StationInputWait(UP.Task):
    """Wait for materials to arrive to do a task."""
    def task(self, *, actor: ManufacturingStation) -> TASK_GEN:
        """Wait for inputs."""
        current_inputs: dict[str, int] = defaultdict(int)
        assert actor.job_list is not None
        next_job = sorted(actor.job_list, key=actor.job_ranks.__getitem__)[0]
        self.set_actor_knowledge(actor, "chosen job", next_job, overwrite=True)
        recipe = [j for j in actor.possible_jobs if j.name == next_job][0]
        actor.log(f"Got job: {next_job}")
        # put out a request for items!
        yield UP.Put(actor.shop.needs, (self, recipe))
        while any(
            current_inputs[need.name] < need.amount
            for need in recipe.inputs
        ):
            inp: ManufacturingItemData = yield UP.Get(actor.input_queue)
            current_inputs[inp.name] += inp.amount


class StationTask(UP.Task):
    """Process materials."""
    def task(self, *, actor: ManufacturingStation) -> TASK_GEN:
        """Create outputs from inputs."""
        rng = UP.get_stage().random
        job = self.get_actor_knowledge(actor, "chosen job", must_exist=True)
        recipe = [j for j in actor.possible_jobs if j.name == job][0]

        time_to_proc = recipe.timing \
            if isinstance(recipe.timing, float) else \
            recipe.timing(rng)

        actor.attempted_jobs[recipe.name] += 1

        yield UP.Wait(time_to_proc)
        success = recipe.success_rate <= rng.random()
        if success:
            actor.jobs_done[recipe.name] += 1
            for output in recipe.outputs:
                actor.products_made[output.name] += output.amount
            # Dump all the outputs in one
            yield UP.Put(actor.output_queue, [replace(x) for x in recipe.outputs])
        else:
            yield UP.Put(actor.output_queue, [ManufacturingItemData(name="TRASH", amount=1)])

        # Remove memory/goal of the job.
        self.clear_actor_knowledge(actor, "chosen job")
        actor.job_list.remove(job)
        # Hold on processing until the output is cleared
        evt = actor.create_knowledge_event("OUTPUT CLEARED")
        yield evt


station_process_net = UP.TaskNetworkFactory.from_ordered_loop(
    "station processing net",
    [StationHold, StationInputWait, StationTask],
)

### Shop management tasks
class ShopStart(UP.DecisionTask):
    """Set requirements for the shop."""
    def make_decision(self, *, actor: ManufacturingShop) -> None:
        """Set requirements then be done."""
        goals: list[ManufacturingItemData] = actor.get_knowledge("output goals", must_exist=True)
        assignment: dict[str, dict[str, int]] = actor.get_knowledge("assignment", must_exist=True)
        for machine_name, processes in assignment.items():
            process_list = list(chain(*[[k]*v for k,v in processes.items()]))
            actor.stations[machine_name].job_list = process_list


class ShopRobotTasking(UP.Task):
    """Watch for changes that need a robot."""
    def task(self, *, actor: ManufacturingShop) -> TASK_GEN:
        """Check for outputs to call robots."""
        need_get = UP.Get(actor.needs)
        stations = list(actor.stations.values())
        gets = [
            UP.Get(station.output_queue)
            for station in stations
        ] + [need_get]
        yield UP.Any(*gets)
        # satisfy an input need first.
        if need_get.is_complete():
            ...


shop_process_net = UP.TaskNetworkFactory(
    "shop process network",
    task_classes={"ShopStart": ShopStart, "ShopRobotTasking": ShopRobotTasking},
    task_links={
        "ShopStart": UP.TaskLinks(default="ShopRobotTasking", allowed=["ShopRobotTasking"]), 
        "ShopRobotTasking": UP.TaskLinks(default="ShopRobotTasking", allowed=["ShopRobotTasking"]),
    },
)