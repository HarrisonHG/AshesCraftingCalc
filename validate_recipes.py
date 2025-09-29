#!/usr/bin/env python3
"""Validate the project recipe CSV."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

DATA_FILE = Path(__file__).parent / "data" / "recipes.csv"

REQUIRED_COLUMNS = {
    "item",
    "materials",
    "method",
    "source",
    "profession",
    "skill_tier",
    "cost",
}

VALID_METHODS = {"craft", "purchase", "raw"}


class ValidationError(Exception):
    """Raised when validation of the CSV fails."""


class RowValidator:
    """Perform field-by-field validation for a CSV row."""

    def __init__(self, row_number: int, raw_row: dict[str, str]):
        self.raw_row = raw_row
        self.errors: list[str] = []

    def add_error(self, message: str) -> None:
        self.errors.append(message)

    def validate_item(self) -> str:
        value = (self.raw_row.get("item") or "").strip()
        if not value:
            self.add_error("Item name must not be empty")
        return value

    def validate_method(self, item: str) -> str:
        raw = (self.raw_row.get("method") or "").strip().lower()
        if raw not in VALID_METHODS:
            self.add_error(f"Method must be one of {sorted(VALID_METHODS)} (got {raw or 'blank'})")
        return raw

    def validate_source(self, item: str) -> None:
        value = (self.raw_row.get("source") or "").strip()
        if not value:
            self.add_error("Source location must not be empty")

    def validate_profession(self) -> None:
        value = (self.raw_row.get("profession") or "").strip()
        if not value:
            self.add_error("Profession must not be empty")

    def validate_skill_tier(self) -> None:
        raw = (self.raw_row.get("skill_tier") or "").strip()
        try:
            value = int(raw)
        except ValueError:
            self.add_error(f"Skill tier must be an integer (got {raw or 'blank'})")
            return
        if not 1 <= value <= 5:
            self.add_error("Skill tier must be between 1 and 5")

    def validate_cost(self) -> None:
        raw = (self.raw_row.get("cost") or "").strip()
        try:
            int(raw)
        except ValueError:
            self.add_error(f"Cost must be an integer (got {raw or 'blank'})")

    def validate_materials(self, item: str, method: str) -> None:
        raw = (self.raw_row.get("materials") or "").strip()
        if not raw:
            if method == "craft":
                self.add_error("Crafted items must list component materials")
            return

        tokens = [chunk.strip() for chunk in raw.split("-") if chunk.strip()]
        if len(tokens) % 2 != 0:
            self.add_error(
                "Materials must contain quantity/item pairs (missing a value?)"
            )
            return

        for qty_token, name in zip(tokens[0::2], tokens[1::2]):
            if not qty_token:
                self.add_error("Material quantity is missing")
                continue
            try:
                quantity = int(qty_token)
            except ValueError:
                self.add_error(
                    f"Material quantity must be an integer (got {qty_token or 'blank'})"
                )
                continue
            if quantity <= 0:
                self.add_error(
                    f"Material quantity must be positive (got {quantity})"
                )
            if not name:
                self.add_error(
                    f"Material name is missing for quantity {qty_token}"
                )

    def validate(self) -> list[str]:
        item = self.validate_item()
        method = self.validate_method(item)
        self.validate_source(item)
        self.validate_profession()
        self.validate_skill_tier()
        self.validate_cost()
        self.validate_materials(item, method)
        return self.errors


def validate_csv(path: Path) -> list[tuple[int, str, list[str]]]:
    """Validate ``path`` and return a list of row errors."""

    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            header = reader.fieldnames
            if header is None:
                raise ValidationError("CSV file has no header row")
            missing = REQUIRED_COLUMNS - set(header)
            if missing:
                missing_list = ", ".join(sorted(missing))
                raise ValidationError(
                    f"CSV is missing required columns: {missing_list}"
                )

            problems: list[tuple[int, str, list[str]]] = []
            for index, row in enumerate(reader, start=2):
                if all((value is None or not str(value).strip()) for value in row.values()):
                    continue
                validator = RowValidator(index, row)
                errors = validator.validate()
                if errors:
                    item = (row.get("item") or "").strip() or "<missing item>"
                    problems.append((index, item, errors))
    except FileNotFoundError as exc:
        raise ValidationError(
            f"Recipe data not found at {path}. Did you download the dataset?"
        ) from exc

    return problems


def main() -> int:
    try:
        problems = validate_csv(DATA_FILE)
    except ValidationError as exc:
        print(f"Error: {exc}")
        return 1

    if not problems:
        print(f"{DATA_FILE.name}: no problems found")
        return 0

    print(f"Found {len(problems)} problem row(s) in {DATA_FILE.name}:")
    for line_number, item, errors in problems:
        heading = f"  Line {line_number}: {item}"
        print(heading)
        for message in errors:
            print(f"    - {message}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
