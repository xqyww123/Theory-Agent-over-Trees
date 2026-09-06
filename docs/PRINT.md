# Rendering: `print` and `quickview`

Status: settled in outline; the renderings themselves are not yet designed.

Every node renders itself, as in AoA:

```python
def print(self, indent: int, out: TextIO) -> int      # the full rendering: fields and status, then children
def quickview(self, indent: int, out: TextIO) -> int  # a summary: one line, children compressed
```

Both return the indent for what follows, as `emit_isar` does (ARCHITECTURE
§4); the return value is kept on purpose for renderings to come. `recall`'s
two detail levels (MCP_SPECIFICATION §1.1) call one or the other; every
tool result ends with the forest's `quickview`.

The forest root renders as

```
Sessions:
- session_A
  <fields, rendered by Session.print>
- session_B
  ...
```

and, when the forest is empty, both `print` and `quickview` render

```
Sessions:
  There are no Isabelle sessions yet. Call `edit` with `{"action": "append", "target_id": "Sessions", "constructs": [{"kind": "session", ...}], "evaluate": false}` to declare one.
```

Not yet designed: what each node class prints, how statuses are marked
(`not_evaluated`, `cannot_evaluate` and its `blocked_by`, a failed
operation's errors), what a compressed child line shows, and the
framework's default renderings.
