# The log

Status: decided (2026-10-02).

## 1. What it is

TAT's log is a record of what one conversation, or one compile, did: one
directory per conversation or compile, one JSON-lines file per category,
one line per event, appended as the event happens. It is for whoever
examines a conversation afterwards or watches it run. No agent reads it,
and nothing TAT answers depends on it.

The model's own words are not in it: TAT does not drive the model, and
they are in the client's transcript. A record written during a tool call
carries the client's id of that call, which the transcript carries too,
so the two join exactly.

## 2. Where

```
<working directory>/.tat/log/<the moment the directory is made, UTC>/
    conversation.jsonl   tool.jsonl        hook.jsonl
    agent.jsonl          edit.jsonl        evaluation.jsonl
    job.jsonl            round_trip.jsonl  store.jsonl
    isabelle.jsonl
```

The directory is named by the moment it is made, to the microsecond, in
the form of a record's `ts` with `-` for `:`,
`2026-10-01T07-24-05.039123Z`; a file exists once its category has a record.
`isabelle.jsonl` is written by the Isabelle side, the others by the Python
side (§5). No file holds every record: each record is written once, in its
category's file. TAT deletes no log.

The directory is created right after the working directory's lock is
taken and before the database is opened (MODULE_STRUCTURE §4.6), so every
later step of the start is recorded and a refused start writes nothing
into a running conversation's log. `.tat/log/` is made when absent, and
the directory itself exclusively, under the lock: a directory that cannot
be created, one that exists already included, is a `TAT_StartupError`,
`TAT cannot write its log under <working directory>: <strerror>`. A
compile (COMPILATION.md §1) makes its directory the same way, named by
its start, and writes there as a conversation does — on the Python side
`start`, `store_opened`, `plugins_loaded`, and `ending` and `ended` when
the compile fails; on the Isabelle side the records of its start (§5).

## 3. A record

```json
{"ts":"2026-10-01T07:24:05.039123Z","category":"agent","event":"compaction",
 "level":"info","agent":"a3f9c1","call":"toolu_01Hx…","data":{"learned_from":"compact_boundary","uuid":"…"}}
```

| field | |
| --- | --- |
| `ts` | when the record was written, UTC, microseconds; with its file it identifies the record |
| `category` | the file's name |
| `event` | what happened: one of the category's events (§4), or `note` |
| `level` | `debug`, `info`, `warning` or `error` (below) |
| `agent` | the agent the record was written for, as its client names it — Claude Code's `agent_id`, Codex's thread id, `main` for Claude Code's main conversation; absent when the record belongs to no agent |
| `call` | the client's id of the tool call the record belongs to (below); absent when it belongs to none |
| `data` | the event's own fields |

`agent` and `call` are context variables, set where a tool call's body
and a hook request begin; a task inherits them from the code that creates
it. So every record written under a call carries them, and an evaluation
job's report, which arrives from the Isabelle side on its own, carries
none. A construction job's run has an owner (ARCHITECTURE §1), and the
framework's wrapper around `_run` sets `agent` to the owner as its first
step (CONSTRUCT_INTERACTION §3.2), so the run's records name the owner
whether a `construct` or a `FAILED` report started it; `call` the run
inherits, the `construct`'s or none. The Isabelle side knows neither, and
its records carry neither.

**Levels.** `info` is the ordinary record. `debug` is detail one reads
only when hunting something: a `note`, the reading of a transcript.
`warning` is an alarm: TAT saw something it does not expect and went on.
`error` is what ended the conversation. Every `warning` and `error`
record has a `data.message`, one sentence for a person. Nothing is
filtered by level: every record is written.

**`note`.** Any category takes a record with the event `note`, level
`debug`, a `message` and whatever fields its writer adds. The
implementation uses it freely; the named events of §4 are the ones a
reader or a test may rely on.

Arguments, results and payloads are recorded whole, never cut.

## 4. Categories and events

### `conversation`

| event | level | data |
| --- | --- | --- |
| `start` | info | TAT's version, the pid, the working directory, the Python packages; for a conversation also the port and the client's name |
| `store_opened` | info | the schema version, the number of nodes |
| `plugins_loaded` | info | the kinds, each with its package |
| `configured` | info | the files written for the client |
| `serving` | info | the URL |
| `client_connected` | info | the `clientInfo` of the MCP `initialize`: name, version |
| `client_refused` | error | the same, and `message`: what refused it (CONSTRUCT_INTERACTION §8); the call's `_meta` when a call's sandbox policy did |
| `ending` | error | what ended the conversation: its class, `message`, the traceback |
| `ended` | info | written by the ending object's exit once the unwinding is over (MODULE_STRUCTURE §4.6): how long the unwinding took; each call's and each job's fate is in its own record; a compile that returns normally writes neither `ending` nor `ended` |

An RPC host that the Isabelle process started — the default; not one
started elsewhere under `RPC_Host` (ARCHITECTURE §9) — exits as soon as
that process goes (`contrib/Isabelle_RPC`, its lifeline). So the usual
end, the manager's SIGTERM or an interrupt at the terminal, leaves no
`ended`, and the log stops where the conversation stood.

### `tool`

| event | level | data |
| --- | --- | --- |
| `call` | info | the tool, the arguments as received |
| `result` | info | the tool, `is_error`, the body's text, the messages delivered with it, the trailer, the `TAT_Error`'s class when there is one, the duration |
| `given_up` | info | the tool, the text the body produced — when it produced one — the messages that would have gone with it, the duration: the body finished after its client had given up on the call, and nobody received the answer (MODULE_STRUCTURE §4.6) |
| `unannounced` | error | the tool, the call's `_meta`, `message` (CONSTRUCT_INTERACTION §8) |
| `while_ending` | info | the tool: a call answered with the ending's line |

### `hook`

| event | level | data |
| --- | --- | --- |
| `request` | info | the payload as received |
| `answer` | info | what the request was judged to be — `announcement`, `interruption`, `stop`, `compaction`, `session_start`, `ignored` — absent when it was not judged, answered 503 while the conversation is ending or 500 on a bug of the path; the status, the body answered, the duration |

### `agent`

| event | level | data |
| --- | --- | --- |
| `created` | info | the client's identity for it, whether it is the main conversation, what first reached TAT — a call or a hook |
| `transcript_read` | debug | Claude Code: the file, the offset read from, the bytes, the complete lines, the boundaries found |
| `compaction` | info | how TAT learned of it — `compact_boundary` with its `uuid`, `transcript_path_changed` with both paths, `session_start` with its `source`, `pre_compact`, `post_compact` — and the size of the seen set cleared |
| `seen` | debug | a key added to the seen set |
| `check_failed` | error | a compaction check failed (CONSTRUCT_INTERACTION §8): which check, its facts, `message`; TAT ends the conversation with a `TAT_InternalError` carrying the message, which the launcher prints |
| `stop_judged` | info | allowed or blocked; when blocked, what stands |
| `interruption_judged` | info | allowed or denied; when denied, the agents that hold work |
| `left_with_jobs` | error | the agent, its jobs, `message` (CONSTRUCT_INTERACTION §7) |

### `edit`

| event | level | data |
| --- | --- | --- |
| `committed` | info | the operation, the parent and index, the nodes created (id, kind), removed, moved; the trees invalidated because their name or imports changed |

A refused edit is a `tool` `result` with its `TAT_Error`.

### `evaluation`

| event | level | data |
| --- | --- | --- |
| `walk_started` | info | the destination, `ignore_error`, `checks` |
| `operation` | info | the node, which operation — its own, its beginning, its ending — whether it ran, the status written with its `messages` (ARCHITECTURE §3.2; an empty list for a clean run; absent when no run produced the write), the duration |
| `stopped` | info | the node, and why: its own command failed (a stop, ARCHITECTURE §3.3), the order constraint, an import with no theory value — then also the importing tree, which was not run |
| `walk_ended` | info | `continue` or the stop, the slots released, the duration |

### `job`

| event | level | data |
| --- | --- | --- |
| `construction_started` | info | the node, the owner |
| `construction_settled` | info | the node, the outcome; `FAILED`'s message |
| `construction_cancelled` | info | the node, the reason: `NODE_DELETED`, `NODE_AMENDED`, `CONTEXT_CHANGED`, or none for `cancel_construct` and the ending |
| `evaluation_started` | info | the node, the job's id, the starter |
| `evaluation_reported` | info | the id, the outcome, the failure the report carried |
| `evaluation_dropped` | info | the id, what dropped it: a status write, a delete, an amend, a construction starting, another job attached, the ending |
| `report_ignored` | info | the id of a job no longer on its node |
| `cancel_sent` | info | the ids sent to `TAT.job_cancel` |
| `message_posted` | info | the recipient, notification or question, what it comes from, whether it interrupts, the text |
| `message_delivered` | info | the recipient |
| `message_dropped` | info | the recipient, why delivery dropped it |
| `question_answered` | info | the node; accepted, refused with `BadAnswer`, or replaced by another question |
| `question_withdrawn` | info | the node |

### `round_trip`

| event | level | data |
| --- | --- | --- |
| `round_trip` | info | the callback's name, its arguments, its result or the error — the connection error, when the connection went — the duration |

### `store`

| event | level | data |
| --- | --- | --- |
| `transaction` | info | the rows written (node, field), the nodes deleted, the duration |
| `transaction_failed` | error | what failed; the `TAT_DisasterError` follows in `conversation` |

### `isabelle`

Written by the Isabelle side: what the Python side cannot see.

| event | level | data |
| --- | --- | --- |
| `callback` | info | the callback's name, how long its function ran, whether it returned, raised or was interrupted |
| `theory_loaded` | info | a library theory loaded from source: its name, the duration |
| `job_forked` | info | an evaluation job's id |
| `job_ended` | info | the id, the failure reported, the duration; whether it was cancelled |
| `report_undelivered` | warning | the id, the failure that went unreported, `message`: `The result of evaluation job <id> could not be reported to the Python side: <reason>` — the reason the report could not be delivered |
| `reset` | info | the futures cancelled, the slots and theories cleared |
| `bug` | error | a `TAT_Framework.Bug` that left a callback or an evaluation job's work: its message |

## 5. Writing

**The Python side.** One object, `Log`, in `log.py`, held by the
`Conversation`: a Python process may host several conversations
(ARCHITECTURE §9), so nothing is configured for the process. It has one
attribute per category, mirroring the files; each event is a method of
its category's attribute, whose parameters are the event's fields
(`log.tool.call(...)`), and every category has `note(message, **fields)`,
the free one. The method stamps `ts`, `agent` and `call`,
encodes the line and appends it: it opens the category's file for
appending (`open(path, "ab")`), writes the line, which is written whole
or raises, and closes the file. The `Log` therefore holds no open file
and is never closed, and a record written after `ended` is appended like
any other.

Every writer reaches the `Log` through the `Conversation`.
`isabelle_driver.call` and `Isar_State_Slot` take the `Conversation`,
which holds the connection too; the store and the ending object are given
the `Log` when they are built; everything else, a node class included,
reaches it as `forest().conversation.log`. `isabelle_driver.reset` alone
runs on a bare connection, before any `Conversation` exists
(MODULE_STRUCTURE §4.3): only the test harness calls it, between
conversations, and the Python side records it nowhere.

The named events are written where the design already funnels everything,
so that none can be bypassed: the tool boundary and the `/hook` path in
`mcp_server.py`; `isabelle_driver.call`, which every round trip of a
conversation goes through, and which writes `round_trip` from the trip's
completion callback, so whether or not its caller still waits;
the status setters of `model.py`, which
every write of an evaluation status goes through, and which are handed
the duration of the hook that ran, or none; `Forest_Store.transaction`;
the edit's commit block; the ending object; a job's `start`, settlement,
`cancel` and drop; the mailbox's post and delivery.

A line is JSON with non-ASCII text written as it is; a lone surrogate,
which UTF-8 cannot hold, is written as its `\udXXX` escape, as AoA's
`_log_meta` does (`contrib/Isa-Mini/IsaMini/AoA/model.py`). An `IsaTerm`
is written as its `.unicode`, the stored spelling; any other value JSON
cannot hold as its `str`. Encoding and writing run under one guard, so a
value that will not encode is a record that cannot be written (below),
never an exception at the writer.

A record that cannot be written after the start, on either side, does
not touch the conversation. The `Log` reports the Python side's first
failure to the RPC host's logger (`connection.server.logger`) —
`TAT could not write its log file <path>: <strerror>. Later failures are not reported.`
— and goes on. The Isabelle side drops the record and reports nothing:
it writes into the same directory, so what stops it stops the Python
side too. A `warning` or an `error` record of the Python side is also
sent to that logger, one line.

**The Isabelle side** appends to `isabelle.jsonl` itself, encoding its
lines with a JSON string function of TAT's own, Isabelle/ML having none.
Every record goes through one function that never raises: the lock —
several Future tasks may write at once — and the append run with
interrupts deferred and every exception captured, as
`Event_Log.append_string` does
(`contrib/Performant_Isabelle_ML/library/event_log.ML`), out of which
the function is factored. So no record changes what a callback answers,
which exception unwinds, or whether `fork_job`'s report is sent. The
records `callback` and `bug` of a callback are written by the wrapper
the framework puts around every callback's function (MODULE_STRUCTURE
§2.5); `job_forked`, `job_ended`, `report_undelivered` and a job's `bug`
by `fork_job` (§2.4); `theory_loaded` by the loader (§2.3); `reset` by
`TAT.reset` (§2.6).

The Isabelle side's log is a value that belongs to one conversation: it
holds the records made so far, in memory, or, once told, the directory.
One cell of the process holds the current one, an empty log from the
moment `TAT_Framework.ML` is loaded, so the theories `TAT.start` loads
before the conversation begins are recorded; the callback wrapper, the
loader and `TAT.log_directory` act on what the cell holds, `TAT.reset`
writes its `reset` record into the old log and then installs a fresh one,
and a job keeps the log it found at its fork.
The directory is the Python side's to name, so the Python side tells it
once the directory exists — its absolute path, through the framework
callback `TAT.log_directory` (MODULE_STRUCTURE §2.6); the records held are written
then, and are lost with a start that fails earlier, whose failure the
launcher prints. `TAT.reset` begins a fresh log for the next
conversation, which tells its own directory; an evaluation job writes
into the log current when it was forked, so a job that `TAT.reset`
cancels ends in its own conversation's log. A compile tells it the
directory too, `TAT.log_directory` being the one framework callback its
command carries (COMPILATION.md §5).

## 6. Reading

Every reader of a log file, the launcher included, reads it line by line
and skips a line that is not JSON: a file may end in a line that was
being written when the process died. The whole conversation in order:

```sh
for f in <directory>/*.jsonl; do jq -c . "$f" 2>/dev/null; done | jq -c -s 'sort_by(.ts)[]'
```

One category while it runs: `tail -f <directory>/tool.jsonl | jq .`.
Everything one tool call did: the records whose `call` is its id.

## 7. The launcher

When the Python side tells the Isabelle side the log directory (§5), the
Isabelle side passes its absolute path on to the launcher, as the
protocol message `TAT.log_directory`, sent the way `TAT.finished` is
(MODULE_STRUCTURE §2.6); a later one, after `TAT.reset`, moves the
launcher to the next conversation's directory; `TAT_compile` receives it
for a compile's log too, and follows the directory as `TAT_mcp` does
(COMPILATION.md §5). On the message the launcher
prints the path as carried,

```
Log: <the directory's absolute path>
```

and from then on follows the directory's files, the Isabelle side's
included, printing each `warning` record as it is written:

```
### <message> (agent.jsonl, 07:24:05.039123Z)
```

At the end it reads what is left, then prints the messages `TAT.finished`
carried (MODULE_STRUCTURE §5). An `error` record is not followed: it is
what ended the conversation, which those messages say.
