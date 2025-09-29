#!/usr/bin/env python3
"""Command line tool for calculating crafting requirements and costs."""

import argparse
import csv
import sys
from pathlib import Path
from typing import Any, Iterable

DATA_FILE = Path(__file__).parent / "data" / "recipes.csv"


class Recipe(dict):
    """Typed recipe mapping for static type-checkers."""


def load_recipes(csv_path: Path) -> dict[str, Recipe]:
    """Load recipe information from ``csv_path``."""

    recipes: dict[str, Recipe] = {}
    try:
        with csv_path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            required_fields = {
                "item",
                "materials",
                "method",
                "source",
                "profession",
                "skill_tier",
                "cost",
            }
            missing_fields = required_fields - set(reader.fieldnames or [])
            if missing_fields:
                raise ValueError(
                    f"CSV is missing required columns: {', '.join(sorted(missing_fields))}"
                )

            for raw_row in reader:
                if all((value is None or not str(value).strip()) for value in raw_row.values()):
                    continue
                item = raw_row.get("item", "").strip()
                if not item:
                    raise ValueError("Encountered a row with an empty item name")

                method = raw_row.get("method", "").strip().lower()
                if method not in {"craft", "purchase", "raw"}:
                    raise ValueError(
                        f"Unknown method '{raw_row.get('method')}' for item {item!r}"
                    )

                source_location = raw_row.get("source", "").strip()
                if not source_location:
                    raise ValueError(
                        f"Source location missing for item {item!r}."
                    )

                profession = raw_row.get("profession", "").strip()
                if not profession:
                    raise ValueError(
                        f"Profession missing for item {item!r}."
                    )

                try:
                    skill_tier = int(raw_row.get("skill_tier", "0"))
                except ValueError as exc:
                    raise ValueError(
                        f"Invalid skill tier '{raw_row.get('skill_tier')}' for item {item!r}"
                    ) from exc
                if not 1 <= skill_tier <= 5:
                    raise ValueError(
                        f"Skill tier for item {item!r} must be between 1 and 5"
                    )

                try:
                    cost = int(raw_row.get("cost", "0"))
                except ValueError as exc:
                    raise ValueError(
                        f"Invalid cost '{raw_row.get('cost')}' for item {item!r}"
                    ) from exc

                materials_field = (raw_row.get("materials") or "").strip()
                materials: list[dict[str, Any]] = []
                if materials_field:
                    tokens = [chunk.strip() for chunk in materials_field.split("-") if chunk.strip()]
                    if len(tokens) % 2 != 0:
                        raise ValueError(
                            f"Materials field for {item!r} must contain pairs of quantity and item"
                        )
                    for qty_token, name in zip(tokens[0::2], tokens[1::2]):
                        try:
                            quantity = int(qty_token)
                        except ValueError as exc:
                            raise ValueError(
                                f"Invalid quantity '{qty_token}' in materials for {item!r}"
                            ) from exc
                        if quantity <= 0:
                            raise ValueError(
                                f"Quantity must be positive for material {name!r} in {item!r}"
                            )
                        if not name:
                            raise ValueError(
                                f"Material name missing for quantity '{qty_token}' in {item!r}"
                            )
                        materials.append({"item": name, "quantity": quantity})

                if method == "craft" and not materials:
                    raise ValueError(
                        f"Crafted item {item!r} must list its component materials"
                    )

                recipes[item] = Recipe(
                    {
                        "item": item,
                        "method": method,
                        "source": source_location,
                        "cost": cost,
                        "materials": materials,
                        "profession": profession,
                        "skill_tier": skill_tier,
                    }
                )
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"Recipe data not found at {csv_path}. Did you download the dataset?"
        ) from exc

    return recipes


def merge_quantity(target: dict[str, int], name: str, quantity: int) -> None:
    target[name] = target.get(name, 0) + quantity


def merge_purchase(
    target: dict[str, dict[str, int]], name: str, quantity: int, unit_cost: int
) -> None:
    entry = target.setdefault(name, {"quantity": 0, "unit_cost": unit_cost})
    if entry["unit_cost"] != unit_cost:
        raise ValueError(
            f"Conflicting unit costs for purchased item {name!r}: {entry['unit_cost']} vs {unit_cost}"
        )
    entry["quantity"] += quantity


def resolve_requirements(
    item: str,
    quantity: int,
    recipes: dict[str, Recipe],
    stack: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Recursively resolve material requirements for ``item``."""

    if quantity <= 0:
        raise ValueError("Quantity must be positive when resolving requirements")

    if item in stack:
        cycle = " -> ".join(stack + (item,))
        raise ValueError(f"Detected a crafting cycle: {cycle}")

    recipe = recipes.get(item)
    if recipe is None:
        gather: dict[str, int] = {item: quantity}
        return {
            "purchase": {},
            "raw": gather,
            "craft_cost": 0,
            "craft": {},
        }

    method = recipe["method"]
    cost = recipe["cost"]

    if method == "purchase":
        return {
            "purchase": {item: {"quantity": quantity, "unit_cost": cost}},
            "raw": {},
            "craft_cost": 0,
            "craft": {},
        }

    if method == "raw":
        return {
            "purchase": {},
            "raw": {item: quantity},
            "craft_cost": 0,
            "craft": {},
        }

    if method != "craft":
        raise ValueError(f"Unsupported method '{method}' for item {item!r}")

    subtotal = {
        "purchase": {},
        "raw": {},
        "craft_cost": cost * quantity,
        "craft": {item: quantity},
    }

    for material in recipe["materials"]:
        material_name = material["item"]
        material_quantity = material["quantity"] * quantity
        child = resolve_requirements(
            material_name, material_quantity, recipes, stack + (item,)
        )

        for purchase_name, info in child.get("purchase", {}).items():
            merge_purchase(
                subtotal["purchase"], purchase_name, info["quantity"], info["unit_cost"]
            )
        for raw_name, raw_qty in child.get("raw", {}).items():
            merge_quantity(subtotal["raw"], raw_name, raw_qty)
        subtotal["craft_cost"] += child.get("craft_cost", 0)
        for craft_name, craft_qty in child.get("craft", {}).items():
            merge_quantity(subtotal["craft"], craft_name, craft_qty)

    return subtotal


def format_coin_amount(value: int) -> str:
    gold = value // 10000
    remainder = value % 10000
    silver = remainder // 100
    copper = remainder % 100

    parts: list[str] = []
    if gold:
        parts.append(f"{gold} gold")
    if silver:
        parts.append(f"{silver} silver")
    if copper or not parts:
        parts.append(f"{copper} copper")
    return ", ".join(parts)


def build_table(headers: tuple[str, ...], rows: list[tuple[str, ...]]) -> str:
    widths = [len(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    def make_border(char: str = "-") -> str:
        segments = [char * (width + 2) for width in widths]
        return "+" + "+".join(segments) + "+"

    header_border = make_border("-")
    separator = make_border("=")
    lines = [header_border]
    header_cells = [f" {headers[i].ljust(widths[i])} " for i in range(len(headers))]
    lines.append("|" + "|".join(header_cells) + "|")
    lines.append(separator)
    for row in rows:
        row_cells = [f" {row[i].ljust(widths[i])} " for i in range(len(headers))]
        lines.append("|" + "|".join(row_cells) + "|")
    lines.append(header_border)
    return "\n".join(lines)


def build_box(title: str, lines: list[str]) -> str:
    content = [title] + lines
    width = max(len(line) for line in content) if content else len(title)
    top = "+" + "-" * (width + 2) + "+"
    separator = "+" + "=" * (width + 2) + "+"
    formatted = [top, f"| {title.ljust(width)} |", separator]
    for line in lines:
        formatted.append(f"| {line.ljust(width)} |")
    formatted.append(top)
    return "\n".join(formatted)


def build_crafting_order(
    target: str, craft_counts: dict[str, int], recipes: dict[str, Recipe]
) -> list[str]:
    order: list[str] = []
    visited: set[str] = set()
    active: set[str] = set()

    def visit(name: str) -> None:
        if name in visited or name not in craft_counts:
            return
        if name in active:
            cycle = " -> ".join(list(active) + [name])
            raise ValueError(f"Detected crafting cycle when ordering steps: {cycle}")
        active.add(name)
        recipe = recipes.get(name)
        if recipe and recipe["method"] == "craft":
            for material in recipe["materials"]:
                child_name = material["item"]
                if child_name in craft_counts:
                    visit(child_name)
        active.remove(name)
        visited.add(name)
        order.append(name)

    if target in craft_counts:
        visit(target)
    else:
        for name in sorted(craft_counts):
            visit(name)

    return order


def join_with_commas(parts: list[str]) -> str:
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return ", ".join(parts[:-1]) + f", and {parts[-1]}"


def format_quantity_name(quantity: int, name: str) -> str:
    if quantity == 1:
        return f"{quantity} {name}"
    if name.lower().endswith("s"):
        return f"{quantity} {name}"
    return f"{quantity} {name}s"


def get_source_location(
    recipes: dict[str, Recipe], item: str, default: str = "Unknown location"
) -> str:
    recipe = recipes.get(item)
    if not recipe:
        return default
    location = recipe.get("source")
    if not location:
        return default
    return location


def get_profession_info(
    recipes: dict[str, Recipe], item: str, default_profession: str = "Unknown"
) -> tuple[str, str]:
    recipe = recipes.get(item)
    if not recipe:
        return default_profession, "-"
    profession = recipe.get("profession") or default_profession
    tier = recipe.get("skill_tier")
    if isinstance(tier, int) and tier > 0:
        tier_str = str(tier)
    else:
        tier_str = "-"
    return profession, tier_str



def compute_purchase_total(purchase_entries: dict[str, dict[str, int]]) -> int:
    """Return the total coin cost for all purchased items."""

    total = 0
    for info in purchase_entries.values():
        total += info["quantity"] * info["unit_cost"]
    return total


def compute_total_coin_cost(purchase_total: int, craft_cost: int) -> int:
    """Return the combined coin cost from purchases and crafting fees."""

    return purchase_total + craft_cost


def gather_items_for_skill_summary(
    item: str,
    craft_counts: dict[str, int],
    raw_entries: dict[str, int],
    purchase_entries: dict[str, dict[str, int]],
) -> set[str]:
    """Collect all items that may contribute to the skill summary."""

    related_items: set[str] = {item}
    related_items.update(craft_counts.keys())
    related_items.update(raw_entries.keys())
    related_items.update(purchase_entries.keys())
    return related_items


def collect_required_skills(items: set[str], recipes: dict[str, Recipe]) -> dict[str, int]:
    """Return the highest tier required per profession for ``items``."""

    requirements: dict[str, int] = {}
    for name in items:
        recipe = recipes.get(name)
        if not recipe:
            continue
        profession = recipe.get("profession")
        tier = recipe.get("skill_tier")
        if not profession or not isinstance(tier, int) or tier <= 0:
            continue
        requirements[profession] = max(requirements.get(profession, 0), tier)
    return requirements


def format_skill_summary(required_skills: dict[str, int]) -> str:
    """Format a human-readable skill summary."""

    if required_skills:
        return ", ".join(
            f"{profession} {tier}" for profession, tier in sorted(required_skills.items())
        )
    return "None"


def build_gathered_ingredients_summary(raw_entries: dict[str, int]) -> str:
    """Summarize gathered ingredients for the report."""

    gathered = [
        format_quantity_name(quantity, name)
        for name, quantity in sorted(raw_entries.items())
    ]
    if not gathered:
        return "None"
    return join_with_commas(gathered)


def build_gather_lines(raw_entries: dict[str, int], recipes: dict[str, Recipe]) -> list[str]:
    """Return lines describing required gathering steps."""

    lines = []
    for name, qty in sorted(raw_entries.items()):
        location = get_source_location(recipes, name)
        lines.append(f"- {format_quantity_name(qty, name)} ({location})")
    if not lines:
        lines.append("- No gathering required")
    return lines


def build_purchase_lines(
    purchase_entries: dict[str, dict[str, int]], recipes: dict[str, Recipe]
) -> list[str]:
    """Return lines describing required purchase steps."""

    lines = []
    for name, info in sorted(purchase_entries.items()):
        quantity = info["quantity"]
        unit_cost = format_coin_amount(info["unit_cost"])
        total_cost = format_coin_amount(quantity * info["unit_cost"])
        location = get_source_location(recipes, name, "Unknown source")
        lines.append(
            f"- {format_quantity_name(quantity, name)} ({location}) "
            f"@ {unit_cost} each -> {total_cost}"
        )
    if not lines:
        lines.append("- No purchases required")
    return lines


def build_craft_lines(
    item: str, craft_counts: dict[str, int], recipes: dict[str, Recipe]
) -> list[str]:
    """Return numbered lines describing crafting steps."""

    order = build_crafting_order(item, craft_counts, recipes)
    descriptions: list[str] = []
    for craft_item in order:
        recipe = recipes.get(craft_item)
        if not recipe or recipe["method"] != "craft":
            continue
        quantity = craft_counts[craft_item]
        materials_used: list[str] = []
        for material in recipe["materials"]:
            total_needed = material["quantity"] * quantity
            materials_used.append(
                format_quantity_name(total_needed, material["item"])
            )
        fee = recipe["cost"] * quantity
        if fee:
            materials_used.append(f"{format_coin_amount(fee)} fee")
        location = get_source_location(
            recipes, craft_item, "Unknown crafting station"
        )
        descriptions.append(
            "Craft "
            f"{format_quantity_name(quantity, craft_item)} at {location} using "
            f"{join_with_commas(materials_used)}"
        )
    if descriptions:
        return [f"{index + 1}. {line}" for index, line in enumerate(descriptions)]
    return ["- No crafting steps required"]


def format_summary_section(
    item: str, requirements: dict[str, Any], recipes: dict[str, Recipe]
) -> str:
    """Return the formatted summary table for ``item``."""

    purchase_entries = requirements.get("purchase", {})
    raw_entries = requirements.get("raw", {})
    craft_cost = requirements.get("craft_cost", 0)
    craft_counts = requirements.get("craft", {})

    purchase_total = compute_purchase_total(purchase_entries)
    total_coin_cost = compute_total_coin_cost(purchase_total, craft_cost)
    gather_list = build_gathered_ingredients_summary(raw_entries)
    related_items = gather_items_for_skill_summary(
        item, craft_counts, raw_entries, purchase_entries
    )
    required_skills = collect_required_skills(related_items, recipes)
    skills_summary = format_skill_summary(required_skills)
    source_location = get_source_location(recipes, item, "Unknown source")

    summary_rows = [
        ("Item", item),
        ("Source", source_location),
        ("Crafting Fees", format_coin_amount(craft_cost)),
        ("Gathered Ingredients", gather_list),
        ("Skills", skills_summary),
        ("Total Coin Cost", format_coin_amount(total_coin_cost)),
    ]
    return build_table(("Summary", "Value"), summary_rows)


def format_raw_material_section(
    requirements: dict[str, Any], recipes: dict[str, Recipe]
) -> str:
    """Return the formatted raw material table."""

    raw_entries = requirements.get("raw", {})
    rows: list[tuple[str, ...]] = []
    for name, quantity in sorted(raw_entries.items()):
        location = get_source_location(recipes, name)
        profession, tier = get_profession_info(recipes, name)
        rows.append((name, str(quantity), location, profession, tier))
    if not rows:
        rows = [("None", "-", "No raw materials required.", "-", "-")]
    return build_table(
        ("Raw Material", "Quantity", "Location", "Profession", "Skill Tier"),
        rows,
    )


def format_purchase_section(
    requirements: dict[str, Any], recipes: dict[str, Recipe]
) -> str:
    """Return the formatted purchase table."""

    purchase_entries = requirements.get("purchase", {})
    rows: list[tuple[str, ...]] = []
    for name, info in sorted(purchase_entries.items()):
        quantity = info["quantity"]
        unit_cost = info["unit_cost"]
        total_cost = quantity * unit_cost
        location = get_source_location(recipes, name, "Unknown source")
        profession, tier = get_profession_info(recipes, name)
        rows.append(
            (
                name,
                str(quantity),
                location,
                profession,
                tier,
                format_coin_amount(unit_cost),
                format_coin_amount(total_cost),
            )
        )
    if not rows:
        rows = [
            (
                "None",
                "-",
                "No purchase locations.",
                "-",
                "-",
                "-",
                "No purchases required.",
            ),
        ]
    return build_table(
        (
            "Purchase Item",
            "Quantity",
            "Location",
            "Profession",
            "Skill Tier",
            "Unit Cost",
            "Total Cost",
        ),
        rows,
    )


def format_gather_box(requirements: dict[str, Any], recipes: dict[str, Recipe]) -> str:
    """Return the gather instructions box."""

    lines = build_gather_lines(requirements.get("raw", {}), recipes)
    return build_box("1) Gather Raw Materials", lines)


def format_purchase_box(requirements: dict[str, Any], recipes: dict[str, Recipe]) -> str:
    """Return the purchase instructions box."""

    lines = build_purchase_lines(requirements.get("purchase", {}), recipes)
    return build_box("2) Purchase Supplies", lines)


def format_crafting_box(
    item: str, requirements: dict[str, Any], recipes: dict[str, Recipe]
) -> str:
    """Return the crafting order box."""

    lines = build_craft_lines(item, requirements.get("craft", {}), recipes)
    return build_box("3) Crafting Order", lines)


def format_report(item: str, recipes: dict[str, Recipe]) -> str:
    """Return the full formatted crafting report for ``item``."""

    requirements = resolve_requirements(item, 1, recipes)

    sections = [
        format_summary_section(item, requirements, recipes),
        format_raw_material_section(requirements, recipes),
        format_purchase_section(requirements, recipes),
        format_gather_box(requirements, recipes),
        format_purchase_box(requirements, recipes),
        format_crafting_box(item, requirements, recipes),
    ]
    return "\n\n".join(sections)


def print_report(item: str, recipes: dict[str, Recipe]):
    print(format_report(item, recipes))


def find_matching_items(query: str, recipes: dict[str, Recipe]) -> list[str]:
    """Return recipe names that contain ``query`` (case-insensitive)."""

    trimmed = query.strip().lower()
    if not trimmed:
        return []
    matches = [name for name in recipes if trimmed in name.lower()]
    return sorted(matches)


def format_match_list(matches: Iterable[str]) -> str:
    lines = [f"- {match}" for match in matches]
    return "\n".join(lines)


def choose_item(query: str, recipes: dict[str, Recipe]) -> str:
    """Return the recipe name that best matches ``query``.

    Raises ``ValueError`` if there are zero or multiple matches.
    """

    matches = find_matching_items(query, recipes)
    if not matches:
        raise ValueError(f"No items found matching {query!r}.")
    if len(matches) > 1:
        match_lines = format_match_list(matches)
        raise ValueError(
            "Multiple items match "
            f"{query!r}. Please clarify which item you want:\n{match_lines}"
        )
    return matches[0]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ashes of Creation crafting helper")
    parser.add_argument(
        "item",
        nargs="?",
        help="Name of the item to craft (supports partial matches)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all available items and exit",
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=DATA_FILE,
        help="Path to the recipes CSV file (defaults to bundled data)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        recipes = load_recipes(Path(args.data))
    except Exception as exc:  # pragma: no cover - argparse prints the error
        print(f"Failed to load recipe data: {exc}", file=sys.stderr)
        return 2

    if args.list:
        for name in sorted(recipes):
            print(name)
        return 0

    if not args.item:
        parser.print_help()
        return 1

    try:
        chosen_item = choose_item(args.item, recipes)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print_report(chosen_item, recipes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
