"""Run a compact, reproducible scenario through all implemented domain phases.

The playable entry point is ``python main.py``.  This script is a diagnostic
companion used by tests and CI to show that the Pygame consumer and the
headless verification seam share the same domain engine.
"""

from colony_simulation import ColonyConfig, ColonySimulation
from simulation_core import canonical_json


def main() -> None:
    config = ColonyConfig(
        seed=20260828,
        width=20,
        height=12,
        population=4,
        settlement_count=2,
        adult_age=2,
        fertility_start=2,
        fertility_end=25,
        max_age=200,
        gestation_ticks=2,
    )
    simulation = ColonySimulation(config)
    mother = simulation.agents["agent-0000"]
    father = simulation.agents["agent-0002"]
    mother.age = father.age = 8
    mother.affinity[father.agent_id] = 1.0
    father.affinity[mother.agent_id] = 1.0
    simulation.courtship(mother.agent_id, father.agent_id)
    simulation.request_reproduction(mother.agent_id, father.agent_id)
    simulation.run(config.gestation_ticks)

    simulation.record_demand("settlement-000", "food", 4)
    simulation.allocate_jobs()
    simulation.run(2)
    if "agriculture" not in simulation.settlements[mother.settlement_id].technologies:
        research_job = simulation.research_jobs_for(mother.settlement_id)
        if research_job is None and mother.job_id is None:
            simulation.start_research(mother.agent_id, "agriculture")
            simulation.run(2)

    simulation.negotiate("settlement-000", "settlement-001", "trade")
    buyer = simulation.agents["agent-0001"]
    simulation.buy_good(buyer.agent_id, "settlement-000", "food", 1)
    simulation.claim_territory("settlement-000", mother.x, mother.y)
    simulation.declare_conflict("settlement-000", "settlement-001")
    simulation.resolve_conflict("settlement-000", "settlement-001")

    checkpoint = simulation.checkpoint()
    uninterrupted = ColonySimulation.from_snapshot(checkpoint["snapshot"]).run(4)
    replayed = ColonySimulation.replay_checkpoint(checkpoint, 4)
    evaluation = ColonySimulation.evaluate_seeds(config, range(32), 60)
    benchmark = ColonySimulation.benchmark(config, ticks=10, warm_up=1, repetitions=2)
    print(
        canonical_json(
            {
                "tick": simulation.tick,
                "children": sorted({child_id for agent in simulation.agents.values() for child_id in agent.children}),
                "technologies": {key: value.technologies for key, value in simulation.settlements.items()},
                "invariants": simulation.invariants(),
                "replay_matches": replayed["state_hash"] == uninterrupted.state_hash() and replayed["event_hash"] == uninterrupted.event_hash(),
                "multi_seed_sample_size": evaluation["sample_size"],
                "emergence_metrics": evaluation["emergence_metrics"],
                "benchmark": benchmark,
            }
        )
    )


if __name__ == "__main__":
    main()
