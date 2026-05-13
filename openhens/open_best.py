"""Open the best solution from durable study artifacts."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from openhens.artifacts import load_study_outcome


def main() -> None:
    parser = argparse.ArgumentParser(description="Print the lowest-TAC solution from OpenHENS artifacts.")
    parser.add_argument("run_folder", type=Path, help="Folder containing manifest.json for one OpenHENS run.")
    args = parser.parse_args()

    outcome = load_study_outcome(args.run_folder)
    best = outcome.solutions.best_by_total_annual_cost()
    if best is None:
        print("No solution with total annual cost was found.")
        return

    print(f"Best solution: {best.name}")
    print(f"Task ID: {best.task_id}")
    print(f"Method: {best.method}")
    print(f"Total annual cost: {best.total_annual_cost}")
    print(f"Stages: {best.stages}")


if __name__ == "__main__":
    main()
