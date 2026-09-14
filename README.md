# Theory-Agent-over-Trees (TAT)

A server that lets an agent write Isabelle theories by editing a **forest of
trees** rather than text. Each tree is one Isabelle theory; each node is a declaration — a
theorem, a definition, a datatype, a section heading. The forest compiles to
ordinary `.thy` files, and each command's result is routed back to the node that
emitted it.

The point of the tree is that routing. An agent that edits theory text can only
be told that line 47 failed; an agent that edits a tree is told which
declaration failed and, for a declaration that produces several commands,
which of them.

The trees are pure declarations. Every proof is emitted as the `AoA` proof
method — Sledgehammer first, falling back to the AoA proof agent when it
times out — so TAT decides what is claimed and how a theory is organised, never
how a claim is established. That divides the work with
[AoA](../Isa-Mini/IsaMini/AoA/) (Agent over AST), which works at proof level
inside a single theorem.

**Status: design; the first steps of the ML framework and the Python model
are implemented.**

## Documents

| Document | Contents |
| --- | --- |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | The design |
| [docs/EVALUATOR_DESIGN.md](docs/EVALUATOR_DESIGN.md) | The Isabelle/ML evaluator: mechanism, theory loading, name resolution |
| [docs/MCP_SPECIFICATION.md](docs/MCP_SPECIFICATION.md) | What TAT exposes to the agent: tools, node ids, evaluation, messages |
| [docs/MODULE_STRUCTURE.md](docs/MODULE_STRUCTURE.md) | Directories, files and modules on both sides |
| [docs/EXCEPTIONS.md](docs/EXCEPTIONS.md) | The exceptions: the hierarchy and the two framework-written fields, `opr` and `raw_ast_path` |
| [docs/TOOL_SCHEMAS.md](docs/TOOL_SCHEMAS.md) | The tools' argument shapes and the first line a failure renders |
| [docs/PLUGIN_SYSTEM.md](docs/PLUGIN_SYSTEM.md) | How node classes register, and how their schemas complete the `edit` tool's |
| [docs/PRINT.md](docs/PRINT.md) | `print` and `quickview`: how nodes and the forest render |
| [docs/RENDER_BASELINES.md](docs/RENDER_BASELINES.md) | The approved agent-facing wording of every error |
| [docs/node_classes/SESSION_AND_THEORY.md](docs/node_classes/SESSION_AND_THEORY.md) | The `Session` and `Theory` node classes |
| [docs/OPEN_QUESTIONS.md](docs/OPEN_QUESTIONS.md) | What is undecided, and what it blocks |

## How it runs

TAT is a Python process and an Isabelle process. The Python side owns the forest
and serves the Model Context Protocol (MCP) tools; the Isabelle side runs an evaluator that TAT provides,
driving Isabelle one command at a time.

Node classes are extensible: every node class is a plugin — an Isabelle
theory and a Python package — and one beyond TAT's own is named to
`isabelle TAT_new` by the full name (SESSION.THEORY) of the theory that
defines it, and loaded from source when the conversation starts.

Register this directory, `contrib/Isabelle_RPC` and
`contrib/Performant_Isabelle_ML` as Isabelle components
(`isabelle components -u <directory>`). Two commands follow:

```
Usage: isabelle TAT_new [OPTIONS] WORKING_DIRECTORY

  Options are:
    -P PLUGIN    a plugin to load in this working directory. Give the full
                 name (SESSION.THEORY) of the theory that defines the plugin.
                 Example: -P My_Nodes.Locale_Node

  Create WORKING_DIRECTORY for TAT. TAT's own node classes are always loaded.
  On an existing working directory, TAT_new adds the given plugins and
  changes nothing else.

Usage: isabelle TAT [OPTIONS] WORKING_DIRECTORY

  Options are:
    -l BASE      the base heap (default: ISABELLE_LOGIC)
    -p PORT      the port of the MCP server (default: 8191)
    -d DIR       as Isabelle's -d: a further directory whose ROOT declares
                 Isabelle sessions
    -o OPTION    as Isabelle's -o: override an Isabelle system option

  Start a TAT conversation on WORKING_DIRECTORY: Isabelle on the base heap,
  and the MCP server on http://127.0.0.1:PORT/mcp.
```

Hand that URL to the agent's client when launching it.
