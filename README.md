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
| [docs/TOOL_SCHEMAS.md](docs/TOOL_SCHEMAS.md) | The tools' argument shapes and what a call renders |
| [docs/PLUGIN_SYSTEM.md](docs/PLUGIN_SYSTEM.md) | How node classes register, and how their schemas complete the `edit` tool's |
| [docs/PRINT.md](docs/PRINT.md) | Rendering: the modes, the marks, the errors, the forest root |
| [docs/RECALL.md](docs/RECALL.md) | The `recall` tool: what it reads, what it renders, the call |
| [docs/CLIENT_HOOKS.md](docs/CLIENT_HOOKS.md) | The agent client's files, written at every launch (the MCP entry, the hooks, the sandbox settings), its launch arguments, and the endpoint the hooks call |
| [docs/RENDER_BASELINES.md](docs/RENDER_BASELINES.md) | The approved agent-facing wording: every error, and the lines the framework writes |
| [docs/node_classes/SESSION_AND_THEORY.md](docs/node_classes/SESSION_AND_THEORY.md) | The `Session` and `Theory` node classes |
| [docs/OPEN_QUESTIONS.md](docs/OPEN_QUESTIONS.md) | What is undecided, and what it blocks |

## How it runs

TAT is a Python process and an Isabelle process. The Python side owns the forest
and serves the Model Context Protocol (MCP) tools; the Isabelle side runs an evaluator that TAT provides,
driving Isabelle one command at a time.

### How to use

Once, from the repository root, register the six Isabelle components
TAT's sessions build on:

    isabelle components -u contrib/Theory-Agent-over-Trees -u contrib/Isabelle_RPC -u contrib/Performant_Isabelle_ML -u contrib/auto_sledgehammer -u contrib/Isa-Mini -u contrib/Semantic_Embedding

Then:

    isabelle TAT -P TAT_Isabelle_Std.TAT_Isabelle_Std -l Minilang_AoA [-c claude-code|codex] WORKING_DIRECTORY [CLIENT_ARGS ...]

`-P` records the plugin of Isabelle's standard commands (`Theorem` among
them) in WORKING_DIRECTORY: this launch and every later one load it,
giving `-P` again changes nothing, and nothing removes it. `-l` names the
base heap holding the `aoa` method the plugin's proofs use; the working
directory does not record it, so it is given at every launch, and this
one command line serves for every launch. Without the plugin the forest
holds sessions and theories only. The command creates WORKING_DIRECTORY
if needed, starts a TAT conversation on it, and starts the agent client
(Claude Code by default) in `WORKING_DIRECTORY/TAT.agents/`, where it
writes the client's configuration at every launch. Arguments after
WORKING_DIRECTORY are passed to the client. The conversation ends with
the client; the forest stays in WORKING_DIRECTORY for the next one.

Lower-level commands: `isabelle TAT_new` creates a working directory;
`isabelle TAT_mcp` serves a conversation on it over HTTP, for a client
started by hand; `isabelle TAT_compile` writes its theories and a ROOT
into it. Each prints its usage when run without arguments.
