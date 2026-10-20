# -*- coding: utf-8 -*-
"""Normalize LLM markdown so Pandoc can emit Word OMML formulas."""
import os
import re

PANDOC_BIN_CANDIDATES = [
    os.environ.get("PYPANDOC_PANDOC"),
    "/root/hljiang/software/pandoc-3.1.11/bin/pandoc",
    "/usr/bin/pandoc",
    "/usr/local/bin/pandoc",
]

PANDOC_FROM_MARKDOWN = (
    "markdown"
    "+tex_math_dollars"
    "+tex_math_single_backslash"
    "+tex_math_double_backslash"
    "+raw_tex"
)

FENCE_MATH_RE = re.compile(r"```(?:math|latex)\s*\n([\s\S]*?)```", re.IGNORECASE)
BEGIN_ENV_RE = re.compile(
    r"\\begin\{(equation\*?|align\*?|aligned\*?|gather\*?|eqnarray\*?)\}"
    r"([\s\S]*?)"
    r"\\end\{\1\}"
)
BLOCK_MATH_RE = re.compile(r"(\$\$[\s\S]*?\$\$)")
DOUBLE_BRACKET_RE = re.compile(r"\\\\\[([\s\S]*?)\\\\\]")
DOUBLE_PAREN_RE = re.compile(r"\\\\\(([\s\S]*?)\\\\\)")
SINGLE_BRACKET_RE = re.compile(r"\\\[([\s\S]*?)\\\]")
SINGLE_PAREN_RE = re.compile(r"\\\(([\s\S]*?)\\\)")


def resolve_pandoc_bin():
    for candidate in PANDOC_BIN_CANDIDATES:
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def ensure_pandoc_env():
    binary = resolve_pandoc_bin()
    if binary:
        os.environ["PYPANDOC_PANDOC"] = binary
    return binary


def _wrap_bare_math_environments(text):
    parts = BLOCK_MATH_RE.split(text)
    out = []
    for part in parts:
        if part.startswith("$$"):
            out.append(part)
        else:
            out.append(BEGIN_ENV_RE.sub(lambda match: "$$\n%s\n$$" % match.group(0), part))
    return "".join(out)


def normalize_math_markdown(text):
    if not text:
        return text or ""
    value = FENCE_MATH_RE.sub(lambda match: "$$\n%s\n$$" % match.group(1).strip(), text)
    value = DOUBLE_BRACKET_RE.sub(lambda match: "$$\n%s\n$$" % match.group(1).strip(), value)
    value = DOUBLE_PAREN_RE.sub(lambda match: "$%s$" % match.group(1).strip(), value)
    value = SINGLE_BRACKET_RE.sub(lambda match: "$$\n%s\n$$" % match.group(1).strip(), value)
    value = SINGLE_PAREN_RE.sub(lambda match: "$%s$" % match.group(1).strip(), value)
    return _wrap_bare_math_environments(value)
