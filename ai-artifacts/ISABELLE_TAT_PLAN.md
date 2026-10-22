# `isabelle TAT`: the implementation plan

Status: revision 8, 2026-10-09. Revisions 1 to 7 (ai-artifacts/review/ISABELLE_TAT_PLAN_rev1.md
to _rev7.md) were reviewed in ISABELLE_TAT_PLAN_REVIEW.md to _REVIEW_7.md;
an audit (2026-10-09) listed what revision 2 had lost of the owner's
decisions, and revision 3 restored it. Review 4's C7 (`LD_LIBRARY_PATH`)
was overruled by the owner (§1.14); review 5's C4 asked to revisit that
ruling, which stands. Revision 8 applies review 7's eleven author fixes and
the terminal condition the owner delegated to the author on 2026-10-09
(§1.3). Three author edits sit inside owner items, and the owner may veto
any of them: §1.4's handler sentence (from review 2's C3, narrowed to two
handlers under review 5's C8) and its "stay in the log" (review 7's C9);
§1.3's rule of what the SIGKILL reaches (review 7's C1). Every decision of
§1 and every approved text of §5 is carried in full. Steps 1 to 3 are
implemented (3b864ca, b0e1045, 0a06b4a, ecba5d3, 9277c01, bd10c00) and step
4's probes recorded (`ai-artifacts/probes/isabelle_tat_step4/`); later
decisions are dated where they stand.

## 1. The decisions

Each item names who decided it and when. "Author" marks a choice the author
made within a decision the owner delegated; the owner may veto it.

1. **The command** (owner, 2026-10-05 and 10-08).
   `isabelle TAT [OPTIONS] WORKING_DIRECTORY [CLIENT_ARGS ...]` is a fourth
   Isabelle tool in `src/scala/tat.scala`. It creates the working directory
   as `TAT_new` does (idempotent: an existing one only gains `-P` plugins),
   starts a conversation on it as `TAT_mcp` does, in the same JVM, and once
   the conversation is served starts the agent client (Claude Code or
   Codex) as its own child process, with the terminal inherited, in the
   agent directory `WORKING_DIRECTORY/TAT.agents/`. The client's exit ends
   the conversation, and the tool exits with the client's code.
   `TAT_new`, `TAT_mcp` and `TAT_compile` stay for use on their own.
2. **Which came first** (owner, 2026-10-08 and 10-09). The JVM keeps one
   record; the first of two events to reach it is written and never
   overwritten: the conversation's end (`TAT.finished`, or a failure the
   launcher itself turns into an end) or the client's exit. If the client's
   exit came first, the tool prints nothing more and exits with the
   client's code. If the conversation's end came first, the tool ends the
   client (§1.3), prints the messages of the conversation's end and exits
   2. A client that exits on its own in the short interval between the
   Python side's beginning to end and `TAT.finished` reaching the JVM
   counts as the client's exit; the log's `ending` record still names the
   cause. Which of the two came first is read from that record alone,
   never from whether the client still runs; only the ending of §1.3 asks
   whether it still runs, to leave a client already gone as it is (the
   author's narrowing of "nothing anywhere asks whether the client is
   still alive", 2026-10-11, re-review R3; the owner may veto).
3. **Ending the client** (owner, 2026-10-09; the terminal's condition
   delegated to the author on 2026-10-09, after review 5's C5 and review
   7's C2; the bound raised to at least 10 s and the SIGKILL made
   unconditional by the owner on 2026-10-11, code review C2). SIGTERM, a
   wait bounded by 10 s, then SIGKILL to the
   client and to every process that descended from it, then the wait for
   it; a client already gone is left as it is. (What §3.2 delivers:
   SIGKILL reaches exactly the processes that are
   the client's descendants at one of two moments, just before the SIGTERM
   and, when the client still runs at the bound, at the bound; a process
   that is a descendant at neither moment is not reached, §3.2 lists the
   examples.)
   When the tool's stdin is a terminal, its stdout is that same terminal,
   and the tool's process group is that terminal's foreground process
   group, the terminal's mode (the line settings, as `stty -g` prints
   them) is saved just before the client starts, and it is restored once
   the client has been reaped, whichever event came first, if the tool's
   process group is still the foreground process group at that moment;
   otherwise the shell has already taken the terminal back and restores
   its own mode. A process sharing the job through a pipe, such as a
   pager, sets the terminal's mode itself, which is why both streams must
   be the terminal; a job member reached through stderr alone is the
   limit that remains. Under the same condition, right after the restore
   and before the end's messages, the launcher writes one fixed sequence
   that switches off, on the screen shown, the escape-sequence modes the
   clients set: `\e[<99u` (the kitty keyboard stack emptied), `\e[>4m`
   (modifyOtherKeys at its initial value), `\e[?1000l` `\e[?1002l`
   `\e[?1003l` `\e[?1006l` (mouse), `\e[?2004l` (bracketed paste),
   `\e[?1004l` (focus events), `\e[?2031l` (colour-scheme notifications),
   `\e[?25h` (the cursor shown). (Owner, 2026-10-13, delegated to the
   author after step 4's probes found Codex leaving the keyboard protocol,
   bracketed paste and focus events on whenever the launcher ends it, so
   that in kitty Ctrl-C no longer interrupts afterwards. The author chose
   this smaller version over an Opus team's judge, who proposed also
   visiting the alternate screen and back inside synchronized output to
   empty both screens' keyboard stacks and leave a stale alternate
   screen: measured safe in kitty 0.32.2's parser and tmux 3.4 but
   resting on cited source elsewhere, it overwrites the main screen's
   saved cursor, and it serves only a client killed from outside on the
   alternate screen. A bare `\e[?1049l` is excluded: in tmux 3.4 it moves
   the cursor back after a clean alternate-screen session. Each element
   kept was measured to change nothing where its mode is off, in kitty's
   parser and in tmux (kitty 0.32.2 does not know mode 2031 and ignores
   it). Records: `ai-artifacts/probes/isabelle_tat_step4/` and
   `ai-artifacts/probes/isabelle_tat_escape_sequence_modes/` (scripts,
   their outputs, RECORD.md).)
4. **Nothing reaches the terminal while the client runs** (owner,
   2026-10-05, restated 10-09; the handler sentence is the author's, from
   review 2's C3, narrowed to two handlers under review 5's C8; "they stay
   in the log" is the author's, review 7's C9). Under `isabelle TAT` the
   log's `warning` records are never echoed; they stay in the log (which
   LOGGING §5 also copies to the RPC host's logger). The protocol handlers
   whose failure could end
   the conversation or leave `launch` waiting, `TAT.finished` and
   `TAT.serving`, catch their own failure and turn it into an end of the
   conversation, so what an escaping failure would print (Isabelle's
   "Failed invocation of protocol function" message) never reaches the
   terminal. Errors print only when no client exists: a refusal before the
   client starts, or the messages of the conversation's end after the
   client has been ended. On a normal end nothing is printed after the URL
   line. `TAT_mcp` and `TAT_compile` on their own keep echoing warnings as
   they are written.
5. **The tool's own output goes to stderr; stdout belongs to the client**
   (author, under review 1's C12). Before the client starts the stream
   shows, in order: `Starting TAT... It may take a while`, then the
   conversation's own lines (a refusal, the base heap's build, the `Log:`
   line, the URL line). Usage errors and refusals go to stderr too, each
   with Isabelle's `*** ` prefix (§2.2).
6. **The client's launch arguments** (owner, 2026-10-08 and 10-09; the
   place is the author's choice, (A)). Every argument a client needs
   beyond its executable is supplied by its client class on the Python
   side, which already owns the client's files and the TOML encoder: for
   Codex `--dangerously-bypass-hook-trust` and the agent directory's
   project trust; for Claude Code `--strict-mcp-config` and
   `--mcp-config <agent directory>/.mcp.json`, so that only that file's
   servers are loaded and none of the user's — the strict flag alone
   ignores the project's file too, measured (owner, 2026-10-13, after
   the jobs session's live run found the user's servers loaded; the jobs
   session made the change and the launcher's cases passed on it;
   CLIENT_HOOKS §2/§5 record it). The launcher always gives them,
   followed by CLIENT_ARGS untouched; it reads no part of the client's
   command line. A user who repeats Codex's flag gets Codex's own refusal
   ("cannot be used multiple times"), the client exits at once, and the
   tool exits with that code (owner, 2026-10-09: no tolerance of a
   repeated flag, which would need a comparison that review 3's C1 showed
   to be unsafe). The launch arguments travel in the `TAT.serving`
   message (A).
7. **The port** (owner, 2026-10-05). `TAT_mcp`'s default port is one the
   system assigns (port 0); `-p PORT` fixes one. The socket is bound in
   `served` and handed to the server's constructor (owner, 2026-10-08), so a
   URL that does not match the bound socket cannot exist. `TAT_mcp` prints
   the URL once the conversation is served.
8. **The refusals** (owner, 2026-10-06 and 10-08). An unknown client:
   `TAT doesn't know the agent client <name>`, one sentence in `TAT_mcp`
   and `isabelle TAT`. A client whose executable is not on `PATH`:
   `TAT cannot find <command> on the path`, before anything is created.
9. **Codex** (owner, 2026-10-08; the `exec` half delegated and dropped by
   the author). No `--skip-git-repo-check` is added; Codex's own error
   names it. The project trust is given at launch, as CLIENT_HOOKS.md §3
   requires, in a form measured before step 3.
10. **The tests of the launcher** (owner, 2026-10-08: "在现有 harness 之外你
    单独搞一套", and 10-09). They run outside the shared harness, on the
    tool's own attached RPC host, through a fixture of their own in
    `test/test_launcher.py`; the process-group code they need lives in
    `test/harness.py` at module scope and is shared with
    `Harness.run_tool` (owner, 10-09: the direction was the separate
    Isabelle process, the shape is the author's, (B)).
11. **README** (owner, 2026-10-09: wording delegated to the author). The
    "How to use" section of §5: the 10-06 text corrected for the session
    structure of R21 (`TAT_Isabelle_Std` builds on `Minilang_AoA`, so six
    components are registered and the standard command names `-P` and
    `-l`), a first version to be polished once the system is done; the
    documents-table row of §5; no sentence about Codex's flags and none
    about Claude Code's folder-trust prompt (CLIENT_HOOKS.md §5 states it).
12. **`TAT_mcp` has `-c` and no option beyond today's**; the `-q` and `-w`
    of revision 1 do not exist (owner, 2026-10-08). The behaviour `-q`
    stood for is §1.4.
13. **Process**: the plan is reviewed before implementation, and no code
    changes before the owner agrees (owner, 2026-10-06 and 10-08); the jar
    is rebuilt only on the owner's word (§3.5).
14. **`LD_LIBRARY_PATH`** (owner, 2026-10-09). Isabelle's settings can leave
    an empty element in `LD_LIBRARY_PATH`, which the loader reads as the
    current directory; under `isabelle TAT` the client's current directory
    is the agent directory, where the agents write, and the hooks' commands
    run there with the client's environment. The owner ruled that this
    needs no handling. It is recorded as an accepted gap in CLIENT_HOOKS §5
    (step 2), nothing else.

## 2. `isabelle TAT`

### 2.1 The usage text (approved 2026-10-06)

```
Usage: isabelle TAT [OPTIONS] WORKING_DIRECTORY [CLIENT_ARGS ...]

  Options are:
    -P PLUGIN    a plugin to load in this working directory, as isabelle TAT_new -P
    -c CLIENT    the agent client: claude-code or codex (default: claude-code)
    -l BASE      the base heap, as isabelle TAT_mcp -l
    -p PORT      the port of the MCP server, as isabelle TAT_mcp -p
    -d DIR       as Isabelle's -d: a further directory whose ROOT declares
                 Isabelle sessions
    -o OPTION    as Isabelle's -o: override an Isabelle system option

  Create WORKING_DIRECTORY for TAT when it does not exist, start a TAT
  conversation on it, and start CLIENT in its agent directory,
  WORKING_DIRECTORY/TAT.agents, with CLIENT_ARGS. The conversation ends
  when the client exits.
```

The tool's description, shown by `isabelle` without arguments:
`start a TAT conversation and its agent client`.

### 2.2 What it does, in order

1. `Getopts` in its internal mode reads `-P` (repeatable), `-c`, `-l`,
   `-p`, `-d` (repeatable), `-o` (repeatable); it stops at the first
   non-option, WORKING_DIRECTORY, and the rest are CLIENT_ARGS, untouched.
   No WORKING_DIRECTORY, or a bad option, is a usage error: the usage text
   on stderr, exit 2 (as `TAT_mcp`'s). The client's name is looked up in
   `clients` by the lookup `TAT_mcp` and `TAT` share (§3.3), which refuses an
   unknown name with §1.8's first sentence, exit 2. `clients` is an
   ordered list of (name, executable): `claude-code` → `claude`,
   `codex` → `codex`. The executable is looked up once, as the shell looks
   it up: `Isabelle_System.getenv("PATH")` is split at `:` with
   `space_explode`, empty entries kept (an empty entry is the current
   directory, as POSIX says); each entry is joined with the name as
   `java.nio.file.Path.of(entry, name)` — `PATH` entries are platform
   paths, so Isabelle's `Path` and its syntax are not used; the first that
   is a regular, executable file (`Files.isRegularFile`,
   `Files.isExecutable`) is made absolute with `toAbsolutePath`, with no
   `normalize` and no `toRealPath`, so no symbolic link is followed and no
   `..` is rewritten; its string is the client's `argv[0]`. None found is
   refused with §1.8's second sentence, exit 2. All of this happens before
   anything is created. Every refusal, like every usage error, is an
   Isabelle `error` and is printed with `*** ` before it.
2. The working directory is created by `create(arg, plugins): Path`,
   `TAT_new`'s whole body after the parse, which `TAT_new` and `TAT` both
   call: it runs `working_directory(arg)` (the absolute path, and the
   bracket refusal), then the two other refusals (a file, a non-TAT
   directory), makes the directory, runs `Plugins.add`, and returns the
   `Path`; the same sentences, exit 2. `TAT` launches only on the `Path`
   `create` returned.
3. `Starting TAT... It may take a while` is printed on a
   `Console_Progress(stderr = true)`, and the conversation is started
   through the launcher's `start` (§3.3), the function `TAT_mcp` and `TAT`
   share, with the port from `-p`, the client's name, and the client: that
   path and CLIENT_ARGS.
4. `launch` handles `TAT.serving` (§3.2): it prints the URL line, saves the
   terminal mode under §1.3's condition, and starts the client in the
   agent directory the message carries, with the message's launch
   arguments followed by CLIENT_ARGS, through
   `isabelle.setup.Environment.process_builder(cmd, cwd, null, false)` with
   `inheritIO()`. The client's exit is the second event of §1.2. While the
   client exists, an interrupt at the terminal belongs to the client:
   `launch`'s interrupt action does nothing then. A terminal hangup, or a
   SIGTERM to the JVM or to its process group, ends the client as §1.3
   says, within the bound, and the JVM exits only after it; the command's
   pid, Isabelle's bash, does not wait for it (below).
5. The launcher's `start` ends the tool as §3.3 says, from the pair
   `(rc, messages)` that `launch` returns. When the client's exit came
   first, the pair is `(the client's code, Nil)`: nothing is printed and
   the tool exits with that code (returning normally when it is 0). When
   the conversation's end came first, `launch` has already ended the
   client and restored the terminal, and the tool prints those messages
   and exits 2, for `TAT_mcp` and `TAT` alike, since `start` alone does the
   printing and the exit.
6. A refusal before the client starts, from `create` or from `launch` (the
   base heap, the options, a session under the working directory, the lock
   held by another conversation, a port that cannot be bound) is printed
   and the tool exits 2; the client never starts. An interrupt before the
   Isabelle process starts ends as MODULE_STRUCTURE §5 states for
   `TAT_mcp` (130 outside the base heap's build; 2 with
   `Failed to build Isabelle/<BASE>` during it; ignored during the check of
   an existing heap).

Exit codes, in one place: 2 for a usage error, a refusal, and a
conversation that ended first; an interrupt before the Isabelle process
starts as MODULE_STRUCTURE §5 states; otherwise the client's code. A
signal from outside is not one of the tool's own ends: a shell reports
128 plus its number (143 for SIGTERM, 129 for a hangup), see the next
paragraph.

A supervisor that ends `isabelle TAT` from outside signals its process
group, then waits until no process of the group runs, not for the pid:
for every Scala tool of Isabelle, `TAT` included, `lib/Tools/java` keeps a
bash without signal handlers between the command's pid and the JVM, and
that bash dies of the signal at once, so the caller sees a death by that
signal while the JVM first ends the client, the Isabelle process and the
Python side. Under the attached RPC host (the default), the Python side's
end releases the working directory's lock; under an RPC host started
elsewhere (`RPC_Host`, ARCHITECTURE §9), the Python side belongs to that
host, its ending runs through the connection's door and releases the lock
once unwound, and the end of the tool's group does not wait for that.
This is stated in MODULE_STRUCTURE §5.

The client inherits Isabelle's settings environment, like every program an
Isabelle tool starts; `LD_LIBRARY_PATH`'s empty element is §1.14's
accepted gap.

## 3. The launcher (`src/scala/tat.scala`)

### 3.1 `TAT_mcp`

- `var port = 0`; `default_port` goes.
- The refusal of §1.8 replaces `TAT knows no client <name>`, through the
  shared lookup (§3.3); the `-c` line of the usage prints the names of
  `clients` only.
- The body calls `start` (§3.3) with no client; `TAT.serving` is handled
  by `launch`, which without a client only prints the URL line.
- The usage text (approved 2026-10-06; the `-l` line shows `ISABELLE_LOGIC`'s
  value, as today):

```
Usage: isabelle TAT_mcp [OPTIONS] WORKING_DIRECTORY

  Options are:
    -c CLIENT    the agent client that will connect: claude-code or codex
                 (default: claude-code)
    -l BASE      the base heap (default: ISABELLE_LOGIC="HOL")
    -p PORT      the port of the MCP server (default: a random one the system assigns)
    -d DIR       as Isabelle's -d: a further directory whose ROOT declares
                 Isabelle sessions
    -o OPTION    as Isabelle's -o: override an Isabelle system option

  Start a TAT conversation on WORKING_DIRECTORY, providing the MCP service
  at http://127.0.0.1:PORT/mcp.
```

### 3.2 `launch`

`launch` keeps its signature and its return type `(Int, List[String])`,
and gains one data parameter, `client: Option[Client]`, where
`Client(executable: java.nio.file.Path, args: List[String])`; `TAT_mcp` and
`TAT_compile` pass `None`. Its parameter `arguments` keeps its meaning,
the boot's argument list. `launch` owns the client's whole lifetime:

- The state is one immutable value in one `Synchronized` cell, with one
  pure transition, `ended(rc, messages)`, which keeps an existing end:
  that is the first-wins record of §1.2. The value also holds the started
  client (below) once started, and one flag, "no client may start any
  more". Today's `finish(rc, messages)` is `state.change(_.ended(rc, messages))`,
  defined before the base heap's build; every way of recording an end
  goes through `ended`. The client's exit enters `finish(code, Nil)`. The
  comment at `ended` lists every event that ends the conversation: the
  `TAT.finished` message; a failure of the `TAT.finished` or `TAT.serving`
  handler, decoding included; the start failure; the process's
  termination; the client's exit.
- The started client is one value holding the `Process` and the saved
  terminal mode (`Option[String]`); its `terminate()`, named after
  Isabelle's `Bash.Process.terminate` and run once in Isabelle's idiom (a
  `def` backed by a private `lazy val`, as `zstd.scala`'s `init` is), is
  §1.3's ending of the client: when the client still runs (`isAlive`), a
  snapshot of
  the client's descendants (`p.descendants()`); SIGTERM (`destroy()`); a
  `waitFor` bounded by `CLIENT_BOUND`, a named constant of 10 s beside this
  value (the owner's "at least 10 s"; its comment states that
  harness.py's `TERMINATION` must exceed it plus Isabelle's own
  termination); when that wait expires with the client
  still running, a second snapshot taken then; SIGKILL
  (`destroyForcibly()`, which checks each process's start time) to the
  client first, then to every process of either snapshot, so that a client
  still running cannot start a child between the two; `waitFor()`; a
  client already gone is left as it is. Then, whichever event came first,
  the restore, `stty(List(saved))` (below), only when a mode was saved and
  `foreground()` holds at that moment, and right after it, under the same
  condition, §1.3's fixed sequence written to stdout
  (`Output.print_stream`). Nothing in it can fail: a snapshot
  that cannot be taken is empty (the one `Exn.capture`, on
  `descendants()`), and the rest runs under `try_uninterruptible`, as
  `Bash.Process.terminate` does. The rule of what SIGKILL reaches:
  exactly the processes that are the client's descendants at one of the
  two moments; a process in the first snapshot is reached even when its
  parent exits later, the client itself included. Not reached, as
  examples of the rule: a process
  already orphaned when the end begins (a command an agent put in the
  background whose shell has returned; a daemon that forked twice; after
  a normal exit of the client, everything it left behind); a process born
  after the first snapshot whose parent exits before the second. Unless
  such a
  process left the tool's process group, a signal to the group reaches
  it. Whichever caller first calls `terminate()` runs the sequence; the
  other waits for it to finish. `foreground()`, `stty` and the save sit
  beside this value, private to the object.
- One predicate, `foreground()`: read `/proc/self/stat` through the JDK
  (`Files.readString`, which reads to the end; Isabelle's `File.read`
  reads the size procfs reports, 0, and returns nothing — code review
  C1), bind the fields
  after the last `)` by their proc(5) names in one pattern (state, ppid,
  pgrp, session, tty_nr, tpgid), and hold exactly when `pgrp` equals
  `tpgid`; a `tpgid` of -1 or a failed read gives false. One helper,
  `stty(args): Option[String]`: it runs `stty` with `args` through
  `Environment.process_builder` with stdin `Redirect.INHERIT` (stty acts
  on its fd 0, which must be the tool's terminal, not a pipe), stdout read
  and stderr `Redirect.DISCARD`, and returns `Some(trimmed output)` on
  exit 0, `None` otherwise. The terminal mode is saved by `stty(List("-g"))`
  only when `foreground()` holds and stdout is the same file as stdin
  (`Files.isSameFile` on `/proc/self/fd/0` and `/proc/self/fd/1`); its
  result is then the test of "stdin is a terminal": `Some(mode)` is the
  saved mode, `None` means nothing is saved. No other probe is used
  (`System.console()` is not, since its meaning changes in JDK 22). No
  kernel call sets the mode only for the foreground group, so between the
  check and the set there is a window in which a Ctrl-Z followed by `bg`
  would stop the tool's group with SIGTTOU: that is an ordinary
  job-control stop, accepted; SIGTTOU is neither ignored nor blocked,
  since either would let the mode be set from the background, underneath
  the shell.
- The `TAT.serving` handler decodes the message's triple into `url`,
  `agent_directory` and `launch_arguments`, a failure becoming the end
  `(2, "TAT.serving could not be decoded: <failure>")`, as the
  `TAT.finished` handler does; prints `TAT is serving on <url>`; then,
  when a client is given, runs one `change` on the state. Inside
  it, only when the state is exactly as `launch` created it (no end, no
  client, the flag not set): the terminal mode is saved and the client is
  started in `agent_directory` (a `java.io.File` built from the carried
  string, never through `Path.explode`) with
  `client.executable.toString :: launch_arguments ::: client.args`, and
  the returned state holds either the started client or
  `st.ended(2, "TAT cannot start <command>: <message>")`. Nothing inside
  the locked section calls `finish`: `Synchronized.change` assigns its
  function's result after the function returns, under a reentrant
  monitor, so a `finish` reached inside would be overwritten. The
  client's exit is registered right after the start, with
  `onExit().thenRunAsync(...)`: the action runs on an executor, never in
  the registering thread, so it blocks on the monitor until the client is
  recorded and only then enters `finish`, wherever the registration sits
  (code review C5). This is argued, not tested.
- The interrupt action of the `POSIX_Interrupt.handler` around the wait:
  nothing while a client process exists; otherwise, under the lock, set
  the flag and terminate the Isabelle process.
- One JVM shutdown hook, registered with `Isabelle_System.create_shutdown_hook`
  before the Isabelle process starts and removed in the outer `finally`
  (the pairing `Bash.Process` uses). Its body is one procedure: under the
  lock, set the flag and read the started client; outside the lock, call
  its `terminate()`.
- After the boot command: `try { the wait } finally { the hook's body }`,
  then `log.stop()` and `session.stop()` as today; the outer `finally`
  only removes the hook. The wait's single read is what `launch` returns;
  nothing reads the state again, and the first-entered-wins rule decides
  only between entries that both arrive before the wake-up.
- `Log_Follower(progress, warnings = client.isEmpty)`: the flag is read in
  one place, `warning`, the one line that echoes a `warning` record;
  otherwise the follower works as under `TAT_mcp` (the thread, `drain`,
  `stop`, and `follow` printing `Log: <directory>`), so no route can echo a
  warning. The class comment says that the flag only suppresses the echo.
- The `TAT.finished` and `TAT.serving` handlers each catch their own
  failure and turn it into an end: the first message is the conversation's
  end itself, and a failure the second let escape would leave neither a
  client nor an end. The `TAT.log_directory` handler stays as it is: its
  one message under `isabelle TAT` arrives before `TAT.serving`, so no
  client exists when it runs; its body cannot fail on what the ML side
  sends, which has passed the same path checks there; and if it did fail,
  the conversation would go on without the `Log:` line.

`TAT_compile` shares `launch` unchanged in behaviour: its exit codes, its
usage text and its three Isabelle-backed cases in `test_launcher.py` stay.
Under the attached RPC host the Python side's conversation ends as it does
today when the Isabelle process is terminated, and no `ended` record is
written (LOGGING.md §4); under an RPC host started elsewhere the ending
runs and `ended` is written, as LOGGING §4 states.

Names: the JVM's two events are "the conversation's end" and "the client's
exit", and the record is "which of the two came first"; "ending" keeps
MODULE_STRUCTURE §4.6's meaning (the conversation's ending and the ending
object). `launch`'s comments and local names follow these names when
step 2 rewrites it (today's `ending` at the wait; the comment at the
state's `ended` above). `ended` names the state's transition only; the
started client's run-once procedure is `terminate()`. The client's launch arguments are defined once, in
MODULE_STRUCTURE §4.6's list of what a client subclass implements;
CLIENT_HOOKS §3, CONSTRUCT_INTERACTION §8 and MODULE_STRUCTURE §5 cite it.

### 3.3 `start`, `TAT_mcp` and `TAT`

One function next to `launch`, the launcher's `start`, named after the
protocol command `TAT.start` it sends, which reaches the ML entry
`TAT_Framework.start`:
`start(progress, dir, logic, dirs, options, port: Int, client_name: String, client: Option[Client]): Unit`.
It calls `launch(..., "TAT.start", List(port.toString, client_name), client)`,
prints the returned messages as error messages on `progress`, and exits
with `rc` when `rc` is not 0; when it is 0 it returns normally. `TAT_mcp`'s
body calls it with no client; `TAT`'s body is §2.2: the options, the
shared lookup of the client's name (one function on `clients` that maps a
`-c` name to its executable and raises §1.8's first sentence for an
unknown one; `TAT_mcp` and `TAT` both call it, `TAT` before the `PATH`
lookup and `create`), the `PATH` lookup, `create`, the progress, and
`start` with the client. `TAT` holds no shared mutable state; the client's
lifetime is `launch`'s.

### 3.4 `create`

`create(arg: String, plugins: List[String]): Path` is `TAT_new`'s whole
body after the parse (§2.2 step 2): `working_directory(arg)`, the two
other refusals, the directory, `Plugins.add`, the `Path` returned.
`TAT_new`'s usage ends, in place of "Afterwards, you can start TAT on it
with: isabelle TAT_mcp WORKING_DIRECTORY", with the sentence of §5.

### 3.5 The jar

`lib/tat.jar` is committed with `no_build = true`. To rebuild: remove the
`no_build` line of `etc/build.props`, run `isabelle scala_build`, restore
the line — only on the owner's word, as for every build in this tree, and
only while `pgrep -af 'Isabelle_Tool [T]AT'` finds nothing: that pattern
catches `TAT`, `TAT_mcp`, `TAT_compile` and `TAT_new`, each through both
its JVM and its `lib/Tools/java` bash; any Isabelle Scala tool started
while the line is out builds the jar itself, because `bin/isabelle` runs
`scala_build` before each one and the component is registered for the
user, and a running TAT tool shows that a test run (the harness's
`TAT_mcp`, the launcher fixture's tools) is in progress. A process found
may be the owner's own conversation and is reported to him. The rebuild
window is told to every peer session (§6, step 0). `etc/build.props`'s
comment states why `no_build` is there and points to MODULE_STRUCTURE §5
for the procedure.

## 4. The Python and ML sides

### 4.1 The socket (`mcp_server.py`, `toplevel.py`)

`served` does `with _bind(port) as sock:` (a `socket.socket` is its own
context manager) and builds `SERVERS[client](ending, sock, tools, agents)`.
`_bind` also listens, inside its existing `try`, so that either failure is
the one `TAT_StartupError` with today's sentence: under `SO_REUSEADDR` a
bound socket that does not listen blocks no second bind, and the bind now
comes before the server's construction and `configure`'s writes, so the
socket `served` holds must own the port from the start (one short comment
gives the reason). The constructor does no I/O: it keeps the socket and
derives `port`, `url`, the `authority` of the transport-security settings
and uvicorn's configuration from `sock.getsockname()`. `__aenter__` no
longer binds; on failure it still removes the loop's reader. The socket
cannot outlive `served`'s block, so a `configure` that raises leaves no
bound socket behind. The rule for the tests: every construction of a
server in `test_mcp_server.py` takes a socket bound with
`with _bind(...) as sock:` — the helpers `serving()`, `configured()` and
`launched()` (which binds and constructs inside its task), the direct
construction at :606 (its own `with`, since `serving()` would start
`serve` and defeat that test's purpose), and the startup-failure case
re-aimed at `remove_reader`; `serving(port, tools)` keeps its signature,
so `test_hooks.py` does not change; `server.port` replaces `_port`; the
bind-failure case is rewritten: inside `with _bind(port):`, a second
`_bind(port)` raises `TAT_StartupError` with the sentence (mutation: the
`listen()` removed); `free_port` stays. `Claude_Code_Server.__init__`
takes `sock: socket.socket`. The `TAT_Server` docstring's sentence
"`async with` binds the port" and `configure`'s "called before the port is
bound" are rewritten.

### 4.2 The order of serving, and `TAT.serving`

In `served`, after `async with server`: `announce(server.port)` writes the
lock's port line, which the hooks read; then
`await isabelle_driver.serving(conversation, server.url, agent_directory, server.launch_arguments(agent_directory))`
makes the one round trip, next to the `serving` log record;
`agent_directory` is the canonical path of `<working directory>/TAT.agents`
(symbolic links resolved), computed once by a helper next to `AGENTS`.
Only after that round trip can a client exist, since `launch` starts it
from the handler; so the port line precedes the client by construction.
`launch_TAT` shrinks to `async with served(...) as (_, _, server): await
server.serve()`; the line it wrote to the connection goes.

`isabelle_driver.serving` calls the ML callback `TAT.serving`, defined
beside `log_directory` with the same `make_callback` shape, whose function
sends `Output.protocol_message [Markup.function "TAT.serving"]` with the
triple encoded by `XML.Encode.triple string string (list string)`; the
Scala handler decodes the same triple. The call lives in `served` only:
`toplevel.conversation()` is shared with `compile_TAT`, whose one round
trip is `TAT.log_directory`, and the compile's ML command keeps
`log_directory` as its only callback (COMPILATION.md §5).

### 4.3 The client's launch arguments

A member declared on `TAT_Server` raising `NotImplementedError` and
overridden by both subclasses, as `_client_files` is, and the first such
member that is static, so that its signature states that it reads no
server state: `@staticmethod launch_arguments(agent_directory: Path) -> list[str]`.
`served` calls it on the server; the step 1 test calls it on the class,
with no socket and no `Ending`.

- `Claude_Code_Server`: `[]`.
- `Codex_Server`: `["--dangerously-bypass-hook-trust", "-c",
  'projects={<K>={trust_level="trusted"}}']`, `<K>` being
  `toml_string(str(agent_directory))`, the TOML string encoder `configure`
  already uses. The trust key and the client's working directory are the
  same value, since both are the carried canonical path. The form is
  measured before step 3 (§6, step 4); if the measurement refutes it, the
  owner decides the form.

CLIENT_HOOKS §3 gains a third code block, beside the two files, showing
the launch arguments Codex's client class gives, citing MODULE_STRUCTURE
§4.6's definition and naming no tool (who starts the client belongs to
CLIENT_HOOKS's opening paragraph, which step 2 rewrites), with
`<agent directory>` as the placeholder, defined there once as the
canonical path of `<working directory>/TAT.agents` (symbolic links
resolved), the trust key and Codex's working directory alike (its
`<working directory>` is the absolute spelling); CLIENT_HOOKS §5 refers
back to it. `test_mcp_server.py:843` unpacks three blocks, and a test
compares `Codex_Server.launch_arguments(...)` with that block as
`documented` does, the TOML value parsed first and filled afterwards.

### 4.4 The log

Proposed to the logging session, which writes LOGGING.md: §4, the `start`
record's `port` is the port asked for, 0 when the system chooses, and the
`serving` record carries the URL with the port bound, as today; §4, the
paragraph after the `conversation` table names the usual ends as
ARCHITECTURE §9 states them and cites §9 (in place of "the manager's
SIGTERM"), and that such an end leaves no `ended` record stays; §7, under
`isabelle TAT` the launcher does not echo `warning` records, which stay in
the log, while `TAT_mcp` and `TAT_compile` echo them as they are written.
The §7 sentence is asked for before step 2's commit (§6, step 0).

## 5. The user-visible texts

Approved: the usage text of `isabelle TAT` and its description (§2.1);
`TAT_mcp`'s usage (§3.1); the refusals `TAT doesn't know the agent client
<name>` and `TAT cannot find <command> on the path`, `<command>` being
`claude` or `codex`; `TAT cannot start <command>: <message>` (2026-10-09);
`TAT.serving could not be decoded: <failure>` (2026-10-09); the URL line
`TAT is serving on http://127.0.0.1:<port>/mcp`; the waiting line
`Starting TAT... It may take a while`; `TAT_new`'s closing sentence
(2026-10-06), in place of "Afterwards, you can start TAT on it with:
isabelle TAT_mcp WORKING_DIRECTORY":

```
  Create WORKING_DIRECTORY for TAT. The recommended way to use TAT is
  isabelle TAT WORKING_DIRECTORY; with it, you don't need to run
  isabelle TAT_new yourself.
```

README's "How it runs" (approved 2026-10-06 as a first version, to be
polished once the system is done; the components and the command corrected
by the author under the 2026-10-09 delegation): its first paragraph ("TAT
is a Python process and an Isabelle process ...") stays; everything after
it, from "Node classes are extensible" to "give it that URL." (the plugin
paragraph and the three usage blocks), is replaced by:

> ### How to use
>
> Once, from the repository root, register the six Isabelle components
> TAT's sessions build on:
>
>     isabelle components -u contrib/Theory-Agent-over-Trees -u contrib/Isabelle_RPC -u contrib/Performant_Isabelle_ML -u contrib/auto_sledgehammer -u contrib/Isa-Mini -u contrib/Semantic_Embedding
>
> Then:
>
>     isabelle TAT -P TAT_Isabelle_Std.TAT_Isabelle_Std -l Minilang_AoA [-c claude-code|codex] WORKING_DIRECTORY [CLIENT_ARGS ...]
>
> `-P` records the plugin of Isabelle's standard commands (`Theorem` among
> them) in WORKING_DIRECTORY: this launch and every later one load it,
> giving `-P` again changes nothing, and nothing removes it. `-l` names the
> base heap holding the `aoa` method the plugin's proofs use; the working
> directory does not record it, so it is given at every launch, and this
> one command line serves for every launch. Without the plugin the forest
> holds sessions and theories only. The command creates WORKING_DIRECTORY
> if needed, starts a TAT conversation on it, and starts the agent client
> (Claude Code by default) in `WORKING_DIRECTORY/TAT.agents/`, where it
> writes the client's configuration at every launch. Arguments after
> WORKING_DIRECTORY are passed to the client. The conversation ends with
> the client; the forest stays in WORKING_DIRECTORY for the next one.
>
> Lower-level commands: `isabelle TAT_new` creates a working directory;
> `isabelle TAT_mcp` serves a conversation on it over HTTP, for a client
> started by hand; `isabelle TAT_compile` writes its theories and a ROOT
> into it. Each prints its usage when run without arguments.

Open for the polish: the Python side's installation, undocumented
anywhere yet.

README's documents table (author, delegated 2026-10-09): the row for
`docs/CLIENT_HOOKS.md` reads
`| [docs/CLIENT_HOOKS.md](docs/CLIENT_HOOKS.md) | The agent client's files, written at every launch (the MCP entry, the hooks, the sandbox settings), its launch arguments, and the endpoint the hooks call |`
(today it says "The hook files `TAT_new` writes for each agent client, and
the endpoint they call").

Nothing awaits approval.

## 6. Steps, tests and checks

Each step's "Files:" line is exactly its commit's pathspec, so a document
hunk cannot ride in a commit whose file was not announced and checked;
steps 1 and 2 each have a "Gate:" line, run on the working tree just
before that step's commit, over the paths it names, with
`/usr/bin/grep -rnI` (step 3 touches no document). Every token goes in
the gate of the step whose hunks make its fact true, so step 1's gate
checks none of step 2's retired tokens: until step 2 lands they still
state the truth about the code.

0. **Coordination**, a check before each step: the step's "Files:" line
   goes to every peer session, and a file holding a peer's uncommitted
   work waits. Promised:
   - the jobs session `[9ffa3c]` learns the new shape of `TAT_Server`'s
     construction as soon as step 1 lands (`serving(port, tools)` in
     `test_mcp_server.py` keeps its signature); `harness.py`'s change (step
     3: the shared context manager with its `terminal` and `stdout`
     parameters, the
     module-level `run_tool` and `deadline`, `Harness.run_tool` and
     `Harness.deadline` keeping their signatures and `Harness.run_tool` its
     shields, and `end_group` now waiting on the group, which also
     corrects `Harness.release_child`'s escalation); for its record: that
     CONSTRUCT_DECISIONS.md §1's "external manager" premise is superseded
     by §1.1–§1.2, that TEST_HARNESS_PLAN.md §1 item 1 no longer holds for
     the launcher's cases and its §10's "never exercises Isabelle's launch
     of an ephemeral host" stops holding from step 3 on (except for the
     interpreter the RPC layer picks for itself), and that the record's
     `isabelle TAT` is the old name of `TAT_mcp`; that the README's `-P`
     paragraph names `Theorem` as the plugin's, which becomes true when a
     `python_packages` list in `Isabelle_Std/ML/TAT_Theorem.ML` names
     `isabelle_theory_agent.std` — the committed step 15 (68e7e03) does
     not, and the jobs session's STEPS_14_15_REVIEW.md, finding A, lists
     that change as a fix needing no question; the check before step 2
     reports the fact itself, with
     `/usr/bin/grep -n 'isabelle_theory_agent.std' Isabelle_Std/ML/TAT_Theorem.ML`;
     that from step 3 on the Isabelle-backed suite grows by about eight
     boots, at most two at a time beside the harness's processes,
     deselectable with `--ignore=test/test_launcher.py`; every commit;
     that the rebuild guard now covers every TAT tool (§3.5);
     `conftest.py` is its file (step 3 adds one name to `HARNESSES`);
   - every peer session, the logging session included (it drives a real
     `TAT_mcp` through the harness), is told the moment the jar rebuild
     begins and when the jar is back, and holds its Isabelle-backed runs
     meanwhile (§3.5);
   - the logging session `[b341d7]` is told when `mcp_server.py` and
     `toplevel.py` are free, to re-run its `configure` and hook tests; that
     under step 1 `configure` runs after the bind with `self.url` final,
     and `tat.lock` keeps its two lines, the second the bound port; that
     `-q` is gone and §1.4 replaces it; the §4.4 proposals, with the §7
     sentence asked for before step 2's commit (the check before step 2
     reports whether it has landed; MODULE_STRUCTURE §5 states §1.4 on its
     own from step 2's commit either way); and what revisions 2 to 8
     changed (the Scala tool, the socket, the `TAT.serving` triple, the
     client's lifetime in `launch`);
   - commits name their files, leaving out other sessions' uncommitted
     ones.
1. **Python and ML** (§4). Files: `isabelle_theory_agent/mcp_server.py`,
   `toplevel.py`, `isabelle_driver.py`; `ML/TAT_Framework.ML`;
   `docs/MODULE_STRUCTURE.md` (§2.6's callback list gains `TAT.serving`;
   §4.6: the socket, bound and listening from `_bind` on, the order of
   serving, the triple, `configure` after the bind, the line to the
   connection removed, the launch arguments in the list of what a client
   subclass implements); `docs/CONSTRUCT_INTERACTION.md` (§8's list gains
   the member); `docs/CLIENT_HOOKS.md` (§3: the third code block and
   `<agent directory>`, and its prose: the launch arguments come from the
   client class, no `exec` rule, the project trust given at launch);
   `test/test_toplevel.py`, `test/test_mcp_server.py`,
   `test/test_conversation.py`. Gate, over `README.md`, `docs` and
   `isabelle_theory_agent`: retired `binds the port` and
   `before the port is bound` (mcp_server.py:458, :526), and the
   `TAT is serving` and `does not echo` hits in `isabelle_theory_agent`
   (toplevel.py:172–173); judged: those two tokens in `docs`
   (MODULE_STRUCTURE §4.6), `TAT.serving` (each hit says only what the
   Python and ML sides send and carry), and `isabelle TAT([^_]|$)` (step 1
   adds no hit). New tests: the lock's second line is the bound port; a
   `served` with port 0 serves on a port that is not 0; the stand-in
   connection records `TAT.serving` with the triple, after the lock's port
   line was written (the Recorder copies `tat.lock` when `TAT.serving`
   arrives; mutation: swap `announce` and the round trip); a `configure`
   refusal closes the socket `served` bound (the test wraps `_bind` at the
   name `served` looks it up by, keeps the socket, asserts
   `fileno() == -1`; mutation: drop the `with`);
   `Codex_Server.launch_arguments(...)` on the `working_directory` fixture
   (a space and a DEL in the path), with no socket and no `Ending`, equals
   CLIENT_HOOKS §3's block with the placeholder filled, and its TOML value
   reads back with `tomllib` to the agent directory's canonical path, and
   `Claude_Code_Server.launch_arguments(...)` is `[]` (mutations: plain
   quotes in place of `toml_string`; a changed key; the flag left out).
   Existing tests adapted: `test_toplevel.py`'s Recorder loses
   `lines`/`writeln` and sets `served` on `TAT.serving`, its assertions at
   :83/:93 and the comment at :103 follow; `test_mcp_server.py` as §4.1
   says, and :843 unpacks three blocks; `test_conversation.py:129` and
   `:137` count three round trips.
2. **The launcher** (§3). Files: `src/scala/tat.scala`, `lib/tat.jar`
   (rebuilt on the owner's word), `etc/build.props` (toggled and
   restored; its comment states why `no_build` is there and points to
   MODULE_STRUCTURE §5 for the procedure), `README.md` ("How to use" and
   the table row),
   `docs/ARCHITECTURE.md` (§1: the **launcher** entry gains `TAT`, the
   **plugin** entry names `-P` to `isabelle TAT_new` or `isabelle TAT`;
   §2.2 likewise; §9: the conversation's lifetime stated once — under
   `isabelle TAT` the client's exit ends the conversation and a
   conversation that ends first ends the client; under `TAT_mcp` alone the
   conversation ends with its process, nothing ties that process to the
   client's, and whoever started `TAT_mcp` ends it when the client ends;
   no manager — keeping its sentence on the two host orders; §9's
   Launching paragraph: its opening names four tools (`isabelle TAT`
   creates the directory when needed, starts a conversation and starts the
   client in the agent directory; `TAT_new` and `TAT_mcp` do the first two
   on their own, for a client started by hand; `TAT_compile` compiles), its
   usage block gains a first line in its own notation,
   `isabelle TAT [-P PLUGIN]... [-c CLIENT] [-l BASE] [-p PORT] [-d DIR]... [-o OPTION]... WORKING_DIRECTORY [CLIENT_ARGS ...]`,
   "`TAT` and `TAT_mcp` choose the agent client with `-c`", the port is
   one the system assigns unless `-p` fixes one, and its exit-code
   sentence names `TAT_mcp` and `TAT_compile` in place of "either tool"
   with its exception clause unchanged), `docs/MODULE_STRUCTURE.md` (§1's
   file table; §4's opening sentence; §4.5 names `-P` to `isabelle TAT_new`
   or `isabelle TAT`;
   §4.6: the sentence beginning "The external manager's SIGTERM ends the
   launcher" restated to name what stops the Isabelle process — under
   `isabelle TAT` the client's exit, a terminal hangup, a SIGTERM or
   hangup to the JVM or to the tool's process group (code review C3), the
   end of `TAT_mcp`'s process — citing ARCHITECTURE §9, keeping the two
   host orders (under an RPC host started elsewhere the end arriving
   through the connection's door, under the attached host no ending
   running), dropping "the client is gone" and saying instead that no call
   is answered with the ending's line and that a client still running finds
   the connection closed, keeping the lock, the database and the log
   clauses; §5: it states each fact of §1.2–§1.5, §1.7–§1.8, §2.2 and
   §3.1–§3.3 once, in §3.2's names — `TAT_mcp`'s steps 1–5 amended in
   place, `isabelle TAT` in a paragraph of its own that refers to them, as
   `TAT_compile`'s paragraph ("shares steps 1 to 3") does, so that
   COMPILATION.md §5's "Steps 1 to 3 of `TAT_mcp`" and its exception
   sentence stay right; in step 5, for `TAT_mcp` and `TAT`, on
   `TAT.serving` the launcher prints `TAT is serving on <url>`, the list
   of ends gains "2 when `TAT.serving` arrived but could not be decoded,
   with `TAT.serving could not be decoded:` and the failure", one clause
   says that the two handlers turn their own failure into an end, and
   "ended by … returning" names `TAT_Framework.start`; the `isabelle TAT`
   paragraph carries the waiting line, §1.5's streams, §1.2's two
   outcomes, `TAT cannot start <command>: <message>`, and its exceptions
   to step 5 as one list, as `TAT_compile`'s paragraph does: §1.4 (the
   launcher echoes no `warning` record; the records stay in the log,
   LOGGING §7) and §2.2 step 4's interrupt rule (while the client exists
   an interrupt belongs to the client and the launcher does nothing with
   it; before that, step 5's sentence applies); unchanged in their words:
   the sentence beginning "Every end of `TAT_mcp` and `TAT_compile` that
   is not a normal return" in its exception clause, extended to `TAT`
   with the client's code as its normal return, and the passage beginning
   "Once the Isabelle process is started", whose first clause the
   `isabelle TAT` paragraph excepts while a client exists and whose clause
   from "before that" on (130) `isabelle TAT` inherits; also the
   supervisor note of §2.2 with its signal clause and its two host orders,
   the inherited environment citing CLIENT_HOOKS §5's entry, the started
   client's `terminate()` running once with every caller waiting for it
   and `CLIENT_BOUND`'s 10 s, the terminal's condition and the save, the
   rule of what SIGKILL reaches cited by its opening words, the
   executable's lookup as §2.2 step 1 spells it, the jar guard with its
   rebuild procedure, and the launcher's `start`, which alone prints the
   messages of the end and exits, for `TAT_mcp` and `TAT` alike), `docs/CONSTRUCT_INTERACTION.md` (§1's first bullet, the serving
   process, gaining one sentence: a further client process on a running
   conversation, beside its client under `isabelle TAT` or `TAT_mcp`, or after it under
   `TAT_mcp` alone, is outside this premise, and TAT does not tell it from
   the first — on Claude Code its new transcript reads as a compaction,
   CLIENT_HOOKS §2; §1's second bullet, the lifetime premise, restated
   whole, its last sentence included: it cites ARCHITECTURE §9, also for
   who ends `TAT_mcp`, keeps that the ending runs only under an RPC host
   started elsewhere, and says that the Python side never detects the
   client's death, while under `isabelle TAT` the launcher, as the
   client's parent, learns of its exit and ends the conversation; §8's
   opening; its sentence "nothing is read from the claude or codex on
   TAT's path" restated: nothing is read from the client's program itself
   — `isabelle TAT` only finds it on the path and starts it, under
   `TAT_mcp` alone the program that connects is started by hand and need
   not be that one, and in both cases what is checked is what the
   connecting client states in `initialize`; the sandbox refusal's remedy
   stays; its `SessionEnd` sentence keeps the hook's reason, that it fires
   while agents still work, and cites what follows the client's exit to
   ARCHITECTURE §9), `docs/CLIENT_HOOKS.md` (the opening paragraph: "The
   client is started in the agent directory", by `isabelle TAT` or by
   hand; §4's `SessionEnd` sentence as above; §5: "TAT starts no client
   and wraps none" → `isabelle TAT` starts the client and wraps it in
   nothing, the sandbox is the client's own; and one entry in its
   "Accepted as they are" list, stated as fact with what was measured kept
   apart from what was inferred, as the socket entry does: under
   `isabelle TAT` the client runs in Isabelle's settings environment,
   whose `LD_LIBRARY_PATH` can end in an empty element that the loader
   reads as the current directory, so a shared library an agent writes
   into the agent directory is loaded outside the sandbox by the hooks'
   commands at every hook, on Claude Code by the program that starts its
   sandbox, and by the next client (§1.14)), `docs/node_classes/THEOREM.md`
   (the sentence beginning "A working directory has it when it was made
   with" names `-P` to `isabelle TAT_new` or `isabelle TAT`),
   `test/test_launcher.py` (the `-c`
   refusal asserts `*** TAT doesn't know the agent client emacs`). Gate,
   over `README.md`, `docs` and `src/scala`: retired, none of which may
   remain: `8191`, `default_port`, `TAT knows no client`,
   `external manager`, `manager's SIGTERM`, `TAT starts no client`,
   `three Isabelle tools`, `process's end` (LOGGING.md's hits leave only
   when the logging session applies §4.4); judged: `TAT_mcp`, with these
   passages listed in advance — CONSTRUCT_INTERACTION §1's first and
   second bullets and §8's opening, CLIENT_HOOKS's opening paragraph,
   MODULE_STRUCTURE §4's opening sentence, ARCHITECTURE §9's Launching
   paragraph, the glossary; `TAT_new -P`; `SIGTERM`; `TAT is serving`;
   `isabelle TAT`; `130` (every copy of the exception list read once:
   MODULE_STRUCTURE §5, COMPILATION.md §5, ARCHITECTURE §9, all unchanged
   in their exception clause). This commit makes `TAT_new`'s closing
   sentence and the README texts true, except what the plugin gives a
   conversation: the README's `Theorem`, like THEOREM.md and
   MODULE_STRUCTURE §4.5, holds once `TAT_Theorem.ML`'s registration
   names `isabelle_theory_agent.std`, the jobs session's fix of its step
   15 (STEPS_14_15_REVIEW.md, finding A). COMPILATION.md is unchanged;
   LOGGING.md's hunks are the logging session's (§4.4).
3. **The launcher's tests**, in `test/test_launcher.py`, outside the shared
   harness. Files: `test/test_launcher.py`, `test/harness.py`,
   `test/conftest.py`, and from the code review's fixes on
   `test/fake_agent_client.py`.
   - **The shared process-group code**, in `harness.py` at module scope,
     under one contract. One predicate, `running(pid)`, reads `/proc` and
     holds for a process that is running (not a zombie); it serves every
     group check and every "pid is not running" assertion. One bounded
     wait on the group polls `/proc` until no running process carries the
     group's id, bounded by `TERMINATION`, and returns the survivors; `group_alive` (which counted zombies through `killpg`)
     goes. `end_group(process, exited)` keeps its signature; its body:
     SIGTERM to the group, that wait, `os.killpg` SIGKILL only if a
     process of the group still runs (the group, not a kill per pid, so a
     reused pid cannot be hit and a late fork cannot be missed), then the
     unbounded await of `exited`; `Harness.release_child`'s final
     assertion uses the group check.
     `tool(argv, env, stdin=subprocess.DEVNULL, stdout=None, terminal=None)`
     is an async context manager that starts a tool with `Popen` in a
     session of its own (`start_new_session=True`,
     `preexec_fn=default_sigint`); `terminal`, a pty's slave, is made the
     controlling terminal by `fcntl.ioctl(fd, termios.TIOCSCTTY, 0)` on
     that descriptor in `preexec_fn`, which CPython calls after `setsid`,
     independently of stdin (bash takes only its stdin as controlling
     terminal, so the parameter is what lets a case have a controlling
     terminal and a non-terminal stdin at once); `stdout`, when given, is
     the child's stdout in place of the pipe. The pipes (stderr, and
     stdout unless given) are each connected through
     `loop.connect_read_pipe` to an `asyncio.StreamReader`, inside one
     `anyio.CancelScope(shield=True)` bounded by one loop turn per pipe, so
     that a cancellation pending at the start lands in the block, under
     its exit; each is read by one
     task from the start, which fills a buffer, signals waiters through an
     `asyncio.Event` (a waiter cancelled by a deadline cannot touch the
     reader), and never gates the
     exit (`asyncio.create_subprocess_exec` is not used: on Python 3.12
     its `wait()` returns only once every pipe is closed, which would let
     the pipes gate the exit). The leader's task stays private to `tool`
     and is what `end_group`
     receives; the handle offers `pid` (the leader's, the group's id),
     `exited` (`asyncio.shield` of that task, so that `await h.exited`
     cannot cancel the task `end_group` waits on — the rule harness.py
     already states for settlements) and `line(stream, predicate)` (the
     first matching line, raising with both buffers when the stream ends
     without one); inside the block `line` is the only read. The block's
     exit runs inside one `anyio.CancelScope(shield=True)` on either path,
     as `Harness.run_tool` does today: a deadline's cancellation is
     level-triggered, so an unshielded wait in the exit would be cut at
     once; and because the shield removes the deadline's protection, every
     wait inside it is bounded. Inside it: SIGINT to the group, on the
     exceptional path only (the deadline's cancellation, a failed
     assertion); the bounded group wait; `end_group` only if a process of
     the group still runs; the readers' join, with a bound of its own, at
     which the reader tasks are cancelled, both transports closed, and the
     exit fails naming the pipes still open (a process outside the group
     can hold them). After the shielded region: on the normal path, the
     failure naming the survivors if any; on the exceptional path, both
     output texts added to the exception as a note, then the re-raise.
     The group, not the pid, is what has exited: §2.2's supervisor rule
     (the leader is Isabelle's bash, which dies first), and `TERMINATION`
     (15 s from this step on, 10 s today) exceeds `CLIENT_BOUND` (10 s)
     plus Isabelle's own termination
     (up to 1 s for `Prover.terminate`, then about 1.1 s for
     `Bash.Process.terminate`) on every path; each constant's comment
     states this inequality against the other (re-review R1). Only after the
     join do the handle's `stdout` and `stderr` hold the complete texts;
     reading either one earlier raises. A module-level `run_tool(argv, env)`
     is `async with tool(argv, env) as h: rc = await h.exited`, and after
     the block `CompletedProcess(argv, rc, h.stdout, h.stderr)`;
     `Harness.run_tool` becomes a call to it with `RPC_Host` set and
     keeps its shields. A module-level `deadline(seconds, what, on_expiry=None)`
     only cancels and raises, unchanged in substance; on an expiry the
     note sits on the cancellation, which is the `TimeoutError`'s implicit
     context, and pytest prints it. The comment at harness.py:105–108 is
     corrected: Isabelle's `bash_process` calls `setsid`, so the Isabelle
     process and the attached RPC host are never in the tool's group.
     Self-tests, unmarked, with `TERMINATION` monkeypatched down:
     (a) `bash -c 'sleep 60 & exit 0'` with no redirection must fail
     naming `sleep 60` within `TERMINATION` plus a margin, and reading
     `stdout` inside the block must raise (mutations: the check removed;
     the clean-up moved before the check; the readers gating the exit; the
     guard on the early read removed); (b) laid out as `lib/Tools/java`
     is, the command line given explicitly,
     `bash -c '"$@"; exit $?' bash <sys.executable> <child.py> <marker>`
     — the child must not be the last command, because bash execs a final
     simple command by itself — where the child installs its signal
     dispositions (SIGINT ignored), writes one fixed line to stdout and
     flushes it, and on SIGTERM writes a different fixed line to stderr,
     flushes it, sleeps briefly, writes a last fixed line to stderr and
     the marker, and exits; the test
     awaits the stdout line through `line`, asserts the layout at that
     point through the module's `/proc` listing and `running` (the
     leader's `/proc/<pid>/comm` is `bash`; the group's running processes
     are the leader and exactly one other, whose parent is the leader),
     then lets a short `deadline(...)` expire, once in each of the block's
     two waits (`h.exited`, and `h.line` on stderr for a line that never
     comes); expected: the `TimeoutError`
     reaches the caller, the marker exists, no process of the group runs,
     the formatted exception contains all three fixed lines, and `h.exited`
     still gives the leader's code after the block (mutations: `end_group`
     waiting on `exited`; the shield removed; the leader's task handed out
     unshielded; the command line without the trailing builtin, which the
     layout assertion must catch; the note not added on the exceptional
     path; the note's texts taken before the readers' join; `more()`
     awaiting a future shared by the pipe's waiters); (c) the
     readers' bound: `bash -c 'setsid sleep 60 & exit 0'` (the `sleep`
     leaves the group and holds both pipes) must fail within the readers'
     bound plus a margin, naming both pipes, and the descriptors the block
     opened are closed afterwards (mutation: thread-backed
     readers, which cancellation cannot stop); (d) a `tool` block under
     `anyio.move_on_after(0)`: the body is reached, the scope's
     cancellation is caught, and no process of the group runs afterwards
     (mutation: the start's shield removed); (e) `sleep` symlinked under a
     16-byte name the kernel cuts inside its last character: `group` lists
     it (mutation: `/proc/<pid>/stat` decoded strictly, which a name cut
     in a character makes raise for every process on the machine).
   - **Fixtures.** A session-scoped warm-up fixture, using no fakes:
     `isabelle TAT_new` on a scratch directory, `isabelle TAT_mcp` on it,
     the URL line awaited through `line` under `deadline(STARTUP, ...)`
     (900 s: a first run may build the base heap), the tool ended inside
     the block; a failure carries the tool's output, so every case errors
     at setup with the reason. `fake_clients`, session-scoped and unmarked:
     a directory holding executables `claude` and `codex` (the module
     `test/fake_agent_client.py` under `#!sys.executable`, one function per
     act; the owner let tests be decided by the author, 2026-10-13, which
     added this file to step 3's set), and an environment with that directory first
     on `PATH`; the broken-shebang `claude` sits in a directory of its own,
     which only its case puts first on `PATH`. Each fake reads its
     behaviour and its report path from environment variables the case
     sets in the `env` it passes to `tool` (the client inherits the JVM's
     environment); it writes a report (its `cwd`, `argv`, the URL read
     from the file the client reads — the one Claude Code's
     `--mcp-config` names, or `.codex/config.toml` —, the HTTP status of a
     request to that URL, every SIGINT and SIGTERM it receives, the pid of
     any child it starts), prints one fixed line to stdout, then acts as
     told. `launcher`, function-scoped on top of the warm-up and
     `fake_clients`: its name joins conftest's `HARNESSES`, so its cases
     carry the `isabelle` marker, run last, are excluded by
     `-m "not isabelle"`, and run under a deadline through the same
     `deadline(seconds, what)` method; its value exposes `deadline`, the
     environment (`RPC_Host` removed, `ISABELLE_RPC_PYTHON=sys.executable`,
     the fakes' directory first on `PATH`) and `tool`. Every tool is held
     by `async with tool(...)` (or `run_tool`) in the case body, never past
     it; a case that stops a long-running tool does so as an explicit step
     inside the block. No fixture ends groups. One helper,
     `conversation_pid(wd)`: it asserts that `<wd>/.tat/log/` holds
     exactly one directory and that that directory's first conversation
     record is `start`, and returns its `data.pid` — written under the
     lock, never cleared, the pid `tat.lock` names; the lock file itself
     is emptied on release and so is no source.
   - **Cases.** Each starts the Isabelle processes named; the whole file
     boots about eight. Every booting case ends with
     `assert not running(conversation_pid(wd))`, which cannot pass
     vacuously — at once after the client's exit, where `session.stop()`
     returns only once the attached RPC host has been terminated, and
     after a SIGTERM to the JVM or its group through one bounded wait
     (`conversation_exits`): the JVM's shutdown hooks end the Isabelle
     process and the JVM exits without waiting for the host, which exits
     on its lifeline, measured up to 0.15 s after the group (the author,
     2026-10-13, from the first run). Assertions on a tool's whole stdout or stderr are made
     after its block. A case with a controlling terminal carries no
     descendant assertion: when the tool's bash, the controlling session
     leader, exits, the kernel's hangup to the foreground group would hide
     leftovers.
     - *Claude Code* (two boots). `isabelle TAT <wd>` with the fake `claude`
       that exits 7 once a marker file appears, a pty's slave passed as
       `stdin` and `terminal`, set raw by the test before the start, and
       stdout the pipe: `foreground()` holds but stdout is not the
       terminal, so nothing is saved; the fake sets the pty to its sane
       mode while it runs, and after the block the pty is as the fake left
       it, not raw again (the pipeline regression: a save here would write
       the raw mode back). The case waits for the fake's fixed stdout line
       through `line`. While it runs: the test sends SIGINT to
       the tool's process group, and the report must record it while the
       tool keeps running; runs a second `isabelle TAT <wd>`, which must
       exit 2 with the lock's refusal (naming the conversation's pid from
       the helper) and start no client (no second report). Then the
       marker: the tool exits 7; after the block, stdout is exactly the
       fake's line and stderr's lines after the waiting line are exactly
       the `Log:` line and the URL line; the report's `cwd` is
       `<wd>/TAT.agents` and its request got an HTTP answer; afterwards
       the conversation's pid is not running and the URL refuses
       connections (deterministic: Isabelle's bash handler terminates the
       attached RPC host before `session.stop()` returns). Mutations: the
       `cwd` dropped; the client started before `TAT.serving`; stdout and
       stderr not separated; the client's exit not ending the
       conversation; the interrupt action terminating the Isabelle process
       although a client exists; the stdout check of the save removed;
       `--mcp-config` dropped from Claude Code's launch arguments.
     - *Codex* (one boot). `-c codex <wd> exec --skip-git-repo-check foo`:
       the fake `codex`'s `argv[0]` is `<fake dir>/codex` and `argv[1:]` is
       exactly `Codex_Server.launch_arguments(<agent directory>)` followed
       by `exec --skip-git-repo-check foo`; `.codex/config.toml` carries
       the URL. Folded in: the fake starts `sleep 3600`, reports its pid,
       and obeys SIGTERM 5 s after it — within the bound, and longer
       than Isabelle's own termination of the Isabelle process, which the
       JVM's other shutdown hooks run; the test finds the
       `java` process among the group's running processes through the
       same `/proc` listing and sends SIGTERM to it alone; when the group
       has exited, neither the fake's pid nor the `sleep` is running (the
       shutdown hook's `terminate()`, and the owner's unconditional sweep:
       a client that obeys SIGTERM within the bound leaves its first
       snapshot to the SIGKILL); the conversation's pid stops running
       within the bounded wait. Mutations:
       an argument altered, reordered or dropped; the sweep made
       conditional on the bound; SIGKILL sent to the client alone;
       `terminate()` reduced to `destroy()`; the hook's body not calling
       `terminate()` (the JVM then halts once Isabelle's hooks are done,
       the fake still in its 5 s and the `sleep` beside it, both left in
       the group — re-review J1 had the fake obeying at once and the
       mutation "caught independently of timing", but a client ended that
       fast is ended by the wait's `finally` as well: `Session.Terminated`
       enters the record before the JVM halts; the author, 2026-10-13,
       from the first mutation run, where that mutation was missed).
     - *The conversation ends first* (one boot; no controlling terminal).
       Before its MCP session the fake `claude` starts
       `sh -c 'sleep 3600 & echo $! > <file>; wait'` with inherited
       stdio; it then opens its MCP session as Claude Code does,
       `initialize` with a `clientInfo` version below `measured_version`,
       then `notifications/initialized`, then `tools/list`; it appends a
       `warning` record to its conversation's log file and waits a second
       before `tools/list`; its SIGTERM handler writes a marker line to
       stderr, SIGKILLs that `sh` (which orphans the grandchild), starts a
       second `sleep 3600`, reports both pids, and goes on ignoring the
       signal. Expected: the refusal ends the conversation; the tool ends
       the client (SIGTERM, then SIGKILL after the bound); after the
       block, stderr shows, in order, the URL line, the marker line, the
       refusal, and no `###` line anywhere; exit 2; neither `sleep` is
       running; the conversation's pid is not running. Mutations: the
       conversation's end not ending the client; the messages printed
       before the client is ended; no bound on the wait; the check in
       `warning` removed; SIGKILL to the client alone; the snapshot before
       SIGTERM dropped; the snapshot at the bound dropped.
     - *The terminal* (one boot): a pty's slave passed as `stdin`, `stdout`
       and `terminal`; the fake `claude` sets raw mode and exits on its
       own with a fixed code, so the restore runs after a client already
       gone (re-review R2; the restore after a client the tool ended is
       step 4's probe).
       Expected: the tool exits with that code, after the block the
       pty's attributes are restored, and the pty received the client's
       line followed by exactly §1.3's sequence. Here
       the tool's bash leads the session and the group and is the JVM's
       parent, so the parent, group and session fields of
       `/proc/self/stat` coincide and the case cannot tell the process
       group from the session; the probe of step 4 does. Mutations: the
       restore dropped; the restore moved inside the `isAlive` guard; the
       foreground group read from the wrong field
       (the field before or after `tpgid`); the sequence not written,
       written outside the condition, written to stderr.
     - *The client cannot be started* (one boot): the broken-shebang
       `claude`, which the `PATH` check finds; a pty's slave passed as
       `terminal`, and one open `/dev/null` as both `stdin` and `stdout`,
       so that `foreground()` holds, stdout is the same file as stdin, and
       `stty -g` runs and fails. Expected: exit 2, stderr exactly the
       waiting line, the `Log:` line, the URL line and
       `*** TAT cannot start claude: <message>`, no stack trace and
       nothing from `stty`; the conversation's pid not running. Mutations:
       the start's failure escapes the handler (the case then hits its
       deadline); `stty`'s stderr inherited.
     - *`isabelle TAT_mcp <wd>` without `-p`* (one boot): the URL line,
       read through `line`, carries a port that is not 8191; then SIGTERM
       to the group, the supervisor rule of §2.2; the block's normal exit
       is the contract's group check, and the conversation's pid stops
       running within the bounded wait. Nothing is asserted about output
       after the SIGTERM.
     - *Refusals that start no Isabelle process* (synchronous, unmarked,
       on `fake_clients`): `-c other` exits 2 with
       `*** TAT doesn't know the agent client other` and creates nothing;
       `isabelle` invoked by its absolute path with a `PATH` holding no
       `claude` — its entries including one with an apostrophe, one that
       is literally `$TAT_UNDEFINED/bin`, and an empty one (the case's
       current directory holds no `claude`) — exits 2 with exactly
       `*** TAT cannot find claude on the path` and creates nothing
       (skipped when no such `PATH` can be built; mutation: the lookup done
       through Isabelle's `Path`); no argument, and `-x` followed by a
       fresh path, each exit 2 with empty stdout and
       `*** Usage: isabelle TAT` on stderr and create nothing (mutation:
       drop `internal = true`); `-o parallel_proofs=3 -P Some.Plugin <wd>`
       exits 2 at `launch`'s refusal, the `plugins` table holds the name,
       no client ran; `TAT` joins `test_a_path_with_a_bracket_is_refused_by_every_tool`,
       all four tools run with `fake_clients`' environment, the same
       assertions (mutation: `TAT` builds its own `Path` instead of
       calling `working_directory`).
   Mutation checks are run as the memory rule says: the implementation
   broken in the way a test guards, the test must fail.
4. **Measurements and checks by hand**, recorded under `ai-artifacts/probes/`.
   Every probe starts the client by the absolute path §2.2 step 1 resolves
   (here `~/.local/bin/claude` and `/usr/bin/codex`, both symbolic links),
   never by its bare name.
   - Before step 2: the terminal under a Scala tool's child started with
     `inheritIO()`: Claude Code's and Codex's interfaces render and take
     input; a Ctrl-C reaches the client (the interface shows it; the TUI
     receives the key); Ctrl-Z and `fg` under Codex; after SIGTERM, and in
     a separate run SIGKILL, to a client started by any parent with
     inherited I/O: `stty -a` afterwards, whether the terminal is back on
     the main screen, whether the cursor shows, whether Ctrl-C interrupts
     `cat -v` rather than printing an escape sequence, the terminal
     emulator and its version, which of the client's processes survive
     (on this machine `/usr/bin/codex` is a Node wrapper that spawns the
     native binary), and each client's time from SIGTERM to its exit
     (against `CLIENT_BOUND`); after SIGTERM to the tool's process group
     and after a closed terminal, no `java`, `poly`, python, `claude` or
     `codex` process of the conversation survives. If a real client leaves
     escape-sequence modes behind after SIGTERM, the record goes to the
     owner, whose ruling (2026-10-13) is §1.3.
   - Before step 3: the Codex project trust (§4.3): a fresh `CODEX_HOME`
     with no `projects` entry and a fresh working directory; `codex exec`
     with the override and a prompt that calls a TAT tool, and a negative
     control without it, with the exact argv the launcher builds (the
     launch arguments before `exec`); and the interactive probe runs Codex
     with exactly its launch arguments and no subcommand, recording
     whether the flag is accepted there, whether the folder-consent prompt
     is gone (the user-visible change), and Codex's own refusal when the
     flag is repeated.
   - After step 3: in an interactive Claude Code session and an
     interactive Codex session started by `isabelle TAT`, the settings
     `configure` writes are in force (the MCP entry, the hooks, the
     sandbox: a TAT tool call is served, the `PreToolUse` hook runs, the
     settings' `env` reaches the hook's process); Claude Code's
     folder-trust prompt appears once; a conversation ended first by
     killing the Isabelle process from another terminal leaves the
     terminal with the observations above and the messages of the
     conversation's end legible, under each client; `claude -p` under the
     tool: stdout is the answer alone; the terminal's condition (§1.3):
     from an interactive shell, a foreground `isabelle TAT` whose fake
     client sets raw mode and ignores SIGTERM, with the conversation
     ending first, `stty -a` afterwards equal to `stty -a` before (this
     is what tells the process group from the session, which the terminal
     case cannot); a `&` run of `isabelle TAT WD -p ...` and of
     `-c codex WD exec ...` from an interactive shell, a Ctrl-Z then `bg`
     then the client's exit, and a group SIGTERM to a foreground run and
     `kill %1` on a background run under an interactive shell made a
     child subreaper, each showing no "Stopped (tty output)", the client's
     code (or 143), no `java`, `poly` or python process of the
     conversation left, and `stty -a` unchanged; the pipeline:
     `isabelle TAT WD -p … | less`, quit `less` before the answer, then
     Ctrl-C, then `stty -a` unchanged; optionally, under Codex, whether a
     job an agent put in the background survives a conversation that ends
     first; optionally, the hook process's `LD_LIBRARY_PATH` and current
     directory under each client, for §1.14's record.

## 7. Order of commits

One commit per step 1–3, naming exactly its step's "Files:" line, after
its "Gate:" line passed, with its tests and document hunks; the probes'
records are not committed.
