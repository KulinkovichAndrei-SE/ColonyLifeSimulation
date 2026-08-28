"""Display-free deterministic simulation infrastructure.

This module deliberately contains only the small probe world needed to prove
the deterministic simulation seam.  It is not a replacement for the legacy
``Human`` or Pygame implementation and contains no lifecycle, relationship,
reproduction, or economy rules.
"""

from __future__ import annotations

import json
import math
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union


SNAPSHOT_SCHEMA_VERSION = 1
SCHEMA_VERSION = SNAPSHOT_SCHEMA_VERSION

_SNAPSHOT_KEYS = frozenset(
    {"schema_version", "config", "tick", "agents", "random_state", "events"}
)
_CONFIG_KEYS = frozenset({"seed", "width", "height", "population"})
_AGENT_KEYS = frozenset({"id", "x", "y"})
_EVENT_KEYS = frozenset(
    {"sequence", "tick", "event_type", "agent_id", "previous_position", "position"}
)
_PROBE_ID_PATTERN = re.compile(r"^probe-[0-9]+$")
_DIRECTIONS: Tuple[Tuple[int, int], ...] = (
    (-1, -1),
    (-1, 0),
    (-1, 1),
    (0, -1),
    (0, 0),
    (0, 1),
    (1, -1),
    (1, 0),
    (1, 1),
)


class SnapshotValidationError(ValueError):
    """Raised when a snapshot is malformed or incompatible with this core."""


def _is_int(value: Any) -> bool:
    """Return whether *value* is a JSON integer, excluding booleans."""

    return type(value) is int


def _require_int(value: Any, name: str) -> int:
    if not _is_int(value):
        raise ValueError(f"{name} must be an integer")
    return value


def _require_non_negative_int(value: Any, name: str) -> int:
    result = _require_int(value, name)
    if result < 0:
        raise ValueError(f"{name} must be non-negative")
    return result


def _require_step_count(value: Any, name: str = "step count") -> int:
    return _require_non_negative_int(value, name)


@dataclass(frozen=True, init=False)
class SimulationConfig:
    """Immutable, validated configuration for one deterministic run.

    ``width`` and ``height`` are the canonical constructor and snapshot
    fields.  ``world_width`` and ``world_height`` are accepted as explicit
    aliases because they make call sites that describe world dimensions more
    readable; both forms cannot disagree.
    """

    seed: int
    width: int
    height: int
    population: int

    def __init__(
        self,
        seed: int,
        width: Optional[int] = None,
        height: Optional[int] = None,
        population: int = 0,
        *,
        world_width: Optional[int] = None,
        world_height: Optional[int] = None,
    ) -> None:
        if width is None:
            width = world_width
        elif world_width is not None and width != world_width:
            raise ValueError("width and world_width must agree")

        if height is None:
            height = world_height
        elif world_height is not None and height != world_height:
            raise ValueError("height and world_height must agree")

        _validate_config_values(seed, width, height, population)
        object.__setattr__(self, "seed", seed)
        object.__setattr__(self, "width", width)
        object.__setattr__(self, "height", height)
        object.__setattr__(self, "population", population)

    @property
    def world_width(self) -> int:
        return self.width

    @property
    def world_height(self) -> int:
        return self.height

    def as_dict(self) -> Dict[str, int]:
        """Return the canonical JSON-compatible configuration mapping."""

        return {
            "seed": self.seed,
            "width": self.width,
            "height": self.height,
            "population": self.population,
        }

    to_dict = as_dict

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SimulationConfig":
        if not isinstance(value, Mapping):
            raise SnapshotValidationError("config must be a JSON object")
        if frozenset(value.keys()) != _CONFIG_KEYS:
            raise SnapshotValidationError("config has missing or unknown fields")
        try:
            return cls(
                seed=value["seed"],
                width=value["width"],
                height=value["height"],
                population=value["population"],
            )
        except (TypeError, ValueError) as exc:
            raise SnapshotValidationError(f"invalid config: {exc}") from exc


def _validate_config_values(
    seed: Any, width: Any, height: Any, population: Any
) -> None:
    _require_int(seed, "seed")
    width_value = _require_int(width, "width")
    height_value = _require_int(height, "height")
    population_value = _require_int(population, "population")
    if width_value <= 0:
        raise ValueError("width must be positive")
    if height_value <= 0:
        raise ValueError("height must be positive")
    if population_value < 0:
        raise ValueError("population must be non-negative")


class SimulationClock:
    """A fixed-step, non-negative integer simulation clock."""

    def __init__(self, tick: int = 0) -> None:
        self._tick = _require_non_negative_int(tick, "tick")

    @property
    def tick(self) -> int:
        return self._tick

    @property
    def current_tick(self) -> int:
        return self._tick

    def advance(self, steps: int = 1) -> int:
        """Advance by exactly ``steps`` ticks and return the new tick."""

        count = _require_step_count(steps)
        self._tick += count
        return self._tick

    def step(self) -> int:
        """Advance this clock by one tick."""

        return self.advance(1)


def _encode_random_state(state: Tuple[Any, ...]) -> List[Any]:
    """Convert the stdlib random state tuple into JSON-compatible lists."""

    version, internal, gauss_next = state
    return [version, list(internal), gauss_next]


def _decode_random_state(value: Any) -> Tuple[int, Tuple[int, ...], Optional[float]]:
    """Validate and convert a JSON random state without touching a live RNG."""

    if type(value) is not list or len(value) != 3:
        raise SnapshotValidationError("random_state must be a three-item array")

    version = value[0]
    if not _is_int(version) or version != 3:
        raise SnapshotValidationError("random_state has an unsupported version")

    internal = value[1]
    if type(internal) is not list or len(internal) != 625:
        raise SnapshotValidationError("random_state internal state is invalid")
    for index, item in enumerate(internal):
        if not _is_int(item) or not 0 <= item <= 0xFFFFFFFF:
            raise SnapshotValidationError(
                f"random_state internal value {index} is invalid"
            )
    if internal[-1] < 0 or internal[-1] > 624:
        raise SnapshotValidationError("random_state index is out of range")

    gauss_next = value[2]
    if gauss_next is not None:
        if type(gauss_next) not in (int, float) or not math.isfinite(gauss_next):
            raise SnapshotValidationError("random_state gaussian value is invalid")

    decoded = (version, tuple(internal), gauss_next)
    verifier = random.Random()
    try:
        verifier.setstate(decoded)
    except (TypeError, ValueError, OverflowError) as exc:
        raise SnapshotValidationError("random_state cannot be restored") from exc
    return decoded


class SeededRandom:
    """A deterministic random source owned by one simulation instance."""

    def __init__(self, seed: int) -> None:
        _require_int(seed, "seed")
        self._seed = seed
        self._random = random.Random(seed)

    @property
    def seed(self) -> int:
        return self._seed

    def choice(self, sequence: Sequence[Any]) -> Any:
        return self._random.choice(sequence)

    def randrange(self, *args: int) -> int:
        return self._random.randrange(*args)

    def get_state(self) -> List[Any]:
        return _encode_random_state(self._random.getstate())

    @property
    def state(self) -> List[Any]:
        return self.get_state()

    def set_state(self, value: Any) -> None:
        """Validate and replace this source's state atomically."""

        decoded = _decode_random_state(value)
        self._random.setstate(decoded)

    @classmethod
    def from_state(cls, seed: int, value: Any) -> "SeededRandom":
        source = cls(seed)
        source.set_state(value)
        return source


@dataclass(frozen=True)
class ProbeAgent:
    """The intentionally small state of one infrastructure probe agent."""

    agent_id: str
    x: int
    y: int

    @property
    def id(self) -> str:
        return self.agent_id

    @property
    def position(self) -> Tuple[int, int]:
        return (self.x, self.y)

    def as_dict(self) -> Dict[str, Any]:
        return {"id": self.agent_id, "x": self.x, "y": self.y}

    to_dict = as_dict


@dataclass(frozen=True)
class SimulationEvent:
    """An ordered, serializable record of a core state transition."""

    sequence: int
    tick: int
    event_type: str
    agent_id: Optional[str]
    previous_position: Optional[Tuple[int, int]]
    position: Optional[Tuple[int, int]]

    def __post_init__(self) -> None:
        if not _is_int(self.sequence) or self.sequence <= 0:
            raise ValueError("event sequence must be a positive integer")
        if not _is_int(self.tick) or self.tick < 0:
            raise ValueError("event tick must be a non-negative integer")
        if not isinstance(self.event_type, str) or not self.event_type:
            raise ValueError("event_type must be a non-empty string")
        if self.agent_id is not None and not isinstance(self.agent_id, str):
            raise ValueError("event agent_id must be a string or null")
        for name, position in (
            ("previous_position", self.previous_position),
            ("position", self.position),
        ):
            if position is None:
                continue
            if (
                type(position) is not tuple
                or len(position) != 2
                or not all(_is_int(item) for item in position)
            ):
                raise ValueError(f"event {name} must be a two-integer tuple or null")

    @property
    def kind(self) -> str:
        return self.event_type

    def as_dict(self) -> Dict[str, Any]:
        return {
            "sequence": self.sequence,
            "tick": self.tick,
            "event_type": self.event_type,
            "agent_id": self.agent_id,
            "previous_position": _position_to_json(self.previous_position),
            "position": _position_to_json(self.position),
        }

    to_dict = as_dict


def _position_to_json(position: Optional[Tuple[int, int]]) -> Optional[List[int]]:
    if position is None:
        return None
    return [position[0], position[1]]


def _expected_agent_id(index: int) -> str:
    return f"probe-{index:04d}"


class DeterministicSimulation:
    """Single-owner deterministic probe simulation.

    The simulation owns its clock, random source, agents, and event log.  No
    domain transition reads wall-clock time, initializes a display, or uses a
    process-global random source.
    """

    def __init__(self, config: SimulationConfig) -> None:
        if not isinstance(config, SimulationConfig):
            raise TypeError("config must be a SimulationConfig")
        self._config = config
        self._clock = SimulationClock()
        self._random = SeededRandom(config.seed)
        self._agents: List[ProbeAgent] = []
        for index in range(config.population):
            self._agents.append(
                ProbeAgent(
                    agent_id=_expected_agent_id(index),
                    x=self._random.randrange(config.width),
                    y=self._random.randrange(config.height),
                )
            )
        self._events: List[SimulationEvent] = []
        self._next_event_sequence = 1

    @property
    def config(self) -> SimulationConfig:
        return self._config

    @property
    def clock(self) -> SimulationClock:
        return self._clock

    @property
    def tick(self) -> int:
        return self._clock.tick

    @property
    def agents(self) -> Tuple[ProbeAgent, ...]:
        return tuple(self._agents)

    @property
    def probe_agents(self) -> Tuple[ProbeAgent, ...]:
        return self.agents

    @property
    def events(self) -> Tuple[SimulationEvent, ...]:
        return tuple(self._events)

    @property
    def random_source(self) -> SeededRandom:
        return self._random

    @property
    def random_state(self) -> List[Any]:
        return self._random.get_state()

    def step(self) -> None:
        """Advance one tick and record its ordered transition events."""

        tick = self._clock.step()
        pending_events = [
            SimulationEvent(
                sequence=self._next_event_sequence,
                tick=tick,
                event_type="tick_advanced",
                agent_id=None,
                previous_position=None,
                position=None,
            )
        ]
        next_sequence = self._next_event_sequence + 1
        next_agents: List[ProbeAgent] = []

        for agent in self._agents:
            dx, dy = self._random.choice(_DIRECTIONS)
            next_position = (
                min(max(agent.x + dx, 0), self._config.width - 1),
                min(max(agent.y + dy, 0), self._config.height - 1),
            )
            updated = ProbeAgent(agent.agent_id, next_position[0], next_position[1])
            next_agents.append(updated)
            pending_events.append(
                SimulationEvent(
                    sequence=next_sequence,
                    tick=tick,
                    event_type="probe_moved",
                    agent_id=agent.agent_id,
                    previous_position=agent.position,
                    position=updated.position,
                )
            )
            next_sequence += 1

        self._agents = next_agents
        self._events.extend(pending_events)
        self._next_event_sequence = next_sequence

    def run(self, steps: int) -> "DeterministicSimulation":
        """Advance exactly ``steps`` ticks; zero is a no-op."""

        count = _require_step_count(steps)
        for _ in range(count):
            self.step()
        return self

    def snapshot(self) -> Dict[str, Any]:
        """Return a fresh canonical JSON-compatible state mapping."""

        return {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "config": self._config.as_dict(),
            "tick": self._clock.tick,
            "agents": [agent.as_dict() for agent in self._agents],
            "random_state": self._random.get_state(),
            "events": [event.as_dict() for event in self._events],
        }

    def canonical_json(self) -> str:
        return canonical_json(self.snapshot())

    snapshot_json = canonical_json
    to_json = canonical_json

    def save_json(self, path: Union[str, Path]) -> None:
        """Write the versioned snapshot as canonical, non-executable JSON."""

        destination = Path(path)
        destination.write_text(self.canonical_json(), encoding="utf-8")

    @classmethod
    def from_snapshot(cls, snapshot: Mapping[str, Any]) -> "DeterministicSimulation":
        """Build a new simulation after validating the complete snapshot."""

        config, tick, agents, random_state, events = _validate_snapshot(snapshot)
        simulation = cls(config)
        simulation._clock = SimulationClock(tick)
        simulation._random.set_state(random_state)
        simulation._agents = list(agents)
        simulation._events = list(events)
        simulation._next_event_sequence = (
            events[-1].sequence + 1 if events else 1
        )
        return simulation

    @classmethod
    def load_json(cls, path: Union[str, Path]) -> "DeterministicSimulation":
        """Load a validated snapshot from JSON into a new simulation."""

        try:
            with Path(path).open("r", encoding="utf-8") as source:
                snapshot = json.load(
                    source,
                    object_pairs_hook=_strict_object_pairs,
                    parse_constant=_reject_json_constant,
                )
        except SnapshotValidationError:
            raise
        except (OSError, UnicodeError) as exc:
            raise SnapshotValidationError(f"could not read snapshot: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise SnapshotValidationError(f"invalid snapshot JSON: {exc}") from exc
        return cls.from_snapshot(snapshot)


def canonical_json(value: Any) -> str:
    """Serialize JSON-compatible data with stable key and separator choices."""

    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"value is not canonical JSON-compatible: {exc}") from exc


def _strict_object_pairs(pairs: List[Tuple[str, Any]]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SnapshotValidationError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise SnapshotValidationError(f"non-standard JSON constant is not allowed: {value}")


def _validate_position(
    value: Any,
    name: str,
    config: SimulationConfig,
    *,
    allow_none: bool = False,
) -> Optional[Tuple[int, int]]:
    if value is None and allow_none:
        return None
    if type(value) is not list or len(value) != 2:
        raise SnapshotValidationError(f"{name} must be a two-item array")
    if not all(_is_int(item) for item in value):
        raise SnapshotValidationError(f"{name} must contain integers")
    x, y = value
    if not 0 <= x < config.width or not 0 <= y < config.height:
        raise SnapshotValidationError(f"{name} is out of bounds")
    return (x, y)


def _validate_snapshot(
    snapshot: Mapping[str, Any],
) -> Tuple[
    SimulationConfig,
    int,
    Tuple[ProbeAgent, ...],
    List[Any],
    Tuple[SimulationEvent, ...],
]:
    if not isinstance(snapshot, Mapping):
        raise SnapshotValidationError("snapshot must be a JSON object")
    if frozenset(snapshot.keys()) != _SNAPSHOT_KEYS:
        raise SnapshotValidationError("snapshot has missing or unknown fields")

    schema_version = snapshot["schema_version"]
    if not _is_int(schema_version) or schema_version != SNAPSHOT_SCHEMA_VERSION:
        raise SnapshotValidationError("unsupported snapshot schema version")

    config = SimulationConfig.from_dict(snapshot["config"])
    try:
        tick = _require_non_negative_int(snapshot["tick"], "tick")
    except ValueError as exc:
        raise SnapshotValidationError(str(exc)) from exc

    raw_agents = snapshot["agents"]
    if type(raw_agents) is not list:
        raise SnapshotValidationError("agents must be an array")
    if len(raw_agents) != config.population:
        raise SnapshotValidationError("agent count does not match population")

    agents: List[ProbeAgent] = []
    expected_ids = [_expected_agent_id(index) for index in range(config.population)]
    for index, raw_agent in enumerate(raw_agents):
        if not isinstance(raw_agent, Mapping):
            raise SnapshotValidationError(f"agent {index} must be an object")
        if frozenset(raw_agent.keys()) != _AGENT_KEYS:
            raise SnapshotValidationError(f"agent {index} has invalid fields")
        agent_id = raw_agent["id"]
        if (
            not isinstance(agent_id, str)
            or not _PROBE_ID_PATTERN.fullmatch(agent_id)
            or agent_id != expected_ids[index]
        ):
            raise SnapshotValidationError(f"agent {index} has an invalid stable id")
        try:
            position = _validate_position(
                [raw_agent["x"], raw_agent["y"]],
                f"agent {index} position",
                config,
            )
        except KeyError as exc:
            raise SnapshotValidationError(f"agent {index} is missing position") from exc
        assert position is not None
        agents.append(ProbeAgent(agent_id, position[0], position[1]))

    # Decode and validate the complete RNG state before any new core is built.
    decoded_random_state = _decode_random_state(snapshot["random_state"])
    encoded_random_state = _encode_random_state(decoded_random_state)

    raw_events = snapshot["events"]
    if type(raw_events) is not list:
        raise SnapshotValidationError("events must be an array")
    events: List[SimulationEvent] = []
    previous_sequence = 0
    previous_tick = 0
    known_ids = set(expected_ids)
    for index, raw_event in enumerate(raw_events):
        if not isinstance(raw_event, Mapping):
            raise SnapshotValidationError(f"event {index} must be an object")
        if frozenset(raw_event.keys()) != _EVENT_KEYS:
            raise SnapshotValidationError(f"event {index} has invalid fields")
        try:
            sequence = _require_int(raw_event["sequence"], f"event {index} sequence")
            event_tick = _require_non_negative_int(
                raw_event["tick"], f"event {index} tick"
            )
        except (KeyError, ValueError) as exc:
            raise SnapshotValidationError(f"event {index} has invalid ordering fields") from exc
        if sequence <= previous_sequence:
            raise SnapshotValidationError("event sequences must be strictly increasing")
        if event_tick < previous_tick or event_tick > tick:
            raise SnapshotValidationError("event ticks must be non-decreasing and current")

        event_type = raw_event["event_type"]
        if not isinstance(event_type, str) or event_type not in {
            "tick_advanced",
            "probe_moved",
        }:
            raise SnapshotValidationError(f"event {index} has an unknown event type")
        agent_id = raw_event["agent_id"]
        if event_type == "tick_advanced":
            if (
                agent_id is not None
                or raw_event["previous_position"] is not None
                or raw_event["position"] is not None
            ):
                raise SnapshotValidationError("tick event has invalid agent or position")
            previous_position = None
            position = None
        else:
            if not isinstance(agent_id, str) or agent_id not in known_ids:
                raise SnapshotValidationError(f"event {index} names an unknown agent")
            previous_position = _validate_position(
                raw_event["previous_position"],
                f"event {index} previous_position",
                config,
            )
            position = _validate_position(
                raw_event["position"], f"event {index} position", config
            )

        events.append(
            SimulationEvent(
                sequence=sequence,
                tick=event_tick,
                event_type=event_type,
                agent_id=agent_id,
                previous_position=previous_position,
                position=position,
            )
        )
        previous_sequence = sequence
        previous_tick = event_tick

    return config, tick, tuple(agents), encoded_random_state, tuple(events)
