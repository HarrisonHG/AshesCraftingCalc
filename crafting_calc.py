#!/usr/bin/env python3
"""Command line tool for calculating crafting requirements and costs."""

import argparse
import csv
import sys
from pathlib import Path
from typing import Any

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


def print_report(item: str, recipes: dict[str, Recipe]):
    requirements = resolve_requirements(item, 1, recipes)

    purchase_entries = requirements.get("purchase", {})
    raw_entries = requirements.get("raw", {})
    craft_cost = requirements.get("craft_cost", 0)
    craft_counts = requirements.get("craft", {})

    purchase_total = sum(
        info["quantity"] * info["unit_cost"] for info in purchase_entries.values()
    )
    total_coin_cost = purchase_total + craft_cost

    gathered_ingredients = [
        format_quantity_name(quantity, name)
        for name, quantity in sorted(raw_entries.items())
    ]
    gather_list = (
        join_with_commas(gathered_ingredients) if gathered_ingredients else "None"
    )

    required_skills: dict[str, int] = {}

    def add_skill(name: str) -> None:
        recipe = recipes.get(name)
        if not recipe:
            return
        profession = recipe.get("profession")
        tier = recipe.get("skill_tier")
        if not profession or not isinstance(tier, int) or tier <= 0:
            return
        required_skills[profession] = max(required_skills.get(profession, 0), tier)

    add_skill(item)
    for craft_name in craft_counts:
        add_skill(craft_name)
    for raw_name in raw_entries:
        add_skill(raw_name)
    for purchase_name in purchase_entries:
        add_skill(purchase_name)

    if required_skills:
        skills_summary = ", ".join(
            f"{profession} {tier}" for profession, tier in sorted(required_skills.items())
        )
    else:
        skills_summary = "None"

    source_location = get_source_location(recipes, item, "Unknown source")

    summary_rows = [
        ("Item", item),
        ("Source", source_location),
        ("Crafting Fees", format_coin_amount(craft_cost)),
        ("Gathered Ingredients", gather_list),
        ("Skills", skills_summary),
        ("Total Coin Cost", format_coin_amount(total_coin_cost)),
    ]
    print(build_table(("Summary", "Value"), summary_rows))

    raw_rows: list[tuple[str, ...]] = []
    for name, quantity in sorted(raw_entries.items()):
        location = get_source_location(recipes, name)
        profession, tier = get_profession_info(recipes, name)
        raw_rows.append((name, str(quantity), location, profession, tier))
    if not raw_rows:
        raw_rows = [("None", "-", "No raw materials required.", "-", "-")]
    print()
    print(
        build_table(
            ("Raw Material", "Quantity", "Location", "Profession", "Skill Tier"),
            raw_rows,
        )
    )

    purchase_rows: list[tuple[str, ...]] = []
    for name, info in sorted(purchase_entries.items()):
        quantity = info["quantity"]
        unit_cost = info["unit_cost"]
        total_cost = quantity * unit_cost
        location = get_source_location(recipes, name, "Unknown source")
        profession, tier = get_profession_info(recipes, name)
        purchase_rows.append(
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
    if not purchase_rows:
        purchase_rows = [
            ("None", "-", "No purchase locations.", "-", "-", "-", "No purchases required."),
        ]
    print()
    print(
        build_table(
            (
                "Purchase Item",
                "Quantity",
                "Location",
                "Profession",
                "Skill Tier",
                "Unit Cost",
                "Total Cost",
            ),
            purchase_rows,
        )
    )

    craft_order = build_crafting_order(item, craft_counts, recipes)
    craft_lines: list[str] = []
    for craft_item in craft_order:
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
        location = get_source_location(recipes, craft_item, "Unknown crafting station")
        description = (
            f"Craft {format_quantity_name(quantity, craft_item)} at {location} using "
            f"{join_with_commas(materials_used)}"
        )
        craft_lines.append(description)

    gather_lines = []
    for name, qty in sorted(raw_entries.items()):
        location = get_source_location(recipes, name)
        gather_lines.append(
            f"- {format_quantity_name(qty, name)} ({location})"
        )
    if not gather_lines:
        gather_lines = ["- No gathering required"]

    purchase_lines = []
    for name, info in sorted(purchase_entries.items()):
        quantity = info["quantity"]
        unit_cost = format_coin_amount(info["unit_cost"])
        total_cost = format_coin_amount(info["quantity"] * info["unit_cost"])
        location = get_source_location(recipes, name, "Unknown source")
        purchase_lines.append(
            f"- {format_quantity_name(quantity, name)} ({location}) @ {unit_cost} each -> {total_cost}"
        )
    if not purchase_lines:
        purchase_lines = ["- No purchases required"]

    if craft_lines:
        craft_lines = [f"{index + 1}. {line}" for index, line in enumerate(craft_lines)]
    else:
        craft_lines = ["- No crafting steps required"]

    print()
    print(build_box("1) Gather Raw Materials", gather_lines))
    print()
    print(build_box("2) Purchase Supplies", purchase_lines))
    print()
    print(build_box("3) Crafting Order", craft_lines))


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Calculate required materials and costs for crafting items."
    )
    parser.add_argument("item", nargs="?", help="Name of the item to craft")
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all available items and exit",
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=DATA_FILE,
        help="Path to the recipes CSV file (defaults to repository data file)",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv or sys.argv[1:])
    recipes = load_recipes(args.data)

    if args.list:
        print("Available items:")
        for item_name in sorted(recipes):
            print(f"  - {item_name}")
        return 0

    if not args.item:
        print("Error: you must provide an item name. Use --list to see available items.")
        return 1

    item_key = args.item.strip()
    if item_key not in recipes:
        print(
            f"No recipe found for '{item_key}'. Use --list to see available items, "
            "or gather it directly."
        )
        return 1

    print_report(item_key, recipes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
