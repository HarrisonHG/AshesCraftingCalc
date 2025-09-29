"""Shiny UI for the Ashes crafting calculator."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from shiny import App, Inputs, Outputs, Session, reactive, render, ui

import crafting_calc


def load_recipe_data(data_path: Path | None = None) -> dict[str, crafting_calc.Recipe]:
    """Load crafting recipes using ``crafting_calc``.

    Parameters
    ----------
    data_path:
        Optional override path for the recipes CSV file. When omitted the value from
        :mod:`crafting_calc` is used.
    """

    target_path = Path(data_path) if data_path is not None else crafting_calc.DATA_FILE
    return crafting_calc.load_recipes(target_path)


def resolve_search_state(
    query: str, recipes: dict[str, crafting_calc.Recipe]
) -> dict[str, Any]:
    """Return metadata describing the state of an item search."""

    state: dict[str, Any] = {
        "query": query,
        "matches": [],
        "selected": None,
    }
    trimmed = query.strip()
    if not trimmed:
        state["status"] = "empty"
        return state

    matches = crafting_calc.find_matching_items(trimmed, recipes)
    state["matches"] = matches
    if not matches:
        state["status"] = "no_matches"
        return state
    if len(matches) == 1:
        state["status"] = "selected"
        state["selected"] = matches[0]
        return state

    state["status"] = "ambiguous"
    return state


def _normalize_step_lines(lines: list[str]) -> list[str]:
    normalized: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("- "):
            normalized.append(stripped[2:].strip())
        else:
            normalized.append(stripped)
    return normalized


def compute_item_overview(
    item: str, recipes: dict[str, crafting_calc.Recipe]
) -> dict[str, Any]:
    """Return data required to display crafting information for ``item``."""

    requirements = crafting_calc.resolve_requirements(item, 1, recipes)
    craft_cost = int(requirements.get("craft_cost", 0) or 0)
    purchase_entries = requirements.get("purchase", {})
    raw_entries = requirements.get("raw", {})
    craft_counts = requirements.get("craft", {})

    profession, tier = crafting_calc.get_profession_info(recipes, item)
    location = crafting_calc.get_source_location(recipes, item, "Unknown source")

    purchase_total = crafting_calc.compute_purchase_total(purchase_entries)
    total_cost = crafting_calc.compute_total_coin_cost(purchase_total, craft_cost)

    gather_lines = _normalize_step_lines(
        crafting_calc.build_gather_lines(raw_entries, recipes)
    )
    purchase_lines = _normalize_step_lines(
        crafting_calc.build_purchase_lines(purchase_entries, recipes)
    )
    craft_lines = _normalize_step_lines(
        crafting_calc.build_craft_lines(item, craft_counts, recipes)
    )

    return {
        "item": item,
        "location": location,
        "profession": profession,
        "skill_tier": tier,
        "craft_cost": craft_cost,
        "craft_cost_text": crafting_calc.format_coin_amount(craft_cost),
        "total_cost": total_cost,
        "total_cost_text": crafting_calc.format_coin_amount(total_cost),
        "gather_lines": gather_lines,
        "purchase_lines": purchase_lines,
        "craft_lines": craft_lines,
    }


app_ui = ui.page_fluid(
    ui.h2("Ashes of Creation Crafting Helper"),
    ui.input_text("query", "Search for an item", placeholder="Enter an item name"),
    ui.output_ui("match_feedback"),
    ui.br(),
    ui.output_ui("info_cards"),
    ui.br(),
    ui.output_ui("recipe_lists"),
)


def server(input: Inputs, output: Outputs, session: Session) -> None:
    load_error: str | None = None
    try:
        initial_recipes = load_recipe_data()
    except Exception as exc:  # pragma: no cover - defensive start-up guard
        initial_recipes = {}
        load_error = str(exc)

    recipes_store = reactive.value(initial_recipes)
    error_store = reactive.value(load_error)

    @reactive.calc
    def search_state() -> dict[str, Any]:
        error = error_store()
        if error:
            return {"status": "error", "error": error}
        return resolve_search_state(input.query(), recipes_store())

    @reactive.calc
    def overview() -> dict[str, Any] | None:
        state = search_state()
        if state.get("status") != "selected":
            return None
        selected_item = state["selected"]
        try:
            data = compute_item_overview(selected_item, recipes_store())
            data["error"] = None
            return data
        except Exception as exc:  # pragma: no cover - defensive UI guard
            return {"item": selected_item, "error": str(exc)}

    @output
    @render.ui
    def match_feedback() -> Any:
        state = search_state()
        status = state.get("status")
        if status == "error":
            return ui.div(
                ui.strong("Failed to load recipes."),
                ui.p(state.get("error", "Unknown error")),
            )
        if status == "empty":
            return ui.div("Type an item name to begin.")
        if status == "no_matches":
            return ui.div(ui.strong("No matching items found."))
        if status == "ambiguous":
            items = [ui.tags.li(name) for name in state.get("matches", [])]
            return ui.div(
                ui.strong("Multiple matches found:"),
                ui.tags.ul(*items),
                ui.p("Refine your search to choose a single item."),
            )
        if status == "selected":
            selected_item = state.get("selected")
            return ui.div(ui.strong(f"Showing details for {selected_item}"))
        return ui.div()

    @output
    @render.ui
    def info_cards() -> Any:
        data = overview()
        if not data:
            return ui.div()
        if data.get("error"):
            return ui.div(
                ui.strong("Unable to display crafting information:"),
                ui.p(data["error"]),
            )
        profession = data.get("profession", "Unknown")
        tier = data.get("skill_tier", "-")
        if tier and tier != "-":
            profession_text = f"{profession} (Tier {tier})"
        else:
            profession_text = profession

        cards = [
            ui.card(
                ui.card_header("Source"),
                ui.p(data.get("location", "Unknown")),
            ),
            ui.card(
                ui.card_header("Profession"),
                ui.p(profession_text),
            ),
            ui.card(
                ui.card_header("Crafting Fees"),
                ui.p(data.get("craft_cost_text", "0 copper")),
            ),
            ui.card(
                ui.card_header("Total Coin Cost"),
                ui.p(data.get("total_cost_text", "0 copper")),
            ),
        ]
        return ui.layout_column_wrap(1 / 4, *cards)

    def _lines_to_list(items: list[str]) -> Any:
        if not items:
            return ui.tags.ul(ui.tags.li("None"))
        return ui.tags.ul(*[ui.tags.li(text) for text in items])

    @output
    @render.ui
    def recipe_lists() -> Any:
        data = overview()
        if not data or data.get("error"):
            return ui.div()
        gather_card = ui.card(
            ui.card_header("Gather"),
            _lines_to_list(data.get("gather_lines", [])),
        )
        purchase_card = ui.card(
            ui.card_header("Purchase"),
            _lines_to_list(data.get("purchase_lines", [])),
        )
        craft_card = ui.card(
            ui.card_header("Craft"),
            _lines_to_list(data.get("craft_lines", [])),
        )
        return ui.layout_column_wrap(1 / 3, gather_card, purchase_card, craft_card)


app = App(app_ui, server)


if __name__ == "__main__":  # pragma: no cover - manual launch helper
    app.run()
