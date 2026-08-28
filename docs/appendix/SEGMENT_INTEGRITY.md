# Keeping emitted text self-delimiting

TAT's own attribution does not depend on this: the evaluator runs one node's
commands at a time and reports the spans it parsed, so a node cannot reach the
next node's commands.

The finished `.thy` is a different matter. Whoever builds the forest parses each
file as a whole, so a node that emits text which does not close — an unclosed
cartouche, an unclosed comment, a truncated command — produces a file in which
one span covers several nodes' text, or a `Malformed_Span`.

So each node's text is checked for balanced cartouches, comments and quotes
before it is accepted, and rejected at the node with a message naming what did
not close. Statement text comes from a language model, so this happens.

The check is cheap and it is also redundant with the evaluator, which will fail
to parse the same text. Its value is the error: it names the node and the
unclosed delimiter, where Isabelle would report a parse error some commands
later.
