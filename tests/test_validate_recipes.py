import sys
import textwrap
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parent.parent))

from validate_recipes import ValidationError, validate_csv


def test_validate_csv_reports_multiple_errors(tmp_path: Path) -> None:
    csv_path = tmp_path / "recipes.csv"
    csv_path.write_text(
        textwrap.dedent(
            """\
            item,materials,method,source,profession,skill_tier,cost
            , ,craft,, ,0,
            Mystery Potion,2-Water-Root,alchemy,Arcane Lab,Alchemist,two,50g
            Bad Materials,1-,craft,Forge,Smith,3,100

            """
        ),
        encoding="utf-8",
    )

    problems = validate_csv(csv_path)

    assert [row for row, *_ in problems] == [2, 3, 4]

    line2_errors = {message for _, item, errors in problems if item == "<missing item>" for message in errors}
    assert "Item name must not be empty" in line2_errors
    assert "Source location must not be empty" in line2_errors
    assert "Profession must not be empty" in line2_errors
    assert "Skill tier must be between 1 and 5" in line2_errors
    assert "Cost must be an integer (got blank)" in line2_errors
    assert "Crafted items must list component materials" in line2_errors

    line3_errors = {message for _, item, errors in problems if item == "Mystery Potion" for message in errors}
    assert "Method must be one of ['craft', 'purchase', 'raw'] (got alchemy)" in line3_errors
    assert "Skill tier must be an integer (got two)" in line3_errors
    assert "Cost must be an integer (got 50g)" in line3_errors
    assert "Materials must contain quantity/item pairs (missing a value?)" in line3_errors

    line4_errors = {message for _, item, errors in problems if item == "Bad Materials" for message in errors}
    assert "Materials must contain quantity/item pairs (missing a value?)" in line4_errors


def test_validate_csv_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        validate_csv(tmp_path / "missing.csv")
