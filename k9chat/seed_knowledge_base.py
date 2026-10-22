# SPDX-License-Identifier: Apache-2.0
# K9-AIF Framework
#
# Seeds the k9chat knowledge base (KnowledgeRetriever's fixed ChromaDB
# collection) with the real K9-AIF framework + K9X ecosystem documentation,
# blog corpus, and developer guides -- chunked and embedded the same way
# dow-k9-aif's seed_synthetic_corpus.py seeds its corpus.
#
# Deliberately docs/prose-only, not raw .py source: code chunks retrieved
# out of context tend to mislead more than help for a "chat and learn about
# the framework" use case. Raw source is better served by a dedicated
# code-search tool later, not mixed into this general knowledge base.
#
# Idempotent-ish: re-running re-embeds and re-stores every chunk under the
# same doc_ids (doc_id = f"{label}:{i}"), so ChromaDB upserts rather than
# duplicating -- safe to re-run after any of these docs change.
#
# Usage (from the k9-aif-examples repo root):
#   python -m k9chat.seed_knowledge_base

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# k9chat moved into its own k9-aif-examples repo 2026-09-21 -- two
# separate roots now (same split as app.py): FRAMEWORK_ROOT for
# k9_aif_abb/ imports (sibling checkout, override via
# K9AIF_FRAMEWORK_PATH), EXAMPLES_ROOT so `k9chat.*` resolves as a
# package regardless of invocation directory.
REPO_ROOT = os.environ.get(
    "K9AIF_FRAMEWORK_PATH",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "../../k9-aif-framework")),
)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

EXAMPLES_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if EXAMPLES_ROOT not in sys.path:
    sys.path.insert(0, EXAMPLES_ROOT)

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

import re

from k9_aif_abb.k9_utils.config_loader import load_yaml
from k9chat.knowledge_retriever import KnowledgeRetriever, COLLECTION_NAME
from k9chat.project_retriever import chunk_text

BASE_DIR = os.path.dirname(__file__)
FRAMEWORK_ROOT = Path(REPO_ROOT)
ECOSYSTEM_ROOT = FRAMEWORK_ROOT.parent / "k9x-ecosystem"
# The DAS checkout is "dow-k9-aif" on the Mac and "dow-k9x" on PowerAI
# (same repo, github.com/k9aif/dow-k9x): use whichever exists.
DOW_ROOT = next((p for p in (FRAMEWORK_ROOT.parent / "dow-k9-aif", FRAMEWORK_ROOT.parent / "dow-k9x")
                 if p.exists()), FRAMEWORK_ROOT.parent / "dow-k9-aif")
BLOGS_ROOT = FRAMEWORK_ROOT.parent / "k9-aif-blogs" / "_posts"
DOIT_ASSETS = FRAMEWORK_ROOT.parent / "doit" / "assets"
VIDEOS_YAML = FRAMEWORK_ROOT.parent / "k9x_video_series" / "videos.yaml"

# (label, path) -- label becomes both the doc_id prefix and the
# "[label] chunk text" filename tag chunk_text() already applies.
# Every path is checked for existence at seed time; a moved/renamed file
# is skipped with a warning, never a hard failure -- one missing doc
# shouldn't block seeding the rest.
TEXT_CORPUS: list[tuple[str, Path]] = [
    # Short, dense, one-definition-per-term -- deliberately first, and
    # deliberately separate from the long-form docs below. Added
    # 2026-09-20 after a real retrieval-quality gap: semantic search over
    # long-form README/blog prose kept losing a single definitional
    # sentence to broader tangential passages, so "what does ABB stand
    # for" never actually surfaced the real definition and the model
    # answered wrong from its own prior knowledge instead.
    ("k9chat/glossary", Path(BASE_DIR) / "knowledge" / "glossary.md"),
    ("k9chat/faq", Path(BASE_DIR) / "knowledge" / "faq.md"),
    ("k9-aif-framework/CLAUDE.md", FRAMEWORK_ROOT / "CLAUDE.md"),
    ("k9-aif-framework/SKILLS.md", FRAMEWORK_ROOT / "SKILLS.md"),
    ("k9-aif-framework/README.md", FRAMEWORK_ROOT / "README.md"),
    ("k9-aif-framework/k9_security/CLAUDE.md",
     FRAMEWORK_ROOT / "k9_aif_abb/k9_security/CLAUDE.md"),
    ("k9x-ecosystem/CLAUDE.md", ECOSYSTEM_ROOT / "CLAUDE.md"),
    ("k9x-ecosystem/README.md", ECOSYSTEM_ROOT / "README.md"),
    ("k9x-ecosystem/k9x_satan/CLAUDE.md", ECOSYSTEM_ROOT / "k9x_satan/CLAUDE.md"),
    ("k9x-ecosystem/k9x_studio/README.md", ECOSYSTEM_ROOT / "k9x_studio/README.md"),
    ("k9x-ecosystem/k9x_continuum/README.md", ECOSYSTEM_ROOT / "k9x_continuum/README.md"),
    ("k9x-ecosystem/k9x_enterprise_repository/README.md",
     ECOSYSTEM_ROOT / "k9x_enterprise_repository/README.md"),
    ("k9x-ecosystem/k9x_testcases/README.md", ECOSYSTEM_ROOT / "k9x_testcases/README.md"),
    ("k9x-ecosystem/k9x_coe/README.md", ECOSYSTEM_ROOT / "k9x_coe/README.md"),
    ("dow-k9-aif/CLAUDE.md", DOW_ROOT / "CLAUDE.md"),
    ("dow-k9-aif/README.md", DOW_ROOT / "README.md"),
]

# When a doc isn't on disk, read it from its public GitHub repo instead.
# Several K9X apps are their own repos nested inside the Mac's
# k9x-ecosystem folder, so PowerAI's k9x-ecosystem clone doesn't have
# them (they were skipped on every seed). Labels stay the same so chunk
# ids don't change. k9x_coe/README.md isn't committed anywhere: local only.
GITHUB_RAW = "https://raw.githubusercontent.com/k9aif"
GITHUB_FALLBACK = {
    "k9x-ecosystem/k9x_satan/CLAUDE.md": "satan/main/CLAUDE.md",
    "k9x-ecosystem/k9x_studio/README.md": "studiox/main/README.md",
    "k9x-ecosystem/k9x_continuum/README.md": "continuum/main/README.md",
    "k9x-ecosystem/k9x_enterprise_repository/README.md": "enterprise_repository/main/README.md",
    "k9x-ecosystem/k9x_testcases/README.md": "k9x_testcases/main/README.md",
    "dow-k9-aif/CLAUDE.md": "dow-k9x/main/CLAUDE.md",
    "dow-k9-aif/README.md": "dow-k9x/main/README.md",
}


def _read_github(label: str) -> str:
    import requests
    resp = requests.get(f"{GITHUB_RAW}/{GITHUB_FALLBACK[label]}", timeout=15)
    resp.raise_for_status()
    return resp.text


# ── K9X videos on YouTube ──────────────────────────────────────────────
# One knowledge entry per published video (title, length, date, link, what
# it covers) plus one for the channel, so "is there a video on X?" finds
# the right one. Sources, never a hand-copied list:
#   - k9x_video_series/videos.yaml: the single list of published videos
#     (titles, lengths), when it's on disk (the Mac);
#   - the channel's public feed: each video's description, and the list
#     itself when videos.yaml isn't there (PowerAI).
YOUTUBE_CHANNEL_URL = "https://www.youtube.com/@k9-aif"
YOUTUBE_FEED_URL = "https://www.youtube.com/feeds/videos.xml?channel_id=UC4W2S3bx5e80gS-DTTz7S2g"
VIDEO_PREFIX = "k9x-videos/"


def _video_id(url: str) -> str:
    m = re.search(r"(?:youtu\.be/|[?&]v=)([A-Za-z0-9_-]{11})", url or "")
    return m.group(1) if m else ""


def _youtube_feed() -> dict:
    """{video_id: {title, published, description}} from the channel feed (latest 15)."""
    import requests
    import xml.etree.ElementTree as ET
    ns = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015",
          "media": "http://search.yahoo.com/mrss/"}
    resp = requests.get(YOUTUBE_FEED_URL, timeout=15)
    resp.raise_for_status()
    out = {}
    for e in ET.fromstring(resp.content).findall("a:entry", ns):
        vid = e.findtext("yt:videoId", default="", namespaces=ns)
        desc = (e.findtext("media:group/media:description", default="", namespaces=ns) or "").strip()
        out[vid] = {"title": e.findtext("a:title", default="", namespaces=ns),
                    "published": (e.findtext("a:published", default="", namespaces=ns) or "")[:10],
                    "description": desc}
    return out


def _video_docs():
    """(label, where, text) per video plus the channel entry, or [] if
    neither videos.yaml nor the feed is available (nothing gets removed)."""
    try:
        feed = _youtube_feed()
    except Exception as exc:
        print(f"[seed] YouTube feed unavailable: {exc}")
        feed = {}
    videos = []
    if VIDEOS_YAML.exists():
        import yaml
        for v in (yaml.safe_load(VIDEOS_YAML.read_text()) or {}).get("videos", []):
            vid = _video_id(v.get("url", ""))
            if vid:
                videos.append({"id": vid, "title": v.get("title", ""), "length": v.get("length", ""),
                               "published": str(v.get("published", "")), **{"description": feed.get(vid, {}).get("description", "")}})
        where = str(VIDEOS_YAML)
    elif feed:
        videos = [{"id": vid, "length": "", **meta} for vid, meta in feed.items()]
        where = "youtube feed"
    else:
        return []

    docs, lines = [], []
    for v in sorted(videos, key=lambda x: x["published"]):
        url = f"https://www.youtube.com/watch?v={v['id']}"
        # Description up to its link list: the prose says what the video covers.
        about = re.split(r"\n\s*(?:Patterns?:|Framework:|Developers:|Try the demo:|Start:)", v["description"])[0].strip()
        meta = ", ".join(x for x in (v["length"], f"published {v['published']}" if v["published"] else "") if x)
        text = (f"[k9x-videos] Video: {v['title']} ({meta}). Watch: {url}\n"
                f"Part of the K9X YouTube channel {YOUTUBE_CHANNEL_URL}.\n{about}").strip()
        docs.append((f"{VIDEO_PREFIX}{v['id']}", where, text))
        lines.append(f"- {v['title']} ({v['length'] or 'video'}): {url}")
    channel = (f"[k9x-videos] Where to watch K9-AIF and K9X videos: the K9X YouTube channel, "
               f"{YOUTUBE_CHANNEL_URL}. Short narrated videos on the framework, its patterns, security "
               f"and the demo applications. Published videos:\n" + "\n".join(lines))
    docs.append((f"{VIDEO_PREFIX}channel", where, channel))
    return docs


# Docs chunked one-section-per-"## heading" instead of chunk_text()'s
# paragraph-merging. Confirmed 2026-09-20: merging multiple glossary
# terms into one chunk diluted the ABB definition's embedding (a real
# question, "what does ABB stand for", couldn't retrieve it) -- a
# glossary needs each fact to embed distinctly on its own, never merged
# with its neighbors.
HEADING_CHUNKED = {"k9chat/glossary", "k9chat/faq"}


def _chunk_by_heading(text: str, filename: str) -> list[str]:
    sections = re.split(r"\n(?=## )", text)
    return [f"[{filename}] {s.strip()}" for s in sections if s.strip()]


# PDFs need text extraction (pypdf, already in requirements.txt) rather
# than a plain read_text().
PDF_CORPUS: list[tuple[str, Path]] = [
    ("k9-aif-developer-guide", DOIT_ASSETS / "Developer-guide.pdf"),
    ("k9-aif-quick-start-guide", DOIT_ASSETS / "Quick-Start-Guide.pdf"),
]


def _extract_pdf_text(path: Path) -> str:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages)


def _iter_corpus():
    """Yields (label, where, read) for every doc in the corpus -- static
    text files, PDFs, and every blog post found under k9-aif-blogs/_posts
    (globbed, not hardcoded, so new posts get picked up automatically on
    the next seed run without editing this file). read is None when the
    doc is neither on disk nor available from GitHub (skipped)."""
    for label, path in TEXT_CORPUS:
        if path.exists():
            yield label, str(path), (lambda p=path: p.read_text(encoding="utf-8"))
        elif label in GITHUB_FALLBACK:
            yield label, f"github:{GITHUB_FALLBACK[label]}", (lambda l=label: _read_github(l))
        else:
            yield label, str(path), None

    for label, path in PDF_CORPUS:
        yield label, str(path), ((lambda p=path: _extract_pdf_text(p)) if path.exists() else None)

    if BLOGS_ROOT.exists():
        for post_path in sorted(BLOGS_ROOT.glob("*.md")):
            label = f"k9-aif-blogs/{post_path.stem}"
            yield label, str(post_path), (lambda p=post_path: p.read_text(encoding="utf-8"))

    for label, where, text in _video_docs():
        yield label, where, (lambda t=text: t)


# How many chunks each doc had at the last seed, so a reseed can delete
# the leftovers when a doc shrinks or a blog post is renamed/removed
# (upsert overwrites ids that still exist, but never removes the rest).
# Kept next to the vector store, in the same data volume.
def _manifest_path(config: dict) -> Path:
    base = os.environ.get("K9CHAT_CHROMA_PATH") or (config.get("vectordb") or {}).get("path") or "./.chroma"
    return Path(base) / "seed_manifest.json"


def _load_manifest(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


# With no manifest yet (first seed after this change), sweep this many ids
# past each doc's new chunk count, to clear leftovers from older seeds.
_FIRST_RUN_SWEEP = 64


def main() -> None:
    config = load_yaml(os.path.join(BASE_DIR, "config.yaml"))
    retriever = KnowledgeRetriever(config)

    total_docs = 0
    total_chunks = 0
    skipped: list[str] = []
    failed: list[str] = []

    manifest_file = _manifest_path(config)
    previous = _load_manifest(manifest_file)
    current = dict(previous)
    seen: set[str] = set()
    removed = 0

    for label, where, read in _iter_corpus():
        if read is None:
            skipped.append(f"{label} ({where})")
            continue

        try:
            text = read()
        except Exception as exc:
            failed.append(f"{label} ({where}): {exc}")
            continue

        chunker = _chunk_by_heading if label in HEADING_CHUNKED else chunk_text
        chunks = chunker(text, label)  # already prefixes each chunk "[label] ..."
        stored = 0
        for i, chunk in enumerate(chunks):
            ok = retriever.store_chunk(
                doc_id=f"{label}:{i}",
                text=chunk,
                metadata={
                    "text": chunk,
                    "source": label,
                    "chunk_index": i,
                },
            )
            if ok:
                stored += 1

        # Leftovers from a longer previous version of this doc.
        old_count = previous.get(label, len(chunks) + _FIRST_RUN_SWEEP)
        for i in range(len(chunks), old_count):
            retriever.delete_chunk(f"{label}:{i}")
            removed += 1 if label in previous else 0
        current[label] = len(chunks)
        seen.add(label)

        source = "" if not where.startswith("github:") else f" (from {where})"
        print(f"[seed] {label}: {stored}/{len(chunks)} chunks stored{source}")
        total_docs += 1
        total_chunks += stored

    # Blog posts that were renamed or deleted: only when the blog folder
    # itself was there this run, so a missing mount never wipes anything.
    prefixes = ["k9-aif-blogs/"] if BLOGS_ROOT.exists() else []
    if any(l.startswith(VIDEO_PREFIX) for l in seen):
        prefixes.append(VIDEO_PREFIX)   # the video list was read this run
    if prefixes:
        for label in [l for l in previous if l.startswith(tuple(prefixes)) and l not in seen]:
            for i in range(previous[label]):
                retriever.delete_chunk(f"{label}:{i}")
                removed += 1
            current.pop(label, None)
            print(f"[seed] {label}: removed (no longer published)")

    try:
        manifest_file.parent.mkdir(parents=True, exist_ok=True)
        manifest_file.write_text(json.dumps(current, indent=1, sort_keys=True))
    except OSError as exc:
        print(f"[seed] could not write {manifest_file}: {exc}")

    print(f"\n[seed] Done. {total_docs} documents, {total_chunks} chunks stored "
          f"into collection '{COLLECTION_NAME}'; {removed} stale chunk(s) removed.")

    if skipped:
        print(f"\n[seed] Skipped {len(skipped)} missing file(s) (not an error, just not found):")
        for s in skipped:
            print(f"  - {s}")

    if failed:
        print(f"\n[seed] Failed to read {len(failed)} file(s):")
        for f in failed:
            print(f"  - {f}")


if __name__ == "__main__":
    main()
