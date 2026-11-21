"""Generic rules (read-only): search, filters by level and source, pagination."""

import json
import math

import streamlit as st

from kbs import normalize
from src.front.rendering.alerts import LEVELS, PHARMACOKINETIC, level_codes
from src.front.rendering.rules import generic_rule_card

RULES_PER_PAGE = 25
SOURCES = ["All", "ANSM Thesaurus", "DDI-Predictor"]  # beginning of the "source" field of the rules


def render(rules):
    st.caption(
        "Rules extracted from the reference documents of src/kbs/KBS_Docs/ (src/kbs/generic_rules.json), read-only. "
        "A Thesaurus class (e.g. oral anticoagulants) is searched through the list of its INNs."
    )
    search_column, level_column, source_column = st.columns([3, 3, 2], vertical_alignment="bottom")
    search = normalize(search_column.text_input(
        "Search", placeholder="INN, class or keyword (e.g. apixaban, hyperkaliémie)", key="rule_search"
    ).strip())
    chosen_levels = level_column.multiselect(
        "Level", list(LEVELS.values()) + [PHARMACOKINETIC], placeholder="All levels"
    )
    chosen_source = source_column.selectbox("Source", SOURCES)

    filtered = [r for r in rules if _matches(r, search, chosen_levels, chosen_source)]
    _paginated(filtered)


def _matches(rule, search, chosen_levels, chosen_source):
    if chosen_source != "All" and not rule.get("source", "").startswith(chosen_source):
        return False
    if chosen_levels:
        labels = [LEVELS[c] for c in level_codes(rule)] or [PHARMACOKINETIC]
        if not any(l in chosen_levels for l in labels):
            return False
    return (
        not search
        or search in normalize(rule["alert"])
        or search in json.dumps(rule.get("drugs", []), ensure_ascii=False)
    )


def _paginated(rules):
    page_count = max(1, math.ceil(len(rules) / RULES_PER_PAGE))
    page_column, info_column = st.columns([1, 4], vertical_alignment="bottom")
    page = page_column.number_input(
        f"Page (of {page_count})", min_value=1, max_value=page_count, value=1, key="rules_page"
    )
    start = (page - 1) * RULES_PER_PAGE
    if rules:
        info_column.caption(f"Rules {start + 1} to {min(start + RULES_PER_PAGE, len(rules))} of {len(rules)}")
    else:
        info_column.caption("No rule matches the search.")
    st.markdown("".join(generic_rule_card(r) for r in rules[start:start + RULES_PER_PAGE]), unsafe_allow_html=True)
