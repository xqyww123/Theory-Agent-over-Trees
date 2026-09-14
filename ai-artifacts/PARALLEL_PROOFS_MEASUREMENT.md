# `parallel_proofs` under `Thy_Info.use_theories`, measured

Measured 2026-09-14 on stock Isabelle2025-2, `isabelle ML_process -l HOL`
(`Multithreading.max_threads () = 8`, so theory bodies run on Future
workers), one process per cell, `Multithreading.parallel_proofs := n` set
before the call. The evidence for EVALUATOR_DESIGN §6's first condition.

Theories, each `imports Main`: `Bad_Terminal` (`lemma bad: "(1::nat) = 2"
by simp`), `Bad_Structured` (the same statement, `by simp` inside
`proof - show ?thesis … qed`), `Good` (`(1::nat) = 1 by simp`), and
`Dependent` (`imports Bad_Terminal`, `lemma derived: "False" using bad by
simp`). Call form: `Thy_Info.use_theories (Options.default ()) ""
[(name, Position.none)]` with the directory of the files as the current
directory; a loaded theory is registered under its bare short name.

## One call on a failing theory

| level | `use_theories` | theory committed | error text |
| --- | --- | --- | --- |
| 0 | raises | no | only inside the raised message |
| 1 | raises | no | printed before the call returns, with `At command` |
| 2 | raises | no | printed before the call returns, with `At command` |
| 3 | raises | **yes** | printed, without `At command` |

Same for both failing theories. At 3 the committed theory holds the false
theorem (`thm bad: 1 = 2` retrievable), and `Dependent`, proving `False`
from it, is committed too; the exception then still names `Bad_Terminal`'s
line. `Good` returns normally and is committed at every level.

## The next call after a failing one

| level | call 1 (bad) | call 2 (`Good`) | call 3 (`Good`) |
| --- | --- | --- | --- |
| 0 | raises | returns | returns |
| 1 | raises | **raises with call 1's error**, `Good` committed | returns |
| 2 | raises | **raises with call 1's error**, `Good` committed | returns |
| 3 | raises | returns | returns |

An explicit `maps Task_Queue.group_status (Execution.reset ())` between the
calls drains one residual failure at 1 and 2 (none at 0 and 3) and makes
call 2 return normally.

## Conclusion

The property the loader needs — a failing load raises and commits nothing —
holds at 0, 1 and 2 and fails at 3, in the commit rather than in the
reporting. The residue that `Loader.load`'s drain removes arises at 1 and
2. Hence the condition is `parallel_proofs` below 3, not equal to 1.
