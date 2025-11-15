"""Loading helpers."""
import yaml
from pathlib import Path
import re
from typing import TypedDict

from upstage_des.units import unit_convert

from manuf_model.inputs import ManufacturingItemData, ManufacturingProcessData, ManufacturingStationData, ShopFloorData


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


class Loaded(TypedDict):
    input_resources: list[ManufacturingItemData]
    recipes: list[ManufacturingProcessData]
    shop: ShopFloorData
    machine_classes: dict[str, list[str]]


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
    return {
        "input_resources": input_resources,
        "recipes": recipes,
        "shop": shop_floor,
        "machine_classes": data["machine_classes"],
    }