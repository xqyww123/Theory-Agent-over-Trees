# Render baselines

Status: approved wording. Every line here is agent-facing text approved by
the project owner (EXCEPTIONS.md §3); the baseline test asserts these
renderings verbatim, and changing a line is changing the interface — it goes
back to the owner first.

Each baseline is one example instance: field values are the example's, the
sentence shapes are the contract. In cause lines every interpolated
identifier is backticked; opening lines echo the call and are not.

## 1. Opening lines

Rendered for every forest-changing operation (TOOL_SCHEMAS.md §4), above
the cause:

```
Cannot append theory_X.section_Basics
Cannot insert_before theory_X.lemma_P
Cannot insert_after theory_X.lemma_P
Cannot amend theory_X.lemma_P
Cannot move theory_Sorting to before theory_X.lemma_P
Cannot move theory_Sorting to after theory_X.section_Basics
Cannot move theory_Sorting to session_Arith
Cannot delete theory_X.section_Basics
```

## 2. Cause lines

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
Unknown kind `lemna`. Available kinds: `lemma`, `theorem`, `corollary`, `definition`, `section`, `text`, `theory`, `session`.
```

`MissingField`:

```
A `lemma` needs the field `statement`.
```

`InvalidField` — `<reason>` is the schema check's or the `gen` author's, a
predicate completing the sentence:

```
The field `statement` <reason>.
```

The schema check's own reasons are `must be` followed by the JSON type —
`a string`, `a number`, `a boolean`, `a list`, `an object` — several
joined with ` or `:

```
The field `statement` must be a string.
```

`UnexpectedField` — the holder is the kind, or a nested container's path,
and `it takes` lists that holder's fields in declaration order:

```
A `lemma` has no field `statment`; it takes `statement`, `name`, `facts`.
`facts[1]` has no field `nmae`; it takes `name`.
```

`InvalidName`, against the name grammar of MCP_SPECIFICATION §2 (the
framework's check), and against the Isabelle identifier a theory name must
be (`Theory.gen`'s check, `theory_name`):

```
`Ch 2` is not a valid name: a name starts with a letter and continues with letters, digits, underscores, primes (') and interior hyphens, and does not end with a hyphen or an underscore.
`Foo-Bar` is not a valid theory name: a theory name starts with a letter and continues with letters, digits, underscores and primes ('), with no hyphen and no dot.
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

`Bad<Class>NodeParent` — each node class carries its own sentence
(EXCEPTIONS.md §3). `Theorem`'s `BadTheoremNodeParent`:

```
A `lemma` cannot be placed under `session_Arith`; it belongs inside a theory.
```

`Session`'s `BadSessionNodeParent`:

```
A `session` cannot be placed under `theory_X`; a session lives directly under `Sessions`.
```

`Theory`'s `BadTheoryNodeParent`:

```
A `theory` cannot be placed under `section_Basics`; a theory lives directly under a session.
```

`MoveIntoOwnSubtree`:

```
`theory_X.section_Basics` cannot move into its own subtree.
```

`ProtectedNode`:

```
The `Sessions` cannot be edited.
```

`ConstructNotSupported`:

```
`theory_X.text_intro` does not support construct.
```

The `raw_ast_path` prefix — on any cause raised while building a batch
(EXCEPTIONS.md §5):

```
At `constructs[2].children[0]`: A `lemma` needs the field `statement`.
```

## 3. Evaluation text

Not exception classes — evaluation failure lives outside the hierarchy
(EXCEPTIONS.md §6) — but TAT-authored and agent-facing all the same.

The order constraint's stop (ai-artifacts/FIRST_END_TO_END_RUN_PLAN.md §6),
a tree importing a forest tree placed after it; `S.C` as the agent wrote
it in `imports`:

```
Since `theory_B` imports `S.C`, you cannot put it before `S.C`. Move it later.
```

`Loader.load_target` (ML side), an import found nowhere:

```
Fail to load `TAT_Nowhere.Nope` because it is not found.
```

## 4. Server text

The one answer the server gives while the conversation is ending
(MODULE_STRUCTURE §4.6), to every call it cancels whose client is still
waiting, and every call that arrives meanwhile — one line per reason the
server gives, and never an exception's own text:

```
TAT has stopped: an internal error; this call did not complete.
TAT has stopped: the forest could not be saved; this call did not complete.
TAT has stopped: Isabelle is gone; this call did not complete.
```
