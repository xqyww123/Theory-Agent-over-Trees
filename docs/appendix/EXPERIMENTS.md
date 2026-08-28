# Experiments

Measured facts, as opposed to facts read out of source.

## 1. A whole-document `didChange` destroys PIDE's prefix reuse

Isabelle-MCP syncs every file change as `textDocument/didChange` carrying the
whole document with no range
(`contrib/Isabelle-MCP/src/isabelle_mcp/lsp_client.py:1327`). On the server that
becomes `Text.Edit.replace(0, whole, whole)` — remove-all plus insert-all
(`contrib/Isabelle2025-2/src/Pure/PIDE/text.scala:148-150`).

### Setup

A theory whose first command is slow and observable, followed by three trivial
lemmas. Session `HOL`, which does not precompile it. The `ML` block appends to a
log file and then sleeps, so re-execution leaves a trace independent of timing.

```
 1  theory PrefixProbe
 2    imports Main
 3  begin
 4
 5  ML \<open>
 6  val _ = File.append (Path.explode ".../probe.log") "EARLY\n";
 7  val _ = OS.Process.sleep (Time.fromSeconds 8);
 8  \<close>
 9
10  lemma a1: "(1::nat) + 1 = 2" by simp
11
12  lemma a2: "(2::nat) + 2 = 4" by simp
13
14  lemma a3: "(3::nat) + 3 = 7" by simp
15
16  end
```

`a3` is false, so `by simp` must fail. That failure is the receipt showing the
edit reached the server, in both arms of the comparison below.

### Result 1: the early command re-executes

The log was deleted, **only line 14** was edited, and the theory re-evaluated.
The log reappeared: the `ML` block at lines 5-8 ran again, although nothing
above line 14 had changed.

`isabelle_evaluation_status` showed the same thing directly, reporting the early
command as running again with a fresh elapsed counter.

### Result 2: a ranged edit does not cause it

`isabelle mcp_server` was then driven directly over LSP, with the same edit to
line 14 delivered two ways.

| how the edit was sent | early command | error diagnostic |
| --- | --- | --- |
| one `contentChange`, whole document, no range | **re-ran after 0.4 s** | on the edited line |
| one `contentChange` with a range covering only that line | **did not re-run within 40 s** | on the edited line |

The diagnostic appears in both arms, so the edit was applied in both. The only
difference is whether the early command ran again.

### Conclusion

PIDE's prefix reuse works. The whole-document `contentChanges` form is what
defeats it.

`contrib/Isabelle-MCP/docs/PIDE_MCP_COMPARISON.md:106-123` states that neither
server re-runs a whole theory on every edit. That holds for PIDE and not for
Isabelle-MCP as it currently sends edits.

### What this experiment does not establish

Wall-clock timings were also collected, and they are not reported here: the
measured durations were shorter than the sleep they were supposed to contain,
which means the clock was not measuring what it appeared to measure. The two
results above do not depend on them. Anyone wanting a cost figure for the
re-execution must measure it again, with the timing boundaries pinned down.

## 2. Evaluation is bounded by the caret

`isabelle_evaluate_to(file, line)` does not merely wait until checking reaches
that line. Commands after it are not executed at all until the caret moves.

### Setup

Two mirror-image `ML` blocks, one before the target line and one after. Each
appends to its own log and sleeps. The early block proves the mechanism works —
path, permissions, cartouche syntax — so an absent late log cannot be blamed on
a broken probe.

```
 1  theory CaretTest
 2    imports Main
 3  begin
 4
 5  ML \<open>
 6  val _ = File.append (Path.explode ".../early.log") "EARLY\n";
 7  val _ = OS.Process.sleep (Time.fromSeconds 1);
 8  \<close>
 9
10  lemma a1: "(1::nat) + 1 = 2" by simp        <-- the target
11
12  ML \<open>
13  val _ = File.append (Path.explode ".../late.log") "LATE\n";
14  val _ = OS.Process.sleep (Time.fromSeconds 3);
15  \<close>
16
17  lemma a2: "(2::nat) + 2 = 4" by simp
18
19  end
```

### Result

`evaluate_to(line=10)` reported `Evaluation complete, arrived at line 10.` and
`clean`. `early.log` was written. `late.log` did not appear — after 91 seconds
of idling in the first run, and 95 seconds in a second run from a freshly
launched session.

Moving the caret to end of file then reported, before completing:

```
pending: 12-15, 17, 19
```

Every command past the old caret was still unexecuted. `late.log` appeared about
eight seconds later.

### A third confirmation, and a constraint it imposes

`isabelle_command_output` was called on line 12 while the caret was still at
line 10. It does not report the command as unevaluated: it **auto-evaluates**,
and the reply caught the block starting for the first time —

```
1 command(s) running.
  CaretTest.thy:12 (0s) ML \<open> val _ = File.append ...
  running: 12-15
```

`late.log` appeared six seconds later. Probing an unevaluated command is what
makes it run — a property of this route, not of TAT's own evaluator, where
reading a node runs nothing because TAT submits the commands.

### Scope

One file, imported by nothing. Whether a tree that other open trees import is
pushed past its own caret by their requirements was not tested.

`contrib/Isabelle-MCP/docs/PIDE_MCP_COMPARISON.md:106-123` states that
`evaluate_to` bounds waiting rather than execution. That does not describe the
behaviour measured here. `docs/TECH_NOTE.md:186-198`, which says the opposite,
matches it.
