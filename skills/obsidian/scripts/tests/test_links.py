import json
from pathlib import Path
import subprocess
import sys

from links import parse_links, parse_tags, rewrite_link_target

SCRIPT = Path(__file__).resolve().parent.parent / "links.py"


class TestParseLinks:
    def test_plain_wikilink(self):
        links = parse_links("see [[Alpha]] for more")
        assert len(links) == 1
        assert links[0].target == "Alpha"
        assert links[0].is_embed is False
        assert links[0].display is None
        assert links[0].heading is None
        assert links[0].block is None

    def test_aliased_wikilink(self):
        links = parse_links("[[Alpha|the alpha]]")
        assert links[0].target == "Alpha"
        assert links[0].display == "the alpha"

    def test_heading_ref(self):
        links = parse_links("[[Alpha#Section Two]]")
        assert links[0].target == "Alpha"
        assert links[0].heading == "Section Two"
        assert links[0].block is None

    def test_block_ref(self):
        links = parse_links("[[Alpha#^abc-123]]")
        assert links[0].target == "Alpha"
        assert links[0].block == "abc-123"
        assert links[0].heading is None

    def test_heading_ref_with_alias(self):
        links = parse_links("[[Alpha#Section|short name]]")
        assert links[0].target == "Alpha"
        assert links[0].heading == "Section"
        assert links[0].display == "short name"

    def test_embed_marker(self):
        links = parse_links("![[Alpha]]")
        assert links[0].is_embed is True
        assert links[0].target == "Alpha"

    def test_embed_image(self):
        links = parse_links("![[diagram.png]]")
        assert links[0].is_embed is True
        assert links[0].target == "diagram.png"

    def test_folder_path_in_target(self):
        links = parse_links("[[notes/Alpha]]")
        assert links[0].target == "notes/Alpha"

    def test_self_heading_ref(self):
        links = parse_links("[[#Heading]]")
        assert links[0].target == ""
        assert links[0].heading == "Heading"

    def test_multiple_links_one_line(self):
        links = parse_links("[[A]] and [[B|the B]] and ![[C]]")
        assert [(lk.target, lk.is_embed) for lk in links] == [
            ("A", False),
            ("B", False),
            ("C", True),
        ]

    def test_skips_fenced_code_block(self):
        text = "before [[A]]\n```\n[[B]]\n```\n[[C]]\n"
        targets = [lk.target for lk in parse_links(text)]
        assert targets == ["A", "C"]

    def test_skips_inline_code(self):
        text = "real [[A]] vs `[[B]]` vs [[C]]"
        targets = [lk.target for lk in parse_links(text)]
        assert targets == ["A", "C"]

    def test_skips_indented_code_block(self):
        text = "para\n\n    [[A]]\n\nback [[B]]\n"
        targets = [lk.target for lk in parse_links(text)]
        assert targets == ["B"]

    def test_empty_brackets_ignored(self):
        assert parse_links("[[]] real [[A]]") == [
            lk for lk in parse_links("[[]] real [[A]]") if lk.target == "A"
        ]
        assert [lk.target for lk in parse_links("[[]] real [[A]]")] == ["A"]

    def test_span_tracks_full_match(self):
        text = "x [[Alpha]] y"
        link = parse_links(text)[0]
        assert text[link.span[0] : link.span[1]] == "[[Alpha]]"

    def test_embed_span_includes_bang(self):
        text = "x ![[Alpha]] y"
        link = parse_links(text)[0]
        assert text[link.span[0] : link.span[1]] == "![[Alpha]]"


class TestParseTags:
    def test_simple_tag(self):
        tags = parse_tags("hello #world today")
        assert [t.name for t in tags] == ["world"]

    def test_nested_tag(self):
        tags = parse_tags("#projects/obsidian/skill")
        assert tags[0].name == "projects/obsidian/skill"

    def test_tag_with_underscore_and_hyphen(self):
        tags = parse_tags("#snake_case and #kebab-case")
        assert sorted(t.name for t in tags) == ["kebab-case", "snake_case"]

    def test_pure_numeric_tag_rejected(self):
        assert parse_tags("#1234") == []

    def test_alphanumeric_with_letters_ok(self):
        assert [t.name for t in parse_tags("#tag1 and #1tag")] == ["tag1", "1tag"]

    def test_tag_at_start_of_line(self):
        assert [t.name for t in parse_tags("#foo")] == ["foo"]

    def test_heading_marker_not_a_tag(self):
        assert parse_tags("# Heading\nbody") == []

    def test_atx_heading_with_two_hashes_not_tag(self):
        assert parse_tags("## Subheading") == []

    def test_inline_attached_to_word_not_a_tag(self):
        assert parse_tags("color#red is not a tag") == []

    def test_url_fragment_not_a_tag(self):
        assert parse_tags("see https://example.com/page#anchor") == []

    def test_tag_in_callout_ok(self):
        assert [t.name for t in parse_tags("> [!note] alert\n> #important")] == ["important"]

    def test_skips_code_block(self):
        text = "real #tag\n```\n#fake\n```\nback #other"
        assert sorted(t.name for t in parse_tags(text)) == ["other", "tag"]

    def test_skips_inline_code(self):
        assert [t.name for t in parse_tags("real #tag `#fake` back #other")] == [
            "tag",
            "other",
        ]


class TestRewriteLinkTarget:
    def test_renames_simple(self):
        assert rewrite_link_target("see [[Old]]", "Old", "New") == "see [[New]]"

    def test_does_not_match_partial(self):
        assert (
            rewrite_link_target("[[Old]] and [[OldOther]]", "Old", "New")
            == "[[New]] and [[OldOther]]"
        )

    def test_preserves_alias(self):
        assert rewrite_link_target("[[Old|display]]", "Old", "New") == "[[New|display]]"

    def test_preserves_heading(self):
        assert rewrite_link_target("[[Old#Section]]", "Old", "New") == "[[New#Section]]"

    def test_preserves_block_ref(self):
        assert rewrite_link_target("[[Old#^abc]]", "Old", "New") == "[[New#^abc]]"

    def test_handles_embed(self):
        assert rewrite_link_target("![[Old]]", "Old", "New") == "![[New]]"

    def test_does_not_touch_code(self):
        text = "real [[Old]]\n```\n[[Old]]\n```\nend"
        out = rewrite_link_target(text, "Old", "New")
        assert "real [[New]]" in out
        assert "```\n[[Old]]\n```" in out

    def test_path_target_renamed(self):
        assert rewrite_link_target("[[notes/Old]]", "notes/Old", "archive/New") == "[[archive/New]]"

    def test_no_match_returns_unchanged(self):
        text = "[[A]] and [[B]] no Old here"
        assert rewrite_link_target(text, "C", "D") == text

    def test_case_insensitive_match(self):
        assert rewrite_link_target("[[old]]", "Old", "New") == "[[New]]"
        assert rewrite_link_target("[[OLD]]", "Old", "New") == "[[New]]"
        assert rewrite_link_target("[[oLd]]", "Old", "New") == "[[New]]"

    def test_case_insensitive_with_alias(self):
        assert rewrite_link_target("[[old|disp]]", "Old", "New") == "[[New|disp]]"

    def test_case_insensitive_path_form(self):
        assert rewrite_link_target("[[NOTES/old]]", "notes/Old", "archive/New") == "[[archive/New]]"

    def test_case_insensitive_does_not_match_partial(self):
        assert rewrite_link_target("[[oldother]]", "Old", "New") == "[[oldother]]"


class TestCli:
    def _run(self, *args: str, stdin: str | None = None):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            input=stdin,
            check=False,
        )

    def test_extract_outputs_json(self, tmp_path: Path):
        note = tmp_path / "n.md"
        note.write_text("see [[Alpha|a]] and #tag")
        result = self._run("extract", str(note))
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["wikilinks"][0]["target"] == "Alpha"
        assert data["tags"][0]["name"] == "tag"
