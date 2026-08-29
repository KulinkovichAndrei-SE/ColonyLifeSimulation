"""Run the autonomous colony simulation quickly without opening the UI."""

from __future__ import annotations

import argparse
import sys
from typing import Any, Dict, Optional

from colony_simulation import ColonyConfig, ColonySimulation
from simulation_core import canonical_json


DEFAULT_TICKS_PER_GENERATION = 20


def _integer(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError(f"expected an integer, got {value!r}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run deterministic autonomous colony training without Pygame."
    )
    parser.add_argument(
        "--generations",
        type=_integer,
        required=True,
        help="number of training windows to execute (non-negative)",
    )
    parser.add_argument(
        "--ticks-per-generation",
        type=_integer,
        default=DEFAULT_TICKS_PER_GENERATION,
        help=f"ticks in each training window (default: {DEFAULT_TICKS_PER_GENERATION})",
    )
    parser.add_argument("--seed", type=_integer, default=7, help="random seed (default: 7)")
    parser.add_argument("--width", type=_integer, default=24, help="world width")
    parser.add_argument("--height", type=_integer, default=16, help="world height")
    parser.add_argument("--population", type=_integer, default=8, help="initial population")
    parser.add_argument("--settlements", type=_integer, default=2, help="number of settlements")
    parser.add_argument("--max-age", type=_integer, default=40, help="maximum resident age")
    parser.add_argument(
        "--stop-on-game-over",
        action="store_true",
        help="stop at a terminal outcome instead of continuing the training workload",
    )
    return parser


def _config_from_args(args: argparse.Namespace) -> ColonyConfig:
    return ColonyConfig(
        seed=args.seed,
        width=args.width,
        height=args.height,
        population=args.population,
        settlement_count=args.settlements,
        max_age=args.max_age,
        ai_enabled=True,
    )


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.generations < 0:
        parser.error("--generations must be non-negative")
    if args.ticks_per_generation <= 0:
        parser.error("--ticks-per-generation must be positive")

    try:
        simulation = ColonySimulation(_config_from_args(args))
        report: Dict[str, Any] = simulation.run_training(
            args.generations,
            ticks_per_generation=args.ticks_per_generation,
            terminal_mode=("diagnostic_stop" if args.stop_on_game_over else "continue_after_game_over"),
        )
        output = canonical_json(report)
    except (AssertionError, TypeError, ValueError) as exc:
        parser.exit(2, f"error: {exc}\n")

    sys.stdout.write(output + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
