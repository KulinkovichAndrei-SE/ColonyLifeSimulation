import json
import unittest
from pathlib import Path

import numpy as np

from colony_simulation import (
    AGENT_ACTIONS,
    NEURAL_HIDDEN_COUNT,
    NEURAL_INPUT_COUNT,
    NEURAL_WEIGHT_COUNT,
    SETTLEMENT_WEIGHT_COUNT,
    ColonyConfig,
    ColonySimulation,
)
from neuralnetwork import NNetwork


class NeuralNetworkTests(unittest.TestCase):
    def test_policy_gradient_moves_probability_in_reward_direction(self):
        zero_weights = [0.0] * NNetwork.getTotalWeights(3, 4, 2)

        positive = NNetwork(3, 4, 2, weights=zero_weights)
        before_positive = float(positive.predict([1.0, 0.0, 0.0])[0])
        positive.learn([1.0, 0.0, 0.0], 0, 1.0)
        self.assertGreater(float(positive.predict([1.0, 0.0, 0.0])[0]), before_positive)

        negative = NNetwork(3, 4, 2, weights=zero_weights)
        before_negative = float(negative.predict([1.0, 0.0, 0.0])[0])
        negative.learn([1.0, 0.0, 0.0], 0, -1.0)
        self.assertLess(float(negative.predict([1.0, 0.0, 0.0])[0]), before_negative)

    def test_explicit_weight_network_does_not_touch_global_numpy_rng(self):
        weights = [0.0] * NNetwork.getTotalWeights(3, 4, 2)
        np.random.seed(123)
        before = np.random.get_state()
        network = NNetwork(3, 4, 2, weights=weights)
        network.predict([0.0, 0.0, 0.0])
        after = np.random.get_state()
        self.assertEqual(before[0], after[0])
        self.assertTrue(np.array_equal(before[1], after[1]))
        self.assertEqual(before[2:], after[2:])

        np.random.seed(456)
        before_active = np.random.get_state()
        ColonySimulation(ColonyConfig(seed=7, population=2, settlement_count=1)).step()
        after_active = np.random.get_state()
        self.assertTrue(np.array_equal(before_active[1], after_active[1]))
        self.assertEqual(before_active[0], after_active[0])
        self.assertEqual(before_active[2:], after_active[2:])

    def test_active_simulation_uses_and_persists_neural_policy(self):
        config = ColonyConfig(seed=17, population=2, settlement_count=1, adult_age=2, max_age=30)
        simulation = ColonySimulation(config)
        before = {agent.agent_id: agent.brain_weights for agent in simulation.alive_agents}
        settlement_before = simulation.settlements["settlement-000"].brain_weights

        simulation.step()

        self.assertEqual(len(before["agent-0000"]), NEURAL_WEIGHT_COUNT)
        self.assertTrue(any(before[agent.agent_id] != agent.brain_weights for agent in simulation.alive_agents))
        self.assertEqual(len(settlement_before), SETTLEMENT_WEIGHT_COUNT)
        self.assertNotEqual(settlement_before, simulation.settlements["settlement-000"].brain_weights)
        decision = next(event for event in simulation.events if event.event_type == "agent_decision")
        learning = next(event for event in simulation.events if event.event_type == "learning_updated")
        self.assertEqual(decision.payload["policy"], "neural_network")
        self.assertEqual(len(decision.payload["probabilities"]), len(AGENT_ACTIONS))
        self.assertAlmostEqual(sum(decision.payload["probabilities"]), 1.0, places=5)
        self.assertTrue(learning.payload["network"])
        self.assertGreater(learning.payload["weight_delta"], 0.0)
        settlement_decision = next(event for event in simulation.events if event.event_type == "settlement_decision")
        settlement_learning = next(event for event in simulation.events if event.event_type == "settlement_learning_updated")
        self.assertEqual(settlement_decision.payload["policy"], "neural_network")
        self.assertEqual(len(settlement_decision.payload["probabilities"]), 6)
        self.assertTrue(settlement_learning.payload["network"])

        restored = ColonySimulation.from_snapshot(simulation.snapshot())
        self.assertEqual(restored.canonical_json(), simulation.canonical_json())

    def test_schema_v4_agents_receive_deterministic_migrated_brains(self):
        fixture_path = Path(__file__).with_name("fixtures") / "colony_schema4_legacy.json"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        first = ColonySimulation.load_json(fixture_path)
        second = ColonySimulation.load_json(fixture_path)
        self.assertEqual(
            [agent.brain_weights for agent in first.agents.values()],
            [agent.brain_weights for agent in second.agents.values()],
        )
        self.assertTrue(all(len(agent.brain_weights) == NEURAL_WEIGHT_COUNT for agent in first.agents.values()))
        self.assertTrue(all(len(settlement.brain_weights) == SETTLEMENT_WEIGHT_COUNT for settlement in first.settlements.values()))
        self.assertTrue(first.config.ai_enabled)
        self.assertEqual(first.random.get_state(), fixture["random_state"])

    def test_child_brain_is_parent_derived_without_mutating_parents(self):
        simulation = ColonySimulation(
            ColonyConfig(seed=23, population=2, settlement_count=1, mutation_percent=0)
        )
        mother = simulation.agents["agent-0000"]
        father = simulation.agents["agent-0001"]
        mother.pregnancy_remaining = 1
        mother.pregnancy_partner_id = father.agent_id
        mother.pregnancy_partner_genome = father.genome
        mother_weights = mother.brain_weights
        father_weights = father.brain_weights

        child_id = simulation._birth(mother)

        self.assertIsNotNone(child_id)
        child = simulation.agents[child_id]
        self.assertEqual(len(child.brain_weights), NEURAL_WEIGHT_COUNT)
        self.assertTrue(all(weight in {left, right} for weight, left, right in zip(child.brain_weights, mother_weights, father_weights)))
        self.assertEqual(mother.brain_weights, mother_weights)
        self.assertEqual(father.brain_weights, father_weights)
        self.assertEqual(child.learned_policy, {})

    def test_mutation_changes_child_policy_without_touching_sources(self):
        simulation = ColonySimulation(
            ColonyConfig(seed=31, population=2, settlement_count=1, mutation_percent=100)
        )
        mother = simulation.agents["agent-0000"]
        father = simulation.agents["agent-0001"]
        mother.brain_weights = tuple(0.0 for _ in mother.brain_weights)
        father.brain_weights = tuple(0.0 for _ in father.brain_weights)
        mother.pregnancy_remaining = 1
        mother.pregnancy_partner_id = father.agent_id
        mother.pregnancy_partner_genome = father.genome

        child_id = simulation._birth(mother)

        self.assertTrue(any(value != 0.0 for value in simulation.agents[child_id].brain_weights))
        self.assertTrue(all(value == 0.0 for value in mother.brain_weights))
        self.assertTrue(all(value == 0.0 for value in father.brain_weights))

    def test_different_seeds_change_neural_trajectory(self):
        base = dict(population=2, settlement_count=1, max_age=200)
        first = ColonySimulation(ColonyConfig(seed=37, **base)).run(3)
        second = ColonySimulation(ColonyConfig(seed=38, **base)).run(3)
        self.assertNotEqual(first.state_hash(), second.state_hash())

    def test_headless_generation_selects_and_recombines_policies(self):
        simulation = ColonySimulation(
            ColonyConfig(seed=29, population=4, settlement_count=1, max_age=200, mutation_percent=0)
        )

        report = simulation.run_training(1, ticks_per_generation=1)

        evolved = [event for event in simulation.events if event.event_type == "genetic_policy_evolved"]
        self.assertEqual(report["executed_generations"], 1)
        self.assertEqual(report["neural_state_hash"], simulation.neural_state_hash())
        self.assertEqual(report["final_metrics"]["neural_state_hash"], simulation.neural_state_hash())
        self.assertEqual(report["windows"][0]["neural_state_hash"], simulation.neural_state_hash())
        self.assertTrue(evolved)
        self.assertTrue(all(len(event.payload["parent_ids"]) == 2 for event in evolved))
        self.assertTrue(all(event.payload["generation"] == 1 for event in evolved))

    def test_headless_training_can_reproduce_and_evolve_a_controlled_colony(self):
        simulation = ColonySimulation(
            ColonyConfig(
                seed=41,
                width=20,
                height=12,
                population=4,
                settlement_count=1,
                adult_age=2,
                fertility_start=2,
                fertility_end=25,
                max_age=200,
                gestation_ticks=1,
                perception_radius=5,
            )
        )
        simulation.settlements["settlement-000"].storage["food"] = 100
        residents = list(simulation.agents.values())
        for resident in residents:
            resident.age = 8
            resident.x = resident.y = 5
            resident.affinity.update({other.agent_id: 1.0 for other in residents if other.agent_id != resident.agent_id})

        report = simulation.run_training(3, ticks_per_generation=2, terminal_mode="continue_after_game_over")

        self.assertEqual(report["executed_generations"], 3)
        self.assertGreater(sum(event.event_type == "child_born" for event in simulation.events), 0)
        self.assertGreater(sum(event.event_type == "genetic_policy_evolved" for event in simulation.events), 0)


if __name__ == "__main__":
    unittest.main()
