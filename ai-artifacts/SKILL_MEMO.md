# Memo for the SKILL files

What the SKILL files TAT will give its agents have to say. A list of
points, each with where it was decided; no wording here is approved, and
the SKILL files themselves are not written yet. Add a point when a
decision produces something an agent must be told.

## Must say

- **No worktree.** An agent does not use `EnterWorktree`, and does not
  start a subagent with `isolation: "worktree"`: the tool is disabled and
  every worktree creation fails, with
  `TAT does not allow git worktrees. Start the subagent without worktree isolation.`
  (CLIENT_HOOKS.md §5). The owner, 2026-10-02: 「在最终我们要给的
  SKILL files 中要提及不能使用 worktree」 (LOGGING_DECISIONS.md, "The
  review").
- **After a compaction, read the briefing.** An agent whose context was
  replaced calls `recall` with no id; TAT pushes nothing
  (CONSTRUCT_INTERACTION §8, PRINT.md §5, RECALL.md;
  CONSTRUCT_DECISIONS.md:609).

## Candidates — what the agent directory design does to an agent

Decided in LOGGING_DECISIONS.md and CLIENT_HOOKS.md §5; whether a SKILL
file says each of them is not decided.

- The agent reads and writes files only inside the directory it was
  started in; the Isabelle sessions it works on are reached through TAT's
  tools alone, and their `.thy` files are not visible to it.
- A file tool's write outside that directory, or to the client's own
  files in it (`.mcp.json`, `.claude/`), is refused.
- Programs installed among the user's files — an `isabelle` under `/home`
  among them — are not found by the agent's shell.
- The shell has the network.
- On Codex the shell has no `/tmp`; a temporary file goes in the agent's
  own directory. On Claude Code `/tmp` is readable and only the client's
  own temp directory under it is writable.
- In a folder the user has not trusted, Claude Code in its default mode
  refuses a shell command it cannot analyse — one with a subshell, or
  `…; echo $?` — and the agent rewrites it as a simple command.
