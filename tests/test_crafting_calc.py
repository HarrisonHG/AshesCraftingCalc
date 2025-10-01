import csv
import sys
import textwrap
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import pytest

import crafting_calc
from crafting_calc import (
    Recipe,
    build_box,
    build_craft_lines,
    build_gather_lines,
    build_gathered_ingredients_summary,
    build_purchase_lines,
    choose_item,
    collect_required_skills,
    compute_purchase_total,
    compute_total_coin_cost,
    find_matching_items,
    format_coin_amount,
    format_crafting_box,
    format_gather_box,
    format_purchase_box,
    format_purchase_section,
    format_report,
    format_raw_material_section,
    format_skill_summary,
    format_summary_section,
    gather_items_for_skill_summary,
    get_profession_info,
    get_source_location,
    join_with_commas,
    main,
    merge_purchase,
    merge_quantity,
    resolve_requirements,
)


@pytest.fixture
def sample_recipes() -> dict[str, Recipe]:
    return {
        "Iron Ore": Recipe(
            {
                "item": "Iron Ore",
                "method": "raw",
                "source": "Iron Vein",
                "cost": 0,
                "materials": [],
                "profession": "Miner",
                "skill_tier": 1,
            }
        ),
        "Coal": Recipe(
            {
                "item": "Coal",
                "method": "raw",
                "source": "Coal Seam",
                "cost": 0,
                "materials": [],
                "profession": "Miner",
                "skill_tier": 1,
            }
        ),
        "Leather": Recipe(
            {
                "item": "Leather",
                "method": "raw",
                "source": "Hunting Grounds",
                "cost": 0,
                "materials": [],
                "profession": "Rancher",
                "skill_tier": 2,
            }
        ),
        "Iron Ingot": Recipe(
            {
                "item": "Iron Ingot",
                "method": "craft",
                "source": "Smelter",
                "cost": 50,
                "materials": [
                    {"item": "Iron Ore", "quantity": 3},
                ],
                "profession": "Smelter",
                "skill_tier": 2,
            }
        ),
        "Steel Ingot": Recipe(
            {
                "item": "Steel Ingot",
                "method": "craft",
                "source": "Forge",
                "cost": 100,
                "materials": [
                    {"item": "Iron Ingot", "quantity": 2},
                    {"item": "Coal", "quantity": 1},
                ],
                "profession": "Armorsmith",
                "skill_tier": 4,
            }
        ),
        "Thread": Recipe(
            {
                "item": "Thread",
                "method": "purchase",
                "source": "Market Stall",
                "cost": 25,
                "materials": [],
                "profession": "Tailor",
                "skill_tier": 1,
            }
        ),
        "Reinforced Boots": Recipe(
            {
                "item": "Reinforced Boots",
                "method": "craft",
                "source": "Cobbler Bench",
                "cost": 150,
                "materials": [
                    {"item": "Steel Ingot", "quantity": 1},
                    {"item": "Thread", "quantity": 3},
                    {"item": "Leather", "quantity": 1},
                ],
                "profession": "Leatherworker",
                "skill_tier": 3,
            }
        ),
    }


@pytest.fixture
def steel_requirements(sample_recipes: dict[str, Recipe]) -> dict[str, dict]:
    return resolve_requirements("Steel Ingot", 1, sample_recipes)


@pytest.fixture
def boots_requirements(sample_recipes: dict[str, Recipe]) -> dict[str, dict]:
    return resolve_requirements("Reinforced Boots", 1, sample_recipes)


def write_recipe_csv(path: Path, recipes: dict[str, Recipe]) -> None:
    fieldnames = (
        "item",
        "materials",
        "method",
        "source",
        "profession",
        "skill_tier",
        "cost",
    )
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for recipe in recipes.values():
            materials_tokens: list[str] = []
            for material in recipe["materials"]:
                materials_tokens.extend([str(material["quantity"]), material["item"]])
            writer.writerow(
                {
                    "item": recipe["item"],
                    "materials": "-".join(materials_tokens),
                    "method": recipe["method"],
                    "source": recipe["source"],
                    "profession": recipe["profession"],
                    "skill_tier": recipe["skill_tier"],
                    "cost": recipe["cost"],
                }
            )


def test_merge_purchase_conflicting_cost_raises():
    purchases: dict[str, dict[str, int]] = {}
    merge_purchase(purchases, "Thread", 2, 25)
    with pytest.raises(ValueError):
        merge_purchase(purchases, "Thread", 1, 30)


def test_resolve_requirements_cycle_detection(sample_recipes: dict[str, Recipe]):
    sample_recipes["Thread"]["method"] = "craft"
    sample_recipes["Thread"]["materials"] = [{"item": "Reinforced Boots", "quantity": 1}]
    with pytest.raises(ValueError):
        resolve_requirements("Reinforced Boots", 1, sample_recipes)


def test_resolve_requirements_invalid_quantity(sample_recipes: dict[str, Recipe]):
    with pytest.raises(ValueError):
        resolve_requirements("Steel Ingot", 0, sample_recipes)


def test_build_crafting_order_cycle_detection():
    recipes = {
        "A": Recipe(
            {
                "item": "A",
                "method": "craft",
                "source": "X",
                "cost": 0,
                "materials": [{"item": "B", "quantity": 1}],
                "profession": "Alchemist",
                "skill_tier": 1,
            }
        ),
        "B": Recipe(
            {
                "item": "B",
                "method": "craft",
                "source": "Y",
                "cost": 0,
                "materials": [{"item": "A", "quantity": 1}],
                "profession": "Alchemist",
                "skill_tier": 1,
            }
        ),
    }
    craft_counts = {"A": 1, "B": 1}
    with pytest.raises(ValueError):
        crafting_calc.build_crafting_order("A", craft_counts, recipes)


def test_compute_purchase_total_boundary_cases():
    assert compute_purchase_total({}) == 0
    purchases = {
        "Thread": {"quantity": 3, "unit_cost": 25},
        "Oil": {"quantity": 2, "unit_cost": 40},
    }
    assert compute_purchase_total(purchases) == (3 * 25) + (2 * 40)


def test_compute_total_coin_cost_adds_components():
    assert compute_total_coin_cost(0, 0) == 0
    assert compute_total_coin_cost(75, 350) == 425


def test_find_matching_items_supports_partial_search(sample_recipes: dict[str, Recipe]):
    matches = find_matching_items("steel", sample_recipes)
    assert matches == ["Steel Ingot"]


def test_choose_item_multiple_matches_lists_options(sample_recipes: dict[str, Recipe]):
    sample_recipes["Steel Sword"] = Recipe(
        {
            "item": "Steel Sword",
            "method": "craft",
            "source": "Forge",
            "cost": 120,
            "materials": [
                {"item": "Steel Ingot", "quantity": 2},
                {"item": "Leather", "quantity": 1},
            ],
            "profession": "Weaponsmith",
            "skill_tier": 4,
        }
    )
    with pytest.raises(ValueError) as excinfo:
        choose_item("steel", sample_recipes)
    message = str(excinfo.value)
    assert "Multiple items match 'steel'" in message
    assert "Steel Ingot" in message
    assert "Steel Sword" in message


def test_main_partial_match_selects_single_item(tmp_path: Path, capsys):
    recipes = {
        "Steel Sword": Recipe(
            {
                "item": "Steel Sword",
                "method": "craft",
                "source": "Forge",
                "cost": 200,
                "materials": [
                    {"item": "Steel Ingot", "quantity": 2},
                    {"item": "Thread", "quantity": 1},
                ],
                "profession": "Weaponsmith",
                "skill_tier": 4,
            }
        ),
        "Steel Ingot": Recipe(
            {
                "item": "Steel Ingot",
                "method": "craft",
                "source": "Forge",
                "cost": 100,
                "materials": [
                    {"item": "Iron Ingot", "quantity": 2},
                    {"item": "Coal", "quantity": 1},
                ],
                "profession": "Armorsmith",
                "skill_tier": 4,
            }
        ),
        "Iron Ingot": Recipe(
            {
                "item": "Iron Ingot",
                "method": "craft",
                "source": "Smelter",
                "cost": 50,
                "materials": [
                    {"item": "Iron Ore", "quantity": 3},
                ],
                "profession": "Smelter",
                "skill_tier": 2,
            }
        ),
        "Iron Ore": Recipe(
            {
                "item": "Iron Ore",
                "method": "raw",
                "source": "Iron Vein",
                "cost": 0,
                "materials": [],
                "profession": "Miner",
                "skill_tier": 1,
            }
        ),
        "Coal": Recipe(
            {
                "item": "Coal",
                "method": "raw",
                "source": "Coal Seam",
                "cost": 0,
                "materials": [],
                "profession": "Miner",
                "skill_tier": 1,
            }
        ),
        "Thread": Recipe(
            {
                "item": "Thread",
                "method": "purchase",
                "source": "Market Stall",
                "cost": 25,
                "materials": [],
                "profession": "Tailor",
                "skill_tier": 1,
            }
        ),
    }
    csv_path = tmp_path / "recipes.csv"
    write_recipe_csv(csv_path, recipes)
    exit_code = main(["--data", str(csv_path), "swo"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Steel Sword" in captured.out


def test_main_multiple_matches_requests_clarification(tmp_path: Path, capsys):
    recipes = {
        "Steel Sword": Recipe(
            {
                "item": "Steel Sword",
                "method": "craft",
                "source": "Forge",
                "cost": 200,
                "materials": [
                    {"item": "Steel Ingot", "quantity": 2},
                    {"item": "Thread", "quantity": 1},
                ],
                "profession": "Weaponsmith",
                "skill_tier": 4,
            }
        ),
        "Steel Shield": Recipe(
            {
                "item": "Steel Shield",
                "method": "craft",
                "source": "Forge",
                "cost": 220,
                "materials": [
                    {"item": "Steel Ingot", "quantity": 3},
                    {"item": "Leather", "quantity": 1},
                ],
                "profession": "Armorsmith",
                "skill_tier": 4,
            }
        ),
        "Steel Ingot": Recipe(
            {
                "item": "Steel Ingot",
                "method": "craft",
                "source": "Forge",
                "cost": 100,
                "materials": [
                    {"item": "Iron Ingot", "quantity": 2},
                    {"item": "Coal", "quantity": 1},
                ],
                "profession": "Armorsmith",
                "skill_tier": 4,
            }
        ),
        "Iron Ingot": Recipe(
            {
                "item": "Iron Ingot",
                "method": "craft",
                "source": "Smelter",
                "cost": 50,
                "materials": [
                    {"item": "Iron Ore", "quantity": 3},
                ],
                "profession": "Smelter",
                "skill_tier": 2,
            }
        ),
        "Iron Ore": Recipe(
            {
                "item": "Iron Ore",
                "method": "raw",
                "source": "Iron Vein",
                "cost": 0,
                "materials": [],
                "profession": "Miner",
                "skill_tier": 1,
            }
        ),
        "Coal": Recipe(
            {
                "item": "Coal",
                "method": "raw",
                "source": "Coal Seam",
                "cost": 0,
                "materials": [],
                "profession": "Miner",
                "skill_tier": 1,
            }
        ),
        "Thread": Recipe(
            {
                "item": "Thread",
                "method": "purchase",
                "source": "Market Stall",
                "cost": 25,
                "materials": [],
                "profession": "Tailor",
                "skill_tier": 1,
            }
        ),
        "Leather": Recipe(
            {
                "item": "Leather",
                "method": "raw",
                "source": "Hunting Grounds",
                "cost": 0,
                "materials": [],
                "profession": "Rancher",
                "skill_tier": 2,
            }
        ),
    }
    csv_path = tmp_path / "recipes.csv"
    write_recipe_csv(csv_path, recipes)
    exit_code = main(["--data", str(csv_path), "steel"])
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Multiple items match 'steel'" in captured.err
    assert "- Steel Sword" in captured.err
    assert "- Steel Shield" in captured.err


def test_gather_items_for_skill_summary_collects_unique_items(boots_requirements):
    items = gather_items_for_skill_summary(
        "Reinforced Boots",
        boots_requirements.get("craft", {}),
        boots_requirements.get("raw", {}),
        boots_requirements.get("purchase", {}),
    )
    assert "Reinforced Boots" in items
    assert "Steel Ingot" in items
    assert "Thread" in items
    assert "Leather" in items


def test_collect_required_skills_filters_invalid(sample_recipes):
    items = {"Iron Ore", "Unknown Item"}
    skills = collect_required_skills(items, sample_recipes)
    assert skills == {"Miner": 1}


def test_format_skill_summary_variations():
    assert format_skill_summary({}) == "None"
    summary = format_skill_summary({"Tailor": 1, "Armorsmith": 4})
    assert summary == "Armorsmith 4, Tailor 1"


def test_build_gathered_ingredients_summary(sample_recipes, boots_requirements):
    summary = build_gathered_ingredients_summary(boots_requirements["raw"])
    assert summary == "1 Coal, 6 Iron Ores, and 1 Leather"
    assert build_gathered_ingredients_summary({}) == "None"


def test_build_gather_lines_outputs_locations(sample_recipes, boots_requirements):
    lines = build_gather_lines(boots_requirements["raw"], sample_recipes)
    assert lines == [
        "- 1 Coal (Coal Seam)",
        "- 6 Iron Ores (Iron Vein)",
        "- 1 Leather (Hunting Grounds)",
    ]
    assert build_gather_lines({}, sample_recipes) == ["- No gathering required"]


def test_build_purchase_lines_formats_entries(sample_recipes, boots_requirements):
    lines = build_purchase_lines(boots_requirements["purchase"], sample_recipes)
    assert lines == ["- 3 Threads (Market Stall) @ 25 copper each -> 75 copper"]
    assert build_purchase_lines({}, sample_recipes) == ["- No purchases required"]


def test_build_craft_lines_orders_dependencies(sample_recipes, boots_requirements):
    lines = build_craft_lines(
        "Reinforced Boots", boots_requirements["craft"], sample_recipes
    )
    assert lines == [
        "1. Craft 2 Iron Ingots at Smelter using 6 Iron Ores and 1 silver fee",
        "2. Craft 1 Steel Ingot at Forge using 2 Iron Ingots, 1 Coal, and 1 silver fee",
        (
            "3. Craft 1 Reinforced Boots at Cobbler Bench using 1 Steel Ingot, "
            "3 Threads, 1 Leather, and 1 silver, 50 copper fee"
        ),
    ]


def test_format_summary_section_outputs_expected(sample_recipes, boots_requirements):
    summary = format_summary_section(
        "Reinforced Boots", boots_requirements, sample_recipes
    )
    expected_rows = [
        ("Item", "Reinforced Boots"),
        ("Source", "Cobbler Bench"),
        ("Crafting Fees", format_coin_amount(350)),
        ("Gathered Ingredients", "1 Coal, 6 Iron Ores, and 1 Leather"),
        (
            "Skills",
            "Armorsmith 4, Leatherworker 3, Miner 1, Rancher 2, Smelter 2, Tailor 1",
        ),
        ("Total Coin Cost", format_coin_amount(425)),
    ]
    expected = crafting_calc.build_table(("Summary", "Value"), expected_rows)
    assert summary == expected


def test_format_raw_material_section_outputs_expected(sample_recipes, boots_requirements):
    table = format_raw_material_section(boots_requirements, sample_recipes)
    expected_rows = [
        ("Coal", "1", "Coal Seam", "Miner", "1"),
        ("Iron Ore", "6", "Iron Vein", "Miner", "1"),
        ("Leather", "1", "Hunting Grounds", "Rancher", "2"),
    ]
    expected = crafting_calc.build_table(
        ("Raw Material", "Quantity", "Location", "Profession", "Skill Tier"),
        expected_rows,
    )
    assert table == expected


def test_format_purchase_section_outputs_expected(sample_recipes, boots_requirements):
    table = format_purchase_section(boots_requirements, sample_recipes)
    expected_rows = [
        (
            "Thread",
            "3",
            "Market Stall",
            "Tailor",
            "1",
            "25 copper",
            "75 copper",
        ),
    ]
    expected = crafting_calc.build_table(
        (
            "Purchase Item",
            "Quantity",
            "Location",
            "Profession",
            "Skill Tier",
            "Unit Cost",
            "Total Cost",
        ),
        expected_rows,
    )
    assert table == expected


def test_format_gather_box_wraps_lines(sample_recipes, boots_requirements):
    box = format_gather_box(boots_requirements, sample_recipes)
    expected = build_box(
        "1) Gather Raw Materials",
        [
            "- 1 Coal (Coal Seam)",
            "- 6 Iron Ores (Iron Vein)",
            "- 1 Leather (Hunting Grounds)",
        ],
    )
    assert box == expected


def test_format_purchase_box_wraps_lines(sample_recipes, boots_requirements):
    box = format_purchase_box(boots_requirements, sample_recipes)
    expected = build_box(
        "2) Purchase Supplies",
        ["- 3 Threads (Market Stall) @ 25 copper each -> 75 copper"],
    )
    assert box == expected


def test_format_report_contains_single_purchase_step(
    sample_recipes: dict[str, Recipe]
) -> None:
    report = format_report("Reinforced Boots", sample_recipes)
    assert report.count("2) Purchase Supplies") == 1


def test_format_crafting_box_wraps_lines(sample_recipes, boots_requirements):
    box = format_crafting_box("Reinforced Boots", boots_requirements, sample_recipes)
    expected = build_box(
        "3) Crafting Order",
        [
            "1. Craft 2 Iron Ingots at Smelter using 6 Iron Ores and 1 silver fee",
            "2. Craft 1 Steel Ingot at Forge using 2 Iron Ingots, 1 Coal, and 1 silver fee",
            (
                "3. Craft 1 Reinforced Boots at Cobbler Bench using 1 Steel Ingot, "
                "3 Threads, 1 Leather, and 1 silver, 50 copper fee"
            ),
        ],
    )
    assert box == expected


def test_build_purchase_lines_and_tables_handle_empty_states(sample_recipes):
    empty_requirements = {"purchase": {}, "raw": {}, "craft": {}, "craft_cost": 0}
    assert format_purchase_section(empty_requirements, sample_recipes) == crafting_calc.build_table(
        (
            "Purchase Item",
            "Quantity",
            "Location",
            "Profession",
            "Skill Tier",
            "Unit Cost",
            "Total Cost",
        ),
        [
            (
                "None",
                "-",
                "No purchase locations.",
                "-",
                "-",
                "-",
                "No purchases required.",
            )
        ],
    )
    assert format_gather_box(empty_requirements, sample_recipes) == build_box(
        "1) Gather Raw Materials", ["- No gathering required"]
    )
    assert format_purchase_box(empty_requirements, sample_recipes) == build_box(
        "2) Purchase Supplies", ["- No purchases required"]
    )
    assert format_crafting_box("Widget", empty_requirements, sample_recipes) == build_box(
        "3) Crafting Order", ["- No crafting steps required"]
    )


def test_format_coin_amount_boundaries():
    assert format_coin_amount(0) == "0 copper"
    assert format_coin_amount(100) == "1 silver"
    assert format_coin_amount(10123) == "1 gold, 1 silver, 23 copper"


def test_join_with_commas_variants():
    assert join_with_commas([]) == ""
    assert join_with_commas(["A"]) == "A"
    assert join_with_commas(["A", "B"]) == "A and B"
    assert join_with_commas(["A", "B", "C"]) == "A, B, and C"


def test_format_quantity_name_pluralization():
    assert crafting_calc.format_quantity_name(1, "Ore") == "1 Ore"
    assert crafting_calc.format_quantity_name(2, "Ore") == "2 Ores"
    assert crafting_calc.format_quantity_name(2, "Glass") == "2 Glass"


def test_get_source_location_defaults(sample_recipes):
    assert get_source_location(sample_recipes, "Iron Ore") == "Iron Vein"
    assert get_source_location(sample_recipes, "Missing", "Fallback") == "Fallback"


def test_get_profession_info_defaults(sample_recipes):
    assert get_profession_info(sample_recipes, "Thread") == ("Tailor", "1")
    assert get_profession_info(sample_recipes, "Missing") == ("Unknown", "-")


def test_merge_quantity_accumulates():
    data: dict[str, int] = {"Iron": 2}
    merge_quantity(data, "Iron", 3)
    merge_quantity(data, "Copper", 1)
    assert data == {"Iron": 5, "Copper": 1}


def test_resolve_requirements_handles_raw_material(sample_recipes):
    result = resolve_requirements("Leather", 2, sample_recipes)
    assert result["raw"] == {"Leather": 2}
    assert result["craft_cost"] == 0


def test_load_recipes_success_and_missing_columns(tmp_path: Path):
    csv_content = textwrap.dedent(
        """\
        item,materials,method,source,profession,skill_tier,cost
        Simple Item,,raw,Field,Farmer,1,0
        """
    )
    csv_path = tmp_path / "recipes.csv"
    csv_path.write_text(csv_content)
    recipes = crafting_calc.load_recipes(csv_path)
    assert recipes["Simple Item"]["method"] == "raw"

    bad_csv = textwrap.dedent(
        """\
        item,source,profession,skill_tier,cost
        Broken,,Smith,2,100
        """
    )
    bad_path = tmp_path / "bad.csv"
    bad_path.write_text(bad_csv)
    with pytest.raises(ValueError):
        crafting_calc.load_recipes(bad_path)


def test_load_recipes_invalid_material_quantity(tmp_path: Path):
    csv_content = textwrap.dedent(
        """\
        item,materials,method,source,profession,skill_tier,cost
        Bad Item,abc-Wood,craft,Workshop,Carpenter,2,10
        """
    )
    csv_path = tmp_path / "invalid.csv"
    csv_path.write_text(csv_content)
    with pytest.raises(ValueError):
        crafting_calc.load_recipes(csv_path)


def test_load_recipes_parses_multiple_outputs_and_simple_materials(tmp_path: Path):
    csv_content = textwrap.dedent(
        """\
        item,materials,method,source,profession,skill_tier,cost
        2-Glass Vial-1-Bottle Stopper,3-Sand-1-Water,craft,Glassworks,Glassblower,2,15
        Sand,,raw,Sand Pit,Gatherer,1,0
        Water,,raw,Well,Gatherer,1,0
        Simple Rope,Fiber,craft,Workshop,Ropemaker,1,5
        Fiber,,raw,Fields,Gatherer,1,0
        """
    )
    csv_path = tmp_path / "multi_outputs.csv"
    csv_path.write_text(csv_content)

    recipes = crafting_calc.load_recipes(csv_path)

    assert {"Glass Vial", "Bottle Stopper"}.issubset(recipes)

    vial_recipe = recipes["Glass Vial"]
    assert vial_recipe["output_quantity"] == 2
    assert vial_recipe["materials"] == [
        {"item": "Sand", "quantity": 3},
        {"item": "Water", "quantity": 1},
    ]
    assert vial_recipe["outputs"] == [
        {"item": "Glass Vial", "quantity": 2},
        {"item": "Bottle Stopper", "quantity": 1},
    ]

    stopper_recipe = recipes["Bottle Stopper"]
    assert stopper_recipe["output_quantity"] == 1
    assert stopper_recipe["materials"] == vial_recipe["materials"]

    rope_recipe = recipes["Simple Rope"]
    assert rope_recipe["materials"] == [{"item": "Fiber", "quantity": 1}]
    assert rope_recipe["output_quantity"] == 1


def test_resolve_requirements_handles_multiple_outputs(tmp_path: Path):
    csv_content = textwrap.dedent(
        """\
        item,materials,method,source,profession,skill_tier,cost
        2-Glass Vial-1-Bottle Stopper,3-Sand-1-Water,craft,Glassworks,Glassblower,2,15
        Sand,,raw,Sand Pit,Gatherer,1,0
        Water,,raw,Well,Gatherer,1,0
        """
    )
    csv_path = tmp_path / "multi_output_requirements.csv"
    csv_path.write_text(csv_content)

    recipes = crafting_calc.load_recipes(csv_path)
    requirements = crafting_calc.resolve_requirements("Glass Vial", 3, recipes)

    assert requirements["craft"]["Glass Vial"] == 4
    assert requirements["craft_cost"] == 30
    assert requirements["raw"] == {"Sand": 6, "Water": 2}
    assert requirements["purchase"] == {}
    assert "Bottle Stopper" not in requirements["craft"]

    lines = crafting_calc.build_craft_lines(
        "Glass Vial", requirements["craft"], recipes
    )
    assert lines == [
        "1. Craft 4 Glass Vials at Glassworks using 6 Sands, 2 Waters, and 30 copper fee"
    ]


def test_load_recipes_allows_missing_profession_for_non_craft(tmp_path: Path):
    csv_content = textwrap.dedent(
        """\
        item,materials,method,source,profession,skill_tier,cost
        Water,,purchase,Vendor,,,33
        Clay,,raw,Clay Pit,,,0
        """
    )
    csv_path = tmp_path / "missing_profession.csv"
    csv_path.write_text(csv_content)

    recipes = crafting_calc.load_recipes(csv_path)
    water = recipes["Water"]
    assert water["profession"] == "Unknown"
    assert water["skill_tier"] == 0

    clay = recipes["Clay"]
    assert clay["profession"] == "Unknown"
    assert clay["skill_tier"] == 0

    bad_csv = textwrap.dedent(
        """\
        item,materials,method,source,profession,skill_tier,cost
        Sword,1-Iron Ingot,craft,Forge,,3,100
        """
    )
    bad_path = tmp_path / "missing_profession_craft.csv"
    bad_path.write_text(bad_csv)
    with pytest.raises(ValueError):
        crafting_calc.load_recipes(bad_path)


def test_load_recipes_validates_non_craft_skill_tier_range(tmp_path: Path):
    csv_content = textwrap.dedent(
        """\
        item,materials,method,source,profession,skill_tier,cost
        Water,,purchase,Vendor,,6,33
        """
    )
    csv_path = tmp_path / "invalid_non_craft_tier.csv"
    csv_path.write_text(csv_content)

    with pytest.raises(ValueError):
        crafting_calc.load_recipes(csv_path)
