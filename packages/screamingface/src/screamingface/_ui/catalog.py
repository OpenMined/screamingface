"""Sequence-like Client catalogues with optional notebook interactivity."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator, Sequence
from typing import Any, overload

from screamingface._ui.card_style import CARD_STYLE
from screamingface._ui.cards import (
    benchmarks_rows_html,
    cases_rows_html,
    catalog_html,
    models_rows_html,
)
from screamingface.discovery import Benchmark, CaseInfo, ModelInfo


class _Catalog[T](Sequence[T], ABC):
    """Immutable data value; notebook filtering lives only in a rendered widget."""

    __slots__ = ("_values",)

    _title: str
    _aria: str
    _placeholder: str

    def __init__(self, values: Sequence[T]) -> None:
        self._values = tuple(values)

    def __len__(self) -> int:
        return len(self._values)

    def __iter__(self) -> Iterator[T]:
        return iter(self._values)

    @overload
    def __getitem__(self, index: int) -> T: ...

    @overload
    def __getitem__(self, index: slice) -> tuple[T, ...]: ...

    def __getitem__(self, index: int | slice) -> T | tuple[T, ...]:
        return self._values[index]

    def __eq__(self, other: object) -> bool:
        if isinstance(other, _Catalog):
            return self._values == other._values
        if isinstance(other, tuple):
            return self._values == other
        return False

    def __repr__(self) -> str:
        return f"{self._title}({len(self)})"

    def _repr_html_(self) -> str:
        return catalog_html(self._title, self._aria, len(self), self._rows(self._values))

    def _ipython_display_(self) -> None:
        from IPython.display import HTML, display

        try:
            display(self._widget())
        except ImportError:
            display(HTML(self._repr_html_()))

    def _widget(self) -> Any:
        try:
            import ipywidgets as widgets
        except ImportError as exc:
            raise ImportError(
                "Install screamingface[notebook] for interactive catalogue search."
            ) from exc

        header = widgets.HTML(
            value=(
                f"{CARD_STYLE}<div class='sf-card__accent sf-card__accent--solid'></div>"
                "<div class='sf-catalog__head'>"
                f"<div class='sf-catalog__title'>{self._title}</div>"
                f"<div class='sf-catalog__count'>{len(self)}</div></div>"
            )
        )
        search = widgets.Text(placeholder=self._placeholder)
        body = widgets.HTML(value=self._rows(self._values))

        def on_change(change: dict[str, Any]) -> None:
            query = str(change["new"]).strip().casefold()
            visible = tuple(value for value in self._values if self._matches(value, query))
            body.value = self._rows(visible)

        search.observe(on_change, names="value")
        root = widgets.VBox(children=(header, search, body))
        root.add_class("sf-ui")
        root.add_class("sf-catalog-widget")
        root.add_class("sf-catalog")
        return root

    def _matches(self, value: T, query: str) -> bool:
        return not query or query in self._search_text(value).casefold()

    @abstractmethod
    def _search_text(self, value: T) -> str:
        """Return searchable real fields for one record."""

    @abstractmethod
    def _rows(self, values: Sequence[T]) -> str:
        """Render escaped rows for one catalogue kind."""


class _ModelCatalog(_Catalog[ModelInfo]):
    _title = "Models"
    _aria = "ScreamingFace model catalogue"
    _placeholder = "Filter models…"

    def _search_text(self, value: ModelInfo) -> str:
        return f"{value.id} {value.provider}"

    def _rows(self, values: Sequence[ModelInfo]) -> str:
        return models_rows_html(values)


class _BenchmarkCatalog(_Catalog[Benchmark]):
    _title = "Benchmarks"
    _aria = "ScreamingFace benchmark catalogue"
    _placeholder = "Filter benchmarks…"

    def _search_text(self, value: Benchmark) -> str:
        return f"{value.id} {value.title} {value.description}"

    def _rows(self, values: Sequence[Benchmark]) -> str:
        return benchmarks_rows_html(values)


class _CaseCatalog(_Catalog[CaseInfo]):
    """One fetched page of a Benchmark's public cases, with its paging envelope."""

    __slots__ = ("limit", "offset", "total")

    _title = "Cases"
    _aria = "ScreamingFace benchmark cases"
    _placeholder = "Filter cases…"

    def __init__(self, values: Sequence[CaseInfo], *, total: int, limit: int, offset: int) -> None:
        super().__init__(values)
        self.total = total
        self.limit = limit
        self.offset = offset

    def __repr__(self) -> str:
        return f"Cases({len(self)} of {self.total}, offset={self.offset})"

    def _search_text(self, value: CaseInfo) -> str:
        return f"{value.id} {value.input}"

    def _rows(self, values: Sequence[CaseInfo]) -> str:
        return cases_rows_html(values)


__all__: list[str] = []
