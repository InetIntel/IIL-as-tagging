import pandas as pd

from as_tagging import ASTagging, SnapshotProvider
from as_tagging.as_tagging import TagHelp


class InMemoryProvider(SnapshotProvider):
    def list_snapshots(self):
        return ["2025-01"]

    def get_snapshot(self, date, use_cache=True):
        return pd.DataFrame({"anycast_v4_cnt": [1]}, index=pd.Index(["13335"], name="asn"))


def _tagger():
    return ASTagging(snapshot_provider=InMemoryProvider(), date="2025-01")


def test_help_atomic_tag_returns_plain_string():
    result = _tagger().Help("anycast_v4_cnt")

    assert isinstance(result, str)
    assert "Anycast" in result


def test_help_composite_tag_returns_tag_help_dict():
    result = _tagger().Help("Domestic")

    # Still a dict: existing code indexing by key keeps working unchanged.
    assert isinstance(result, TagHelp)
    assert isinstance(result, dict)
    assert result["Preset threshold"] == [0.66]
    assert "Background" in result


def test_help_composite_tag_renders_readably_not_as_single_line_repr():
    result = _tagger().Help("Sibling Transit")

    text = str(result)
    # Multi-line, one field per line, not a single-line dict repr.
    assert "\n" in text
    assert "Description:" in text
    assert "Background:" in text
    assert "{" not in text

    # The Jupyter rich-display hook renders the same content as Markdown.
    markdown = result._repr_markdown_()
    assert "**Description:**" in markdown
    assert "**Background:**" in markdown


def test_help_unknown_tag_returns_error_string():
    result = _tagger().Help("NoSuchTag")

    assert isinstance(result, str)
    assert "does not contain this tag" in result
