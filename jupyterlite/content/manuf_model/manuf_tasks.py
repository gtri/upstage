"""Tasks for shop floor machines and planning."""
from collections import defaultdict
from dataclasses import replace

from actors import ManufacturingShop, ManufacturingStation
from inputs import ManufacturingItemData
from utils import assign_work, solve_for_inputs

import upstage_des.api as UP
from upstage_des.type_help import TASK_GEN

### Station tasks


class StationHold(UP.Task):
    """Wait for a job to be assigned."""
    def task(self, *, actor: ManufacturingStation) -> TASK_GEN:
        """Infinite hold until a variable being set kicks us out."""
        if actor.current_job is None:
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
        recipe = [j for j in actor.possible_jobs if j.name == actor.current_job][0]
        while True:
            # put out a request for items!
            yield UP.Put(actor.shop.needs, (self, recipe))
            inp: ManufacturingItemData = yield UP.Get(actor.input_queue)
            current_inputs[inp.name] += inp.amount
            if all(
                current_inputs[need.name] <= need.amount
                for need in recipe.inputs
            ):
                # We can process the recipe and put the rest of the ingredients
                # back on the input stack.
                use = {need.name: need.amount for need in recipe.inputs}
                for k, v in current_inputs.items():
                    amt = v - use.get(k, 0)
                    if amt > 0:
                        yield UP.Put(actor.input_queue, ManufacturingItemData(k, amt))


class StationTask(UP.Task):
    """Process materials."""
    def task(self, *, actor: ManufacturingStation) -> TASK_GEN:
        """Create outputs from inputs."""
        rng = UP.get_stage().random
        recipe = [j for j in actor.possible_jobs if j.name == actor.current_job][0]

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
        # Find the stations that can produce the goals
        process_counts = solve_for_inputs(goals, actor.processes)
        # hard coded for now..
        classes = ["Chemistry", "Cutter", "Paper Making", "Adhesion", "Sandpaper"]
        assignment, message = assign_work(process_counts, actor.stations, classes)
        if assignment is None:
            raise UP.SimulationError(f"Bad solve in assignment: {message}")
        for machine_name, processes in assignment.items():
            ...


class ShopRobotTasking(UP.Task):
    """Watch for changes that need a robot."""
    def task(self, *, actor: ManufacturingShop) -> TASK_GEN:
        """Check for outputs to call robots."""
        stations = list(actor.stations.values())
        gets = [
            UP.Get(station.output_queue)
            for station in stations
        ]
        yield UP.Any(*gets)
        for station, get in zip(stations, gets):
            if get.is_complete():
                # Kick off a task to get robots!
                ...
            else:
                get.cancel()
