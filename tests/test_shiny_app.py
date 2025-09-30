from pathlib import Path

import sys
import types

sys.path.append(str(Path(__file__).resolve().parent.parent))


if "shiny" not in sys.modules:  # pragma: no cover - testing fallback
    shiny_stub = types.ModuleType("shiny")

    class _App:  # pragma: no cover - used only when shiny is absent
        def __init__(self, ui, server):
            self.ui = ui
            self.server = server

        def run(self):  # pragma: no cover - defensive stub
            raise RuntimeError("Shiny runtime is not available in tests")

    class _ReactiveNamespace(types.SimpleNamespace):
        @staticmethod
        def value(initial):
            return lambda: initial

        @staticmethod
        def calc(func):
            return func

    class _RenderNamespace(types.SimpleNamespace):
        @staticmethod
        def ui(func):
            return func

    class _UI(types.SimpleNamespace):
        def __getattr__(self, name):  # pragma: no cover - simple builder stub
            def _builder(*args, **kwargs):
                return {"component": name, "args": args, "kwargs": kwargs}

            return _builder

    shiny_stub.App = _App
    shiny_stub.Inputs = object
    shiny_stub.Outputs = object
    shiny_stub.Session = object
    shiny_stub.reactive = _ReactiveNamespace()
    shiny_stub.render = _RenderNamespace()
    ui_stub = _UI()
    ui_stub.tags = _UI()
    shiny_stub.ui = ui_stub
    sys.modules["shiny"] = shiny_stub


import pytest

import shiny_app


def test_load_recipe_data_defaults_to_crafting_calc(monkeypatch):
    calls: list[Path] = []

    def fake_load(path: Path):
        calls.append(path)
        return {"loaded": True}

    monkeypatch.setattr(shiny_app.crafting_calc, "load_recipes", fake_load)
    result = shiny_app.load_recipe_data()
    assert result == {"loaded": True}
    assert calls == [shiny_app.crafting_calc.DATA_FILE]


def test_load_recipe_data_with_custom_path(monkeypatch):
    custom = Path("/tmp/custom.csv")

    def fake_load(path: Path):
        assert path == custom
        return {"path": path}

    monkeypatch.setattr(shiny_app.crafting_calc, "load_recipes", fake_load)
    result = shiny_app.load_recipe_data(custom)
    assert result == {"path": custom}


def test_resolve_search_state_empty_input(monkeypatch):
    def fake_find(query: str, recipes: dict):  # pragma: no cover - defensive
        raise AssertionError("find_matching_items should not be called")

    monkeypatch.setattr(shiny_app.crafting_calc, "find_matching_items", fake_find)
    state = shiny_app.resolve_search_state("   ", {})
    assert state["status"] == "empty"
    assert state["matches"] == []
    assert state["selected"] is None


def test_resolve_search_state_ambiguous(monkeypatch):
    calls: list[str] = []

    def fake_find(query: str, recipes: dict):
        calls.append(query)
        return ["Steel Ingot", "Steel Sword"]

    monkeypatch.setattr(shiny_app.crafting_calc, "find_matching_items", fake_find)
    state = shiny_app.resolve_search_state(" Steel ", {})
    assert calls == ["Steel"]
    assert state["status"] == "ambiguous"
    assert state["matches"] == ["Steel Ingot", "Steel Sword"]
    assert state["selected"] is None


def test_resolve_search_state_selected(monkeypatch):
    def fake_find(query: str, recipes: dict):
        return ["Steel Ingot"]

    monkeypatch.setattr(shiny_app.crafting_calc, "find_matching_items", fake_find)
    state = shiny_app.resolve_search_state("Steel", {})
    assert state["status"] == "selected"
    assert state["selected"] == "Steel Ingot"


def test_resolve_search_state_no_matches(monkeypatch):
    def fake_find(query: str, recipes: dict):
        return []

    monkeypatch.setattr(shiny_app.crafting_calc, "find_matching_items", fake_find)
    state = shiny_app.resolve_search_state("Unknown", {})
    assert state["status"] == "no_matches"
    assert state["matches"] == []


def test_compute_item_overview_uses_crafting_calc(monkeypatch):
    requirements = {
        "craft_cost": 200,
        "purchase": {"Thread": {"quantity": 2, "unit_cost": 25}},
        "raw": {"Iron Ore": 3},
        "craft": {"Steel Ingot": 1},
    }
    resolve_calls = {}

    def fake_resolve(item: str, qty: int, recipes: dict):
        resolve_calls["item"] = item
        resolve_calls["qty"] = qty
        resolve_calls["recipes"] = recipes
        return requirements

    monkeypatch.setattr(shiny_app.crafting_calc, "resolve_requirements", fake_resolve)
    monkeypatch.setattr(
        shiny_app.crafting_calc,
        "get_profession_info",
        lambda recipes, item: ("Blacksmith", "3"),
    )
    monkeypatch.setattr(
        shiny_app.crafting_calc,
        "get_source_location",
        lambda recipes, item, default="Unknown": "Forge",
    )
    monkeypatch.setattr(
        shiny_app.crafting_calc,
        "compute_purchase_total",
        lambda entries: 150,
    )
    monkeypatch.setattr(
        shiny_app.crafting_calc,
        "compute_total_coin_cost",
        lambda purchase, craft: purchase + craft,
    )
    monkeypatch.setattr(
        shiny_app.crafting_calc,
        "format_coin_amount",
        lambda value: f"{value} coins",
    )
    monkeypatch.setattr(
        shiny_app.crafting_calc,
        "build_gather_lines",
        lambda raw, recipes: ["- Gather ore"],
    )
    monkeypatch.setattr(
        shiny_app.crafting_calc,
        "build_purchase_lines",
        lambda purchases, recipes: ["- Buy thread"],
    )
    monkeypatch.setattr(
        shiny_app.crafting_calc,
        "build_craft_lines",
        lambda item, craft, recipes: ["1. Craft ingot"],
    )

    overview = shiny_app.compute_item_overview("Steel Ingot", {"Steel Ingot": {}})

    assert resolve_calls == {
        "item": "Steel Ingot",
        "qty": 1,
        "recipes": {"Steel Ingot": {}},
    }
    assert overview["location"] == "Forge"
    assert overview["profession"] == "Blacksmith"
    assert overview["skill_tier"] == "3"
    assert overview["craft_cost"] == 200
    assert overview["craft_cost_text"] == "200 coins"
    assert overview["total_cost"] == 350
    assert overview["total_cost_text"] == "350 coins"
    assert overview["gather_lines"] == ["Gather ore"]
    assert overview["purchase_lines"] == ["Buy thread"]
    assert overview["craft_lines"] == ["1. Craft ingot"]


