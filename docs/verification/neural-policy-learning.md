# Neural Policy Learning — verification

Status: implementation verification for `codex/agent-development-foundation`.
Verdict: PASS — local checks and the independent quality gate passed after the final remediation.

## Evidence

The phase was implemented after inspecting the legacy `neuralnetwork.py` and
confirming that the active engine previously selected actions from scalar
heuristics. The active engine now constructs resident and settlement
`NNetwork` controllers, selects from their action outputs, applies explicit
environment rewards, updates weights, and persists the weights in schema 5 JSON
snapshots. Child resident brains use seeded crossover and bounded mutation.
Pygame and headless training both advance the same `ColonySimulation.step()`
path.

## Commands and outcomes

All commands were run from the repository root with the bundled Python runtime:

```text
C:\Users\kulin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m unittest discover -s tests -v
68 tests, OK, 5.810s

C:\Users\kulin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m unittest tests.test_neuralnetwork -v
9 tests, OK

C:\Users\kulin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m unittest tests.test_colony_simulation tests.test_pygame_app -v
37 tests, OK

C:\Users\kulin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m compileall .
exit 0, no compilation errors

C:\Users\kulin\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\cmd\git.exe diff --check
exit 0, only repository LF/CRLF normalization warnings
```

Focused evidence includes: positive reward raises the selected action's
probability, negative reward lowers it; active residents and settlements emit
`policy="neural_network"`, action probabilities, `network=true`, and positive
weight deltas; snapshot round-trip is canonical-identical; schema-4 snapshots
without `brain_weights` receive deterministic migrations (210 weights for
residents and 186 for settlements) while preserving the random stream; a child
receives only parent weights when mutation is disabled; mutation-enabled child
creation changes child policy weights without changing sources; and a
one-window headless run emits `genetic_policy_evolved` events after elite
selection while source policies remain unchanged. Different seeds 37 and 38
produce different three-tick hashes:
`0b96e8f690a25f0c9f1be299fd747f2d9c45277f210b11f444bd6de18089b382` and
`35bff93f6180beff9a98083565dbd396ae6a7eb43fba0240c323fd88e3334a88`.

Headless continuation workload, exact CLI configuration
`seed=7,width=20,height=12,population=4,settlement_count=2,max_age=200` plus
the CLI's documented defaults for the remaining config fields, 100 windows × 20
ticks, `terminal_mode=continue_after_game_over`:

```text
C:\Users\kulin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe fast_training.py --seed 7 --generations 100 --ticks-per-generation 20 --width 20 --height 12 --population 4 --settlements 2 --max-age 200
```

```text
requested=100, executed=100, ticks=2000, learning_updates=209,
settlement_learning_updates=4000, genetic_updates=0, births=0, deaths=4,
first_terminal_reason=winner, first_terminal_tick=23,
first_terminal_winner=settlement-000, post_terminal_ticks=1977,
neural_weights=210,
same_seed_equal=true,
state_hash=f8fffa608de813fbe78882b3d1230ac90347b31c24ce89bc389d691843d8c8ad,
event_hash=974df0b150e48c71a532a6e8bf02cf6b2c4cf1f5c0bbe7e0687eed6fd9c634f5,
neural_state_hash=842b28432fc5850d06f1ffd52a15c4547f7288ff674f13d0503393ab90efaf87
```

The same-seed comparison was performed by running the exact workload twice;
the final hashes were equal. This particular workload reached extinction and
therefore produced no birth event; the parent-derived child path and a
controlled three-window run with 10 births and 7 genetic policy events are
covered by the deterministic focused test.

The Pygame dummy-display tests passed in the full suite, including the UI
header's neural-policy status and the observation-only keyboard contract.

## Requirement trace

| Requirement | Evidence | Result |
|---|---|---|
| REQ-001 active neural decision source | Active simulation test and `agent_decision.policy` | PASS |
| REQ-002 seeded/replay determinism | Canonical snapshot tests and same-seed 100-window run | PASS |
| REQ-003 reward learning | Primitive direction test and `weight_delta` event assertion | PASS |
| REQ-004 ownership/persistence/migration | Schema round-trip and v4 migration tests | PASS |
| REQ-005 genetic transfer | Mutation-enabled child, parent immutability, and controlled headless elite-selection run | PASS |
| REQ-006 UI/headless shared path | Pygame tests and `run_training` workload | PASS |
| REQ-007 observable evidence | Probability, reward, network marker, deltas, and separate neural-state hash | PASS |
| REQ-008 regression/evaluation coverage | 68-test suite, focused run, headless evidence | PASS |

## Baseline and limitations

The final `compileall .` and native `git diff --check` both exited successfully;
the latter emitted only LF/CRLF normalization warnings. A real display is not
required; the bounded dummy-display Pygame check is the reproducible UI check.
Recurrent memory and cross-run population selection remain roadmap work and are
not claimed as implemented by this phase.
