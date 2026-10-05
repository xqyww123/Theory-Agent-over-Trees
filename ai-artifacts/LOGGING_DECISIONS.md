# The log: decisions

The owner's decisions on TAT's log and on the agent directory, in the order
they were taken, each with the owner's words. *(author)* marks an internal
shape the author chose and told the owner. What of it is in `docs/` is
listed under "Written", at the end. A later decision amends an earlier one
where it says so: 9's route through `tat.lock` and 10's and 13's `seq` are
gone ("The review").

## What existed before (read 2026-10-01)

- `isabelle_theory_agent` makes no logging call. Three sentences in the
  documents say "logged" with no destination: MODULE_STRUCTURE §2.4
  (`fork_job`: "a task whose report cannot be delivered logs and ends"),
  CONSTRUCT_INTERACTION §7 (an agent left with jobs running) and §8 (a call
  no `PreToolUse` announced).
- The RPC host process, in which TAT's Python side runs, sends the root
  logger to `$ISABELLE_HOME_USER/log/RPC_attached_<token>.log`
  (`contrib/Isabelle_RPC/Isabelle_RPC_Host/rpc.py`, `mk_logger_`); a
  procedure reaches it as `connection.server.logger`.
- The launcher prints the messages `TAT.finished` carried, once, at the end
  (`src/scala/tat.scala`); it echoes nothing else the Isabelle process
  prints.
- AoA (`contrib/Isa-Mini/IsaMini/AoA/model.py`, `Session._setup_log_directory`,
  `_log`, `_log_meta`): one directory per invocation; five YAML files, one
  per category (`interaction`, `proofs`, `proof_oprs`, `retrieval`,
  `missing_lemmas`), plus `meta.jsonl.zst`, which receives every record;
  one method per event (`log_tool_call(tool_name, tool_input)`); the time
  and the role stamped in one place. Nothing deletes old directories:
  15,083 of them, 1 GB, under `~/.isabelle/Isabelle2025-2/log/AoA` on
  2026-10-01.
- The ML side serves the callbacks of one RPC call one at a time
  (`contrib/Isabelle_RPC/Tools/RPC.ML`, `dispatch_loop`): a callback sent
  while another runs waits for it.
- Isabelle/ML has `File.append` and no JSON encoder; Isabelle/Scala has
  both JSON and SQLite, and the launcher already opens `TAT.sqlite`.

## Decided

1. **TAT has a log of its own, with categories, as AoA has.** 「总体上希望
   类似 AoA 那样，有多个 category」.
2. **The format is JSON lines.** 「赞同 jsonl」. Not SQLite, and never
   inside `TAT.sqlite`.
3. **One log per conversation, under `<working directory>/.tat/log/`.**
   「当然是前者。位置赞同 .tat/log/」.
4. **Each category is its own `.jsonl` file.** 「可以分别写到不同的 jsonl
   文件中（类似 AoA 那样分类）」 — said after the first request's 「统一写到
   一个 jsonl」; whether a file holding every record is kept beside them is
   open (below).
5. **The implementation logs generously.** 「建议积极在 TAT 的实现中多写
   各种日志」.
6. **The agent client is configured explicitly to skip `.tat/`.** 「要显示
   配置以跳过 .tat」. How, per client, is being established (below).
7. **A log that cannot be created at start is a `TAT_StartupError`**,
   `TAT cannot write its log under <working directory>: <strerror>`; a
   write that fails later does not touch the conversation and is reported
   once to the RPC host's logger. 「赞同」.
8. **TAT deletes no log.** 「赞同不自动删」. Compression and cleaning wait
   for sizes measured on real runs.

9. **The launcher prints `warning` and `error` records as they are
   written**, by following the files of the running conversation's log
   directory; not through Isabelle, whose ML side serves one callback at a
   time. 「能实时打印吗？」, then 「赞同」 to the proposal. *(author)*: the
   launcher finds the directory through a third line of `tat.lock`, and at
   the end reads what is left before it prints the `TAT.finished` messages.

10. **The Isabelle side writes records too, into the same directory, in a
    file of its own, each with its timestamp.** 「可以让 Isabelle 也写日志进
    我们刚刚讨论的目录下吗？可以是不同的文件，带上时间戳就好」. So
    MODULE_STRUCTURE §2.4's "logs and ends" stands as written. Checked
    2026-10-01: Isabelle/ML has `File.append` and the Basis `Date`, and no
    JSON encoder, nor have the sibling repositories; the ML side is given
    the working directory at `start` and not the conversation's log
    directory. Confirmed 「赞同」: the Isabelle side's file is
    `isabelle.jsonl`, and the Python side's records of round trips go to
    `round_trip.jsonl`; its records carry a timestamp and no `seq`, and
    the files merge by timestamp; it records what the Python side cannot
    see — a callback's own duration, a library theory loaded from source,
    an evaluation job's task, an undelivered report, a `Bug`. *(author)*:
    the Python side tells it the directory through one callback once the
    directory exists; earlier records wait in memory.

11. **No file holds every record.** Each record is written once, in its
    category's file; the whole conversation in order is the files merged
    by timestamp. 「这个都可以，按你推荐的来好了」.

12. **The event tables of LOGGING_PLAN.md §4 are approved**, and a round
    trip's and a tool call's arguments and results are recorded whole,
    never cut. 「批准」「同意全文记录」.

13. **The launcher follows `warning` records only** — narrowing 9: an
    `error` record is what ended the conversation, which the launcher
    prints at the end as it does today, and following it too would print
    it twice. 「赞同你的建议」. Its lines: `Log: <directory>` once the log
    directory is found; `### <message> (<file>, seq <n>)` for a `warning`,
    `(<file>, <time>)` for the Isabelle side's; the ending's messages as
    today.
14. **Three wordings approved** 「批准文案」:
    - `The result of evaluation job <id> could not be reported to the Python side: <failure>`
      (the `isabelle` record `report_undelivered`);
    - `TAT could not write its log file <path>: <strerror>. Later failures are not reported.`
      (to the RPC host's logger, the first failure);
    - `TAT refuses this Codex session: its sandbox is not the one TAT configured. Start Codex in <working directory>/TAT.agents without a sandbox option.`
      (the `TAT_StartupError`; to be adjusted to what the measurement shows
      TAT can see).
    The `message` of each compaction check's `check_failed` record is the
    compaction session's to word.

## Keeping the agent out of `.tat/`: what the clients offer (read 2026-10-01, nothing run)

**Claude Code** — from the official documentation (code.claude.com/docs:
permissions, settings-reference, tools-reference, sandboxing, hooks), not
measured on 2.1.285/2.1.286.

- `"permissions": {"deny": ["Read(/.tat/**)", "Edit(/.tat/**)"]}` in the
  project's `.claude/settings.json`; `/path` is relative to the settings
  source. Documented to cover Read, Grep and Glob (matching files are left
  out of results), `@` mentions, Edit, Write, NotebookEdit (the `Edit`
  rule), and Bash commands that name the file (`cat`, `head`, `tail`,
  `sed`, redirections); in every permission mode, in subagents and under
  `-p`; without the trust dialog.
- Documented not to cover "a command that reads files without naming them,
  such as `grep -r pattern .`", nor a script that opens files itself. On
  Linux the default tool set has no Grep and no Glob: the agent searches
  with `grep` and `find` through Bash (embedded `ugrep` and `bfs`).
- Not documented: whether the embedded `ugrep` and `bfs` skip hidden
  directories or honour `.gitignore` / `.ignore`; that a deny rule leaves
  the hooks' own `sh …/.tat/hook.sh` alone (hook commands run unsandboxed
  is documented; the rest is inference).
- The documented complete answer is the sandbox (`sandbox.enabled`), which
  merges the `Read` deny rules into its `denyRead`; it wraps every Bash
  command and needs `bubblewrap` and `socat`.
- There is no `.claudeignore`.

**Codex 0.156.1** — from the source of that version
(`/home/qiyuan/.claude/jobs/bb9fec78/tmp/codex_src/codex-rust-v0.156.1/codex-rs`),
nothing run.

- The model has no read, list or search tool: files are reached through the
  shell (`exec_command`), `apply_patch` and `view_image`
  (`core/src/tools/spec_plan.rs`). The base prompt recommends `rg`
  (`protocol/src/prompts/base_instructions/default.md:264`), which by its
  own defaults skips hidden directories and honours `.ignore` everywhere,
  `.gitignore` only inside a git repository. `grep -r`, `find`, `cat`
  apply none of that.
- A named permission profile in the project's `.codex/config.toml` can deny
  the directory at the level of the operating system (bubblewrap mounts an
  empty unreadable tmpfs over it, `linux-sandbox/src/bwrap.rs:1286-1322`):
  `default_permissions = "tat"`, `[permissions.tat] extends = ":workspace"`,
  `[permissions.tat.filesystem.":workspace_roots"] ".tat" = "deny"`.
  Subagents inherit it (`core/src/agent/child_config.rs:183-192`); hook
  commands run outside the sandbox
  (`hooks/src/engine/command_runner.rs:397-433`).
- Two costs: a sandbox flag at launch (`-s …`,
  `--dangerously-bypass-approvals-and-sandbox`) makes Codex ignore the
  profile (`core/src/config/mod.rs:2536-2537`); and the profile is a whole
  sandbox definition, which replaces a `sandbox_mode` in the user's own
  configuration (`core/src/config/mod.rs:2556-2566`).
- `permissions.filesystem.deny_read` exists only in managed
  `requirements.toml`, not in `config.toml`.
- The `@` picker honours `.ignore` (`file-search/src/lib.rs:430-446`).

## The whole working directory hidden from the agents (raised 2026-10-01)

The owner: 「整个 tat 工作目录都应该是对 agents 隐藏的，也许我们只给 agents
一个临时目录 比如 the_working_dir/tmp 然后用 chroot 来防止它进行任何访问？」
— the direction is stated, the means is a question. Not decided.

Measured on this machine (Ubuntu 24.04.5, uid 1002, 2026-10-01):

- `chroot <dir> /bin/true` without root is refused (`Operation not
  permitted`).
- `bwrap` 0.9.0 is installed and runs without root:
  `bwrap --ro-bind / / --tmpfs <dir> sh -c 'ls <dir> | wc -l'` prints 0 for
  a directory that holds 15 entries outside, its siblings unchanged.
- `socat`, which Claude Code's own sandbox requires on Linux, is not
  installed.

Documented for Claude Code (settings-reference,
`permissions.blockReadsOutsideWorkingDirectories`, v2.1.257 or later):
`Read`, `Grep`, `Glob` and `LSP` refuse paths outside the working
directories in every permission mode, `bypassPermissions` included; shell
commands are not refused the same way — one that reads such a path prompts.

**Decided (2026-10-01): the separation is enforced by each client's own
sandbox.** 「我建议走 自带的 sandbox，安装 socat 没问题的」. Not `chroot`, and
TAT does not start the client. `socat` 1.8.0.0 was installed on this
machine the same day (`apt-get install socat`).

What the two sandboxes can express (documentation and source, nothing run):

- Claude Code, shell commands: `sandbox.enabled`, `sandbox.failIfUnavailable`
  (exit at startup when the sandbox cannot start), `sandbox.allowUnsandboxedCommands:
  false` (the `dangerouslyDisableSandbox` retry ignored),
  `sandbox.filesystem.denyRead` with absolute paths, and
  `sandbox.filesystem.allowRead`, which "re-open[s] reading for specific
  paths inside a region that `denyRead` blocks" — the documented example
  denies `~/` and allows `.`, the project root. `Read(...)` deny rules are
  added to `denyRead` by Claude Code itself. Sandboxed commands run without
  a permission prompt by default (`autoAllowBashIfSandboxed`), write only
  to the launch directory and the temp directory, and reach no network host
  that is not pre-allowed.
- Claude Code, file tools (Read, Edit, Write; Grep and Glob where present):
  these do not go through the sandbox. A `Read(//<absolute path>/**)` deny
  rule hides a directory from them, and no rule re-opens a directory
  nested under a denied one; `permissions.blockReadsOutsideWorkingDirectories`
  makes them refuse every path outside the launch directory, and with the
  sandbox on also denies sandboxed commands the roots that hold user files
  (`/home`, `/root`, `/mnt`, `/media`, `/srv`, …) except the launch
  directory.
- Codex: a writable root nested under a denied directory is handled by
  design — the denied ancestor is masked first and the writable descendant
  re-opened inside it (`linux-sandbox/src/bwrap.rs`, `create_filesystem_args`
  and `append_existing_unreadable_path_args`). A profile may also restrict
  reads to named roots (`:minimal`, `:workspace_roots`) instead of the whole
  disk.

**Decided (2026-10-01): apart from its own directory, the agents read no
user files.** 「建议除了 agent 自己的目录，用户文件一律不可读」. On Claude
Code this is `permissions.blockReadsOutsideWorkingDirectories` with the
sandbox on; on Codex a profile that grants reads by name instead of the
whole disk. The consequence the owner was told: the agents cannot read the
Isabelle and AFP sources when those lie under a root that holds user
files, and TAT's `query` tool, which would answer for them, does not exist
yet.

**Decided (2026-10-01): the agent client's directory is a subdirectory of
the working directory.** 「放在 working directory 里面, 名字推荐一下」.

Facts for the name:

- A `Session`'s folder sits at the top of the working directory under the
  `Session`'s name, grammar `[A-Za-z][A-Za-z0-9_-]*` not ending in `-` or
  `_` (`model.py`, `is_valid_session_name`): `tmp`, `agents`, `workspace`
  are all names a `Session` may bear. A name with a dot, or beginning with
  `_` or `.`, cannot collide.
- Codex gives `.agents` under the cwd a meaning of its own
  (`core-plugins/src/loader.rs:471`, `.agents/plugins/marketplace.json`;
  `windows-sandbox-rs/src/workspace_acl.rs:20`).
- Claude Code stores a session's history under a path derived from the
  launch directory, so the directory is permanent, not temporary.
- Seen on the way, the compilation design's to settle: `ROOT` is itself a
  legal `Session` name, and that `Session`'s folder would collide with the
  ROOT file.

**Decided (2026-10-01): the directory is `<working directory>/TAT.agents/`.**
「赞同 TAT.agents」. The glossary term proposed with it, **agent
directory**, was not objected to.

### The Codex profile that grants reads by name (source of 0.156.1, nothing run)

```toml
default_permissions = "tat-agent"

[permissions.tat-agent.filesystem]
":minimal"   = "read"
":tmpdir"    = "write"
":slash_tmp" = "write"
"<working directory, absolute>" = "deny"

[permissions.tat-agent.filesystem.":workspace_roots"]
"." = "write"

[permissions.tat-agent.network]
enabled = false
```

- `:minimal` on Linux is `/bin`, `/sbin`, `/usr`, `/etc`, `/lib`, `/lib64`,
  `/nix/store`, `/run/current-system/sw` (`linux-sandbox/src/bwrap.rs:50-59`).
- A path no entry matches has no access
  (`protocol/src/permissions.rs:1031`); with no readable `/` the sandbox
  starts from an empty filesystem and mounts the listed roots into it
  (`linux-sandbox/src/bwrap.rs:519-576`), so `/home` and the working
  directory do not exist inside.
- The sandboxed shell still starts: Codex adds its own helper directory
  `~/.codex/tmp/arg0` as readable (`core/src/config/permissions.rs:514-540`),
  and `/usr/bin/codex` resolves under `/usr`.
- The explicit `deny` entry is what keeps an escalation or a retry after a
  sandbox failure inside the sandbox (`core/src/tools/sandboxing.rs:276-296`,
  `core/src/tools/orchestrator.rs:228-236`); without any deny entry an
  approved retry runs unsandboxed.
- `apply_patch` and `view_image` read through the same policy
  (`file-system/src/lib.rs:406-411`).
- Lost with it: every program installed under `/home` (conda,
  `~/.local/bin`, an Isabelle there) is not found by the agent's shell
  unless its path gets a `read` entry; the shell's rc files are not read.
- Which policy is active is observable from outside. A server that
  declares `capabilities.experimental["codex/sandbox-state-meta"]` in its
  `initialize` result receives, on every `tools/call`,
  `_meta["codex/sandbox-state-meta"]` with the compiled policy
  (`codex-mcp/src/rmcp_client.rs:981-985`, `core/src/mcp_tool_call.rs:821-860`).
  The rollout's turn-context lines carry `active_permission_profile`, null
  when a sandbox flag forced the old path (`protocol/src/protocol.rs:3307-3320`).
  Hook payloads carry nothing about the sandbox.
- Codex loads `.codex/`, `AGENTS.md` and `.agents/skills` from every
  directory between the project root — the nearest ancestor holding `.git`,
  else the cwd — and the cwd (`config/src/loader/mod.rs:1476-1520, 1631-1680`,
  `core/src/agents_md.rs:215-240`). A working directory inside a git
  repository therefore brings that repository's files into the agents'
  context; the client reads them itself, outside the sandbox.
- Protected names directly under the cwd: `.git`, `.agents`, `.codex`
  (`protocol/src/permissions.rs:35-52`); `TAT.agents` matches none.

**Decided (2026-10-01), on the three consequences:**

- Programs installed under `/home` are not found by the agent's shell, and
  none gets a `read` entry. 「接受」.
- TAT checks, on every Codex tool call, the sandbox policy the call
  carries, and a policy that is not TAT's profile refuses the session and
  ends the conversation, through the door the client's version check uses.
  「没问题」. The wording of the refusal is still to be proposed.
- The instruction files a client loads by itself from the directories above
  its own — `AGENTS.md`, `.codex/`, `CLAUDE.md` — are the user's; TAT does
  nothing about them and the document says so. 「接受」.

**Approved (2026-10-01): one measurement of the whole arrangement on both
clients by an Opus agent.** 「批准」. Files under
`ai-artifacts/probes/agent_directory/`, never committed.

## Measured (2026-10-01): `ai-artifacts/probes/agent_directory/REPORT.md`

59 runs, Claude Code 2.1.286 and Codex 0.156.1, the main conversation and
one subagent each, working directories under `/home` inside a git
repository, under `/home` outside one, and under `/tmp`.

**Codex.** With the profile, every shell read of the working directory,
of `..` and of other user files fails, `apply_patch` outside the agent
directory is rejected, the hooks fire and read `tat.lock`, the MCP tool
works, a subagent is bound alike, in all three placements — once
`":slash_tmp"` and `":tmpdir"` are removed: with them the host's `/tmp` is
mounted read-write, and an agent read a working directory under `/tmp` and
wrote `/tmp/p_probe`. `_meta["codex/sandbox-state-meta"]` arrives on every
`tools/call`, identical for the main thread and the subagent; under the
profile it is `managed` with the `deny` entry on the working directory;
`-s read-only` and `-s workspace-write` replace it with a root-readable
policy, `-s danger-full-access` and
`--dangerously-bypass-approvals-and-sandbox` with `{"type":"disabled"}`,
and in each of the four the hidden files were readable. The parent's
`AGENTS.md` is not loaded under the profile. `codex exec` outside a git
repository needs `--skip-git-repo-check`. Codex leaves empty `.git/` and
`.agents/` in the agent directory. Not measured: an escalation, the model
refusing to request one.

**Claude Code.** With `blockReadsOutsideWorkingDirectories`, the sandbox
and `denyRead` on the working directory: shell reads of the working
directory, of `..`, of `~` fail for the main conversation and the
subagent, in default `-p` and under `--dangerously-skip-permissions`; the
Read tool refuses paths outside the agent directory; `dangerouslyDisableSandbox`
is ignored; the hooks fire; the MCP tool works; the agent's shell cannot
reach TAT's port. What it took, and what is left:

- On this host every sandboxed command fails (`apply-seccomp: … nested
  userns is capability-restricted`, the AppArmor profile
  `bwrap-userns-restrict`) unless `sandbox.network.allowAllUnixSockets` is
  true; `failIfUnavailable` does not catch it. With it,
  `systemd-run --user … cat` read the hidden database through the D-Bus
  socket and the libvirt socket answered; `/run` in `denyRead` closes both.
- `/tmp` is readable by default; `/tmp` in `denyRead` closes it, except
  `/tmp/claude-1002`, Claude Code's own temp directory, shared by every
  session of the user, which stays readable and writable.
- Without the explicit `denyRead`, a working directory under `/tmp` is
  exposed; with it the agent directory stays usable; `allowRead` changes
  nothing.
- The block covers reads only: under `--dangerously-skip-permissions` the
  Write tool wrote into the working directory. A `PreToolUse` hook on
  `Write|Edit|NotebookEdit|MultiEdit` that denies a path outside the agent
  directory closes it; an `Edit` deny rule on the working directory blocks
  the agent directory too; `acceptEdits` refuses outside but also refuses
  untraceable shell commands.
- In default `-p` mode the Write tool is refused inside the agent
  directory as well, and a command with a subshell is refused.
- Nothing TAT receives — hook payloads, `initialize`, `_meta` — differs
  with the sandbox on or off, and `--settings '{"sandbox":{"enabled":false}}'`
  switches it off.
- The parent's `CLAUDE.md` is loaded.
- With `socat` missing: exit 1, "sandbox required but unavailable …".

Not measured: interactive sessions; a host without the AppArmor
restriction; the final Claude Code file outside a git repository.

## Decided on the measurement (2026-10-01)

- **Codex's profile has no `:slash_tmp` and no `:tmpdir`**: the agent's
  shell has no `/tmp`. 「接受」「可以」.
- **Claude Code's settings gain three things**: `sandbox.network.allowAllUnixSockets`
  with `/run` in `denyRead`; `/tmp` in `denyRead`; and a `PreToolUse` hook
  on the file-writing tools that refuses a path outside the agent
  directory. 「接受」「赞同」.
- **The hook judges by a fixed rule.** 「好。但我们要用固定的规则去判断。」
- **Writing inside `TAT.agents` must be allowed**, in whatever permission
  mode. 「我们必须允许 TAT.agents 下的写入」 — how is being measured by an
  Opus agent, approved with one more run of the final file in the three
  placements (「批准一次小的补测」).
- **Accepted as best effort**: that TAT cannot tell whether Claude Code's
  sandbox is on (「这根本不重要」); that `/tmp/claude-1002` stays readable
  and writable (「问题不大」); that Claude Code's sandbox subtracts from the
  whole filesystem instead of building from nothing (「OK」); that the
  parent's `CLAUDE.md` is loaded (「接受」).

- **The fixed rule** 「确认」: take the path in the tool's arguments; make
  it canonical — absolute, `..` removed, symbolic links resolved, and for a
  file that does not exist yet the canonical form of its nearest existing
  ancestor plus the rest; inside the canonical agent directory the hook
  answers allow, otherwise deny. Nothing else is read: not the permission
  mode, not the agent.

## Measured (2026-10-01), second run: `ai-artifacts/probes/agent_directory/REPORT2.md`

54 runs of Claude Code 2.1.286 with the fixed rule inside the probe
server's `/hook`, reached through `sh <wd>/.tat/hook.sh`; three placements
(under `/home` in a git repository, under `/home` outside one and outside
`~/.claude`, under `/tmp`).

- **The hook's `allow` alone lets a write inside the agent directory
  through** — Write (a new file, a new file in new subdirectories), Edit,
  NotebookEdit — for the main conversation, a foreground and a background
  subagent, in default `-p`, `acceptEdits`, `--dangerously-skip-permissions`
  and `auto`. No `permissions.allow` rule and no `defaultMode` is needed.
  This build has no MultiEdit.
- **The hook's `deny` holds in every one of those**, for the working
  directory, `TAT.agents/..`, a symbolic link inside the agent directory
  pointing out, `/tmp`, `/home`; nothing landed on disk; it wins over
  `permissions.allow` rules and over bypass mode. Claude Code hands the
  hook a path already absolute, `~` expanded and `..` removed, symbolic
  links not resolved.
- **The client's own files inside the agent directory**
  (`.claude/settings.json`, `.claude/settings.local.json`, `.mcp.json`,
  `.claude/agents/x.md`), the rule answering allow for everything inside:
  Claude Code refuses them itself in default and `acceptEdits`; in bypass
  mode all four writes land, and Claude Code reloads its settings while the
  session runs — after the agent set `sandbox.enabled` to false, a shell
  command created `<wd>/escape2` on the real disk; in `auto` the settings
  writes are refused and the other two land. With the rule also refusing
  `.mcp.json` and everything under `.claude/`, all are refused in every
  mode and nothing Claude Code needs breaks. A sandboxed shell command
  cannot change those files.
- **Shell writes** inside the agent directory work in every mode; aimed
  outside, none lands on disk.
- **A command with a subshell** is refused in default and `acceptEdits`
  mode ("Contains shell syntax (;) that cannot be statically analyzed"),
  sandboxed or not; `permissions.allow: ["Bash"]` in the project file
  makes it run, sandboxed, only where the folder is trusted — in `-p`
  Claude Code ignores a project's allow rules in an untrusted folder, and
  says so on stderr; `--allowedTools Bash` on the command line does it
  anywhere; bypass mode runs it.
- The final file passed the whole matrix, main conversation and subagent,
  in the three placements, in default and bypass mode.

Not measured: interactive sessions; whether a changed `.mcp.json` takes
effect in the running session; the `plan` and `dontAsk` modes.

## Decided on the second measurement (2026-10-01)

- **The rule also refuses the client's own files**: `.mcp.json` and
  everything under `.claude/` in the agent directory. 「赞同」.
- **The two sentences a refused write is answered with** 「批准」:
  `TAT allows writing only inside <agent directory>.` and
  `TAT does not allow changing the agent client's own files.`
- **`configure` writes `permissions.allow: ["Bash"]`** on Claude Code.
  「允许」.
- *(author)*: a path that reaches the hook relative is refused; the
  payload's `cwd` is not read.

## The review (2026-10-01)

Two-turn adversarial review, 26 agents: the ruling is
`ai-artifacts/review/LOGGING_AGENT_DIRECTORY_RULING.md`, the debate
`LOGGING_AGENT_DIRECTORY_DEBATE.md`. Verdict: not ready overall; twenty
concerns, nineteen upheld at least in part; eleven points for the owner.
Nothing has been changed on it yet.

The owner on C10 (the ruling's fix: refuse every MCP tool but TAT's):
「不啊，我们是应该允许联网，Bash 等一系列的工具的啊」 — the agents are to
have the network, Bash and a range of tools. Two things follow that are
not settled: the agents' shell commands have no network in the files as
written (Claude Code's sandbox default, measured; Codex's
`network enabled = false`, the author's recommendation, which the owner
had never confirmed — the author's error to have written it as settled);
and whether "a range of tools" includes MCP servers other than TAT's,
which run outside both sandboxes.

**Decided (2026-10-01): a whitelist of MCP servers and tools.** 「我们应该
只允许白名单中的 MCP 与工具，这个名单目前应该包含 claude/codex 原本所有的
工具，以及 TAT mcp 的所有工具」. So every tool the client has of its own is
allowed, TAT's tools are allowed, and the tools of any other MCP server
are refused. *(author)*: an MCP tool is one named `mcp__<server>__…`, and
every other tool is the client's own, so the whitelist is enforced by
refusing the `mcp__` tools that are not TAT's.

**Decided (2026-10-01): the `Skill` tool stays allowed.** 「Skill 工具应该
被允许」. The ruling's fix for C1 (`permissions.deny: ["Skill"]`) is
therefore not taken; whether the escape C1 describes is real has not been
measured.

**Decided (2026-10-01):**

- The sentence a refused MCP tool is answered with:
  `` TAT does not allow tools of the MCP server `<server>`. `` 「批准」.
- `EnterWorktree` is disabled, the one exception to "every tool the
  client has of its own". 「禁用 EnterWorktree」.
- C1 — a skill an agent plants in a subdirectory of the agent directory,
  whose hooks would run outside the sandbox — is accepted as a gap.
  「允许 Skill，接受这个缺口」. It was derived from Claude Code's
  documentation and has not been measured.

- The agents' shell commands reach every outside host, and none of the
  machine's own addresses. 「赞同放行所有外部主机、拒绝本机地址」. How each
  client expresses it is to be read and measured.
- The connectors of the user's account — the MCP servers Claude Code
  loads from the claude.ai account it is logged in with — are on the
  whitelist. 「允许连接器」. *(author's reading)*: the Chrome extension's
  server, which the owner was told is another kind, is not; the owner has
  been told this reading.
- A compile (`isabelle TAT_compile`, COMPILATION.md) writes no log.
  「不写」. *(author, the ruling's shape)*: `Log` is a required field of
  `Conversation`, and a compile passes one that writes nothing.
- Two changes to the approved event tables 「赞同你的建议」: the
  `evaluation` event `operation` no longer carries the messages, which the
  `round_trip` record of the same call holds; the `tool` table gains
  `given_up`, for a call whose body finished after its client had given up
  on it: the tool, the text the body produced, the messages that would
  have gone with it, the duration.
- `seq` is dropped; a record is identified by its file and its `ts`, and
  the launcher's line is `### <message> (<file>, <time>)` for both sides.
  「赞同」. This amends decisions 10 and 13.
- The Isabelle side drops a record it cannot write and reports nothing;
  its writer never raises. 「赞同你的建议」. This narrows decision 7's
  "reported once" to the Python side, which meets the same cause in the
  same directory and reports it.
- A working directory whose path contains `[` or `]` is refused, by
  `TAT_new` and at launch:
  `<path> contains [ or ], which TAT cannot use in a working directory path`.
  「批准」. Both clients read those characters in a deny entry as pattern
  syntax (Claude Code's `denyRead`, settings-reference; Codex's
  `permission_path.rs:70`).
- Accepted as a gap: between the check of a file tool's path and Claude
  Code's own write, an agent that swaps a directory of the path for a
  symbolic link can make the write land outside the agent directory.
  「赞同你的建议」. It allows writing out, not reading; no check made
  before the write by anything but the client can close it.
- Accepted as a gap: on Codex the whitelist is enforced by a hook, and
  Codex runs a project's hooks only when the project is trusted and the
  launch carries `--dangerously-bypass-hook-trust`; without them no hook
  runs, TAT ends the conversation at the first call nobody announced, and
  the Codex process goes on with its other MCP servers. 「接受此缺口」.
  The profile, which hides the files, does not depend on hooks.
- The ending's line for a Codex session under a sandbox that is not
  TAT's: `TAT has stopped: Codex's sandbox is not the one TAT configured; this call did not complete.`
  「批准」.

## Written (2026-10-01)

- The log: `docs/LOGGING.md`, with MODULE_STRUCTURE §2.4, §2.6, §4, §4.6
  and §5, CONSTRUCT_INTERACTION §7 and §8, ARCHITECTURE §1, EXCEPTIONS §1
  and CLIENT_HOOKS §1.
- The agent directory: CLIENT_HOOKS.md (the opening, §1's table, §2 and
  §3's files, the new §5), ARCHITECTURE §1 (the term) and §9,
  CONSTRUCT_INTERACTION §1 and §8, MODULE_STRUCTURE §4.6, EXCEPTIONS §1,
  LOGGING.md §4; the measurements in AGENT_CLIENTS_MEASURED.md.
- No code. Not written anywhere yet: the implementation of either.

## Written (2026-10-02), after the review

With the owner's 「同意现在就改文档」. From the ruling, by its concern:

- C3 — the launcher is told the log directory by the protocol message
  `TAT.log_directory`; `tat.lock` has two lines again (LOGGING §7,
  MODULE_STRUCTURE §2.6, §4.6, §5, CLIENT_HOOKS §1). COMPILATION.md:899
  still speaks of the lock file's third line: the compilation session's
  to change.
- C4, C12 — the Isabelle side's log is a value of one conversation,
  captured by a job at its fork; its writer never raises and reports
  nothing (LOGGING §5, MODULE_STRUCTURE §2.4, §2.6).
- C5 — the directory is named to the microsecond and made exclusively
  (LOGGING §2).
- C6 — the routes to the `Log`, a record written by open, one write and
  close, `agent` and `call` as context variables, the start order
  (LOGGING §3, §5, MODULE_STRUCTURE §4.1, §4.3, §4.6).
- C7 — the fifth ending line (MODULE_STRUCTURE §4.6, RENDER_BASELINES §4),
  `client_refused`'s `_meta` (LOGGING §4), "cannot run" (EXCEPTIONS §1,
  §3).
- C13 — a `Bug` in an evaluation job's work travels in the report and
  ends the conversation (MODULE_STRUCTURE §2.4, CONSTRUCT_INTERACTION
  §3.3, EXCEPTIONS §1, LOGGING §4).
- C16 — the ending object is built after the `Log`; whatever escapes
  `launch_TAT` once the log exists enters the ending; the host the
  Isabelle process started exits with it, so the usual end leaves no
  `ended` (LOGGING §4, MODULE_STRUCTURE §4.6, CONSTRUCT_INTERACTION §1,
  ARCHITECTURE §9, EXCEPTIONS §1).
- C17, C20 and the owner's decisions since — `given_up`, `operation`
  without the messages, no `seq`, the launcher's line (LOGGING §3, §4,
  §6, §7); the `[`/`]` refusal (MODULE_STRUCTURE §5).
- C2, in part — the `write` event is gone from `/hook` (LOGGING §4,
  MODULE_STRUCTURE §4.6, CONSTRUCT_INTERACTION §8).
- C19 — items 2 and 5. Item 1, raising Claude Code's floor to 2.1.286, is
  not taken: the compaction session has since rewritten CLIENT_HOOKS.md's
  opening to say each fact is measured on the version AGENT_CLIENTS_MEASURED.md
  names and TAT requires at least 2.1.285, and the owner asked for the
  version rule to be looser, not tighter.

Waiting for the third measurement (`REPORT3.md`): CLIENT_HOOKS.md §1's
table, §2's and §3's files and §5 — the guard script, the whitelist, the
quoted commands, `EnterWorktree`, the network, the accepted gaps, C18's
and C19's wordings there — and the SKILL memo's facts.

**A compile writes a log** — the owner, 2026-10-02, amending 「不写」:
「我真觉的无所谓，那就写吧，真无所谓」. So the compilation session's text
stands: a compile makes its log directory and `Log` as a conversation
does, its Python side writes there, and the Isabelle side, told no
directory, writes nothing (LOGGING.md §2, §5, §7, MODULE_STRUCTURE §4.6,
COMPILATION.md §5). The ruling's fix for C14 — a `Log` that writes
nothing — is not taken. COMPILATION.md's two mentions of the lock file's
lines were brought in line with the two-line lock.

**Claude Code's floor stays 2.1.285**, as the compaction session wrote
it. 「这个也真无所谓」.

Carried over, not this record's to decide: what an alarm does to the
conversation — end it or continue — is the compaction session's question.

## Measured (2026-10-02), third run: `ai-artifacts/probes/agent_directory/REPORT3.md`

73 runs (Claude Code 2.1.286, Codex 0.156.1), main conversation and a
subagent, default `-p` and bypass mode, a path with a space included.

- **The guard script** (`<wd>/.tat/guard.py`, no connection, never exits 2)
  holds with TAT stopped: inside writes pass; outside writes, the client's
  own files, another server's tools and resources are refused. With its
  interpreter path wrong, in bypass mode, an outside write landed and
  another server's tool ran: it fails open.
- **The whitelist on Claude Code** holds through a `PreToolUse` on
  `mcp__.*|ListMcpResourcesTool|ReadMcpResourceTool|ReadMcpResourceDirTool`.
  Without it the resource tools read another server's resource with no
  prompt even in default mode. Of two hooks on one call, a `deny` wins;
  TAT's own calls pass with both matching. A connector is recognised by
  `mcp_server.source == "claudeai"` in the payload; a project server given
  a connector's name keeps source `project` and is refused. With no
  decision from the guard a connector call is refused in default `-p` and
  runs in bypass mode. `allowedMcpServers` with TAT's URL alone also
  blocks the connectors, and re-admitting them admits every HTTPS server.
- **The whitelist on Codex** holds, calls from a code-mode script
  included; the payload names no server and no source. The account's apps
  are served by the built-in server `codex_apps`; a user's server named
  `codex_apps__spoof` passed a rule on that prefix.
- **Worktrees**: with the deny, `EnterWorktree` is absent from the tool
  list; a subagent with `isolation: "worktree"` gets
  `WorktreeCreate hook failed: hook succeeded but returned no worktree path (command: echo the path to stdout; http/callback: return hookSpecificOutput.worktreePath)`,
  and the repository is unchanged. Claude Code's sandbox writes an empty
  `.git/config.worktree` into the enclosing repository at session start;
  the TAT repository has one from the first probe.
- **Quoted commands** work on both clients with a space in the path.
  Unquoted, every hooked tool call is blocked (`sh` exits 2); a Stop is
  not, Claude Code reading "cannot open" as a missing script.
- **The network on Claude Code**: `/tmp` in `denyRead` hides the proxy's
  socket (`/tmp/srt-mux-<pid>-0.sock`) and every outbound connection
  fails; no project setting re-opens it. Without `/tmp` there,
  `allowedDomains: ["*"]` with `deniedDomains` listing loopback and the
  host's interface addresses reaches outside hosts and refuses those
  addresses in every spelling and every name resolving to them — but not
  127.0.0.2 … 127.255.255.254, through which a service listening on
  `0.0.0.0` was reached (on this machine Isa-REPL listens on
  `0.0.0.0:6666`); TAT, which binds 127.0.0.1, was not. Other working
  directories under `/tmp` are then readable.
- **The network on Codex**: `enabled = true` alone leaves the host's
  network namespace — every local service reached, no DNS. With
  `[features] network_proxy = true` (experimental) and
  `domains "*" = "allow"`, outside hosts are reached and every loopback
  and private address is refused, all of 127/8 included.

Not measured: interactive sessions, auto mode; `WebFetch`/`WebSearch`
toward local addresses; a real Codex app call.

## Decided on the third measurement (2026-10-02)

- On Claude Code the shell's network is kept and `/tmp` is no longer
  hidden: `/tmp` leaves `denyRead`. 「赞同保联网，放弃隐藏 /tmp」. This
  amends "Claude Code's settings gain three things".
- Accepted as gaps: Claude Code cannot refuse 127.0.0.2 …
  127.255.255.254, so a service of the machine that listens on every
  address is reachable from an agent's shell (「接受」); on Codex the
  account's apps are recognised by the server name's prefix alone, which a
  server the user names so also passes (「接受。尽力就好」); a guard script
  that cannot start lets everything through (「接受」).
- Codex's `[features] network_proxy = true`: proposed by the author with
  the measurement, not objected to; it is what gives "every outside host,
  none of the machine's own addresses" there.

- **The whitelist is withdrawn: the agents may use the other MCP servers
  the client has.** 「其实我现在改变了想法，觉得可以放开，可以允许访问其他
  的 mcp？」, then 「确认」. So the guard script judges no MCP tool and no
  MCP resource tool; the sentence ``TAT does not allow tools of the MCP
  server `<server>`.``, the rule for connectors and the gap about Codex's
  apps fall away; every tool the client has is available but
  `EnterWorktree`. The owner was told the cost: such a server runs outside
  the sandbox, and one that reads files by path — `isabelle-mcp` in the
  measurements — shows an agent the working directory's files.
- **The line an agent reads when a worktree is refused**:
  `TAT does not allow git worktrees. Start the subagent without worktree isolation.`
  「赞同文案」, after 「能有办法改一下吗？改成比如“worktree 不被接受，你不能
  使用 worktree” 之类的？」. How the guard delivers it is being measured
  (approved, 「批准这次小实测」).

## Measured (2026-10-02), fourth run: `ai-artifacts/probes/agent_directory/REPORT4.md`

Ten runs, on Claude Code 2.1.287 (the client had updated itself), in a
scratch git repository.

- The tool that launches a subagent is `Task` in the init list and `Agent`
  in the model's calls and in the hook's `tool_name`. Its `tool_input` has
  `description`, `prompt`, `subagent_type`, `run_in_background`, and
  `isolation: "worktree"` when the call asks for it.
- A guard on `PreToolUse` `Agent|Task` that denies a call carrying
  `isolation: "worktree"` makes the model read
  `PreToolUse:Agent hook error: TAT does not allow git worktrees. Start the subagent without worktree isolation.`,
  in default `-p` and in bypass mode, from the main conversation and from
  a subagent launching a nested one; a launch without isolation gets no
  decision and runs. No `WorktreeCreate` fires.
- Isolation set in a subagent definition's frontmatter does not appear in
  the payload; only `WorktreeCreate` stops it. The guard printing the
  sentence on stderr and exiting 1 makes the model read
  `WorktreeCreate hook failed: <the hook's command line>: TAT does not allow git worktrees. Start the subagent without worktree isolation.`;
  on stdout, or nothing, the sentence does not arrive. The creation fails
  in every case.

## Decided after the fourth measurement (2026-10-02)

- **Nothing blocks the machine's own addresses, on either client.**
  「那就干脆不拦截本地网络请求了呗」, then 「都适用」. This withdraws
  "every outside host, and none of the machine's own addresses": Claude
  Code's settings carry `allowedDomains: ["*"]` and no `deniedDomains`,
  and the gap about 127.0.0.2 … is moot.
- **Follow the client's defaults; no more settings or restrictions than
  needed.** 「我们最好按默认行为来，别做过多设置/限制」. Codex's
  `network_proxy` feature, experimental and off by default
  (`features/src/lib.rs:1284-1293`), is not switched on.
- **TAT's `/hook` takes no secret**: an agent's shell can reach it, and
  the agents are trusted not to forge requests. 「不用，可信任」.
- Approved: a fifth measurement — how Codex resolves outside names with
  `enabled = true` and no proxy, and a regression of the assembled final
  files on both clients. 「批准」.

## Measured (2026-10-02), fifth run: `ai-artifacts/probes/agent_directory/REPORT5.md`

16 runs, Claude Code 2.1.287 and Codex 0.156.1.

- Codex resolves no outside name because `/etc/resolv.conf` is a symbolic
  link into `/run`, which the profile's empty filesystem lacks. One read
  entry for the link's real path
  (`/run/systemd/resolve/stub-resolv.conf` on this host) makes `curl`,
  `git` and Python reach outside hosts, the hidden files staying hidden.
  An entry for `/etc/resolv.conf` itself makes every command fail. The
  proxy feature is not needed. *(author)*: `configure` adds the entry for
  the real path of `/etc/resolv.conf` when it lies outside the `:minimal`
  directories.
- The assembled files — CLIENT_HOOKS.md §2, §3 and the guard script of §5
  — pass the regression in every cell: three placements, default and
  bypass mode on Claude Code, the main conversation and a subagent on
  both clients; nothing lands outside the agent directory; the
  conversation's hooks reach TAT; the guard holds with TAT stopped.

## Written (2026-10-02), after the measurements

CLIENT_HOOKS.md: the opening, §1 (the write row gone; the conversation's
hooks alone go to TAT), §2's and §3's files as measured, §5 rewritten —
the guard script, the write rule, worktrees, the network, Codex's
resolver entry, the accepted gaps. ARCHITECTURE §1 and §9 and
MODULE_STRUCTURE §4.6 follow. AGENT_CLIENTS_MEASURED.md gains the later
runs. SKILL_MEMO.md is new.

## The second review (2026-10-02)

31 agents; the ruling is
`ai-artifacts/review/LOGGING_AGENT_DIRECTORY_RULING_2.md`, the debate
`LOGGING_AGENT_DIRECTORY_DEBATE_2.md`. Twenty-five concerns, twenty-one
upheld at least in part, four struck (D8, D21, D22, D25). Verdict: not
ready today; ready once the author's fixes are written and the owner
approves D5; no third review. Four points for the owner: D5 (the shape of
`register_callback`), D1 (one ending line), D7 and D23 (two more gap
lines), D12(b) (the `operation` record carries the messages again).

**Decided on it (2026-10-02):**

- **D5** 「批准」: `register_callback` takes `env -> ('a,'b)
  Remote_Procedure_Calling.callback`, the record before `mk_callback`; the
  framework wraps the record's `function` — timing it, recording whether
  it returned, raised or was interrupted as the `isabelle` event
  `callback`, writing `bug` when a `Bug` left it, releasing the result
  unchanged — and calls `mk_callback` itself; its own callbacks are made
  the same way; the duplicate-name check reads the record's `name`. A
  node class author drops the `mk_callback` call and changes nothing
  else. The wrapper reads the Isabelle-side log current at the call.
- **D1** 「赞同你的提议」: one `TAT_StartupError` subclass for a refusal
  raised while serving, its constructor requiring the ending line; the
  ending's line is chosen by that reason, then `TAT_DisasterError`, the
  connection gone, else "an internal error"; the line for a client whose
  version or name fails the check in a later MCP session:
  `TAT has stopped: a client TAT does not serve connected; this call did not complete.`
- **D7** 「接受」: on Claude Code a command can act outside the sandbox
  through a Unix socket outside `/run` — a tmux server's or the X
  display's under `/tmp` — inferred from the measured D-Bus route, not
  measured itself.
- **D23** 「接受」: Claude Code itself re-opens to the agents the user's
  git configuration (`~/.gitconfig`, `~/.config/git/`) and parts of
  `~/.claude` (skills, plugins, rules, agents, commands, shell snapshots).
- **The compile and the log, amended by the compilation session's
  ruling** (COMPILATION_REVIEW.md §10, contract-1, owner: 「告诉 Isabelle
  侧日志目录完全无害，保留」): a compile calls `TAT.log_directory` too, its
  command carrying that one framework callback; the Isabelle side writes a
  compile's records; `TAT_compile` prints the `Log:` line; a compile
  builds the ending object. Written into LOGGING §2, §5, §7 and
  MODULE_STRUCTURE §4.6 at that session's request; the owner has not yet
  seen it from this side.
- **D12(b)** 「很好批准」: the `evaluation` event `operation` carries
  `messages` again — the messages of the status value written,
  `CannotEvaluate(messages)` or `Ready(messages)`, an empty list for a
  clean run, absent for a status write that followed no run — and the
  pointer to `round_trip` goes. This reverses one clause of the 2026-10-01
  table change; a failed operation's messages then appear in
  `evaluation.jsonl` and, as the callback's raw answer, in
  `round_trip.jsonl`.

## Written (2026-10-02), after the second review

Concern by concern (the ruling's §5), with the owner's four answers:

- D1 — EXCEPTIONS §3: `ClientRefused`, a `TAT_StartupError` subclass
  whose constructor requires its ending line; RENDER_BASELINES §4: the
  sixth line and the rule choosing a line; MODULE_STRUCTURE §4.6: the rule
  in place of the fenced copy; CONSTRUCT_INTERACTION §8: the sandbox
  refusal's "every tool call is answered the ending's line" clause.
- D2 — MODULE_STRUCTURE §4.1 is the one list of what the `Conversation`
  holds (connection, working directory, `Log`, ending object);
  ARCHITECTURE §9 and PLUGIN_SYSTEM §2 point to it; PLUGIN_SYSTEM §2: a
  node class writes `note` records alone.
- D3, D4, D19 — MODULE_STRUCTURE §4.6: the start as three layers of
  numbered steps, the ending object entered as a context right after the
  `Log` (its exit the door for whatever escapes, and the writer of
  `ended`), the `Forest` handed to it, `tat.lock` in its own paragraph;
  LOGGING §2 (what a compile writes), §4 (`start`'s port and client name
  for a conversation only; `ended` by the exit, zero counts for a failed
  start or compile, none for a compile that returns); EXCEPTIONS §1 "as
  one raised at start does once the conversation's log exists" stands.
- D5 — MODULE_STRUCTURE §2.5: `register_callback` takes the callback
  record, the framework wraps `function` and calls `mk_callback`; LOGGING
  §4 (`callback`: "how long its function ran"), §5 (the wrapper as the
  site; the sites of the other Isabelle records).
- D6 — CLIENT_HOOKS §5: the guard's failure answers hook by hook.
- D7, D23 — CLIENT_HOOKS §5: `allowAllUnixSockets` described as what it
  does and written on every host; the gap lines for Unix sockets under
  `/tmp` and for what Claude Code re-opens; "short of the gaps listed at
  the end of CLIENT_HOOKS.md §5" in ARCHITECTURE §1 (both entries), §9
  and CLIENT_HOOKS §5's first sentence.
- D9 — MODULE_STRUCTURE §4.3: the private function of a connection,
  `call` for a conversation, `reset` on a bare connection and the fresh
  Isabelle-side log; LOGGING §5 "every round trip of a conversation".
- D10 — the report's argument is `failure` (MODULE_STRUCTURE §2.4,
  CONSTRUCT_INTERACTION §3.3; the two summaries in §2.5 and ARCHITECTURE
  §6.2 name the procedure only); LOGGING §4's `evaluation_reported` and
  `job_ended` say "the failure".
- D11 — MODULE_STRUCTURE §4.6 "to which the conversation's hooks post";
  CLIENT_HOOKS §1 retitled "The conversation's hooks".
- D12 — MODULE_STRUCTURE §4.1: the setter writes `operation` and takes
  the hook's duration or `None`; LOGGING §4: `operation` carries the
  status's `messages`.
- D13 — LOGGING §5: `open(path, "ab")`, whole line or raise; §6: every
  reader skips a line that is not JSON, the recipe reads file by file.
- D14 — LOGGING §5, §7 and MODULE_STRUCTURE §4.6: the directory's
  absolute path, printed as carried.
- D15 — the conversation's script is `hook.py`, Python, standard library,
  connecting directly whatever proxy the environment names; both scripts
  run as `'<python>' -I '<working directory>/.tat/<script>'` and find
  what they need beside themselves; the guard takes no argument
  (CLIENT_HOOKS opening, §1, §2, §3, §5; MODULE_STRUCTURE §4's listing;
  CONSTRUCT_INTERACTION §8 "the script failing").
- D16, D17 — CLIENT_HOOKS §5: `WorktreeCreate` is the hook that refuses,
  the `Agent` entry changes what the agent reads, a launch without
  isolation gets no decision; the gap line "lets every write through; a
  worktree is still refused"; MODULE_STRUCTURE §4's listing gains
  `hook.py` and `guard.py`, copied by `configure`. To check at
  implementation (the ruling's note): whether a configured
  `WorktreeCreate` hook makes Claude Code advise agents to use worktree
  isolation.
- D18 — CLIENT_HOOKS §5: the trust key after Codex's `.git/`, "empty
  directories", the network clause once; CONSTRUCT_INTERACTION §8 points
  to CLIENT_HOOKS §2, §3, §5 instead of retelling `configure`.
- D20 — LOGGING §3: a construction run's `agent` is its owner, set by the
  wrapper around `_run` (handed to the jobs session with the two faults).
- D24 — MODULE_STRUCTURE §4.6: every file through its format's one
  encoder, TOML strings through one escaping function, every hook
  command through one function with `shlex.quote`.
- D25 (optional) — MODULE_STRUCTURE §5: `*` and `?` Isabelle refuses.
- D8 (optional) — AGENT_CLIENTS_MEASURED.md: the policy under the final
  files.
- The judge's own gap — CLIENT_HOOKS §5: `.tat/` removed while a client
  runs blocks every hooked action.
- Handoffs sent: the jobs session (the two faults and D20); the
  compilation session (D4's lists, D12(a)'s setter clause — accepted, it
  is writing them); the compaction design's owner (D1's subclass for the
  transcript refusal).

Not done, and not mine: the `isabelle TAT_mcp` rename and the compile's
texts, which their sessions write.

## The implementation plan and its review (2026-10-02/03)

`LOGGING_IMPLEMENTATION_PLAN.md`; its small review,
`review/LOGGING_IMPLEMENTATION_PLAN_RULING.md`: 13 findings kept, none
reopening an owner decision. Decided on it:

- **Two wordings** 「批准」: the launcher's line for a client whose version
  or name fails the check, `TAT cannot serve this client: it is <name>
  <version>; TAT requires <client> <version> or newer.` (MODULE_STRUCTURE
  §4.6); `hook.py` prints `TAT is not running in this directory.` on every
  failure of its own (CLIENT_HOOKS §1).
- **The corrections K2–K13 written** into the plan and into LOGGING §2, §5,
  MODULE_STRUCTURE §2.4, §4.6, CLIENT_HOOKS §1, §5 「同意把评审的修正写进
  计划和文档」; the plan to be read through once more for consistency;
  code begins after this session's context is compacted 「我们在 compact
  后再开始写代码」.
- **K1**: the jobs session [682d5e] builds the client machinery, after
  steps 1–2 and the compilation code are on `main` (its DOC_SYNC_LIST.md
  entry 16); the owner: 「主要是 682d5e 的实现需要你负责的 logging system，
  请与 682d5e 沟通」.
- `isabelle scala_build` after steps 8 and 12: the owner's standing
  exception, not asked again.

**A failed compaction check ends the conversation** (2026-10-03, 「建议继续
结束 conversation」, the author's degrading declined): `check_failed` is an
`error` record, the conversation ends with a `TAT_InternalError` carrying
its `message`, the launcher prints it with `TAT.finished`'s messages, and
the agents read the internal error's line (LOGGING §4, written). The
wording of each check's `message` is still to be proposed to the owner;
[682d5e] owns the checks' design in CONSTRUCT_INTERACTION §8.

## Implementation (from 2026-10-03, 「准许开工」)

**Step 1, `log.py` and `test/test_log.py`** — written; 18 cases pass,
pyright clean. The shapes decided by the author, none a design change:

- An event method is declared by its signature alone: a decorator
  `_event(level)` makes the method's name the event, its keyword-only
  parameters the record's fields (a `**` parameter's entries flattened
  into them) and runs no body; pyright checks every call site against
  the declared fields (a misspelled field, a positional argument or a
  missing `message` is a type error — probed, `ai-artifacts/probes/log/`).
  `conversation.ending(exception, level=)` is the one method with a body:
  `class` is the exception's class name, `message` the one line of
  `traceback.format_exception_only` (module-qualified outside the
  builtins, never empty, never raising), `traceback` the formatted one.
- A field whose value is `None` is absent from `data`: this one rule is
  every "absent when" of LOGGING §4 (a compile's `start` without port and
  client, `operation` without `messages`, `result` without `class`,
  `client_refused` without `_meta`, …). Inside a value, `None` stays.
  Consequence: a `round_trip` whose callback returned `None` has no
  `result` field; `error` absent says it returned.
- The line a `warning` or `error` record sends to the RPC host's logger
  is its `message` alone, at the same level; it is sent whether or not
  the file could be written.
- Field names where the table gives only a phrase: `start` —
  `version`, `pid`, `working_directory`, `python_packages`, `port`,
  `client`; `ended` — `duration`; `result` — `text`, `messages`,
  `trailer`, `class` (the `TAT_Error` class's name; the parameter is
  `class_`); `hook.answer` — `judged`, `status`, `body`; `agent.created`
  — `identity`, `main`, `first`; `stop_judged` — `allowed`, `stands`;
  `interruption_judged` — `allowed`, `holding_work`; `evaluation.stopped`
  — `reason`, `tree` (the importing tree, for `import_without_theory`);
  `construction_cancelled` — `reason`; `walk_ended` — `outcome`,
  `slots_released`; `evaluation_dropped` — `dropped_by`; `message_posted`
  — `recipient`, `kind`, `source`, `interrupts`, `text`; `store.transaction`
  — `rows_written`, `nodes_deleted`; `_meta` spelled as MCP spells it.
  Durations are seconds, floats.
- `log.now()` is the `ts` function; the log directory's name (step 2) is
  `now()` with `-` for `:`.
- The test for "a file made read-only" makes the category's file a
  directory instead, which refuses `open` for root too.

**`walk_started` lost `evaluate`** (2026-10-03): the compilation session
[9779f8] edited LOGGING §4's row to "the destination, `ignore_error`,
`checks`" on its sixth review's ruling (COMPILATION_REVIEW.md §13 — every
walk evaluates; an edit with `evaluate` false starts no walk); accepted
and reflected in `log.py`. The same session reworded the `stopped` row's
reasons (its reader 8): "its own command failed (a stop, ARCHITECTURE
§3.3), the order constraint, an import with no theory value" — "an
obstacle" had covered a nesting node whose beginning failed, which the
walk goes past and which is no stop; accepted, no signature changes.

**The plan's step 8 test** corrected by the author: it said a `warning` is
written through `log.agent.check_failed`, which has been an `error` since
the owner's ruling above; the launcher case appends a `warning` record to
a file itself, no Python-side event being a `warning`.

**Step 2, the start order and the ending object** — written 2026-10-03;
the Isabelle-backed suite (test_conversation, test_forest_walk: 50 cases)
passes through the new start against a real `isabelle TAT_mcp`, and the
cases without Isabelle pass but for 18 that compare documents' text with
code the documents have moved ahead of (CLIENT_HOOKS §1's old hook files,
PRINT.md/RECALL.md/RENDER_BASELINES §5–§6 examples, EXCEPTIONS.md and
SESSION_AND_THEORY.md wordings, the tool descriptions) — none of them in
the files this step touched; they belong to the compilation and jobs
sessions' pending work. The author's shapes:

- The ending object is the class `Ending` in `mcp_server.py`, beside
  `stopped` and the new `connection_went(exn)` both use (the level of
  `ending` and the line of RENDER_BASELINES §4 come from the one test).
  It is an async context; `end(exn)` writes `ending` and cancels the
  spawned tasks; `spawn(coroutine)` registers a task; `unwound()` waits
  for every spawned task; `entered`, `ended_by`, `wait()`, `forest`,
  `log`. The server's exit is the drain: it enters the ending for
  whatever escapes its block, stops accepting, waits for the requests in
  flight and for `unwound()`, and stops — the stop in a `finally`, so a
  cancellation during the drain (the RPC host's, 3 s after the connection
  closes) skips none of it. The context's exit enters the ending for an
  exception escaping the start, waits again only on paths that never
  served, and writes `ended`, which carries the duration alone.
  `TAT_Server(ending, port, tools, on_compaction)` holds it as the public
  attribute `ending` and keeps no ending state; `serve` runs uvicorn's
  loop as a task, waits on the ending (a loop that fails on its own enters
  the ending as a bug), tells the loop to exit and raises `ended_by`.
- `toplevel.conversation(python_packages, working_directory, connection,
  port=None)` is layers 1 and 2 of MODULE_STRUCTURE §4.6, yielding the
  `Forest`, the `Loaded` plugins and the lock's `announce`; `toplevel.
  served(...)` adds layer 3 (the server, the port line, `serving`) and is
  what `launch_TAT` and the test harness enter. `TAT.log_directory` is
  not called yet (step 8).
- `start` records the installed distribution's version
  (`importlib.metadata`), `plugins_loaded` each kind's module.
- `Conversation(connection, working_directory, log, ending, seen=…)`;
  the cases without Isabelle build one through `test/stand_ins.py`, whose
  `Log` writes under the case's temporary directory (set by an autouse
  fixture in `conftest.py`), so no test log can land in the repository.
- `test/test_mcp_server.py` unpacks the six ending lines of
  RENDER_BASELINES §4 (the jobs session had widened it to four when the
  fourth line was added; the fifth and sixth are this design's).

Committed 2026-10-03 as `bd48a93` on the owner's 「请提交，请继续」, with
the sibling sessions' uncommitted work swept in and named in the message
(the CLAUDE.md rule for the shared tree); `ai-artifacts/probes/` and the
review directories stay untracked, as the precedent under `ai-artifacts/`
has only the plans tracked.

**Step 3, `isabelle_driver.call(conversation, name, args)`** — written
2026-10-03, uncommitted. `call` is the private `_call(connection, name,
args, log)` plus the record; the record is written from the trip's done
callback (`_trip_done`, where `_dropped` ran), so a trip whose caller was
cancelled is still recorded when it completes: `round_trip` with the
result or the error, a connection error included. The
`error` text is an `IsabelleError`'s messages one per line, any other
exception with its class (`ConnectionResetError: peer closed
connection`). `reset` passes no log. `Isar_State_Slot` holds the
`Conversation`; every caller passes it; `Forest` methods use
`self.conversation`. Tests: `test_isabelle_driver.py` asserts the records
in every case, including the cancelled caller's and the abandoned
failure's; the Isabelle-backed suite passes (50), and a real case's
`round_trip.jsonl` was read back: a unit-returning callback has no
`result` field, as decided above.

**Step 4, the funnels** — written 2026-10-03, uncommitted; every test
module of the plan gained its assertion on the records. The shapes:

- The tool boundary (`TAT_Server._call_tool`) writes `tool.call` for
  every call on arrival, then exactly one of: `result` (text, `is_error`,
  the `TAT_Error`'s class as `class`), `given_up` (the checkpoint after
  the body raised the client's cancellation: the answer went to nobody;
  `text` absent when the body produced none), `while_ending` (answered
  with the ending's line — the call that entered the ending and a call
  arriving during it alike). `messages=[]` and `trailer=None` until the mailbox exists
  (the jobs session fills them). `current_agent` and `current_call` are
  NOT set at the boundary, because both are the client subclasses'
  knowledge (the jobs session's): the call's id comes from the call's own
  `_meta`, under each client's key, and the agent on Claude Code from the
  announcement `agent_of_call` matched; the subclass sets `current_call`
  at the top of the handler and `current_agent` before `tool.call` is
  written, and resets neither in the body's `finally` (the review's
  boundary-4; an earlier version of this line said the call id was known
  only once the announcement matched, which was wrong).
- The setters take `duration: float | None` as a third positional
  argument; `Node._stored(ev, index, new, duration)` writes `operation`
  with `node=forest.full_id(node)`, `operation` one of `own`, `beginning`,
  `ending`, `ran=duration is not None`, `status` and `messages` from
  `_status_to_store(new)`, `messages` only when it ran; `_timed(hook)`
  measures the three hook calls. `Forest._handle_tree` writes `stopped`
  once per stop, with `command_failed`, `order_constraint` or
  `import_without_theory` — for the last also `tree`, the importing tree
  that was not run; its local `reason` carries no annotation, pyright
  checking it against the event. `Forest._run` writes `walk_started`
  (`checks` absent until the jobs' `checks` exists; `destination` absent
  for an invalidation only because an edit's invalidation still goes
  through `_run` — the decided target, funnels-2 of the review, in
  [9779f8]'s rewrite: walk records belong to the evaluating walk alone,
  `destination` is required, and an edit writes only its `operation`
  records and `committed`) and `walk_ended` (`outcome` `continue` or the
  stop's id, `slots_released` from `Evaluation.releases`, counted at each
  `flush` as the names of its `state_delete` and summed by
  `_handle_tree` over the trees' own evaluations).
  `_invalidate_changed_trees` returns the trees it invalidated for the
  `committed` record.
- `edit._committed(forest, operation, location, *, created, removed,
  moved, invalidated)` after each of the four commit blocks; `operation`
  is the entry's name (`insert`, `amend`, `delete`, `move`); `created`
  every node that entered, in tree order, as `[id, kind]`; `removed` ids
  taken before the nodes detached.
- `Forest_Store(path, log)`; `transaction()` writes `transaction`
  (`rows_written` as `[node, field]` pairs, `nodes_deleted`, `duration`)
  after the commit, `transaction_failed` before raising the
  `TAT_DisasterError`. Every test's store is built with `stand_ins.log()`.
- Ids in the records are `Forest.full_id`'s — the full id, linear in the
  node's depth — so the tests compare against `f.full_id(node)`, not a
  spelled-out id; `id_of`'s shortest form is for text an agent reads, and
  `resolve`'s exact match is `full_id(n) == id`. `id_of` keeps its own
  loop: it deletes components of the chain one at a time, which a full id
  as a string does not express.
- The compilation session [9779f8] began its rewrite of the walk, the
  setters, the commit blocks and the store the same day; told the exact
  places of every record so its rewrite carries them.

Steps 3–4 committed 2026-10-03 as `2e8f6e7` (「提交第 3、4 步」); the
owner then ordered the adversarial review of steps 1–4 (Workflow,
challengers → a fresh defender per finding → judge, Opus, xhigh) and
Batch 2 to start meanwhile, with no fix applied before agreement.

**Batch 2 (steps 5, 6, 8), the Isabelle side and the launcher** —
written 2026-10-03, uncommitted. Step 7 (`fork_job`) waits for the jobs.
The shapes:

- `Event_Log.never_raising : (exn -> unit) -> (unit -> unit) -> unit` in
  `contrib/Performant_Isabelle_ML/library/event_log.ML` (its own
  repository): the deferred-interrupt, every-failure-captured run that
  `append_string` did inline, now a function `append_string` calls with
  `warn_once` and TAT's log with `K ()`. `Event_Log_Test.thy` re-run from
  source on Pure after the factoring (`isabelle ML_process -l Pure`,
  `ISABELLE_EVENT_LOG_DIR` set): passes.
- `TAT_Framework.Log`: a JSON value type and `string_of` (strings
  escaped per JSON, control characters as `\uXXXX`, reals as six
  decimals), `timestamp ()` UTC to the microsecond, `datatype state =
  Held of string list | Writing of Path.T`, `type T = state
  Synchronized.var`, the process cell `current` (`get_current`, `renew`),
  `record log {event, level, data}` and `tell log directory` — both
  through `never_raising`, so neither raises nor reports. `category` is
  always `isabelle`; no `agent`/`call`.
- `bug_message` in the signature; `TAT_Common_Nodes.escapes` keeps its
  own search for a *nested* interrupt (a breakdown inside a `Par_Exn` or
  an `Exn.EXCEPTIONS`, which `Exn.is_interrupt` alone does not see) —
  the design's "`is_some (bug_message e) orelse Exn.is_interrupt e`" would
  have lost it, so the author kept the recursion as `interrupted`.
- `make_callback : ('a, 'b) callback -> callback'` = the wrapper + `mk_callback`:
  it captures the log current when the callback begins (so `TAT.reset`'s
  own `callback` record lands in the conversation it ends), times the
  function, writes `callback` {name, duration, outcome ∈ returned |
  raised | interrupted} and `bug` {message, callback} when `bug_message`
  finds one, and releases the result. `register_callback` stores
  `make_callback o f`; `framework_callbacks` and the test plugin give
  records, `mk_callback` appears nowhere else.
- `Slots.clear`/`Theories.clear` answer how many they cleared; `TAT.reset`
  writes `reset` {futures_cancelled: 0 until the jobs, slots_cleared,
  theories_cleared} and then `Log.renew ()`.
- `Loader.load` writes one `theory_loaded` {name, duration} per theory new
  in `Thy_Info` after the load, each with the load's whole duration.
- `TAT.log_directory` (`log_directory`, a value, the one framework
  callback a compile's command will carry): `Log.tell` then the protocol
  message `TAT.log_directory` carrying the path as `XML.Encode.string`,
  the way `TAT.finished` is sent. Python: `isabelle_driver.log_directory(
  conversation, directory)` sends `str(directory.absolute())`, called in
  `toplevel.conversation()` right after the `start` record.
- `tat.scala`: `class Log_Follower(progress)` — a daemon thread draining
  every 200 ms; `follow(dir)` drains the previous directory, prints `Log:
  <path>`, starts on the new one; `read` takes each `*.jsonl`'s complete
  lines from the last offset (an incomplete last line waits), parses each
  with `JSON.parse`, skips what is not JSON, prints `### <message>
  (<file>, <time after T>)` for level `warning`; `stop()` drains once
  more at the ending, before the `TAT.finished` messages. `lib/tat.jar`
  rebuilt with `isabelle scala_build` (the `no_build` line of
  `etc/build.props` removed for the build and restored). Lesson: the
  rebuild overwrote the jar under a running test child, which hung — the
  jar is rebuilt only with no `isabelle TAT_mcp` of mine running.
- Tests (test_conversation): the Isabelle side's `callback` records for
  the probes, `theory_loaded` for `TAT_Lib_Helper`, three `bug` records
  and `raised` outcomes in the escaping-callback case, `isabelle.jsonl`
  replaced by a directory with the probes still answering, and the
  launcher case appending a `warning` record (after a non-JSON line) and
  polling the child's output for the `Log:` and `###` lines.
- **An error of the author's, found and fixed the same day:** the
  replace-all that turned `Remote_Procedure_Calling.mk_callback` into
  `make_callback` at the seven framework callbacks also hit the one
  occurrence inside `make_callback`'s own body, so the function called
  itself; every `isabelle TAT_mcp` then recursed for minutes and died of a
  segmentation violation (return code 139), with nothing printed. Found by
  loading cut-down copies of the file through an editor session
  (isabelle-mcp): the definition compiled, its first application hung.
  The lesson: a replace-all over a file must be checked against the
  definition of the name it introduces. The owner approved `isabelle
  build` for this diagnosis (2026-10-03, 「批准你使用 isabelle build 进行编
  译」); the `Isabelle_RPC` and `Performant_Isabelle_ML` heaps, outdated
  by the `event_log.ML` edit, were rebuilt under that approval.
- A second defect found by the same run: the launcher's follower died —
  and with it the `TAT.log_directory` handler and the launcher, exit 2 —
  when a log file could not be read (the test that puts a directory where
  `isabelle.jsonl` was). `read` now tries each file under `Exn.capture`
  and keeps its offset on a failure: the log is nothing the launcher may
  fail over. Jar rebuilt.
- Verified: the Isabelle-backed suite passes whole (52 cases), the
  launcher prints `Log: <directory>` for every conversation and the `###`
  line for an appended `warning` record, and a real `isabelle.jsonl` was
  read back — `callback` for every run, `bug` for each `Bug`, `reset`
  followed by `TAT.reset`'s own `callback` record in the old log.

## The code review of steps 1–4 (2026-10-03)

`review/LOGGING_CODE_RULING.md` and `review/LOGGING_CODE_DEBATE.md`:
7 challengers, 36 findings, a fresh defender each, one judge (Workflow
`wf_ed0bd73e-b35`, Opus, xhigh). Accepted apart from 28 items the author
fixes and resubmits, and 6 the owner decided (「1. (a) 2. 赞同你的建议
3. 赞同 (a) 4–6. 赞同你的建议」), all written:

1. **log-7** — LOGGING §5 and LOGGING_PLAN describe the implemented shape:
   one attribute per category, `note(message, **fields)` on each.
2. **start-3** — the server's exit is the one drain: MODULE_STRUCTURE
   §4.6's doors gain "at the server's exit, for whatever escapes the
   third layer, so that the server stops only after the ending's calls
   are answered"; `TAT_Server.__aexit__` enters the ending, stops
   accepting, waits for the requests in flight and the spawned tasks,
   then stops; `serve` shrinks (to be coded with the 28).
3. **elegance-6 + start-6 + elegance-5** — `ended` carries only how long
   the unwinding took (LOGGING §4); the counts and `_calls_cancelled` go.
4. **elegance-13 + driver-1** — `connection_lost` folded into
   `round_trip`: one record per trip, the connection error as its error
   (LOGGING §4, §5; the plan's step 3).
5. **funnels-6** — `stopped` gains, for `import_without_theory`, the
   importing tree that was not run (LOGGING §4): an optional `tree`
   field, written in `_handle_tree`.
6. **boundary-1 + elegance-11** — `given_up`'s text "when it produced
   one" (LOGGING §4): the checkpoint branch always writes `given_up`,
   `text` absent when the ending answers.

The 28 author items are listed in the ruling. The owner: 「好，你先自行
修吧，但我没看，不能 endorse，如有必要你需要 run agents 来 verify」, and the
division approved. Written 2026-10-03 (the suite without Isabelle: 300
pass, the 18 doc-drift failures unchanged):

- Done in the code — the tests and the record lines the ruling also asked
  for only in part, as the verification below found; the send-backs
  closed the gaps: log-1 (`ending`'s `message` is
  `traceback.format_exception_only`'s one line — for a class outside the
  builtins it carries the module,
  `isabelle_theory_agent.exceptions.TAT_InternalError: …`; the start-1
  test on `Ending.end` was missing), log-2 (`Literal` fields), log-5
  (`class_` → `class`; the suffix rule first ran after the `**` merge),
  log-6, start-2 (`Ending.unwound()`; the server-level test missing),
  start-3 (the drain is `TAT_Server.__aexit__`; `serve` still stops
  accepting as soon as the loop exits, so a call arriving after `serve`
  raised is refused at the transport; the window test missing),
  start-4 (`asyncio.wait({main_loop})`; its test could not fail),
  start-5, start-7 (both tests), driver-2 (`TAT.gone`; the docstrings
  not), driver-4 (`_text` shared), elegance-14's rename (`_trip_done`),
  funnels-1 (`Forest.full_id` in every record; not yet in `resolve`),
  funnels-3 (`_changed`, net effect; the test_store test, not test_edit's
  assertions), funnels-5 (counted at `flush`; no test), funnels-8
  (`_status_to_store`), elegance-3 (`stopped` once in `_handle_tree`,
  with `tree`), boundary-1/2/3 (`Answer(text, is_error, class_)`, `_run`
  refuses a non-text; the name not put to the owner), tests-6, the six
  owner decisions.
- Done later the same day: log-3 (`baselines.event_tables` reads LOGGING
  §4; test_log checks the categories, events and levels against it — the
  names check with a hand-written exception for `ending`), log-4 (one
  reader, `stand_ins.records`; the three wrappers kept as forwarders,
  test_log's own fixture kept), tests-7, driver-5 (`Probes.conversation`;
  the nine stubs' `conn` left, wrongly — they hold a `Conversation`),
  start-8 (the leaf-exists case, `now` patched), funnels-7 (b) (the sum
  asserted after the `ignore_error` walk, where it is 0 == 0), tests-9
  (the `committed` assertions for insert, two moves, amend, delete, and
  `removed` in the children-first delete; the third bullet not),
  boundary-4 (the notes; [682d5e] told). Waiting for [9779f8]'s rewrite:
  funnels-7 (d) and the second half of tests-2 (the first half, the
  vacuous assertion deleted, is done). Handed to [9779f8], acknowledged:
  funnels-2's code, funnels-4's guard, elegance-8. Still the author's,
  after the rewrite: funnels-2 (iii), a test_edit assertion that a move
  writes no `walk_started`; funnels-4's test, once the guard lands — a
  second strict walk past the same stop writes no `operation` record for
  nodes already stored as not_evaluated, while a change from ready to
  not_evaluated is still recorded. The suite without Isabelle: 304 pass,
  the 18 doc-drift failures unchanged; the Isabelle-backed suite: 52 pass.
- Committed as `d9472b3` (TAT) and `67a504b` (Performant_Isabelle_ML)
  on 「请提交」, 2026-10-03.

**Verification of the fixes** (`review/LOGGING_FIXES_VERIFICATION.md`,
Workflow `wf_c51d022f-526`, 31 verifiers + judge): **not accepted** — the
production fixes are sound and match the ruling; what fails is tests the
ruling asked for and left out, records marked "Done" with parts missing,
docstrings naming the review, and one real defect: `TAT_Server.__aexit__`
waits (requests, `unwound`) before the teardown with no `try/finally`, so
the RPC host's cancellation 3 s after the connection closes skips
`_stop_listening`/`aclose`/`shutdown`. 24 send-back items, all listed in
that file — the next work, before anything else of the plan: the
start-1/start-2/start-3/start-4/funnels-5/funnels-6/funnels-3/tests-9
tests; the try/finally; `_handle_tree`'s duplicate `Literal`; log-3's
exact names check and baselines docstring; log-4's leftovers in
test_log; log-5's suffix rule applied before the `**` merge and the field
list here; the two LOGGING §4 clauses added beyond the approved wording
(`ended`: "each call's and each job's fate is in its own record";
`round_trip`: "— the connection error, when the connection went —") to
revert or put to the owner; the `_answer` name clash with the module
function; driver-2/driver-5/boundary-2 docstrings and renames;
funnels-1's `resolve`/`id_of` reuse; funnels-7 (b)'s assertion placed
after the strict walk; telling [9779f8] about `_changed`, `flush`,
`_status_to_store`, `full_id` in its files; and this record's "Done"
lines corrected in place. The author's "Done" lines above were
overstated for log-3, log-4, log-5, start-1/2/3/4, driver-2, driver-5,
funnels-1/3/5/7(b), tests-9 and boundary-3; they are corrected in place,
as are the step-1 to step-4 lines the verification named.

**The two LOGGING §4 clauses stay** (owner, 2026-10-03: 「问题不大，在日志
里的措辞不用那么谨慎，如果有更多信息量的话可以加上」): the `ended` row's
"each call's and each job's fate is in its own record" and the
`round_trip` row's "— the connection error, when the connection went —"
are approved after the fact, and a clause that adds information to a
LOGGING §4 row may be added without a fresh approval. That send-back item
(elegance-6 + elegance-13's wording) is closed; the other 23 stand.

**The send-backs** (2026-10-03). The production side, the author's:

- `TAT_Server.__aexit__` runs the stop (`_stop_listening`,
  `_running.aclose()`, `_uvicorn.shutdown`) in a `finally` after the
  drain: the one defect. The order on the normal path is the approved one.
- `_handle_tree`'s local `reason` lost its `Literal` annotation; `resolve`
  matches exactly through `full_id`; `id_of` keeps its loop (step 4
  above says why).
- `_event` applies the `_` suffix rule to the declared parameters only,
  computed once at declaration; a `**` entry is written under the name
  given, as `note` writes it.
- Put to the owner: the one sentence of CONSTRUCT_INTERACTION §9 ("`serve`
  waits for the tasks to unwind before the store closes" — the server's
  exit does); the name of the boundary's tuple, `Answer`, whose root the
  jobs vocabulary uses for the agent's answer to a question (`answer`,
  `Answered`, `BadAnswer`), and with it the method `_answer`, which shares
  its name with the module's HTTP `_answer`.
- [9779f8] told of `_changed`, the counting at `flush`, `_status_to_store`
  in `_stored`, `full_id` (in `resolve` too), the one `stopped` write in
  `_handle_tree`, and elegance-8's name from the design's phrase "the
  edit's one store transaction".
- The tests, written by three subagents briefed from the verification's
  "Sent back" (one per file group), their diffs read by the author and
  their mutation checks run in memory through pytest plugins, never by
  editing the package. test_mcp_server: `end` with an exception whose
  `__str__` raises, a task spawned (`wait()` returns, `entered`, the task
  cancelled — the one test failing with `str(ended_by)` put before
  `_entered.set()`); the connection going before `serve` with `slow` in
  flight (the connection-gone line; `call`, `ending`, `while_ending`,
  `ended` in timestamp order — fails, by hanging, without `end(exc)` in
  the server's exit); a task reading the store while it unwinds, through
  `served()` and `serve()` (fails without `unwound()` in the exit; sleeps
  0.3 s past uvicorn's tick and shutdown); the host's cancellation during
  the drain (nothing accepts, no connection left, the manager's run
  closed, no cancel-scope error — fails without the `finally`); the
  loop-failure test parametrized over "another door first" (`exn is
  first`; the text `loop-bug`; a fresh POST refused — both fail with
  `await main_loop` back); `slow_bug`'s `[(call, slow_bug), (given_up,
  slow_bug)]`; the comment and docstrings; helpers `launched`
  (`launch_TAT`'s shape) and `refused_at_the_transport`; `Recorder` and
  `cancelled_by_the_host` imported from test_toplevel (a `Recorder` in
  stand_ins would be cleaner — later). test_forest_walk: the two-importers
  case (fails with `tree=` the first importer); the per-tree sum after the
  strict walk, 4 = 2 + 2 (fails with the sum dropped or doubled); the
  whole amend `committed` record, `invalidated` = the replacement
  (renamed), B, C. test_edit: `nodes_deleted` on the real path — insert,
  both moves and the amend `[]`, the delete `[a]`, the children-first
  delete `[sec, a, b]` literal (fails with a deletion kept through a
  later `put`); the childless block's amend, `slots_released == 3` (fails
  under the old counting). test_store's comment. test_log: the names
  check over every public method but `note`, the log-4 shape, a `**`
  entry `path_` kept. test_isabelle_driver, test_toplevel, the nine stubs.
- Departures from the ruling's letter, with the reason: `only` keeps its
  two lines (the one-line form would drop "exactly one record"); `id_of`
  keeps its loop (step 4 above); the amend's `nodes_deleted == []` is one
  assertion beyond the ruling's three (it pins the delete-then-put path).
- A consequence of the `finally` to know: the host's cancellation landing
  mid-drain cuts the drain short, so a call still in flight then gets no
  answer (`given_up` written) — as before start-3; the teardown now
  completes where it was skipped.
- The suite without Isabelle: 304 pass, 15 known doc-drift failures (the
  14 of other sessions' documents and `test_on_compaction_answers_the_
  briefing_in_the_clients_shape`, which goes with `/on-compaction`).
  The Isabelle-backed suite (test_conversation, test_launcher): 26 pass,
  the 3 known test_launcher failures (CLIENT_HOOKS §1's fenced blocks
  moved by another session).
  pyright: the package and test_mcp_server, test_log, baselines,
  test_isabelle_driver, test_toplevel, test_store at 0; test_model and
  test_session_theory (15) and test_forest_walk and test_edit (54, plus
  one in the new two-importers test) carry errors from before this work
  — the files' `f.sub_nodes[0].sub_nodes` idiom and `Node.runs`.
- **Verified** (`review/LOGGING_SENDBACKS_VERIFICATION.md`, Workflow
  `wf_62d19433-b05`, 23 verifiers + judge, Opus, xhigh, 20 minutes):
  **accepted** — all 23 items done, every mutation check failing the
  test it should, no send-back; the judge dismissed as hair-splitting
  test_log iterating over LOGGING §4's categories only, the late call's
  arguments not asserted, `_event`'s docstring showing the rule by its one
  instance, `id_of`'s own root case, `Recorder` imported from
  test_toplevel. One item for the owner: to confirm the `finally` in
  `TAT_Server.__aexit__` and its consequence (above).
- The boundary's tuple is `Result(text, is_error, class_)` (owner,
  2026-10-03, 「赞同 Result」 — the design's word for what a tool call
  returns: MODULE_STRUCTURE §4.6, LOGGING §4's `tool.result`, MCP's
  `CallToolResult`); `_result_of(name, body)` decides it,
  `_call_tool_result(text, is_error)` renders MCP's form; the HTTP
  `_answer` keeps its name alone. CONSTRUCT_INTERACTION §9's sentence
  reworded as proposed (owner, 「批准」).

**Division with the jobs session [682d5e]** (2026-10-03, its question;
the owner: 「按你推荐的最佳方式来分工」): step 7 — `fork_job`, `TAT.job_cancel`,
`job_finished`, the wire shapes, the `TAT_InternalError` on `["bug", …]`
and the ML records `job_forked`/`job_ended`/`report_undelivered` through
`TAT_Framework.Log` captured at the fork — is [682d5e]'s whole; the
author's step 7 becomes a review of that code against LOGGING §4. Batch
3's order: [682d5e] lands `-c`, the two `TAT_Server` subclasses, `POST
/hook`, `event_of_hook`, `agent_of_call` (and threads the client name
into `start`); steps 9–11 sit on it; `hook.py` is CLIENT_HOOKS §1 and
nothing beyond. Step 13 and [682d5e]'s smoke run are one live run, after
both sides are in, with both plans' measurements taken in it.
The order after its plan's review (2026-10-03): step 9 now; step 10
after its step 1 (`-c`, the subclasses, the `configure` call point);
step 11 after its step 2 (the announcement, `agent_of_call`,
`ClientRefused`); LIP's steps 7 and 11 and its division paragraph
brought in line. Its one refusing method on `TAT_Server` writes
`client_refused` and enters the ending with the `ClientRefused`; the
sandbox check calls it.
[682d5e] also adds `ClientRefused(TAT_StartupError)` with its `line`,
`stopped()`'s branch answering it and RENDER_BASELINES §4's fourth and
sixth lines (its two refusals: `clientInfo`, Claude Code's missing
transcript); step 11 adds the sandbox check with the fifth line, calling
that method, which writes the `client_refused` record. Announced by
[682d5e] for its steps: `TAT_Server` loses `on_compaction` —
`/on-compaction`, `mcp.on_compaction` and
`test_on_compaction_answers_the_briefing_in_the_clients_shape` go in its
step 4, with the per-agent seen set, not with `POST /hook` (its step 2),
since until then the old path is what clears the one set; the server is
built in `served()` from the client's subclass; `configure(
working_directory)` a base method called before the port is bound,
empty until step 10;
`Tool.run` takes the calling `Agent`; `Ending.end` cancels the
construction jobs and drops the evaluation jobs in its synchronous
stretch — told to keep `_entered.set()` unconditional and `forest` None
before the start built it. The SDK runs each message in a task of its
own (`Server.run`, mcp 1.26.0: `tg.start_soon(self._handle_message, …)`),
confirmed by [682d5e], so the context variables set in the handler reach
no other request.

## Batch 3 (from 2026-10-03, after `df271ca`)

The owner asked whether the send-backs' delta needs a review of its own;
the author's answer: no — four small production spots and the tests, each
verified with mutation checks by a verifier of its own; the next review
is Batch 3's, which may look at this delta too.

**Step 9, `hook.py` and `guard.py`** — written 2026-10-03. The author's
shapes:

- Both scripts are modules of the package (MODULE_STRUCTURE §4's listing),
  standard library only, run as `'<python>' -I '<wd>/.tat/<script>'`;
  each finds the working directory as the parent of its own directory.
- `hook.py`: `tat.lock`'s first two lines (pid, port — `toplevel._held`'s
  format: a cleared or half-written file has fewer), `os.kill(pid, 0)` for
  the holder's life, `urllib.request` with `ProxyHandler({})` so the
  address itself is connected whatever proxy the environment names, the
  payload posted byte for byte with `Content-Type: application/json`, a
  200 answer's body written to stdout unchanged (an empty body is an
  empty answer); any other status, and every exception, is exit 1 with
  CLIENT_HOOKS §1's line on stderr.
- `guard.py`: the probe `tat_guard5.py` without its probe-only parts;
  `hook_of(payload)` names the hook served — `write`, `launch`,
  `worktree` or none — and is read again by the failure branch, which
  answers as that hook needs (a write refused with the first sentence, a
  worktree refused with the sentence and exit 1, a launch left undecided
  with exit 1, a payload whose hook cannot be told refused as a write);
  `tool_input` is taken strictly (`payload["tool_input"]`), so a
  malformed one is a failure of the guard's own.
- `test/test_scripts.py`: the scripts copied into a temporary `.tat/`
  beside a `TAT.agents/` and run through `subprocess` as the client runs
  them; the sentences read from CLIENT_HOOKS §1 and §5's fenced lines;
  a stub `HTTPServer` answering `/hook` with a given status and body,
  keeping the requests (path, content type, payload); the lock's five
  states as test_launcher listed them; a proxy named in the environment
  ignored. 11 cases pass.

**Step 12, the launcher's bracket refusal** — written 2026-10-03. The
check sits in `TAT.working_directory(arg)`, which both tools call right
after `Getopts`, so it comes before every other check and a bracket path
that does not exist is refused as such by `TAT_mcp` too (MODULE_STRUCTURE
§5 lists the refusals as alternatives, not in an order); the sentence is
the design's, through `error`, exit 2. `lib/tat.jar` rebuilt with
`isabelle scala_build` (no `isabelle TAT_mcp` running; `etc/build.props`'s
`no_build` line removed and restored). test_launcher: the new case
passes for both tools and both bracket characters; the 3 known failures
(the old hook files, [682d5e]'s to retire) stay. A slip of the author's,
caught at once: the rebuild script assigned zsh's read-only variable
`status` after the build and aborted before restoring `build.props`,
which was restored by hand from the backup — a shell script around a
build restores in a `trap` or avoids shell-reserved names.

**The review of Batch 3's code** (owner, 2026-10-04: 「跑一轮小评审」;
`review/LOGGING_BATCH3_REVIEW.md`, Workflow `wf_8ef84f09-ade`: three
challengers capped at four findings each, a fresh defender per finding,
one judge, Opus, xhigh, 21 minutes): **not accepted**. The production
code of `hook.py` and `guard.py` is correct; commit `cdb776c` and the
four assertions drew no finding. Ten findings, six defects, five of them
in `test/test_scripts.py` — a check the design requires can be deleted
with every test green: the path must be absolute (`run` did not start
the scripts in the agent directory, where the client starts them); the
agent directory made canonical (the temporary directory holds no
symbolic link); the pid check (the dead holder's lock named a port
nothing listens on); the lock's format (written by hand, not through
`toplevel._held`); the proxy ignored (the shell's `no_proxy` exempts
127.0.0.1) — and one of shape in `guard.py`: `main`'s failure handler
repeats the dispatch, its worktree branch calling the failed function
again, and the worktree line of the own-failure test fails nothing. One
question for the owner: CLIENT_HOOKS §1 names `urllib`; `http.client`
reads no proxy variable and follows no redirect, so the hook's two
promises would hold by construction. Nothing is changed before the owner
agrees to the fixes.

The owner (2026-10-04): the fixes need no item-by-item discussion —
「如果需要跟我讨论请给我具体问题，否则请 run Opus agents 来 review」; on
the library, 「问题不大，可以接受。建议用性能好的那个」. Measured: under
`-I`, `import http.client` costs about 11 ms and `import urllib.request`
about 17 ms (the whole process 35 ms against 41 ms, a bare interpreter
21 ms), and the hook runs at every TAT tool call; so `hook.py` posts with
`http.client.HTTPConnection`, CLIENT_HOOKS §1's sentence names
`http.client`, and what goes over the wire is unchanged. The fixes, as
the judge ruled them:

- `test_scripts.run` starts every script in the agent directory, where
  the client starts it, and the relative-path case is `a.md`.
- The fixture's working directory is reached through a symbolic link, so
  every case runs on a linked path.
- `guard.main` answers each failure beside the step it covers — a payload
  whose hook cannot be told, the write's judgment, the launch's — and the
  worktree's answer, which reads nothing, stands outside every handler;
  the answers are unchanged. The own-failure test's worktree line, which
  failed nothing (a worktree reads no `tool_input`), is replaced by the
  one failure a worktree creation can have: a standard error that cannot
  be written — still a failure, never exit 0 or 2. A departure from the
  plan's step-9 test list, which named the old line.
- The hook's tests take the lock through `toplevel._held` itself and
  walk its states: absent; held, no port yet; a port nothing accepts on;
  cleared; left by a holder that died (a child process that `os._exit`s
  inside `_held`) with a live stub server on its port — the hook fails
  and the stub received nothing, which pins the pid check.
- The proxy case empties `no_proxy`/`NO_PROXY`: a proxy named, no host
  exempted.

Mutation checks, on copies of the scripts swapped in through a pytest
plugin: without `isabs`; without the agent directory's `realpath`; the
worktree inside a handler that falls back to the write's refusal; without
the pid check; with a library that reads proxies; without the status
check; `_held` writing another format — each fails at least one case;
unmutated, 11 pass, also with `NO_PROXY=127.0.0.1` inherited.

**Verified** (`review/LOGGING_BATCH3_FIXES_VERIFICATION.md`, Workflow
`wf_dc399a14-c99`, five verifiers and a judge, Opus, xhigh, 11 minutes):
**accepted**, no send-back. The verifiers' own checks: the old and the
new guard answer alike over 978 payload and stream combinations; the
request on the wire is unchanged but for urllib's `User-Agent` and
`Connection: close` headers, which TAT's server reads neither; a mutant
for every ruled check fails. Known and accepted: an answer of 301, 302 or
303 from whatever listens on the lock's port is now "TAT is not
running", exit 1, where urllib followed it — TAT's server sends none;
the hook's run takes about 55 ms where it took 86 ms.

Steps 9 and 12 committed 2026-10-04 as `ba5f999` (「提交」), [682d5e]
told. Steps 10, 11 and 13 wait: 10 for [682d5e]'s step 1, 11 for its
step 2, 13 for both sides.

The sessions' refs changed with a restart of the machine (2026-10-04):
the jobs session, [682d5e] in this record, is now listed as [9ffa3c]
(it confirmed); the compilation session, [9779f8], as [ebfd21]; this
session, [9904c0], as [b341d7]. A ref is the listing's, not the
session's: after a restart, `ListAgents` before any message.

**The compilation session's plan** (2026-10-04, its message;
`ai-artifacts/COMPILATION_IMPLEMENTATION_PLAN.md`, start approved by the
owner, no code yet). What touches this work, and the answers given:

- After its step A1 `walk_started` carries `checks` (`"no"` until the
  jobs code passes another value) and an edit writes no
  `walk_started`/`walk_ended`; it changes
  `test_blocked_by_a_failed_header`'s expected data and rewrites the
  childless block's amend case (the one `state_delete`'s three names; no
  `walk_started`). Asked to keep, in the same change, the pin on how
  `slots_released` is counted — that case is the only test failing under
  the old per-`release()` counting. It carries the pin (its plan's A7,
  case 9) in two forms: a direct case on `Evaluation` (one slot released
  twice, one flush, the `state_delete` naming it once, `releases == 1`)
  and a walk over a tree holding a nesting node with an owned slot
  (`owned_slots`), invalidated whole after a strict stop before it,
  `walk_ended.slots_released == len(names)`. The scenario the author had
  proposed was wrong, corrected by that session: a childless block
  invalidated whole by a walk releases two different slots; the amend's
  double release came from `old._states_inside()` and
  `old._state_after_beginning()` naming one slot, which only an edit
  does.
- elegance-8 lands as one function, `_store_transaction(...)` in edit.py,
  not the context manager the ruling named: what each entry stores is
  data, so the block has no body; it runs the edit's one store
  transaction and then writes `committed`. Agreed, a departure from the
  ruling's letter that keeps its point — no entry can commit without the
  record.
- Its step A5 changes log.py's `IsaTerm` import line: the shared class
  is AoA's, moved unchanged into Isabelle_RPC (the owner, 2026-10-04, as
  that session reports); `from_isabelle` and `from_agent` keep their
  names, so test_log's `IsaTerm` case stands.
- It tells this session when A1–A3 are in the tree; then the author's
  three waiting tests: a move writes no `walk_started`; funnels-4's test;
  tests-2's second half.
- A1–A3 (and A4–A6) in the tree, 2026-10-04, uncommitted. The author's
  waiting assertions, four with funnels-7 (d), written against it inside
  three existing test functions and green: test_model's
  `test_b_a_stop_strict_then_ignore` — the second strict walk past the
  same stop writes `walk_started` and `walk_ended` alone (funnels-4;
  with the setters' guard `_unchanged` made never to hold, in memory,
  the test fails), and the strict walk after the `ignore_error` one
  writes T2, the section's ending, T3 and T4 each as `{operation, ran:
  false, status: not_evaluated}`, no messages, no duration (funnels-7
  (d)); test_forest_walk's
  `test_evaluate_to_inside_an_import_invalidates_its_importers_whole` —
  the walk's `operation` records are A's ending and B's and C's
  beginnings and endings, from the nodes, each written by no run
  (tests-2); test_edit's `test_move_between_parents` — moving an
  evaluated node writes `operation` records and no walk record (funnels-2
  (iii)). They are in that session's uncommitted files and go into its
  Phase A commit, named there as the author's. The `slots_released` pin
  is its `test_model.py::test_slots_released_counts_each_deleted_name_once`.
- After Phase A's own review (its message, 2026-10-04): the `operation`
  record is written in `Node._written(ev, index, old, duration)`, the
  setters' shared tail, before `on_invalidated` — `_stored`, named in
  step 4 above, is gone; `Forest._run(destination, ignore_error,
  checks="no")` makes the walk's `Evaluation` itself. The records are
  unchanged. Its review mutation-checked the author's four assertions
  and found them pinning, and added two cases on these funnels: a loaded
  node's invalidation writes `slots_released == 0` and no `state_delete`;
  a two-tree walk makes one store transaction per tree.
- Phase A committed 2026-10-04 as `dfefca1`, the author's four
  assertions in it and named as such; with `cb886e7` under it the suite
  without Isabelle is 330 pass, the 15 known document-drift failures.
  Every test the code review of steps 1–4 left with the author is now
  written. Before its step B5 touches `mcp_server.stopped` for the
  seventh reason, that session tells this one — told and agreed
  2026-10-04: one branch, `CannotUseWorkingDirectory` (a
  `TAT_StartupError` of `model`), through `stopped_for`; no branch of
  `stopped` may test the base class, since `ClientRefused` is another
  subclass.
- The order changed (the jobs session's message, 2026-10-04): the owner
  has not yet let its steps 1 to 3 start, and the compilation session's
  Phase B now edits the ML files, tat.scala, the jar, toplevel.py,
  exceptions.py, harness.py and Test_TAT_Framework.thy; so the jobs
  session's step 1 and step 2 start after Phase B, when those files are
  free and the owner allows. Steps 10 and 11 here wait for them as
  before, so now behind Phase B as well. The owner (2026-10-04): 「建议等
  compilation 那个工作进行到不能再继续，你再考虑继续。请耐心等待」 — this
  session writes nothing ahead meanwhile (not the parts of step 10 that
  need no subclass, not the move of the test stand-ins) and waits for the
  compilation session's notice.
- Phase B committed 2026-10-05 as `ee9e4f5`. In this session's files it
  carries only what was told: `stopped`'s branch for
  `CannotUseWorkingDirectory` and its assertion; `stand_ins.conversation`
  on a per-case working directory; harness's exit 2 and the group
  helpers. `_held`'s format unchanged; test_scripts, test_log,
  test_mcp_server, test_toplevel: 61 pass, the one known failure. The
  jobs session's steps 1 and 2 may now start on the owner's word; steps
  10 and 11 here follow them.
- The jobs session's step 1 began 2026-10-05 on the owner's word (`-c`,
  the two `TAT_Server` subclasses, `configure` as the base's method, the
  bound variable), editing tat.scala, the jar, the ML boot and framework,
  toplevel.py, mcp_server.py, harness.py, Test_TAT_Framework.thy,
  test_launcher.py, test_toplevel.py; not `Ending`, `stopped`,
  `stopped_for`. This session touches none of those files until it says
  step 1 is in; asked of it: `configure` empty on the base, called in
  `served()` before the port is bound; the client name into `start`'s
  `client`; the jar rebuilt only with no `isabelle TAT_mcp` running;
  `tat.lock`'s format kept.

**Step 10, `configure`** — written 2026-10-05 on the jobs session's step 1
(in the tree, uncommitted: `TAT_Server.configure(working_directory)`
declared empty on the base and called by `served()` before the port is
bound; `Claude_Code_Server`, `Codex_Server`, `SERVERS`). The author's
shapes:

- The base's `configure` does what both clients share: the agent
  directory `TAT.agents/` made when absent; the client's files, which
  `self._client_files(working_directory)` gives as name-within-the-agent-
  directory → text, written whole; both scripts copied from the package
  into `.tat/` for either client (MODULE_STRUCTURE §5: "the two scripts"),
  nothing else there touched; the `configured` record, whose `files` are
  the paths written, relative to the working directory, in that order
  (`TAT.agents/.mcp.json`, `TAT.agents/.claude/settings.json`,
  `.tat/hook.py`, `.tat/guard.py` for Claude Code).
- Each subclass's `_client_files` builds its files as Python values and
  encodes them once: JSON through `json.dumps` (`_json`, indent 2); the
  TOML as a template whose values go through `toml_string` — the TOML
  basic string with `"` and `\` escaped and every control character and
  DEL as `\uXXXX`. One base helper, `_hook(working_directory, script,
  matcher=None)`, builds every hook entry, the command
  `shlex.quote(sys.executable) -I shlex.quote(<wd>/.tat/<script>)`, the
  timeout `HOOK_TIMEOUT` = 10.
- `resolver_entry(resolv_conf)`: the real path when outside `MINIMAL`
  (CLIENT_HOOKS §5's eight directories), else None; the Codex subclass
  calls it on `RESOLV_CONF` (`/etc/resolv.conf`), a module constant the
  test replaces with a fake layout.
- Tests (test_mcp_server, "configure"): the written files parse and equal
  CLIENT_HOOKS §2's and §3's fenced blocks with the placeholders filled,
  a hook command compared as its `shlex` tokens so that an interpreter
  path with a space and a `'` compares as the shell reads it — and the
  written command checked literally once, `shlex.quote`'s spelling; the
  TOML with and without the resolver line (a fake `resolv.conf` linking
  outside, or to `/etc/hosts`); the scripts equal the package's, a stale
  script overwritten, the user's file and the log left in `.tat/`; the
  `configured` record; a second `configure` leaves an agent's file in the
  agent directory; `resolver_entry` on a fake layout; `toml_string`
  round-tripping through `tomllib`. CLIENT_HOOKS §4's "exact project-level
  file names … confirmed at implementation" is step 13's.
- The record `configured` now sits between `plugins_loaded` and `serving`
  in every conversation's log; the expectations in test_toplevel (two
  spots) and test_conversation (`test_a_fresh_conversation_holds_nothing`,
  which also checks `.mcp.json` and `.tat/hook.py` exist) follow. The jobs
  session's step 1 committed by itself as `b3ab4ec`; the fast suite with
  step 10 on it: 369 pass, 14 known document-drift failures; the
  Isabelle-backed suite: 35 pass, the 3 known test_launcher failures (the
  old hook files, the jobs session's to retire). pyright: mcp_server.py,
  test_mcp_server.py, test_toplevel.py at 0.
- Committed 2026-10-05 as `55e9f20` (「提交」). The jobs session's step 2
  began the same day: `ClientRefused(message, line)` in exceptions.py,
  `jobs.py`'s `Agent`, test/test_hooks.py, the harness announcing its
  calls to `/hook`; in mcp_server.py one branch first in `stopped`,
  `isinstance(ended_by, ClientRefused)` → `ended_by.line`, and the one
  refusing method `TAT_Server._refuse(message, reason, client,
  _meta=None)`, which writes `client_refused` and enters the ending with
  `ClientRefused(message, stopped_for(reason))` — step 11's sandbox check
  calls it with `Codex's sandbox is not the one TAT configured`. This
  session leaves mcp_server.py and test_mcp_server.py to it until step 2
  is in. The author recommended to the owner a small review of step 10
  now (its files configure the clients' sandboxes; the tests compare them
  with the documents, so a mistake shared by both would pass), awaiting
  the word; ordered (「请跑第 10 步的小评审」), Workflow `wf_14aadf89-f37`.
- In log.py, by the jobs session (told after, three lines): the `Literal`
  of `hook.answer`'s `judged` is the module-level alias `Judged`, used by
  `answer` and imported by mcp_server.py for `_judge`'s return type and a
  local. A departure from log-2's letter ("no alias names"), kept: the
  ruling's reasons were a second meaning (`Edit_Operation`) and a coined
  noun (`Stop_Reason`), and `Judged` is the field's own name; an inline
  `Literal` would have to be written twice, in the event and in the
  function that computes the value, which is the duplication the ruling
  was against.
- The jobs session's step 2 in the tree and tested (2026-10-05, awaiting
  the owner's commit). What step 11 builds on: `TAT_Server._refuse(message,
  reason, client, _meta=None)`, `client` a `types.Implementation` (name,
  version); `_check_client(session)` once per `ServerSession` at
  `tools/list` and `tools/call`; `_call_tool` reads `request_ctx.get()`
  for the call's `meta` and `session`, so the sandbox policy is in
  `context.meta` there; `ClientRefused(message, line)` defined in
  mcp_server.py; `stopped`'s first branch returns its line. Step 11 starts
  after step 2's commit, so the files' hunks stay apart.

**The review of step 10** (`review/LOGGING_STEP10_REVIEW.md`, Workflow
`wf_14aadf89-f37`, three challengers, a defender per finding, a judge;
20 minutes): **not accepted**. Eleven findings, eight rulings for the
author, one for the owner, two dismissed. The files written are right;
the way they are written has a hole: `configure` writes through a
symbolic link an agent left at one of TAT's names in the agent directory
(`.claude`, `.mcp.json`, `.codex`), outside any sandbox — the same-client
Codex route is closed (a defender measured Codex's sandbox mounting
`.codex` read-only), the cross-client route is open (a Codex agent links
`.claude` into the user's home; the next `-c claude-code` launch
overwrites the user's own settings). Smaller: `shutil.copy` carries the
package scripts' mode, so a read-only install fails the second launch;
`configure` does not make `.tat/` itself although CLIENT_HOOKS §1 says it
does, and `.tat` is spelled twice (`SCRIPTS` beside toplevel's `LOG`);
the tests cannot see `toml_string` in use (the placeholders are filled
before parsing), nor that a later launch rewrites the files, nor the
resolver rule's separator; `_hook` should use `shlex.join`, the resolver
rule `Path.is_relative_to`. The judge's shape for the first three: one
function through which every file goes — the directory made when absent,
whatever stands at TAT's name removed (a link included), the file
created afresh through compile.py's existing `_create` (UTF-8, no mode).
For the owner: whether a write `configure` cannot make is a
`TAT_StartupError` with a sentence (EXCEPTIONS §1, MODULE_STRUCTURE §4.6;
the judge recommends yes), and to confirm that `configure` replaces what
stands at its own names rather than refusing. Nothing changed before the
owner's word.
The jobs session's step 2 committed 2026-10-05 as `7168bfc`; mcp_server.py
and test_mcp_server.py are this session's again, for the review's fixes
and step 11; its step 3 is in the ML files.

The owner on the two questions (2026-10-05): 「怎样都可以，我没有意见」 on
replacing what stands at TAT's names, 「可以算，也可以算灾难性错误，都可以」
on the failed write — both left to the author. Chosen: replace (the
judge's shape; refusing would need a sentence and would let one link a
Codex agent left block every later Claude Code launch), with one
sentence added to CLIENT_HOOKS's opening ("replacing whatever stands at
their names — a symbolic link or a file an agent left — rather than
writing through it"); a write `configure` cannot make is a
`TAT_StartupError`, `TAT cannot write <path>: <strerror>` — the siblings'
pattern, not a `TAT_DisasterError`, which is the store's — added to
EXCEPTIONS §1's list and MODULE_STRUCTURE §4.6's third layer.

**The fixes** (2026-10-05, uncommitted):

- Every file `configure` writes goes through `_replaced(directory, name,
  text)`: the directory made when absent; below it, whatever stands at a
  folder on the way and is not one, and a file or a link at the file's
  name, removed, never written through — a directory at the file's name
  refused, as compile refuses one (COMPILATION §2); the file created afresh
  through compile.py's `_create` (UTF-8, no mode carried) — imported as a
  framework-internal member across files, which MODULE_STRUCTURE §4's
  underscore rule allows (the compilation session's point: a public
  `create` would be a new plugin-facing surface, which needs the owner's
  wording). `shutil` goes. The agent directory and `.tat/` themselves are
  never replaced (a user may link either; the log is under `.tat/`).
- `.tat` spelled once: `DOT_TAT` in mcp_server.py, toplevel's `LOG` built
  from it; `configure` makes `.tat/` itself, as CLIENT_HOOKS §1 says.
- `_hook` builds the command with `shlex.join`; the resolver rule with
  `Path.is_relative_to`.
- Tests: `documented(block, placeholders, loads)` parses first and fills
  after, keys included, so the TOML's escapes are compared (`written(path,
  loads)` likewise); the shared `configured()` runs every case under an
  interpreter path holding a space and both quotes and a working
  directory holding a space and DEL (Isabelle's path syntax allows no `"`
  or `\`), on a directory without `.tat/`; the Claude Code case seeds
  `.tat/` with the log, a user's file and a stale script, and overwrites
  `.mcp.json` with `{}` before the second `configure`; a new case plants
  links at `.mcp.json`, `.claude`, `.codex` and below a real `.claude/`,
  and a file where `.codex` goes, and asserts the targets untouched and
  TAT's names real; a case with `TAT.agents` a file asserts the
  `TAT_StartupError`'s sentence and no record; the resolver's fake target
  holds `"` and `\`; `/etcetera/resolv.conf` pins the separator.

**Step 11, the Codex sandbox check** — written 2026-10-05 on the jobs
session's step 2. The author's shapes:

- `_App(experimental)`, a two-method `Server` subclass whose
  `create_initialization_options` adds the subclass's `experimental`
  capabilities to the `initialize` result; `TAT_Server.experimental = {}`,
  `Codex_Server.experimental = {SANDBOX_STATE: {}}` (`SANDBOX_STATE` =
  `codex/sandbox-state-meta`, the capability and the `_meta` key).
- `configure` records `self._working_directory`; `_check_sandbox(session,
  meta)`, a no-op on the base and so on Claude Code, runs in `_call_tool`
  right after `_check_client`; Codex's reads `meta.model_extra[
  SANDBOX_STATE]` and refuses through the jobs session's `_refuse` with
  CONSTRUCT_INTERACTION §8's sentence (the agent directory filled in),
  the reason `Codex's sandbox is not the one TAT configured`, and the
  call's `_meta` (`_dumped(meta)`, the helper the `unannounced` record now
  shares). Before `configure` or `initialize`, a `TAT_InternalError` enters
  the ending — neither can happen in `served()`.
- `sandbox_is_the_profile(policy, working_directory)`: true when some
  entry of `policy["permissionProfile"]["file_system"]["entries"]` denies
  a `path` whose real path is the working directory's; any other shape,
  `{"type": "disabled"}`, no policy: false. Real paths on both sides, so
  a canonicalised path from Codex still matches.
- Test (test_hooks, where the Codex client plumbing is):
  `the_profile(working_directory)` as recorded on a host running
  systemd-resolved (the resolver's read entry before the `deny`, `network`
  the string `enabled`, Codex's own install paths left out); a call under it
  served; then, with a `slow` call in flight, a call with no policy, a
  disabled one, a read-only one, or one denying another directory — the
  refusal answers the fifth line to it and to the call in flight, the
  conversation ends with the `ClientRefused` whose message is the
  sentence and whose `line` is the fifth, `client_refused` carries the
  call's `_meta`; the Codex server's `initialize` declares the capability,
  Claude Code's declares none. The jobs session's two-agents test now
  calls `configure` and carries the policy on Codex.
- Mutation checks, in memory: the committed write-through shape; the
  command by concatenation; the resolver's prefix test; `toml_string`
  without escapes; the sandbox check removed; the capability not
  declared; writing only when absent; the record omitted — each fails at
  least one case. Fast suite: 389 pass, the 14 known failures; the
  Isabelle-backed test_conversation: 24 pass; pyright 0 on mcp_server.py,
  toplevel.py, test_mcp_server.py, test_hooks.py.

**Verified and reviewed** (`review/LOGGING_STEP10_FIXES_STEP11_REVIEW.md`,
Workflow `wf_17bca8fc-968`: eight verifiers, two challengers on step 11
with a defender per finding, a judge; 23 minutes): **not accepted, but
close** — the production code right on every point, seven rulings done,
one partly; what blocked it was in the tests and the prose, fixed the
same day as the judge ruled:

- test_mcp_server.py did not compile under Python 3.11, the declared
  minimum (a backslash inside an f-string expression, line 865); the
  judge checked with a real 3.11.15. The expression is gone with the
  `working_directory` fixture below. Both test files now compile under
  that interpreter (checked the same way).
- The shared helper `configured()` chose the working directory's name
  itself, so its callers re-spelt `"work dir\x7f"` seven times and its
  docstring said "fresh" when three callers seeded the directory first:
  the directory is now a fixture, `working_directory`, which carries the
  sentence about the space and DEL; `configured(server_class,
  working_directory, monkeypatch)` returns the server alone.
- The replacement test planted a file at `.codex`, never a link, so its
  assertion on the user's `config.toml` could not fail, and the record said
  otherwise: the second round now links `.codex` to the user's directory
  (the file stays in the first round, the case of a file where a directory
  goes), runs both servers, and asserts the user's directory holds its one
  file and `.codex` is no link.
- A directory at one of TAT's file names is refused (`Is a directory`),
  not replaced — `Path.unlink` cannot remove one, and compile refuses a
  folder at a file's path the same way (COMPILATION §2, owner-approved);
  the judge kept the code and had the prose follow: `_replaced`'s
  docstring, CLIENT_HOOKS's sentence ("replacing a symbolic link or a file
  an agent left at their names rather than writing through it, a directory
  there refused"), this record; the startup-error test is parametrised
  over the file at `TAT.agents` and the directory at `.mcp.json`.
- The sandbox check's test could not see the rule's `deny` (a check
  without the access condition passed every test — and would serve
  `codex -s workspace-write --add-dir <working directory>`, whose entry on
  the working directory is a `write`): a fifth refused policy, "the
  working directory writable"; the policies are functions of the working
  directory. `the_profile` claimed the measured shape but had the entries
  in another order and `network` as a dict: now the recorded shape (the
  resolver's read entry first, then the `deny`, `:minimal`, the write on
  the agent directory; `network` the string `enabled`; `sandboxCwd`,
  `useLegacyLandlock`), so a check reading only the first entry fails.
  The real-path comparison is pinned by a unit test on
  `sandbox_is_the_profile` through a linked working directory.
- Dismissed by the judge: pinning that a broken installation's scripts
  stay a bug (would fake `__file__`); the `{}` line's own mutant; the
  replacement test checking TAT's text only through `.mcp.json`'s type.

The judge's five mutants — the access condition dropped, the first entry
alone, raw strings for real paths, Codex alone following a link at
`.codex`, a directory removed with `rmtree` — each fail at least one case
now. Fast suite and pyright as before; test_mcp_server and test_hooks
compile under Python 3.11.15.

**`hook.answer`'s `judged` is absent when the request was not judged**
(owner, 2026-10-05, ruled to the jobs session on its review, relayed: a
503 while the conversation is ending, a 500 on a bug of the path):
LOGGING §4's row says so; `log.hook.answer(judged: Judged | None, ...)` —
no default, so every writer states it, None absent from the record as
every other field. The jobs session's `/hook` passes None on those two
paths once it takes mcp_server.py again.

For the owner, from the judge, neither blocking: (1) CLIENT_HOOKS §5's
rule accepts a policy that carries both the profile's `deny` and a
`write` on the working directory (`--add-dir <working directory>` under
the profile); nobody has measured which entry wins inside Codex's
sandbox — the judge recommends measuring once and, if the `write` wins,
tightening the rule to "no entry on the working directory but its
`deny`"; (2) `[tool.pyright] pythonVersion = "3.11"` in pyproject.toml,
so pyright checks against the declared minimum — a configuration change.
The owner (2026-10-05): (1) 「问题不大，不用管，可以相信用户不会写这种矛盾」
— the rule stays as CLIENT_HOOKS §5 has it; (2) 「赞同」 — the setting is
in pyproject.toml.

Committed 2026-10-05 as `94e721b` (「提交」): this session's files, one
hunk of MODULE_STRUCTURE.md staged alone (`git apply --cached` of that
hunk), EXCEPTIONS.md's hunk with the jobs session's three lines named.
The other hunks left in MODULE_STRUCTURE.md and ARCHITECTURE.md are the
jobs session's (the `Isabelle_Std` plugin, the bound, the declared
imports), not the compilation session's as the author had assumed — the
compilation session has nothing uncommitted (its work is in `dfefca1`,
`ee9e4f5`, `96d1bb4`, `b3bb2d2`).
Of the logging plan, what remains: step 7's review once the jobs session's
`fork_job` is written; step 13, the one live run, with the jobs session,
when the owner says.

The jobs session's fixes after its own review (2026-10-05, in the tree,
awaiting the owner's commit), where they touch this session's work:
`_refuse`'s keyword is `meta`; `_check_sandbox` is called as before, right
after `_check_client`, before `current_call` is set, so `client_refused`
carries `_meta` in its data and no `call` field, like `client_connected`;
the matchers and the TOML's server table are written from `TOOL_PREFIX`
and `SERVER_NAME`, the files byte-identical; the sandbox test posts
through `post_hook` (the harness's `announce` renamed) and its Codex
`_meta` carries `threadId`/`sessionId`, a Codex agent being named by the
call's `threadId`; `/hook` passes `judged=None` on 503 and 500. Committed
by it as `9dc8f9b`. Its step 4 next: `/on-compaction` with `CLIENTS`,
`envelope`, `unknown_client`, `mcp.on_compaction` and the test
`test_on_compaction_answers_the_briefing_in_the_clients_shape` go, and
`TAT_new`'s hook files in tat.scala (a jar rebuild — it says when, so no
`isabelle TAT_mcp` runs meanwhile); it tells this session before opening
mcp_server.py. Done 2026-10-05 (in the tree, uncommitted): the jar
rebuilt without `TAT_new`'s hook files, `no_build` restored;
`TAT_Server.__init__(ending, port, tools, agents)`, `Body(agent,
arguments)`; the configure tests' server constructions pass `{}` as the
agents; the three compaction cases and their imports gone with the path.
Committed by it as `0319ba4`. Its step 5 next (compaction events, the
`agent.compaction` record — the first writer of that event); it tells
this session before opening mcp_server.py again.

**State for a resumption of this session** (2026-10-05, context near its
limit): everything of the logging plan that this session can do is
committed — last `94e721b`; the working tree holds only this record's
tail uncommitted. Open, neither startable here: step 7's review of the
jobs session's `fork_job` once written; step 13, the one live run with
the jobs session, when the owner says. The standing rules of the session
are at the top of this record and in CLAUDE.md; the sessions' refs after
the restart: jobs [9ffa3c] at `uds:/run/user/1002/cc-socks/5611.sock`,
compilation [ebfd21] at `uds:/run/user/1002/cc-socks/7431.sock`, this
one [b341d7].

**`ending` is always `error`** (owner, 2026-10-04: 「连接断开的日志级别要从
info 改成 error」, said to the compilation session, which relayed it; put
to the owner here with the exact edit and confirmed, 「批准」): the
connection between the Python process and the Isabelle process going is
a critical crash. LOGGING §4's row is level `error`, its "`info` when the
connection went" clause gone; `log.conversation.ending(ended_by)` has no
`level` parameter; `Ending.end` no choice; `connection_went` stays for
`stopped()`'s line (so the step-2 note above, that the record's level
and the line come from the one test, now holds of the line alone).
Known and accepted: every conversation that ends by Isabelle stopping —
the normal way — ends its log with an `error` record, and, by LOGGING
§5's mirroring, puts one ERROR line into the RPC host's log
(`ConnectionResetError: peer closed connection`, or
`asyncio.exceptions.CancelledError` when the host's cancellation enters
the ending). Tests: test_log's `ending` case reads the level from §4's
table; test_toplevel's host-cancellation case expects `error`.

**The ending's answer** (owner, 2026-10-04: approved to the compilation
session, 「好的批准」, relayed, then confirmed here on the exact text,
「文本如上，照此改」). One form for every reason:

    TAT has stopped: <reason>; this is a critical error, and this call
    did not complete. Stop now and call TAT no more. If another agent
    started you, tell it to stop as well; otherwise tell the user that
    TAT has stopped.

(one line in the document), and seven reasons — the six of RENDER_BASELINES
§4 in their order and a seventh, `it cannot use its working directory`,
for the `TAT_StartupError` of a `Session`'s folder that cannot be made
when a theory begins. Landed in one change, since test_mcp_server unpacks
the block's lines at import: RENDER_BASELINES §4's fenced block and its
paragraph ("the fourth to sixth for a `ClientRefused`", the seventh's
rule); `mcp_server.stopped_for(reason)`, the one place the form is
written, with `stopped(ended_by)` choosing among the three reasons it
has branches for; test_mcp_server's unpack of seven lines and an
assertion that every line of the block is `stopped_for` of its reason.
The seventh line has no branch until the compilation session's step B5,
as the fourth to sixth have none until the jobs session's
`ClientRefused`; both add reasons through `stopped_for`, never a second
copy of the sentence. `stopped` is thus edited by three sessions, each
telling the others first. The jobs session took it into its step 2: its
refusing method builds a `ClientRefused`'s `line` as
`stopped_for(<reason>)`, its branch returns `ended_by.line`, and it
calls `log.conversation.ending(ended_by)` with no level.

