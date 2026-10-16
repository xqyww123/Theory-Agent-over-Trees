# Codex sees `edit`'s constructs: plan

Status: decisions taken by the owner 2026-10-15/16 (§1). Revision 3,
after a two-turn adversarial review, the owner's rulings on its three open
points, and a focused re-review that cleared it to start (2026-10-16); not
yet implemented.

## 0. The problem

Codex renders each MCP tool's input schema as a TypeScript declaration
for the model. TAT's `edit` schema is shown as `constructs:
Array<unknown>`: no node kind, no field. Three limits are involved (Codex
source `codex-rs/code-mode-protocol/src/json_schema_types.rs`, and
measurement, scratchpad `codex_schema/`):

- the schema's JSON size: above `mcp_servers.<name>.tool_input_schema_max_bytes`
  bytes (default 5,000; the setting is new in 0.163.0) Codex compacts the
  schema before rendering;
- the rendered declaration's size (16,000 by default; per Codex source the
  same setting also sets this limit, which §6 measures); past it the whole
  input becomes `unknown`;
- `$ref` expansions, fixed constants no setting changes: at most 2 along
  one path and 32 in one schema; past either, the renderer writes
  `unknown`.

| Codex | today's schema | `children` replaced (§3), `$ref`s kept |
|---|---|---|
| 0.156.1 | `Array<unknown>` | `Array<unknown>` |
| 0.163.0, defaults | `Array<unknown>` | `Array<unknown>` |
| 0.163.0, `mcp_servers.<name>.tool_input_schema_max_bytes` raised | session and theory rendered, the other four kinds `unknown` (32 expansions spent) | all six kinds rendered, no `unknown`, every field description kept; 4,749 chars; 16 of the 32 expansions spent |

The 32-expansion cap would come back as node classes are added
(`docs/node_classes/INDEX.md` §1 plans more), silently. So the Codex view
carries no `$ref` at all (§3.1): only the byte limits remain, and TAT sets
them.

Claude Code (2.1.296, measured) passes the schema to the model unchanged
and is not affected.

## 1. Decisions

1. Recursion happens only at `children` (2026-10-16). The plugin system's
   permission for a node class's own `$defs` to refer to themselves
   (PLUGIN_SYSTEM §3, §5; MODULE_STRUCTURE §4.4) is withdrawn. No class
   TAT ships uses it.
2. For Codex, every node class's top-level `children` in the advertised
   `edit` schema becomes the one value `GivenLater` (2026-10-16). The
   field stays, so the agent sees the node is not a leaf; it keeps the
   class's own description; no sentence is added.
3. The server accepts `children: "GivenLater"` from every client and
   processes the construct as if `children` were absent (2026-10-16),
   where the class declares `children`; elsewhere it is refused as any
   unexpected `children` is (the author's reading, delegated by the owner
   2026-10-16).
4. The per-client difference uses the existing mechanism: one
   `TAT_Server` subclass per client (`Codex_Server`).
5. `Codex_Server` writes `tool_input_schema_max_bytes = 1000000` in its
   `[mcp_servers.TAT]` table, generous and room for more node classes; no
   `code_mode` setting, which 0.163.0 does not recognise (2026-10-16).
   `measured_version` becomes 0.163.0 after re-measuring on 0.163.0 what
   TAT relies on (§6). The machine's Codex is 0.163.0 (2026-10-16).
6. The Codex view is preprocessed in TAT: after decision 2, every `$ref`
   is inlined and `$defs` dropped (2026-10-16).
7. A node that can hold children and has none shows, wherever its
   children would be printed, the line (approved wording)

   ```
   Empty so far. Call `edit` with action `append` and target_id `{id}` to add children.
   ```

8. The empty forest's line (approved wording):

   ```
   There are no Isabelle sessions yet. Call `edit` with action `append` and target_id `Sessions` to declare one.
   ```

9. `edit`'s `action` description, `append` part, for every client
   (approved wording):

   ```
   append: add the constructs at the end of the target's children (the way to give children marked `GivenLater`)
   ```

## 2. Recursion only at `children` (`plugin.py`)

- `_validate_typeddict` (`plugin.py:528`): `if td in enclosing: return`
  becomes a refusal: the argument schema's TypedDict nests itself, and
  recursion happens only at `children`.
- `_validate_construct_schema` (`plugin.py:632`) refuses `$defs` cycles in
  the walk it already makes. In its `$ref` branch it keeps the entries on
  the current path, refusing a back edge (`` `$defs` entry `{name}` refers
  back to itself; recursion happens only at `children` ``), and the set of
  entries reached, descending into each once. Its trailing loop refuses an
  unreached entry with today's sentence. The rule "skip the top-level
  `kind` and `children`" stays encoded once, in that walk.
- `_Agreement` loses `met`, `reached_every_def` and the short-circuit in
  `agree`, and becomes frozen: with no cycle, the agreement walk ends
  because the annotation is finite, and reachability is the construct
  schema's walk's.

## 3. The Codex view

### 3.1 The preprocessing (`plugin.py`)

- A constant `GIVEN_LATER = "GivenLater"`, imported by the preprocessing
  and by `edit.py`, so the value advertised and the value accepted cannot
  drift apart.
- A pure function next to `assemble`, from an assembled tool schema to
  what Codex is shown, in two steps:
  1. For each node class named in `$defs.Construct.anyOf` (the form
     `assemble` writes) whose properties hold `children`: that declared
     property changes, it is not rebuilt. `items` goes, `type` becomes
     `string`, `enum: [GIVEN_LATER]` is added; what remains is what
     registration allows beside them (`plugin.py:292`), an optional
     `description`. A description on `items` goes with `items`. A
     `children` inside a class's own `$defs` is an ordinary field and is
     not touched.
  2. Inlining: every `$ref` is replaced by its entry, the site's own keys
     (at most a `description`) laid over it, and `$defs` is dropped. Step 1
     left no cycle (§2; `assemble` merges two classes' `$defs` under one
     name only when equal), so this ends. Definitions' own descriptions
     come along: `syntax?:` gains the Mixfix and TypeMixfix comments.

  A schema without `$defs` comes back unchanged, so the function applies
  to every tool without naming `edit`.
- The `action` description (decision 9) is the same for every client; it
  lives in `isabelle_theory_agent/tools/edit.jsonc`, copied in
  `docs/TOOL_SCHEMAS.md` §1.

### 3.2 Where Codex gets it (`mcp_server.py`)

- A static method on `TAT_Server`, from a tool's schema to the schema
  advertised, returning it unchanged, as `launch_arguments` is static;
  `Codex_Server` overrides it with §3.1's function.
- `__init__` keeps one `self._tools`, each built with
  `dataclasses.replace(tool, input_schema=…)`; calls are still checked
  against the assembled schema `mcp._tool`'s closure holds. `_list_tools`
  serves `self._tools` as today.
- The `Tool` and `TAT_Server` docstrings, and the principle "one object is
  what the agent is told and what a call is held to" (`mcp.py` `_tool`
  docstring; MODULE_STRUCTURE §4.4), say: the advertised schema may differ
  only inside the constructs, which the tool-level check treats as
  opaque, and every construct it admits is one the server accepts.

### 3.3 The server drops the marker (`edit.py`)

In `_construct_element` (`edit.py:418`), the one function every construct
passes through at every depth: after `cls` is known and before the
children-legality checks, when `raw.get("children") == GIVEN_LATER` and
`cls.construct_schema["properties"]` holds `children`, `raw` loses
`children`. The condition is the preprocessing's own, so the marker is
accepted exactly where the Codex view offers it. Then:

- a Leaf, or a class not declaring `children`, given the marker is refused
  as today (`UnexpectedChildren`, `UnexpectedField`);
- an amend's replacement with the marker is accepted: absent `children` is
  what amend wants, since the replacement inherits the target's children;
- a node given the marker behaves exactly as a node given no `children`,
  automatic construction included.

The rule is stated once, in MCP_SPECIFICATION §3.1, and cited from the
`UnexpectedChildren` row of EXCEPTIONS.md, MODULE_STRUCTURE §4.2 step 1,
PLUGIN_SYSTEM (`:219`) and TOOL_SCHEMAS §1.

## 4. The size setting (`Codex_Server._client_files`)

`_client_files` (`mcp_server.py:1413`) writes `tool_input_schema_max_bytes
= 1000000` in the existing `[mcp_servers.TAT]` table, from one module
constant. In Codex's source the same value also raises the rendered
declaration's limit (`code_mode.rs` `effective_input_schema_max_bytes`);
this is from source and measured on 0.163.0 in §6.

A test asserts the compact UTF-8 JSON of the Codex view of every tool
stays under a tenth of that constant; when it fails, the constant is to be
reconsidered.

## 5. The empty node's line (`model.py`)

- The line of decision 7, `{id}` the id in the form the node's own line
  prints (MCP_SPECIFICATION §2.1), so the agent copies it as `target_id`.
  One constant beside `EMPTY_FOREST`, which takes the wording of
  decision 8.
- A private module-level function `_shows_children(mode, depth)` in
  `model.py` says whether a mode prints a node's children: `Briefing`;
  `Recall` above `LAST_PRINTED_DEPTH`; `Relative_Focus` on a focus or a
  node above one; never `Out_Focus`. A plugin cannot override it.
  `_children_to_print` (`model.py:1185`) opens with it, its `Briefing` and
  `Recall` branches merged.
- `Node.print` (`model.py:799`) writes the line at `below`, where it writes
  the children, when `isinstance(self, NonLeaf_Node) and not
  self.sub_nodes and _shows_children(mode, depth)`. `NonLeaf_Node` is what
  `append` accepts as a target (`mcp.py` `_location`). PRINT.md §2's rule
  for a line with no dash then places it for the lone session.

## 6. Re-measuring on Codex 0.163.0 (before any code)

- What TAT relies on in Codex, as CLIENT_HOOKS.md (hooks, the permission
  profile and sandbox, project trust) and CONSTRUCT_INTERACTION.md state
  it for 0.156.1, measured again on 0.163.0 with the probes those
  documents cite. Each result is one dated line in
  `ai-artifacts/AGENT_CLIENTS_MEASURED.md` naming the probe run; its
  "Where the probes are" section (line 1181) is brought up to date. A
  difference is reported to the owner, not worked around.
- Whether `tool_input_schema_max_bytes` also raises the rendered
  declaration's limit: a schema whose declaration exceeds 16,000
  characters, rendered with the setting raised. A "no" is reported to the
  owner, like the differences above.
- The measurement tools (the fake model endpoint and its runner, now in
  this session's scratchpad `codex_schema/`) move to
  `ai-artifacts/probes/codex_schema/`, on disk, not committed; their tool
  filter uses `TOOL_PREFIX` (`mcp__TAT__`), not the stub's `mcp__tat__`.
- Then `measured_version = "0.163.0"`; the version mentions in
  `docs/CLIENT_HOOKS.md` (lines 7, 467), `docs/CONSTRUCT_INTERACTION.md`
  (line 890) and `test/test_hooks.py:360` follow.

After the code (§9 step 5), two checks:

1. Deterministic: the `.codex/` files `isabelle TAT` writes, the fake
   model endpoint in `ai-artifacts/probes/codex_schema/`, the declaration
   captured. It passes when the `edit` declaration was captured and its
   `constructs` union shows every registered kind; there is no `unknown`;
   each `children` shows `"GivenLater"` with its class's own description;
   and Codex prints no "unrecognized configuration setting" line.
2. A real model in `isabelle TAT` under Codex, told to create a theory
   with `GivenLater` and then append its children; it passes when the call
   log shows the first call's arguments holding `"children": "GivenLater"`
   and both calls succeeding.

## 7. Documents

- `docs/PLUGIN_SYSTEM.md` §3 (the recursion paragraph), §4 (the loader
  keeps references; the Codex view is inlined by the server's
  preprocessing; a description on `children`'s `items` is not shown to
  Codex), §5: the reachability bullet (`:261-265`) now belongs to the
  construct schema's walk and gains the `$defs` cycle refusal; the
  `argument_schema` bullet (`:254-256`) gains the refusal of a TypedDict
  that nests itself; the memoisation clause (`:278-281`) goes. `:219`
  cites the marker rule.
- `docs/MODULE_STRUCTURE.md` §4.4 (recursion; the "one object"
  restatement), §4.2 step 1 (cites the marker rule), and the paragraph
  that deferred this decision (`:1438-1444`): the schema now has a finite
  inlining, which is what Codex is served.
- `docs/MCP_SPECIFICATION.md` §3.1: the marker rule.
- `docs/EXCEPTIONS.md`: the `UnexpectedChildren` row cites it.
- `docs/TOOL_SCHEMAS.md` §1: the `action` description; cites the marker
  rule, amend's first construct included.
- `docs/PRINT.md` §2 (the empty node's line among what the framework
  writes under a line: "three more things" becomes four; `:138-140`), §6
  (the empty forest's line; its two example blocks gain the empty node's
  line under `theory_X`, shown to the owner).
- `docs/RECALL.md` §2: the line.
- `docs/RENDER_BASELINES.md` §5: the lead sentence points to PRINT.md for
  both lines.
- `docs/CLIENT_HOOKS.md` §3: the setting in `config.toml`'s block (the
  whole-file comparison test then pins it), and in the prose listing the
  server entry's keys (`:212-214`).
- §6's files: `ai-artifacts/AGENT_CLIENTS_MEASURED.md` and its "Where the
  probes are" section; `docs/CLIENT_HOOKS.md:7`, `:467`;
  `docs/CONSTRUCT_INTERACTION.md:890`.
- The docstrings of `Node.print` and `Forest.print`.
- `ai-artifacts/ISABELLE_TAT_HANDOFF.md`: the sentence claiming a full
  rendering with the settings raised is corrected (§0's table), and the
  paragraph "Options put to the owner (undecided)" (`:280-286`) is marked
  decided, pointing to this plan.

## 8. Tests

Changed:

- `test/test_plugin.py`: `Tree_RawAST` and
  `test_a_definition_may_refer_to_itself_through_an_object` become refusal
  tests (a self-nesting TypedDict; a reached `$defs` cycle). The
  unreached self-referring `Loop` (`:661`) keeps today's "reached by no
  `$ref`" refusal.
- `test/test_edit.py:407`: `Nesting_RawAST` moves into the refused list.
- Re-baselined for the empty node's line: the eleven affected renderings
  in `test/test_print.py` (`:332-333` among them), `test/test_mcp.py:478-482`,
  `test/test_conversation.py:808-819`.
- `test/test_hooks.py:360`: the version.
- `test/test_plugin.py`: the docstring of
  `test_every_def_is_reached_by_a_ref_of_the_schema` (`:643-644`, "after
  the agreement").

New:

- The preprocessing: only top-level `children` of the classes in
  `Construct`; a `$defs` field named `children` untouched; a class whose
  `children` has no description; schemas without `$defs` unchanged; the
  Codex view holds no `$ref` and no `$defs` (mutation: the inlining step
  replaced by the identity).
- The inlining, exactly: the function's output on a small hand-written
  schema with a site's description over an entry's own, an `anyOf` entry
  carrying its own description, and a `$ref` inside an entry. Mutations:
  `{}` for every reference; the entry's description winning over the
  site's; definitions' own descriptions dropped.
- Over the classes `plugin.load(["isabelle_theory_agent.std"])` registers,
  with `test_common.EXAMPLES` (`test/test_common.py:40`) beside
  `SHIPPED_EXAMPLES` (`test/test_plugin.py:922`): Draft 2020-12
  `check_schema` on the Codex view; each example with `GIVEN_LATER` in its
  `children` is valid against the view, the nested original is not, and
  the marked example goes through `edit`. §4's size test runs over the
  same classes.
- `_list_tools`: Codex is served the Codex view, Claude Code the assembled
  schema.
- `edit`: `GivenLater` on a session and on a theory, nested at depth; on
  amend's first construct; refused on a Leaf; refused with
  `UnexpectedField` on a nesting class of the test suite that does not
  declare `children`, written beside the test (mutation: the condition
  swapped for `NonLeaf_Node`). That only `GivenLater` counts as the marker
  is already checked by `test_children_field_must_be_a_list`
  (`test/test_edit.py:482-489`).
- `_client_files`: the size test of §4.
- `test/test_print.py`: the empty node's line in each mode that shows
  children; absent under `Out_Focus` and under `Recall` at
  `LAST_PRINTED_DEPTH` (the fixture at `:274-288`); the quickview of a
  lone empty session (mutation: `below` swapped for `indent + 1`).

Every new test is mutation-checked: the implementation swapped for a
wrong one in memory, the test must fail.

## 9. Order

1. Announce the touched files (§7, §8 and the code of §2-§5) to the peer
   sessions.
2. §6's re-measurement; differences to the owner.
3. §2 with its tests and documents.
4. §3, §4, §5 with their tests and documents.
5. `measured_version`; the whole suite; §6's two checks; commit.
