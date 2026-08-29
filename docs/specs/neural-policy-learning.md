# Neural Policy Learning

Status: implemented on branch `codex/agent-development-foundation`.
Owner: Maintainer / primary agent
Base commit: `cf894816fc6c7c5b197318205904afde0574cd4b`
Last updated: 2026-08-29

## Scope and evidence

The legacy prototype contains `neuralnetwork.py` and constructs `NNetwork` instances, but the active `ColonySimulation` currently chooses resident actions through hand-written scores and only updates a scalar `learned_policy` summary. This phase connects the neural policy to the active deterministic engine and adds genetic transfer between generations. Pygame and headless execution must remain views/orchestrators of the same simulation rules.

## Implemented baseline

- The active engine has explicit resident actions, rewards, seeded randomness, snapshots, births, and a headless generation runner.
- The legacy `NNetwork` can perform a forward pass but has no deterministic initialization contract or learning update and is not used by the active engine.
- The active engine emits decision and learning events that the UI can observe.

## Requirements

### REQ-001 — Neural policy is the active resident decision source

For every eligible living resident and every settlement while `ai_enabled` is true, the engine must build a fixed-size observation vector, run the owning neural network, and select an action from the network output. The old action-score table must not select resident or settlement actions. Action execution remains constrained by world rules such as available resources, valid locations, and survival feasibility.

### REQ-002 — Deterministic, seeded networks

Network initialization, exploration/tie-breaking, and learning must be reproducible from the simulation seed. Two simulations with equal configuration and seed must produce equal state/event hashes after equal ticks. No domain decision may use global wall-clock or unseeded randomness.

### REQ-003 — Online reward learning

After each selected action, the engine must calculate the existing explicit environment reward, update the resident network weights using a documented learning rule, and emit `learning_updated` containing the action, reward, network marker, and enough information to observe that weights changed. Learning must not mutate the inherited genome directly.

### REQ-004 — Neural state ownership and persistence

Network weights belong to each resident and settlement controller, are included in snapshots, are validated for finite numeric values and expected architecture, and round-trip without drift. Snapshot schema version 5 must support migration of version 4 snapshots that do not contain neural weights by deterministically creating weights from the simulation seed and actor identity. Unsafe pickle loading remains forbidden.

### REQ-005 — Genetic transfer between generations

When a child is born, its neural genome must be derived from its parents' network weights by deterministic crossover and mutation, while the child's episodic memory and scalar learned-policy telemetry start fresh. At the end of each headless training generation, each settlement must select an elite resident subset by an explicit fitness signal and recombine/mutate policies for the non-elite residents. Mutation must use the simulation random source, be bounded, and leave source parents unchanged. The inherited biological genome and neural policy weights remain separate fields.

### REQ-006 — Same policy in UI and headless modes

Pygame ticks and `run_training()` ticks must call the same active neural decision path. UI controls may start/stop/accelerate or inspect state, but must not inject scripted resident actions or a second learning implementation. The UI must identify that neural learning is enabled when it is enabled.

### REQ-007 — Observable learning evidence

Decision events must expose the chosen action and output probabilities/scores for residents and settlements. Learning events must expose reward and a measurable weight-change signal. A deterministic headless run must be able to report learning update counts and final neural-state hashes without opening a display.

### REQ-008 — Regression and evaluation coverage

Automated tests must cover forward-pass shape, deterministic learning direction, active network use, weight mutation after a rewarded/penalized action, snapshot round-trip and version-4 migration, parent immutability during child creation, equal-seed replay, and a multi-generation headless smoke run. Verification must record commands, seed, configuration, and outcomes.

## Acceptance criteria

1. A focused deterministic test proves active resident and settlement weights change after an AI tick and their emitted decisions contain probability vectors.
2. A focused test proves positive reward raises the selected action's probability for the same observation and negative reward lowers it.
3. Snapshot round-trip preserves neural weights exactly under canonical serialization; a version-4 fixture loads with deterministic migrated weights.
4. Child creation and headless generation evolution produce bounded, deterministic parent/elite-derived networks with at least one possible mutation and do not modify source policies.
5. Two equal-seed headless runs are identical; a different seed can produce a different neural trajectory.
6. The existing full suite and a documented headless multi-generation run pass, with no display required.

## Deferred roadmap

- More expressive recurrent memory, explicit curiosity, and a population-wide evolutionary selection loop across complete simulated runs.
- Neural policy visualization beyond probabilities, update counts, and hashes.
