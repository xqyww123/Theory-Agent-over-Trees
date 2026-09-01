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
Cannot move theory_Sorting to after theory_X.section_Basics
Cannot move theory_Sorting to session_Arith
Cannot delete theory_X.section_Basics
Cannot new_session session_Arith
```

## 2. Cause lines

`NodeNotFound` — without near matches, the first sentence alone:

```
`lemma_fo` is not found. Did you mean: `lemma_foo`, `lemma_fold`?
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
Unknown kind `lemna`. Available kinds: `lemma`, `theorem`, `corollary`, `definition`, `section`, `text`, `theory`.
```

`MissingField`:

```
A `lemma` needs the field `statement`.
```

`InvalidField` — `<reason>` is the schema check's or the `gen` author's:

```
Field `statement`: <reason>.
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
The theory name `List` conflicts with the short name of `HOL.List`. No theories can share the same short name.
```

`UnexpectedChildren`, on an amend's replacement:

```
When amending a non-leaf node, `children` is not allowed: the amended node inherits its existing children. To change the children, use `delete` and/or `append`/`insert_before`.
```

`UnexpectedChildren`, on a leaf:

```
`children` is not allowed: a `lemma` holds no children.
```

`ChildrenNotInheritable`:

```
`theory_X.section_Basics` has 3 children, which a `lemma` cannot hold. Move or delete them first.
```

`Bad<Class>NodeParent` — each node class's carries its own sentence
(EXCEPTIONS.md §3). `Theorem`'s `BadTheoremNodeParent`:

```
A `lemma` cannot be placed under `session_Arith`; it belongs inside a theory.
```

`Session`'s `BadSessionNodeParent`:

```
A `Session` cannot be inserted under `theory_X`. Use `new_session` to create a session.
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
