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
    locations: dict[str, tuple[float, float]]
