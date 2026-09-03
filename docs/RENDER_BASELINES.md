# Render baselines

Status: approved wording. Every line here is agent-facing text approved by
the project owner (EXCEPTIONS.md §3); the baseline test asserts these
renderings verbatim, and changing a line is changing the interface — it goes
back to the owner first.

Each baseline is one example instance: field values are the example's, the
sentence shapes are the contract. In cause lines every interpolated
identifier is backticked; opening lines echo the call and are not.

## 1. Opening lines

Rendered for the six forest-changing operations (TOOL_SCHEMAS.md §5), above
the cause:

```
Cannot append theory_X.section_Basics
Cannot insert_before theory_X.lemma_P
Cannot amend theory_X.lemma_P
Cannot move theory_Sorting to before theory_X.lemma_P
Cannot move theory_Sorting to after theory_X.section_Basics
Cannot move theory_Sorting to session_Arith
Cannot delete theory_X.section_Basics
Cannot new_session session_Arith
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
Expected a node description object.
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

`InvalidName`:

```
`Ch. 2 lemmas` is not a valid name: a name starts with a letter and continues with letters, digits, underscores and primes ('), and does not end with an underscore.
```

`DuplicateName`, colliding with an existing sibling:

```
The name `lemma_assoc` is already taken by `theory_Sorting.lemma_assoc`. Amend that node, or pick another name.
```

`DuplicateName`, colliding inside the submitted batch:

```
The name `lemma_assoc` is already used by `nodes[0]` of this call.
```

`DuplicateTheoryShortName`:

```
The theory name `List` conflicts with the short name of `HOL.List`. No two theories can share a short name.
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
A `Session` cannot be inserted under `theory_X`. Use `new_session` to create a session.
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
The `$Root` cannot be edited.
```

`ConstructNotSupported`:

```
`theory_X.text_intro` does not support construct.
```

The `raw_ast_path` prefix — on any cause raised while building a batch
(EXCEPTIONS.md §5):

```
At `nodes[2].children[0]`: A `lemma` needs the field `statement`.
```

## 3. Evaluation text (ML side)

Not exception classes — evaluation failure lives outside the hierarchy
(EXCEPTIONS.md §6) — but TAT-authored and agent-facing all the same.

`Loader.load_target`, an import found nowhere:

```
Fail to load `TAT_Nowhere.Nope` because it is not found.
```
