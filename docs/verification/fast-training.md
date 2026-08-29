# Fast headless training verification

Verdict: PASS
Working tree evaluated: `codex/agent-development-foundation`, based on `cf89481`
Last updated: 2026-08-29

## Requirement evidence matrix

| Requirement | Evidence | Result |
|---|---|---|
| REQ-001 | `fast_training.py` runs `ColonySimulation` without importing Pygame. CLI subprocess and import probe passed. | PASS |
| REQ-002 | `run_training()` uses one simulation, one event stream, and one seeded RNG across windows. API final state/event hashes matched uninterrupted 15 ticks. | PASS |
| REQ-003 | Seed 7, 3 windows × 5 ticks produced `(0,5)`, `(5,10)`, `(10,15)`, final tick 15; zero-window no-op passed. | PASS |
| REQ-004 | Runner advances only with explicit `step()` calls and contains no sleep/frame timing/runtime field. | PASS |
| REQ-005 | Window records include population, invariant metrics, event deltas/counts, state hash, and event hash; births/deaths matched `child_born`/`agent_died` deltas. | PASS |
| REQ-006 | CLI emitted one parseable canonical JSON document; stdout matched `canonical_json(report) + "\\n"`. | PASS |
| REQ-007 | Negative/zero/malformed numeric and invalid config inputs returned non-zero with diagnostic stderr and empty stdout. | PASS |
| REQ-008 | Diagnostic mode preserved the partial terminal window; default training continuation executed all requested windows and reported first-terminal/post-terminal metrics. | PASS |
| REQ-009 | Repeated API and CLI invocations with identical inputs produced byte-identical reports and hashes. | PASS |
| REQ-010 | Default UI configurations explicitly pass `ai_enabled=True`; header reports `AI learning: ON`; UI regression confirms `learning_updated` after a tick and action keys remain non-mutating. | PASS |

## Commands and observed results

All commands below used the bundled Python 3.12 runtime at
`C:\Users\kulin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`.

```powershell
& 'C:\Users\kulin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest tests.test_fast_training -v
```

PASS — 11 fast-training tests.

```powershell
& 'C:\Users\kulin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest discover -s tests -v
```

PASS — 59 tests, 2.513 seconds.

Follow-up UI enablement was then made explicit in `pygame_app.py`: default UI
configurations pass `ai_enabled=True`, the header reports `AI learning: ON`, and
the UI regression test confirms a tick emits `learning_updated`. The full suite
was rerun afterward: PASS — 59 tests, 2.513 seconds.

The training terminal policy was then updated: CLI training continues after
`game_over` by default, while `--stop-on-game-over` selects diagnostic stop. The
focused suite passed 11 tests, including both modes and terminal metadata.

```powershell
& 'C:\Users\kulin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -c "import json,subprocess,sys,time; c=[sys.executable,'fast_training.py','--seed','7','--generations','100','--ticks-per-generation','20']; t=time.perf_counter(); p=subprocess.run(c,capture_output=True,text=True); elapsed=time.perf_counter()-t; r=json.loads(p.stdout); print({'returncode':p.returncode,'elapsed_seconds':round(elapsed,3),'requested_generations':r['requested_generations'],'executed_generations':r['executed_generations'],'completed_generations':r['completed_generations'],'executed_ticks':r['executed_ticks'],'learning_updates':r['final_metrics']['event_counts'].get('learning_updated',0),'births':r['final_metrics']['births_total'],'deaths':r['final_metrics']['deaths_total'],'game_over':r['game_over'],'winner':r['winner'],'terminal_reason':r['terminal_reason'],'terminal_winner':r['terminal_winner'],'terminal_tick':r['terminal_tick'],'post_terminal_ticks':r['post_terminal_ticks'],'stdout_bytes':len(p.stdout.encode())})"
```

PASS — 100 requested/executed/completed windows, 2,000 ticks, 298 learning
updates, 3 births, 11 deaths, first terminal winner `settlement-001` at tick 31,
1,969 post-terminal ticks, 2.238 seconds, and 240,311 bytes of canonical JSON.

```powershell
& 'C:\Users\kulin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m compileall colony_simulation.py fast_training.py tests
```

PASS — compilation completed.

```powershell
& 'C:\Users\kulin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -c "import json,subprocess,sys; c=[sys.executable,'fast_training.py','--seed','7','--generations','3','--ticks-per-generation','5','--population','4','--max-age','200']; a=subprocess.run(c,capture_output=True,text=True); b=subprocess.run(c,capture_output=True,text=True); r=json.loads(a.stdout); print({'returncode':a.returncode,'bytes':len(a.stdout.encode()),'byte_identical':a.stdout==b.stdout,'windows':len(r['windows']),'ticks':r['executed_ticks'],'learning_updates':r['final_metrics']['event_counts'].get('learning_updated',0),'terminal':r['terminal_reason']})"
```

PASS — return code 0, 3 windows, 15 ticks, 8,856-byte stdout, byte-identical
repeat, 60 `learning_updated` events, no terminal state.

```powershell
Measure-Command { & 'C:\Users\kulin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' fast_training.py --seed 7 --generations 100 --ticks-per-generation 20 --population 8 --max-age 200 | Out-Null } | Select-Object TotalSeconds
```

PASS — external `Measure-Command` observed 3.78 seconds for this 100-window,
2,000-tick workload with `population=8` and `max-age=200`; continuation completed
all requested windows after game over. No production-scale threshold is claimed.

```powershell
$env:SDL_VIDEODRIVER='dummy'; & 'C:\Users\kulin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' main.py --frames 8
```

PASS — bounded Pygame smoke run exited successfully in the dummy display.

The independent simulation evaluator also returned PASS: focused tests,
compileall, canonical/repeatability probes, 8-seed distinct-hash check, invalid
input checks, no-Pygame import check, terminal fixture, and a bounded performance
probe. Its 100-window probe reached terminal state early, which is an evidence
limitation rather than a failed requirement because no performance threshold is
specified.

The independent quality gate initially returned FAIL because this artifact was
missing, and a later gate flagged the UI edits while the older spec still called
UI out-of-scope. The spec/plan now explicitly include the requested UI learning
enablement as REQ-010. The final native-Git quality gate returned PASS with no
blocking findings; it verified the scoped UI files, all ten requirements, the
100-window continuation, and the 59-test suite.

## Not run / limitations

- No multi-process or concurrent training check was needed; the design is
  intentionally single-owner and sequential.
- Neural snapshot migration is covered by the separate neural-policy phase;
  current snapshots use schema version 5 and the output-only training report
  remains schema version 1.
- The actual biological cohort-generation model, cross-run selection, inherited
  learned policies, and population reset/respawn after extinction remain
  explicitly deferred. Continuing a terminal simulation completes the requested
  workload but does not create new learning once all agents are dead.

## Required remediation

No behavioral or process remediation remains. Commit after maintainer review;
do not include generated reports, caches, or other temporary artifacts.
