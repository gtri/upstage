"""Simple input structure for manufacturing style problems."""
from collections.abc import Callable
from dataclasses import dataclass, field
from random import Random


@dataclass
class ManufacturingItemData:
    """Datatype for an item."""
    name: str
    amount: float


@dataclass
class ManufacturingProcessData:
    """A simplified manufacturing process with only inputs/outputs.
    
    A simple implied model for how it works.
    """
    name: str
    inputs: list[ManufacturingItemData]
    outputs: list[ManufacturingItemData]
    timing: float | Callable[[Random], float]
    success_rate: float = field(default=1.0)

    def has_output(self, name: str) -> bool:
        return any([name==o.name for o in self.outputs])
    
    def has_input(self, name: str) -> bool:
        return any([name==i.name for i in self.inputs])

    def get_output(self, name: str) -> ManufacturingItemData:
        return [o for o in self.outputs if name==o.name][0]
    
    def get_input(self, name: str) -> ManufacturingItemData:
        return [i for i in self.inputs if name==i.name][0]


@dataclass
class ManufacturingStationData:
    """A location that can do one of several kinds of processing."""
    name: str
    capable_processes: list[str]


@dataclass
class ShopFloorData:
    """A manufacturing plant, very roughly approximated."""
    name: str
    machines: list[ManufacturingStationData]
    station_locations: dict[str, tuple[float, float]]
    robot_depot: tuple[float, float]
    input_station: tuple[float, float]
    output_station: tuple[float, float]
    extent: tuple[float, float]
