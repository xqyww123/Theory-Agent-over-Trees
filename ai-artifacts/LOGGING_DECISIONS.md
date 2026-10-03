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
[682d5e] also adds `ClientRefused(TAT_StartupError)` with its `line`,
`stopped()`'s branch answering it and RENDER_BASELINES §4's fourth and
sixth lines (its two refusals: `clientInfo`, Claude Code's missing
transcript); step 11 adds the sandbox check, the fifth line and the
`client_refused` record on that class. Announced by [682d5e] for its
steps: `TAT_Server` loses `on_compaction` (`/on-compaction` and
`mcp.on_compaction` go with `POST /hook`; the server is built in
`served()` from the client's subclass; `configure(working_directory)` a
base method called before the port is bound, empty until step 10);
`Tool.run` takes the calling `Agent`; `Ending.end` cancels the
construction jobs and drops the evaluation jobs in its synchronous
stretch — told to keep `_entered.set()` unconditional and `forest` None
before the start built it. The SDK runs each message in a task of its
own (`Server.run`, mcp 1.26.0: `tg.start_soon(self._handle_message, …)`),
confirmed by [682d5e], so the context variables set in the handler reach
no other request.
