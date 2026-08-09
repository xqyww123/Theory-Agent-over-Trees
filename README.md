# Theory-Agent-over-Trees (TAT)

An agent that writes Isabelle theories by editing a **forest of trees** rather than
by editing text. Each tree is one Isabelle theory; each node is a semantic unit
(a theorem, a definition, a datatype, a section heading). The forest **compiles**
to ordinary `.thy` files, which Isabelle checks; per-command results are routed
back to the node that emitted them and rendered for the agent.

TAT is the theory-level counterpart of
[AoA](../Isa-Mini/IsaMini/AoA/) (Agent over AST), which works at proof level
inside a single theorem. AoA's design principle applies here too: the agent
manipulates a structured object whose nodes carry their own results, instead of
emitting source text and re-locating results by line numbers afterwards.

**Status: design. No implementation yet.**

## Documents

| Document | Contents |
| --- | --- |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | The model (forest / tree / node / segment), compilation, and the command-to-node mapping |
| [docs/SUBSTRATE_RESEARCH.md](docs/SUBSTRATE_RESEARCH.md) | How Isabelle is driven: five candidate routes, the evidence for each, and why four were rejected |
| [docs/EXPERIMENTS.md](docs/EXPERIMENTS.md) | Measured facts, as opposed to facts read out of source |
| [docs/OPEN_QUESTIONS.md](docs/OPEN_QUESTIONS.md) | Decisions still to be made, and what each one blocks |

## Relationship to Isabelle-MCP

TAT is built as a plugin of [Isabelle-MCP](../Isabelle-MCP/), reusing its
Isabelle process management, evaluation-completion logic, and its forked Isabelle
Scala component (`isabelle mcp_server`). TAT exposes its **own** MCP server; in
the intended deployment Isabelle-MCP's own tools are disabled and only TAT's are
visible to the agent.
