"""Every text the compile puts inside a cartouche but the lead's names,
which std/common.py's `english_cartouche` writes as they stand, being
checked identifiers (COMPILATION.md §3): prose through `latex_of` and
`document_cartouche`, as LaTeX in which Isabelle's document presentation
finds nothing to evaluate; the bodies of the formal comments inside
Isabelle text through `_comments_translated`; the ROOT's description,
untranslated, through `_cartouche`.

`latex_of` reads its text as Isabelle reads document text, into pieces,
and renders them; the reader is best effort, and the renderer alone holds
COMPILATION.md §3's invariant, placing the items and cutting what it
writes again before it writes it.  Two readers restate Isabelle's:
`_document`, with `_closers`, `_string_ends` and `_antiquotation_parts`,
reads as `Antiquote.parse_comments`, `Comment.scan_inner` and the head of
`Document_Antiquotation.parse_antiq` do (antiquote.ML, comment.ML,
document_antiquotation.ML), but for two departures on text Isabelle
accepts — it reads `\\<^marker>‹…›` as a comment and drops it, and it does
not recognise a backquoted string in an `@{…}` body — and leniently where
Isabelle refuses; `_comments_translated` reads as `Comment.read_body`
(comment.ML)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TypeGuard, cast

from Isabelle_RPC_Host.unicode import ascii_of_unicode, is_identifier, is_malformed, pretty_unicode, symbol_explode

_OPEN, _CLOSE = "\\<open>", "\\<close>"
_COMMENTS = ("\\<comment>", "\\<^cancel>", "\\<^latex>", "\\<^marker>")
_COMMENT, _CANCEL, _LATEX = _COMMENTS[:3]
_FORMATTING = {"emph": "\\emph", "bold": "\\textbf", "footnote": "\\protect\\footnote"}
_SPACING = ("noindent", "smallskip", "medskip", "bigskip")
_ONE_SYMBOL = ("\\<^sub>", "\\<^sup>", "\\<^bold>")
_SPANS = {"\\<^bsub>": "\\<^esub>", "\\<^bsup>": "\\<^esup>"}
_ITEMS = ("\\<^item>", "\\<^enum>", "\\<^descr>")
_STRAY = {_OPEN: "{\\isasymopen}", _CLOSE: "{\\isasymclose}"}     # isabellesym.sty's macros for the marks
_DEPTH = 32                                                        # reading again stops here (§3)

_CONTROL_CHARACTERS = re.compile(r"[\x00-\x09\x0b\x0c\x0e-\x1f\x7f]")    # all but the newline and the carriage return
_NAME_CHARACTER = re.compile(r"[A-Za-z0-9_'.]")                    # of an `@{…}` body's name
_BLANKS = (" ", "\t", "\n", "\r", "\x0b", "\x0c")                  # `Symbol.is_blank`, symbol.ML
_LATEX_CHARACTERS = frozenset("$\\{}%&#~^")                       # what LaTeX reads in plain text
_BRACKETS = {")": "(", "]": "[", "\u201d": "\u201c", "\u2019": "\u2018"}   # closing: opening
_QUOTES = ('"', "`")                                               # neither opening nor closing
_PUNCTUATION = frozenset(".,;:!?")                                 # left out at the end of what a script takes


class Plain(str):
    """A plain piece: LaTeX plain text."""


class Cartouche(str):
    """A cartouche piece: text for Isabelle to typeset as quasi-formal
    text, which the renderer cuts and filters."""


class Item(str):
    """An item piece: a Markdown item, which `_render` keeps or drops."""


Piece = Plain | Cartouche | Item


class Body(list[Plain | Cartouche]):
    """A body read again: its pieces, settled by its own reading, one element that no word
    of the text around it enters, until `_document` splices it in after its word pass."""


def latex_of(text: str, lists: bool = False) -> str:
    """Prose as LaTeX in which Isabelle's document presentation finds nothing to
    evaluate (COMPILATION.md §3): the agent's spelling to `\\<name>`, every ASCII
    control character but the newline a space, a carriage return a newline, the text
    read as document text into plain, cartouche and item pieces, the pieces rendered — a
    plain run with no `\\<` and no `@{`, a cartouche with nothing Isabelle evaluates or
    refuses; with `lists`, a Markdown item that starts a line kept for Isabelle to build a
    list from."""
    return _render(_document(_symbols(text), depth=0), lists)


def document_cartouche(text: str, lists: bool = False) -> str:
    """Prose as a `text` command or a heading carries it: `‹` + latex_of(text, lists) +
    `›`, in the `unicode` spelling (`pretty_unicode`), which the compile's conversion
    gives back; with `lists` and an item kept, the content starts on a line of its own, so
    that every item line carries the indentation `emit_lines` gives the command's later
    lines."""
    latex = latex_of(text, lists)
    own_line = lists and any(s in _ITEMS for s in symbol_explode(latex))
    return "‹" + ("\n" if own_line else "") + pretty_unicode(latex) + "›"


def _comments_translated(text: str) -> str:
    """Isabelle text in the `\\<name>` spelling, returned in the same spelling, read as
    Isabelle's `Comment.read_body` reads it (COMPILATION.md §3): the body of every
    `\\<comment>` cartouche through `latex_of`, of every `\\<^cancel>` cartouche through
    the content filter, of every `\\<^latex>` cartouche as it is but for its malformed
    symbols, written as their characters."""
    symbols = symbol_explode(text)
    partners = _partners(symbols, _OPEN, _CLOSE)
    out: list[str] = []
    i = 0
    while i < len(symbols):
        s = symbols[i]
        j = _comment_at(symbols, i, partners) if s in (_COMMENT, _CANCEL, _LATEX) else None
        if j is None:
            out.append(s)
            i += 1
            continue
        body = symbols[j + 1:partners[j]]
        out += symbols[i:j + 1]
        if s == _COMMENT:
            out.append(latex_of("".join(body)))
        elif s == _CANCEL:
            out += _filtered(body)
        else:
            out += (_characters(b) if is_malformed(b) else b for b in body)
        out.append(symbols[partners[j]])
        i = partners[j] + 1
    return "".join(out)


def _cartouche(text: str) -> str:
    """The ROOT's description as one cartouche that closes (COMPILATION.md §3): the
    pairing rule, a stray mark `"`."""
    symbols = symbol_explode(ascii_of_unicode(text))
    stray = _unpaired(symbols, _OPEN, _CLOSE)
    return "‹" + "".join('"' if i in stray else s for i, s in enumerate(symbols)) + "›"


# --- step 1, and what a symbol is

def _symbols(text: str) -> list[str]:
    """The agent's spelling to `\\<name>` (`ascii_of_unicode`), every ASCII control
    character but the newline and the carriage return, and DEL, a space — a tab, VT and FF
    among them, which Markdown refuses —, then cut into Isabelle's symbols
    (`symbol_explode`, a carriage return read as a newline)."""
    return symbol_explode(_CONTROL_CHARACTERS.sub(" ", ascii_of_unicode(text)))


def _control(symbol: str) -> bool:
    return symbol.startswith("\\<^") and not is_malformed(symbol)


def _blank(symbol: str) -> bool:
    """Isabelle's `Symbol.is_blank`."""
    return symbol in _BLANKS


def _operand(symbol: str) -> bool:
    """What a one-symbol typesetting control applies to: a plain character or a
    well-formed symbol that is neither a blank, a control symbol, a comment symbol, an item
    nor a mark."""
    return not (_blank(symbol) or _control(symbol) or symbol in _COMMENTS or symbol in _ITEMS or symbol in _STRAY
                or is_malformed(symbol))


def _applies(symbols: list[str], i: int) -> bool:
    """Whether the one-symbol typesetting control at `i` has an operand."""
    return i + 1 < len(symbols) and _operand(symbols[i + 1])


def _characters(malformed: str) -> str:
    """A malformed symbol as its characters, the backslash and the `<` written as
    Isabelle's macros for them (latex.ML)."""
    return malformed.replace("\\", "{\\isacharbackslash}").replace("<", "{\\isacharless}")


# --- the tables the readers consult, each built in one pass

def _partners(symbols: list[str], opening: str, closing: str) -> dict[int, int]:
    """The partner map: each `closing` paired with the nearest `opening` before it not
    yet paired, in one pass with a stack; the index of an open mark to its partner's."""
    out: dict[int, int] = {}
    stack: list[int] = []
    for i, s in enumerate(symbols):
        if s == opening:
            stack.append(i)
        elif s == closing and stack:
            out[stack.pop()] = i
    return out


def _unpaired(symbols: list[str], opening: str, closing: str) -> set[int]:
    """The positions of the `opening` and `closing` marks the partner map leaves without
    a partner; of cartouche marks, the stray ones."""
    partners = _partners(symbols, opening, closing)
    return {i for i, s in enumerate(symbols) if s in (opening, closing)} - partners.keys() - set(partners.values())


def _string_ends(symbols: list[str]) -> list[int | None]:
    """For every position, the first `"` at or after it, a backslash escaping the symbol
    after it (`Symbol_Pos.scan_string_qq`); one backward pass."""
    out: list[int | None] = [None] * (len(symbols) + 2)
    for k in range(len(symbols) - 1, -1, -1):
        out[k] = k if symbols[k] == '"' else out[k + 2] if symbols[k] == "\\" else out[k + 1]
    return out


def _closers(symbols: list[str], closing: str, partners: dict[int, int],
             string_ends: list[int | None]) -> list[int | None]:
    """For every position, the first `closing` at or after it outside every `"…"` string
    and cartouche, as `Antiquote.scan_antiq_body` reads an `@{…}` body but for
    backquoted strings, which it does not recognise: no brace nesting; one backward
    pass."""
    out: list[int | None] = [None] * (len(symbols) + 1)
    for k in range(len(symbols) - 1, -1, -1):
        s = symbols[k]
        if s == closing:
            out[k] = k
        elif s == '"':
            end = string_ends[k + 1]
            out[k] = None if end is None else out[end + 1]
        elif s == _OPEN and k in partners:
            out[k] = out[partners[k] + 1]
        else:
            out[k] = out[k + 1]
    return out


def _comment_at(symbols: list[str], i: int, partners: dict[int, int]) -> int | None:
    """The open mark of the cartouche the comment symbol at `i` takes
    (`Comment.scan_inner`): Isabelle's blanks may stand after `\\<comment>`, nothing
    after the other three; None when no paired cartouche follows."""
    j = i + 1
    if symbols[i] == _COMMENT:
        while j < len(symbols) and _blank(symbols[j]):
            j += 1
    return j if j < len(symbols) and symbols[j] == _OPEN and j in partners else None


# --- the reader

def _document(symbols: list[str], depth: int) -> list[Piece]:
    """The pieces of document text, read as COMPILATION.md §3's table says, in its order
    of precedence: a Markdown item, a comment symbol, a control symbol, a bare cartouche,
    `@{`, any other `\\<…`, any other character.  A Markdown item is an item piece.  A body
    read again is read at `depth + 1` and comes back as one `Body`, without its item
    pieces; at `_DEPTH` it is a cartouche piece instead.  Each sub- or superscript and span
    then takes the word it stands in (`_scripts_with_words`), and each body is spliced in
    where it stands."""
    out: list[Piece | Body] = []
    controls: set[int] = set()                  # the positions in `out` of the cartouches a typesetting control made
    scripts: set[int] = set()                   # of those, the sub- and superscripts and the spans
    n = len(symbols)
    partners = _partners(symbols, _OPEN, _CLOSE)
    spans = {o: _partners(symbols, o, c) for o, c in _SPANS.items()}
    closers = _closers(symbols, "}", partners, _string_ends(symbols))

    def again(body: list[str]) -> Body | Cartouche:
        if depth + 1 < _DEPTH:
            return Body(p for p in _document(body, depth + 1) if not isinstance(p, Item))
        return Cartouche("".join(body))

    def argument(name: str, body: list[str]) -> list[Piece | Body]:
        if name in _FORMATTING:
            return [Plain(_FORMATTING[name] + "{"), again(body), Plain("}")]
        return [Cartouche("".join(body))]

    i = 0
    while i < n:
        s = symbols[i]
        if s in _ITEMS:
            out.append(Item(s))
            i += 1
            continue
        if s in _COMMENTS:
            j = _comment_at(symbols, i, partners)
            if j is None:                       # no cartouche: dropped
                i += 1
                continue
            body = symbols[j + 1:partners[j]]
            i = partners[j] + 1
            if s == _COMMENT:                   # Isabelle's enclosure, document_output.ML:69
                out += [Plain("%\n\\isamarkupcmt{"), again(body), Plain("%\n}")]
            elif s == _CANCEL:
                out += [Plain("\\isamarkupcancel{"), Cartouche("".join(body)), Plain("}")]
            elif s == _LATEX:
                out.append(again(body))
            continue                            # a marker: dropped, its body with it
        if _control(s):
            name = s[3:-1]
            if i + 1 < n and symbols[i + 1] == _OPEN and i + 1 in partners:
                out += argument(name, symbols[i + 2:partners[i + 1]])
                i = partners[i + 1] + 1
                continue
            if name in _SPACING:
                out.append(Plain("\\" + name + "{}"))
            elif s in _ONE_SYMBOL and _applies(symbols, i):
                controls.add(len(out))
                if s != "\\<^bold>":
                    scripts.add(len(out))
                out.append(Cartouche(s + symbols[i + 1]))
                i += 2
                continue
            elif s in spans and i in spans[s]:
                controls.add(len(out))
                scripts.add(len(out))
                out.append(Cartouche("".join(symbols[i:spans[s][i] + 1])))
                i = spans[s][i] + 1
                continue
            i += 1                              # with nothing to apply to, or unpaired: dropped
            continue
        if s == _OPEN and i in partners:
            out.append(Cartouche("".join(symbols[i + 1:partners[i]])))
            i = partners[i] + 1
            continue
        if s in _STRAY:                         # every paired close mark went with its partner
            out.append(Plain(_STRAY[s]))
            i += 1
            continue
        if s == "@" and i + 1 < n and symbols[i + 1] == "{":
            end = closers[i + 2]
            if end is None:                     # it does not close: plain text
                out.append(Plain("@\\{"))
                i += 2
                continue
            name, arg = _antiquotation_parts(symbols[i + 2:end])
            i = end + 1
            if not all(_blank(a) for a in arg):
                out += argument(name, arg)
            elif name in _SPACING:
                out.append(Plain("\\" + name + "{}"))
            continue
        if s.startswith("\\<"):
            out.append(Plain(_characters(s)) if is_malformed(s) else Cartouche(s))
            i += 1
            continue
        out.append(Plain(s))
        i += 1
    pieces: list[Piece] = []
    for p in _scripts_with_words(out, controls, scripts):
        pieces += p if isinstance(p, Body) else [p]
    return pieces


@dataclass(slots=True)
class _Frame:
    """The word pass's state in one bracket pair, or in the text outside every pair."""
    start: int | None                           # where its word starts; None once LaTeX stands in it
    latex_anywhere: bool = False                # LaTeX anywhere in the pair
    stretch: int | None = None                  # the start of the stretch being joined

    def latex(self) -> None:
        self.start = self.stretch = None
        self.latex_anywhere = True


def _scripts_with_words(out: list[Piece | Body], controls: set[int], scripts: set[int]) -> list[Piece | Body]:
    """Each sub- or superscript and span cartouche joined with the word it stands in into
    one cartouche piece, by COMPILATION.md §3's "A script's word".  The brackets are paired
    first, by a stack that an item piece and a newline plain piece empty; then one pass,
    with a frame per pair."""
    def plain(p: Piece | Body) -> TypeGuard[Plain]:
        return isinstance(p, Plain) and len(symbol_explode(p)) == 1 and p not in _LATEX_CHARACTERS

    def joins_a_word(p: Piece | Body) -> TypeGuard[Cartouche]:
        return isinstance(p, Cartouche) and (is_identifier(p) or len(symbol_explode(p)) == 1 and _operand(p))

    def paired_within(p: Piece | Body) -> bool:
        if not isinstance(p, Cartouche):
            return False
        symbols = symbol_explode(p)
        return not any(_unpaired(symbols, o, c) for o, c in [(_OPEN, _CLOSE), *_SPANS.items()])

    def ends_in_backslash_or_malformed(p: Piece | Body) -> bool:
        if not isinstance(p, Cartouche) or p == "":
            return False
        last = symbol_explode(p)[-1]
        return last == "\\" or is_malformed(last)

    pairs: dict[int, int] = {}
    opened: list[int] = []
    for i, p in enumerate(out):
        if isinstance(p, Item) or isinstance(p, Plain) and p == "\n":
            opened.clear()
        elif not plain(p):
            continue
        elif p in _BRACKETS.values():
            opened.append(i)
        elif p in _BRACKETS and opened and out[opened[-1]] == _BRACKETS[p]:
            pairs[opened.pop()] = i
    closes = set(pairs.values())

    frames = [_Frame(0)]
    joins: list[list[int]] = []                 # the [start, end] of each stretch to join, in order

    def extend(start: int, end: int) -> None:
        while joins[-1][0] > start:
            joins.pop()
        joins[-1][1] = end

    for i, p in enumerate(out):
        top = frames[-1]
        if i in controls and paired_within(p):  # joined, a mark with no partner in it could pair with another piece's or split the joined piece
            if top.stretch is not None:
                extend(top.stretch, i + 1)
            elif i in scripts:
                start = i if top.start is None else top.start
                while joins and joins[-1][0] >= start:
                    joins.pop()
                joins.append([start, i + 1])
                top.stretch = start
        elif i in pairs:
            frames.append(_Frame(i + 1))
        elif i in closes:
            inner = frames.pop()
            top = frames[-1]
            if inner.latex_anywhere:
                top.latex()
            elif top.stretch is not None:
                extend(top.stretch, i + 1)
        elif isinstance(p, Item) or plain(p) and (_blank(p) or p in _QUOTES or p in _BRACKETS or p in _BRACKETS.values()):
            top.start, top.stretch = i + 1, None
        elif isinstance(p, Body):               # to a pair holding it, LaTeX; an edge of its word
            top.latex()
            top.start = i + 1
        elif plain(p) or joins_a_word(p):
            if top.stretch is not None and not (plain(p) and p in _PUNCTUATION):
                extend(top.stretch, i + 1)
        else:
            top.latex()
        if ends_in_backslash_or_malformed(p):   # joined, it could fuse with what follows: it takes nothing after it
            top.latex()
    joined: list[Piece | Body] = []
    i = 0
    for start, end in joins:
        joined += out[i:start]
        joined.append(Cartouche("".join(cast("list[Piece]", out[start:end]))))     # no stretch holds a body
        i = end
    return joined + out[i:]


def _antiquotation_parts(body: list[str]) -> tuple[str, list[str]]:
    """An `@{…}` body: its name, and its argument with one `[…]` option list dropped and
    each cartouche or `"…"` string replaced by what it encloses, a backslash in a string
    escaping the symbol after it."""
    n = len(body)
    partners = _partners(body, _OPEN, _CLOSE)
    string_ends = _string_ends(body)
    i = 0
    while i < n and _blank(body[i]):
        i += 1
    j = i
    while j < n and _NAME_CHARACTER.fullmatch(body[j]):
        j += 1
    name = "".join(body[i:j])
    while j < n and _blank(body[j]):
        j += 1
    if j < n and body[j] == "[":
        end = _closers(body, "]", partners, string_ends)[j]
        j = n if end is None else end + 1
    arg: list[str] = []
    while j < n:
        s = body[j]
        if s == _OPEN and j in partners:
            arg += body[j + 1:partners[j]]
            j = partners[j] + 1
        elif s == '"':
            end = string_ends[j + 1]
            stop = n if end is None else end
            k = j + 1
            while k < stop:
                if body[k] == "\\" and k + 1 < stop:
                    k += 1
                arg.append(body[k])
                k += 1
            j = stop + 1
        else:
            arg.append(s)
            j += 1
    return name, arg


# --- the renderer

def _render(pieces: list[Piece], lists: bool) -> str:
    """Every cartouche piece expanded by `_cartouche_piece`; with `lists`, an item piece
    that holds one of the three Markdown items and has nothing but spaces before it on its
    output line kept (markdown.ML `read_marker`), a space after it unless a blank or the
    end follows, and every other item piece dropped, the plain pieces around it joining
    one run; then, over the expanded list, each plain run through `_plain_run`, each
    cartouche between `‹` and `›`, each item piece as it stands (one well-formed symbol)."""
    expanded: list[Piece] = []
    line_start = True
    for piece in pieces:
        for p in _cartouche_piece(piece) if isinstance(piece, Cartouche) else [piece]:
            if isinstance(p, Item) and not (lists and line_start and p in _ITEMS):
                continue
            if expanded and isinstance(expanded[-1], Item) and not (isinstance(p, Plain) and _blank(p[:1])):
                expanded.append(Plain(" "))
            line_start = isinstance(p, Plain) and _ends_at_line_start(p, line_start)
            expanded.append(p)
    out: list[str] = []
    run: list[str] = []
    for p in expanded:
        if isinstance(p, Plain):
            run.append(p)
            continue
        if run:
            out.append(_plain_run("".join(run)))
            run = []
        out.append(p if isinstance(p, Item) else _OPEN + p + _CLOSE)
    if run:
        out.append(_plain_run("".join(run)))
    return "".join(out)


def _ends_at_line_start(plain: str, line_start: bool) -> bool:
    """Whether nothing but spaces stands after the last newline of `plain`, or, with no
    newline in it, in all of it after a line's start."""
    _, newline, tail = plain.rpartition("\n")
    return (bool(newline) or line_start) and not tail.strip(" ")


def _cartouche_piece(text: str) -> list[Piece]:
    """The text cut by `_symbols`, split at every stray mark (a plain piece between the
    parts), each part filtered and trimmed; an empty part writes nothing."""
    symbols = _symbols(text)
    out: list[Piece] = []
    start = 0
    for i in [*sorted(_unpaired(symbols, _OPEN, _CLOSE)), len(symbols)]:
        part = _trimmed(_filtered(symbols[start:i]))
        if part:
            out.append(Cartouche("".join(part)))
        if i < len(symbols):
            out.append(Plain(_STRAY[symbols[i]]))
        start = i + 1
    return out


def _plain_run(latex: str) -> str:
    """The run cut again by `_symbols`; then `\\relax` between an `@` and a `{` after it,
    a space between a `\\` and a `<`."""
    return "".join(_symbols(latex)).replace("@{", "@\\relax{").replace("\\<", "\\ <")


def _filtered(symbols: list[str]) -> list[str]:
    """The content filter on one part: a space for every comment symbol, Markdown item,
    malformed symbol and control symbol that is not a typesetting control, for a
    one-symbol typesetting control with nothing to apply to, and for a span marker with no
    partner in the part.  It replaces and never deletes, so it joins no two symbols into
    one."""
    unpaired = set().union(*(_unpaired(symbols, o, c) for o, c in _SPANS.items()))
    span_markers = _SPANS.keys() | _SPANS.values()
    out = list(symbols)
    for i, s in enumerate(symbols):
        if (s in _COMMENTS or s in _ITEMS or is_malformed(s)
                or (_control(s) and s not in _ONE_SYMBOL and s not in span_markers)
                or (s in _ONE_SYMBOL and not _applies(symbols, i)) or i in unpaired):
            out[i] = " "
    return out


def _trimmed(symbols: list[str]) -> list[str]:
    """The part without its leading and trailing spaces, by slicing."""
    a, b = 0, len(symbols)
    while a < b and symbols[a] == " ":
        a += 1
    while b > a and symbols[b - 1] == " ":
        b -= 1
    return symbols[a:b]
