# Theory-Agent-over-Trees (TAT)

An agent that writes Isabelle theories by editing a **forest of trees** rather
than text. Each tree is one Isabelle theory; each node is a declaration — a
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

**Status: design. No implementation yet.**

## Documents

| Document | Contents |
| --- | --- |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | The design |
| [docs/EVALUATOR_DESIGN.md](docs/EVALUATOR_DESIGN.md) | The Isabelle/ML evaluator: mechanism, theory loading, name resolution |
| [docs/MCP_SPECIFICATION.md](docs/MCP_SPECIFICATION.md) | What TAT exposes to the agent: tools, node ids, evaluation, messages |
| [docs/MODULE_STRUCTURE.md](docs/MODULE_STRUCTURE.md) | Directories, files and modules on both sides |
| [docs/EXCEPTIONS.md](docs/EXCEPTIONS.md) | The exceptions: the hierarchy and the two framework-written fields, `opr` and `raw_ast_path` |
| [docs/TOOL_SCHEMAS.md](docs/TOOL_SCHEMAS.md) | The tools' argument shapes and the first line a failure renders |
| [docs/node_classes/SESSION_AND_THEORY.md](docs/node_classes/SESSION_AND_THEORY.md) | The `Session` and `Theory` node classes |
| [docs/OPEN_QUESTIONS.md](docs/OPEN_QUESTIONS.md) | What is undecided, and what it blocks |
| [docs/appendix/SEGMENT_INTEGRITY.md](docs/appendix/SEGMENT_INTEGRITY.md) | The check that a node's text is self-delimiting |

## How it runs

TAT is a Python process and an Isabelle process. The Python side owns the forest
and serves the Model Context Protocol (MCP) tools; the Isabelle side runs an evaluator that TAT provides,
driving Isabelle one command at a time.

Node classes are extensible, and a node class is installed by naming its theory
to the conversation, which loads it from source at start.
