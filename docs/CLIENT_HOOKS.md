# The agent clients' hooks

Status: decided (2026-09-21); the files are written by `isabelle TAT_new`
(MODULE_STRUCTURE §5) into the working directory, and an agent started
there runs them.

Every client calls `POST /on-compaction` on TAT's server (MODULE_STRUCTURE
§4.6) when the agent's context is replaced. TAT clears the seen set
(PRINT.md §4) and answers the briefing (PRINT.md §5), shaped for the
client named by the query parameter `client`:

| `client` | answer |
| --- | --- |
| `claude-code`, `codex`, `gemini-cli` | `{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "<briefing>"}}` |
| `cursor` | `{"additional_context": "<briefing>"}` |
| `opencode`, or no parameter | the briefing as text |

The port is read at every call from `tat.lock` in the working directory,
whose second line the running conversation writes (MODULE_STRUCTURE
§4.6); the files carry no port. A hook that finds no `tat.lock` fails
with this line on its standard error and a non-zero exit:

```
TAT is not running in this directory (no tat.lock).
```

Every command hook is therefore the same command, `<client>` and the
handling of the answer apart:

```sh
test -f tat.lock || { echo 'TAT is not running in this directory (no tat.lock).' >&2; exit 1; }; curl -sSf -X POST "http://127.0.0.1:$(sed -n 2p tat.lock)/on-compaction?client=<client>"
```

`curl -sS` prints no progress and does print a failure, so a stale
`tat.lock` after a crash is reported too. A client whose hook fires only
before a compaction discards the answer with `-o /dev/null`: the seen set
is cleared all the same, and the agent's next tool result renders every
error afresh.

## Claude Code — `.claude/settings.json`

`SessionStart` fires on `startup`, `resume`, `clear` and, after a
compaction, `compact`; the hook's `additionalContext` enters the agent's
new context. No `matcher` on the group, so every source fires it.

```json
{ "hooks": { "SessionStart": [ { "hooks": [
  { "type": "command", "timeout": 10,
    "command": "test -f tat.lock || { echo 'TAT is not running in this directory (no tat.lock).' >&2; exit 1; }; curl -sSf -X POST \"http://127.0.0.1:$(sed -n 2p tat.lock)/on-compaction?client=claude-code\"" } ] } ] } }
```

## Codex — `.codex/hooks.json`

The same events and sources. `additionalContextLimit` is the size in
tokens above which Codex keeps only the beginning of the answer.

```json
{ "hooks": { "SessionStart": [ { "hooks": [
  { "type": "command", "timeout": 10, "additionalContextLimit": 20000,
    "command": "test -f tat.lock || { echo 'TAT is not running in this directory (no tat.lock).' >&2; exit 1; }; curl -sSf -X POST \"http://127.0.0.1:$(sed -n 2p tat.lock)/on-compaction?client=codex\"" } ] } ] } }
```

## Gemini CLI — `.gemini/settings.json`

`SessionStart` fires on `startup`, `resume` and `clear`; a compaction is
announced only beforehand, by `PreCompress`, whose output is not used.

```json
{ "hooks": {
  "SessionStart": [ { "matcher": "*", "hooks": [ { "name": "TAT", "type": "command",
    "command": "test -f tat.lock || { echo 'TAT is not running in this directory (no tat.lock).' >&2; exit 1; }; curl -sSf -X POST \"http://127.0.0.1:$(sed -n 2p tat.lock)/on-compaction?client=gemini-cli\"" } ] } ],
  "PreCompress": [ { "matcher": "*", "hooks": [ { "name": "TAT", "type": "command",
    "command": "test -f tat.lock || { echo 'TAT is not running in this directory (no tat.lock).' >&2; exit 1; }; curl -sSf -o /dev/null -X POST \"http://127.0.0.1:$(sed -n 2p tat.lock)/on-compaction\"" } ] } ] } }
```

## Cursor — `.cursor/hooks.json`

`sessionStart` injects `additional_context`; `preCompact` fires before a
compaction and can only observe it.

```json
{ "version": 1, "hooks": {
  "sessionStart": [ { "command": "test -f tat.lock || { echo 'TAT is not running in this directory (no tat.lock).' >&2; exit 1; }; curl -sSf -X POST \"http://127.0.0.1:$(sed -n 2p tat.lock)/on-compaction?client=cursor\"" } ],
  "preCompact":   [ { "command": "test -f tat.lock || { echo 'TAT is not running in this directory (no tat.lock).' >&2; exit 1; }; curl -sSf -o /dev/null -X POST \"http://127.0.0.1:$(sed -n 2p tat.lock)/on-compaction\"" } ] } }
```

## OpenCode — `.opencode/plugins/tat.js`

OpenCode has plugins instead of hook files. There is no injection point at
a session's start; `experimental.session.compacting` runs before the
summary is written and takes text for the summary's prompt, so the summary
carries the forest's state.

```js
const port = async () => {
  const lock = Bun.file("tat.lock")
  if (!(await lock.exists())) throw new Error("TAT is not running in this directory (no tat.lock).")
  return (await lock.text()).split("\n")[1]
}
export const TAT = async () => ({
  event: async ({ event }) => {
    if (event.type === "session.created")
      await fetch(`http://127.0.0.1:${await port()}/on-compaction`, { method: "POST" })
  },
  "experimental.session.compacting": async (_input, output) => {
    const reply = await fetch(`http://127.0.0.1:${await port()}/on-compaction?client=opencode`, { method: "POST" })
    output.context.push(await reply.text())
  },
})
```

## Not verified yet

Measured when the endpoint lands: that Claude Code's `additionalContext`
reaches the context in the current version, and that a group without a
`matcher` fires on every source; that Codex and Gemini CLI take the
envelope with `hookEventName`; the project-level location of Codex's
`hooks.json`; that Gemini CLI accepts an empty standard output from the
`PreCompress` hook; that an OpenCode plugin may `fetch` a local port; what
each client shows the user when the hook exits non-zero.
