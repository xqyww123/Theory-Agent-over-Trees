"""The prose translator (prose.py; COMPILATION.md §3) and the build reader
(test/ml_process.py).  Without Isabelle: §3's examples and the pins the
document cannot hold, by §3's one comparison rule; every entry of
prose.py's data tables pinned; the invariant and the fixpoint on the
hostile corpus (test/hostile_prose.py), with `lists` off and on; linear
time on the size cases; the renderer on pieces no reader made; the
reader leaving the renderer nothing to separate but what the agent typed;
the ROOT's cartouche; the comment translation.  Through the std harness:
three files the build reader must refuse.
Run: python -m pytest test/test_prose.py
"""

import contextlib
import gc
import io
import random
import re
import shutil
import signal
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from Isabelle_RPC_Host.unicode import ascii_of_unicode, pretty_unicode, symbol_explode

import hostile_prose
import test_session_theory as ts
from baselines import DOCS, fenced_blocks
from harness import text_of
from ml_process import BUILD_READER, ml_process, ml_string, read_back

from isabelle_theory_agent import compile as C, model as M

from isabelle_theory_agent import prose
from isabelle_theory_agent.prose import _cartouche, _comments_translated, document_cartouche, latex_of
from isabelle_theory_agent.std.common import english_cartouche

COMPILATION = DOCS / "COMPILATION.md"
HEADER = 'theory "TAT_Std_A"\n  imports "Main" "TAT_Std.TAT_Std"\nbegin\n'


def pinned(got: str, expected: str) -> bool:
    """§3's comparison rule: what the file gets, against a pin written in
    the `unicode` spelling.  A writer other than `latex_of` hands its text
    over after `ascii_of_unicode`."""
    return got == ascii_of_unicode(expected)


def section_3_s_pins() -> list[tuple[str, str]]:
    """§3's fence of line pairs: the prose, then `↦ ` and what it becomes."""
    [_, _, examples] = fenced_blocks(COMPILATION, "3.")
    pairs = [pair.split("\n") for pair in "\n".join(examples).split("\n\n")]
    assert all(len(pair) == 2 and pair[1].startswith("↦ ") for pair in pairs), pairs
    return [(text, out.removeprefix("↦ ")) for text, out in pairs]


# The pins §3's fence cannot hold: a leading space, an empty output, a
# control character, a newline, and the pins with `lists`.  (text, lists, expected)
CANNOT_HOLD = [
    ("a\x01b\tc\x7fd", False, "a b c d"), ("‹x \x05\x06 y›", False, "‹x    y›"), ("✐‹tag›", False, ""),
    ("⇙ alone", False, " alone"), ("▪ first\n▪ second", False, " first\n second"),
    ("‹x\n›", False, "‹x\n›"),                                   # a newline is a blank but not a space: the trim keeps it
    ("a\rb", False, "a\nb"), ("a\r\nb", False, "a\nb"),          # a carriage return a newline, as Isabelle reads it
    ("‹\\<foo›", False, ""),
    (r'@{term \"<x"}', False, ""),                               # the join `\<x`, a malformed symbol, filtered and trimmed
    ("✐‹tag› a", False, " a"), ("― a", False, " a"),
    ("― ‹see @{const f}›", False, "%\n\\isamarkupcmt{see ‹f›%\n}"),
    ("a ― ‹50% off› b", False, "a %\n\\isamarkupcmt{50% off%\n} b"),     # the closing brace on a line of its own
    ("▪ first\n▪ second", True, "▪ first\n▪ second"), ("▸ one\n➧ two", True, "▸ one\n➧ two"),
    ("▪‹x› y", True, "▪ ‹x› y"), ("▪x", True, "▪ x"), ("a ▪ b", True, "a  b"), ("∗‹▪ a›", True, "\\emph{ a}"),
    ("― ‹▪ a›", True, "%\n\\isamarkupcmt{ a%\n}"), ("\\<^latex>‹▪ a›", True, " a"),   # a body's item, at a line's start too
    ("✐‹m›▪ a", True, "▪ a"),                                    # the marker dropped, the item starts its output line
    ("Intro:\n  ▪ a\n  ▪ b", True, "Intro:\n  ▪ a\n  ▪ b"), ("  ▪ a", True, "  ▪ a"),   # indented items kept
    ("▪ a\n  ▪ nested\n▪ b", True, "▪ a\n  ▪ nested\n▪ b"),       # the agent's indentation nests
    ("▪", True, "▪"), ("▪\n▪ b", True, "▪\n▪ b"),                  # no space before a blank or the end
    ("▪ a\n\n▪ b", True, "▪ a\n\n▪ b"), ("▪ a\n\n\n▪ b", True, "▪ a\n\n\n▪ b"), ("text\n▪ a\nmore", True, "text\n▪ a\nmore"),
    ("▪ ― ‹c› x", True, "▪ %\n\\isamarkupcmt{c%\n} x"), ("▪ @{const f}", True, "▪ ‹f›"),
]

# One pin per edge of a script's word (§3, "A script's word"); (text, lists, expected)
WORD_EDGES = [
    ("a$n² a\\n² a{n² a}n² a%n² a&n² a#n² a~n² a^n²", False,
     "a$n‹²› a\\n‹²› a{n‹²› a}n‹²› a%n‹²› a&n‹²› a#n‹²› a~n‹²› a^n‹²›"),          # LaTeX before: none taken
    ("n²$a n²\\a n²{a n²}a n²%a n²&a n²#a n²~a n²^a", False,
     "‹n²›$a ‹n²›\\a ‹n²›{a ‹n²›}a ‹n²›%a ‹n²›&a ‹n²›#a ‹n²›~a ‹n²›^a"),          # LaTeX after: taken up to it
    ("(a b)² [a b]² “a b”² ‘a b’²", False, "‹(a b)²› ‹[a b]²› ‹“a b”²› ‹‘a b’²›"),     # a pair crosses its blanks
    ("(n² [n² “n² ‘n²", False, "(‹n²› [‹n²› “‹n²› ‘‹n²›"),                          # an opener with no partner ends it
    ("a)n² a]n² a”n² a’n² (a]n²", False, "a)‹n²› a]‹n²› a”‹n²› a’‹n²› (a]‹n²›"),    # so does a closer
    ('"n²" `n²` ("a")²', False, '"‹n²›" `‹n²›` ‹("a")²›'),                           # a quote outside every pair
    ("n². n², n²; n²: n²! n²? x₁,x₂", False, "‹n²›. ‹n²›, ‹n²›; ‹n²›: ‹n²›! ‹n²›? ‹x₁,x₂›"),   # trailing punctuation
    ("n².\\emph{x} n²,$m$ n².‹a b›", False, "‹n²›.\\emph{x} ‹n²›,$m$ ‹n²›.‹a b›"),   # before LaTeX too
    ("n²‹.› n²‹\"›x x²‹(›y", False, "‹n².› ‹n²\"x› ‹x²(y›"),                           # only in plain text
    ("a n² a\nn²", False, "a ‹n²› a\n‹n²›"), ("▪n² a▪n²", True, "▪ ‹n²› a‹n²›"),     # a blank, an item
    ("‹x›₁ ‹xs›₁ ‹∀›₁ ‹x y›₁ a‹›² x²‹›y @{term \"a b\"}x²", False,
     "‹x₁› ‹xs₁› ‹∀₁› ‹x y›‹₁› a‹²› ‹x²›y ‹a b›x‹²›"),                                # the agent's cartouches
    ("a‹⇩›b² a‹⇘›b‹⇙›² a‹ ›b² x‹⇧›2²", False, "ab‹²› ab‹²› ab‹²› x2‹²›"),            # one symbol no typesetting control applies to
    ("‹\\›<x² x²‹\\›<y ‹\\<alpha›>² (‹\\›<x)² (‹\\<alpha›>)²", False,
     "‹\\›<x‹²› ‹x²\\›<y >‹²› (‹\\›<x)‹²› (>)‹²›"),                                  # one ending in `\\` or malformed takes nothing after it
    ("x⇩\\✐‹m›<alpha> x²❙\\✐‹m›<y \\<^bold>\\✐‹m›<x⇩2 (a⇩\\✐‹m›<b)²", False,
     "‹x⇩\\›<alpha> ‹x²❙\\›<y ‹❙\\›<x‹₂› (‹a⇩\\›<b)‹²›"),                            # so does a typesetting control's
    ("x⇘ij⇙k (x⇗i⇖)²", False, "‹x⇘ij⇙k› ‹(x⇗i⇖)²›"),                                # the spans
    ("x⇘a⇗b⇙⇘c⇖d⇙ x⇘a‹⇙b⇘›c⇙", False, "x‹⇘a b⇙›‹⇘c d⇙› x‹a›{\\isasymopen}b{\\isasymclose}‹c›"),   # one with a mark paired outside it
    ("x⇘a›⇙ x⇘a⇗b⇙", False, "x‹a›{\\isasymclose} x‹⇘a b⇙›"),                       # or a mark with no partner at all
    ("($x$)² ((a$b$))² x²(a$b$) x²(a b) x²(y²)", False, "($x$)‹²› ((a$b$))‹²› ‹x²›(a$b$) ‹x²(a b)› ‹x²(y²)›"),   # pairs
    ("(a b²) (a \"b²\") f(x²)y ((a b)²)", False, "(a ‹b²›) (a \"‹b²›\") f(‹x²›)y (‹(a b)²›)"),   # the pair the script stands in
    ("([a)² f(x’)²", False, "([a)‹²› ‹f(x’)²›"),                                    # a closer of another kind: no partner
    ("x (\n▪ a)²\nx²(\n▪ b) (a ▪ b)²", True, "x (\n▪ a)‹²›\n‹x²›(\n▪ b) (a  b)‹²›"),     # no pair spans an item
    ("Note (a.\n\nb)² (a +\n b)²", False, "Note (a.\n\nb)‹²› (a +\n b)‹²›"),         # no pair spans a line
    ("(a ‹b\nc› d)e² (x⇘i\nj⇙)²", False, "(a ‹b\nc› d)e‹²› ‹(x⇘i\nj⇙)²›"),           # a newline inside a cartouche is none
    ("a▪n² ∗‹a▪n²›", False, "a‹n²› \\emph{a‹n²›}"),                                    # an item, whatever `lists` is
    ("\\<^latex>‹n›² x²\\<^latex>‹y› a\\<^latex>‹y›b² x²\\<^latex>‹y›b (\\<^latex>‹y›)²", False,
     "n‹²› ‹x²›y ay‹b²› ‹x²›yb (y)‹²›"),                                                 # the edges of a body read again
    ("(\\<^latex>‹a›)b² b²(a \\<^latex>‹q›)c (a \\<^latex>‹q›)c² (a $q$)c²", False,
     "(a)b‹²› ‹b²›(a q)c (a q)c‹²› (a $q$)c‹²›"),                                       # to a pair holding it, LaTeX
    ("∗‹a›n² a›n² @{xn²", False, "\\emph{a}n‹²› a{\\isasymclose}n‹²› @\\{xn‹²›"),   # pieces the reader wrote
    ("x²‹y› x²‹y z› x²@{const f} x²@{term \"a b\"}", False, "‹x²y› ‹x²›‹y z› ‹x²f› ‹x²›‹a b›"),
]
LIST_TEXTS = [text for text, lists, _ in CANNOT_HOLD + WORD_EDGES if lists]     # the Markdown lists, for `lists`


def test_compilation_md_section_3_s_examples():
    for text, expected in section_3_s_pins():
        assert pinned(latex_of(text), expected), (text, latex_of(text))


def test_the_pins_the_document_cannot_hold():
    for text, lists, expected in CANNOT_HOLD + WORD_EDGES:
        assert pinned(latex_of(text, lists), expected), (text, lists, latex_of(text, lists))


def test_a_kept_list_starts_on_a_line_of_its_own():
    """`document_cartouche` with `lists`: a line of its own for the content
    when an item is kept, so that every item line carries the command's
    indentation; none otherwise."""
    assert document_cartouche("▪ a", lists=True) == "‹\n▪ a›"
    assert document_cartouche("plain", lists=True) == "‹plain›"
    assert document_cartouche("▪ a") == "‹ a›"


def test_every_table_entry_has_a_pin():
    """Every key of prose.py's data tables occurs in some pin's input, and
    for a dict table that same pin's output holds the key's value."""
    pins = [(ascii_of_unicode(t), ascii_of_unicode(e)) for t, e in section_3_s_pins()]
    pins += [(ascii_of_unicode(t), ascii_of_unicode(e)) for t, _, e in CANNOT_HOLD + WORD_EDGES]
    for table in (prose._SPACING, prose._ONE_SYMBOL, prose._ITEMS, prose._COMMENTS, prose._LATEX_CHARACTERS,
                  prose._QUOTES, prose._PUNCTUATION):
        for key in table:
            assert any(key in text for text, _ in pins), key
    for table in (prose._FORMATTING, prose._SPANS, prose._STRAY, prose._BRACKETS):
        for key, value in table.items():
            assert any(key in text and value in out for text, out in pins), key


# --- the invariant (COMPILATION.md §3), by predicates written from Isabelle's definitions

_WELL_FORMED = re.compile(r"\\<\^?[A-Za-z][A-Za-z0-9_']*>")          # symbol.ML's grammar of a symbol
_COMMENT_SYMBOLS = ("\\<comment>", "\\<^cancel>", "\\<^latex>", "\\<^marker>")
_MARKDOWN_ITEMS = ("\\<^item>", "\\<^enum>", "\\<^descr>")


def _control_character(symbol: str) -> bool:
    return len(symbol) == 1 and (ord(symbol) < 32 or ord(symbol) == 127) and symbol != "\n"


def faults(output: str, lists: bool = False) -> list[str]:
    """How `output` breaks the invariant's three clauses.  Its marks pair as
    Isabelle's reader pairs them, so a stray mark stands in a plain run.  A
    plain run holding `\\<`, `@{` or a control character, or, but with
    `lists` at a line's start before a blank or the end, a Markdown item; a
    cartouche holding a comment symbol, an item, a malformed symbol or a
    control character; `ascii_of_unicode` changing the output."""
    found: list[str] = []
    symbols = symbol_explode(output)
    paired: set[int] = set()
    opened: list[int] = []
    for i, s in enumerate(symbols):
        if s == "\\<open>":
            opened.append(i)
        elif s == "\\<close>" and opened:
            paired |= {opened.pop(), i}
    depth, line_start, runs = 0, True, [[]]
    for i, s in enumerate(symbols):
        if i in paired:
            depth += 1 if s == "\\<open>" else -1
            runs.append([])
            line_start = False
        elif depth == 0:
            if lists and s in _MARKDOWN_ITEMS and line_start and (i + 1 == len(symbols) or symbols[i + 1] in " \n"):
                runs[-1].append(" ")
                line_start = False
                continue
            if s.startswith("\\<") or _control_character(s):
                found.append(f"a plain run holds {s!r}")
            line_start = s == "\n" or (line_start and s == " ")
            runs[-1].append(s)
        elif (s in _COMMENT_SYMBOLS or s in _MARKDOWN_ITEMS or _control_character(s)
              or (s.startswith("\\<") and not _WELL_FORMED.fullmatch(s))):
            found.append(f"a cartouche holds {s!r}")
    if any("@{" in "".join(run) for run in runs):
        found.append("a plain run holds @{")
    if ascii_of_unicode(output) != output:
        found.append("ascii_of_unicode changes it")
    return found


@pytest.mark.parametrize("lists", [False, True])
def test_the_invariant_holds_on_the_hostile_corpus(lists):
    """Every output keeps the three clauses and is a fixpoint; no call
    raises."""
    texts = hostile_prose.corpus() + (LIST_TEXTS if lists else [])
    broken = []
    for text in texts:
        out = latex_of(text, lists)
        if faults(out, lists) or latex_of(out, lists) != out:
            broken.append((text, out, faults(out, lists)))
    assert not broken, (len(broken), broken[:5])


class _Late(Exception):
    pass


@contextlib.contextmanager
def _backstop(seconds: float):
    """A fixed alarm: the harness's own deadline cannot interrupt a loop
    that never awaits."""
    def late(*_):
        raise _Late
    previous = signal.signal(signal.SIGALRM, late)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def _fastest(text: str) -> float:
    gc.disable()
    try:
        times = []
        for _ in range(3):
            start = time.perf_counter()
            latex_of(text)
            times.append(time.perf_counter() - start)
        return min(times)
    finally:
        gc.enable()


def _assert_linear(make, n: int) -> None:
    """The text at `4n` takes at most eight times the text at `n` — a
    quadratic cost gives about sixteen —, under a 30 s backstop."""
    with _backstop(30):
        ratio = _fastest(make(4 * n)) / _fastest(make(n))
    assert ratio <= 8, ratio


SIZE_CASES = {                                   # each name gives the length at 4n
    "depth 10,000 of emph, balanced": lambda n: "∗‹" * n + "x" + "›" * n,
    "depth 10,000 of footnote, balanced": lambda n: "\\<^footnote>‹" * n + "x" + "›" * n,
    "depth 10,000 of comment, balanced": lambda n: "―‹" * n + "x" + "›" * n,
    "depth 10,000 of latex, balanced": lambda n: "\\<^latex>‹" * n + "x" + "›" * n,
    "depth 10,000 of @{emph, balanced": lambda n: "@{emph ‹" * n + "x" + "›}" * n,
    "depth 10,000 of emph, unclosed": lambda n: "∗‹" * n + "x",
    "100,000 stray open marks": lambda n: "‹" * (10 * n),
    "100,000 stray close marks": lambda n: "›" * (10 * n),
    "100,000 span openers": lambda n: "⇘" * (10 * n),
    "100,000 unclosed @{emph": lambda n: "@{emph " * (10 * n),
    "100,000 nested @{": lambda n: "@{" * (10 * n),
    "100,000 unclosed strings inside @{": lambda n: '@{a "' * (10 * n),
    "100,000 closed strings inside @{": lambda n: '@{a "x" ' * (10 * n),
    "100,000 strings inside one closed @{term": lambda n: "@{term " + '"x" ' * (10 * n) + "}",
    "100,000 cartouches inside one closed @{term": lambda n: "@{term " + "‹x› " * (10 * n) + "}",
    "100,000 span markers inside one cartouche": lambda n: "‹" + "⇘" * (10 * n) + "›",
    "400,000 leading blanks inside one cartouche": lambda n: "‹" + " " * (40 * n) + "x›",
    "400,000 leading emph symbols inside one cartouche": lambda n: "‹" + "∗" * (40 * n) + "x›",
    "400,000 trailing blanks inside one cartouche": lambda n: "‹x" + " " * (40 * n) + "›",
    "200,000 plain characters": lambda n: "a " * (10 * n),
    "50,000 subscripts": lambda n: "x₁ " * (5 * n),
    "50,000 bare cartouches": lambda n: "‹x› " * (5 * n),
    "50,000 stray marks inside one cartouche": lambda n: "‹" + "› ‹" * (5 * n),
    "50,000 superscripts in one word": lambda n: "a²" * (5 * n),
    "50,000 words after a closer with no partner": lambda n: "x )" + " y²" * (5 * n),
    "50,000 openers before a superscript": lambda n: "(" * (5 * n) + "a²",
    "50,000 blanks inside one bracket pair": lambda n: "(" + "a " * (5 * n) + ")²",
}


@pytest.mark.parametrize("case", SIZE_CASES)
def test_the_size_cases_take_linear_time(case):
    _assert_linear(SIZE_CASES[case], 2_500)


def _pieces(seed: int, count: int):
    """`count` lists of up to six pieces: plain and cartouche pieces of up to
    four tokens of the hostile alphabet, and, about one in seven, an item
    piece, half of them holding a Markdown item and half such tokens."""
    r = random.Random(seed)

    def tokens() -> str:
        return "".join(r.choice(hostile_prose.ALPHABET) for _ in range(r.randint(0, 4)))
    for _ in range(count):
        yield [prose.Item(r.choice(prose._ITEMS) if r.random() < 0.5 else tokens()) if r.random() < 0.15 else
               (prose.Plain if r.random() < 0.5 else prose.Cartouche)(tokens()) for _ in range(r.randint(0, 6))]


@pytest.mark.parametrize("lists", [False, True])
def test_the_renderer_holds_the_invariant_on_any_pieces(lists):
    """§3: the renderer alone holds the invariant, items included, whatever
    it is handed — here pieces no reader made."""
    broken = []
    for pieces in _pieces(7, 5_000):
        out = prose._render(pieces, lists)
        if faults(out, lists) or latex_of(out, lists) != out:
            broken.append((pieces, out, faults(out, lists)))
    assert not broken, (len(broken), broken[:5])


def test_the_prose_writers_write_latex_of_back_in_the_unicode_spelling():
    """§3: `document_cartouche`, `english_cartouche` and the always-quoted
    writer write the `unicode` spelling (`pretty_unicode` leaves their
    output as it is), and the compile's conversion gives back `latex_of`'s
    bytes, and `_comments_translated`'s, on the corpus."""
    for lists in (False, True):
        for text in hostile_prose.corpus() + (LIST_TEXTS if lists else []):
            latex, out = latex_of(text, lists), document_cartouche(text, lists)
            own_line = "\n" if lists and any(s in prose._ITEMS for s in symbol_explode(latex)) else ""
            assert pretty_unicode(out) == out and ascii_of_unicode(out) == "\\<open>" + own_line + latex + "\\<close>", text
    for text in hostile_prose.corpus():
        period = "." if text and text[-1] not in ".!?" else ""
        out = english_cartouche(text, ("Lemma", ["q"]))
        assert pretty_unicode(out) == out and ascii_of_unicode(out) == (
            "\\<open>Lemma \\<open>q\\<close>. " + latex_of(text) + period + "\\<close>"), text
        out = M._always_quoted(text)
        assert pretty_unicode(out) == out and ascii_of_unicode(out) == M.string_token(_comments_translated(ascii_of_unicode(text))), text


def test_the_renderer_separates_only_what_the_agent_typed(monkeypatch):
    """With the plain-run step left out, a text with no lone `\\` and no `@`
    but an `@{`'s leaves no `\\<` and no `@{` in a plain run: the reader
    writes none, and the step separates only what the agent typed."""
    monkeypatch.setattr(prose, "_plain_run", lambda latex: latex)
    kept, broken = 0, []
    for text in hostile_prose.corpus():
        symbols = prose._symbols(text)
        if "\\" in symbols or any(s == "@" and symbols[i + 1:i + 2] != ["{"] for i, s in enumerate(symbols)):
            continue
        kept += 1
        out = latex_of(text)
        if any("plain run" in f for f in faults(out)):
            broken.append((text, out))
    assert kept > 10_000 and not broken, (kept, broken[:5])


SPAN_TOKENS = ["a", "²", "⇘", "⇙", "⇗", "⇖", "‹", "›"]                    # spans and marks crossing in a word


def test_a_script_s_word_shows_the_symbols_of_its_pieces(monkeypatch):
    """On the corpus, the pins and texts of spans and marks, the word pass loses no piece,
    and every cartouche piece it joins is its pieces' text and shows, rendered, the symbols
    they show apart (§3, "A script's word"): joined, no piece fuses with another into a
    symbol, and none changes what another shows."""
    word_pass, joins = prose._scripts_with_words, []

    def spy(out, controls, scripts):
        result, i = word_pass(out, controls, scripts), 0
        for p in result:
            if i < len(out) and p is out[i]:
                i += 1
                continue
            j = next((j for j in range(i + 1, len(out) + 1) if "".join(out[i:j]) == p), None)
            assert j is not None, (p, out[i:])
            joins.append((p, out[i:j]))
            i = j
        assert i == len(out), out[i:]
        return result

    def shown(p):
        if isinstance(p, prose.Cartouche):
            return [s for q in prose._cartouche_piece(p) for s in symbol_explode(q)]
        return prose._symbols(p)

    monkeypatch.setattr(prose, "_scripts_with_words", spy)
    for text in [*hostile_prose.corpus(), *hostile_prose.generated(10_000, 41, SPAN_TOKENS),
                 *(t for t, _ in section_3_s_pins()), *(t for t, _, _ in CANNOT_HOLD + WORD_EDGES)]:
        latex_of(text)
    changed = [(p, parts) for p, parts in joins if shown(p) != [s for q in parts for s in shown(q)]]
    assert len(joins) > 1_000 and not changed, (len(joins), changed[:5])


def test_the_roots_cartouche_keeps_paired_marks_and_quotes_stray_ones():
    """The pairing rule: a paired mark kept, a stray one `"`; on the corpus
    the marks of every `_cartouche` balance."""
    assert pinned(ascii_of_unicode(_cartouche("a ‹ b ‹c›")), '‹a " b ‹c››')
    for text in hostile_prose.corpus():
        depth = 0
        for s in symbol_explode(_cartouche(text)):
            depth += (s in ("‹", "\\<open>")) - (s in ("›", "\\<close>"))
            assert depth >= 0, text
        assert depth == 0, text


COMMENT_PINS = {
    "f x ― ‹x₁ is the first›": "f x ― ‹‹x₁› is the first›",
    "f x ⌦‹a \\<foo b›": "f x ⌦‹a   b›",
    "f x ⌦‹ wrong ›": "f x ⌦‹ wrong ›",                                    # no trim, no extra marks
    "f x \\<^latex>‹\\<foo y›": "f x \\<^latex>‹{\\isacharbackslash}{\\isacharless}foo y›",
    "f ‹a ― ‹x₁› b›": "f ‹a ― ‹‹x₁›› b›",                                  # inside a literal too
    "f x ―  ‹x₁›": "f x ―  ‹‹x₁››",                                        # two blanks: still a comment
    "f x ⌦ ‹a \\<foo b›": "f x ⌦ ‹a \\<foo b›",                            # a blank after `\<^cancel>`: no comment
    "f x \\<^latex>‹a ― ‹x₁››": "f x \\<^latex>‹a ― ‹x₁››",                # a `\<^latex>` body taken whole
    "f x ⌦‹x₁›": "f x ⌦‹x₁›", "f x \\<^latex>‹x₁›": "f x \\<^latex>‹x₁›",  # `₁` is two symbols, not a malformed one
    "f x = y": "f x = y",
}


def test_comments_inside_isabelle_text_are_translated():
    for text, expected in COMMENT_PINS.items():
        got = _comments_translated(ascii_of_unicode(text))
        assert pinned(ascii_of_unicode(got), expected), (text, got)


# --- the build reader, through the std harness

def said(refused) -> str:
    """What the process printed, as `read_back`'s assertion carries it."""
    return "".join(refused.value.args[0])


@pytest.mark.isabelle(deadline=300)
async def test_read_back_refuses_a_formal_comment_that_names_nothing(std_harness, tmp_path):
    """A build's presentation evaluates every formal comment's body."""
    with pytest.raises(AssertionError) as refused:
        await read_back(std_harness, HEADER + 'consts c :: "prop" \\<comment> \\<open>a @{const nonexistent_c} b\\<close>\n'
                                              "end\n", tmp_path)
    assert "Undefined constant" in said(refused) and "nonexistent_c" in said(refused)


@pytest.mark.isabelle(deadline=300)
async def test_read_back_refuses_a_header_text_that_names_nothing(std_harness, tmp_path):
    """The text before the `theory` line is read and presented too."""
    with pytest.raises(AssertionError) as refused:
        await read_back(std_harness, "text \\<open>a @{const nonexistent_c} b\\<close>\n" + HEADER + "end\n", tmp_path)
    assert "Undefined constant" in said(refused) and "nonexistent_c" in said(refused)


@pytest.mark.isabelle(deadline=300)
async def test_read_back_refuses_a_malformed_symbol_in_a_latex_comment(std_harness, tmp_path):
    """A `\\<^latex>` body is written raw by the presentation; the token
    check of `Command.read_span` alone refuses its malformed symbol."""
    with pytest.raises(AssertionError) as refused:
        await read_back(std_harness, HEADER + 'lemma "True \\<^latex>\\<open>\\<foo\\<close>"\n  by simp\nend\n', tmp_path)
    assert "Malformed command syntax" in said(refused)


# Hostile prose in every place a theory file carries it, and the lines the file
# gets for it (§3's comparison rule)
DESCRIPTION = ("Prose in every place, x₁ and n², where the proofs begin\n▪ a list, \\<^emph>‹see \\<^const>‹nonexistent_c››\n"
               "▪ with\ta tab, 🗏‹missing.txt›\ntheory B, @{const nonexistent_c")
TITLE = "▪ x₁, n², \\<^emph>‹see \\<^const>‹nonexistent_c›› and 🗏‹missing.txt›"      # an item: dropped in a heading
PASSAGE = "Under the heading:\n▪ x₁ and @{const nonexistent_c\n▪ n² ▪ mid-line, ‹x \x01y›"
ENGLISH = "Sums of n², by \\<^emph>‹see \\<^const>‹nonexistent_c››, ▪ mid-line, 🗏‹missing.txt›, @{const nonexistent_c"
CONCLUSION = "True ― ‹x₁ is the first, \\<^emph>‹see \\<^const>‹nonexistent_c››, 🗏‹missing.txt››"
EQUATION = "twice n = n + n ― ‹n² and ▪ an item and @{const nonexistent_c›"
WRITTEN = [
    "text ‹\nProse in every place, ‹x₁› and ‹n²›, where the proofs begin\n▪ a list, \\emph{see ‹nonexistent_c›}\n"
    "▪ with a tab, ‹missing.txt›\ntheory B, @\\{const nonexistent_c›\ntheory \"TAT_Std_P\"\n",
    "section ‹ ‹x₁›, ‹n²›, \\emph{see ‹nonexistent_c›} and ‹missing.txt››\n",
    "text ‹\nUnder the heading:\n▪ ‹x₁› and @\\{const nonexistent_c\n▪ ‹n²›  mid-line, ‹x  y››\n",
    "text ‹Lemma ‹prose_lemma›. Sums of ‹n²›, by \\emph{see ‹nonexistent_c›},  mid-line, ‹missing.txt›, @\\{const nonexistent_c.›\n",
    '  shows "True ― ‹‹x₁› is the first, \\\\emph{see ‹nonexistent_c›}, ‹missing.txt››"\n',
    '  "twice n = n + n ― ‹‹n²› and  an item and @\\\\{const nonexistent_c›"\n',
]


@pytest.mark.isabelle(deadline=300)
async def test_prose_reads_back_in_every_place(std_conversation, std_harness, tmp_path):
    """A theory's description, a heading's title, a passage, a lemma's
    `english`, a formal comment in a lemma's conclusion and one in a
    definition's equation, each hostile: evaluated, compiled, and read back
    as a build reads it; the lines the file gets pinned."""
    forest = std_conversation.forest
    async with std_conversation.client() as session:
        result = await session.call_tool("edit", {
            "action": "append", "target_id": "Sessions", "evaluate": True,
            "constructs": [ts.session("TAT_Suite", ts.theory("TAT_Std_P") | {"description": DESCRIPTION, "children": [
                {"kind": "section", "name": "Hostile", "title": TITLE, "children": [
                    {"kind": "text", "name": "passage", "text": PASSAGE},
                    {"kind": "lemma", "name": "prose_lemma", "statement": {
                        "english": ENGLISH, "for_any": [], "premises": [], "conclusion": CONCLUSION}},
                    {"kind": "definition", "english": "Twice a natural number", "constants": [{"name": "twice", "type": "nat ⇒ nat"}],
                     "equations": [EQUATION], "auto_reduction": True}]}]})]})
        assert not result.isError and "Error:" not in text_of(result), text_of(result)
    file = C.render(forest).files[C.Path("TAT_Suite/TAT_Std_P.thy")]
    await read_back(std_harness, file, tmp_path)
    for line in WRITTEN:
        assert ascii_of_unicode(line) in file, (line, file)


# The ROOT's descriptions: §2.3's hostile set, written untranslated through `_cartouche`
ROOT_DESCRIPTIONS = [
    "a › b ‹c›", "x₁ and n² ∀x", "see @{const sorted_wrt for details", "― ‹note› and ⌦‹x›", "▪ one\n▪ two",
    "line ending in begin\ntheory X\nimports Main\nbegin", 'a "quoted" word', "\\<foo y and \\<^> z", "a\x01b\tc",
    "x\x05y\x06z", "›››‹‹‹", "%\\emph{x}_$",
]


@pytest.mark.isabelle(deadline=300)
async def test_isabelle_reads_the_root(std_harness, tmp_path):
    """`isabelle sessions -D` reads a ROOT whose sessions' descriptions are
    hostile, each written through `_cartouche` and converted as the
    compile's ROOT is (COMPILATION.md §2)."""
    names = [f"H{i}" for i in range(len(ROOT_DESCRIPTIONS))]
    (tmp_path / "ROOT").write_text(ascii_of_unicode("".join(
        f'session "{n}" in "{n}" = "Pure" +\n  description {_cartouche(d)}\n\n' for n, d in zip(names, ROOT_DESCRIPTIONS))))
    for n in names:
        (tmp_path / n).mkdir()
    r = await std_harness.run_tool(["isabelle", "sessions", "-D", str(tmp_path)])
    assert r.returncode == 0 and set(names) <= set(r.stdout.split()), (r.stdout, r.stderr)


# --- the translations in every place, on Pure (the build reader's verdicts; COMPILATION.md §3)

PLACES = BUILD_READER + """
  val thy = Context.the_global_context ();
  val ctxt = Proof_Context.init_global thy;
  fun presented markdown text () = exported (Document_Output.output_document ctxt {markdown = markdown} (Input.string text));
  val head = "theory \\"A\\"\\n  imports Pure\\nbegin\\n";
  fun read text () = read_as_built thy text;
  fun report i (place, f) =
    (case verdict f of "ok" => () | r => writeln ("REFUSED " ^ string_of_int i ^ " " ^ place ^ ": " ^ r));
  fun six i x = List.app (report i)
    [("markdown", presented true x), ("plain", presented false x),
     ("text", read (head ^ "text \\<open>" ^ x ^ "\\<close>\\nend\\n")),
     ("before the header", read ("text \\<open>" ^ x ^ "\\<close>\\n" ^ head ^ "end\\n")),
     ("section", read (head ^ "section \\<open>" ^ x ^ "\\<close>\\nend\\n")),
     ("comment", read (head ^ "consts c :: \\"prop\\" \\<comment> \\<open>" ^ x ^ "\\<close>\\nend\\n"))];
  fun lists i (x, command, nested) = List.app (report i)
    [("markdown", presented true x), ("text", read (head ^ command ^ "\\nend\\n")),
     ("before the header", read (command ^ "\\n" ^ head ^ "end\\n")),
     ("nested", read (head ^ "section \\<open>S\\<close>\\n\\n" ^ nested ^ "end\\n"))];
  val accepted = Unsynchronized.ref 0;
  fun term_place i (raw, token) =
    (case Exn.result (fn () => Syntax.read_term ctxt raw) () of
      Exn.Exn _ => ()
    | Exn.Res _ => (accepted := ! accepted + 1; report i ("term", read (head ^ "term " ^ token ^ "\\nend\\n"))));
"""


async def refusals(harness, tmp_path, cases: str) -> list[str]:
    """`PLACES` and `cases` read inside a Pure theory (one exec argument is
    capped, so through a file); the `REFUSED` lines, after the end mark."""
    file = tmp_path / "places.ML"
    file.write_text(PLACES + cases + 'val _ = writeln ("CASES DONE " ^ string_of_int (! accepted));\n')
    r = await ml_process(harness, f"val _ = in_theory thy0 [{ml_string(str(file))}];", logic="Pure", base="Pure")
    lines = r.stdout.splitlines()
    assert r.returncode == 0 and any(line.startswith("CASES DONE") for line in lines), (r.stdout[-3000:], r.stderr[-3000:])
    return [line for line in lines if line.startswith(("REFUSED", "CASES DONE"))]


# Raw texts Isabelle refuses in every place, so the probe can fail (COMPILATION.md §3)
RAW_REFUSED = ["‹\\<comment>‹@{const nonexistent_c}››", "‹\\<comment>‹x\\<^sub>1››", "‹\\<foo›", "‹\\<›", "‹\\<^>›",
               "‹\\<^cancel>‹\\<foo y››", "a@{x}", "‹x\x05\x06y›"]


@pytest.mark.isabelle(deadline=600)
async def test_the_translations_are_accepted_in_the_six_places(std_harness, tmp_path):
    """The outputs of §3's fence, of the pins it cannot hold and of the
    hostile corpus, each in the six places: `output_document` with
    Markdown on and off, and as a build reads them, a `text` command, the
    `text` block before the header, a `section` and a formal comment in a
    command.  Each raw text of `RAW_REFUSED` is refused in every place —
    `‹x\\x05\\x06y›` by the YXML export alone."""
    outputs = sorted({latex_of(t) for t in [*(t for t, _ in section_3_s_pins()), *(t for t, _, _ in CANNOT_HOLD + WORD_EDGES),
                                             *hostile_prose.corpus()]})
    controls = [ascii_of_unicode(t) for t in RAW_REFUSED]
    said = await refusals(std_harness, tmp_path, "".join(f"val _ = six {i} {ml_string(x)};\n"
                                                         for i, x in enumerate(controls + outputs)))
    refused = {}
    for line in said[:-1]:
        i, rest = line.split(" ", 2)[1:]
        refused.setdefault(int(i), set()).add(rest.split(":")[0])
    six = {"markdown", "plain", "text", "before the header", "section", "comment"}
    assert all(refused.get(i) == six for i in range(len(controls))), (refused, said[:20])
    assert not [line for line in said[:-1] if int(line.split(" ")[1]) >= len(controls)], said[:20]


@pytest.mark.isabelle(deadline=600)
async def test_the_lists_are_accepted_in_the_text_places(std_harness, tmp_path):
    """The outputs with `lists` of the corpus and of the hand-made lists:
    `output_document` with Markdown on, and as a build reads them a `text`
    command, the block before the header and a `text` command nested under
    a heading as `emit_lines` indents it, each written by
    `document_cartouche(…, lists=True)`.  An item mid-line, or directly
    before a cartouche, written raw in a `text` command is refused."""
    texts = sorted(set(hostile_prose.corpus() + LIST_TEXTS))
    def nested(command: str) -> str:
        """The command as `emit_lines` writes it under a heading."""
        out = io.StringIO()
        M.emit_lines(1, out, command)
        return out.getvalue()
    cases = [(latex_of(t, lists=True), ascii_of_unicode(c), ascii_of_unicode(nested(c)))
             for t in texts for c in ["text " + document_cartouche(t, lists=True)]]
    controls = [(x, c, nested(c)) for x in ("a \\<^item> b", "\\<^item>\\<open>x\\<close> y") for c in ["text \\<open>" + x + "\\<close>"]]
    said = await refusals(std_harness, tmp_path, "".join(f"val _ = lists {i} ({ml_string(x)}, {ml_string(c)}, {ml_string(n)});\n"
                                                         for i, (x, c, n) in enumerate(controls + cases)))
    refused = [line for line in said[:-1] if int(line.split(" ")[1]) >= len(controls)]
    assert not refused, refused[:20]
    assert all(any(line.startswith(f"REFUSED {i} text:") for line in said) for i in range(len(controls))), said[:10]


@pytest.mark.isabelle(deadline=600)
async def test_the_comment_translations_are_accepted_in_the_term_place(std_harness, tmp_path):
    """Each corpus text as the body of each comment kind inside a term,
    `f x ― ‹…›`: every term the evaluation reads, written through the
    always-quoted writer and the compile's conversion, as a build reads it
    in a `term` command.  `f x ― ‹x₁ is the first›` untranslated is
    refused."""
    raws = [ascii_of_unicode(f"f x {kind}‹{t}›") for t in hostile_prose.corpus() for kind in ("― ", "⌦", "\\<^latex>")]
    control = ascii_of_unicode("f x ― ‹x₁ is the first›")
    cases = [(control, ascii_of_unicode(M.string_token(control)))] + [(raw, ascii_of_unicode(M._always_quoted(raw))) for raw in raws]
    said = await refusals(std_harness, tmp_path, "".join(f"val _ = term_place {i} ({ml_string(r)}, {ml_string(t)});\n"
                                                         for i, (r, t) in enumerate(cases)))
    assert said[0].startswith("REFUSED 0 term:"), said[:5]
    assert not said[1:-1], said[1:20]
    assert int(said[-1].split()[-1]) > 30_000, said[-1]                 # most terms read: the probe is not vacuous


# --- LaTeX, outside TAT: §3's fence in Isabelle's three wrappers, compiled (optional)

LATEX = """
  fun property name props = the_default "" (Properties.get props name);
  fun latex body = implode (map latex_tree body)
  and latex_tree (XML.Text s) = s
    | latex_tree (XML.Elem ((name, props), body)) =
        if name = Markup.document_latexN orelse name = Markup.latex_outputN then latex body
        else if name = Markup.latex_macro0N then "\\\\" ^ property "name" props
        else if name = Markup.latex_macroN then "\\\\" ^ property "name" props ^ "{" ^ latex body ^ "}"
        else if name = Markup.latex_environmentN then
          "%\\n\\\\begin{" ^ property "name" props ^ "}%\\n" ^ latex body ^ "%\\n\\\\end{" ^ property "name" props ^ "}"
        else error ("no LaTeX for the markup " ^ name);
  val ctxt = Proof_Context.init_global (Context.the_global_context ());
  fun rendered markdown text =
    writeln ("@@" ^ latex (Document_Output.output_document ctxt {markdown = markdown} (Input.string text)) ^ "@@END");
"""

PREAMBLE = (  # mkroot's root.tex, less the parts a single text needs not
    "\\documentclass[11pt,a4paper]{article}\n\\usepackage[T1]{fontenc}\n\\usepackage{isabelle,isabellesym}\n"
    "\\usepackage{pdfsetup}\n\\urlstyle{rm}\n\\isabellestyle{it}\n\\begin{document}\n\\begin{isabellebody}%\n"
    "\\setisabellecontext{X}%\n")
WRAPPERS = {                                     # how Isabelle's presentation writes a `text`, a heading, a formal comment
    "text": ("\\begin{isamarkuptext}%\n", "%\n\\end{isamarkuptext}\\isamarkuptrue%\n"),
    "heading": ("\\isamarkupsection{", "%\n}\n\\isamarkuptrue%\n"),
    "comment": ("\\isacommand{consts}\\isamarkupfalse%\n\\ c\\ {\\isacharcolon}{\\isacharcolon}\\ prop\\ %\n\\isamarkupcmt{",
                "%\n}\n"),
}
# The fence's prose whose LaTeX a document build refuses — the agent's own LaTeX, as Isabelle's would be: after an
# `@{` that does not close, a `_`; a malformed symbol's tail, a `^`; a backslash typed directly before a symbol
ENGINES = ("lualatex", "pdflatex")
LATEX_FAILURES = {"see @{const sorted_wrt for details", "\\<^> x", "\\∀"}


def compiled(directory, name: str, engine: str) -> bool:
    for _ in range(2):
        r = subprocess.run([engine, "-interaction=nonstopmode", "-halt-on-error", name + ".tex"], cwd=directory,
                           capture_output=True, text=True, errors="replace", timeout=120)
        if r.returncode != 0:
            return False
    return True


@pytest.mark.isabelle(deadline=900)
async def test_the_examples_compile(std_harness, tmp_path):
    """Each output of §3's fence, and three `english`s with their leads, as
    Isabelle's presentation renders them (`output_document`, Markdown on
    for a `text`, off for a heading and a formal comment), in Isabelle's
    three wrappers under mkroot's preamble, two passes each under lualatex
    and pdflatex: every one compiles but `LATEX_FAILURES`, the agent's own
    LaTeX; a `%` in a formal comment's body compiles, since the closing
    brace stands on a line of its own."""
    missing = [e for e in ENGINES if not shutil.which(e)]
    if missing:
        pytest.skip("not installed: " + ", ".join(missing))
    texts = [t for t, _ in section_3_s_pins()] + ["a ― ‹50% off› b", "∗‹see ― ‹10% more››"]
    contents = [latex_of(t) for t in texts]
    for english, lead in (("The sum of the first n odd numbers is n², by ∗‹induction› on \\<^const>‹sum_upto›", ("Lemma", ["sum_odd"])),
                          ("Parity", ("Definition", ["even", "odd"])), ("Reversal keeps the length", ("Lemma", ["rev_length"]))):
        texts.append(f"{lead}: {english}")
        contents.append(ascii_of_unicode(english_cartouche(english, lead))[len("\\<open>"):-len("\\<close>")])
    cases = tmp_path / "latex.ML"
    cases.write_text(LATEX + "".join(f"val _ = rendered {str(kind == 'text').lower()} {ml_string(content)};\n"
                                     for content in contents for kind in WRAPPERS))
    r = await ml_process(std_harness, f"val _ = in_theory thy0 [{ml_string(str(cases))}];", logic="Pure", base="Pure")
    rendered = re.findall(r"@@(.*?)@@END", r.stdout, re.S)
    assert r.returncode == 0 and len(rendered) == len(texts) * len(WRAPPERS), (r.stdout[-2000:], r.stderr[-2000:])
    home = await std_harness.run_tool(["isabelle", "getenv", "-b", "ISABELLE_HOME"])
    for f in (Path(home.stdout.strip()) / "lib" / "texinputs").iterdir():
        shutil.copy(f, tmp_path)
    jobs = []
    for i, (t, kind) in enumerate((t, kind) for t in texts for kind in WRAPPERS):
        for engine in ENGINES:
            name = f"case{i}_{engine}"
            before, after = WRAPPERS[kind]
            (tmp_path / f"{name}.tex").write_text(PREAMBLE + before + rendered[i] + after + "\\end{isabellebody}%\n\\end{document}\n")
            jobs.append((t, kind, engine, name))
    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(lambda job: compiled(tmp_path, job[3], job[2]), jobs))
    failed = {(t, kind, engine) for (t, kind, engine, _), ok in zip(jobs, results) if not ok}
    assert {t for t, _, _ in failed} <= LATEX_FAILURES, sorted(failed)
    assert all(t in {x for x, _, _ in failed} for t in LATEX_FAILURES), sorted(failed)     # the probe can fail
