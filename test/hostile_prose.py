"""The hostile texts of test/test_prose.py, against which COMPILATION.md
§3's invariant is asserted: `ALPHABET`, 81 hostile tokens, and
`generated`, the seeded generator over it; `HAND_PICKED`, 212 texts written
by hand to break the translator; `TARGETED`, 16 aimed at the joins and the
control characters; `READER_JOINS`, 8 in which the reader joins a `\\` and a
`<`, or an `@` and a `{`, across a piece it drops.  `corpus()` is the
whole corpus: the texts written by hand and 20,000 generated; the
Markdown lists are test_prose.py's `lists` pins."""

import random

ALPHABET = [
    'a', ' ', '\n', '\t', '@', '{', '}', '\\', '<', '>', '^', '‹', '›', '\\<open>', '\\<close>', '\\<^', '\\<',
    '\\<^>', '\\<>', '\\<forall>', '\\<^sub>', '\\<^sup>', '\\<^bold>', '\\<^emph>', '\\<^footnote>', '\\<^cancel>',
    '\\<^latex>', '\\<^marker>', '\\<comment>', '―', '⌦', '✐', '@{', '@{term ', '@{emph ', '@{text ', '@{verbatim ',
    '@{noindent', '"', '`', '[', ']', '[x="]"]', '▪', '∗', '❙', '⇩', '⇧', '²', '%', '$', '\\<^item>', '\\<^enum>',
    '\\<^noindent>', '\\<^const>', '\\<^bsub>', '\\<^esub>', '⇘', '⇙', '\\<foo', '\\<foo>', 'é', 'x₁',
    '\\<^verbatim>', '_', '𝐚', '🗏', '\x0b', '\x01', '\r', '\\emph{', '\\\\', '\x7f', '\x05', '\x06', '<comment>',
    '<^item>', '<open>', '<close>', '<foo', '\\\\<comment><comment>‹@{const nonexistent_c}›',
]

HAND_PICKED = [
    '∗‹a ∗‹b ❙‹c›››', '@{emph ‹@{bold ‹x @{const nonexistent_c}›}›}', '―‹a ―‹b @{const nonexistent_c}››',
    '\\<^footnote>‹∗‹x› ▪ y›', '∗‹see ‹rev ‹xs›››', '@{emph ‹see \\<^const>‹nonexistent_c› and ‹q››}', '∗‹see',
    '‹rev', '@{term ‹x', '@{term "x', '@{term [show_types', '―‹note', '⌦‹x', '\\<^latex>‹\\foo', '@{emph ‹a',
    'a ‹b ‹c›', 'x⇩1 x₁ 𝐱 ❙x ⇘a⇙ ⇗b⇖ ▪ ― ⌦ ✐ 🗏', 'n² terms', 'x⇩', 'x⇩\n', 'x⇩ y', 'x⇩⇧2', '❙', '⇘unpaired', '⇙',
    'a⇩‹b›', '― ‹ok›', '―\n‹c›', '\\<comment>\t‹c›', '\\<^cancel> ‹x›', '\\<^latex> ‹x›', '✐‹tag› a', '\\<^marker>',
    'a ― b', '@{term [show_types, mode=latex] "x"}', '@{thm [display, source] foo}', '@{term [x="]"] y}',
    '@{term "a \\"b\\" c"}', '@{term `x`}', '@{text "‹"} and ›', '@{emph "‹"} ›', '@{text "›"} x',
    '@{emph "a ‹ b"} c › d', '@{footnote `‹`}›', '@{x ‹a›‹b›}', '\\<^const>‹x›‹y›',
    '\\emph{x} $\\forall x$ \\\\ 50\\% \\verb|@{x}|', '\\begin{itemize}\\item a\\end{itemize}', '%comment', 'a } b',
    '\\url{a@b.org}', '\\url{a@{b}}', '\\textbf{∀x}', '$x₁ + n²$', '▪ a\n▪ b', '  ▪ a\n    ▪ b', '▪▪ a', '▪\ta',
    '▪‹x›', 'a\n\n▪ b', '▪ a\n\n\n▪ b\n  c', '\\<^enum> a\n\\<^descr> b', 'a ▪ b', '▪ a\tb', '\t▪ a', ' ▪ ∗‹x› ▪ y',
    '▪ ⌦‹x› ▪ y', '\\<^item>\\<^item>', '', ' ', '\n', '\n\n', 'a\x00b', 'a\x0bb', 'a\x0cb', 'a\x7fb', 'a\rb', '@',
    '@@{x}', '@\\<^marker>‹m›{', '@‹x›{', '@⌦‹x›{y}', 'a@∀', '@{}', '@{ }', 'x@{}y', '@{', '{@}{x}', '\\∀',
    '\\\\<^item>', '\\⌦‹x›<y', '\\▪<foo>', 'a\\', '\\', '\\<^>', '\\<>', '\\<^', '\\<', '\\<foo', '\\<foo>',
    '\\<^foo>', '\\<^foo>‹x›', '‹\\<^>›', '‹\\<foo›', '‹\\<>›', '‹(* ‹x› *)›', '‹\\<^latex>‹\\foo››',
    '‹―‹@{const nonexistent_c}››', '‹x⇩›', '‹▪ a›', '‹\\<^latex> x›', '‹\\<^cancel>‹@{const nonexistent_c}››',
    '‹@{const nonexistent_c}›', '‹⇘a›', '‹\t▪›', '\\<^verbatim>‹@{x}›', '@{ML_text ‹x›}', '@{1abc x}',
    '🗏‹missing.txt›', '\\<^url>‹http://a.org/%20›', '@{cite nonexistent_key}', '\\<^here>', '@{goals}',
    '\\<^theory_text>‹lemma x: y›', '@{term "x\\<^sub>1"}', '@{verbatim ‹\\<forall>›}', '\\<^term>‹\\<^item>›',
    '@{term ‹a ― ‹c› b›}', '@{text "―‹@{const nonexistent_c}›"}', '\\<^noindent>abc', '@{noindent} a',
    '\\<^noindent>‹x›', '⇤ a', '@{medskip ‹x›}', '\\<^emph> ‹x›', '\\<^bold>text', '\\<^bold>‹A› and @{bold ‹B›}',
    '∗‹▪ a›', '∗‹a\n\nb›', '\\<^footnote>‹x›', 'Lemma ‹rev_length›. ∀x ∈ A. x ≤ y …', 'a\\<^sub>\\<^sup>2',
    '\\<^emph>‹x\\<^sub>›', '@{term a @{const b}', 'x\\<^sub>1 here', 'n\\<^sup>2 terms', '\\<^noindent> a',
    'a \\<^item> b', 'a \\<^emph>‹see \\<^const>‹nonexistent_c›› b', 'a ‹\\<^const>‹nonexistent_c›› b',
    'a \\<^cancel>‹@{const nonexistent_c}› b', 'a @{const nonexistent_c} b', 'a @{term [show_types] "x"} b',
    'plain ‹quoted› text', 'a @{const nonexistent_c b', 'the sum of n² terms', 'x₁ and x₂₃', '▪ one\n▪ two',
    '∗‹care› and ❙‹bold› and 🗏‹missing.txt›', '∀x. P x ⟶ Q', 'Use \\<^verbatim>‹@{foo}› here',
    '@{emph ‹see @{const sorted}›}', '@{text "@{const x}"}', '\\<^bold>‹A› and @{emph ‹@{const f}›}',
    '@{term rev left open, \\<^const>‹never closed', '\\<^const>‹foo', 'x \\<alpha>‹y›', 'A \\<^cancel>‹wrong› right',
    '⌦‹a›', 'a ― ‹note @{const nonexistent_c}› b', 'a \\<comment>‹c ∀›', 'a ✐‹tag› b',
    'a \\<^latex>‹\\textbf{L} ∀ @{x}› b', '\\<comment>', '\\<^cancel> x', 'a ‹ b ‹c›', 'a › b', '‹unclosed rest $x$',
    'a@\\<forall> b', 'a@\\<^marker>‹m›{x}', 'a\\\\<^marker>‹m›<x', 'x\\<^sub>', 'x\\<^sub>\\<^sup>2',
    '⇘ab⇙ and ⇗cd⇖ and ⇘unpaired', '\\<foo> \\<foo \\< \\<^foo \\<^foo>',
    '\\emph{e} $x_1$ \\textbf{b} 50% {x} \\{ \\}', '@{cite [p. 3] key}', '@{url ‹http://x.org/a%20b›}',
    '@{thm [source] foo_def}', '\\<^term>‹rev xs›', '@{term ‹rev xs›}', '@{const "sorted"}', '‹', '›', '\\<open>',
    '\\<close>', '‹a ― ‹@{const nonexistent_c}› b›', '‹x \\<^latex>‹L››', '‹x\\<foo y›', '\\<^footnote>‹▪ x›',
    '\\<^emph>‹\\<^noindent> x›', 'tab\there\tand ▪ item', 'café — “q” » ◇', '\\<^item>‹x›', '\\<^sub>‹x›',
    '\\<^file>‹f›', 'Lemma ‹rev_length›. Reversal keeps the length.', 'a\\\\', 'end with @', '‹a›‹b›', '@{x}@{y}',
    '\\<^emph>‹a›\\<^bold>‹b›',
]

TARGETED = [
    '‹\\\\<comment><comment>‹@{const nonexistent_c}››', '‹\\\\<^item><^item> x›', '‹a\\\\<x<b›',
    '@{text "\\<comment>‹@{const nonexistent_c}›"}', '@{text "‹"} and ‹a›', '@{text "›"} b', '@{text "a ‹ b"}',
    '@{term "x \x05\x06 y"}', '‹x \x05\x06 y›', '∀\x05', 'x⇩\x05', '‹\\<^marker>‹t› ―‹@{const nonexistent_c}››',
    '\\\\‹x›', '@‹x›', 'a\\\\<^item>', '‹\\\\\\<^item>›',
]

READER_JOINS = [
    '@{term \\"<x"}', '@{term ‹a\\›‹<b›}', '@{term x\\‹<comment>‹@{const nonexistent_c}››}', '@{term ‹x\\›‹<open>›}',
    '∗‹a\\›<b', '‹a\\›‹›<b', '\\✐‹›<comment>‹x›', '‹a@›{x}',
]


def generated(count: int, seed: int, alphabet: list[str] = ALPHABET) -> list[str]:
    """`count` texts of 1 to 16 tokens drawn from `alphabet`, seeded."""
    r = random.Random(seed)
    return ["".join(r.choice(alphabet) for _ in range(r.randint(1, 16))) for _ in range(count)]


def corpus() -> list[str]:
    """The texts written by hand, then 10,000 generated over the whole
    alphabet and 10,000 over its first 40 tokens."""
    return HAND_PICKED + TARGETED + READER_JOINS + generated(10_000, 31) + generated(10_000, 32, ALPHABET[:40])
