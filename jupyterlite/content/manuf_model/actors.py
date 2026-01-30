"""Actors for a simple machine shop."""
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

import networkx as nx
from manuf_model.inputs import ManufacturingItemData, ManufacturingProcessData

import upstage_des.api as UP


class ManufacturingStation(UP.Actor):
    """A station that does some manufacturing task."""
    location = UP.State[UP.CartesianLocation]()
    possible_jobs = UP.State[list[ManufacturingProcessData]]()
    job_ranks = UP.State[dict[str, int]]()
    shop = UP.State["ManufacturingShop"](default=None, allow_none_default=True)
    job_list = UP.State[list[str] | None](default=None, allow_none_default=True)
    output_location = UP.State[str](default="")
    attempted_jobs = UP.DictionaryState[int](valid_types=(int,), recording=True)
    jobs_done = UP.DictionaryState[int](valid_types=(int,), recording=True)
    products_made = UP.DictionaryState[int](valid_types=(int,), recording=True)
    input_queue = UP.ResourceState[UP.SelfMonitoringStore](
        valid_types=UP.SelfMonitoringStore,
        default=UP.SelfMonitoringStore,
    )
    output_queue = UP.ResourceState[UP.SelfMonitoringStore](
        valid_types=UP.SelfMonitoringStore,
        default=UP.SelfMonitoringStore,
    )


@dataclass
class NeedsData:
    time: float
    needing_station: ManufacturingStation
    kind: Literal["OUTPUT", "INPUT"]
    need: ManufacturingProcessData | list[ManufacturingItemData]


class ManufacturingShop(UP.Actor):
    """Coordinate a shop floor."""
    stations = UP.State[dict[str, ManufacturingStation]]()
    processes = UP.State[list[ManufacturingProcessData]]()
    robot_capacity = UP.State[dict[str, int]]()
    robots = UP.MultiStoreState(
        valid_types=UP.SelfMonitoringContainer,
        default=UP.SelfMonitoringContainer,
    )
    storage = UP.MultiStoreState(
        valid_types=UP.SelfMonitoringContainer,
        default=UP.SelfMonitoringContainer,
    )
    needs = UP.ResourceState[UP.SelfMonitoringStore](
        valid_types=UP.SelfMonitoringStore,
        default=UP.SelfMonitoringStore,
    )
    outgoing = UP.ResourceState[UP.SelfMonitoringStore](
        valid_types=UP.SelfMonitoringStore,
        default=UP.SelfMonitoringStore,
    )
    paths = UP.State[nx.DiGraph](valid_types=nx.DiGraph)
    _pending_needs = UP.State[list[NeedsData]](default_factory=list)
    status_change = UP.State[int](default=0)

    @lru_cache
    def robot_counts(self, amount: int) -> set[tuple[int, ...]]:
        """Create options for robot counts to move items.

        Args:
            amount (int): Amount of items to move.

        Returns:
            set[tuple[int, ...]]: Options.
        """
        # Dictionaries change ordering from run to run, so determinism is
        # better guaranteed after a key sort.
        keys = sorted(self.robot_capacity)
        capacity = [self.robot_capacity[k] for k in keys]
        if amount <= 0:
            return set([tuple([0]*len(capacity))])
        opts = set()
        for i, cap in enumerate(capacity):
            for opt in self.robot_counts(amount - cap):
                n_carry = sum(c*v for c,v in zip(capacity, opt))
                z = list(opt)
                if n_carry < amount:
                    z[i] += 1
                opts.add(tuple(z))
        return opts


class TransportRobot(UP.Actor):
    """Robot."""
    capacity = UP.State[float]()
    holding = UP.State[list[ManufacturingItemData]](default_factory=list, recording=True)
    location = UP.CartesianLocationChangingState(recording=True)
    sight_radius = UP.State[float](default=0.5)
