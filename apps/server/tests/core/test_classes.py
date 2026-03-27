"""Tests for the Odoo-style class registry."""

from __future__ import annotations

import pytest

from screamingface.core.classes import ClassRegistry


def test_register_and_resolve(classes: ClassRegistry) -> None:
    class Base:
        def value(self) -> int:
            return 1

    classes.register("test.Base", Base)
    resolved = classes.resolve("test.Base")
    assert resolved is Base
    assert resolved().value() == 1


def test_extend_with_mixin(classes: ClassRegistry) -> None:
    class Base:
        def value(self) -> int:
            return 1

    class Extension(Base):
        def value(self) -> int:
            return super().value() + 10

    classes.register("test.Base", Base)
    classes.extend("test.Base", Extension, plugin_name="ext")

    resolved = classes.resolve("test.Base")
    assert resolved().value() == 11


def test_multiple_extensions_mro(classes: ClassRegistry) -> None:
    class Base:
        def value(self) -> int:
            return 1

    class Ext1(Base):
        def value(self) -> int:
            return super().value() + 10

    class Ext2(Base):
        def value(self) -> int:
            return super().value() * 2

    classes.register("test.Base", Base)
    classes.extend("test.Base", Ext1, plugin_name="p1")
    classes.extend("test.Base", Ext2, plugin_name="p2")

    # MRO: Ext1 -> Ext2 -> Base (first extension is first in MRO)
    # Ext1.value() = super().value() + 10 = Ext2.value() + 10 = (1 * 2) + 10 = 12
    resolved = classes.resolve("test.Base")
    assert resolved().value() == 12


def test_resolve_caching(classes: ClassRegistry) -> None:
    class Base:
        pass

    classes.register("test.Base", Base)
    first = classes.resolve("test.Base")
    second = classes.resolve("test.Base")
    assert first is second


def test_extend_invalidates_cache(classes: ClassRegistry) -> None:
    class Base:
        pass

    class Ext:
        pass

    classes.register("test.Base", Base)
    first = classes.resolve("test.Base")

    classes.extend("test.Base", Ext, plugin_name="p")
    second = classes.resolve("test.Base")
    assert first is not second


def test_unregister_plugin(classes: ClassRegistry) -> None:
    class Base:
        def value(self) -> int:
            return 1

    class Ext(Base):
        def value(self) -> int:
            return super().value() + 10

    classes.register("test.Base", Base)
    classes.extend("test.Base", Ext, plugin_name="removable")

    classes.unregister_plugin("removable")
    resolved = classes.resolve("test.Base")
    assert resolved().value() == 1


def test_register_duplicate_raises(classes: ClassRegistry) -> None:
    class Base:
        pass

    classes.register("test.Base", Base)
    with pytest.raises(ValueError, match="already registered"):
        classes.register("test.Base", Base)


def test_extend_unknown_key_raises(classes: ClassRegistry) -> None:
    class Ext:
        pass

    with pytest.raises(KeyError, match="not registered"):
        classes.extend("nonexistent.Key", Ext, plugin_name="p")


def test_resolve_unknown_key_raises(classes: ClassRegistry) -> None:
    with pytest.raises(KeyError, match="not registered"):
        classes.resolve("nonexistent.Key")


def test_list_keys(classes: ClassRegistry) -> None:
    class A:
        pass

    class B:
        pass

    classes.register("z.Class", A)
    classes.register("a.Class", B)
    assert classes.list_keys() == ["a.Class", "z.Class"]
