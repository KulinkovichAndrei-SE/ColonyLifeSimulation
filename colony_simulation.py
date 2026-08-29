"""Deterministic, display-free colony simulation rules.

The legacy Pygame prototype remains in its original modules.  This module is
the headless domain path for the roadmap: every transition is driven by an
explicit simulation tick, an owned seeded random source, and an ordered event
stream.  The implementation intentionally keeps individual state, memory,
learned policy, genome, settlement knowledge, and economic state separate.
"""

from __future__ import annotations

import json
import hashlib
import math
import statistics
import time
import tracemalloc
from math import ceil
from dataclasses import MISSING, dataclass, field, replace
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

from simulation_core import (
    SeededRandom,
    SimulationClock,
    SnapshotValidationError,
    canonical_json,
)
from neuralnetwork import NNetwork


SNAPSHOT_SCHEMA_VERSION = 5
SUPPORTED_SNAPSHOT_SCHEMA_VERSIONS = {4, SNAPSHOT_SCHEMA_VERSION}
MAX_MEMORY_ITEMS = 24
MAX_RELATION_MEMORY = 32
MATERIAL_PRICES = {"wood": 3, "grain": 4, "stone": 5, "ore": 7}
AGENT_ACTIONS = ("move", "produce", "socialize", "care", "trade", "learn")
NEURAL_INPUT_COUNT = 10
NEURAL_HIDDEN_COUNT = 12
NEURAL_WEIGHT_COUNT = NNetwork.getTotalWeights(NEURAL_INPUT_COUNT, NEURAL_HIDDEN_COUNT, len(AGENT_ACTIONS))
SETTLEMENT_ACTIONS = ("produce", "research", "observe", "migrate", "trade", "diplomacy")
SETTLEMENT_INPUT_COUNT = 8
SETTLEMENT_HIDDEN_COUNT = 12
SETTLEMENT_WEIGHT_COUNT = NNetwork.getTotalWeights(
    SETTLEMENT_INPUT_COUNT, SETTLEMENT_HIDDEN_COUNT, len(SETTLEMENT_ACTIONS)
)


def _is_int(value: Any) -> bool:
    return type(value) is int


def _require_int(value: Any, name: str) -> int:
    if not _is_int(value):
        raise ValueError(f"{name} must be an integer")
    return value


def _non_negative(value: Any, name: str) -> int:
    result = _require_int(value, name)
    if result < 0:
        raise ValueError(f"{name} must be non-negative")
    return result


def _positive(value: Any, name: str) -> int:
    result = _require_int(value, name)
    if result <= 0:
        raise ValueError(f"{name} must be positive")
    return result


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _position_key(x: int, y: int) -> str:
    return f"{x},{y}"


def _split_position(value: str) -> Tuple[int, int]:
    try:
        x_text, y_text = value.split(",", 1)
        return int(x_text), int(y_text)
    except (AttributeError, ValueError) as exc:
        raise SnapshotValidationError("invalid position key") from exc


@dataclass(frozen=True)
class ColonyConfig:
    """Validated knobs for a reproducible multi-phase simulation."""

    seed: int
    width: int = 24
    height: int = 16
    population: int = 8
    settlement_count: int = 2
    adult_age: int = 5
    fertility_start: int = 5
    fertility_end: int = 30
    max_age: int = 40
    gestation_ticks: int = 4
    settlement_capacity: int = 50
    storage_capacity: int = 100
    perception_radius: int = 4
    affinity_gain: float = 0.12
    consent_threshold: float = 0.55
    hunger_decay: int = 2
    energy_decay: int = 1
    mutation_percent: int = 8
    combat_damage: int = 18
    memory_capacity: int = 24
    memory_ttl: int = 20
    research_failure_percent: int = 0
    ai_enabled: bool = True

    def __post_init__(self) -> None:
        _require_int(self.seed, "seed")
        _positive(self.width, "width")
        _positive(self.height, "height")
        _non_negative(self.population, "population")
        _positive(self.settlement_count, "settlement_count")
        _non_negative(self.adult_age, "adult_age")
        _non_negative(self.fertility_start, "fertility_start")
        if self.fertility_end < self.fertility_start:
            raise ValueError("fertility_end must not precede fertility_start")
        if self.max_age <= self.adult_age:
            raise ValueError("max_age must exceed adult_age")
        _positive(self.gestation_ticks, "gestation_ticks")
        _positive(self.settlement_capacity, "settlement_capacity")
        _positive(self.storage_capacity, "storage_capacity")
        _non_negative(self.perception_radius, "perception_radius")
        if type(self.affinity_gain) not in (int, float) or not math.isfinite(self.affinity_gain):
            raise ValueError("affinity_gain must be finite")
        if not 0 < self.affinity_gain <= 1:
            raise ValueError("affinity_gain must be in (0, 1]")
        if type(self.consent_threshold) not in (int, float) or not math.isfinite(self.consent_threshold):
            raise ValueError("consent_threshold must be finite")
        if not 0 <= self.consent_threshold <= 1:
            raise ValueError("consent_threshold must be in [0, 1]")
        _non_negative(self.hunger_decay, "hunger_decay")
        _non_negative(self.energy_decay, "energy_decay")
        if not _is_int(self.mutation_percent) or not 0 <= self.mutation_percent <= 100:
            raise ValueError("mutation_percent must be in [0, 100]")
        _positive(self.combat_damage, "combat_damage")
        _positive(self.memory_capacity, "memory_capacity")
        _positive(self.memory_ttl, "memory_ttl")
        if not _is_int(self.research_failure_percent) or not 0 <= self.research_failure_percent <= 100:
            raise ValueError("research_failure_percent must be in [0, 100]")
        if type(self.ai_enabled) is not bool:
            raise ValueError("ai_enabled must be a boolean")

    def as_dict(self) -> Dict[str, Any]:
        return {
            "seed": self.seed,
            "width": self.width,
            "height": self.height,
            "population": self.population,
            "settlement_count": self.settlement_count,
            "adult_age": self.adult_age,
            "fertility_start": self.fertility_start,
            "fertility_end": self.fertility_end,
            "max_age": self.max_age,
            "gestation_ticks": self.gestation_ticks,
            "settlement_capacity": self.settlement_capacity,
            "storage_capacity": self.storage_capacity,
            "perception_radius": self.perception_radius,
            "affinity_gain": self.affinity_gain,
            "consent_threshold": self.consent_threshold,
            "hunger_decay": self.hunger_decay,
            "energy_decay": self.energy_decay,
            "mutation_percent": self.mutation_percent,
            "combat_damage": self.combat_damage,
            "memory_capacity": self.memory_capacity,
            "memory_ttl": self.memory_ttl,
            "research_failure_percent": self.research_failure_percent,
            "ai_enabled": self.ai_enabled,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ColonyConfig":
        expected = set(cls.__dataclass_fields__)
        if not isinstance(value, Mapping) or set(value) != expected:
            raise SnapshotValidationError("config has missing or unknown fields")
        try:
            return cls(**dict(value))
        except (TypeError, ValueError) as exc:
            raise SnapshotValidationError(f"invalid colony config: {exc}") from exc


@dataclass(frozen=True)
class Recipe:
    name: str
    inputs: Mapping[str, int]
    output: Mapping[str, int]
    labor_ticks: int

    def __post_init__(self) -> None:
        if not self.name or not isinstance(self.name, str):
            raise ValueError("recipe name must be a non-empty string")
        _positive(self.labor_ticks, "recipe labor_ticks")
        for mapping_name, mapping in (("inputs", self.inputs), ("output", self.output)):
            if not mapping:
                raise ValueError(f"recipe {mapping_name} cannot be empty")
            for good, quantity in mapping.items():
                if not isinstance(good, str) or not good:
                    raise ValueError("recipe goods must be named strings")
                _positive(quantity, f"recipe {mapping_name} quantity")


RECIPES: Dict[str, Recipe] = {
    "bread": Recipe("bread", {"grain": 1}, {"food": 2}, 2),
    "wooden_tool": Recipe("wooden_tool", {"wood": 1}, {"tool": 1}, 2),
    "stone_block": Recipe("stone_block", {"stone": 1}, {"block": 1}, 3),
}


TECHNOLOGIES: Dict[str, Dict[str, Any]] = {
    "agriculture": {"prerequisites": (), "research_ticks": 2, "cost": 4},
    "metalworking": {"prerequisites": ("agriculture",), "research_ticks": 3, "cost": 7},
    "masonry": {"prerequisites": ("agriculture",), "research_ticks": 3, "cost": 6},
}


@dataclass
class AgentState:
    agent_id: str
    settlement_id: str
    sex: str
    age: int
    x: int
    y: int
    health: int = 100
    hunger: int = 100
    energy: int = 100
    alive: bool = True
    genome: Tuple[int, ...] = (50, 50, 50, 50)
    memory: List[Dict[str, Any]] = field(default_factory=list)
    semantic_memory: Dict[str, str] = field(default_factory=dict)
    learned_policy: Dict[str, float] = field(default_factory=dict)
    # Neural policy state is intentionally separate from the biological
    # genome, episodic memory, and scalar telemetry kept for compatibility.
    brain_weights: Tuple[float, ...] = field(default_factory=tuple)
    semantic_memory_ticks: Dict[str, int] = field(default_factory=dict)
    skills: Dict[str, int] = field(default_factory=dict)
    wallet: int = 20
    inventory: Dict[str, int] = field(default_factory=dict)
    affinity: Dict[str, float] = field(default_factory=dict)
    bond_partner_id: Optional[str] = None
    pregnancy_remaining: Optional[int] = None
    pregnancy_partner_id: Optional[str] = None
    pregnancy_partner_genome: Optional[Tuple[int, ...]] = None
    children: List[str] = field(default_factory=list)
    job_id: Optional[str] = None

    @property
    def is_adult(self) -> bool:
        return self.age >= 0 and self.age >= self._adult_age

    _adult_age: int = field(default=5, repr=False, compare=False)

    def is_fertile(self, config: ColonyConfig) -> bool:
        return self.alive and self.sex in {"female", "male"} and config.fertility_start <= self.age <= config.fertility_end

    def position(self) -> Tuple[int, int]:
        return self.x, self.y

    def remember(self, item: Mapping[str, Any], capacity: int = MAX_MEMORY_ITEMS) -> None:
        self.memory.append(dict(item))
        if len(self.memory) > capacity:
            del self.memory[:-capacity]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "settlement_id": self.settlement_id,
            "sex": self.sex,
            "age": self.age,
            "x": self.x,
            "y": self.y,
            "health": self.health,
            "hunger": self.hunger,
            "energy": self.energy,
            "alive": self.alive,
            "genome": list(self.genome),
            "memory": self.memory,
            "semantic_memory": self.semantic_memory,
            "semantic_memory_ticks": self.semantic_memory_ticks,
            "learned_policy": self.learned_policy,
            "brain_weights": list(self.brain_weights),
            "skills": self.skills,
            "wallet": self.wallet,
            "inventory": self.inventory,
            "affinity": self.affinity,
            "bond_partner_id": self.bond_partner_id,
            "pregnancy_remaining": self.pregnancy_remaining,
            "pregnancy_partner_id": self.pregnancy_partner_id,
            "pregnancy_partner_genome": list(self.pregnancy_partner_genome) if self.pregnancy_partner_genome is not None else None,
            "children": self.children,
            "job_id": self.job_id,
            "adult_age": self._adult_age,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "AgentState":
        if not isinstance(value, Mapping):
            raise SnapshotValidationError("agent must be an object")
        try:
            agent = cls(
                agent_id=value["agent_id"],
                settlement_id=value["settlement_id"],
                sex=value["sex"],
                age=value["age"],
                x=value["x"],
                y=value["y"],
                health=value["health"],
                hunger=value["hunger"],
                energy=value["energy"],
                alive=value["alive"],
                genome=tuple(value["genome"]),
                memory=[dict(item) for item in value["memory"]],
                semantic_memory=dict(value["semantic_memory"]),
                semantic_memory_ticks=dict(value.get("semantic_memory_ticks", {})),
                learned_policy=dict(value["learned_policy"]),
                brain_weights=tuple(float(item) for item in value.get("brain_weights", ())),
                skills=dict(value["skills"]),
                wallet=value["wallet"],
                inventory=dict(value["inventory"]),
                affinity={key: float(item) for key, item in value["affinity"].items()},
                bond_partner_id=value["bond_partner_id"],
                pregnancy_remaining=value["pregnancy_remaining"],
                pregnancy_partner_id=value["pregnancy_partner_id"],
                pregnancy_partner_genome=tuple(value["pregnancy_partner_genome"]) if value["pregnancy_partner_genome"] is not None else None,
                children=list(value["children"]),
                job_id=value["job_id"],
                _adult_age=value.get("adult_age", 5),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise SnapshotValidationError(f"invalid agent: {exc}") from exc
        if not isinstance(agent.agent_id, str) or not isinstance(agent.settlement_id, str):
            raise SnapshotValidationError("agent identifiers must be strings")
        if agent.sex not in {"female", "male"}:
            raise SnapshotValidationError("agent sex is invalid")
        for name in ("age", "x", "y", "health", "hunger", "energy", "wallet"):
            if not _is_int(getattr(agent, name)):
                raise SnapshotValidationError(f"agent {name} must be an integer")
        if not agent.alive and agent.health < 0:
            raise SnapshotValidationError("dead agent health cannot be negative")
        if any(not math.isfinite(weight) for weight in agent.brain_weights):
            raise SnapshotValidationError("agent neural weights must be finite")
        return agent


@dataclass
class SettlementState:
    settlement_id: str
    treasury: int = 100
    storage: Dict[str, int] = field(default_factory=dict)
    demand: Dict[str, int] = field(default_factory=dict)
    knowledge: Dict[str, str] = field(default_factory=dict)
    technologies: List[str] = field(default_factory=list)
    territory: List[str] = field(default_factory=list)
    relations: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    learned_policy: Dict[str, float] = field(default_factory=dict)
    brain_weights: Tuple[float, ...] = field(default_factory=tuple)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "settlement_id": self.settlement_id,
            "treasury": self.treasury,
            "storage": self.storage,
            "demand": self.demand,
            "knowledge": self.knowledge,
            "technologies": sorted(self.technologies),
            "territory": sorted(self.territory),
            "relations": {
                relation_id: {
                    **dict(relation),
                    "memory": [dict(item) for item in relation.get("memory", [])],
                }
                for relation_id, relation in sorted(self.relations.items())
            },
            "learned_policy": self.learned_policy,
            "brain_weights": list(self.brain_weights),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SettlementState":
        try:
            state = cls(
                settlement_id=value["settlement_id"],
                treasury=value["treasury"],
                storage=dict(value["storage"]),
                demand=dict(value["demand"]),
                knowledge=dict(value["knowledge"]),
                technologies=list(value["technologies"]),
                territory=list(value["territory"]),
                relations={
                    key: {
                        **dict(item),
                        "memory": [dict(memory) for memory in item.get("memory", [])],
                    }
                    for key, item in value["relations"].items()
                },
                learned_policy={key: float(item) for key, item in value.get("learned_policy", {}).items()},
                brain_weights=tuple(float(item) for item in value.get("brain_weights", ())),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise SnapshotValidationError(f"invalid settlement: {exc}") from exc
        if not isinstance(state.settlement_id, str) or not _is_int(state.treasury) or state.treasury < 0:
            raise SnapshotValidationError("invalid settlement identity or treasury")
        if any(not math.isfinite(weight) for weight in state.brain_weights):
            raise SnapshotValidationError("settlement neural weights must be finite")
        return state


@dataclass
class ProductionJob:
    job_id: str
    settlement_id: str
    agent_id: str
    recipe_name: str
    remaining_ticks: int
    reserved_inputs: Dict[str, int]
    material_cost: int
    labor_cost: int
    started_tick: int

    def as_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "settlement_id": self.settlement_id,
            "agent_id": self.agent_id,
            "recipe_name": self.recipe_name,
            "remaining_ticks": self.remaining_ticks,
            "reserved_inputs": self.reserved_inputs,
            "material_cost": self.material_cost,
            "labor_cost": self.labor_cost,
            "started_tick": self.started_tick,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ProductionJob":
        try:
            job = cls(
                job_id=value["job_id"],
                settlement_id=value["settlement_id"],
                agent_id=value["agent_id"],
                recipe_name=value["recipe_name"],
                remaining_ticks=value["remaining_ticks"],
                reserved_inputs=dict(value["reserved_inputs"]),
                material_cost=value["material_cost"],
                labor_cost=value["labor_cost"],
                started_tick=value["started_tick"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise SnapshotValidationError(f"invalid production job: {exc}") from exc
        if job.recipe_name not in RECIPES or job.remaining_ticks < 0:
            raise SnapshotValidationError("invalid production job recipe or duration")
        return job


@dataclass
class ResearchJob:
    job_id: str
    settlement_id: str
    agent_id: str
    technology: str
    remaining_ticks: int
    started_tick: int

    def as_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "settlement_id": self.settlement_id,
            "agent_id": self.agent_id,
            "technology": self.technology,
            "remaining_ticks": self.remaining_ticks,
            "started_tick": self.started_tick,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ResearchJob":
        try:
            job = cls(
                job_id=value["job_id"],
                settlement_id=value["settlement_id"],
                agent_id=value["agent_id"],
                technology=value["technology"],
                remaining_ticks=value["remaining_ticks"],
                started_tick=value["started_tick"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise SnapshotValidationError(f"invalid research job: {exc}") from exc
        if job.technology not in TECHNOLOGIES or job.remaining_ticks < 0:
            raise SnapshotValidationError("invalid research job technology or duration")
        return job


@dataclass(frozen=True)
class DomainEvent:
    sequence: int
    tick: int
    event_type: str
    payload: Mapping[str, Any]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "sequence": self.sequence,
            "tick": self.tick,
            "event_type": self.event_type,
            "payload": dict(self.payload),
        }


class ColonySimulation:
    """Single-owner deterministic simulation covering all roadmap seams."""

    def __init__(self, config: ColonyConfig) -> None:
        if not isinstance(config, ColonyConfig):
            raise TypeError("config must be ColonyConfig")
        self.config = config
        self.clock = SimulationClock()
        self.random = SeededRandom(config.seed)
        self.agents: Dict[str, AgentState] = {}
        self.settlements: Dict[str, SettlementState] = {}
        self.production_jobs: Dict[str, ProductionJob] = {}
        self.research_jobs: Dict[str, ResearchJob] = {}
        self.events: List[DomainEvent] = []
        self.resources: Dict[str, str] = {}
        self._next_event_sequence = 1
        self._next_job_number = 1
        self._next_research_number = 1
        self._initialize_settlements()
        self._initialize_resources()
        self._initialize_agents()
        self._emit("simulation_initialized", population=config.population)

    @property
    def tick(self) -> int:
        return self.clock.tick

    @property
    def alive_agents(self) -> Tuple[AgentState, ...]:
        return tuple(agent for agent in self.agents.values() if agent.alive)

    @property
    def alive_population(self) -> int:
        return len(self.alive_agents)

    def _initialize_settlements(self) -> None:
        for index in range(self.config.settlement_count):
            settlement_id = f"settlement-{index:03d}"
            settlement = SettlementState(
                settlement_id=settlement_id,
                treasury=100,
                storage={"wood": 10, "grain": 10, "stone": 4, "food": 2},
                brain_weights=self._deterministic_brain_weights(
                    f"settlement:{settlement_id}",
                    SETTLEMENT_INPUT_COUNT,
                    SETTLEMENT_HIDDEN_COUNT,
                    len(SETTLEMENT_ACTIONS),
                ),
            )
            self.settlements[settlement_id] = settlement
        ids = sorted(self.settlements)
        for left in ids:
            for right in ids:
                if left != right:
                    self.settlements[left].relations[right] = {
                        "trust": 0.0,
                        "treaty": "neutral",
                        "memory": [],
                    }

    def _initialize_resources(self) -> None:
        for index in range(max(1, self.config.width // 3)):
            x = (index * 5 + 1) % self.config.width
            y = (index * 7 + 2) % self.config.height
            self.resources[_position_key(x, y)] = "wood"
        for index in range(max(1, self.config.height // 4)):
            x = (index * 7 + 3) % self.config.width
            y = (index * 3 + 5) % self.config.height
            self.resources[_position_key(x, y)] = "grain"

    def _new_brain_weights(
        self,
        input_count: int = NEURAL_INPUT_COUNT,
        hidden_count: int = NEURAL_HIDDEN_COUNT,
        output_count: int = len(AGENT_ACTIONS),
    ) -> Tuple[float, ...]:
        """Create bounded weights from this simulation's owned RNG."""

        weight_count = NNetwork.getTotalWeights(input_count, hidden_count, output_count)
        return tuple(
            round((self.random.randrange(2001) - 1000) / 1000.0, 6)
            for _ in range(weight_count)
        )

    def _deterministic_brain_weights(
        self,
        identity: str,
        input_count: int,
        hidden_count: int,
        output_count: int,
    ) -> Tuple[float, ...]:
        """Create v4 migration weights without consuming the live RNG stream."""

        digest = hashlib.sha256(f"{self.config.seed}:{identity}:neural-v5".encode("utf-8")).digest()
        migration_seed = int.from_bytes(digest[:8], "big", signed=False)
        source = SeededRandom(migration_seed)
        weight_count = NNetwork.getTotalWeights(input_count, hidden_count, output_count)
        return tuple(
            round((source.randrange(2001) - 1000) / 1000.0, 6)
            for _ in range(weight_count)
        )

    def _migrated_brain_weights(self, agent_id: str) -> Tuple[float, ...]:
        return self._deterministic_brain_weights(
            f"agent:{agent_id}", NEURAL_INPUT_COUNT, NEURAL_HIDDEN_COUNT, len(AGENT_ACTIONS)
        )

    def _migrated_settlement_brain_weights(self, settlement_id: str) -> Tuple[float, ...]:
        return self._deterministic_brain_weights(
            f"settlement:{settlement_id}",
            SETTLEMENT_INPUT_COUNT,
            SETTLEMENT_HIDDEN_COUNT,
            len(SETTLEMENT_ACTIONS),
        )

    def _initialize_agents(self) -> None:
        settlement_ids = sorted(self.settlements)
        for index in range(self.config.population):
            settlement_id = settlement_ids[index % len(settlement_ids)]
            local_index = index // len(settlement_ids)
            sex = "female" if local_index % 2 == 0 else "male"
            age = self.config.adult_age + self.random.randrange(
                max(1, self.config.max_age - self.config.adult_age)
            )
            x = self.random.randrange(self.config.width)
            y = self.random.randrange(self.config.height)
            genome = tuple(self.random.randrange(101) for _ in range(4))
            agent_id = f"agent-{index:04d}"
            self.agents[agent_id] = AgentState(
                agent_id=agent_id,
                settlement_id=settlement_id,
                sex=sex,
                age=age,
                x=x,
                y=y,
                genome=genome,
                brain_weights=self._new_brain_weights(),
                _adult_age=self.config.adult_age,
            )

    def _emit(self, event_type: str, **payload: Any) -> DomainEvent:
        event = DomainEvent(self._next_event_sequence, self.tick, event_type, payload)
        self.events.append(event)
        self._next_event_sequence += 1
        return event

    def _agent(self, agent_id: str) -> AgentState:
        try:
            agent = self.agents[agent_id]
        except KeyError as exc:
            raise ValueError(f"unknown agent: {agent_id}") from exc
        if not agent.alive:
            raise ValueError(f"agent is not alive: {agent_id}")
        return agent

    def _settlement(self, settlement_id: str) -> SettlementState:
        try:
            return self.settlements[settlement_id]
        except KeyError as exc:
            raise ValueError(f"unknown settlement: {settlement_id}") from exc

    def _distance(self, first: AgentState, second: AgentState) -> int:
        return abs(first.x - second.x) + abs(first.y - second.y)

    def _is_adult(self, agent: AgentState) -> bool:
        return agent.alive and agent.age >= self.config.adult_age

    def step(self) -> "ColonySimulation":
        self.clock.step()
        self._emit("tick_advanced")
        self._update_needs_and_lifecycle()
        self._decay_memory()
        self._update_perception()
        if self.config.ai_enabled:
            self._run_ai()
        self._update_production()
        self._update_research()
        self._consume_food_for_need()
        self._assert_invariants()
        return self

    def run(self, steps: int) -> "ColonySimulation":
        count = _non_negative(steps, "steps")
        for _ in range(count):
            self.step()
        return self

    @staticmethod
    def _count_events(events: Iterable[DomainEvent]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for event in events:
            counts[event.event_type] = counts.get(event.event_type, 0) + 1
        return dict(sorted(counts.items()))

    def _terminal_reason(self) -> Optional[str]:
        if self.winner() is not None:
            return "winner"
        if self.alive_population == 0:
            return "all_agents_dead"
        return None

    def run_training(
        self,
        generations: int,
        ticks_per_generation: int = 20,
        terminal_mode: str = "diagnostic_stop",
    ) -> Dict[str, Any]:
        """Run sequential headless training windows and return a JSON report.

        The public ``generations`` name is retained for the command-line
        workflow, but each item is a fixed tick window in one continuous
        simulation.  It is intentionally not a biological cohort boundary.

        ``diagnostic_stop`` preserves the short-run terminal behavior. The
        ``continue_after_game_over`` mode is intended for online training and
        executes the requested workload even after a winner is observed.
        """

        window_count = _non_negative(generations, "generations")
        window_ticks = _positive(ticks_per_generation, "ticks_per_generation")
        if terminal_mode not in {"diagnostic_stop", "continue_after_game_over"}:
            raise ValueError("terminal_mode must be diagnostic_stop or continue_after_game_over")
        start_tick = self.tick
        terminal_at_start = self.game_over
        terminal_tick: Optional[int] = self.tick if terminal_at_start else None
        first_terminal_reason: Optional[str] = self._terminal_reason() if terminal_at_start else None
        terminal_winner: Optional[str] = self.winner() if terminal_at_start else None
        windows: List[Dict[str, Any]] = []
        completed_windows = 0

        for window_number in range(1, window_count + 1):
            window_start = self.tick
            event_start = len(self.events)
            for _ in range(window_ticks):
                if terminal_mode == "diagnostic_stop" and self.game_over:
                    break
                self.step()
                if terminal_tick is None and self.game_over:
                    terminal_tick = self.tick
                    first_terminal_reason = self._terminal_reason()
                    terminal_winner = self.winner()

            self._evolve_neural_population(window_number)

            window_end = self.tick
            interval_events = self.events[event_start:]
            interval_event_counts = self._count_events(interval_events)
            cumulative_event_counts = self._count_events(self.events)
            terminal = self.game_over
            actual_ticks = window_end - window_start
            boundary_invariants = self.invariants()
            windows.append(
                {
                    "training_window": window_number,
                    "start_tick": window_start,
                    "end_tick": window_end,
                    "requested_ticks": window_ticks,
                    "actual_ticks": actual_ticks,
                    "alive_population": self.alive_population,
                    "dead_population": boundary_invariants["dead_population"],
                    "births": interval_event_counts.get("child_born", 0),
                    "deaths": interval_event_counts.get("agent_died", 0),
                    "interval_event_count": len(interval_events),
                    "cumulative_event_count": len(self.events),
                    "interval_event_counts": interval_event_counts,
                    "cumulative_event_counts": cumulative_event_counts,
                    "game_over": terminal,
                    "terminal_reason": first_terminal_reason,
                    "terminal_tick": terminal_tick,
                    "terminal_winner": terminal_winner,
                    "post_terminal_ticks": max(0, self.tick - terminal_tick) if terminal_tick is not None else 0,
                    "winner": self.winner(),
                    "invariants": boundary_invariants,
                    "state_hash": self.state_hash(),
                    "event_hash": self.event_hash(),
                    "neural_state_hash": self.neural_state_hash(),
                }
            )
            if actual_ticks == window_ticks:
                completed_windows += 1
            if terminal and terminal_mode == "diagnostic_stop":
                break

        final_invariants = self.invariants()
        final_event_counts = self._count_events(self.events)
        executed_windows = len(windows)
        final_metrics = {
            "tick": self.tick,
            "executed_ticks": self.tick - start_tick,
            "alive_population": self.alive_population,
            "dead_population": final_invariants["dead_population"],
            "births_total": final_event_counts.get("child_born", 0),
            "deaths_total": final_event_counts.get("agent_died", 0),
            "event_count": len(self.events),
            "event_counts": final_event_counts,
            "game_over": self.game_over,
            "terminal_tick": terminal_tick,
            "terminal_winner": terminal_winner,
            "post_terminal_ticks": max(0, self.tick - terminal_tick) if terminal_tick is not None else 0,
            "invariants": final_invariants,
            "state_hash": self.state_hash(),
            "event_hash": self.event_hash(),
            "neural_state_hash": self.neural_state_hash(),
        }
        return {
            "report_schema_version": 1,
            "mode": "headless_training",
            "effective_config": self.config.as_dict(),
            "terminal_mode": terminal_mode,
            "terminal_at_start": terminal_at_start,
            "terminal_reached": terminal_tick is not None,
            "terminal_tick": terminal_tick,
            "terminal_winner": terminal_winner,
            "post_terminal_ticks": max(0, self.tick - terminal_tick) if terminal_tick is not None else 0,
            "requested_generations": window_count,
            "ticks_per_generation": window_ticks,
            "executed_generations": executed_windows,
            "completed_generations": completed_windows,
            "unexecuted_generations": window_count - executed_windows,
            "executed_ticks": self.tick - start_tick,
            "game_over": self.game_over,
            "terminal_reason": first_terminal_reason,
            "winner": self.winner(),
            "windows": windows,
            "final_metrics": final_metrics,
            "state_hash": self.state_hash(),
            "event_hash": self.event_hash(),
            "neural_state_hash": self.neural_state_hash(),
        }

    def _agent_fitness(self, agent: AgentState) -> float:
        """Return an observable fitness signal for policy selection."""

        return (
            agent.health / 100.0
            + agent.hunger / 100.0
            + agent.energy / 100.0
            + min(1.0, sum(agent.skills.values()) / 10.0)
            + min(1.0, len(agent.children) / 4.0)
        )

    def _evolve_neural_population(self, generation: int) -> None:
        """Select, cross, and mutate resident policies at a training boundary."""

        for settlement_id in sorted(self.settlements):
            residents = sorted(
                (
                    agent
                    for agent in self.alive_agents
                    if agent.settlement_id == settlement_id and self._is_adult(agent)
                ),
                key=lambda agent: (-self._agent_fitness(agent), agent.agent_id),
            )
            if len(residents) < 2:
                continue
            elite_count = max(1, ceil(len(residents) * 0.6))
            elites = residents[:elite_count]
            for agent in residents[elite_count:]:
                first = self.random.choice(elites)
                second = self.random.choice(elites)
                old_weights = agent.brain_weights
                agent.brain_weights = self._inherit_brain(first, second)
                self._emit(
                    "genetic_policy_evolved",
                    settlement_id=settlement_id,
                    generation=generation,
                    agent_id=agent.agent_id,
                    parent_ids=[first.agent_id, second.agent_id],
                    fitness=round(self._agent_fitness(agent), 6),
                    weight_delta=round(
                        sum(abs(float(new) - float(old)) for new, old in zip(agent.brain_weights, old_weights)),
                        8,
                    ),
                )

    def _update_needs_and_lifecycle(self) -> None:
        for agent_id in sorted(self.agents):
            agent = self.agents[agent_id]
            if not agent.alive:
                continue
            agent.age += 1
            agent.hunger = max(0, agent.hunger - self.config.hunger_decay)
            agent.energy = max(0, agent.energy - self.config.energy_decay)
            if agent.hunger == 0:
                agent.health = max(0, agent.health - 2)
                self._emit("need_critical", agent_id=agent_id, need="hunger")
            if agent.age > self.config.max_age or agent.health <= 0:
                self._kill_agent(agent, "old_age" if agent.age > self.config.max_age else "health")
                continue
            if agent.pregnancy_remaining is not None:
                agent.pregnancy_remaining -= 1
                if agent.pregnancy_remaining <= 0:
                    self._birth(agent)

    def _update_perception(self) -> None:
        radius = self.config.perception_radius
        for agent in sorted(self.alive_agents, key=lambda item: item.agent_id):
            # A newborn's first state is an explicit empty-memory boundary;
            # perception starts on its first subsequent tick.
            if agent.age == 0:
                continue
            for other in sorted(self.alive_agents, key=lambda item: item.agent_id):
                if agent.agent_id == other.agent_id or self._distance(agent, other) > radius:
                    continue
                agent.remember({"tick": self.tick, "kind": "agent_observed", "subject": other.agent_id}, self.config.memory_capacity)
                agent.semantic_memory[f"agent:{other.agent_id}"] = other.settlement_id
                agent.semantic_memory_ticks[f"agent:{other.agent_id}"] = self.tick
                self._emit("observation_recorded", agent_id=agent.agent_id, subject_id=other.agent_id)
            for position, resource in sorted(self.resources.items()):
                x, y = _split_position(position)
                if abs(agent.x - x) + abs(agent.y - y) <= radius:
                    agent.remember({"tick": self.tick, "kind": "resource_observed", "subject": position, "resource": resource}, self.config.memory_capacity)
                    agent.semantic_memory[f"resource:{position}"] = resource
                    agent.semantic_memory_ticks[f"resource:{position}"] = self.tick
                    self._emit("observation_recorded", agent_id=agent.agent_id, subject_id=position)

    def _move_agent(self, agent: AgentState) -> None:
        """Apply one movement decision selected by the resident policy."""

        directions = (
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
        remembered_positions = []
        for fact, resource in agent.semantic_memory.items():
            if not fact.startswith("resource:"):
                continue
            position = fact.split(":", 1)[1]
            if position not in self.resources or resource != self.resources[position]:
                continue
            x, y = _split_position(position)
            remembered_positions.append((abs(agent.x - x) + abs(agent.y - y), x, y))
        if remembered_positions:
            _, target_x, target_y = min(remembered_positions)
            dx = 0 if target_x == agent.x else 1 if target_x > agent.x else -1
            dy = 0 if target_y == agent.y else 1 if target_y > agent.y else -1
        else:
            dx, dy = self.random.choice(directions)
        old_position = agent.position()
        agent.x = min(max(agent.x + dx, 0), self.config.width - 1)
        agent.y = min(max(agent.y + dy, 0), self.config.height - 1)
        if old_position != agent.position():
            self._emit("agent_moved", agent_id=agent.agent_id, from_position=old_position, to_position=agent.position())

    def _decay_memory(self) -> None:
        for agent in self.alive_agents:
            agent.memory = [
                item
                for item in agent.memory
                if _is_int(item.get("tick")) and self.tick - item["tick"] < self.config.memory_ttl
            ]
            for fact, recorded_tick in list(agent.semantic_memory_ticks.items()):
                if not _is_int(recorded_tick) or self.tick - recorded_tick >= self.config.memory_ttl:
                    agent.semantic_memory_ticks.pop(fact, None)
                    agent.semantic_memory.pop(fact, None)

    def _update_relationships(self) -> None:
        adults = [agent for agent in self.alive_agents if self._is_adult(agent)]
        for index, first in enumerate(adults):
            for second in adults[index + 1 :]:
                if first.settlement_id != second.settlement_id or self._distance(first, second) > self.config.perception_radius:
                    continue
                self.interact(first.agent_id, second.agent_id, "proximity")
                if first.bond_partner_id is None and second.bond_partner_id is None:
                    if self._consent_score(first, second) >= self.config.consent_threshold and self._consent_score(second, first) >= self.config.consent_threshold:
                        self.courtship(first.agent_id, second.agent_id)
                if (
                    first.bond_partner_id == second.agent_id
                    and second.bond_partner_id == first.agent_id
                    and first.pregnancy_remaining is None
                    and second.pregnancy_remaining is None
                    and first.sex != second.sex
                ):
                    self.request_reproduction(first.agent_id, second.agent_id)

    def _update_production(self) -> None:
        for job_id in sorted(list(self.production_jobs)):
            job = self.production_jobs.get(job_id)
            if job is None:
                continue
            agent = self.agents.get(job.agent_id)
            settlement = self.settlements[job.settlement_id]
            if agent is None or not agent.alive:
                for good, quantity in job.reserved_inputs.items():
                    settlement.storage[good] = settlement.storage.get(good, 0) + quantity
                if agent is not None:
                    agent.job_id = None
                del self.production_jobs[job_id]
                self._emit("production_cancelled", job_id=job_id, reason="worker_unavailable")
                continue
            if agent.energy <= 0:
                self._emit("production_paused", job_id=job_id, reason="worker_exhausted")
                continue
            agent.energy = max(0, agent.energy - 1)
            job.remaining_ticks -= 1
            self._emit("production_progressed", job_id=job_id, remaining_ticks=job.remaining_ticks)
            if job.remaining_ticks > 0:
                continue
            recipe = self._effective_recipe(settlement, job.recipe_name)
            for good, quantity in recipe.output.items():
                settlement.storage[good] = settlement.storage.get(good, 0) + quantity
            agent.job_id = None
            agent.skills[job.recipe_name] = agent.skills.get(job.recipe_name, 0) + 1
            agent.learned_policy[job.recipe_name] = min(1.0, agent.learned_policy.get(job.recipe_name, 0.0) + 0.1)
            del self.production_jobs[job_id]
            self._emit(
                "production_completed",
                job_id=job_id,
                recipe=job.recipe_name,
                output=dict(recipe.output),
                material_cost=job.material_cost,
                labor_cost=job.labor_cost,
            )
            self._emit("skill_learned", agent_id=agent.agent_id, skill=job.recipe_name)

    def _update_research(self) -> None:
        for job_id in sorted(list(self.research_jobs)):
            job = self.research_jobs[job_id]
            agent = self.agents.get(job.agent_id)
            if agent is None or not agent.alive:
                del self.research_jobs[job_id]
                self._emit("research_cancelled", job_id=job_id, reason="researcher_unavailable")
                continue
            if agent.energy <= 0:
                self._emit("research_paused", job_id=job_id, reason="researcher_exhausted")
                continue
            agent.energy = max(0, agent.energy - 1)
            job.remaining_ticks -= 1
            self._emit("research_progressed", job_id=job_id, remaining_ticks=job.remaining_ticks)
            if job.remaining_ticks > 0:
                continue
            settlement = self.settlements[job.settlement_id]
            if self.random.randrange(100) < self.config.research_failure_percent:
                del self.research_jobs[job_id]
                self._emit(
                    "research_failed",
                    job_id=job_id,
                    settlement_id=job.settlement_id,
                    technology=job.technology,
                    reason="experiment_failed",
                )
                continue
            if job.technology not in settlement.technologies:
                settlement.technologies.append(job.technology)
                settlement.technologies.sort()
            del self.research_jobs[job_id]
            self._emit("research_succeeded", job_id=job_id, settlement_id=job.settlement_id, technology=job.technology)
            self._emit("technology_unlocked", settlement_id=job.settlement_id, technology=job.technology)

    def _consume_food_for_need(self) -> None:
        for agent in sorted(self.alive_agents, key=lambda item: item.agent_id):
            if agent.hunger >= 45:
                continue
            settlement = self.settlements[agent.settlement_id]
            source = "settlement"
            if settlement.storage.get("food", 0) <= 0 and agent.inventory.get("food", 0) > 0:
                source = "inventory"
            if (settlement.storage.get("food", 0) if source == "settlement" else agent.inventory.get("food", 0)) <= 0:
                self._emit("need_unmet", agent_id=agent.agent_id, need="food")
                continue
            if source == "settlement":
                settlement.storage["food"] -= 1
            else:
                agent.inventory["food"] -= 1
            agent.hunger = min(100, agent.hunger + 35)
            self._emit("need_met", agent_id=agent.agent_id, need="food", source=source)

    def _run_ai(self) -> None:
        """Let agents and settlements select actions from current state."""

        self._run_agent_ai()
        self._update_relationships()
        self._run_settlement_ai()

    def _run_agent_ai(self) -> None:
        for agent in sorted(self.alive_agents, key=lambda item: item.agent_id):
            if agent.age == 0:
                # Birth is an observable empty-state boundary.  Caregivers may
                # act on a newborn, but the newborn learns on later ticks.
                continue
            observation = self._agent_brain_inputs(agent)
            brain = NNetwork(
                NEURAL_INPUT_COUNT,
                NEURAL_HIDDEN_COUNT,
                len(AGENT_ACTIONS),
                weights=agent.brain_weights,
            )
            probabilities = brain.predict(observation)
            # The network chooses; the world only masks actions that have no
            # possible target or resource. This keeps invalid actions from
            # dominating early learning without scripting a preferred story.
            selectable = probabilities.copy()
            if not any(
                child_id in self.agents
                and self.agents[child_id].alive
                and self.agents[child_id].age < self.config.adult_age
                and self._distance(agent, self.agents[child_id]) <= self.config.perception_radius
                for child_id in agent.children
            ):
                selectable[AGENT_ACTIONS.index("care")] = 0.0
            if not any(
                other.agent_id != agent.agent_id
                and other.alive
                and other.settlement_id == agent.settlement_id
                for other in self.alive_agents
            ):
                selectable[AGENT_ACTIONS.index("socialize")] = 0.0
            if agent.job_id is not None or self._best_recipe_for(agent) is None:
                selectable[AGENT_ACTIONS.index("produce")] = 0.0
            total_probability = float(selectable.sum())
            if total_probability <= 0:
                selectable[AGENT_ACTIONS.index("move")] = 1.0
                total_probability = 1.0
            probabilities = selectable / total_probability
            action_index = max(
                range(len(AGENT_ACTIONS)),
                key=lambda index: (float(probabilities[index]), AGENT_ACTIONS[index]),
            )
            action = AGENT_ACTIONS[action_index]
            probability_map = {
                name: round(float(probabilities[index]), 6)
                for index, name in enumerate(AGENT_ACTIONS)
            }
            self._emit(
                "agent_decision",
                agent_id=agent.agent_id,
                action=action,
                scores=probability_map,
                probabilities=[probability_map[name] for name in AGENT_ACTIONS],
                policy="neural_network",
            )
            reward = self._apply_agent_action(agent, action)
            old_weights = brain.get_weights()
            brain.learn(observation, action_index, reward)
            new_weights = brain.get_weights()
            agent.brain_weights = tuple(round(float(value), 8) for value in new_weights)
            previous = agent.learned_policy.get(action, 0.0)
            updated = _clamp(previous + 0.2 * (reward - previous), -1.0, 1.0)
            agent.learned_policy[action] = round(updated, 6)
            self._emit(
                "learning_updated",
                agent_id=agent.agent_id,
                action=action,
                reward=round(reward, 4),
                value=agent.learned_policy[action],
                network=True,
                weight_delta=round(sum(abs(float(new) - float(old)) for new, old in zip(new_weights, old_weights)), 8),
            )

    def _agent_brain_inputs(self, agent: AgentState) -> Tuple[float, ...]:
        """Return the fixed observation vector consumed by a resident brain."""

        settlement = self.settlements[agent.settlement_id]
        nearby_adults = sum(
            1
            for other in self.alive_agents
            if other.agent_id != agent.agent_id
            and other.settlement_id == agent.settlement_id
            and self._is_adult(other)
            and self._distance(agent, other) <= self.config.perception_radius
        )
        max_affinity = max(
            (value for value in agent.affinity.values() if math.isfinite(value)),
            default=0.0,
        )
        return (
            round(agent.hunger / 100.0, 6),
            round(agent.energy / 100.0, 6),
            round(agent.health / 100.0, 6),
            round(min(1.0, len(agent.memory) / max(1, self.config.memory_capacity)), 6),
            round(min(1.0, nearby_adults / 4.0), 6),
            round(min(1.0, settlement.storage.get("food", 0) / 20.0), 6),
            round(min(1.0, settlement.storage.get("grain", 0) / 20.0), 6),
            1.0 if agent.job_id is not None else 0.0,
            round(_clamp(max_affinity, -1.0, 1.0), 6),
            round(min(1.0, len(settlement.technologies) / max(1, len(TECHNOLOGIES))), 6),
        )

    def _agent_action_scores(self, agent: AgentState) -> Dict[str, float]:
        same_settlement_adults = [
            other for other in self.alive_agents
            if other.agent_id != agent.agent_id and other.settlement_id == agent.settlement_id and self._is_adult(other)
        ]
        settlement = self.settlements[agent.settlement_id]
        scores = {
            "move": 0.35 + agent.genome[2] / 500 + (0.45 if agent.job_id is None else 0.0),
            "produce": 0.25 + agent.genome[0] / 500,
            "socialize": 0.15 + (0.35 if same_settlement_adults else 0.0) + agent.affinity.get(agent.bond_partner_id or "", 0.0) * 0.2,
            "care": 0.1 + (0.6 if any(child_id in agent.children for child_id in self.agents) else 0.0),
            "trade": 0.1 + max(0, 50 - agent.hunger) / 50 + max(0, 3 - settlement.storage.get("food", 0)) * 0.1,
            "learn": 0.2 + (0.4 if agent.memory else 0.0) + agent.genome[3] / 500,
        }
        for action, value in agent.learned_policy.items():
            if action in scores:
                scores[action] += value * 0.25
        if agent.job_id is not None:
            scores["produce"] = -1.0
        return scores

    def _apply_agent_action(self, agent: AgentState, action: str) -> float:
        if action == "move":
            self._move_agent(agent)
            return 0.35
        if action == "produce":
            if agent.job_id is not None:
                return -0.1
            recipe_name = self._best_recipe_for(agent)
            if recipe_name and self.start_production(agent.agent_id, recipe_name):
                return 0.6
            return -0.1
        if action == "socialize":
            candidates = [
                other for other in self.alive_agents
                if other.agent_id != agent.agent_id and other.settlement_id == agent.settlement_id
            ]
            if candidates:
                other = min(candidates, key=lambda item: (self._distance(agent, item), item.agent_id))
                return self.interact(agent.agent_id, other.agent_id, "ai_conversation")
            return 0.0
        if action == "care":
            before = agent.energy
            self._update_childcare_for(agent)
            return 0.4 if agent.energy < before else 0.0
        if action == "trade":
            settlement = self.settlements[agent.settlement_id]
            self.record_demand(settlement.settlement_id, "food", 1)
            return 0.25 if self.buy_good(agent.agent_id, settlement.settlement_id, "food", 1) else -0.05
        if action == "learn":
            self.learn(agent.agent_id, "adaptation", 1)
            return 0.3
        return 0.1

    def _update_childcare_for(self, parent: AgentState) -> None:
        for child_id in parent.children:
            child = self.agents.get(child_id)
            if child is None or not child.alive or child.age >= self.config.adult_age:
                continue
            if child.settlement_id == parent.settlement_id and self._distance(parent, child) <= self.config.perception_radius:
                child.hunger = min(100, child.hunger + 3)
                parent.energy = max(0, parent.energy - 1)
                self._emit("childcare_provided", parent_id=parent.agent_id, child_id=child_id)

    def _best_recipe_for(self, agent: AgentState) -> Optional[str]:
        settlement = self.settlements[agent.settlement_id]
        candidates: List[Tuple[float, str]] = []
        for recipe_name, recipe in RECIPES.items():
            if any(settlement.storage.get(good, 0) < quantity for good, quantity in recipe.inputs.items()):
                continue
            effective = self._effective_recipe(settlement, recipe_name)
            shortage = sum(max(0, 4 - settlement.storage.get(good, 0)) + settlement.demand.get(good, 0) for good in effective.output)
            candidates.append((shortage + agent.skills.get(recipe_name, 0) * 0.25, recipe_name))
        return max(candidates, key=lambda item: (item[0], item[1]))[1] if candidates else None

    def _settlement_brain_inputs(self, settlement_id: str) -> Tuple[float, ...]:
        settlement = self.settlements[settlement_id]
        population = self._settlement_population(settlement_id)
        food_shortage = max(0, population * 2 - settlement.storage.get("food", 0))
        storage_load = sum(settlement.storage.values())
        relation_trust = [
            float(relation.get("trust", 0.0))
            for relation in settlement.relations.values()
            if math.isfinite(float(relation.get("trust", 0.0)))
        ]
        active_jobs = sum(
            1
            for job in self.production_jobs.values()
            if job.settlement_id == settlement_id
        ) + sum(
            1
            for job in self.research_jobs.values()
            if job.settlement_id == settlement_id
        )
        return (
            round(min(1.0, food_shortage / max(1, population * 2)), 6),
            round(min(1.0, population / max(1, self.config.settlement_capacity)), 6),
            round(min(1.0, settlement.treasury / 200.0), 6),
            round(min(1.0, storage_load / max(1, self.config.storage_capacity)), 6),
            round(min(1.0, len(settlement.technologies) / max(1, len(TECHNOLOGIES))), 6),
            round(min(1.0, len(settlement.territory) / max(1, self.config.width * self.config.height)), 6),
            round(min(1.0, active_jobs / 8.0), 6),
            round(_clamp(statistics.mean(relation_trust) if relation_trust else 0.0, -1.0, 1.0), 6),
        )

    def _settlement_has_migration_target(self, settlement_id: str) -> bool:
        current = self.settlements[settlement_id]
        population = self._settlement_population(settlement_id)
        shortage = max(0, population * 2 - current.storage.get("food", 0))
        if shortage <= 0 or population <= 1:
            return False
        return any(
            target_id != settlement_id
            and current.relations[target_id].get("treaty") != "war"
            and target.storage.get("food", 0) - self._settlement_population(target_id) * 2 > 0
            and self._settlement_population(target_id) < self.config.settlement_capacity
            for target_id, target in self.settlements.items()
        )

    def _run_settlement_ai(self) -> None:
        ids = sorted(self.settlements)
        for settlement_id in ids:
            settlement = self.settlements[settlement_id]
            population = self._settlement_population(settlement_id)
            food_shortage = max(0, population * 2 - settlement.storage.get("food", 0))
            observation = self._settlement_brain_inputs(settlement_id)
            brain = NNetwork(
                SETTLEMENT_INPUT_COUNT,
                SETTLEMENT_HIDDEN_COUNT,
                len(SETTLEMENT_ACTIONS),
                weights=settlement.brain_weights,
            )
            probabilities = brain.predict(observation)
            selectable = probabilities.copy()
            research_available = (
                self.research_jobs_for(settlement_id) is None
                and self._next_research_target(settlement) is not None
                and any(
                    self._is_adult(agent)
                    and agent.settlement_id == settlement_id
                    and agent.job_id is None
                    for agent in self.alive_agents
                )
            )
            production_available = any(
                self._is_adult(agent)
                and agent.settlement_id == settlement_id
                and agent.job_id is None
                and self._best_recipe_for(agent) is not None
                for agent in self.alive_agents
            )
            migration_available = self._settlement_has_migration_target(settlement_id)
            trade_available = any(
                relation.get("treaty") in {"trade", "alliance"}
                for relation in settlement.relations.values()
            )
            diplomacy_available = any(
                relation.get("treaty") == "neutral"
                for relation in settlement.relations.values()
            )
            if not research_available:
                selectable[SETTLEMENT_ACTIONS.index("research")] = 0.0
            if not production_available:
                selectable[SETTLEMENT_ACTIONS.index("produce")] = 0.0
            if not migration_available:
                selectable[SETTLEMENT_ACTIONS.index("migrate")] = 0.0
            if not trade_available:
                selectable[SETTLEMENT_ACTIONS.index("trade")] = 0.0
            if not diplomacy_available:
                selectable[SETTLEMENT_ACTIONS.index("diplomacy")] = 0.0
            if food_shortage and migration_available and not production_available and not trade_available:
                # In a resource-empty settlement, migration is the only
                # feasible survival response. The network still decides in
                # every ordinary state; this is an environmental action mask.
                for unavailable_survival_action in ("research", "observe", "diplomacy"):
                    selectable[SETTLEMENT_ACTIONS.index(unavailable_survival_action)] = 0.0
            total_probability = float(selectable.sum())
            if total_probability <= 0:
                selectable[SETTLEMENT_ACTIONS.index("observe")] = 1.0
                total_probability = 1.0
            probabilities = selectable / total_probability
            action_index = max(
                range(len(SETTLEMENT_ACTIONS)),
                key=lambda index: (float(probabilities[index]), SETTLEMENT_ACTIONS[index]),
            )
            action = SETTLEMENT_ACTIONS[action_index]
            probability_map = {
                name: round(float(probabilities[index]), 6)
                for index, name in enumerate(SETTLEMENT_ACTIONS)
            }
            self._emit(
                "settlement_decision",
                settlement_id=settlement_id,
                action=action,
                food_shortage=food_shortage,
                scores=probability_map,
                probabilities=[probability_map[name] for name in SETTLEMENT_ACTIONS],
                policy="neural_network",
            )
            reward = 0.05
            if action == "produce":
                if food_shortage:
                    self.record_demand(settlement_id, "food", max(1, food_shortage))
                self.allocate_jobs(settlement_id)
                reward = 0.4 if food_shortage else 0.1
            elif action == "research":
                researcher = next(
                    (
                        agent
                        for agent in sorted(self.alive_agents, key=lambda item: item.agent_id)
                        if agent.settlement_id == settlement_id
                        and self._is_adult(agent)
                        and agent.job_id is None
                    ),
                    None,
                )
                technology = self._next_research_target(settlement)
                if researcher is not None and technology is not None:
                    self.start_research(researcher.agent_id, technology)
                    reward = 0.4
                else:
                    reward = -0.05
            elif action == "migrate":
                before_population = population
                self._run_ai_migration(settlement_id)
                reward = 0.3 if self._settlement_population(settlement_id) < before_population else -0.05
            elif action == "trade":
                reward = 0.2
            elif action == "diplomacy":
                target_id = next(
                    (
                        target_id
                        for target_id, relation in sorted(settlement.relations.items())
                        if relation.get("treaty") == "neutral"
                    ),
                    None,
                )
                reward = 0.2 if target_id is not None and self.negotiate(settlement_id, target_id, "trade") else -0.05
            old_weights = brain.get_weights()
            brain.learn(observation, action_index, reward)
            new_weights = brain.get_weights()
            settlement.brain_weights = tuple(round(float(value), 8) for value in new_weights)
            previous = settlement.learned_policy.get(action, 0.0)
            settlement.learned_policy[action] = round(_clamp(previous + 0.15 * (reward - previous), -1.0, 1.0), 6)
            self._emit(
                "settlement_learning_updated",
                settlement_id=settlement_id,
                action=action,
                reward=round(reward, 4),
                value=settlement.learned_policy[action],
                network=True,
                weight_delta=round(sum(abs(float(new) - float(old)) for new, old in zip(new_weights, old_weights)), 8),
            )
            for agent in sorted(self.alive_agents, key=lambda item: item.agent_id):
                if agent.settlement_id == settlement_id:
                    self.claim_territory(settlement_id, agent.x, agent.y)
                    break
        for index, first_id in enumerate(ids):
            for second_id in ids[index + 1 :]:
                relation = self.settlements[first_id].relations[second_id]
                if relation["treaty"] == "war":
                    self.resolve_conflict(first_id, second_id)
                    continue
                if self.tick % 5 == 0:
                    first_score = self._settlement_strength(first_id)
                    second_score = self._settlement_strength(second_id)
                    if self.tick >= 20 and abs(first_score - second_score) >= 3:
                        attacker = first_id if first_score > second_score else second_id
                        defender = second_id if attacker == first_id else first_id
                        self.declare_conflict(attacker, defender)
                    elif relation["treaty"] == "neutral":
                        self.negotiate(first_id, second_id, "trade")
                relation = self.settlements[first_id].relations[second_id]
                if relation["treaty"] in {"trade", "alliance"}:
                    self._run_ai_exchange(first_id, second_id)
                    self._run_ai_diffusion(first_id, second_id)

    def _run_ai_exchange(self, first_id: str, second_id: str) -> None:
        """Let a treaty-connected pair react to a real food imbalance."""

        settlements = self.settlements
        candidates = ((first_id, second_id), (second_id, first_id))
        for buyer_id, seller_id in candidates:
            buyer_settlement = settlements[buyer_id]
            seller_settlement = settlements[seller_id]
            buyer_need = max(0, self._settlement_population(buyer_id) * 2 - buyer_settlement.storage.get("food", 0))
            seller_surplus = seller_settlement.storage.get("food", 0) - self._settlement_population(seller_id)
            if buyer_need <= 0 or seller_surplus <= 0:
                continue
            buyer = next(
                (
                    agent
                    for agent in sorted(self.alive_agents, key=lambda item: item.agent_id)
                    if agent.settlement_id == buyer_id and self._is_adult(agent)
                ),
                None,
            )
            if buyer is None:
                continue
            self.record_demand(buyer_id, "food", 1)
            if self.buy_good(buyer.agent_id, seller_id, "food", 1):
                self._emit(
                    "settlement_trade_decision",
                    buyer_settlement_id=buyer_id,
                    seller_settlement_id=seller_id,
                    good="food",
                    reason="food_imbalance",
                )
                return

    def _run_ai_diffusion(self, first_id: str, second_id: str) -> None:
        """Share one useful technology when diplomacy makes it available."""

        first = self.settlements[first_id]
        second = self.settlements[second_id]
        for source_id, target_id in ((first_id, second_id), (second_id, first_id)):
            source = self.settlements[source_id]
            target = self.settlements[target_id]
            for technology in sorted(source.technologies):
                if technology not in target.technologies and self.share_technology(source_id, target_id, technology):
                    self._emit(
                        "settlement_knowledge_decision",
                        source_settlement_id=source_id,
                        target_settlement_id=target_id,
                        knowledge=f"technology:{technology}",
                    )
                    return

    def _run_ai_migration(self, settlement_id: str) -> None:
        """Move one resident toward a treaty-compatible settlement with food surplus."""

        current = self.settlements[settlement_id]
        population = self._settlement_population(settlement_id)
        shortage = max(0, population * 2 - current.storage.get("food", 0))
        if shortage <= 0 or population <= 1:
            return
        targets = []
        for target_id, target in sorted(self.settlements.items()):
            if target_id == settlement_id:
                continue
            relation = current.relations[target_id]
            surplus = target.storage.get("food", 0) - self._settlement_population(target_id) * 2
            if relation["treaty"] != "war" and surplus > 0 and self._settlement_population(target_id) < self.config.settlement_capacity:
                targets.append((-surplus, target_id))
        if not targets:
            return
        migrant = next(
            (
                agent
                for agent in sorted(self.alive_agents, key=lambda item: item.agent_id, reverse=True)
                if agent.settlement_id == settlement_id
                and self._is_adult(agent)
                and agent.job_id is None
                and agent.pregnancy_remaining is None
            ),
            None,
        )
        if migrant is None:
            return
        _, target_id = min(targets)
        if self.migrate(migrant.agent_id, target_id):
            self._emit(
                "settlement_migration_decision",
                settlement_id=settlement_id,
                agent_id=migrant.agent_id,
                target_settlement_id=target_id,
                reason="food_shortage",
            )

    def research_jobs_for(self, settlement_id: str) -> Optional[ResearchJob]:
        return next((job for job in self.research_jobs.values() if job.settlement_id == settlement_id), None)

    def _next_research_target(self, settlement: SettlementState) -> Optional[str]:
        for technology, details in TECHNOLOGIES.items():
            if technology not in settlement.technologies and all(item in settlement.technologies for item in details["prerequisites"]):
                return technology
        return None

    def _settlement_strength(self, settlement_id: str) -> int:
        settlement = self.settlements[settlement_id]
        population = self._settlement_population(settlement_id)
        genome_strength = sum(agent.genome[0] for agent in self.alive_agents if agent.settlement_id == settlement_id) // 40
        return population * 2 + settlement.treasury // 20 + len(settlement.technologies) * 3 + len(settlement.territory) + genome_strength

    def winner(self) -> Optional[str]:
        active = [settlement_id for settlement_id in sorted(self.settlements) if self._settlement_population(settlement_id) > 0]
        return active[0] if len(active) == 1 else None

    @property
    def game_over(self) -> bool:
        return self.winner() is not None or self.alive_population == 0

    def run_until_winner(self, max_steps: int = 1000) -> Optional[str]:
        limit = _positive(max_steps, "max_steps")
        for _ in range(limit):
            if self.game_over:
                return self.winner()
            self.step()
        return self.winner()

    def interact(self, first_id: str, second_id: str, interaction: str = "conversation") -> float:
        first = self._agent(first_id)
        second = self._agent(second_id)
        if first_id == second_id:
            raise ValueError("an agent cannot interact with itself")
        distance_factor = 1.0 if self._distance(first, second) <= self.config.perception_radius else 0.25
        compatibility = self._compatibility(first, second)
        gain = self.config.affinity_gain * distance_factor * (0.5 + compatibility / 2)
        first.affinity[second_id] = _clamp(first.affinity.get(second_id, 0.0) + gain)
        second.affinity[first_id] = _clamp(second.affinity.get(first_id, 0.0) + gain)
        first.remember({"tick": self.tick, "kind": "interaction", "subject": second_id, "interaction": interaction})
        second.remember({"tick": self.tick, "kind": "interaction", "subject": first_id, "interaction": interaction})
        self._emit("interaction", first_id=first_id, second_id=second_id, interaction=interaction, gain=round(gain, 6))
        return gain

    def _compatibility(self, first: AgentState, second: AgentState) -> float:
        return 1.0 - sum(abs(a - b) for a, b in zip(first.genome, second.genome)) / (len(first.genome) * 100)

    def _consent_score(self, chooser: AgentState, partner: AgentState) -> float:
        affinity = chooser.affinity.get(partner.agent_id, 0.0)
        compatibility = self._compatibility(chooser, partner)
        health = chooser.health / 100
        return _clamp(0.5 * affinity + 0.3 * compatibility + 0.2 * health)

    def courtship(self, initiator_id: str, target_id: str) -> bool:
        initiator = self._agent(initiator_id)
        target = self._agent(target_id)
        if not self._is_adult(initiator) or not self._is_adult(target):
            self._emit("courtship_rejected", initiator_id=initiator_id, target_id=target_id, reason="adult_required")
            return False
        if initiator.settlement_id != target.settlement_id:
            self._emit("courtship_rejected", initiator_id=initiator_id, target_id=target_id, reason="different_settlement")
            return False
        initiator_score = self._consent_score(initiator, target)
        target_score = self._consent_score(target, initiator)
        if initiator_score < self.config.consent_threshold or target_score < self.config.consent_threshold:
            self._emit(
                "courtship_rejected",
                initiator_id=initiator_id,
                target_id=target_id,
                reason="consent",
                initiator_score=round(initiator_score, 6),
                target_score=round(target_score, 6),
            )
            return False
        initiator.bond_partner_id = target_id
        target.bond_partner_id = initiator_id
        self._emit("pair_bonded", first_id=initiator_id, second_id=target_id)
        return True

    def request_reproduction(self, first_id: str, second_id: str) -> bool:
        first = self._agent(first_id)
        second = self._agent(second_id)
        if not self._is_adult(first) or not self._is_adult(second) or not first.is_fertile(self.config) or not second.is_fertile(self.config):
            self._emit("reproduction_rejected", first_id=first_id, second_id=second_id, reason="fertility")
            return False
        if first.bond_partner_id != second_id or second.bond_partner_id != first_id:
            self._emit("reproduction_rejected", first_id=first_id, second_id=second_id, reason="mutual_bond_required")
            return False
        if self._consent_score(first, second) < self.config.consent_threshold or self._consent_score(second, first) < self.config.consent_threshold:
            self._emit("reproduction_rejected", first_id=first_id, second_id=second_id, reason="consent")
            return False
        mother = first if first.sex == "female" else second if second.sex == "female" else None
        if mother is None:
            self._emit("reproduction_rejected", first_id=first_id, second_id=second_id, reason="compatible_pair_required")
            return False
        if mother.pregnancy_remaining is not None:
            self._emit("reproduction_rejected", first_id=first_id, second_id=second_id, reason="already_pregnant")
            return False
        settlement = self.settlements[mother.settlement_id]
        if self.alive_population >= self.config.settlement_capacity or self._settlement_population(mother.settlement_id) >= self.config.settlement_capacity:
            self._emit("reproduction_rejected", first_id=first_id, second_id=second_id, reason="capacity")
            return False
        if settlement.storage.get("food", 0) < 1:
            self._emit("reproduction_rejected", first_id=first_id, second_id=second_id, reason="resources")
            return False
        settlement.storage["food"] -= 1
        mother.pregnancy_remaining = self.config.gestation_ticks
        mother.pregnancy_partner_id = second_id if mother.agent_id == first_id else first_id
        mother.pregnancy_partner_genome = tuple((second if mother.agent_id == first_id else first).genome)
        self._emit("reproduction_accepted", first_id=first_id, second_id=second_id)
        self._emit("pregnancy_started", mother_id=mother.agent_id, partner_id=mother.pregnancy_partner_id, gestation_ticks=self.config.gestation_ticks)
        return True

    def _inherit_brain(self, first: AgentState, second: Optional[AgentState]) -> Tuple[float, ...]:
        """Crossover and boundedly mutate two parental neural policies."""

        first_weights = first.brain_weights
        second_weights = second.brain_weights if second is not None else first_weights
        if len(first_weights) != NEURAL_WEIGHT_COUNT:
            first_weights = self._new_brain_weights()
        if len(second_weights) != NEURAL_WEIGHT_COUNT:
            second_weights = first_weights
        inherited: List[float] = []
        for first_weight, second_weight in zip(first_weights, second_weights):
            value = first_weight if self.random.randrange(2) == 0 else second_weight
            if self.random.randrange(100) < self.config.mutation_percent:
                mutation = self.random.randrange(1, 101) / 1000.0
                value += mutation if self.random.randrange(2) == 0 else -mutation
            inherited.append(round(max(-2.0, min(2.0, value)), 8))
        return tuple(inherited)

    def _birth(self, mother: AgentState) -> Optional[str]:
        partner_id = mother.pregnancy_partner_id
        partner = self.agents.get(partner_id) if partner_id else None
        partner_genome = mother.pregnancy_partner_genome or (partner.genome if partner is not None else None)
        if not mother.alive or partner_genome is None:
            mother.pregnancy_remaining = None
            mother.pregnancy_partner_id = None
            mother.pregnancy_partner_genome = None
            self._emit("pregnancy_cancelled", mother_id=mother.agent_id, reason="genome_unavailable")
            return None
        if self._settlement_population(mother.settlement_id) >= self.config.settlement_capacity:
            mother.pregnancy_remaining = 1
            self._emit("birth_deferred", mother_id=mother.agent_id, reason="capacity")
            return None
        child_id = f"agent-{len(self.agents):04d}"
        child_sex = self.random.choice(("female", "male"))
        child_genome: List[int] = []
        for first_gene, second_gene in zip(mother.genome, partner_genome):
            gene = self.random.choice((first_gene, second_gene))
            if self.random.randrange(100) < self.config.mutation_percent:
                gene = max(0, min(100, gene + self.random.choice((-1, 1)) * self.random.randrange(1, 6)))
            child_genome.append(gene)
        child = AgentState(
            agent_id=child_id,
            settlement_id=mother.settlement_id,
            sex=child_sex,
            age=0,
            x=mother.x,
            y=mother.y,
            genome=tuple(child_genome),
            brain_weights=self._inherit_brain(mother, partner),
            _adult_age=self.config.adult_age,
        )
        self.agents[child_id] = child
        mother.children.append(child_id)
        if partner is not None and partner.alive:
            partner.children.append(child_id)
        mother.pregnancy_remaining = None
        mother.pregnancy_partner_id = None
        mother.pregnancy_partner_genome = None
        self._emit("child_born", child_id=child_id, mother_id=mother.agent_id, father_id=partner_id, sex=child_sex)
        return child_id

    def _settlement_population(self, settlement_id: str) -> int:
        return sum(1 for agent in self.alive_agents if agent.settlement_id == settlement_id)

    def _kill_agent(self, agent: AgentState, reason: str) -> None:
        if not agent.alive:
            return
        settlement = self.settlements[agent.settlement_id]
        for good, quantity in agent.inventory.items():
            settlement.storage[good] = settlement.storage.get(good, 0) + quantity
        settlement.treasury += agent.wallet
        agent.inventory.clear()
        agent.wallet = 0
        agent.alive = False
        agent.health = 0
        if agent.job_id and agent.job_id in self.production_jobs:
            job = self.production_jobs.pop(agent.job_id)
            for good, quantity in job.reserved_inputs.items():
                settlement.storage[good] = settlement.storage.get(good, 0) + quantity
        agent.job_id = None
        for job_id, research_job in list(self.research_jobs.items()):
            if research_job.agent_id == agent.agent_id:
                del self.research_jobs[job_id]
                self._emit("research_cancelled", job_id=job_id, reason="researcher_died")
        if agent.bond_partner_id:
            partner = self.agents.get(agent.bond_partner_id)
            if partner is not None and partner.bond_partner_id == agent.agent_id:
                partner.bond_partner_id = None
                self._emit("bond_ended", first_id=agent.agent_id, second_id=partner.agent_id, reason="death")
        agent.bond_partner_id = None
        self._emit("agent_died", agent_id=agent.agent_id, reason=reason)

    # Phase 3: individual memory and explicit settlement knowledge sharing.
    def share_knowledge(self, agent_id: str, fact: str, value: str) -> bool:
        agent = self._agent(agent_id)
        settlement = self.settlements[agent.settlement_id]
        agent.semantic_memory[fact] = value
        agent.semantic_memory_ticks[fact] = self.tick
        settlement.knowledge[fact] = value
        self._emit("knowledge_shared", agent_id=agent_id, settlement_id=agent.settlement_id, fact=fact, value=value)
        return True

    def can_act_on_resource(self, agent_id: str, position: str) -> bool:
        """Return whether perception or retained semantic memory identifies a resource."""

        agent = self._agent(agent_id)
        x, y = _split_position(position)
        in_range = abs(agent.x - x) + abs(agent.y - y) <= self.config.perception_radius
        if in_range and position in self.resources:
            return True
        return agent.semantic_memory.get(f"resource:{position}") == self.resources.get(position)

    def learn(self, agent_id: str, skill: str, amount: int = 1) -> int:
        agent = self._agent(agent_id)
        count = _positive(amount, "learning amount")
        agent.skills[skill] = agent.skills.get(skill, 0) + count
        agent.learned_policy[skill] = min(1.0, agent.learned_policy.get(skill, 0.0) + count * 0.1)
        self._emit("skill_learned", agent_id=agent_id, skill=skill, amount=count)
        return agent.skills[skill]

    # Phase 4: production, material/labor cost foundations, money, demand, and trade.
    def _effective_recipe(self, settlement: SettlementState, recipe_name: str) -> Recipe:
        recipe = RECIPES[recipe_name]
        output = dict(recipe.output)
        labor_ticks = recipe.labor_ticks
        if recipe_name == "bread" and "agriculture" in settlement.technologies:
            output["food"] += 1
        if recipe_name == "wooden_tool" and "metalworking" in settlement.technologies:
            labor_ticks = max(1, labor_ticks - 1)
        return Recipe(recipe.name, dict(recipe.inputs), output, labor_ticks)

    def production_cost(self, recipe_name: str, settlement_id: Optional[str] = None) -> Dict[str, int]:
        if recipe_name not in RECIPES:
            raise ValueError(f"unknown recipe: {recipe_name}")
        settlement = self._settlement(settlement_id) if settlement_id else next(iter(self.settlements.values()))
        recipe = self._effective_recipe(settlement, recipe_name)
        material_cost = sum(quantity * MATERIAL_PRICES.get(good, 1) for good, quantity in recipe.inputs.items())
        labor_cost = recipe.labor_ticks * 2
        return {"material_cost": material_cost, "labor_cost": labor_cost, "cost_floor": material_cost + labor_cost, "labor_ticks": recipe.labor_ticks}

    def _settlement_goods_load(self, settlement_id: str) -> int:
        settlement = self.settlements[settlement_id]
        stored = sum(settlement.storage.values())
        reserved = sum(
            sum(job.reserved_inputs.values())
            for job in self.production_jobs.values()
            if job.settlement_id == settlement_id
        )
        return stored + reserved

    def start_production(self, agent_id: str, recipe_name: str) -> Optional[str]:
        agent = self._agent(agent_id)
        if recipe_name not in RECIPES:
            raise ValueError(f"unknown recipe: {recipe_name}")
        if agent.job_id is not None:
            raise ValueError("agent already has a production job")
        if any(job.agent_id == agent_id for job in self.research_jobs.values()):
            self._emit("production_rejected", agent_id=agent_id, recipe=recipe_name, reason="worker_busy")
            return None
        settlement = self.settlements[agent.settlement_id]
        recipe = self._effective_recipe(settlement, recipe_name)
        for good, quantity in recipe.inputs.items():
            if settlement.storage.get(good, 0) < quantity:
                self._emit("production_rejected", agent_id=agent_id, recipe=recipe_name, reason="missing_input")
                return None
        goods_load_after_completion = self._settlement_goods_load(agent.settlement_id) - sum(recipe.inputs.values()) + sum(recipe.output.values())
        if goods_load_after_completion > self.config.storage_capacity:
            self._emit("production_rejected", agent_id=agent_id, recipe=recipe_name, reason="storage_capacity")
            return None
        for good, quantity in recipe.inputs.items():
            settlement.storage[good] -= quantity
        costs = self.production_cost(recipe_name, agent.settlement_id)
        job_id = f"production-{self._next_job_number:04d}"
        self._next_job_number += 1
        job = ProductionJob(job_id, agent.settlement_id, agent_id, recipe_name, recipe.labor_ticks, dict(recipe.inputs), costs["material_cost"], costs["labor_cost"], self.tick)
        self.production_jobs[job_id] = job
        agent.job_id = job_id
        self._emit("production_started", job_id=job_id, agent_id=agent_id, recipe=recipe_name, material_cost=job.material_cost, labor_cost=job.labor_cost, labor_ticks=recipe.labor_ticks)
        return job_id

    def allocate_jobs(self, settlement_id: Optional[str] = None) -> Tuple[str, ...]:
        """Assign free adults to the most constrained available recipe.

        The policy is intentionally incentive-based: current stock, recorded
        demand, and learned skill determine the score.  No agent is given a
        permanent scripted profession.
        """

        settlement_ids = [settlement_id] if settlement_id is not None else sorted(self.settlements)
        started: List[str] = []
        for current_id in settlement_ids:
            settlement = self._settlement(current_id)
            free_agents = sorted(
                (agent for agent in self.alive_agents if agent.settlement_id == current_id and self._is_adult(agent) and agent.job_id is None),
                key=lambda item: item.agent_id,
            )
            for agent in free_agents:
                candidates: List[Tuple[float, str]] = []
                for recipe_name, recipe in RECIPES.items():
                    if any(settlement.storage.get(good, 0) < quantity for good, quantity in recipe.inputs.items()):
                        continue
                    output_need = 0.0
                    effective = self._effective_recipe(settlement, recipe_name)
                    for good, quantity in effective.output.items():
                        stock = settlement.storage.get(good, 0)
                        demand = settlement.demand.get(good, 0)
                        output_need += max(0.0, 4.0 - stock) + demand / max(1, quantity)
                    skill_bonus = agent.skills.get(recipe_name, 0) * 0.25
                    candidates.append((output_need + skill_bonus, recipe_name))
                if not candidates:
                    continue
                _, selected_recipe = max(candidates, key=lambda item: (item[0], item[1]))
                job_id = self.start_production(agent.agent_id, selected_recipe)
                if job_id is not None:
                    started.append(job_id)
        self._emit("jobs_allocated", settlement_id=settlement_id, job_ids=tuple(started))
        return tuple(started)

    def record_demand(self, settlement_id: str, good: str, quantity: int = 1) -> int:
        settlement = self._settlement(settlement_id)
        amount = _positive(quantity, "demand quantity")
        settlement.demand[good] = settlement.demand.get(good, 0) + amount
        self._emit("demand_recorded", settlement_id=settlement_id, good=good, quantity=amount)
        return settlement.demand[good]

    def market_quote(self, settlement_id: str, good: str, quantity: int = 1) -> int:
        settlement = self._settlement(settlement_id)
        amount = _positive(quantity, "quote quantity")
        stock = settlement.storage.get(good, 0)
        demand = settlement.demand.get(good, 0)
        base = self._good_cost_floor(settlement, good)
        pressure = demand / max(1, stock)
        unit_price = max(base, math.ceil(base * (1 + pressure)))
        unit_price = min(base * 5, unit_price)
        return unit_price * amount

    def _good_cost_floor(self, settlement: SettlementState, good: str) -> int:
        floors = []
        for recipe_name, recipe in RECIPES.items():
            if good in recipe.output:
                floors.append(self.production_cost(recipe_name, settlement.settlement_id)["cost_floor"] // recipe.output[good])
        return max(1, min(floors) if floors else MATERIAL_PRICES.get(good, 1))

    def buy_good(self, buyer_id: str, seller_settlement_id: str, good: str, quantity: int = 1) -> bool:
        buyer = self._agent(buyer_id)
        seller = self._settlement(seller_settlement_id)
        amount = _positive(quantity, "trade quantity")
        if buyer.settlement_id != seller_settlement_id:
            relation = self.settlements[buyer.settlement_id].relations[seller_settlement_id]
            if relation["treaty"] not in {"trade", "alliance"}:
                self._emit("trade_rejected", buyer_id=buyer_id, seller_settlement_id=seller_settlement_id, reason="treaty_required")
                return False
        total = self.market_quote(seller_settlement_id, good, amount)
        if seller.storage.get(good, 0) < amount or buyer.wallet < total:
            self._emit("trade_rejected", buyer_id=buyer_id, seller_settlement_id=seller_settlement_id, reason="stock_or_funds")
            return False
        # All checks happen before these mutations: exchange is atomic.
        seller.storage[good] -= amount
        buyer.wallet -= total
        seller.treasury += total
        buyer.inventory[good] = buyer.inventory.get(good, 0) + amount
        buyer_ledger = self.settlements[buyer.settlement_id]
        buyer_ledger.demand[good] = max(0, buyer_ledger.demand.get(good, 0) - amount)
        seller.demand[good] = max(0, seller.demand.get(good, 0) - amount)
        self._record_relation_memory(buyer.settlement_id, seller_settlement_id, "trade", good=good, amount=amount)
        self._emit("trade_completed", buyer_id=buyer_id, seller_settlement_id=seller_settlement_id, good=good, quantity=amount, total=total)
        return True

    # Phase 5: research, prerequisites, effects, and explicit diffusion.
    def start_research(self, agent_id: str, technology: str) -> Optional[str]:
        agent = self._agent(agent_id)
        if technology not in TECHNOLOGIES:
            raise ValueError(f"unknown technology: {technology}")
        settlement = self.settlements[agent.settlement_id]
        if technology in settlement.technologies:
            raise ValueError("technology already known")
        prerequisites = TECHNOLOGIES[technology]["prerequisites"]
        if any(item not in settlement.technologies for item in prerequisites):
            self._emit("research_rejected", settlement_id=agent.settlement_id, technology=technology, reason="prerequisites")
            return None
        if settlement.treasury < TECHNOLOGIES[technology]["cost"]:
            self._emit("research_rejected", settlement_id=agent.settlement_id, technology=technology, reason="funds")
            return None
        if any(job.settlement_id == agent.settlement_id for job in self.research_jobs.values()):
            raise ValueError("settlement already has a research job")
        if agent.job_id is not None:
            self._emit("research_rejected", settlement_id=agent.settlement_id, technology=technology, reason="worker_busy")
            return None
        settlement.treasury -= TECHNOLOGIES[technology]["cost"]
        job_id = f"research-{self._next_research_number:04d}"
        self._next_research_number += 1
        self.research_jobs[job_id] = ResearchJob(job_id, agent.settlement_id, agent_id, technology, TECHNOLOGIES[technology]["research_ticks"], self.tick)
        self._emit("research_started", job_id=job_id, settlement_id=agent.settlement_id, technology=technology)
        return job_id

    def share_technology(self, source_settlement_id: str, target_settlement_id: str, technology: str) -> bool:
        source = self._settlement(source_settlement_id)
        target = self._settlement(target_settlement_id)
        relation = source.relations[target_settlement_id]
        prerequisites = TECHNOLOGIES.get(technology, {}).get("prerequisites", ())
        if (
            technology not in TECHNOLOGIES
            or technology not in source.technologies
            or relation["treaty"] not in {"trade", "alliance"}
            or any(item not in target.technologies for item in prerequisites)
        ):
            self._emit(
                "technology_diffusion_rejected",
                source_settlement_id=source_settlement_id,
                target_settlement_id=target_settlement_id,
                technology=technology,
                reason="prerequisites_or_contact",
            )
            return False
        target.technologies = sorted(set(target.technologies) | {technology})
        target.knowledge[f"technology:{technology}"] = source_settlement_id
        self._record_relation_memory(source_settlement_id, target_settlement_id, "technology_diffusion", technology=technology)
        self._emit("technology_diffused", source_settlement_id=source_settlement_id, target_settlement_id=target_settlement_id, technology=technology)
        return True

    # Phase 6: territory, diplomacy, migration, alliances, and conflict.
    def claim_territory(self, settlement_id: str, x: int, y: int) -> bool:
        settlement = self._settlement(settlement_id)
        _require_int(x, "x")
        _require_int(y, "y")
        if not 0 <= x < self.config.width or not 0 <= y < self.config.height:
            raise ValueError("territory position is out of bounds")
        position = _position_key(x, y)
        owner = next((item.settlement_id for item in self.settlements.values() if position in item.territory), None)
        if owner is not None and owner != settlement_id:
            self._emit("territory_claim_rejected", settlement_id=settlement_id, position=position, reason="owned")
            return False
        if position not in settlement.territory:
            settlement.territory.append(position)
            settlement.territory.sort()
        self._emit("territory_claimed", settlement_id=settlement_id, position=position)
        return True

    def negotiate(self, first_settlement_id: str, second_settlement_id: str, treaty: str) -> bool:
        if first_settlement_id == second_settlement_id:
            raise ValueError("a settlement cannot negotiate with itself")
        if treaty not in {"trade", "alliance", "truce"}:
            raise ValueError("unsupported treaty")
        first = self._settlement(first_settlement_id)
        second = self._settlement(second_settlement_id)
        first.relations[second_settlement_id]["treaty"] = treaty
        second.relations[first_settlement_id]["treaty"] = treaty
        trust_gain = {"trade": 0.2, "truce": 0.1, "alliance": 0.4}[treaty]
        first.relations[second_settlement_id]["trust"] = _clamp(first.relations[second_settlement_id]["trust"] + trust_gain)
        second.relations[first_settlement_id]["trust"] = _clamp(second.relations[first_settlement_id]["trust"] + trust_gain)
        self._record_relation_memory(first_settlement_id, second_settlement_id, "treaty", treaty=treaty)
        self._emit("treaty_signed", first_settlement_id=first_settlement_id, second_settlement_id=second_settlement_id, treaty=treaty)
        return True

    def declare_conflict(self, attacker_settlement_id: str, defender_settlement_id: str) -> bool:
        if attacker_settlement_id == defender_settlement_id:
            raise ValueError("a settlement cannot attack itself")
        attacker = self._settlement(attacker_settlement_id)
        defender = self._settlement(defender_settlement_id)
        attacker.relations[defender_settlement_id]["treaty"] = "war"
        defender.relations[attacker_settlement_id]["treaty"] = "war"
        self._record_relation_memory(attacker_settlement_id, defender_settlement_id, "conflict_declared")
        self._emit("conflict_declared", attacker_settlement_id=attacker_settlement_id, defender_settlement_id=defender_settlement_id)
        return True

    def migrate(self, agent_id: str, target_settlement_id: str) -> bool:
        agent = self._agent(agent_id)
        target = self._settlement(target_settlement_id)
        current = self.settlements[agent.settlement_id]
        if current.settlement_id == target.settlement_id:
            return False
        relation = current.relations[target.settlement_id]
        if relation["treaty"] == "war" or self._settlement_population(target_settlement_id) >= self.config.settlement_capacity:
            self._emit("migration_rejected", agent_id=agent_id, target_settlement_id=target_settlement_id)
            return False
        if agent.job_id and agent.job_id in self.production_jobs:
            job = self.production_jobs.pop(agent.job_id)
            for good, quantity in job.reserved_inputs.items():
                current.storage[good] = current.storage.get(good, 0) + quantity
            agent.job_id = None
        for job_id, research_job in list(self.research_jobs.items()):
            if research_job.agent_id == agent.agent_id:
                del self.research_jobs[job_id]
                self._emit("research_cancelled", job_id=job_id, reason="researcher_migrated")
        old_settlement = agent.settlement_id
        agent.settlement_id = target_settlement_id
        self._record_relation_memory(old_settlement, target_settlement_id, "migration", agent_id=agent_id)
        self._emit("agent_migrated", agent_id=agent_id, from_settlement=old_settlement, to_settlement=target_settlement_id)
        return True

    def resolve_conflict(self, attacker_settlement_id: str, defender_settlement_id: str) -> Optional[str]:
        attacker = self._settlement(attacker_settlement_id)
        defender = self._settlement(defender_settlement_id)
        if attacker.relations[defender_settlement_id]["treaty"] != "war":
            raise ValueError("settlements must be at war")
        attackers = sorted((agent for agent in self.alive_agents if agent.settlement_id == attacker_settlement_id and self._is_adult(agent)), key=lambda item: item.agent_id)
        defenders = sorted((agent for agent in self.alive_agents if agent.settlement_id == defender_settlement_id and self._is_adult(agent)), key=lambda item: item.agent_id)
        if not attackers or not defenders:
            self._emit("conflict_resolved", attacker_settlement_id=attacker_settlement_id, defender_settlement_id=defender_settlement_id, winner=attacker_settlement_id if attackers else defender_settlement_id if defenders else None)
            return attacker_settlement_id if attackers else defender_settlement_id if defenders else None
        attacker_agent = attackers[0]
        defender_agent = defenders[0]
        attack_power = self.config.combat_damage + attacker_agent.skills.get("combat", 0) + attacker_agent.genome[0] // 20
        defense_power = self.config.combat_damage + defender_agent.skills.get("combat", 0) + defender_agent.genome[1] // 20
        defender_agent.health = max(0, defender_agent.health - attack_power)
        attacker_agent.health = max(0, attacker_agent.health - max(1, defense_power // 2))
        self._emit("combat_resolved", attacker_id=attacker_agent.agent_id, defender_id=defender_agent.agent_id, attacker_damage=attack_power, defender_damage=max(1, defense_power // 2))
        if defender_agent.health == 0:
            self._kill_agent(defender_agent, "combat")
        if attacker_agent.health == 0:
            self._kill_agent(attacker_agent, "combat")
        winner = attacker_settlement_id if defender_agent.health == 0 else defender_settlement_id
        if winner == attacker_settlement_id and defender.territory:
            position = sorted(defender.territory).pop()
            defender.territory.remove(position)
            if position not in attacker.territory:
                attacker.territory.append(position)
                attacker.territory.sort()
        self._record_relation_memory(attacker_settlement_id, defender_settlement_id, "combat", winner=winner)
        self._emit("conflict_resolved", attacker_settlement_id=attacker_settlement_id, defender_settlement_id=defender_settlement_id, winner=winner)
        return winner

    def _record_relation_memory(self, first_id: str, second_id: str, kind: str, **payload: Any) -> None:
        if first_id == second_id:
            return
        for left, right in ((first_id, second_id), (second_id, first_id)):
            relation = self.settlements[left].relations[right]
            relation["memory"].append({"tick": self.tick, "kind": kind, **payload})
            if len(relation["memory"]) > MAX_RELATION_MEMORY:
                del relation["memory"][:-MAX_RELATION_MEMORY]

    # Phase 7: invariant observability, snapshots, replay, evaluation, and benchmarks.
    def specialization_metrics(self) -> Dict[str, Any]:
        """Summarize incentive-driven recipe focus without assigning professions."""

        by_settlement: Dict[str, Dict[str, int]] = {}
        dominant: Dict[str, Optional[str]] = {}
        focus: Dict[str, Dict[str, Any]] = {}
        for settlement_id in sorted(self.settlements):
            skills = {
                recipe_name: sum(
                    agent.skills.get(recipe_name, 0)
                    for agent in self.agents.values()
                    if agent.settlement_id == settlement_id
                )
                for recipe_name in sorted(RECIPES)
            }
            by_settlement[settlement_id] = skills
            positive = [(value, recipe_name) for recipe_name, value in skills.items() if value > 0]
            dominant[settlement_id] = max(positive)[1] if positive else None
            total_skill = sum(skills.values())
            dominant_skill = max((value for value, _ in positive), default=0)
            focus[settlement_id] = {
                "dominant_recipe": dominant[settlement_id],
                "dominant_share": round(dominant_skill / total_skill, 6) if total_skill else 0.0,
                "skill_total": total_skill,
                "storage_load": self._settlement_goods_load(settlement_id),
                "storage_capacity": self.config.storage_capacity,
                "capacity_utilization": round(self._settlement_goods_load(settlement_id) / self.config.storage_capacity, 6),
            }
        active_recipe_types = sum(
            1 for recipe_skills in by_settlement.values() for value in recipe_skills.values() if value > 0
        )
        production_by_recipe: Dict[str, int] = {}
        incentive_events = {"demand_recorded": 0, "jobs_allocated": 0, "production_started": 0}
        for event in self.events:
            if event.event_type == "production_started":
                recipe_name = event.payload.get("recipe")
                if isinstance(recipe_name, str):
                    production_by_recipe[recipe_name] = production_by_recipe.get(recipe_name, 0) + 1
                incentive_events["production_started"] += 1
            elif event.event_type in incentive_events:
                incentive_events[event.event_type] += 1
        return {
            "settlement_recipe_skill": by_settlement,
            "dominant_recipe": dominant,
            "settlement_focus": focus,
            "active_recipe_types": active_recipe_types,
            "production_by_recipe": dict(sorted(production_by_recipe.items())),
            "incentive_events": incentive_events,
        }

    def invariants(self) -> Dict[str, Any]:
        reserved_goods: Dict[str, int] = {}
        for job in self.production_jobs.values():
            for good, quantity in job.reserved_inputs.items():
                reserved_goods[good] = reserved_goods.get(good, 0) + quantity
        goods = dict(reserved_goods)
        for settlement in self.settlements.values():
            for good, quantity in settlement.storage.items():
                goods[good] = goods.get(good, 0) + quantity
        for agent in self.agents.values():
            for good, quantity in agent.inventory.items():
                goods[good] = goods.get(good, 0) + quantity
        total_money = sum(settlement.treasury for settlement in self.settlements.values()) + sum(agent.wallet for agent in self.agents.values())
        return {
            "tick": self.tick,
            "alive_population": self.alive_population,
            "dead_population": sum(1 for agent in self.agents.values() if not agent.alive),
            "total_money": total_money,
            "goods": dict(sorted(goods.items())),
            "event_count": len(self.events),
            "production_jobs": len(self.production_jobs),
            "research_jobs": len(self.research_jobs),
            "specialization": self.specialization_metrics(),
        }

    def _assert_invariants(self) -> None:
        if self.tick < 0:
            raise AssertionError("tick moved backwards")
        sequences = [event.sequence for event in self.events]
        if sequences != list(range(1, len(sequences) + 1)):
            raise AssertionError("event sequence is not canonical")
        if len(self.agents) < self.config.population:
            raise AssertionError("snapshot lost configured initial agents")
        if len(self.settlements) != self.config.settlement_count:
            raise AssertionError("settlement count does not match configuration")
        event_ticks = [event.tick for event in self.events]
        if event_ticks != sorted(event_ticks):
            raise AssertionError("event ticks are not monotonic")
        settlement_ids = set(self.settlements)
        for agent in self.agents.values():
            if agent.settlement_id not in settlement_ids:
                raise AssertionError("agent references an unknown settlement")
        for job in self.production_jobs.values():
            if job.settlement_id not in settlement_ids or job.agent_id not in self.agents:
                raise AssertionError("production job references unknown ownership")
            if self.agents[job.agent_id].job_id != job.job_id:
                raise AssertionError("production job is not linked to its worker")
        for job in self.research_jobs.values():
            if job.settlement_id not in settlement_ids or job.agent_id not in self.agents:
                raise AssertionError("research job references unknown ownership")
            if self.agents[job.agent_id].settlement_id != job.settlement_id:
                raise AssertionError("research job worker is outside its settlement")
        for agent in self.agents.values():
            if not 0 <= agent.x < self.config.width or not 0 <= agent.y < self.config.height:
                raise AssertionError("agent left world bounds")
            if len(agent.brain_weights) != NEURAL_WEIGHT_COUNT or any(not math.isfinite(weight) for weight in agent.brain_weights):
                raise AssertionError("agent neural policy has invalid weights")
            if agent.wallet < 0 or any(quantity < 0 for quantity in agent.inventory.values()):
                raise AssertionError("agent asset total became negative")
        for settlement in self.settlements.values():
            if len(settlement.brain_weights) != SETTLEMENT_WEIGHT_COUNT or any(not math.isfinite(weight) for weight in settlement.brain_weights):
                raise AssertionError("settlement neural policy has invalid weights")
        if any(settlement.treasury < 0 or any(quantity < 0 for quantity in settlement.storage.values()) for settlement in self.settlements.values()):
            raise AssertionError("settlement asset total became negative")

    def snapshot(self) -> Dict[str, Any]:
        return {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "config": self.config.as_dict(),
            "tick": self.tick,
            "random_state": self.random.get_state(),
            "agents": [self.agents[key].as_dict() for key in sorted(self.agents)],
            "settlements": [self.settlements[key].as_dict() for key in sorted(self.settlements)],
            "resources": dict(sorted(self.resources.items())),
            "production_jobs": [self.production_jobs[key].as_dict() for key in sorted(self.production_jobs)],
            "research_jobs": [self.research_jobs[key].as_dict() for key in sorted(self.research_jobs)],
            "events": [event.as_dict() for event in self.events],
            "next_event_sequence": self._next_event_sequence,
            "next_job_number": self._next_job_number,
            "next_research_number": self._next_research_number,
        }

    def canonical_json(self) -> str:
        return canonical_json(self.snapshot())

    def state_hash(self) -> str:
        """Return a stable hash for checkpoint/replay comparisons."""

        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def neural_state_hash(self) -> str:
        """Return a stable hash of resident and settlement policy weights only."""

        policy_state = {
            "agents": [
                {"agent_id": agent.agent_id, "brain_weights": list(agent.brain_weights)}
                for agent in sorted(self.agents.values(), key=lambda item: item.agent_id)
            ],
            "settlements": [
                {
                    "settlement_id": settlement.settlement_id,
                    "brain_weights": list(settlement.brain_weights),
                }
                for settlement in sorted(self.settlements.values(), key=lambda item: item.settlement_id)
            ],
        }
        return hashlib.sha256(canonical_json(policy_state).encode("utf-8")).hexdigest()

    def event_hash(self) -> str:
        return hashlib.sha256(
            canonical_json([event.as_dict() for event in self.events]).encode("utf-8")
        ).hexdigest()

    def checkpoint(self) -> Dict[str, Any]:
        """Capture a complete replay checkpoint at the current tick."""

        return {
            "tick": self.tick,
            "state_hash": self.state_hash(),
            "event_hash": self.event_hash(),
            "snapshot": self.snapshot(),
            "invariants": self.invariants(),
        }

    def run_checkpoints(self, steps: int, interval: int) -> Dict[int, Dict[str, Any]]:
        count = _non_negative(steps, "steps")
        cadence = _positive(interval, "checkpoint interval")
        final_tick = self.tick + count
        checkpoints: Dict[int, Dict[str, Any]] = {self.tick: self.checkpoint()}
        for _ in range(count):
            self.step()
            if self.tick % cadence == 0 or self.tick == final_tick:
                checkpoints[self.tick] = self.checkpoint()
        return checkpoints

    @classmethod
    def replay_checkpoint(cls, checkpoint: Mapping[str, Any], steps: int) -> Dict[str, Any]:
        if not isinstance(checkpoint, Mapping) or "snapshot" not in checkpoint:
            raise SnapshotValidationError("checkpoint must contain a snapshot")
        simulation = cls.from_snapshot(checkpoint["snapshot"])
        simulation.run(steps)
        return {
            "tick": simulation.tick,
            "state_hash": simulation.state_hash(),
            "event_hash": simulation.event_hash(),
            "snapshot": simulation.snapshot(),
            "invariants": simulation.invariants(),
        }

    def save_json(self, path: Union[str, Path]) -> None:
        Path(path).write_text(self.canonical_json(), encoding="utf-8")

    @classmethod
    def from_snapshot(cls, snapshot: Mapping[str, Any]) -> "ColonySimulation":
        required = {"schema_version", "config", "tick", "random_state", "agents", "settlements", "resources", "production_jobs", "research_jobs", "events", "next_event_sequence", "next_job_number", "next_research_number"}
        if not isinstance(snapshot, Mapping) or set(snapshot) != required:
            raise SnapshotValidationError("colony snapshot has missing or unknown fields")
        schema_version = snapshot.get("schema_version") if isinstance(snapshot, Mapping) else None
        if schema_version not in SUPPORTED_SNAPSHOT_SCHEMA_VERSIONS:
            raise SnapshotValidationError("unsupported colony snapshot schema version")
        raw_config = snapshot["config"]
        if schema_version == 4 and isinstance(raw_config, Mapping):
            # Schema 4 predates the explicit AI switch in some working-tree
            # snapshots. Fill only declared dataclass defaults; unknown keys
            # remain rejected by ColonyConfig.from_dict.
            migrated_config = dict(raw_config)
            for field_name, field_info in ColonyConfig.__dataclass_fields__.items():
                if field_name not in migrated_config and field_info.default is not MISSING:
                    migrated_config[field_name] = field_info.default
            migrated_config.setdefault("ai_enabled", True)
            raw_config = migrated_config
        config = ColonyConfig.from_dict(raw_config)
        try:
            tick = _non_negative(snapshot["tick"], "tick")
            next_event = _positive(snapshot["next_event_sequence"], "next_event_sequence")
            next_job = _positive(snapshot["next_job_number"], "next_job_number")
            next_research = _positive(snapshot["next_research_number"], "next_research_number")
        except ValueError as exc:
            raise SnapshotValidationError(str(exc)) from exc
        simulation = cls(config)
        simulation.clock = SimulationClock(tick)
        simulation.random.set_state(snapshot["random_state"])
        try:
            simulation.agents = {}
            for raw_agent in snapshot["agents"]:
                agent = AgentState.from_dict(raw_agent)
                if schema_version == 4 and not agent.brain_weights:
                    agent.brain_weights = simulation._migrated_brain_weights(agent.agent_id)
                if len(agent.brain_weights) != NEURAL_WEIGHT_COUNT:
                    raise SnapshotValidationError("agent neural weights do not match architecture")
                if agent.agent_id in simulation.agents:
                    raise SnapshotValidationError("duplicate agent id")
                if not 0 <= agent.x < config.width or not 0 <= agent.y < config.height:
                    raise SnapshotValidationError("agent position is out of bounds")
                simulation.agents[agent.agent_id] = agent
            simulation.settlements = {}
            for raw_settlement in snapshot["settlements"]:
                settlement = SettlementState.from_dict(raw_settlement)
                if schema_version == 4 and not settlement.brain_weights:
                    settlement.brain_weights = simulation._migrated_settlement_brain_weights(settlement.settlement_id)
                if len(settlement.brain_weights) != SETTLEMENT_WEIGHT_COUNT:
                    raise SnapshotValidationError("settlement neural weights do not match architecture")
                if settlement.settlement_id in simulation.settlements:
                    raise SnapshotValidationError("duplicate settlement id")
                simulation.settlements[settlement.settlement_id] = settlement
            if not isinstance(snapshot["resources"], Mapping):
                raise SnapshotValidationError("resources must be an object")
            simulation.resources = {}
            for key, value in snapshot["resources"].items():
                if not isinstance(key, str) or value not in {"wood", "grain"}:
                    raise SnapshotValidationError("resource keys and values must be strings from the resource catalog")
                resource_x, resource_y = _split_position(key)
                if not 0 <= resource_x < config.width or not 0 <= resource_y < config.height:
                    raise SnapshotValidationError("resource position is out of bounds")
                simulation.resources[key] = value
            simulation.production_jobs = {}
            for raw_job in snapshot["production_jobs"]:
                job = ProductionJob.from_dict(raw_job)
                if job.job_id in simulation.production_jobs:
                    raise SnapshotValidationError("duplicate production job id")
                simulation.production_jobs[job.job_id] = job
            simulation.research_jobs = {}
            for raw_job in snapshot["research_jobs"]:
                job = ResearchJob.from_dict(raw_job)
                if job.job_id in simulation.research_jobs:
                    raise SnapshotValidationError("duplicate research job id")
                simulation.research_jobs[job.job_id] = job
            simulation.events = []
            previous_sequence = 0
            previous_tick = 0
            for raw_event in snapshot["events"]:
                sequence = _positive(raw_event["sequence"], "event sequence")
                event_tick = _non_negative(raw_event["tick"], "event tick")
                if sequence != previous_sequence + 1 or event_tick < previous_tick or event_tick > tick:
                    raise SnapshotValidationError("event stream is not ordered")
                event = DomainEvent(sequence, event_tick, raw_event["event_type"], dict(raw_event["payload"]))
                simulation.events.append(event)
                previous_sequence = sequence
                previous_tick = event_tick
            if next_event != previous_sequence + 1:
                raise SnapshotValidationError("next event sequence does not follow event stream")
        except (KeyError, TypeError, ValueError) as exc:
            raise SnapshotValidationError(f"invalid colony snapshot state: {exc}") from exc
        simulation._next_event_sequence = next_event
        simulation._next_job_number = next_job
        simulation._next_research_number = next_research
        try:
            simulation._assert_invariants()
        except (AssertionError, KeyError, TypeError, ValueError) as exc:
            raise SnapshotValidationError(f"invalid colony snapshot invariants: {exc}") from exc
        return simulation

    @classmethod
    def load_json(cls, path: Union[str, Path]) -> "ColonySimulation":
        try:
            with Path(path).open("r", encoding="utf-8") as source:
                snapshot = json.load(source, object_pairs_hook=_strict_pairs, parse_constant=_reject_constant)
        except SnapshotValidationError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise SnapshotValidationError(f"could not load colony snapshot: {exc}") from exc
        return cls.from_snapshot(snapshot)

    @classmethod
    def evaluate_seeds(cls, config: ColonyConfig, seeds: Iterable[int], steps: int) -> Dict[str, Any]:
        results = []
        for seed in seeds:
            simulation = cls(replace(config, seed=seed)).run(steps)
            event_counts: Dict[str, int] = {}
            for event in simulation.events:
                event_counts[event.event_type] = event_counts.get(event.event_type, 0) + 1
            results.append(
                {
                    "seed": seed,
                    **simulation.invariants(),
                    "winner": simulation.winner(),
                    "event_counts": dict(sorted(event_counts.items())),
                }
            )
        populations = [item["alive_population"] for item in results]
        event_totals: Dict[str, int] = {}
        winners: Dict[str, int] = {}
        for item in results:
            for event_type, count in item["event_counts"].items():
                event_totals[event_type] = event_totals.get(event_type, 0) + count
            if item["winner"] is not None:
                winners[item["winner"]] = winners.get(item["winner"], 0) + 1
        specialization_values = [item["specialization"]["active_recipe_types"] for item in results]
        return {
            "world": {"width": config.width, "height": config.height, "population": config.population, "settlements": config.settlement_count},
            "steps": steps,
            "sample_size": len(results),
            "runs": results,
            "alive_population": {"min": min(populations) if populations else 0, "mean": statistics.mean(populations) if populations else 0, "max": max(populations) if populations else 0},
            "emergence_metrics": {
                "event_totals": dict(sorted(event_totals.items())),
                "winner_distribution": dict(sorted(winners.items())),
                "specialization_active_recipe_types": {
                    "min": min(specialization_values) if specialization_values else 0,
                    "mean": statistics.mean(specialization_values) if specialization_values else 0,
                    "max": max(specialization_values) if specialization_values else 0,
                },
            },
        }

    @classmethod
    def benchmark(cls, config: ColonyConfig, ticks: int, repetitions: int = 3, warm_up: int = 2) -> Dict[str, Any]:
        _non_negative(ticks, "ticks")
        _positive(repetitions, "repetitions")
        _non_negative(warm_up, "warm_up")
        for index in range(warm_up):
            cls(replace(config, seed=config.seed + index)).run(ticks)
        durations: List[float] = []
        peaks: List[int] = []
        for index in range(repetitions):
            tracemalloc.start()
            started = time.perf_counter()
            cls(replace(config, seed=config.seed + warm_up + index)).run(ticks)
            durations.append(time.perf_counter() - started)
            _, peak = tracemalloc.get_traced_memory()
            peaks.append(peak)
            tracemalloc.stop()
        sorted_durations = sorted(durations)
        p95_index = max(0, min(len(sorted_durations) - 1, math.ceil(len(sorted_durations) * 0.95) - 1))
        return {
            "world": {"width": config.width, "height": config.height},
            "population": config.population,
            "settlements": config.settlement_count,
            "ticks": ticks,
            "warm_up": warm_up,
            "repetitions": repetitions,
            "seconds": {"min": min(durations), "mean": statistics.mean(durations), "median": statistics.median(durations), "p95": sorted_durations[p95_index], "max": max(durations)},
            "peak_memory_bytes": {"min": min(peaks), "mean": statistics.mean(peaks), "max": max(peaks)},
        }


def _strict_pairs(pairs: List[Tuple[str, Any]]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SnapshotValidationError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise SnapshotValidationError(f"non-standard JSON constant is not allowed: {value}")


__all__ = [
    "AgentState",
    "ColonyConfig",
    "ColonySimulation",
    "DomainEvent",
    "RECIPES",
    "SNAPSHOT_SCHEMA_VERSION",
    "TECHNOLOGIES",
]
