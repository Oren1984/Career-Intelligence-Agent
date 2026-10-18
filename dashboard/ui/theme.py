"""Global styling: spacing, cards, badges, long-text handling, footer and RTL support."""
from __future__ import annotations

import streamlit as st

from dashboard.i18n import is_rtl

_BASE_CSS = """
<style>
:root {
  --cia-accent: #2a78d6;
  --cia-muted: rgba(128, 128, 128, 0.85);
  --cia-border: rgba(128, 128, 128, 0.25);
}
.block-container { padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1280px; }
/* Long text never breaks the layout on narrow screens */
[data-testid="stMarkdownContainer"] p, [data-testid="stMarkdownContainer"] li,
[data-testid="stCaptionContainer"] { overflow-wrap: anywhere; }
/* KPI cards */
[data-testid="stMetric"] { padding: 0.15rem 0.25rem; }
[data-testid="stMetricValue"] { font-size: 1.65rem; font-weight: 650; }
[data-testid="stMetricLabel"] p { font-size: 0.82rem; color: var(--cia-muted); }
.cia-subtitle { color: var(--cia-muted); margin-top: -0.6rem; margin-bottom: 1rem; }
.cia-badge {
  display: inline-block; padding: 2px 10px; border-radius: 999px;
  font-size: 0.8rem; font-weight: 600; color: #fff; white-space: nowrap;
}
.cia-chip {
  display: inline-block; padding: 1px 8px; border-radius: 6px; font-size: 0.78rem;
  border: 1px solid var(--cia-border); color: var(--cia-muted); white-space: nowrap;
}
.cia-footer {
  margin-top: 2.5rem; padding-top: 0.8rem; border-top: 1px solid var(--cia-border);
  font-size: 0.8rem; color: var(--cia-muted); text-align: center;
}
.cia-ltr { direction: ltr; unicode-bidi: isolate; display: inline-block; }
@media (max-width: 640px) {
  .block-container { padding-left: 0.8rem; padding-right: 0.8rem; }
  [data-testid="stMetricValue"] { font-size: 1.3rem; }
}
</style>
"""

_RTL_CSS = """
<style>
[data-testid="stMain"], [data-testid="stSidebar"] { direction: rtl; }
[data-testid="stMarkdownContainer"], [data-testid="stCaptionContainer"],
[data-testid="stWidgetLabel"], [data-testid="stMetric"] { text-align: right; }
[data-testid="stMarkdownContainer"] p, [data-testid="stMarkdownContainer"] li,
[data-testid="stMarkdownContainer"] h1, [data-testid="stMarkdownContainer"] h2,
[data-testid="stMarkdownContainer"] h3, [data-testid="stMarkdownContainer"] h4 { unicode-bidi: plaintext; }
input, textarea { unicode-bidi: plaintext; }
/* Technical content stays left-to-right */
code, pre, [data-testid="stCode"], [data-testid="stDataFrame"], [data-testid="stDataEditor"],
[data-testid="stVegaLiteChart"], [data-testid="stArrowVegaLiteChart"], input[type="password"],
.cia-ltr { direction: ltr; text-align: left; }
.cia-footer { direction: ltr; }
</style>
"""


def apply_theme(lang: str) -> None:
    st.markdown(_BASE_CSS, unsafe_allow_html=True)
    if is_rtl(lang):
        st.markdown(_RTL_CSS, unsafe_allow_html=True)
