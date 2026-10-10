"""Link-integrity guard for the docs/ tree.

Every relative markdown link under docs/ must resolve to a file in this
repository, and ``file.md#anchor`` links must point at a real heading in the
target page (GitHub-style heading slugs). Root-level docs (README, CONTEXT,
SECURITY, VERSIONING) get the same check for their relative links.

No network, no database: external web links are out of scope by design --
they rot for reasons this repo cannot see. This guard is only about internal
consistency, and it runs in the plain unit suite.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS_ROOT = REPO_ROOT / "docs"
ROOT_DOCS = ("README.md", "CONTEXT.md", "SECURITY.md", "VERSIONING.md")

# [text](target) or [text](target "title"); angle-bracket targets allowed.
INLINE_LINK_RE = re.compile(r"\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
# Reference definitions: [label]: target "title"
REFDEF_RE = re.compile(
    r"^\s{0,3}\[[^\]]+\]:\s+(<?[^>\s]+>?)\s*(?:\"[^\"]*\")?\s*$", re.M
)
FENCE_RE = re.compile(r"^\s*(```|~~~)")
EXTERNAL_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:|^/")


def strip_code_blocks(text: str) -> str:
    """Drop fenced code blocks and inline code spans -- their contents never
    render as links or headings, so scanning them only produces false hits."""
    kept: list[str] = []
    fence: str | None = None
    for line in text.splitlines():
        marker = FENCE_RE.match(line)
        if fence:
            fence = None if marker else fence
            continue
        if marker:
            fence = marker.group(1)
            continue
        kept.append(line)
    return "\n".join(kept)


def strip_inline_code(text: str) -> str:
    return re.sub(r"`+[^`]*`+", "", text)


def iter_links(text: str) -> list[str]:
    """All link targets in a markdown document: inline plus reference defs."""
    clean = strip_inline_code(strip_code_blocks(text))
    targets = INLINE_LINK_RE.findall(clean)
    targets.extend(REFDEF_RE.findall(clean))
    return [t.strip("<>") for t in targets]


def heading_slugs(md_text: str) -> set[str]:
    """GitHub-style slugs of every markdown heading, code fences excluded.

    Duplicates get the usual ``-1``/``-2`` suffixes GitHub appends.
    """
    clean = strip_inline_code(strip_code_blocks(md_text))
    counts: dict[str, int] = {}
    slugs: set[str] = set()
    for line in clean.splitlines():
        match = re.match(r"^\s*#{1,6}\s+(.*?)\s*#*\s*$", line)
        if not match:
            continue
        text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", match.group(1))  # links
        text = re.sub(r"[*_]", "", text)  # emphasis markers
        slug = re.sub(r"[^\w\- ]", "", text.lower()).replace(" ", "-")
        if not slug:
            continue
        n = counts.get(slug, 0)
        counts[slug] = n + 1
        slugs.add(slug if n == 0 else f"{slug}-{n}")
    return slugs


def check_file(md: Path, broken: list[str]) -> None:
    """Append a message to ``broken`` for every unresolved link in ``md``."""
    text = md.read_text()
    for target in iter_links(text):
        if EXTERNAL_RE.match(target):
            continue
        path_part, _, anchor = target.partition("#")
        if not path_part:  # anchor-only link into the same file
            continue
        resolved = (md.parent / path_part).resolve()
        if not resolved.exists():
            broken.append(f"{md.relative_to(REPO_ROOT)} -> {target} (missing file)")
            continue
        if anchor and resolved.suffix == ".md":
            if anchor not in heading_slugs(resolved.read_text()):
                broken.append(
                    f"{md.relative_to(REPO_ROOT)} -> {target} (missing anchor)"
                )


def test_docs_relative_links_resolve():
    broken: list[str] = []
    assert DOCS_ROOT.is_dir(), "docs/ tree is missing"
    for md in sorted(DOCS_ROOT.rglob("*.md")):
        check_file(md, broken)
    assert not broken, "broken relative links in docs/:\n" + "\n".join(broken)


def test_root_doc_references_resolve():
    broken: list[str] = []
    for name in ROOT_DOCS:
        md = REPO_ROOT / name
        assert md.is_file(), f"{name} is missing from the repo root"
        check_file(md, broken)
    assert not broken, "broken relative links in root docs:\n" + "\n".join(broken)
