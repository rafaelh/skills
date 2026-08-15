from pathlib import Path

from conftest import TEST_VAULT
from parser import (
    load_spec,
    locate_vault,
    parse_declaration,
    parse_note,
    read_frontmatter,
)
import pytest


def declaration(text: str, host: str = "inline"):
    """Parse `text` as a whole declaration, the way its host delimits it."""
    return parse_declaration(text, Path("note.md"), host, 0, len(text))


class TestBindTargets:
    def test_bare_property(self):
        parsed = declaration("INPUT[text:count]")
        assert parsed is not None
        assert parsed.bind_target is not None
        assert parsed.bind_target.prop_path == ("count",)
        assert parsed.bind_target.storage_path is None
        assert parsed.bind_target.storage_type is None

    def test_cross_note(self):
        parsed = declaration("INPUT[text:other note#title]")
        assert parsed is not None
        assert parsed.bind_target is not None
        assert parsed.bind_target.storage_path == "other note"
        assert parsed.bind_target.prop_path == ("title",)

    def test_dotted_path(self):
        parsed = declaration("INPUT[text:proficiency.acrobatics]")
        assert parsed is not None
        assert parsed.bind_target is not None
        assert parsed.bind_target.prop_path == ("proficiency", "acrobatics")

    def test_quoted_object_access(self):
        parsed = declaration('INPUT[text:nested["object"]]')
        assert parsed is not None
        assert parsed.bind_target is not None
        assert parsed.bind_target.prop_path == ("nested", "object")
        assert parsed.bind_target.props[1].kind == "quoted"

    def test_list_index(self):
        parsed = declaration("INPUT[text:list[0]]")
        assert parsed is not None
        assert parsed.bind_target is not None
        assert parsed.bind_target.props[1].kind == "index"
        assert parsed.bind_target.props[1].name == "0"

    @pytest.mark.parametrize("scope", ["memory", "globalMemory"])
    def test_memory_scope(self, scope: str):
        parsed = declaration(f"INPUT[text:{scope}^scratch]")
        assert parsed is not None
        assert parsed.bind_target is not None
        assert parsed.bind_target.storage_type == scope
        assert parsed.bind_target.prop_path == ("scratch",)

    def test_render_round_trips(self):
        for source in (
            "count",
            "other note#title",
            "proficiency.acrobatics",
            'nested["object"]',
            "list[0]",
            "memory^scratch",
        ):
            parsed = declaration(f"INPUT[text:{source}]")
            assert parsed is not None
            assert parsed.bind_target is not None
            assert parsed.bind_target.render() == source

    def test_unicode_property(self):
        parsed = declaration("INPUT[text:こんにちは]")
        assert parsed is not None
        assert parsed.bind_target is not None
        assert parsed.bind_target.prop_path == ("こんにちは",)


class TestArguments:
    def test_no_arguments(self):
        parsed = declaration("INPUT[text():count]")
        assert parsed is not None
        assert parsed.arguments == ()

    def test_flag_argument(self):
        parsed = declaration("INPUT[slider(addLabels):count]")
        assert parsed is not None
        assert parsed.arguments[0].name == "addLabels"
        assert parsed.arguments[0].values == ()

    def test_multiple_values(self):
        parsed = declaration("INPUT[inlineSelect(option(1, Normal Pace)):speed]")
        assert parsed is not None
        assert parsed.arguments[0].values == ("1", "Normal Pace")

    def test_escaped_option_strings(self):
        parsed = declaration(
            r"INPUT[inlineSelect(option(0, 'don\'t do this'), option(1, 'do this \\')):choice]"
        )
        assert parsed is not None
        assert parsed.errors == ()
        assert parsed.arguments[0].values == ("0", "don't do this")
        assert parsed.arguments[1].values == ("1", "do this \\")

    def test_brackets_inside_an_argument_value(self):
        parsed = declaration("INPUT[inlineSelect(option(80, Griffon [flying])):speed]")
        assert parsed is not None
        assert parsed.errors == ()
        assert parsed.arguments[0].values == ("80", "Griffon [flying]")

    def test_multiline_declaration(self):
        parsed = declaration(
            "INPUT[select(\noption(option a),\noption(option b)\n):choice]", host="fence"
        )
        assert parsed is not None
        assert parsed.errors == ()
        assert len(parsed.arguments) == 2

    def test_trailing_comma_is_an_error(self):
        parsed = declaration("INPUT[inlineSelect(option(a,)):choice]")
        assert parsed is not None
        assert parsed.errors != ()


class TestTemplates:
    def test_template_name(self):
        parsed = declaration("INPUT[myTemplate][toggle:done]")
        assert parsed is not None
        assert parsed.template_name == "myTemplate"
        assert parsed.field_type == "toggle"

    def test_template_with_spaces(self):
        parsed = declaration("INPUT[my template][toggle:done]")
        assert parsed is not None
        assert parsed.template_name == "my template"

    def test_template_supplies_the_type(self):
        parsed = declaration("INPUT[myTemplate][]")
        assert parsed is not None
        assert parsed.errors == ()
        assert parsed.field_type is None

    def test_empty_template_name_is_an_error(self):
        parsed = declaration("INPUT[][toggle:done]")
        assert parsed is not None
        assert parsed.errors != ()


class TestViewFields:
    def test_reads_every_placeholder(self):
        parsed = declaration("VIEW[{a} + {b}]")
        assert parsed is not None
        assert [target.render() for target in parsed.read_targets] == ["a", "b"]
        assert parsed.field_type is None

    def test_math_with_write_target(self):
        parsed = declaration("VIEW[{count} * 2][math:doubled]")
        assert parsed is not None
        assert parsed.field_type == "math"
        assert parsed.bind_target is not None
        assert parsed.bind_target.render() == "doubled"

    def test_hidden_argument(self):
        parsed = declaration("VIEW[floor(({STR} - 10) / 2)][math(hidden):memory^STR_mod]")
        assert parsed is not None
        assert parsed.errors == ()
        assert parsed.arguments[0].name == "hidden"
        assert parsed.read_targets[0].render() == "STR"


class TestButtons:
    def test_group_reference(self):
        parsed = declaration("BUTTON[one, two, three]")
        assert parsed is not None
        assert parsed.button_ids == ("one", "two", "three")

    def test_single_reference(self):
        parsed = declaration("BUTTON[only]")
        assert parsed is not None
        assert parsed.button_ids == ("only",)

    def test_button_config_yaml(self):
        source = "label: Go\nstyle: primary\nid: go\naction:\n  type: command\n  command: x\n"
        parsed = parse_declaration(
            source, Path("n.md"), "fence", 0, len(source), "meta-bind-button"
        )
        assert parsed is not None
        assert isinstance(parsed.button_config, dict)
        assert parsed.button_config["id"] == "go"

    def test_button_bind_target_keeps_its_offset(self):
        source = "label: Go\nstyle: primary\naction:\n  type: updateMetadata\n  bindTarget: count\n"
        parsed = parse_declaration(
            source, Path("n.md"), "fence", 0, len(source), "meta-bind-button"
        )
        assert parsed is not None
        target = parsed.read_targets[0]
        assert target.render() == "count"
        assert source[target.span.start : target.span.end] == "count"

    def test_malformed_button_yaml_is_reported(self):
        source = "label: Unbalanced\nstyle: [default\n"
        parsed = parse_declaration(
            source, Path("n.md"), "fence", 0, len(source), "meta-bind-button"
        )
        assert parsed is not None
        assert parsed.errors != ()


class TestHosts:
    def test_inline_span_in_prose(self):
        text = "text `INPUT[text:count]` more text\n"
        found = parse_note(Path("n.md"), text)
        assert len(found) == 1
        assert found[0].host == "inline"
        assert found[0].line == 1

    def test_fields_in_a_table_row(self):
        text = "| a | `INPUT[number:count]` | `VIEW[{count}]` |\n"
        assert len(parse_note(Path("n.md"), text)) == 2

    def test_fields_in_a_callout(self):
        text = "> [!note] T\n> `INPUT[toggle:done]`\n"
        assert len(parse_note(Path("n.md"), text)) == 1

    def test_frontmatter_is_not_scanned(self):
        text = "---\nnote: '`INPUT[text:count]`'\n---\n\nbody\n"
        assert parse_note(Path("n.md"), text) == []

    def test_declarations_inside_a_plain_code_fence_are_ignored(self):
        text = "```js\nconst s = `\\`INPUT[number:list[0]]\\``;\n```\n"
        assert parse_note(Path("n.md"), text) == []

    def test_meta_bind_fence(self):
        text = "```meta-bind\nINPUT[toggle:done]\n```\n"
        found = parse_note(Path("n.md"), text)
        assert len(found) == 1
        assert found[0].host == "fence"
        assert found[0].line == 2

    def test_js_view_fence(self):
        text = "```meta-bind-js-view\n{count} as count\nsave to {doubled}\n---\nreturn 1;\n```\n"
        found = parse_note(Path("n.md"), text)
        assert len(found) == 1
        assert found[0].kind == "js-view"
        assert found[0].read_targets[0].render() == "count"
        assert found[0].bind_target is not None
        assert found[0].bind_target.render() == "doubled"
        assert found[0].js_code == "return 1;"

    def test_embed_fence(self):
        text = "```meta-bind-embed\n[[Other Note]]\n```\n"
        found = parse_note(Path("n.md"), text)
        assert found[0].kind == "embed"
        assert found[0].embed_target == "Other Note"

    def test_line_and_column_are_one_based(self):
        text = "one\ntwo `INPUT[text:count]` three\n"
        found = parse_note(Path("n.md"), text)
        assert (found[0].line, found[0].column) == (2, 6)

    def test_declarations_come_back_in_document_order(self):
        text = "`INPUT[text:a]`\n\n```meta-bind\nINPUT[text:b]\n```\n\n`INPUT[text:c]`\n"
        found = parse_note(Path("n.md"), text)
        assert [d.bind_target.render() for d in found if d.bind_target] == ["a", "b", "c"]

    def test_non_declaration_code_spans_are_skipped(self):
        assert parse_note(Path("n.md"), "run `ls -la` first\n") == []


class TestVault:
    def test_locate_vault_from_a_note(self):
        assert locate_vault(TEST_VAULT / "Fields.md") == TEST_VAULT.resolve()

    def test_read_frontmatter(self):
        frontmatter = read_frontmatter(TEST_VAULT / "Fields.md")
        assert frontmatter["count"] == 3
        assert frontmatter["nested"] == {"object": "nested value"}

    def test_read_frontmatter_without_any(self):
        assert read_frontmatter(TEST_VAULT / ".obsidian" / "community-plugins.json") == {}

    def test_fixture_vault_parses_without_errors_outside_broken(self):
        for note in ("Fields.md", "Buttons.md", "Other Note.md"):
            for parsed in parse_note(TEST_VAULT / note):
                assert parsed.errors == (), f"{note}:{parsed.line} {parsed.raw}"


class TestSpec:
    def test_loads_the_committed_spec(self):
        spec = load_spec()
        assert "toggle" in spec.input_field_types
        assert "math" in spec.view_field_types
        assert "updateMetadata" in spec.button_action_types
        assert spec.raw["embed_max_depth"] == 8

    def test_option_argument_table(self):
        option = load_spec().input_field_arguments["option"]
        assert option["allow_multiple"] is True
        assert option["arities"] == [1, 2]
        assert "select" in option["allowed_field_types"]

    def test_select_does_not_render_inline(self):
        types = load_spec().input_field_types
        assert types["select"]["allow_inline"] is False
        assert types["text"]["allow_inline"] is True
