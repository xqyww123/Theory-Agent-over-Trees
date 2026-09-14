# Hand-off into plan §7 step 5 (2026-09-14)

Where things stand: the design of the entry point is final and reviewed —
MODULE_STRUCTURE §2.6 and §5 (the launcher `isabelle TAT_new` / `isabelle
TAT`, the boot `ML/TAT_Boot.ML`, the protocol commands `TAT.boot` and
`TAT.start`, `TAT.finished` and the exit codes), ARCHITECTURE §9,
EVALUATOR_DESIGN §6 (measured; data in PARALLEL_PROOFS_MEASUREMENT.md),
FIRST_END_TO_END_RUN_PLAN §7 step 5. Nothing of step 5 is implemented yet.

## Owner's standing permissions for this work

- `isabelle TAT` may be run at will (it may build a base heap).
- `isabelle scala_build` may be run at will, for this component.
- `isabelle ML_process` was used for measurements; `isabelle build` stays
  forbidden except `repl_server.sh`.
- Test framework: the author's call (plan §7 step 5 names the shape).

## Implementation order

1. ML: `ML/TAT_Boot.ML`; `TAT.start` in `TAT_Framework.ML`; `start` taking
   a list of theories (registrations deduplicated by serial); `start'` not
   flattening `Remote_Calling_Failure` into one `error`;
   `check_parallel_proofs` asserting `< 3`; `TAT.finished (rc, messages)`
   on every path.
2. Scala: `src/scala/tat.scala` (`TAT_new`, `TAT`), `etc/build.props`,
   `lib/tat.jar` committed, `etc/settings` classpath line.
3. Python: `launch_TAT` (lock, `Conversation`, `Forest_Store` on
   `TAT.sqlite`, plugins, `Forest`, server, served line), `mcp_server.py`,
   `mcp.py` tools, `isabelle_driver.call` shield, `plugin.py` registry vs
   table.
4. Tests: one Python RPC host, then one `isabelle TAT` with `RPC_Host`
   exported, the `mcp` SDK's Streamable HTTP client; retire
   `test/run_ml_framework_test.py` and `test/routing_forest.py`.

## To propose to the owner when reached

- Isabelle_RPC: a distinct ML exception for the connection closing, so
  `TAT.finished`'s code is decided without parsing the library's message
  text (`Tools/RPC.ML:571-572` vs `:594-596` differ only in the message).
- `docs/node_classes/THEOREM.md`: untracked draft, to discuss before the
  `Theorem` class.

## To verify at the first run (from the reviews)

`parallel_proofs` inside the loader after the boot's restore; a missing
base heap is built and found; the served line reaches the terminal; the
exit codes (clean ending, exception, each pre-flight refusal, Ctrl-C,
process death without `TAT.finished`); a mistyped `-P` ends with a message
naming the theory; `editor_tracing_messages=0` is load-bearing; a plugin
declared only under a `-d` ROOT resolves; `Scala.function` calls during
the boot's load complete; whether `init_build`'s print modes change any
approved rendering (RENDER_BASELINES); start latency on a stock HOL heap.
