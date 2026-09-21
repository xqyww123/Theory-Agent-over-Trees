# The agent clients' hooks

Status: decided (2026-09-21). `isabelle TAT_new` (MODULE_STRUCTURE §5)
writes into the working directory one script, `.tat/on-compaction.sh`,
and one hook file per client that calls it. An agent started in the
working directory runs them; they need a POSIX shell, `curl` 7.76 or
newer (`--fail-with-body`, March 2021), and the working directory as the
hook's current directory.

Every client calls `POST /on-compaction` on TAT's server (MODULE_STRUCTURE
§4.6) when the agent's context is replaced. TAT clears the seen set
(PRINT.md §4) and answers the briefing (PRINT.md §5), shaped for the
client named by the query parameter `client`:

| `client` | answer |
| --- | --- |
| `claude-code`, `codex`, `gemini-cli` | `{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "<briefing>"}}` |
| `cursor` | `{"additional_context": "<briefing>"}` |
| `opencode`, or no parameter | the briefing as text |

## An unknown client

A `client` outside the table is refused with status 400 and one line,
before anything is touched — here for `emacs`:

```
TAT does not know the client `emacs`; it knows claude-code, codex, gemini-cli, cursor and opencode
```

## The script — `.tat/on-compaction.sh`

```sh
#!/bin/sh
# Written by `isabelle TAT_new`; the agent clients' hooks call it (docs/CLIENT_HOOKS.md).
not_running() { echo 'TAT is not running in this directory.' >&2; exit 1; }
pid=$(sed -n 1p tat.lock 2>/dev/null)
port=$(sed -n 2p tat.lock 2>/dev/null)
{ [ -n "$port" ] && kill -0 "$pid" 2>/dev/null; } || not_running
if [ $# -eq 0 ]
then curl -sS --fail-with-body -o /dev/null -X POST "http://127.0.0.1:$port/on-compaction"
else curl -sS --fail-with-body -X POST "http://127.0.0.1:$port/on-compaction?client=$1"
fi
rc=$?
[ $rc -eq 7 ] && not_running
exit $rc
```

Called with the client's name it prints TAT's answer for that client;
called with none it discards the answer, for a hook that fires only
before a compaction: the seen set is cleared all the same, and the
agent's next tool result renders every error afresh.

`tat.lock` is written by the conversation, its pid on the first line when
it takes the lock and its port on the second once the server is
listening, and cleared on release (MODULE_STRUCTURE §4.6): a conversation
that ended leaves the file present and empty, or — when its Python
process was killed, as a Ctrl-C in the terminal kills it — still holding
the dead process's pid and port. The script fails the same way for an
absent file, an emptied one, the moment before the port is written, a
pid that is no longer alive, and a port nothing accepts on (`curl`'s
exit 7: a conversation still starting or already ending, or a recycled
pid), with this line on its standard error and a non-zero exit:

```
TAT is not running in this directory.
```

`curl -sS` prints no progress and does print a failure; `--fail-with-body`
keeps the unknown client's line readable.

## Claude Code — `.claude/settings.json`

`SessionStart` fires on `startup`, `resume`, `clear` and, after a
compaction, `compact`; the hook's `additionalContext` enters the agent's
new context. No `matcher` on the group, so every source fires it.

```json
{ "hooks": { "SessionStart": [ { "hooks": [
  { "type": "command", "timeout": 10, "command": "sh .tat/on-compaction.sh claude-code" } ] } ] } }
```

## Codex — `.codex/hooks.json`

The same events and sources. `additionalContextLimit` is the size in
tokens above which Codex keeps only the beginning of the answer.

```json
{ "hooks": { "SessionStart": [ { "hooks": [
  { "type": "command", "timeout": 10, "additionalContextLimit": 20000, "command": "sh .tat/on-compaction.sh codex" } ] } ] } }
```

## Gemini CLI — `.gemini/settings.json`

`SessionStart` fires on `startup`, `resume` and `clear`; a compaction is
announced only beforehand, by `PreCompress`, whose output is not used, so
that hook discards the answer.

```json
{ "hooks": {
  "SessionStart": [ { "matcher": "*", "hooks": [ { "name": "TAT", "type": "command", "command": "sh .tat/on-compaction.sh gemini-cli" } ] } ],
  "PreCompress": [ { "matcher": "*", "hooks": [ { "name": "TAT", "type": "command", "command": "sh .tat/on-compaction.sh" } ] } ] } }
```

## Cursor — `.cursor/hooks.json`

`sessionStart` injects `additional_context`; `preCompact` fires before a
compaction and can only observe it, so that hook discards the answer.

```json
{ "version": 1, "hooks": {
  "sessionStart": [ { "command": "sh .tat/on-compaction.sh cursor" } ],
  "preCompact":   [ { "command": "sh .tat/on-compaction.sh" } ] } }
```

## OpenCode — `.opencode/plugins/tat.js`

OpenCode has plugins instead of hook files, and hands a plugin Bun's
shell, `$`. There is no injection point at a session's start;
`experimental.session.compacting` runs before the summary is written and
takes text for the summary's prompt, so the summary carries the forest's
state. `$` throws on a non-zero exit, so the plugin fails as the shell
hooks do, with the script's line.

```js
export const TAT = async ({ $ }) => ({
  event: async ({ event }) => {
    if (event.type === "session.created") await $`sh .tat/on-compaction.sh`.quiet()
  },
  "experimental.session.compacting": async (_input, output) => {
    output.context.push(await $`sh .tat/on-compaction.sh opencode`.text())
  },
})
```

## Not verified yet

Measured (2026-09-21, a real conversation): the script reaches the
endpoint through `tat.lock`, every client's shape comes back as the table
says, the no-argument call discards, an unknown client's refusal is
readable, and the three failure paths print the line above. Not yet
measured, with the clients themselves: that Claude Code's
`additionalContext` reaches the context in the current version, and that
a group without a `matcher` fires on every source; that Codex and Gemini
CLI take the envelope with `hookEventName`; the project-level location of
Codex's `hooks.json`; that Gemini CLI accepts an empty standard output
from the `PreCompress` hook; that an OpenCode plugin's `$` runs the script
and may reach a local port; what each client shows the user when the hook
exits non-zero; that the hooks run with the working directory as their
current directory; whether the hosts that matter carry `curl` 7.76 or
newer.
