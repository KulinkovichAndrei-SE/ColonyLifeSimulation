import tempfile
import unittest
from pathlib import Path

from colony_simulation import ColonyConfig, ColonySimulation
from simulation_core import SnapshotValidationError


class ColonySimulationTests(unittest.TestCase):
    def fixture(self, **overrides):
        values = {
            "seed": 7,
            "width": 20,
            "height": 12,
            "population": 4,
            "settlement_count": 2,
            "adult_age": 2,
            "fertility_start": 2,
            "fertility_end": 25,
            "max_age": 40,
            "gestation_ticks": 2,
            "perception_radius": 5,
        }
        values.update(overrides)
        return ColonySimulation(ColonyConfig(**values))

    def test_needs_age_and_death_are_tick_driven(self):
        simulation = self.fixture(population=1, settlement_count=1, hunger_decay=3, energy_decay=2)
        agent = simulation.agents["agent-0000"]
        agent.health = 1
        agent.hunger = 0
        before_age = agent.age

        simulation.step()

        self.assertEqual(agent.age, before_age + 1)
        self.assertFalse(agent.alive)
        self.assertEqual(agent.health, 0)
        self.assertTrue(any(event.event_type == "agent_died" for event in simulation.events))

    def test_affinity_changes_from_explicit_interaction(self):
        simulation = self.fixture(population=2, settlement_count=1)
        first = simulation.agents["agent-0000"]
        second = simulation.agents["agent-0001"]
        first.x = second.x
        first.y = second.y

        gain = simulation.interact(first.agent_id, second.agent_id)

        self.assertGreater(gain, 0)
        self.assertGreater(first.affinity[second.agent_id], 0)
        self.assertGreater(second.affinity[first.agent_id], 0)
        self.assertEqual(simulation.events[-1].event_type, "interaction")

    def test_residents_move_deterministically_each_tick(self):
        simulation = self.fixture(population=1, settlement_count=1)
        agent = simulation.agents["agent-0000"]
        before = agent.position()

        simulation.run(2)
        after = agent.position()
        repeated = self.fixture(population=1, settlement_count=1)
        repeated.run(2)

        self.assertNotEqual(before, after)
        self.assertEqual(after, repeated.agents["agent-0000"].position())
        self.assertTrue(any(event.event_type == "agent_moved" for event in simulation.events))

    def test_ai_makes_autonomous_resident_and_settlement_decisions(self):
        simulation = self.fixture(population=2, settlement_count=1)
        before = {agent.agent_id: agent.position() for agent in simulation.alive_agents}

        simulation.run(3)

        after = {agent.agent_id: agent.position() for agent in simulation.alive_agents}
        self.assertTrue(any(before[agent_id] != position for agent_id, position in after.items()))
        self.assertTrue(any(event.event_type == "agent_decision" for event in simulation.events))
        self.assertTrue(any(event.event_type == "learning_updated" for event in simulation.events))
        self.assertTrue(any(event.event_type == "settlement_decision" for event in simulation.events))
        self.assertTrue(any(agent.learned_policy for agent in simulation.alive_agents))

    def test_ai_run_can_reach_single_settlement_winner(self):
        simulation = self.fixture(population=4, settlement_count=2)

        winner = simulation.run_until_winner(120)

        self.assertIn(winner, simulation.settlements)
        self.assertTrue(simulation.game_over)
        self.assertEqual(sum(1 for settlement_id in simulation.settlements if simulation._settlement_population(settlement_id) > 0), 1)

    def test_ai_uses_treaty_for_trade_and_technology_diffusion(self):
        simulation = self.fixture(population=4, settlement_count=2, max_age=200)
        first = simulation.settlements["settlement-000"]
        second = simulation.settlements["settlement-001"]
        simulation.negotiate(first.settlement_id, second.settlement_id, "trade")
        first.storage["food"] = 0
        second.storage["food"] = 20
        first.technologies = []
        second.technologies = ["agriculture"]

        simulation.step()

        self.assertTrue(any(event.event_type == "trade_completed" for event in simulation.events))
        self.assertTrue(any(event.event_type == "technology_diffused" for event in simulation.events))
        self.assertTrue(any(event.event_type == "settlement_trade_decision" for event in simulation.events))

    def test_ai_can_choose_migration_from_food_pressure(self):
        simulation = self.fixture(population=4, settlement_count=2, max_age=200)
        current = simulation.settlements["settlement-000"]
        target = simulation.settlements["settlement-001"]
        current.storage.update({"food": 0, "grain": 0, "wood": 0, "stone": 0})
        target.storage["food"] = 20

        simulation.step()

        self.assertTrue(any(event.event_type == "settlement_migration_decision" for event in simulation.events))
        self.assertEqual(sum(1 for agent in simulation.alive_agents if agent.settlement_id == current.settlement_id), 1)

    def test_storage_capacity_and_specialization_are_observable(self):
        simulation = self.fixture(population=1, settlement_count=1, storage_capacity=26)
        agent = simulation.agents["agent-0000"]

        self.assertIsNone(simulation.start_production(agent.agent_id, "bread"))
        self.assertTrue(any(event.payload.get("reason") == "storage_capacity" for event in simulation.events))
        metrics = simulation.specialization_metrics()
        self.assertIn("active_recipe_types", metrics)
        self.assertIn("settlement-000", metrics["settlement_recipe_skill"])
        self.assertIn("dominant_share", metrics["settlement_focus"]["settlement-000"])
        self.assertIn("capacity_utilization", metrics["settlement_focus"]["settlement-000"])
        self.assertIn("demand_recorded", metrics["incentive_events"])

    def test_rejected_courtship_has_no_bond_or_pregnancy(self):
        simulation = self.fixture(population=2, settlement_count=1, consent_threshold=0.99)
        first = simulation.agents["agent-0000"]
        second = simulation.agents["agent-0001"]

        self.assertFalse(simulation.courtship(first.agent_id, second.agent_id))
        self.assertIsNone(first.bond_partner_id)
        self.assertIsNone(second.bond_partner_id)
        self.assertIsNone(first.pregnancy_remaining)
        self.assertEqual(simulation.events[-1].event_type, "courtship_rejected")

    def test_consent_bond_gestation_birth_and_inheritance_are_isolated(self):
        simulation = self.fixture(population=2, settlement_count=1, mutation_percent=0)
        mother = simulation.agents["agent-0000"]
        father = simulation.agents["agent-0001"]
        mother.age = father.age = 8
        mother.affinity[father.agent_id] = 1.0
        father.affinity[mother.agent_id] = 1.0
        mother_genome = mother.genome
        father_genome = father.genome

        self.assertTrue(simulation.courtship(mother.agent_id, father.agent_id))
        self.assertTrue(simulation.request_reproduction(mother.agent_id, father.agent_id))
        self.assertEqual(mother.pregnancy_remaining, 2)
        self.assertEqual(simulation.settlements["settlement-000"].storage["food"], 1)

        simulation.run(2)

        children = [agent for agent in simulation.agents.values() if agent.age == 0]
        self.assertEqual(len(children), 1)
        child = children[0]
        self.assertEqual(child.settlement_id, mother.settlement_id)
        self.assertEqual(child.memory, [])
        self.assertEqual(child.semantic_memory, {})
        self.assertEqual(child.learned_policy, {})
        self.assertIn(child.agent_id, mother.children)
        self.assertIn(child.agent_id, father.children)
        self.assertEqual(mother.genome, mother_genome)
        self.assertEqual(father.genome, father_genome)

        simulation.learn(child.agent_id, "bread")
        self.assertEqual(child.genome, tuple(child.genome))
        self.assertEqual(mother.genome, mother_genome)
        self.assertEqual(father.genome, father_genome)

    def test_pregnancy_keeps_partner_genome_if_partner_dies(self):
        simulation = self.fixture(population=2, settlement_count=1, mutation_percent=0)
        mother = simulation.agents["agent-0000"]
        father = simulation.agents["agent-0001"]
        mother.age = father.age = 8
        mother.affinity[father.agent_id] = 1.0
        father.affinity[mother.agent_id] = 1.0
        self.assertTrue(simulation.courtship(mother.agent_id, father.agent_id))
        self.assertTrue(simulation.request_reproduction(mother.agent_id, father.agent_id))
        father.alive = False

        simulation.run(2)

        self.assertTrue(any(event.event_type == "child_born" for event in simulation.events))

    def test_death_reclaims_assets_and_cleans_jobs(self):
        simulation = self.fixture(population=1, settlement_count=1)
        agent = simulation.agents["agent-0000"]
        agent.inventory["food"] = 2
        agent.wallet = 9
        job_id = simulation.start_production(agent.agent_id, "bread")
        self.assertIsNotNone(job_id)
        agent.health = 1
        agent.hunger = 0

        simulation.step()

        self.assertFalse(agent.alive)
        self.assertNotIn(job_id, simulation.production_jobs)
        self.assertIsNone(agent.job_id)
        self.assertEqual(agent.wallet, 0)
        self.assertEqual(simulation.settlements[agent.settlement_id].treasury, 109)

    def test_perception_memory_is_private_bounded_and_expires(self):
        simulation = self.fixture(population=1, settlement_count=1, perception_radius=0, memory_capacity=3, memory_ttl=2)
        agent = simulation.agents["agent-0000"]
        resource_position = next(iter(simulation.resources))
        agent.x, agent.y = map(int, resource_position.split(","))

        simulation.step()
        self.assertTrue(simulation.can_act_on_resource(agent.agent_id, resource_position))
        self.assertLessEqual(len(agent.memory), 3)
        self.assertNotIn("resource:" + resource_position, simulation.settlements[agent.settlement_id].knowledge)

        agent.x = (agent.x + 5) % simulation.config.width
        agent.y = (agent.y + 5) % simulation.config.height
        simulation.run(2)

        self.assertFalse(simulation.can_act_on_resource(agent.agent_id, resource_position))
        self.assertNotIn("resource:" + resource_position, agent.semantic_memory)

    def test_knowledge_sharing_copies_a_fact_without_aliasing_memory(self):
        simulation = self.fixture(population=1, settlement_count=1)
        agent = simulation.agents["agent-0000"]
        settlement = simulation.settlements[agent.settlement_id]

        agent.semantic_memory["private:plan"] = "hidden"
        self.assertNotIn("private:plan", settlement.knowledge)
        simulation.share_knowledge(agent.agent_id, "resource:known", "wood")

        self.assertEqual(settlement.knowledge["resource:known"], "wood")
        self.assertIsNot(settlement.knowledge, agent.semantic_memory)
        agent.semantic_memory["resource:known"] = "changed-locally"
        self.assertEqual(settlement.knowledge["resource:known"], "wood")

    def test_learning_changes_policy_and_skill_without_changing_genome(self):
        simulation = self.fixture(population=1, settlement_count=1)
        agent = simulation.agents["agent-0000"]
        genome_before = agent.genome

        simulation.learn(agent.agent_id, "foraging", 2)

        self.assertEqual(agent.skills["foraging"], 2)
        self.assertGreater(agent.learned_policy["foraging"], 0)
        self.assertEqual(agent.genome, genome_before)

    def test_production_reserves_materials_and_waits_for_labor_ticks(self):
        simulation = self.fixture(population=1, settlement_count=1)
        agent = simulation.agents["agent-0000"]
        settlement = simulation.settlements[agent.settlement_id]
        grain_before = settlement.storage["grain"]
        food_before = settlement.storage["food"]

        job_id = simulation.start_production(agent.agent_id, "bread")

        self.assertIsNotNone(job_id)
        self.assertEqual(settlement.storage["grain"], grain_before - 1)
        self.assertEqual(settlement.storage["food"], food_before)
        simulation.step()
        self.assertIn(job_id, simulation.production_jobs)
        self.assertEqual(settlement.storage["food"], food_before)
        simulation.step()
        self.assertNotIn(job_id, simulation.production_jobs)
        self.assertEqual(settlement.storage["food"], food_before + 2)

    def test_production_cost_has_material_and_labor_foundation(self):
        simulation = self.fixture(population=1, settlement_count=1)

        costs = simulation.production_cost("bread", "settlement-000")

        self.assertEqual(costs["material_cost"], 4)
        self.assertEqual(costs["labor_cost"], 4)
        self.assertEqual(costs["cost_floor"], 8)
        self.assertGreaterEqual(simulation.market_quote("settlement-000", "food"), 4)

    def test_demand_pressure_raises_price_and_supply_reduces_pressure(self):
        simulation = self.fixture(population=1, settlement_count=1)
        settlement = simulation.settlements["settlement-000"]
        settlement.storage["food"] = 5
        baseline = simulation.market_quote(settlement.settlement_id, "food")

        simulation.record_demand(settlement.settlement_id, "food", 5)
        pressured = simulation.market_quote(settlement.settlement_id, "food")
        settlement.storage["food"] += 10
        replenished = simulation.market_quote(settlement.settlement_id, "food")

        self.assertGreater(pressured, baseline)
        self.assertLessEqual(replenished, pressured)

    def test_trade_conserves_money_and_invalid_trade_has_no_partial_side_effects(self):
        simulation = self.fixture(population=2, settlement_count=1)
        buyer = simulation.agents["agent-0000"]
        seller = simulation.settlements["settlement-000"]
        seller.storage["food"] = 5
        simulation.record_demand(seller.settlement_id, "food", 2)
        money_before = simulation.invariants()["total_money"]
        stock_before = seller.storage["food"]
        self.assertTrue(simulation.buy_good(buyer.agent_id, seller.settlement_id, "food", 1))
        self.assertEqual(simulation.invariants()["total_money"], money_before)
        self.assertEqual(seller.storage["food"], stock_before - 1)
        self.assertEqual(buyer.inventory["food"], 1)

        wallet_after = buyer.wallet
        seller_after = seller.storage["food"]
        buyer.wallet = 0
        self.assertFalse(simulation.buy_good(buyer.agent_id, seller.settlement_id, "food", 1))
        self.assertEqual(buyer.wallet, 0)
        self.assertEqual(seller.storage["food"], seller_after)
        self.assertEqual(buyer.inventory["food"], 1)

    def test_incentive_job_allocation_uses_current_shortage_and_skill(self):
        simulation = self.fixture(population=2, settlement_count=1)
        settlement = simulation.settlements["settlement-000"]
        settlement.storage["food"] = 0
        settlement.storage["tool"] = 0
        simulation.record_demand(settlement.settlement_id, "food", 4)

        jobs = simulation.allocate_jobs(settlement.settlement_id)

        self.assertTrue(jobs)
        self.assertTrue(all(job_id in simulation.production_jobs for job_id in jobs))
        self.assertEqual(len(jobs), 2)

    def test_research_requires_prerequisites_and_consumes_ticks_and_funds(self):
        simulation = self.fixture(population=1, settlement_count=1)
        agent = simulation.agents["agent-0000"]
        settlement = simulation.settlements[agent.settlement_id]
        treasury_before = settlement.treasury

        self.assertIsNone(simulation.start_research(agent.agent_id, "metalworking"))
        self.assertNotIn("metalworking", settlement.technologies)
        research_id = simulation.start_research(agent.agent_id, "agriculture")
        self.assertIsNotNone(research_id)
        self.assertEqual(settlement.treasury, treasury_before - 4)

        simulation.step()
        self.assertNotIn("agriculture", settlement.technologies)
        simulation.step()
        self.assertIn("agriculture", settlement.technologies)
        self.assertTrue(any(event.event_type == "technology_unlocked" for event in simulation.events))

    def test_research_can_fail_after_consuming_deterministic_cost(self):
        simulation = self.fixture(population=1, settlement_count=1, research_failure_percent=100)
        agent = simulation.agents["agent-0000"]
        settlement = simulation.settlements[agent.settlement_id]
        treasury_before = settlement.treasury

        self.assertIsNotNone(simulation.start_research(agent.agent_id, "agriculture"))
        simulation.run(2)

        self.assertEqual(settlement.treasury, treasury_before - 4)
        self.assertNotIn("agriculture", settlement.technologies)
        self.assertTrue(any(event.event_type == "research_failed" for event in simulation.events))

    def test_research_and_production_cannot_share_one_worker(self):
        simulation = self.fixture(population=1, settlement_count=1)
        agent = simulation.agents["agent-0000"]

        self.assertIsNotNone(simulation.start_research(agent.agent_id, "agriculture"))
        self.assertIsNone(simulation.start_production(agent.agent_id, "bread"))
        self.assertEqual(len(simulation.production_jobs), 0)

        simulation = self.fixture(population=1, settlement_count=1)
        agent = simulation.agents["agent-0000"]
        self.assertIsNotNone(simulation.start_production(agent.agent_id, "bread"))
        self.assertIsNone(simulation.start_research(agent.agent_id, "agriculture"))
        self.assertEqual(len(simulation.research_jobs), 0)

    def test_technology_changes_recipe_effects(self):
        simulation = self.fixture(population=1, settlement_count=1)
        settlement = simulation.settlements["settlement-000"]
        agent = simulation.agents["agent-0000"]
        settlement.technologies = []
        simulation.start_production(agent.agent_id, "bread")
        simulation.run(2)
        food_without_technology = settlement.storage["food"]

        settlement.technologies = ["agriculture"]
        agent.job_id = None
        simulation.start_production(agent.agent_id, "bread")
        simulation.run(2)

        self.assertEqual(settlement.storage["food"] - food_without_technology, 3)

    def test_technology_diffuses_only_after_diplomatic_contact(self):
        simulation = self.fixture(population=2, settlement_count=2)
        source = simulation.settlements["settlement-000"]
        target = simulation.settlements["settlement-001"]
        source.technologies = ["agriculture"]

        self.assertFalse(simulation.share_technology(source.settlement_id, target.settlement_id, "agriculture"))
        self.assertNotIn("agriculture", target.technologies)
        simulation.negotiate(source.settlement_id, target.settlement_id, "trade")

        self.assertTrue(simulation.share_technology(source.settlement_id, target.settlement_id, "agriculture"))
        self.assertIn("agriculture", target.technologies)
        self.assertNotIn("technology:agriculture", source.knowledge)
        self.assertEqual(target.knowledge["technology:agriculture"], source.settlement_id)

        source.technologies = ["agriculture", "metalworking"]
        target.technologies = []
        self.assertFalse(simulation.share_technology(source.settlement_id, target.settlement_id, "metalworking"))
        target.technologies = ["agriculture"]
        self.assertTrue(simulation.share_technology(source.settlement_id, target.settlement_id, "metalworking"))

    def test_territory_claims_and_migration_are_explicit(self):
        simulation = self.fixture(population=2, settlement_count=2)
        first = simulation.settlements["settlement-000"]
        second = simulation.settlements["settlement-001"]
        migrant = simulation.agents["agent-0000"]

        self.assertTrue(simulation.claim_territory(first.settlement_id, 2, 2))
        self.assertFalse(simulation.claim_territory(second.settlement_id, 2, 2))
        self.assertTrue(simulation.migrate(migrant.agent_id, second.settlement_id))

        self.assertEqual(migrant.settlement_id, second.settlement_id)
        self.assertIn("2,2", first.territory)
        self.assertTrue(any(event.event_type == "agent_migrated" for event in simulation.events))

    def test_migration_cancels_research_owned_by_the_moving_worker(self):
        simulation = self.fixture(population=2, settlement_count=2)
        migrant = simulation.agents["agent-0000"]
        research_id = simulation.start_research(migrant.agent_id, "agriculture")

        self.assertIsNotNone(research_id)
        self.assertTrue(simulation.migrate(migrant.agent_id, "settlement-001"))

        self.assertNotIn(research_id, simulation.research_jobs)
        self.assertTrue(any(event.event_type == "research_cancelled" and event.payload["reason"] == "researcher_migrated" for event in simulation.events))

    def test_trade_between_settlements_requires_treaty(self):
        simulation = self.fixture(population=2, settlement_count=2)
        buyer = simulation.agents["agent-0000"]
        seller = simulation.settlements["settlement-001"]
        seller.storage["food"] = 3

        self.assertFalse(simulation.buy_good(buyer.agent_id, seller.settlement_id, "food", 1))
        simulation.negotiate(buyer.settlement_id, seller.settlement_id, "trade")
        self.assertTrue(simulation.buy_good(buyer.agent_id, seller.settlement_id, "food", 1))
        self.assertEqual(buyer.inventory["food"], 1)
        self.assertEqual(simulation.settlements[buyer.settlement_id].demand.get("food", 0), 0)
        relation = simulation.settlements[buyer.settlement_id].relations[seller.settlement_id]
        self.assertTrue(relation["memory"])
        self.assertEqual(relation["memory"][-1]["kind"], "trade")

    def test_conflict_injures_and_can_transfer_territory_without_creating_assets(self):
        simulation = self.fixture(population=2, settlement_count=2, combat_damage=120)
        attacker = simulation.settlements["settlement-000"]
        defender = simulation.settlements["settlement-001"]
        defender_agent = simulation.agents["agent-0001"]
        attacker_agent = simulation.agents["agent-0000"]
        defender_agent.health = 100
        attacker_agent.health = 100
        simulation.claim_territory(defender.settlement_id, 4, 4)
        money_before = simulation.invariants()["total_money"]
        goods_before = simulation.invariants()["goods"]

        simulation.declare_conflict(attacker.settlement_id, defender.settlement_id)
        winner = simulation.resolve_conflict(attacker.settlement_id, defender.settlement_id)

        self.assertEqual(winner, attacker.settlement_id)
        self.assertFalse(defender_agent.alive)
        self.assertIn("4,4", attacker.territory)
        self.assertNotIn("4,4", defender.territory)
        self.assertEqual(simulation.invariants()["total_money"], money_before)
        self.assertEqual(simulation.invariants()["goods"], goods_before)
        relation = simulation.settlements[attacker.settlement_id].relations[defender.settlement_id]
        self.assertTrue(any(item["kind"] == "combat" for item in relation["memory"]))

    def test_checkpoint_replay_matches_uninterrupted_state_and_events(self):
        config = ColonyConfig(seed=41, population=4, settlement_count=2, adult_age=2)
        source = ColonySimulation(config).run(2)
        checkpoint = source.checkpoint()
        uninterrupted = ColonySimulation(config).run(5)

        replayed = ColonySimulation.replay_checkpoint(checkpoint, 3)

        self.assertEqual(replayed["tick"], uninterrupted.tick)
        self.assertEqual(replayed["state_hash"], uninterrupted.state_hash())
        self.assertEqual(replayed["event_hash"], uninterrupted.event_hash())
        self.assertEqual(checkpoint["tick"], 2)

    def test_checkpoint_cadence_and_multi_seed_report_are_explicit(self):
        simulation = self.fixture(population=2, settlement_count=1)
        checkpoints = simulation.run_checkpoints(5, 2)
        report = ColonySimulation.evaluate_seeds(simulation.config, [1, 2, 3], 3)

        self.assertEqual(sorted(checkpoints), [0, 2, 4, 5])
        self.assertEqual(report["sample_size"], 3)
        self.assertEqual(report["steps"], 3)
        self.assertEqual(report["world"]["width"], simulation.config.width)
        self.assertIn("event_totals", report["emergence_metrics"])

    def test_benchmark_report_contains_workload_warmup_repetitions_and_memory(self):
        report = ColonySimulation.benchmark(self.fixture(population=2, settlement_count=1).config, ticks=2, repetitions=2, warm_up=1)

        self.assertEqual(report["ticks"], 2)
        self.assertEqual(report["warm_up"], 1)
        self.assertEqual(report["repetitions"], 2)
        self.assertIn("median", report["seconds"])
        self.assertIn("p95", report["seconds"])
        self.assertIn("peak_memory_bytes", report)

    def test_full_snapshot_round_trip_and_resume(self):
        config = ColonyConfig(seed=91, population=4, settlement_count=2, adult_age=2, fertility_start=2)
        checkpoint = ColonySimulation(config).run(3)
        uninterrupted = ColonySimulation(config).run(6)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "colony.json"
            checkpoint.save_json(path)
            loaded = ColonySimulation.load_json(path)
            loaded.run(3)

        self.assertEqual(loaded.canonical_json(), uninterrupted.canonical_json())

    def test_invalid_full_snapshot_is_rejected(self):
        simulation = self.fixture().run(1)
        snapshot = simulation.snapshot()
        snapshot["schema_version"] = 999

        with self.assertRaises(SnapshotValidationError):
            ColonySimulation.from_snapshot(snapshot)

        snapshot = simulation.snapshot()
        snapshot["agents"] = []
        with self.assertRaises(SnapshotValidationError):
            ColonySimulation.from_snapshot(snapshot)

        snapshot = simulation.snapshot()
        snapshot["events"][0]["tick"] = 1
        snapshot["events"][1]["tick"] = 0
        with self.assertRaises(SnapshotValidationError):
            ColonySimulation.from_snapshot(snapshot)

        snapshot = simulation.snapshot()
        resource_position = next(iter(snapshot["resources"]))
        snapshot["resources"][resource_position] = 123
        with self.assertRaises(SnapshotValidationError):
            ColonySimulation.from_snapshot(snapshot)

    def test_checkpoint_replay_does_not_mutate_checkpoint_relation_memory(self):
        simulation = self.fixture(population=4, settlement_count=2).run(5)
        checkpoint = simulation.checkpoint()
        before = checkpoint["state_hash"]

        first = ColonySimulation.replay_checkpoint(checkpoint, 3)
        second = ColonySimulation.replay_checkpoint(checkpoint, 3)

        self.assertEqual(first["state_hash"], second["state_hash"])
        self.assertEqual(checkpoint["state_hash"], before)


if __name__ == "__main__":
    unittest.main()
