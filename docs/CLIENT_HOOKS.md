# The agent clients' hooks

Status: decided (2026-09-21). `isabelle TAT_new` (MODULE_STRUCTURE §5)
writes into the working directory one script, `.tat/on-compaction.sh`,
and one hook file per client that calls it. An agent started in the
working directory runs them; they need a POSIX shell, `curl`, and the
working directory as the hook's current directory.

Every client calls `POST /on-compaction` on TAT's server (MODULE_STRUCTURE
§4.6) when the agent's context is replaced. TAT clears the seen set
(PRINT.md §4) and answers the briefing (PRINT.md §5), shaped for the
client named by the query parameter `client`:

| `client` | answer |
| --- | --- |
| `claude-code`, `codex`, `gemini-cli` | `{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "<briefing>"}}` |
| `cursor` | `{"additional_context": "<briefing>"}` |
| `opencode`, or no parameter | the briefing as text |

## The script — `.tat/on-compaction.sh`

```sh
#!/bin/sh
# Written by `isabelle TAT_new`; the agent clients' hooks call it (docs/CLIENT_HOOKS.md).
port=$(sed -n 2p tat.lock 2>/dev/null)
[ -n "$port" ] || { echo 'TAT is not running in this directory.' >&2; exit 1; }
if [ $# -eq 0 ]
then exec curl -sS --fail-with-body -o /dev/null -X POST "http://127.0.0.1:$port/on-compaction"
else exec curl -sS --fail-with-body -X POST "http://127.0.0.1:$port/on-compaction?client=$1"
fi
```

Called with the client's name it prints TAT's answer for that client;
called with none it discards the answer, for a hook that fires only
before a compaction: the seen set is cleared all the same, and the
agent's next tool result renders every error afresh.

The port is the second line of `tat.lock`, which the running conversation
writes and clears on release (MODULE_STRUCTURE §4.6): a finished
conversation leaves the file present and empty. The script fails the same
way for an absent file, an emptied one, and the moment before the port is
written, with this line on its standard error and a non-zero exit:

```
TAT is not running in this directory.
```

`curl -sS` prints no progress and does print a failure, so a stale port
is reported too; `--fail-with-body` keeps the line TAT answers an unknown
`client` with (MODULE_STRUCTURE §4.6) readable.

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

Measured when the endpoint lands: that Claude Code's `additionalContext`
reaches the context in the current version, and that a group without a
`matcher` fires on every source; that Codex and Gemini CLI take the
envelope with `hookEventName`; the project-level location of Codex's
`hooks.json`; that Gemini CLI accepts an empty standard output from the
`PreCompress` hook; that an OpenCode plugin's `$` runs the script and may
reach a local port; what each client shows the user when the hook exits
non-zero; that the hooks run with the working directory as their current
directory; the `curl` version that has `--fail-with-body` on the hosts
that matter.
