"""Helpers and proxies for States."""

from collections.abc import ItemsView, Iterable, KeysView, ValuesView
from dataclasses import is_dataclass
from typing import TYPE_CHECKING, Any, Generic, TypeVar

VTD = TypeVar("VTD")
TDC = TypeVar("TDC")


if TYPE_CHECKING:
    from .actor import Actor  # pragma: no cover
    from .states import _KeyValueBase  # pragma: no cover


class _DictionaryProxy(Generic[VTD]):
    """An in-between way to have dictionary-like access on descriptors."""

    def __init__(
        self,
        descriptor: "_KeyValueBase",
        instance: "Actor",
        wrapped: dict[str, VTD],
    ):
        self.descriptor = descriptor
        self.instance = instance
        self._wrapped = wrapped

    def __setitem__(self, key: str, value: VTD) -> None:
        self._wrapped[key] = value
        if not self.descriptor._type_check(value, throw=False):
            raise TypeError(f"Bad type for dictionary: {key}: {value}")
        self.descriptor._record_state(self.instance, key, all=False)

    def setdefault(self, key: str, value: VTD) -> VTD:
        if key in self._wrapped:
            return self._wrapped[key]
        self.__setitem__(key, value)
        return value

    def items(self) -> ItemsView[str, VTD]:
        """Get the items from the proxied dictionary.

        Returns:
            list[tuple[str, MST]]
        """
        return self._wrapped.items()

    def keys(self) -> KeysView[str]:
        """Get the keys from the proxied dictionary.

        Returns:
            list[str]
        """
        return self._wrapped.keys()

    def values(self) -> ValuesView[VTD]:
        """Get the items from the proxied dictionary.

        Returns:
            list[MST]
        """
        return self._wrapped.values()

    def __getitem__(self, key: str) -> VTD:
        return self._wrapped[key]

    def __iter__(self) -> Iterable[str]:
        yield from self._wrapped

    def __contains__(self, key: str) -> bool:
        return key in self._wrapped


class _DataclassProxy(Generic[TDC]):
    def __init__(self, descr: "_KeyValueBase", instance: "Actor", wrapped: TDC):
        self._descr = descr
        self._inst = instance
        if not is_dataclass(wrapped):
            raise TypeError("Wrapped value is not dataclass")
        self._wrapped = wrapped

    @property
    def __dataclass_fields__(self) -> Any:
        """Support asking for fields() on the proxy."""
        return self._wrapped.__dataclass_fields__

    def _typecheck(self, name: str, value: Any) -> None:
        field_type = self._wrapped.__annotations__[name]
        if not isinstance(value, field_type):
            raise TypeError(
                f"Dataclass value {value} for field {name} doesn't match type: {field_type}."
            )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._wrapped, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name in ["_wrapped", "_descr", "_inst"]:
            super().__setattr__(name, value)
        elif is_dataclass(self._wrapped):
            if hasattr(self._wrapped, name):
                self._typecheck(name, value)
                setattr(self._wrapped, name, value)
                self._descr._record_state(self._inst, name, all=False)
