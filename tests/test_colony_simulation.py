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


if __name__ == "__main__":
    unittest.main()
