from blackglass_server.text_utils import split_frontmatter, extract_wikilinks, extract_tags


def test_split_frontmatter_with_yaml():
    text = "---\ntitle: Test\ntags: [a, b]\n---\nBody here."
    fm, body = split_frontmatter(text)
    assert fm == {"title": "Test", "tags": ["a", "b"]}
    assert body == "Body here."


def test_split_frontmatter_none():
    text = "No frontmatter here."
    fm, body = split_frontmatter(text)
    assert fm == {}
    assert body == "No frontmatter here."


def test_extract_wikilinks():
    body = "See [[Note One]] and [[Note Two|display]]."
    links = extract_wikilinks(body)
    assert links == ["Note One", "Note Two"]


def test_extract_wikilinks_empty():
    assert extract_wikilinks("No links here.") == []


def test_extract_tags_from_frontmatter():
    fm = {"tags": ["alpha", "beta"]}
    assert extract_tags(fm) == ["alpha", "beta"]


def test_extract_tags_string_value():
    fm = {"tags": "solo"}
    assert extract_tags(fm) == ["solo"]


def test_extract_tags_missing():
    assert extract_tags({}) == []
