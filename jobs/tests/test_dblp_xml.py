"""Regression test for a real, serious bug found running the ETL against the
full dblp dump: streaming a small in-memory XML document, lxml's
`resolve_entities=True` substitutes a DTD entity like `&uuml;` straight into
an element's `.text` - but streaming the real multi-GB file through
`iterparse` does not. libxml2's incremental push parser instead leaves an
`_Entity` node in the element's children (its own `.text` is the literal
`'&uuml;'` string, with the rest of the original text in its `.tail`), so
plain `.text` / `findtext()` silently truncates at the entity: a real author
tag containing "J&uuml;rgen Schneider" came back as just "J". Since author
identity in this pipeline is keyed by name text, this was silently merging
unrelated real authors who happened to truncate to the same prefix (verified
against the actual loaded database - see "2. Initial Slicing Task Table.md",
P2).

This can't be reproduced by parsing a small in-memory fixture (small
documents resolve the entity correctly), so this test instead builds the
exact `_Entity`-node tree structure observed via a real debug session
against the live dump, and asserts `element_text` recovers the true text
regardless of why the parser left it in that shape.
"""

from lxml import etree

from dblp_xml import author_key, element_text


def _make_author_with_unresolved_entity() -> etree._Element:
    """<author>J&uuml;rgen Schneider</author>, but with the entity left as
    an unresolved child node - exactly what was observed streaming the real
    dblp dump, rather than merged into `.text`."""
    author = etree.Element("author")
    author.text = "J"
    entity = etree.Entity("uuml")
    entity.tail = "rgen Schneider"
    author.append(entity)
    return author


def test_element_text_recovers_full_name_past_an_unresolved_entity():
    author = _make_author_with_unresolved_entity()

    assert author.text == "J"  # the naive/buggy read
    assert element_text(author) == "Jürgen Schneider"


def test_author_key_is_entity_safe():
    smith = etree.Element("author")
    smith.text = "Jane Smith"

    jurgen = _make_author_with_unresolved_entity()

    assert author_key(smith) == "name:Jane Smith"
    assert author_key(jurgen) == "name:Jürgen Schneider"
    # The specific real failure: before the fix, both of these would have
    # collapsed towards the same truncated "name:J"-ish key.
    assert author_key(smith) != author_key(jurgen)
