# AshesCraftingCalc

Calculate what mats you need to craft the item of your dreams, where to get them from and how much moolah it'll cost you.
I'll be honest, a lot of this code is likely to come from Codex or some other AI coder. I don't have the time to focus on this full time.

## Getting started

This repository contains a simple command line tool that reads crafting recipe data from `data/recipes.csv` and produces a cost and shopping breakdown for a requested item.

### Prerequisites

* Python 3.9 or newer.

### Usage

List the available craftable items:

```bash
python crafting_calc.py --list
```

Generate the crafting plan for a specific item:

```bash
python crafting_calc.py "Steel Longsword"
```

The tool will display:

* A summary of the requested item alongside its crafting station, total crafting fees, gathering checklist, total coin cost, and the professions required (with their highest tiers).
* ASCII tables outlining raw materials to gather and items that must be purchased, including the locations, professions, and skill tiers needed to acquire them.
* Totals for purchase costs and overall copper spend, expressed as gold/silver/copper.
* Step-by-step directions covering the gathering checklist, purchase plan, and crafting order from lowest to highest tier.

### Custom data

You can point the tool at an alternate CSV file by passing the `--data` flag:

```bash
python crafting_calc.py "Steel Longsword" --data other_recipes.csv
```

The CSV must contain the following columns:

* `item` – the name of the item the row defines.
* `materials` – a hyphen-separated list of quantity/item pairs describing the materials required to craft the item (for example `4-Iron Ingot-2-Leather Wrap`). Leave this field blank for purchased or raw items.
* `method` – one of `craft`, `purchase`, or `raw`.
  * `craft` indicates the item can be produced using the listed materials. Every craft incurs the copper `cost` listed for the row.
  * `purchase` indicates the item must be bought from a vendor for the listed copper `cost` per unit.
  * `raw` indicates the item is gathered directly and has no copper cost.
* `source` – a descriptive location. For example, crafted items specify the station required, purchased items list the vendor, and raw items describe the gathering location.
* `profession` – the profession or trade skill associated with acquiring the item (crafting, purchasing, or gathering).
* `skill_tier` – an integer from 1–5 describing the tier required in the listed profession.
* `cost` – total copper required for the action described by `method`. For crafted items this is the per-item crafting fee, while for purchased items it is the per-unit price.

If an ingredient referenced in `materials` does not have its own row, it is treated as a raw resource that must be gathered with no copper cost. Crafting requirements are resolved recursively, so crafting an item will also include any costs or materials needed to craft its components.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
