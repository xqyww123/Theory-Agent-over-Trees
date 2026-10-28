"""The strings against which the input layer (plugin.py; MODULE_STRUCTURE
§4.4) is compared with Isabelle's own reading: `ALPHABET` and `random`,
strings drawn from it; `structured`, YXML bodies of random elements, some
with one character changed; `HAND`, 48 written by hand, `WRAPPINGS` among
them; `FRAMED`, 7 bodies of an `input` element, the wrappings among them;
`POSITION_CASES`, 16 position properties of an `input` element around
`x`, each with whether Isabelle reads it.  `corpus()` is the whole:
10,000 random, 6,000 structured, the hand-written strings, the framed
ones and the position cases."""

import random as _random

X, Y = "\x05", "\x06"                       # YXML's markup characters
ALPHABET = [X, X, X, Y, Y, Y, "=", "=", "a", "b", "x", " ", "\\<open>", "\\<close>", "\\<^sub>",
            "\\<comment>", '"', "\n", "input", "‹", "α"]


def random(seed: int, n: int) -> list[str]:
    r = _random.Random(seed)
    return ["".join(r.choice(ALPHABET) for _ in range(r.randint(1, 24))) for _ in range(n)]


NAMES = ["a", "b", "input", "xml_elem", "xml_body", "xml_name", "a=b", "\\<open>", "x y"]
KEYS = ["k", "xml_name", "xml_body", "a b", "\\<close>", "delimited", "offset"]
VALUES = ["", "v", "=", "a=b", "1", "\\<open>", " "]
TEXTS = ["x", "f x", " ", "\\<comment>\\<open>a", "c\\<close>", "=", "\n", '"', "‹y›"]


def _tree(r: _random.Random, depth: int) -> str:
    if depth > 3 or r.random() < 0.35:
        return r.choice(TEXTS)
    name = r.choice(NAMES)
    attributes = [r.choice(KEYS) + "=" + r.choice(VALUES) for _ in range(r.choice([0, 0, 1, 1, 2, 3]))]
    if name == "xml_elem" and r.random() < 0.7:
        attributes = ["xml_name=" + r.choice(VALUES)] + attributes
    children = [_tree(r, depth + 1) for _ in range(r.randint(0, 3))]
    if name == "xml_elem" and r.random() < 0.7:
        children = [X + Y + "xml_body" + (Y + "k=v" if r.random() < 0.2 else "") + X
                    + "".join(_tree(r, depth + 2) for _ in range(r.randint(0, 2))) + X + Y + X] + children
    return X + Y + Y.join([name] + attributes) + X + "".join(children) + X + Y + X


def structured(seed: int, n: int) -> list[str]:
    r = _random.Random(seed)
    out = []
    for _ in range(n):
        s = "".join(_tree(r, 0) for _ in range(r.randint(1, 3)))
        if r.random() < 0.4 and s:                  # one character deleted, inserted or replaced
            i = r.randrange(len(s))
            op = r.choice(["del", "ins", "rep"])
            c = r.choice([X, Y, "=", "a", ""])
            s = s[:i] + (c if op != "del" else "") + s[i + (0 if op == "ins" else 1):]
        out.append(s)
    return out


def element(name: str, attributes: list[str], body: str) -> str:
    return X + Y + Y.join([name, *attributes]) + X + body + X + Y + X


def _framed(prop: str) -> str:
    return element("input", [], prop)


# `xml_elem` wrappings and near misses: Isabelle's `content_of` skips an `xml_elem`'s
# first child where the element's first attribute is `xml_name` and the child a bare `xml_body`
WRAPPINGS = [
    X + Y + "xml_elem" + Y + "xml_name=n" + X + X + Y + "xml_body" + X + "hidden" + X + Y + X + "shown" + X + Y + X,
    X + Y + "xml_elem" + Y + "xml_name=" + Y + "k=v" + X + X + Y + "xml_body" + X + "hidden" + X + Y + X + X + Y + X,
    X + Y + "xml_elem" + Y + "k=v" + Y + "xml_name=n" + X + X + Y + "xml_body" + X + "hidden" + X + Y + X + "shown" + X + Y + X,
    X + Y + "xml_elem" + Y + "xml_name=n" + X + "t" + X + Y + "xml_body" + X + "hidden" + X + Y + X + X + Y + X,
    X + Y + "xml_elem" + Y + "xml_name=n" + X + X + Y + "xml_body" + Y + "k=v" + X + "hidden" + X + Y + X + X + Y + X,
    X + Y + "xml_elem" + X + X + Y + "xml_body" + X + "hidden" + X + Y + X + X + Y + X,
]

HAND = [
    "", "plain text", "f x \\<equiv> x", "\\<comment>\\<open>a\\<close>",
    X, Y, X + X, X + Y + X, X + X + Y + X, Y + X, X + Y, X + Y + Y + X, X + Y + Y + X + X + Y + X,
    "a" + Y + "b", "a" + Y + Y + "b", "a" + Y, Y + "a", "a" + X + "b", X + "a" + X, "a" + X + Y + X,
    X + Y + "a" + X + "t" + X + Y + X,
    X + Y + "a" + Y + "k=v" + X + "t" + X + Y + X,
    X + Y + "a" + Y + "k=v" + Y + "l=w" + Y + "m=" + X + "t" + X + Y + X,
    X + Y + "a" + Y + "k=v=w" + X + "t" + X + Y + X,
    X + Y + "a" + Y + "k" + X + "t" + X + Y + X,
    X + Y + "a" + Y + "=v" + X + "t" + X + Y + X,
    X + Y + "a" + Y + "=" + X + "t" + X + Y + X,
    X + Y + "a" + Y + "a=" + X + "t" + X + Y + X,
    X + Y + "a" + Y + X + "t" + X + Y + X,
    X + Y + "a=b" + X + "t" + X + Y + X,
    X + Y + "a" + X + "t" + Y + "u" + X + Y + X,
    X + Y + "a" + X + X + Y + "b" + X + "u" + X + Y + X + "v" + X + Y + X,
    X + Y + "a" + X + "t",
    X + Y + "a" + X + "t" + X + Y + X + X + Y + X,
    _framed("x \\<equiv> x"),
    _framed("x \\<equiv> x \\<comment>\\<open>a" + X + Y + "b" + X + "c\\<close>" + X + Y + X),
    X + Y + "input" + X + "x \\<equiv> x \\<comment>\\<open>a" + X + Y + "b" + X + "c\\<close>" + X + Y + X + X + Y + X,
    X + Y + "b" + X + "f x" + X + Y + X,
    *WRAPPINGS,
    _framed("f " + X + Y + "xml_elem" + Y + "xml_name=n" + X + X + Y + "xml_body" + X + "hidden" + X + Y + X + "x" + X + Y + X),
    X + Y + "input" + Y + "delimited=true" + Y + "offset=1" + Y + "end_offset=5" + X + "f x" + X + Y + X,
    X * 3 + "a" + X * 3,
    "a" + X + Y + "b" + Y + "k=v" + X + "c" + X + Y + X + "d",
]

# The wrappings inside an `input` element, where Isabelle reads their content, and an
# element with no name inside one, which it refuses
FRAMED = [*map(_framed, WRAPPINGS), _framed(X + Y + Y + "k=v" + X + "a" + X + Y + X)]

# An `input` element's position properties, and whether Isabelle reads
# them (position.ML `range_of_properties`: each name's first value an
# integer, value.ML `parse_int`); unread, it raises `Bad integer`.
POSITION_CASES = [
    (["line=a"], False), (["end_offset=a"], False), (["end_line=a"], False),
    (["offset=+3"], False), (["offset= 3"], False), (["offset=1_0"], False), (["offset=３"], False),
    (["offset=-"], False), (["line=-"], False),
    (["offset=-0"], True), (["offset=-1"], True), (["end_line=-7"], True),
    (["offset=3", "offset=a"], True), (["offset=a", "offset=3"], False),
    (["end_line=3", "end_line=a"], True), (["end_line=a", "end_line=3"], False),
]


def positioned(properties: list[str]) -> str:
    """`x` in an `input` element with the position properties given."""
    return element("input", properties, "x")


def corpus() -> list[str]:
    return [*random(1, 5000), *random(2, 5000), *structured(3, 3000), *structured(4, 3000), *HAND, *FRAMED,
            *(positioned(p) for p, _ in POSITION_CASES)]
