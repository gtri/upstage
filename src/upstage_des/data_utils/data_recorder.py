"""Class for custom recording of things."""

from copy import deepcopy
from typing import Any

from upstage_des.base import SPECIAL_ENTITY_CONTEXT_VAR, UpstageBase


class DataRecorder(UpstageBase):
    """An UpstageBase subclass to help with data recording."""

    def record_data(self, data: Any, copy: bool = False) -> None:
        """Record any data at this time for retrieval later.

        The data recorded should be immutable or unchanging to preserve
        the values of the data at a given time. E.g. don't supply an Actor
        or other objects that change. Dictionaries or dataclasses are fine
        as long as they are not used anywhere else.

        A deepcopy parameter is supplied to get around this, but it may not
        work with all entities or objects.

        Args:
            data (Any): Any object or data to record.
            copy (bool, optional): Whether to attempt a deepcopy.
                Defaults to False.
        """
        ans = SPECIAL_ENTITY_CONTEXT_VAR.get().data_recorded
        inp = data if not copy else deepcopy(data)
        ans.append((self.env.now, inp))


def record_data(data: Any, copy: bool = False) -> None:
    """Record any data at this time for retrieval later.

    The data recorded should be immutable or unchanging to preserve
    the values of the data at a given time. E.g. don't supply an Actor
    or other objects that change. Dictionaries or dataclasses are fine
    as long as they are not used anywhere else.

    A deepcopy parameter is supplied to get around this, but it may not
    work with all entities or objects.

    This function must be run inside an environment context.

    Args:
        data (Any): Any object or data to record.
        copy (bool, optional): Whether to attempt a deepcopy.
            Defaults to False.
    """
    dr = DataRecorder()
    dr.record_data(data, copy=copy)


def get_recorded_data() -> list[tuple[float, Any]]:
    """Return all data recorded with record_data or DataRecorder.

    Returns:
        list[tuple[float, Any]]: The data.
    """
    dr = DataRecorder()
    return dr.get_recorded()
