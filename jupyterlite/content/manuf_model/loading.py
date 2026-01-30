"""Loading helpers."""
import yaml
from pathlib import Path
import re
from typing import TypedDict
import networkx as nx

import upstage_des.api as UP
from upstage_des.units import unit_convert

from manuf_model.actors import ManufacturingStation, ManufacturingShop
from manuf_model.inputs import ManufacturingItemData, ManufacturingProcessData, ManufacturingStationData, ShopFloorData
from manuf_model import utils, manuf_tasks


def _time_string(input: str | float) -> float:
    """Convert a time-like string to hours.
    
    Args:
        input (str | float): The time string

    Returns:
        float: the time in hours
    """
    if isinstance(input, float | int):
        return float(input)
    time_pairs = re.findall(r"([\d\.]+)\s+(\b[a-zA-Z]+\b)", input)
    time = 0.0
    for amt, unit in time_pairs:
        time += unit_convert(float(amt), unit, "hours")
    return time


class RobotData(TypedDict):
    capacity: float
    count: int


class Loaded(TypedDict):
    input_resources: list[ManufacturingItemData]
    recipes: list[ManufacturingProcessData]
    shop: ShopFloorData
    machine_classes: dict[str, list[str]]
    robots: dict[str, RobotData]


def load_from_yaml(file: Path) -> Loaded:
    """Load a sim from a yaml.

    Args:
        file (Path): File to load.

    Returns:
        Loaded: The dictionary of shop data.
    """
    data = yaml.safe_load(file.read_text())
    input_resources = [
        ManufacturingItemData(k, v)
        for k, v in data.get("raw_inputs", {}).items()
    ]
    recipes = [
        ManufacturingProcessData(
            name=recipe["name"],
            inputs=[
                ManufacturingItemData(k, v)
                for k, v in recipe.get("inputs", {}).items()
            ],
            outputs=[
                ManufacturingItemData(k, v)
                for k, v in recipe.get("outputs", {}).items()
            ],
            timing=_time_string(recipe["timing"]),
            success_rate=recipe.get("success_rate", 1.0),
        )
        for recipe in data.get("manufacturing_recipes", [])
    ]
    stations = [
        ManufacturingStationData(**station)
        for station in data.get("manufacturing_stations", [])
    ]
    shop = data["shop_layout"]
    shop_floor = ShopFloorData(
        name="The Shop",
        machines=stations,
        station_locations={k: tuple(v) for k, v in shop["machine_locations"].items()},
        robot_depot=shop["robot_depot"],
        input_station=shop["input_station"],
        output_station=shop["output_station"],
        extent=shop["extent"],
    )
    robots = {k: {**v} for k, v in data["robots"].items()}
    return {
        "input_resources": input_resources,
        "recipes": recipes,
        "shop": shop_floor,
        "machine_classes": data["machine_classes"],
        "robots": robots,
    }


def start_model(
    inputs: Loaded,
    goals: list[ManufacturingItemData],
):
    process_counts, process_ranks, needs = utils.solve_for_inputs(
        outputs=goals,
        processes=inputs["recipes"],
    )
    machine_to_job, res = utils.assign_work(
        {k: v for k,v in process_counts.items() if v>0},
        inputs["shop"].machines,
        inputs["machine_classes"],
    )
    if machine_to_job is None:
        raise ValueError(f"Bad planning solve: {res}")
    
    shop = inputs["shop"]

    robot_capacity = {k: v["capacity"] for k, v in inputs["robots"].items()}
    all_resources = {
        manuf_item.name
        for recipe in inputs["recipes"]
        for manuf_item in recipe.inputs
    } | {
        manuf_item.name
        for recipe in inputs["recipes"]
        for manuf_item in recipe.outputs
    }
    res_amounts = inputs["input_resources"]
    with UP.EnvironmentContext() as env:
        locs = shop.station_locations
        stations = [
            ManufacturingStation(
                name=station.name,
                location = UP.CartesianLocation(*locs[station.name]),
                possible_jobs=[
                    [r for r in inputs["recipes"] if r.name == proc][0]
                    for proc in station.capable_processes
                ],
                job_ranks=process_ranks,
            )
            for station in shop.machines
        ]

        the_shop = ManufacturingShop(
            name=shop.name,
            stations={s.name: s for s in stations},
            processes=inputs["recipes"],
            robot_capacity={k: v["capacity"] for k, v in inputs["robots"].items()},
            robots={k: {"init": v["count"]} for k, v in inputs["robots"].items()},
            storage={r:{"init":res_amounts.get(r, 0.0)} for r in all_resources},
            paths=nx.DiGraph(),
        )
        the_shop.set_bulk_knowledge(
            {
                "output goals": goals,
                "assignment": machine_to_job,
            },
        )

        for s in stations:
            s.shop = the_shop
            # Start the station process
            net = manuf_tasks.station_process_net.make_network()
            s.add_task_network(net)
            s.start_network_loop(net.name, "StationHold")
            # Make a nucleus to watch state(s)
            nuc = UP.TaskNetworkNucleus(s)
            nuc.add_network(net.name, ["current_job"])

        # For the shop, we just have one net
        shop_net = manuf_tasks.shop_process_net.make_network()
        the_shop.add_task_network(shop_net)
        
        
        # WAIT TO START IT
        nuc = UP.TaskNetworkNucleus(actor=the_shop)
        nuc.add_network(shop_net.name, ["status_change"])
        the_shop.start_network_loop(shop_net.name, "ShopStart")
