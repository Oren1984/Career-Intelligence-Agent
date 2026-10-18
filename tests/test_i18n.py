"""Translation catalog completeness and hard-coded string checks."""
import re
import string
from pathlib import Path

import pytest

from dashboard.i18n import catalog, translate

ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = ROOT / "dashboard"
SOURCES = [p for p in DASHBOARD.rglob("*.py") if "i18n" not in p.parts]


def _placeholders(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def test_catalogs_have_identical_keys():
    en, he = catalog("en"), catalog("he")
    assert set(en) - set(he) == set(), "missing in he.yaml"
    assert set(he) - set(en) == set(), "missing in en.yaml"


def test_placeholders_match_between_languages():
    en, he = catalog("en"), catalog("he")
    mismatched = [k for k in en if _placeholders(en[k]) != _placeholders(he[k])]
    assert mismatched == []


def test_hebrew_values_are_translated():
    en, he = catalog("en"), catalog("he")
    # Technical tokens may stay identical; real sentences must not.
    same = [k for k in en if en[k] == he[k] and len(en[k]) > 12 and " " in en[k]]
    assert same == []


def _code() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in SOURCES)


def test_every_static_key_used_in_code_exists():
    keys = set(re.findall(r"""\bt\(\s*["']([a-z_]+(?:\.[A-Za-z0-9_\-]+)+)["']""", _code()))
    assert keys, "no keys found — regex broken?"
    missing = sorted(k for k in keys if k not in catalog("en"))
    assert missing == []


def test_every_dynamic_key_prefix_exists():
    prefixes = set(re.findall(r"""\bt\(\s*f["']([a-z_]+)\.\{""", _code()))
    en = catalog("en")
    missing = sorted(p for p in prefixes if not any(k.startswith(p + ".") for k in en))
    assert missing == []


def test_enumerated_values_are_translated():
    from app.db.models import VALID_FEEDBACK_SIGNALS
    from app.services.job_service import VALID_STATUSES
    from dashboard.ui.components import LABEL_KEYS
    from dashboard.views.analyze_job import EXEC_MODES
    from dashboard.views.jobs_common import FETCH_MODES, LEVELS

    expected = (
        [f"job_status.{s}" for s in VALID_STATUSES]
        + [f"feedback.{s}" for s in VALID_FEEDBACK_SIGNALS]
        + [f"labels.{k}" for k in LABEL_KEYS.values()]
        + [f"exec.{m}" for m in EXEC_MODES] + [f"exec.{m}_desc" for m in EXEC_MODES]
        + [f"levels.{lv}" for lv in LEVELS] + [f"source_modes.{m}" for m in FETCH_MODES]
        + [f"coverage.{c}" for c in ("high", "medium", "low", "none")]
        + [f"apply_decision.{d}" for d in ("YES", "NO", "CONDITIONAL")]
        + [f"workspace.{w}" for w in ("personal", "demo")]
    )
    for lang in ("en", "he"):
        missing = [k for k in expected if k not in catalog(lang)]
        assert missing == [], lang


_WIDGETS = ("title|header|subheader|caption|button|selectbox|text_input|text_area|radio|slider|checkbox|"
            "toggle|metric|info|warning|error|success|expander|form_submit_button|download_button|"
            "file_uploader|link_button|popover|toast|tabs|date_input|number_input|multiselect")
_ALLOWED_LITERALS = {"desc", "description"}  # collapsed labels, never shown


def test_no_hard_coded_ui_strings():
    pattern = re.compile(rf"""st\.(?:{_WIDGETS})\(\s*["']([^"']*[A-Za-z]{{3,}}[^"']*)["']""")
    offenders = []
    for path in SOURCES:
        for m in pattern.finditer(path.read_text(encoding="utf-8")):
            if m.group(1) not in _ALLOWED_LITERALS:
                offenders.append(f"{path.relative_to(ROOT)}: {m.group(1)}")
    assert offenders == []


@pytest.mark.parametrize("lang", ["en", "he"])
def test_translate_formats_and_falls_back(lang):
    assert translate(lang, "classic.count", n=3).count("3") == 1
    assert translate(lang, "no.such.key") == "no.such.key"
