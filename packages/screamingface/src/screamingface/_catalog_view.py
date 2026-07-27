"""Interactive engine-catalog views with an ipywidgets-free static fallback.

FEATURE: sf.models.view() / sf.benchmarks.view() browse the engine catalog in a notebook.
STORY: as a researcher, I search the catalog and read the exact provider/model IDs I can use.
INVARIANT: `.value` is the tuple of IDs currently shown after filtering, so `view(...).value`
equals `list(...)` for the same query/tools arguments.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from screamingface._card_display import (
    _STYLE,
    benchmarks_rows_html,
    catalog_html,
    models_rows_html,
)

if TYPE_CHECKING:
    from screamingface._profile import BenchmarkRecord, ModelRecord


class _CatalogView(ABC):
    """Shared behavior for the model and benchmark catalog browsers."""

    _title: str
    _aria: str
    _placeholder: str

    def __init__(self, records: Sequence[Any]) -> None:
        self._records = tuple(records)
        self._query = ""
        self._body: Any = None

    @property
    def value(self) -> list[str]:
        """IDs currently shown after the active search filter."""

        return [self._id(record) for record in self._visible()]

    def _visible(self) -> tuple[Any, ...]:
        needle = self._query.strip().casefold()
        if not needle:
            return self._records
        return tuple(record for record in self._records if needle in self._id(record).casefold())

    def widget(self) -> Any:
        """Build the interactive notebook view when the notebook extra is installed."""

        try:
            import ipywidgets as widgets
        except ImportError as exc:  # pragma: no cover - exercised in a dependency-isolated install
            raise ImportError(
                "Install screamingface[notebook] to use the interactive catalog view."
            ) from exc

        header = widgets.HTML(
            value=(
                f"{_STYLE}<div class='sf-catalog__head'>"
                f"<div class='sf-catalog__title'>{self._title}</div></div>"
            )
        )
        search = widgets.Text(placeholder=self._placeholder)
        self._body = widgets.HTML()

        def on_change(change: dict[str, Any]) -> None:
            self._query = change["new"]
            self._render()

        search.observe(on_change, names="value")
        root = widgets.VBox(children=(header, search, self._body))
        root.add_class("sf-ui")
        root.add_class("sf-catalog-widget")
        root.add_class("sf-catalog")
        self._render()
        return root

    def _render(self) -> None:
        if self._body is not None:
            self._body.value = self._rows_html(self._visible())

    def _repr_html_(self) -> str:
        return catalog_html(
            self._title, self._aria, len(self._records), self._rows_html(self._records)
        )

    def _ipython_display_(self) -> None:
        from IPython.display import display

        display(self.widget())

    def __repr__(self) -> str:
        return f"{type(self).__name__}({len(self._records)} shown)"

    @abstractmethod
    def _id(self, record: Any) -> str: ...

    @abstractmethod
    def _rows_html(self, records: Sequence[Any]) -> str: ...


class ModelsView(_CatalogView):
    """A searchable view over engine-advertised model records."""

    _title = "Models"
    _aria = "ScreamingFace model catalog"
    _placeholder = "Filter models…"

    def _id(self, record: ModelRecord) -> str:
        return record.id

    def _rows_html(self, records: Sequence[ModelRecord]) -> str:
        return models_rows_html(records)


class BenchmarksView(_CatalogView):
    """A searchable view over engine-advertised benchmark records."""

    _title = "Benchmarks"
    _aria = "ScreamingFace benchmark catalog"
    _placeholder = "Filter benchmarks…"

    def _id(self, record: BenchmarkRecord) -> str:
        return record.id

    def _rows_html(self, records: Sequence[BenchmarkRecord]) -> str:
        return benchmarks_rows_html(records)


__all__ = ["BenchmarksView", "ModelsView"]
