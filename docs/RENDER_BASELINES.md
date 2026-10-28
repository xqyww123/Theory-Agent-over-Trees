# Render baselines

Status: approved wording. Every line here is agent-facing text approved by
the project owner (EXCEPTIONS.md §3); the baseline test asserts these
renderings verbatim, and changing a line is changing the interface — it goes
back to the owner first.

Each baseline is one example instance: field values are the example's, the
sentence shapes are the contract. In cause lines every interpolated
identifier is backticked; opening lines echo the call and are not.

## 1. Opening lines

Rendered for every forest-changing operation that failed
(TOOL_SCHEMAS.md §4), above the cause:

```
Cannot append theory_X.section_Basics
Cannot insert_before theory_X.lemma_P
Cannot insert_after theory_X.lemma_P
Cannot amend theory_X.lemma_P
Cannot move theory_Sorting before theory_X.lemma_P
Cannot move theory_Sorting after theory_X.section_Basics
Cannot move theory_Sorting into session_Arith
Cannot delete theory_X.section_Basics
```

## 2. Cause lines

The indefinite article before a kind in backquotes is computed from the
kind, in every sentence of this document that has one
(`exceptions.a_kind`): `an` when the kind starts with a vowel letter, `a`
otherwise — ``A `lemma` …``, ``An `inductive` …``.

`NodeNotFound` — when there are no near matches, only the first sentence
renders:

```
`lemma_fo` is not found. Did you mean `lemma_foo` or `lemma_fold`?
```

`AmbiguousId`:

```
The id `lemma_P` matches more than one node: `theory_X.lemma_P`, `theory_Y.lemma_P`. Choose the one you meant.
```

`MalformedRawAST`, its two cases:

```
Expected a construct object.
The field `kind` is missing.
```

`UnknownKind`:

```
Unknown kind `lemna`. Available kinds: `lemma`, `theorem`, `corollary`, `proposition`, `definition`, `section`, `text`, `theory`, `session`.
```

`MissingField`, and its form for a tool call's own arguments
(TOOL_SCHEMAS.md §4):

```
A `lemma` needs the field `statement`.
An `inductive` needs the field `name`.
The `edit` tool needs the argument `evaluate`.
```

`InvalidField` — `<reason>` is a schema check's or the class's, from its
`gen` or its field check (PLUGIN_SYSTEM §2), a predicate completing the
sentence; `argument` replaces `field` for a tool call's own arguments; a
line the field check raises is told alone, as its node's first own
operation's message, with no path before it and no opening line:

```
The field `statement` <reason>.
The argument `constructs` <reason>.
```

A schema check's own reasons are `must be` followed by the JSON type —
`a string`, `an integer`, `a number`, `a boolean`, `a list`, `an object`,
and `null` for the one arm a construct's union may admit (PLUGIN_SYSTEM §5)
— several joined with ` or `, each JSON type once, in the order the schema first names them; `must be one of` followed by the `enum`,
backticked, `must not be empty` for `minItems`, `must be a 64-bit
integer` for an integer outside the signed 64-bit range, and `cannot
hold Isabelle's internal markup (U+0005 or U+0006)` for a string still
holding either character once the call's strings are repaired
(MCP_SPECIFICATION §1) — but in the field that tells a union's arms
apart, whose value matches no arm's `enum` and is told `must be one of`
— for a tool call's arguments and a construct's fields alike
(MODULE_STRUCTURE §4.4);
and `must not be nested deeper than 100 levels`, said of a tool call's
argument before any other check, each object or array a level:

```
The field `statement` must be an object.
The field `implicit_structure` must be a string or null.
The argument `action` must be one of `append`, `insert_before`, `insert_after`, `amend`.
The argument `constructs` must not be empty.
The argument `constructs` must not be nested deeper than 100 levels.
The field `types` must not be empty.
The field `types[0].constructors[1].syntax.form` must be one of `infix`, `infixl`, `infixr`, `binder`, `mixfix`, `NoSyntax`.
The field `types[0].constructors[1].syntax.priority` must be a 64-bit integer.
The field `english` cannot hold Isabelle's internal markup (U+0005 or U+0006).
The argument `node_id` cannot hold Isabelle's internal markup (U+0005 or U+0006).
```

`UnexpectedField` — the holder is the kind, or a nested container's path,
and `it takes` lists that holder's fields in the order the schema
declares them, less `kind` and `children` at a construct's top — for a
union told apart by a `Literal` field, before
that field has chosen an arm, every arm's fields in the order they
first appear, the arms in the schema's order (MODULE_STRUCTURE §4.4);
a holder declaring no field takes `no fields`, or `no arguments` within
a tool call; for a tool call's own arguments the holder is the tool:

```
A `lemma` has no field `statment`; it takes `name`, `statement`.
`statement.premises[1]` has no field `nmae`; it takes `name`, `term`.
A `note` has no field `children`; it takes no fields.
The `edit` tool has no argument `kind`; it takes `action`, `target_id`, `constructs`, `evaluate`, `auto_construct`.
`location` has no argument `where`; it takes `position`, `node_id`.
`answer` has no argument `verdict`; it takes no arguments.
```

`InvalidName`, against the name grammar of MCP_SPECIFICATION §2 (the
framework's check), against the theory name's grammar (`Theory.gen`'s
check), against the session name's (`Session.gen`'s check), and
against the fact name's, the type name's, the constant name's and the
locale name's — a plugin node's own name, checked by its class's `gen`
against the id grammar without hyphens (node_classes/COMMON.md §5; the
class's document, §4); `grammar` selects the rendering, the fact
name's, the type name's, the constant name's and the locale name's
sharing one text:

```
`Ch 2` is not a valid name: a name starts with a letter and continues with letters, digits, underscores, primes (') and interior hyphens, and does not end with a hyphen or an underscore.
`Foo-Bar` is not a valid theory name: a theory name starts with a letter and continues with letters, digits and underscores, with no hyphen and no dot.
`S'` is not a valid session name: a session name starts with a letter and continues with letters, digits, underscores and interior hyphens, and does not end with a hyphen or an underscore.
`rev-length` is not a valid fact name: a fact name starts with a letter and continues with letters, digits, underscores and primes ('), and does not end with an underscore.
`my-list` is not a valid type name: a type name starts with a letter and continues with letters, digits, underscores and primes ('), and does not end with an underscore.
`dl-rev` is not a valid constant name: a constant name starts with a letter and continues with letters, digits, underscores and primes ('), and does not end with an underscore.
`idempotent-semigroup` is not a valid locale name: a locale name starts with a letter and continues with letters, digits, underscores and primes ('), and does not end with an underscore.
```

`DuplicateName` — two siblings would share an id component
`<kind>_<name>` (MCP_SPECIFICATION §2) — colliding with an existing
sibling:

```
The id component `lemma_assoc` is already taken by `theory_Sorting.lemma_assoc`. Amend that node, or give this one another name.
```

`DuplicateName`, colliding inside the submitted batch:

```
The id component `lemma_assoc` is already used by `constructs[0]` of this call.
```

`DuplicateTheoryShortName`, against the base heap or another tree:

```
The theory name `List` conflicts with the short name of `HOL.List`. No two theories can share a short name.
```

`DuplicateTheoryShortName`, colliding inside the submitted batch:

```
The theory name `Foo` is also used by `constructs[1].children[0]` of this call.
```

`ReservedTheoryName`, a name the Isabelle session layout declares global,
or one Isabelle reserves as a file or theory name:

```
`FOL` is a reserved theory name; choose another name.
```

`ReservedSessionName`, a name Isabelle reserves as a file or session
name, or `ROOT`:

```
`Aux` is a reserved session name; choose another name.
`ROOT` is a reserved session name; choose another name.
```

`HoldsNoChildren`:

```
`theory_X.lemma_P` is a `lemma`, and it cannot hold children.
```

`UnexpectedChildren`, on an amend's replacement:

```
When amending a non-leaf node, `children` is not allowed: the amended node inherits its existing children. To change the children, use `delete` to remove them and `append` or `insert_before` to add new ones.
```

`UnexpectedChildren`, on a leaf:

```
`children` is not allowed: a `lemma` holds no children.
```

`ChildrenNotInheritable`, and with one child:

```
`theory_X.section_Basics` has 3 children, which a `lemma` cannot hold. Move or delete them first.
`theory_X.section_Basics` has 1 child, which a `lemma` cannot hold. Move or delete it first.
```

`BadNodeParent` — the forest's shape, checked at the edit (ARCHITECTURE
§2; EXCEPTIONS.md §3): the head, naming the node's kind and the parent by
its full id, then the remedy as a sentence of its own. The framework's
`BadNodeParent`, for a node of any class but `Session` and `Theory` under
the root or a session; `Theory`'s `BadTheoryNodeParent`; `Session`'s
`BadSessionNodeParent`:

```
A `lemma` cannot stand under `Sessions`. Put it in a theory.
A `lemma` cannot stand under `session_Arith`. Put it in a theory.
A `theory` cannot stand under `Sessions`. Put it in a session.
A `theory` cannot stand under `session_Arith.theory_X.section_Basics`. Put it in a session.
A `session` cannot stand under `session_Arith`. Put it under `Sessions`.
A `session` cannot stand under `session_Arith.theory_X`. Put it under `Sessions`.
```

`MoveIntoOwnSubtree`:

```
`theory_X.section_Basics` cannot move into its own subtree.
```

`MoveBesideItself`:

```
`theory_X.lemma_P` is already in that position; a move must name another node.
```

`ProtectedNode`:

```
The `Sessions` cannot be edited.
```

`ConstructNotSupported`, when the call named one node and when it named
several:

```
`theory_X.section_Basics` has nothing to construct.
None of these nodes has anything to construct.
```

The other framework `ConstructionError`s, which `answer` raises:
`NoQuestionPending`, the framework's sentence for a node on which no
question of the caller's waits, whatever its construction job's state;
`ConstructOwnedByAnother`, the job class's `owned_by_another_refusal`,
composed from the job's title by default (CONSTRUCT_INTERACTION §3.2),
here for `proof construction`; `BadAnswer` renders the question's own
sentence:

```
`theory_X.definition_f` has no question waiting for an answer.
The proof construction on `lemma_P` belongs to another agent.
```

The `raw_ast_path` prefix — on any cause raised while building a batch
(EXCEPTIONS.md §5):

```
At `constructs[2].children[0]`: A `lemma` needs the field `statement`.
```

## 3. Evaluation text

Not exception classes — evaluation failure lives outside the hierarchy
(EXCEPTIONS.md §6) — but TAT-authored and agent-facing all the same.

The order constraint's stop (ARCHITECTURE §3.3), a tree importing a forest
tree placed after it, or itself — composed by the tool from the forest's
answer (`Forest._order_violation`, MODULE_STRUCTURE §4.1): the tree's id
and the offending item, `S.C` as the agent wrote it in `imports`; the
second line when the item names the tree itself, which no move can put
after it (approved 2026-10-05):

```
Since `theory_B` imports `S.C`, you cannot put it before `S.C`. Move it later.
`theory_B` imports itself. Remove `S.B` from its imports.
```

`Loader.fetch` (ML side), an import found nowhere — no forest tree, no
base-heap theory, no file the Isabelle session layout knows — or a
qualified import whose short name the layout declares global (`HOL.Main`,
EVALUATOR_DESIGN §7), named as Isabelle resolved it:

```
Fail to load `TAT_Nowhere.Nope` because it is not found.
```

A node the placement check refuses (PLUGIN_SYSTEM §2): its first own
operation's `CannotEvaluate`, the hook never run. The framework writes
the head — the node's kind with its article, and the ancestor it cannot
stand under, by its full id — and the remedy after it is the answer of
that ancestor's class or of the node's own, approved and pinned in that
class's document; a test composes the full line from this form and the
remedy's home:

```
<A|An> `<node's kind>` cannot stand under `<ancestor's full id>`. <remedy>
```

## 4. Server text

The one answer the server gives while the conversation is ending
(MODULE_STRUCTURE §4.6), to every tool call it cancels whose client is
still waiting, and every tool call that arrives meanwhile — one line per reason the
server gives, and never an exception's own text:

```
TAT has stopped: an internal error; this is a critical error, and this call did not complete. Stop now and call TAT no more. If another agent started you, tell it to stop as well; otherwise tell the user that TAT has stopped.
TAT has stopped: the sessions could not be saved; this is a critical error, and this call did not complete. Stop now and call TAT no more. If another agent started you, tell it to stop as well; otherwise tell the user that TAT has stopped.
TAT has stopped: Isabelle is gone; this is a critical error, and this call did not complete. Stop now and call TAT no more. If another agent started you, tell it to stop as well; otherwise tell the user that TAT has stopped.
TAT has stopped: Claude Code saves no transcript; this is a critical error, and this call did not complete. Stop now and call TAT no more. If another agent started you, tell it to stop as well; otherwise tell the user that TAT has stopped.
TAT has stopped: Codex's sandbox is not the one TAT configured; this is a critical error, and this call did not complete. Stop now and call TAT no more. If another agent started you, tell it to stop as well; otherwise tell the user that TAT has stopped.
TAT has stopped: a client TAT does not serve connected; this is a critical error, and this call did not complete. Stop now and call TAT no more. If another agent started you, tell it to stop as well; otherwise tell the user that TAT has stopped.
TAT has stopped: it cannot use its working directory; this is a critical error, and this call did not complete. Stop now and call TAT no more. If another agent started you, tell it to stop as well; otherwise tell the user that TAT has stopped.
```

The line is chosen by what ended the conversation (MODULE_STRUCTURE
§4.6): the second for a `TAT_DisasterError`, the third for the
connection gone, the fourth to sixth for a `ClientRefused` (EXCEPTIONS.md
§3), each of which carries its line — the sixth is the client's version
or name failing the check in a later MCP session — the seventh for the
`TAT_StartupError` of a `Session`'s folder that cannot be made when a
theory begins (MODULE_STRUCTURE §4.1), and the first for everything
else.

A tool call whose body completed — before the ending reached it, or after
ignoring its cancellation — is answered what it did (MODULE_STRUCTURE
§4.6).

## 5. Rendering

The lines the framework writes in every rendering (PRINT.md); the empty
forest's hint is PRINT.md §6's, the empty node's line PRINT.md §2's, and
a class's own marks are its own document's.

A node's line, one per default mark; `Theorem`'s two-slot marks are
node_classes/THEOREM.md §7's:

```
- section_Basics (complete)
- section_Basics (incomplete)
- datatype_tree (not evaluated)
- datatype_color (failed)
```

The framework's tags, after the class's mark (PRINT.md §1,
CONSTRUCT_INTERACTION §6): `automatic construction` on a node whose
construction job has that setting on, for every agent; `needs your
answer …` on a node whose construction job waits for the answer of the
agent the rendering is for; both, in that order:

```
- lemma_Q (valid statement, proven, automatic construction)
- lemma_rev_length (valid statement, proving, needs your answer, call `check_construct` to see it)
- lemma_rev_length (valid statement, proving, automatic construction, needs your answer, call `check_construct` to see it)
```

A message block, as `print_error` writes it — `Error:` under a
`CannotEvaluate`, `Notice:` under a `Ready` that reported something
(PRINT.md §3):

```
Error:
  Type unification failed: ...
```

```
Notice:
  Ignoring duplicate rewrite rule: ...
```

A job's failure block — the header is the job class's, the shape the
framework's (PRINT.md §2):

```
  No proof was found:
    Sledgehammer timed out on every prover.
```

The children header, over a nesting node's children where a keyed line
stands under its line (PRINT.md §2) — the phrase the class's, `Theory`'s
here (node_classes/SESSION_AND_THEORY.md §4), the colon and the level
the framework's:

```
  declarations:
    - lemma_A (valid statement, proven)
```

The summary under an `incomplete` nesting node at `Recall`'s last depth
(PRINT.md §2), one line per group with members, ids up to five, the
count alone past five:

```
  3 proof constructions incomplete: lemma_A, lemma_C, context_C.lemma_B
  12 proof checks incomplete
  1 node failed: definition_f
  2 nodes not evaluated: lemma_E, lemma_F
```

## 6. Success lines

Rendered for every forest-changing operation that succeeded, above the
quickview (TOOL_SCHEMAS.md §4); the second form when the call's
evaluation stopped at a node, which it names in its shortest form:

```
Done: append theory_X.
Done: insert_after theory_X.lemma_P; evaluation stopped at definition_f.
Done: move theory_Sorting after theory_X.section_Basics.
Done: delete theory_X.section_Basics.
```

A successful `evaluate_to` opens with one of two lines, above its
quickview: the destination, when no stop is reported, or the stop, the
node in its shortest form:

```
Evaluation reached theory_X.
Evaluation stopped at definition_f.
```

When the stop is the order constraint's, its sentence (§3) follows on
the line after the stop line — after an edit's `Done` line just the same.

A successful `construct` or `cancel_construct` opens instead with each job
class's `starting_notice` or `cancelling_notice`, one per class, composed from its title
by default (CONSTRUCT_INTERACTION §3.2), above the quickview. Each names
every node the call started or cancelled: one node; two or three, `on`
repeated and `and` before the last; more, a header and one id per
line, each in its shortest form; none, a fixed sentence. A call whose evaluation started
constructions automatically names them before its trailer in the same
forms, opened with `Automatically started` (CONSTRUCT_INTERACTION §5):

```
Automatically started the proof construction on `lemma_A`; call `check_construct` before you exit.
Started the proof construction on `lemma_P`; call `check_construct` before you exit.
Started the proof construction on `lemma_P`, on `lemma_Q` and on `lemma_R`; call `check_construct` before you exit.
Started the following proof constructions; call `check_construct` before you exit:
  - lemma_P
  - lemma_Q
  - lemma_R
  - lemma_S
No construction job was started.
Cancelled the proof construction on `lemma_P`.
Cancelled the proof construction on `lemma_P`, on `lemma_Q` and on `lemma_R`.
Cancelled the following proof constructions:
  - lemma_P
  - lemma_Q
  - lemma_R
  - lemma_S
No construction job was running.
```
