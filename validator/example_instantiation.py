"""Worked example: an agent (or a human) produces item_labels as a CSV —
category and priority are supposed to come from a closed vocabulary. This
script is the gate. It never re-implements validation logic; it only
supplies SCHEMA to the shared validator_skeleton functions.

Run:
    py -3 example_instantiation.py --csv example_labels.csv
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from validator_skeleton import run_cli  # noqa: E402

SCHEMA = {
    "item_id": {"required": True},
    "category": {"required": True, "enum": {"bug", "feature", "chore"}},
    "priority": {"required": True, "enum": {"low", "medium", "high"}},
    "notes": {"required": False},
}

if __name__ == "__main__":
    sys.exit(run_cli(SCHEMA))
