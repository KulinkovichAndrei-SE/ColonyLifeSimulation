"""Deterministic, display-free colony simulation rules.

The legacy Pygame prototype remains in its original modules.  This module is
the headless domain path for the roadmap: every transition is driven by an
explicit simulation tick, an owned seeded random source, and an ordered event
stream.  The implementation intentionally keeps individual state, memory,
learned policy, genome, settlement knowledge, and economic state separate.
"""

from __future__ import annotations

import json
import math
import statistics
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

from simulation_core import (
    SeededRandom,
    SimulationClock,
    SnapshotValidationError,
    canonical_json,
)


SNAPSHOT_SCHEMA_VERSION = 3
MAX_MEMORY_ITEMS = 24
MAX_RELATION_MEMORY = 32
MATERIAL_PRICES = {"wood": 3, "grain": 4, "stone": 5, "ore": 7}


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
    perception_radius: int = 4
    affinity_gain: float = 0.12
    consent_threshold: float = 0.55
    hunger_decay: int = 2
    energy_decay: int = 1
    mutation_percent: int = 8
    combat_damage: int = 18
    memory_capacity: int = 24
    memory_ttl: int = 20

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
        if not 0 <= self.mutation_percent <= 100:
            raise ValueError("mutation_percent must be in [0, 100]")
        _positive(self.combat_damage, "combat_damage")
        _positive(self.memory_capacity, "memory_capacity")
        _positive(self.memory_ttl, "memory_ttl")

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
            "perception_radius": self.perception_radius,
            "affinity_gain": self.affinity_gain,
            "consent_threshold": self.consent_threshold,
            "hunger_decay": self.hunger_decay,
            "energy_decay": self.energy_decay,
            "mutation_percent": self.mutation_percent,
            "combat_damage": self.combat_damage,
            "memory_capacity": self.memory_capacity,
            "memory_ttl": self.memory_ttl,
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

    def as_dict(self) -> Dict[str, Any]:
        return {
            "settlement_id": self.settlement_id,
            "treasury": self.treasury,
            "storage": self.storage,
            "demand": self.demand,
            "knowledge": self.knowledge,
            "technologies": sorted(self.technologies),
            "territory": sorted(self.territory),
            "relations": self.relations,
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
                relations={key: dict(item) for key, item in value["relations"].items()},
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise SnapshotValidationError(f"invalid settlement: {exc}") from exc
        if not isinstance(state.settlement_id, str) or not _is_int(state.treasury) or state.treasury < 0:
            raise SnapshotValidationError("invalid settlement identity or treasury")
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

    def _initialize_agents(self) -> None:
        settlement_ids = sorted(self.settlements)
        for index in range(self.config.population):
            settlement_id = settlement_ids[index % len(settlement_ids)]
            sex = "female" if index % 2 == 0 else "male"
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
        self._update_childcare()
        self._decay_memory()
        self._update_perception()
        self._update_relationships()
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

    def _update_childcare(self) -> None:
        for parent in sorted(self.alive_agents, key=lambda item: item.agent_id):
            for child_id in list(parent.children):
                child = self.agents.get(child_id)
                if child is None or not child.alive or child.age >= self.config.adult_age:
                    continue
                if child.settlement_id == parent.settlement_id and self._distance(parent, child) <= self.config.perception_radius:
                    child.hunger = min(100, child.hunger + 3)
                    parent.energy = max(0, parent.energy - 1)
                    self._emit("childcare_provided", parent_id=parent.agent_id, child_id=child_id)

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
            if job.technology not in settlement.technologies:
                settlement.technologies.append(job.technology)
                settlement.technologies.sort()
            del self.research_jobs[job_id]
            self._emit("technology_unlocked", settlement_id=job.settlement_id, technology=job.technology)

    def _consume_food_for_need(self) -> None:
        for agent in sorted(self.alive_agents, key=lambda item: item.agent_id):
            if agent.hunger >= 45:
                continue
            settlement = self.settlements[agent.settlement_id]
            if settlement.storage.get("food", 0) <= 0:
                self._emit("need_unmet", agent_id=agent.agent_id, need="food")
                continue
            settlement.storage["food"] -= 1
            agent.hunger = min(100, agent.hunger + 35)
            self._emit("need_met", agent_id=agent.agent_id, need="food")

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

    def start_production(self, agent_id: str, recipe_name: str) -> Optional[str]:
        agent = self._agent(agent_id)
        if recipe_name not in RECIPES:
            raise ValueError(f"unknown recipe: {recipe_name}")
        if agent.job_id is not None:
            raise ValueError("agent already has a production job")
        settlement = self.settlements[agent.settlement_id]
        recipe = self._effective_recipe(settlement, recipe_name)
        for good, quantity in recipe.inputs.items():
            if settlement.storage.get(good, 0) < quantity:
                self._emit("production_rejected", agent_id=agent_id, recipe=recipe_name, reason="missing_input")
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
        if technology not in source.technologies or relation["treaty"] not in {"trade", "alliance"}:
            self._emit("technology_diffusion_rejected", source_settlement_id=source_settlement_id, target_settlement_id=target_settlement_id, technology=technology)
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
        }

    def _assert_invariants(self) -> None:
        if self.tick < 0:
            raise AssertionError("tick moved backwards")
        sequences = [event.sequence for event in self.events]
        if sequences != list(range(1, len(sequences) + 1)):
            raise AssertionError("event sequence is not canonical")
        for agent in self.agents.values():
            if not 0 <= agent.x < self.config.width or not 0 <= agent.y < self.config.height:
                raise AssertionError("agent left world bounds")
            if agent.wallet < 0 or any(quantity < 0 for quantity in agent.inventory.values()):
                raise AssertionError("agent asset total became negative")
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

    def save_json(self, path: Union[str, Path]) -> None:
        Path(path).write_text(self.canonical_json(), encoding="utf-8")

    @classmethod
    def from_snapshot(cls, snapshot: Mapping[str, Any]) -> "ColonySimulation":
        required = {"schema_version", "config", "tick", "random_state", "agents", "settlements", "resources", "production_jobs", "research_jobs", "events", "next_event_sequence", "next_job_number", "next_research_number"}
        if not isinstance(snapshot, Mapping) or set(snapshot) != required:
            raise SnapshotValidationError("colony snapshot has missing or unknown fields")
        if snapshot["schema_version"] != SNAPSHOT_SCHEMA_VERSION:
            raise SnapshotValidationError("unsupported colony snapshot schema version")
        config = ColonyConfig.from_dict(snapshot["config"])
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
                if agent.agent_id in simulation.agents:
                    raise SnapshotValidationError("duplicate agent id")
                if not 0 <= agent.x < config.width or not 0 <= agent.y < config.height:
                    raise SnapshotValidationError("agent position is out of bounds")
                simulation.agents[agent.agent_id] = agent
            simulation.settlements = {}
            for raw_settlement in snapshot["settlements"]:
                settlement = SettlementState.from_dict(raw_settlement)
                if settlement.settlement_id in simulation.settlements:
                    raise SnapshotValidationError("duplicate settlement id")
                simulation.settlements[settlement.settlement_id] = settlement
            simulation.resources = {str(key): str(value) for key, value in snapshot["resources"].items()}
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
            for raw_event in snapshot["events"]:
                sequence = _positive(raw_event["sequence"], "event sequence")
                event_tick = _non_negative(raw_event["tick"], "event tick")
                if sequence != previous_sequence + 1 or event_tick > tick:
                    raise SnapshotValidationError("event stream is not ordered")
                event = DomainEvent(sequence, event_tick, raw_event["event_type"], dict(raw_event["payload"]))
                simulation.events.append(event)
                previous_sequence = sequence
            if next_event != previous_sequence + 1:
                raise SnapshotValidationError("next event sequence does not follow event stream")
        except (KeyError, TypeError, ValueError) as exc:
            raise SnapshotValidationError(f"invalid colony snapshot state: {exc}") from exc
        simulation._next_event_sequence = next_event
        simulation._next_job_number = next_job
        simulation._next_research_number = next_research
        simulation._assert_invariants()
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
            results.append({"seed": seed, **simulation.invariants()})
        populations = [item["alive_population"] for item in results]
        return {
            "steps": steps,
            "runs": results,
            "alive_population": {"min": min(populations) if populations else 0, "mean": statistics.mean(populations) if populations else 0, "max": max(populations) if populations else 0},
        }

    @classmethod
    def benchmark(cls, config: ColonyConfig, ticks: int, repetitions: int = 3) -> Dict[str, Any]:
        _non_negative(ticks, "ticks")
        _positive(repetitions, "repetitions")
        durations: List[float] = []
        for index in range(repetitions):
            started = time.perf_counter()
            cls(replace(config, seed=config.seed + index)).run(ticks)
            durations.append(time.perf_counter() - started)
        return {
            "population": config.population,
            "settlements": config.settlement_count,
            "ticks": ticks,
            "repetitions": repetitions,
            "seconds": {"min": min(durations), "mean": statistics.mean(durations), "max": max(durations)},
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
