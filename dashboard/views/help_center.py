"""Help Center — searchable articles loaded from dashboard/help/<lang>.md.

Each article starts with a "## Title" line followed by "<!-- topic: key -->".
Contextual help buttons elsewhere set st.session_state["help_topic"] to open
the matching article.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import streamlit as st

from dashboard.i18n import DEFAULT_LANGUAGE
from dashboard.ui.components import empty_state, page_header
from dashboard.ui.context import lang, t

_HELP_DIR = Path(__file__).resolve().parent.parent / "help"
_TOPIC_RE = re.compile(r"<!--\s*topic:\s*([a-z0-9_-]+)\s*-->")


@dataclass(frozen=True)
class Article:
    topic: str
    title: str
    body: str


@lru_cache(maxsize=None)
def load_articles(language: str) -> tuple[Article, ...]:
    path = _HELP_DIR / f"{language}.md"
    if not path.exists():
        path = _HELP_DIR / f"{DEFAULT_LANGUAGE}.md"
    articles: list[Article] = []
    for block in re.split(r"(?m)^## ", path.read_text(encoding="utf-8"))[1:]:
        title, _, body = block.partition("\n")
        match = _TOPIC_RE.search(body)
        topic = match.group(1) if match else re.sub(r"\W+", "-", title.lower()).strip("-")
        articles.append(Article(topic=topic, title=title.strip(), body=_TOPIC_RE.sub("", body).strip()))
    return tuple(articles)


def search(articles, query: str):
    terms = [q for q in query.lower().split() if q]
    if not terms:
        return list(articles)
    return [a for a in articles if all(term in (a.title + "\n" + a.body).lower() for term in terms)]


def render() -> None:
    page_header("help.title", "help.subtitle")
    articles = load_articles(lang())
    selected = st.session_state.pop("help_topic", None)
    query = st.text_input(t("help.search"), placeholder=t("help.search_ph"), key="help_query")
    results = search(articles, query)
    if query:
        st.caption(t("help.results", n=len(results)))
    if not results:
        empty_state(t("help.no_results"))
        return
    if selected:
        results.sort(key=lambda a: a.topic != selected)
    for article in results:
        with st.expander(article.title, expanded=bool(query) or article.topic == selected):
            st.markdown(article.body)
