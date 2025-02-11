# Copyright (C) 2024 by the Georgia Tech Research Institute (GTRI)

# Licensed under the BSD 3-Clause License.
# See the LICENSE file in the project root for complete license terms and disclaimers.
"""Filter stores that allow sorting of items."""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from simpy import Store
from simpy.resources.base import BoundClass, Get

from ..events import Get as UPGet

__all__ = ("SortedFilterStore", "SortedFilterGet")


class _SortedFilterStoreGet(Get):
    """A getter for a custom store to retrieve items using filters and priorities.

    Request to get an *item* from the *store* matching the *filter* and
    minimizing the *sorter*. The request is triggered once there is such an
    item available in the store.

    *filter* should return ``True`` for items matching the filter criterion.
    The default function returns ``True`` for all items, which makes the
    request behave exactly like :class:`StoreGet`.

    *sorter* is a function receiving one item. It should return a value that
    is to be minimized among the filter items. The default function is to not
    sort, which makes the request behave exactly like :class:`FilterStoreGet`.

    :param resource:
    :param filter: filter function for one item
    :param sorter: sort function for one item

    :type resource:
    :type filter: function
    :type sorter: function

    """

    def __init__(
        self,
        resource: "SortedFilterStore",
        filter: Callable[[Any], bool] = lambda item: True,
        sorter: Callable[[Any], tuple[Any, ...]] | None = None,
        reverse: bool = False,
    ):
        self.filter = filter
        self.sorter = sorter
        self.reverse = reverse
        super().__init__(resource)


class SortedFilterStore(Store):
    """A store that supports the filtered and sorted retrieval of items.

    Resource with *capacity* slots for storing arbitrary objects supporting
    filtered and sorted get requests. Like the :class:`Store`, the *capacity*
    is unlimited by default and objects are put and retrieved from the store in
    a first-in first-out order.

    Get requests can be customized with a filter function to only trigger for
    items for which said filter function returns ``True``. They can further be
    customized with a sorter function that prioritizes which of the filtered
    items are to be returned. The prioritization happens through a
    minimization.

    """

    # Request to get an *item* for which *filter* returns ``True`` and for
    # which *sorter* returns the minimum value out of the store.
    if TYPE_CHECKING:

        def get(self) -> _SortedFilterStoreGet:  # type: ignore[override]
            """Request to get an *item* out of the store."""
            return _SortedFilterStoreGet(self)

    else:
        get = BoundClass(_SortedFilterStoreGet)

    def _do_get(self, event: _SortedFilterStoreGet) -> bool:  # type: ignore[override]
        min_item: Any = None
        # min_val is a tuple, in case the sorter returns an iterable
        min_val: tuple[Any, ...] | None = None
        for item in self.items:
            if event.filter(item):
                if event.sorter is not None:
                    val = event.sorter(item)
                    if min_val is None or (val > min_val if event.reverse else val < min_val):
                        min_item = item
                        min_val = val
                else:
                    min_item = item
                    break
        if min_item:
            self.items.remove(min_item)
            event.succeed(min_item)
        return True


class SortedFilterGet(UPGet):
    """A Get for a SortedFilterStore."""

    def __init__(
        self,
        get_location: SortedFilterStore,
        filter: Callable[[Any], bool] = lambda item: True,
        sorter: Callable[[Any], tuple[Any, ...]] | None = None,
        reverse: bool = False,
        rehearsal_time_to_complete: float = 0.0,
    ) -> None:
        """Create a Get request on a SortedFilterStore.

        The filter function returns a boolean (True/False for in/out of consideration).

        The sorter function must return something sortable (number, tuple, e.g.)

        Args:
            get_location (SIM.Store | SIM.Container): The place for the Get request
            filter (Callable[[Any], bool]): The function that filters items in the store.
            sorter (Callable[[Any], Any]): The function that returns values to sort an item on.
            reverse (bool, optional): Whether to reverse the sort to be ascending.
            rehearsal_time_to_complete (float, optional): _description_. Defaults to 0.0.
        """
        super().__init__(
            get_location=get_location,
            rehearsal_time_to_complete=rehearsal_time_to_complete,
            filter=filter,
            sorter=sorter,
            reverse=reverse,
        )
