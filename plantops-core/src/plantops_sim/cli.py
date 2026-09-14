from __future__ import annotations

import argparse
import json

from .engine import ProductionLineSimulation
from .scenario import make_mvp_scenario


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the PlantOps MVP production line.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--minutes", type=float, default=480)
    parser.add_argument("--no-failures", action="store_true")
    args = parser.parse_args()
    scenario = make_mvp_scenario(cnc_failure_probability=0 if args.no_failures else 0.055)
    simulation = ProductionLineSimulation(scenario, seed=args.seed)
    result = simulation.run(args.minutes)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"event_digest={simulation.digest()}")


if __name__ == "__main__":
    main()
