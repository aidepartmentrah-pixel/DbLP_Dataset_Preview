"""CHAT-2/6 accept check: tool dispatch and citation-key regex/validation,
against a seeded real Postgres database (see conftest.py)."""

from app.chat_tools import SQL_TEMPLATES, UnknownTemplate, sql_query
from app.routers.chat import CITATION_KEY_RE, _validate_citations


def test_citation_key_regex_matches_dblp_keys():
    text_ = "Jane Smith's work [conf/kdd/P1] builds on [journals/tkde/P3]."
    assert CITATION_KEY_RE.findall(text_) == ["conf/kdd/P1", "journals/tkde/P3"]


def test_citation_key_regex_ignores_non_key_brackets():
    assert CITATION_KEY_RE.findall("See [1] for details.") == []


def test_validate_citations_drops_hallucinated_keys(seeded_client):
    with seeded_client.test_session_factory() as session:
        real = "conf/kdd/P1"
        fake = "conf/kdd/DoesNotExist99"
        result = _validate_citations(session, f"Cited [{real}] and also [{fake}].")
    assert result == [real]


def test_sql_query_unknown_template_raises():
    import pytest

    with pytest.raises(UnknownTemplate):
        sql_query("not_a_real_template")


def test_sql_query_kpis_runs_for_real_against_the_readonly_role():
    """chat_tools.sql_query always uses DATABASE_URL_READONLY (the real
    dblp_readonly Postgres role - see db/init/004_readonly_role.sql), which
    points at the real production database in every environment, not a
    per-test seeded one. So this exercises the real, live-loaded data
    directly, rather than trying to redirect a fixed role to a throwaway
    test database."""
    rows = sql_query("kpis")
    assert len(rows) == 1
    assert rows[0]["paper_count"] > 0


def test_sql_templates_cover_expected_question_types():
    # §6.4 example questions: "top authors in a venue, papers per year, an
    # author's co-authors" - confirm each has a real template.
    assert "papers_per_year" in SQL_TEMPLATES
    assert "top_authors_by_papers" in SQL_TEMPLATES
    assert "author_coauthors" in SQL_TEMPLATES
    assert len(SQL_TEMPLATES) >= 15
