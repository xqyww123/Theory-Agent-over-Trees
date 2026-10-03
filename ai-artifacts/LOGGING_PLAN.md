# The log: draft of `docs/LOGGING.md`

Status: draft for the owner. What the owner decided is in
LOGGING_DECISIONS.md; everything else here is the author's proposal, and
§8 lists what waits for the owner. Nothing here is in `docs/` yet.

## 1. What it is

TAT's log is a record of what one conversation did: one directory per
conversation, one JSON-lines file per category, one line per event,
appended as the event happens. It is for whoever examines a conversation
afterwards or watches it run. No agent reads it and nothing TAT answers
depends on it.

The model's own words are not in it: TAT does not drive the model, and they
are in the client's transcript. A record written during a tool call carries
the client's id of that call, which the transcript carries too, so the two
join exactly.

## 2. Where

```
<working directory>/.tat/log/<start of the conversation, UTC>/
    conversation.jsonl   tool.jsonl        hook.jsonl
    agent.jsonl          edit.jsonl        evaluation.jsonl
    job.jsonl            round_trip.jsonl  store.jsonl
    isabelle.jsonl
```

`isabelle.jsonl` is written by the Isabelle side; the Python side writes
the others.

The directory is named by the conversation's start, `2026-10-01T07-24-05Z`;
a file exists once its category has a record. TAT deletes none of it.

The directory is created right after the working directory's lock is taken
and before the database is opened, so every later step of the start is
recorded and a refused start writes nothing into a running conversation's
log. A directory that cannot be created is a `TAT_StartupError`,
`TAT cannot write its log under <working directory>: <strerror>`.

## 3. A record

```json
{"ts":"2026-10-01T07:24:05.039123Z","seq":412,"category":"agent","event":"compaction",
 "level":"info","agent":"a3f9c1","call":"toolu_01Hx…","data":{"learned_from":"compact_boundary","uuid":"…"}}
```

| field | |
| --- | --- |
| `ts` | when the record was written, UTC, microseconds |
| `seq` | the record's number among those the Python side wrote in the conversation, counted across its files; it orders them exactly where two share a `ts`. The Isabelle side's records have none |
| `category` | the file's name |
| `event` | what happened, one of the category's events (§4) or `note` |
| `level` | `debug`, `info`, `warning` or `error` (below) |
| `agent` | the agent the record was written for, as its client names it — Claude Code's `agent_id`, Codex's thread id, `main` for Claude Code's main conversation; absent when the record belongs to no agent |
| `call` | the client's id of the tool call the record was written during; absent outside one |
| `data` | the event's own fields |

`agent` and `call` are set once, where a tool call's body and a hook
request begin, and every record written under them carries them; a
construction job's run carries those of the `construct` that started it.
The Isabelle side knows neither, and its records carry neither.

**Levels.** `info` is the ordinary record. `debug` is detail one reads only
when hunting something: a `note`, the reading of a transcript. `warning` is
an alarm: TAT saw something it does not expect and went on. `error` is what
ended the conversation. Every `warning` and `error` record has a
`data.message`, one sentence for a person. Nothing is filtered by level:
every record is written.

**`note`.** Any category takes a record with the event `note`, level
`debug`, a `message` and whatever fields its writer adds. It is what the
implementation uses freely; the named events below are the ones a reader
or a test may rely on.

## 4. Categories and events

### `conversation`

| event | level | data |
| --- | --- | --- |
| `start` | info | TAT's version, the pid, the working directory, the port, the client's name, the Python packages |
| `store_opened` | info | the schema version, the number of nodes |
| `plugins_loaded` | info | the kinds, each with its package |
| `configured` | info | the files written for the client |
| `serving` | info | the URL |
| `client_connected` | info | the `clientInfo` of the MCP `initialize`: name, version |
| `client_refused` | error | the same, and `message`: the version or the name that refused it; on Codex also a sandbox policy that is not TAT's |
| `ending` | info or error | what ended the conversation: its class, `message`, the traceback; `info` when the connection went, `error` otherwise |
| `ended` | info | the construction jobs cancelled, the evaluation jobs dropped, the calls cancelled, how long the unwinding took |

### `tool`

| event | level | data |
| --- | --- | --- |
| `call` | info | the tool, the arguments as received |
| `result` | info | the tool, `is_error`, the body's text, the messages delivered with it, the trailer, the `TAT_Error`'s class when there is one, the duration |
| `unannounced` | error | the tool, the call's `_meta`, `message` |
| `while_ending` | info | the tool: a call answered with the ending's line |

### `hook`

| event | level | data |
| --- | --- | --- |
| `request` | info | the payload as received |
| `answer` | info | what the request was judged to be — `announcement`, `interruption`, `stop`, `compaction`, `session_start`, `ignored` — the status, the body answered, the duration |

### `agent`

| event | level | data |
| --- | --- | --- |
| `created` | info | the client's identity for it, whether it is the main conversation, what first reached TAT — a call or a hook |
| `transcript_read` | debug | Claude Code: the file, the offset read from, the bytes, the complete lines, the boundaries found |
| `compaction` | info | how TAT learned of it — `compact_boundary` with its `uuid`, `transcript_path_changed` with both paths, `session_start` with its `source`, `post_compact` — and the size of the seen set cleared |
| `seen` | debug | a key added to the seen set |
| `check_failed` | warning | which check — a boundary older than the agent's previous announcement, a `PostCompact` no boundary answers, a prompt sent again — its facts, `message` |
| `stop_judged` | info | allowed or blocked; when blocked, what stands |
| `interruption_judged` | info | allowed or denied; when denied, the agents that hold work |

### `edit`

| event | level | data |
| --- | --- | --- |
| `committed` | info | the operation, the parent and index, the nodes created (id, kind), removed, moved; the trees invalidated because their name or imports changed |

A refused edit is a `tool` `result` with its `TAT_Error`.

### `evaluation`

| event | level | data |
| --- | --- | --- |
| `walk_started` | info | the destination, `ignore_error`, `evaluate`, `checks` |
| `operation` | info | the node, which operation — its own, its beginning, its ending — whether it ran, the status written, the messages, the duration |
| `stopped` | info | the node, and why: an obstacle, the order constraint, an import with no theory value |
| `walk_ended` | info | `continue` or the stop, the slots released, the duration |

### `job`

| event | level | data |
| --- | --- | --- |
| `construction_started` | info | the node, the owner |
| `construction_settled` | info | the node, the outcome; `FAILED`'s message |
| `construction_cancelled` | info | the node, the reason: `NODE_DELETED`, `NODE_AMENDED`, `CONTEXT_CHANGED`, or none for `cancel_construct` and the ending |
| `evaluation_started` | info | the node, the job's id, the starter |
| `evaluation_reported` | info | the id, the outcome, the errors |
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
| `round_trip` | info | the callback's name, its arguments, its result or the error, the duration |
| `connection_lost` | info | the connection error |

### `isabelle`

Written by the Isabelle side: what the Python side cannot see.

| event | level | data |
| --- | --- | --- |
| `callback` | info | the callback's name, how long it ran on the Isabelle side, whether it answered, raised or was interrupted |
| `theory_loaded` | info | a library theory loaded from source: its name, the duration |
| `job_forked` | info | an evaluation job's id |
| `job_ended` | info | the id, the errors, the duration; whether it was cancelled |
| `report_undelivered` | warning | the id, the failure, `message` |
| `reset` | info | the futures cancelled, the slots and theories cleared |
| `bug` | error | a `TAT_Framework.Bug` raised: its message |

### `store`

| event | level | data |
| --- | --- | --- |
| `transaction` | info | the rows written (node, field), the nodes deleted, the duration |
| `transaction_failed` | error | what failed; the `TAT_DisasterError` follows in `conversation` |

## 5. Writing

One object, `Log`, in `log.py`, held by the `Conversation`: a Python
process may host several conversations, so nothing is configured for the
process. One attribute per category; each event is a method of its
category's attribute, whose parameters are the event's fields, and every
category has `note(message, **fields)`, the free one. The method stamps
`ts`, `seq`, `agent` and `call`, encodes the line and appends it with one
write, flushed.

The named events are written where the design already funnels everything,
so that none can be bypassed: the tool boundary and the `/hook` path in
`mcp_server.py`; `isabelle_driver.call`, which every round trip goes
through; the status setters of `model.py`, which every write of an
evaluation status goes through; `Forest_Store.transaction`; the edit's
commit block; the ending object; a job's `start`, settlement, `cancel`
and drop; the mailbox's post and delivery.

A node class writes through the same object, reached as
`forest().conversation.log`.

The Isabelle side appends to `isabelle.jsonl` itself, with `File.append`
under one lock, since several Future tasks may write at once; it encodes
its lines with a JSON string function of TAT's own, Isabelle/ML having
none. The directory is the Python side's to name, so the Python side
tells it once the directory exists, through the framework callback
`TAT.log_directory`; records made before that are kept in memory and
written then, and are lost with a start that fails earlier, whose failure
the launcher prints anyway. `TAT.reset` forgets the directory, and the
next conversation tells its own.

A line is JSON with non-ASCII text written as it is; a lone surrogate,
which UTF-8 cannot hold, is written as its `\udXXX` escape — AoA's
`_log_meta` does the same (`contrib/Isa-Mini/IsaMini/AoA/model.py`). A
value JSON cannot hold is written as its `str`.

A write that fails after the start does not touch the conversation: the
`Log` reports the first failure to the RPC host's logger and goes on. A
`warning` or an `error` record is also sent to that logger, one line.

## 6. Reading

The whole conversation in order:
`cat <directory>/*.jsonl | jq -c -s 'sort_by(.ts, .seq)[]'`. One category while
it runs: `tail -f <directory>/tool.jsonl | jq .`. Everything one tool call
did: the records whose `call` is its id.

## 7. The three sentences that said "logged"

- CONSTRUCT_INTERACTION §8, a call no `PreToolUse` announced: the `tool`
  record `unannounced`.
- CONSTRUCT_INTERACTION §7, an agent reported gone with jobs running: an
  `agent` record of level `error`, when a client ever reports it.
- MODULE_STRUCTURE §2.4, `fork_job`: "a task whose report cannot be
  delivered logs and ends" — the `isabelle` record `report_undelivered`.

## 8. The launcher

The launcher prints every `warning` and `error` record as it is written.
It follows the files of the running conversation's directory, the
Isabelle side's included, which it finds through a third line of
`tat.lock`, written when the directory is made; at the end it reads what
is left before it prints the `TAT.finished` messages. It does not go
through Isabelle: the ML side serves one callback at a time
(`contrib/Isabelle_RPC/Tools/RPC.ML`, `dispatch_loop`), so an alarm sent
that way would wait behind the round trip in flight.

## 9. Waiting for the owner

The line the launcher prints for a record, and the wording of the
`message`s that have none yet.
