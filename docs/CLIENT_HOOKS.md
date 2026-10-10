# The agent client's hooks

Status: decided (2026-09-30, with CONSTRUCT_INTERACTION.md §7 and §8).
The client facts these files rest on are measured in
ai-artifacts/AGENT_CLIENTS_MEASURED.md, each on the version named
there, not every one on the versions TAT requires. TAT requires of the
client that connects at least Claude Code 2.1.286 or Codex 0.156.1,
read from its MCP `initialize` (CONSTRUCT_INTERACTION §8).

One `isabelle TAT_mcp` serves one agent client process, Claude Code or
Codex, chosen at launch by `-c` (MODULE_STRUCTURE §5). Before serving, the
server subclass for that client writes the client's files whole into the
agent directory, `<working directory>/TAT.agents/` (ARCHITECTURE §1),
which it makes when absent, and the scripts the hooks run into
`<working directory>/.tat/` — `configure`, MODULE_STRUCTURE §4.6 — and
overwrites them at every launch, replacing a symbolic link or a file an
agent left at their names rather than writing through it, a directory
there refused (MODULE_STRUCTURE §4.6), and touching nothing else in
`.tat/`: the
MCP server entry, the hooks below,
and the client's settings, which also keep the agents inside the agent
directory (§5). `isabelle TAT_new` writes none of them. The client is
started in the agent directory, where its project-level files are read.
The two scripts are Python, standard library only, run under the
interpreter TAT's Python side runs under, as `'<python>' -I
'<working directory>/.tat/<script>'`; each finds what it needs from its
own location, and every path in a hook's command is quoted, so a working
directory with a space in its path works.
TAT never reads a hook payload's `cwd` as the working directory.

## 1. The conversation's hooks

Every hook of the conversation runs the same script, `.tat/hook.py`,
which posts the hook's standard input —
the client's JSON payload — to `POST /hook` on TAT's server
(MODULE_STRUCTURE §4.6) and prints TAT's answer on its standard output.
The hooks that keep the agents in the agent directory run another
script, which answers by itself (§5).
TAT reads the payload's `hook_event_name` and, per client, the fields
`event_of_hook` needs, and answers with the hook output JSON the client
documents:

| hook | TAT's answer |
| --- | --- |
| `PreToolUse` on a TAT tool, `mcp__TAT__…` — the announcement | records the call for `agent_of_call` (CONSTRUCT_INTERACTION §8); Claude Code: `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}}`, which grants the call; Codex: an empty answer |
| `PreToolUse` on `TaskStop` (Claude Code) or `collaborationinterrupt_agent` (Codex) — an interruption | `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "<the two lines of CONSTRUCT_INTERACTION §7>"}}` when the interruption is refused, else an empty answer — `TaskStop` needs no grant, and Codex treats a bare `allow` as an unsupported decision and marks the hook failed |
| `Stop`, `SubagentStop` — the agent is about to stop | `{"decision": "block", "reason": "<the reason of CONSTRUCT_INTERACTION §7>"}` when the stop is blocked, else an empty answer |
| `SessionStart` (Codex) — the main conversation's context was replaced (`startup`, `resume`, `clear`, `fork`, `compact`) | an empty answer; the main conversation's seen set cleared (PRINT.md §4) |
| `PreCompact`, `PostCompact` (Codex) — a thread is about to compact; it has compacted | an empty answer; at each of the two, the seen set of the agent `agent_id` names — the main conversation when there is none — cleared |
| `PostCompact` (Claude Code) — some agent has compacted | an empty answer; its `transcript_path` names the session, and for a session TAT reads the hook is matched with a compaction boundary in that session's transcripts (§2's second check); nothing else read from it |

An empty answer is an empty standard output, which both clients read as
no decision. Every decision travels in the JSON; the script never exits
2 — its every failure of its own is exit 1: TAT gone or ending (status
503), a bug on the path (status 500, MODULE_STRUCTURE §4.6), no
connection, the script failing for a reason of its own. Neither client
reads exit 1 as a block, so a TAT that is gone holds nobody, while exit
2 would block every stop and refuse every interruption. Under `-p`
Claude Code grants a TAT tool call only on the announcement's answer, so
with TAT gone an agent's TAT calls are refused there and nothing else
changes.

The script is `hook.py` of the Python package (MODULE_STRUCTURE §4),
copied into `.tat/` by `configure`. It finds the running conversation
through `tat.lock` beside its own directory — the conversation's pid on
the first line when it takes the lock, its port on the second once the
server listens, both cleared on release (MODULE_STRUCTURE §4.6) — so no
file carries a port and nothing depends on the hook's current directory.
It reads the two lines, checks the pid is alive, posts its standard input
to `http://127.0.0.1:<port>/hook` with `http.client`, connecting to the
address directly whatever proxy the environment names, prints the body
of a 200 answer, and exits 1 on everything else. It fails the same way
for an absent lock file, an emptied one, the moment before the port is
written, a pid that is no longer alive, and a port nothing accepts on (a
conversation still starting or already ending, or a recycled pid), and
for every other failure — an answer that is not 200, an exception of its
own — with this line on its standard error and exit 1:

```
TAT is not running in this directory.
```

The two scripts exist only while `.tat/` does, which `configure` makes
and no agent can reach (§5).

## 2. Claude Code

`.mcp.json` carries the server entry, `TAT`, with TAT's URL and the
twelve-hour tool limit; `.claude/settings.json` the environment, the
hooks, and the permissions and sandbox settings of §5.
`CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS=0` keeps a long
`check_construct` from being moved to the background;
`CLAUDE_CODE_STOP_HOOK_BLOCK_CAP=0` switches off Claude Code's ceiling on
consecutive blocks (CONSTRUCT_INTERACTION §8). The `PreToolUse` announcement
matches `mcp__TAT__.*` and identifies the caller by its `agent_id`, empty
for the main conversation, paired with the call through `tool_use_id`;
`TaskStop`'s `task_id` is whatever the parent passed — the subagent's
`agent_id`, its launch name in any capitalisation, or an id in the old
`shell_id` field — and TAT does not read it: the refusal judges every
agent but the caller and the main conversation (CONSTRUCT_INTERACTION
§7).

No compaction hook of Claude Code's — `PreCompact`, `SessionStart` with
`compact`, `PostCompact` — names the agent that compacted (measured, AGENT_CLIENTS_MEASURED.md). TAT registers `PostCompact` alone, answered with nothing and read for nothing but its `transcript_path`, the session it belongs to (the second check below), and detects an agent's compaction at that agent's next announcement, from the agent's
own transcript. The transcript is the payload's `transcript_path` for
the main conversation; for a subagent it is the file
`agent-<agent_id>.jsonl` under
`<transcript_path minus .jsonl>/subagents/`, at any depth — a workflow
agent's lies under `subagents/workflows/<run>/`. At each announcement
TAT reads the lines the file has gained since it last read it, and a
`compact_boundary` line it has not recorded is that agent's compaction
event; the line is on disk before the agent's next `PreToolUse`
(measured, AGENT_CLIENTS_MEASURED.md).

An announcement whose `transcript_path` differs from the one at the
same agent's previous announcement is that agent's compaction event
too. `/clear` and `/resume` give the conversation a new transcript; a
background subagent that keeps running across a `/clear` keeps its
context, has its later lines written under the new path, and is cleared
with the rest. From then on TAT reads the agent's file under the new
path, from its first line.

A transcript whose part TAT had read is no longer there — another file
at the path, or the file no longer ending where TAT's reading stopped:
Claude Code cuts the main transcript in place when a message is
removed, and can rewrite it under its name — is that agent's compaction
event too. TAT reads the file again from its first line, and a boundary
it has recorded counts no second time.

An agent whose transcript TAT does not find at an announcement cannot
be served, and the conversation ends (CONSTRUCT_INTERACTION §8).

Two checks guard the premise, and a failed check ends the conversation
with a `TAT_InternalError` carrying its message (CONSTRUCT_INTERACTION
§8): a boundary whose own timestamp precedes the agent's previous served
announcement; and a `PostCompact` for a session TAT reads that no
boundary of that session's matches. Each such hook is matched with one
boundary in the session's transcripts — the main conversation's file
and every `.jsonl` under its directory — timestamped within 10 seconds
before the hook, or appearing within 10 seconds after it, TAT reading
those transcripts while a hook waits; a `PostCompact` for a session TAT
does not read yet starts no check. Neither check clears a seen set.
Claude Code writes no transcript when it is started with
`--no-session-persistence`, or through the SDK with
`persistSession: false`. It also writes none when its environment
carries `CLAUDE_CODE_SKIP_PROMPT_HISTORY=1`, or when an interactive
Claude Code is started from inside another one; the last two `env`
entries below turn the transcript back on in those two cases.

```json
{ "mcpServers": { "TAT": { "type": "http", "url": "http://127.0.0.1:<port>/mcp", "timeout": 43200000 } } }
```

```json
{ "env": { "CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS": "0", "CLAUDE_CODE_STOP_HOOK_BLOCK_CAP": "0",
           "CLAUDE_CODE_SKIP_PROMPT_HISTORY": "0", "CLAUDE_CODE_FORCE_SESSION_PERSISTENCE": "1" },
  "permissions": { "allow": ["Bash"], "deny": ["EnterWorktree"], "blockReadsOutsideWorkingDirectories": true },
  "sandbox": { "enabled": true, "failIfUnavailable": true, "allowUnsandboxedCommands": false,
               "network": { "allowAllUnixSockets": true, "allowedDomains": ["*"] },
               "filesystem": { "denyRead": ["<working directory>", "/run"] } },
  "hooks": {
    "PreToolUse":   [ { "matcher": "mcp__TAT__.*", "hooks": [ { "type": "command", "timeout": 10, "command": "'<python>' -I '<working directory>/.tat/hook.py'" } ] },
                      { "matcher": "TaskStop",     "hooks": [ { "type": "command", "timeout": 10, "command": "'<python>' -I '<working directory>/.tat/hook.py'" } ] },
                      { "matcher": "Write|Edit|NotebookEdit|MultiEdit", "hooks": [ { "type": "command", "timeout": 10, "command": "'<python>' -I '<working directory>/.tat/guard.py'" } ] },
                      { "matcher": "Agent|Task",   "hooks": [ { "type": "command", "timeout": 10, "command": "'<python>' -I '<working directory>/.tat/guard.py'" } ] } ],
    "Stop":         [ { "hooks": [ { "type": "command", "timeout": 10, "command": "'<python>' -I '<working directory>/.tat/hook.py'" } ] } ],
    "SubagentStop": [ { "hooks": [ { "type": "command", "timeout": 10, "command": "'<python>' -I '<working directory>/.tat/hook.py'" } ] } ],
    "PostCompact":  [ { "hooks": [ { "type": "command", "timeout": 10, "command": "'<python>' -I '<working directory>/.tat/hook.py'" } ] } ],
    "WorktreeCreate": [ { "hooks": [ { "type": "command", "timeout": 10, "command": "'<python>' -I '<working directory>/.tat/guard.py'" } ] } ] } }
```

`<python>` is the interpreter TAT's Python side runs under.

The project settings load only when Claude Code starts in the agent
directory; the stall watchdog is left as it is.

## 3. Codex

`.codex/config.toml` carries the server entry, `TAT`, with the URL,
`tool_timeout_sec` 43200 and `default_tools_approval_mode = "approve"`;
`check_for_update_on_startup = false`; `features.multi_agent_v2 =
true`, under which alone the interruption tool is named
`collaborationinterrupt_agent`; and the permission profile of §5.
`.codex/hooks.json` carries the hooks.
The announcement identifies the caller by the call's `_meta.threadId`
(the same value as `_meta["x-codex-turn-metadata"].thread_id`), paired
with the call through `tool_use_id` = `_meta.callId`; a hook payload
names its agent by `agent_id`, the subagent's thread id, and a payload
without one is the main conversation's, whose thread id is the payload's
`session_id`; `interrupt_agent`
names its target by a path, which TAT does not read, as it reads no
`task_id` on Claude Code: the refusal judges every agent other than the
caller and the main conversation — held by the stop rule, or with a
TAT call still working (CONSTRUCT_INTERACTION §7). `SessionStart` fires for
`startup`, `resume`, `clear`, `compact` and `fork`. Codex runs project
hooks only when the project is trusted and only under
`--dangerously-bypass-hook-trust`, which has no configuration equivalent:
both come from the client class, as the arguments the client is given at
its launch before the user's own (MODULE_STRUCTURE §4.6) — the third
block below, one argument per line, as the client receives them — and
no sandbox option is (§5). The trust is given under `<agent directory>`,
the canonical path of `<working directory>/TAT.agents`, symbolic links
resolved, which is also the directory the client is started in;
`<working directory>` is the absolute path as given.

```toml
check_for_update_on_startup = false
default_permissions = "tat-agent"

[features]
multi_agent_v2 = true

[permissions.tat-agent.filesystem]
":minimal" = "read"
"<working directory>" = "deny"
"<the real path of /etc/resolv.conf, when outside :minimal>" = "read"

[permissions.tat-agent.filesystem.":workspace_roots"]
"." = "write"

[permissions.tat-agent.network]
enabled = true

[mcp_servers.TAT]
url = "http://127.0.0.1:<port>/mcp"
tool_timeout_sec = 43200
default_tools_approval_mode = "approve"
```

```json
{ "hooks": {
    "PreToolUse":   [ { "matcher": "mcp__TAT__.*", "hooks": [ { "type": "command", "timeout": 10, "command": "'<python>' -I '<working directory>/.tat/hook.py'" } ] },
                      { "matcher": "collaborationinterrupt_agent", "hooks": [ { "type": "command", "timeout": 10, "command": "'<python>' -I '<working directory>/.tat/hook.py'" } ] } ],
    "Stop":         [ { "hooks": [ { "type": "command", "timeout": 10, "command": "'<python>' -I '<working directory>/.tat/hook.py'" } ] } ],
    "SubagentStop": [ { "hooks": [ { "type": "command", "timeout": 10, "command": "'<python>' -I '<working directory>/.tat/hook.py'" } ] } ],
    "SessionStart": [ { "hooks": [ { "type": "command", "timeout": 10, "command": "'<python>' -I '<working directory>/.tat/hook.py'" } ] } ],
    "PreCompact":   [ { "hooks": [ { "type": "command", "timeout": 10, "command": "'<python>' -I '<working directory>/.tat/hook.py'" } ] } ],
    "PostCompact":  [ { "hooks": [ { "type": "command", "timeout": 10, "command": "'<python>' -I '<working directory>/.tat/hook.py'" } ] } ] } }
```

```
--dangerously-bypass-hook-trust
-c
projects={"<agent directory>"={trust_level="trusted"}}
```

`PreCompact` and `PostCompact` fire for every thread that compacts, the
main conversation and each subagent, with `agent_id` naming a subagent
(measured, AGENT_CLIENTS_MEASURED.md); `SessionStart` fires for the main
conversation only. A thread that is no spawned subagent — a `/review`
thread — carries no `agent_id`: its compaction is taken for the main
conversation's, and its own set, should it call TAT, is never cleared.
TAT clears the thread's seen set at both compaction hooks. On Codex the model calls TAT's tools from a script it has Codex
run, and such a call can end while the thread's summary is being
written, between the two hooks, its result delivered into the new
context: cleared at `PreCompact`, the set is empty for that rendering;
cleared again at `PostCompact`, it forgets what that rendering
recorded. A compaction that fails runs `PreCompact` alone, and the
thread's set is then cleared for nothing. Nothing a compaction hook
answers reaches the model, and TAT answers all three hooks with nothing;
the agent reads the briefing itself, `recall` with no id (PRINT.md §5).

On Codex a blocked stop's reason reaches the model XML-escaped and cut at
about 10 KB; the reason carries no message, so nothing of substance is
lost (CONSTRUCT_INTERACTION §7, AGENT_CLIENTS_MEASURED.md).

## 4. What is not handled

`SessionEnd` fires on Claude Code's `/clear` and `/resume` and on Codex's
idle unload while agents still work, and the process's end is the
ending's, so TAT registers no `SessionEnd` hook. The client behaviours
that bypass every hook — Escape, Claude Code's stall watchdog and
`maxTurns`, a session ended with a subagent running, SIGINT — are
accepted as they are (CONSTRUCT_INTERACTION §1). So is a result held
back on Codex: the script through which the model calls TAT's tools can
keep a result and print it to the model only after the thread has
compacted, or never. TAT rendered it before any hook told of that
compaction, so what it left out as already shown may be gone from the
context it arrives in. A rewind of the
conversation — Claude Code's rewind menu restoring the conversation to
an earlier prompt, or Esc Esc to edit an earlier prompt and send it
again — removes context, fires no hook and writes no compaction
boundary; TAT assumes it does not happen (CONSTRUCT_INTERACTION §1).
The exact project-level file names above, and an interactive session
reading the two transcript `env` entries from the project settings, are
confirmed at implementation.

## 5. The agents stay in the agent directory

With its own tools — its shell and the client's file tools — an agent,
the main conversation or a subagent, reads and writes no file of the
user's but those of the agent directory, short of the gaps listed at the
end of this section: not the working directory, of which the agent
directory is a subdirectory, nor the rest of the user's files. Each
client's own sandbox enforces it, configured by the files `configure`
writes (§2, §3); TAT starts no client and wraps none. Whatever keeps the
agents in holds whether or not TAT runs: the sandbox settings, deny
entries, and on Claude Code a guard script, `.tat/guard.py`, which opens
no connection. The conversation's hooks (§1) are the only ones TAT
answers.

Beyond that the agents are left what the client gives them. Every tool
the client has is theirs, the tools of whatever other MCP servers it has
included, git worktrees alone excepted. Their shell has the network:
every outside host, and the machine's own addresses, TAT's port among
them — the agents are trusted not to forge requests to it. On both
clients the hooks' commands and the client's own requests to TAT's
server run outside the sandbox, so the hook script reads `tat.lock`
although no agent can. A program installed among the user's files —
under `/home` — is not found by an agent's shell. All of it but an
escalation on Codex is measured (AGENT_CLIENTS_MEASURED.md), in the
clients' non-interactive modes.

**Claude Code.** Shell commands run in Claude Code's sandbox
(`sandbox.enabled`), without which Claude Code refuses to start
(`failIfUnavailable`) and which an agent cannot ask to leave
(`allowUnsandboxedCommands: false`); they need no approval
(`permissions.allow: ["Bash"]`, which Claude Code honours only once the
user has trusted the folder it keys trust on — the nearest directory at
or above the agent directory that holds a `.git`, else the agent
directory itself, and once Codex has run in the agent directory, which
leaves an empty `.git/` there, the agent directory itself; a trusted
parent does not count under `-p`; without it a command Claude Code
cannot analyse, one with a subshell for instance, is refused outside
`bypassPermissions` mode).
`permissions.blockReadsOutsideWorkingDirectories` makes the file
tools refuse every path outside the agent directory and denies sandboxed
commands the roots that hold user files — `/home`, `/root`, `/mnt`,
`/media`, `/srv` and their like; `sandbox.filesystem.denyRead` adds the
working directory, which may lie under none of those, and `/run`.
`sandbox.network.allowAllUnixSockets` lets a sandboxed command connect
to any Unix socket; it is written on every host, because on one whose
AppArmor restricts unprivileged user namespaces the sandbox runs no
command without it, and `/run` is denied so that the sockets there — the
user's D-Bus among them — are not reached through it.
`allowedDomains: ["*"]` lets a command reach any host without a prompt.
`/tmp` stays readable: the sandbox's network proxy keeps its socket
there, and hiding `/tmp` cuts the network.

Those settings stop reads, not the file tools' writes, and they stop no
worktree. The guard script judges both. Claude Code runs it before each
call of a file-writing tool and of the tool that launches a subagent, and
at each creation of a worktree; it finds the agent directory beside its
own, reads the hook's JSON, answers from that alone, and never exits 2.
A failure of its own answers as the hook it serves needs: a write is
refused with the first sentence below, a worktree creation fails as
below, a subagent launch gets no decision and exit 1, which no client
reads as a block; a payload it cannot parse at all, whose hook it cannot
tell, gets the write's refusal.

A write by a file tool is judged by one fixed rule: the path in the
tool's arguments (`file_path`, `notebook_path`) must be absolute, as
Claude Code hands it over, and is made canonical by `os.path.realpath`
— `..` removed, symbolic links resolved, dangling ones too, a file that
does not exist yet through its nearest existing ancestor; when the
canonical path lies inside the canonical agent directory and is neither
`.mcp.json` nor under `.claude/` there, the answer is `allow`, and
otherwise `deny` with one of two reasons:

```
TAT allows writing only inside <agent directory>.
TAT does not allow changing the agent client's own files.
```

The rule reads nothing else — not the permission mode, not the agent.
The `allow` is what lets a write inside the agent directory through in
the `default`, `acceptEdits`, `auto` and `bypassPermissions` modes, and
the `deny` holds in each of them and against any allow rule. The
client's own files are refused because Claude Code reloads its settings
while a session runs: an agent that could write them could switch the
sandbox off.

Git worktrees are refused because Claude Code makes one itself, outside
the sandbox, in the git repository around the agent directory.
`permissions.deny: ["EnterWorktree"]` takes that tool away, and the hook
`WorktreeCreate` is what refuses every other creation — a subagent
launched with `isolation: "worktree"`, an isolation set in a subagent's
definition, or, by Claude Code's documentation, `claude --worktree`: the
guard prints the sentence on its standard error and exits 1, the one case
in which it exits non-zero, and Claude Code fails a creation whose hook
gives it no path, the guard unable to start included. The guard also
answers the `PreToolUse` on the tool that launches a subagent, `Agent`:
`deny` with the sentence when the call asks for `isolation: "worktree"`,
no decision otherwise — which changes only what the agent reads, the
sentence alone instead of after `WorktreeCreate hook failed:` and the
hook's command line. The sentence:

```
TAT does not allow git worktrees. Start the subagent without worktree isolation.
```

**Codex.** The permission profile `tat-agent`, which
`default_permissions` selects: read of the system directories
(`:minimal` — on Linux `/bin`, `/sbin`, `/usr`, `/etc`, `/lib`, `/lib64`,
`/nix/store`, `/run/current-system/sw`), write of the agent directory
(`:workspace_roots`), the
network on, and nothing else — Codex's sandbox starts from an empty
filesystem, so nothing of the working directory, the user's files or
the host's `/tmp` is visible inside. The working directory is also
denied by name, which keeps an escalated or retried command inside the
sandbox. With the network on, the shell shares the host's network. To
resolve an outside name it must read the resolver's file, so `configure`
adds one read entry: the real path of `/etc/resolv.conf`, when that
lies outside the `:minimal` directories — on a host that runs
systemd-resolved, `/run/systemd/resolve/stub-resolv.conf`. The entry
names the real path and never the symbolic link, on which the sandbox
fails every command. `apply_patch` obeys the same profile, and Codex has
no other file tool and no worktree tool, so it needs no guard script.
A sandbox option at launch — `-s`,
`--dangerously-bypass-approvals-and-sandbox`, neither among the launch
arguments of §3 — makes Codex ignore the
profile, so TAT checks it: TAT's server declares
`capabilities.experimental["codex/sandbox-state-meta"]` in its
`initialize` result, Codex then sends the policy in force as
`_meta["codex/sandbox-state-meta"]` with every tool call, and a call
whose policy is not the profile's — the profile's is recognised by its
`deny` entry on the working directory, and a call without the key is not
the profile's — refuses the session
(CONSTRUCT_INTERACTION §8).

Accepted as they are:

- TAT cannot tell whether Claude Code's sandbox is on, and a user can
  switch it off at launch.
- On Claude Code `/tmp` is readable, and Claude Code's own temp
  directory, `/tmp/claude-<uid>`, which all the user's sessions share,
  is writable too. Its sandbox subtracts from the whole filesystem, so a
  path under none of the roots above stays readable.
- An MCP server the client has runs outside the sandbox and shows the
  agents whatever it reaches; one that reads files by their paths shows
  them the working directory. A user who wants the working directory
  hidden gives the client no such server.
- A service of the machine that an agent's shell can reach is the
  agent's to use: over the network, TAT's own port included, and on
  Claude Code through a Unix socket outside `/run` — a tmux server's or
  the X display's under `/tmp` — through which a command acts outside
  the sandbox; the socket route is inferred from the measured one
  through `/run`, not measured itself.
- Claude Code itself re-opens to the agents the user's git configuration
  (`~/.gitconfig`, `~/.config/git/`) and parts of `~/.claude` — skills,
  plugins, rules, agents, commands, shell snapshots.
- Claude Code loads the `CLAUDE.md` of the directories above the agent
  directory by itself, outside any sandbox; those files are the user's.
- By Claude Code's documentation, a skill an agent writes into a
  subdirectory of the agent directory can carry hooks, which run outside
  the sandbox; not measured.
- Between the guard's check of a path and Claude Code's own write, an
  agent that swaps a directory of the path for a symbolic link can make
  the write land outside the agent directory.
- A guard script that cannot start — its interpreter gone — lets every
  write through; a worktree is still refused.
- The scripts exist only while `.tat/` does. A user who removes it while
  a client runs makes the interpreter exit 2 at every hook, which both
  clients read as a block: of every write, every subagent launch, every
  TAT call and every stop.

Both sandboxes leave empty directories behind: Codex a `.git/` and an
`.agents/` in the agent directory, Claude Code a `.git/config.worktree`
file and a `.claude/.cc-writes/` in a git repository that encloses it.
