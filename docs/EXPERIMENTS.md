# Experiments

Measured facts, as opposed to facts read out of source. Each entry records what
was run, what was observed, and what it settles.

## 1. Full-text `didChange` destroys PIDE's prefix reuse

**Question.** Isabelle-MCP syncs file changes as `textDocument/didChange` with
the whole document text and no range
(`Isabelle-MCP/src/isabelle_mcp/lsp_client.py:1327`,
`contentChanges: [{"text": content}]`), which becomes
`Text.Edit.replace(0, whole, whole)` on the server — remove-all plus insert-all
(`Pure/PIDE/text.scala:148-150`). Does that defeat PIDE's reuse of the
unchanged prefix?

Source reading gave two conflicting answers, so it was measured.

**Setup.** A theory with a deliberately slow `ML` command early and three trivial
`by simp` lemmas after it; session `HOL` (which does not precompile it).

```
theory PrefixTest imports Main begin
ML ‹OS.Process.sleep (Time.fromSeconds 15)›   (* line 5 — slow, early *)
lemma a1: "(1::nat) + 1 = 2" by simp
lemma a2: "(2::nat) + 2 = 4" by simp
lemma a3: "(3::nat) + 3 = 6" by simp          (* line 13 — the one edited *)
end
```

**Result — timings through the MCP tools.**

| Action | Wall to `complete` |
| --- | --- |
| first full evaluation | ~24.7 s (the 15 s sleep ran) |
| edit **only** `a3`, re-evaluate | **12.8 s** |
| re-evaluate with **no** edit (control) | ~0 s |
| edit **only** `a3` again | **13.9 s** |
| edit line 5, sleep 15 -> 6 (positive control) | 5.7 s |
| edit **only** `a3`, sleep now 6 | **9.9 s** |

The no-edit control returns instantly, so `evaluate_to` does not itself force
re-execution — the *edit* does. The positive control tracks the real work
(6 s sleep -> 5.7 s), so the timing method detects re-execution.

**Corroborating signals.** Immediately after editing only the last lemma, the
early command is running again from zero:

```
1 command(s) running.
  …/PrefixTest.thy:5 (4s) ML ‹OS.Process.sleep (Time.fromSeconds 15)›
  running: 5
  pending: 7, 9, 11, 13
```

And a non-timing probe: the early `ML` block was changed to append a line to a
log file. The log was deleted, **only** `a3` was edited, and the theory
re-evaluated — the log reappeared. The early command literally re-executed.

**Isolation — the cause is the full-text form, not PIDE.** `isabelle mcp_server`
was then driven directly over LSP with the same theory and the *same* edit
delivered two ways. The edit makes `a3` false so that `by simp` must fail, which
proves the edit really reached the server in both modes.

| mode | early command | error diagnostic |
| --- | --- | --- |
| one `contentChange`, whole document, no range (what Isabelle-MCP sends) | **re-ran after 0.4 s** | at line 13 |
| one `contentChange` with an LSP range covering just the `a3` line | **did not re-run within 40 s** | at line 13 |

**Verdict.** Prefix reuse is destroyed on the Isabelle-MCP path. PIDE's own
prefix reuse is *intact* — a ranged `didChange` reuses it perfectly. The
full-document `contentChanges` form at `lsp_client.py:1327` is causally
responsible.

This contradicts `Isabelle-MCP/docs/PIDE_MCP_COMPARISON.md:106-123`, which claims
of both servers that neither "re-runs a whole theory on every edit". That claim
is true of PIDE and false of Isabelle-MCP as it currently sends edits.

**Consequence for TAT.** As things stand, editing one node costs a full
re-execution of its theory from `begin` — the cost of an edit is the cost of the
whole file, not of the tail. See ARCHITECTURE §9.
