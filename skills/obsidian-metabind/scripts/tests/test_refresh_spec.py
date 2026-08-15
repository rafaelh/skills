from __future__ import annotations

import json
from typing import TYPE_CHECKING

from conftest import TEST_VAULT
import pytest
from refresh_docs import (
    RefreshError,
    build_spec,
    main,
    parse_const_object,
    parse_enums,
    parse_interfaces,
    plugin_version,
    strip_comments,
)

if TYPE_CHECKING:
    from pathlib import Path

INPUT_TYPES = [
    ("TOGGLE", "toggle"),
    ("SLIDER", "slider"),
    ("TEXT", "text"),
    ("TEXT_AREA", "textArea"),
    ("SELECT", "select"),
    ("MULTI_SELECT", "multiSelect"),
    ("DATE", "date"),
    ("TIME", "time"),
    ("DATE_PICKER", "datePicker"),
    ("NUMBER", "number"),
    ("SUGGESTER", "suggester"),
    ("EDITOR", "editor"),
    ("IMAGE_SUGGESTER", "imageSuggester"),
    ("PROGRESS_BAR", "progressBar"),
    ("INLINE_SELECT", "inlineSelect"),
    ("LIST", "list"),
]
INPUT_ARGS = [
    ("CLASS", "class"),
    ("ADD_LABELS", "addLabels"),
    ("MIN_VALUE", "minValue"),
    ("MAX_VALUE", "maxValue"),
    ("STEP_SIZE", "stepSize"),
    ("OPTION", "option"),
    ("TITLE", "title"),
    ("SHOWCASE", "showcase"),
    ("ON_VALUE", "onValue"),
    ("OFF_VALUE", "offValue"),
    ("DEFAULT_VALUE", "defaultValue"),
]
ACTIONS = [
    ("COMMAND", "command", "Command", ["command: string;"]),
    ("JS", "js", "JS", ["file: string;", "args?: Record<string, unknown>;"]),
    ("OPEN", "open", "Open", ["link: string;", "newTab?: boolean;"]),
    ("INPUT", "input", "Input", ["str: string;"]),
    ("SLEEP", "sleep", "Sleep", ["ms: number;"]),
    ("CREATE_NOTE", "createNote", "CreateNote", ["fileName: string;", "folderPath?: string;"]),
    ("REPLACE_SELF", "replaceSelf", "ReplaceSelf", ["replacement: string;"]),
    ("INSERT_INTO_NOTE", "insertIntoNote", "InsertIntoNote", ["line: number;", "value: string;"]),
    ("INLINE_JS", "inlineJS", "InlineJS", ["code: string;"]),
    (
        "UPDATE_METADATA",
        "updateMetadata",
        "UpdateMetadata",
        ["bindTarget: string;", "evaluate: boolean;", "value: string;"],
    ),
]


def field_configs_ts(input_types: list[tuple[str, str]] = INPUT_TYPES) -> str:
    """A stand-in for FieldConfigs.ts with the same shapes, not its GPL text."""
    members = "\n".join(f"\t{key} = '{value}'," for key, value in input_types)
    configs = "\n".join(
        f"\t[InputFieldType.{key}]: {{\n"
        f"\t\ttype: InputFieldType.{key},\n"
        f"\t\tallowInBlock: true,\n"
        f"\t\tallowInline: {'false' if value in ('select', 'multiSelect') else 'true'},\n"
        f"\t}},"
        for key, value in input_types
    )
    argument_members = "\n".join(f"\t{key} = '{value}'," for key, value in INPUT_ARGS)
    argument_configs = "\n".join(
        f"\t[InputFieldArgumentType.{key}]: {{\n"
        f"\t\ttype: InputFieldArgumentType.{key},\n"
        f"\t\tallowedFieldTypes: [InputFieldType.SLIDER],\n"
        f"\t\tvalues: [[{{ name: 'value', allowed: ['number'], description: 'x' }}]],\n"
        f"\t\tallowMultiple: false,\n"
        f"\t}},"
        for key, _ in INPUT_ARGS
    )
    return f"""
/**
 * @internal — a doc comment mentioning a // slash and a 'quote'.
 */
export enum InputFieldType {{
{members}

\tINVALID = 'invalid',
}}

export enum InputFieldArgumentType {{
{argument_members}

\tINVALID = 'invalid',
}}

export const InputFieldConfigs: Record<InputFieldType, InputFieldConfig> = {{
{configs}
\t[InputFieldType.INVALID]: {{
\t\ttype: InputFieldType.INVALID,
\t\tallowInBlock: false,
\t\tallowInline: false,
\t}},
}} as const;

export const InputFieldArgumentConfigs: Record<
\tInputFieldArgumentType,
\tInputFieldArgumentConfig
> = {{
{argument_configs}
\t[InputFieldArgumentType.OPTION]: {{
\t\ttype: InputFieldArgumentType.OPTION,
\t\tallowedFieldTypes: [InputFieldType.SELECT, InputFieldType.INLINE_SELECT],
\t\tvalues: [
\t\t\t[{{ name: 'value', allowed: [], description: '' }}],
\t\t\t[
\t\t\t\t{{ name: 'value', allowed: [], description: '' }},
\t\t\t\t{{ name: 'name', allowed: [], description: '' }},
\t\t\t],
\t\t],
\t\tallowMultiple: true,
\t}},
\t[InputFieldArgumentType.INVALID]: {{
\t\ttype: InputFieldArgumentType.INVALID,
\t\tallowedFieldTypes: [],
\t\tvalues: [[]],
\t\tallowMultiple: true,
\t}},
}};

export enum ViewFieldType {{
\tMATH = 'math',
\tTEXT = 'text',
\tLINK = 'link',
\tIMAGE = 'image',

\tINVALID = 'invalid',
}}

export enum ViewFieldArgumentType {{
\tRENDER_MARKDOWN = 'renderMarkdown',
\tHIDDEN = 'hidden',
\tCLASS = 'class',

\tINVALID = 'invalid',
}}

export const ViewFieldArgumentConfigs: Record<ViewFieldArgumentType, ViewFieldArgumentConfig> = {{
\t[ViewFieldArgumentType.RENDER_MARKDOWN]: {{
\t\ttype: ViewFieldArgumentType.RENDER_MARKDOWN,
\t\tallowedFieldTypes: [ViewFieldType.TEXT],
\t\tvalues: [[], [{{ name: 'value', allowed: ['true', 'false'], description: '' }}]],
\t\tallowMultiple: false,
\t}},
\t[ViewFieldArgumentType.HIDDEN]: {{
\t\ttype: ViewFieldArgumentType.HIDDEN,
\t\tallowedFieldTypes: [],
\t\tvalues: [[], [{{ name: 'value', allowed: ['true', 'false'], description: '' }}]],
\t\tallowMultiple: false,
\t}},
\t[ViewFieldArgumentType.CLASS]: {{
\t\ttype: ViewFieldArgumentType.CLASS,
\t\tallowedFieldTypes: [],
\t\tvalues: [[{{ name: 'className', allowed: [], description: '' }}]],
\t\tallowMultiple: true,
\t}},
\t[ViewFieldArgumentType.INVALID]: {{
\t\ttype: ViewFieldArgumentType.INVALID,
\t\tallowedFieldTypes: [],
\t\tvalues: [[]],
\t\tallowMultiple: true,
\t}},
}};

export const EMBED_MAX_DEPTH = 8;
"""


def button_config_ts() -> str:
    members = "\n".join(f"\t{key} = '{value}'," for key, value, _, _ in ACTIONS)
    interfaces = "\n".join(
        f"export interface {name}ButtonAction {{\n"
        f"\ttype: ButtonActionType.{key};\n" + "".join(f"\t{field}\n" for field in fields) + "}\n"
        for key, _, name, fields in ACTIONS
    )
    return f"""
export enum ButtonStyleType {{
\t/** Default grey button */
\tDEFAULT = 'default',
\tPRIMARY = 'primary',
\tDESTRUCTIVE = 'destructive',
\tPLAIN = 'plain',
}}

export enum ButtonActionType {{
{members}
}}

{interfaces}

export interface ButtonConfig {{
\t/** The text displayed on the button */
\tlabel: string;
\ticon?: string;
\tstyle: ButtonStyleType;
\tclass?: string;
\ttooltip?: string;
\tid?: string;
\thidden?: boolean;
\taction?: ButtonAction;
\tactions?: ButtonAction[];
}}
"""


def fake_fetcher(*, field_configs: str | None = None, tree: list[str] | None = None) -> object:
    sources = {
        "FieldConfigs.ts": field_configs if field_configs is not None else field_configs_ts(),
        "ButtonConfig.ts": button_config_ts(),
    }

    def fetch(url: str) -> bytes:
        if "/commits/" in url:
            return json.dumps({"sha": "0" * 40}).encode()
        if "/git/trees/" in url:
            paths = tree if tree is not None else []
            return json.dumps({"tree": [{"type": "blob", "path": path} for path in paths]}).encode()
        for name, body in sources.items():
            if url.endswith(name):
                return body.encode()
        return f"# cached body of {url}\n".encode()

    return fetch


class TestTypeScriptParsing:
    def test_strip_comments_keeps_strings(self):
        source = "const a = 'http://x'; // trailing\n/* block */ const b = 1;"
        stripped = strip_comments(source)
        assert "'http://x'" in stripped
        assert "trailing" not in stripped
        assert "block" not in stripped

    def test_parse_enums(self):
        enums = parse_enums(strip_comments(button_config_ts()))
        assert enums["ButtonStyleType"]["PRIMARY"] == "primary"
        assert enums["ButtonActionType"]["UPDATE_METADATA"] == "updateMetadata"

    def test_parse_const_object_resolves_computed_keys(self):
        source = strip_comments(field_configs_ts())
        configs = parse_const_object(source, "InputFieldConfigs", parse_enums(source))
        assert configs["toggle"] == {
            "type": "toggle",
            "allowInBlock": True,
            "allowInline": True,
        }

    def test_parse_const_object_resolves_nested_enum_references(self):
        source = strip_comments(field_configs_ts())
        configs = parse_const_object(source, "InputFieldArgumentConfigs", parse_enums(source))
        assert configs["option"]["allowedFieldTypes"] == ["select", "inlineSelect"]
        assert len(configs["option"]["values"]) == 2

    def test_missing_export_is_an_error(self):
        with pytest.raises(RefreshError, match="not found"):
            parse_const_object("export const Other = {};", "InputFieldConfigs", {})

    def test_parse_interfaces_marks_optional_fields(self):
        interfaces = parse_interfaces(strip_comments(button_config_ts()))
        assert interfaces["OpenButtonAction"]["link"]["optional"] is False
        assert interfaces["OpenButtonAction"]["newTab"]["optional"] is True


class TestBuildSpec:
    def spec(self):
        return build_spec(field_configs_ts(), button_config_ts(), {"source_ref": "test"})

    def test_input_field_types(self):
        types = self.spec()["input_field_types"]
        assert "invalid" not in types
        assert types["select"]["allow_inline"] is False
        assert types["text"]["allow_inline"] is True

    def test_argument_arities(self):
        option = self.spec()["input_field_arguments"]["option"]
        assert option["arities"] == [1, 2]
        assert option["allow_multiple"] is True

    def test_view_fields(self):
        spec = self.spec()
        assert set(spec["view_field_types"]) == {"math", "text", "link", "image"}
        assert set(spec["view_field_arguments"]) == {"renderMarkdown", "hidden", "class"}

    def test_button_actions(self):
        actions = self.spec()["button_action_types"]
        assert actions["sleep"] == {"required": ["ms"], "optional": []}
        assert actions["open"] == {"required": ["link"], "optional": ["newTab"]}

    def test_button_config_fields(self):
        fields = self.spec()["button_config_fields"]
        assert fields["required"] == ["label", "style"]
        assert "actions" in fields["optional"]

    def test_embed_max_depth(self):
        assert self.spec()["embed_max_depth"] == 8

    def test_provenance_is_carried_through(self):
        assert self.spec()["provenance"] == {"source_ref": "test"}

    def test_sanity_floor_rejects_a_truncated_source(self):
        with pytest.raises(RefreshError, match="sanity floor"):
            build_spec(field_configs_ts(INPUT_TYPES[:4]), button_config_ts(), {})

    def test_missing_enum_is_an_error(self):
        with pytest.raises(RefreshError, match="upstream layout changed"):
            build_spec("export const EMBED_MAX_DEPTH = 8;", button_config_ts(), {})


class TestVersionPinning:
    def test_reads_the_vault_manifest(self):
        assert plugin_version(TEST_VAULT, "obsidian-meta-bind-plugin", "1.5.1") == (
            "1.5.0",
            "vault-manifest",
        )

    def test_reads_the_js_engine_manifest(self):
        assert plugin_version(TEST_VAULT, "js-engine", "0.3.6") == ("0.3.5", "vault-manifest")

    def test_falls_back_without_a_vault(self):
        assert plugin_version(None, "obsidian-meta-bind-plugin", "1.5.1") == ("1.5.1", "fallback")

    def test_falls_back_without_a_manifest(self, tmp_path: Path):
        (tmp_path / ".obsidian").mkdir()
        assert plugin_version(tmp_path, "obsidian-meta-bind-plugin", "1.5.1") == (
            "1.5.1",
            "fallback",
        )


class TestCli:
    def test_generates_the_spec(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        spec_path = tmp_path / "field-spec.json"
        code = main(
            [
                "--vault",
                str(TEST_VAULT),
                "--only",
                "spec",
                "--spec-path",
                str(spec_path),
                "--json",
                "--quiet",
            ],
            fetcher=fake_fetcher(),
        )
        assert code == 0
        capsys.readouterr()
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        assert spec["provenance"]["source_ref"] == "1.5.0"
        assert spec["provenance"]["meta_bind_version"] == "1.5.0"
        assert spec["provenance"]["source_commit"] == "0" * 40

    def test_ref_overrides_the_vault_version(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ):
        spec_path = tmp_path / "field-spec.json"
        main(
            [
                "--vault",
                str(TEST_VAULT),
                "--ref",
                "1.4.0",
                "--only",
                "spec",
                "--spec-path",
                str(spec_path),
                "--quiet",
            ],
            fetcher=fake_fetcher(),
        )
        capsys.readouterr()
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        assert spec["provenance"]["source_ref"] == "1.4.0"

    def test_regenerating_is_byte_identical(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ):
        spec_path = tmp_path / "field-spec.json"
        argv = [
            "--vault",
            str(TEST_VAULT),
            "--only",
            "spec",
            "--spec-path",
            str(spec_path),
            "--quiet",
        ]
        main(argv, fetcher=fake_fetcher())
        first = spec_path.read_bytes()
        main(argv, fetcher=fake_fetcher())
        capsys.readouterr()
        assert spec_path.read_bytes() == first

    def test_a_broken_upstream_leaves_the_spec_untouched(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ):
        spec_path = tmp_path / "field-spec.json"
        spec_path.write_text('{"kept": true}\n', encoding="utf-8")
        code = main(
            [
                "--vault",
                str(TEST_VAULT),
                "--only",
                "spec",
                "--spec-path",
                str(spec_path),
                "--quiet",
            ],
            fetcher=fake_fetcher(field_configs=field_configs_ts(INPUT_TYPES[:3])),
        )
        assert code == 2
        assert "sanity floor" in capsys.readouterr().err
        assert spec_path.read_text(encoding="utf-8") == '{"kept": true}\n'

    def test_caches_docs_prose(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        code = main(
            [
                "--vault",
                str(TEST_VAULT),
                "--only",
                "cache",
                "--cache-dir",
                str(tmp_path),
                "--quiet",
            ],
            fetcher=fake_fetcher(
                tree=["src/content/docs/guides/buttons.md", "src/content/docs/reference/api.mdx"]
            ),
        )
        assert code == 0
        capsys.readouterr()
        assert (tmp_path / "docs" / "guides" / "buttons.md").is_file()
        assert (tmp_path / "docs" / "reference" / "api.mdx").is_file()
        assert (tmp_path / "js-engine" / "index.ts").is_file()
        assert (tmp_path / "js-engine" / "README.md").is_file()

    def test_cache_skips_unchanged_files(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        argv = [
            "--vault",
            str(TEST_VAULT),
            "--only",
            "cache",
            "--cache-dir",
            str(tmp_path),
            "--json",
            "--quiet",
        ]
        fetcher = fake_fetcher(tree=["src/content/docs/guides/buttons.md"])
        main(argv, fetcher=fetcher)
        capsys.readouterr()
        main(argv, fetcher=fetcher)
        summary = json.loads(capsys.readouterr().out)
        assert summary["cache"]["written"] == 0
        assert summary["cache"]["unchanged"] == 3

    def test_filter_matching_nothing_exits_3(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ):
        code = main(
            [
                "--vault",
                str(TEST_VAULT),
                "--only",
                "cache",
                "--cache-dir",
                str(tmp_path),
                "--filter",
                "nothing-matches-this",
                "--quiet",
            ],
            fetcher=fake_fetcher(tree=["src/content/docs/guides/buttons.md"]),
        )
        capsys.readouterr()
        assert code == 3

    def test_a_bad_vault_exits_1(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        code = main(["--vault", str(tmp_path), "--only", "spec", "--quiet"], fetcher=fake_fetcher())
        assert code == 1
        assert json.loads(capsys.readouterr().err)["code"] == "NOT_IN_VAULT"

    def test_a_fetch_failure_exits_2(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]):
        def broken(url: str) -> bytes:
            raise RefreshError(f"fetch failed for {url}")

        code = main(
            [
                "--vault",
                str(TEST_VAULT),
                "--only",
                "spec",
                "--spec-path",
                str(tmp_path / "spec.json"),
                "--quiet",
            ],
            fetcher=broken,
        )
        assert code == 2
        assert json.loads(capsys.readouterr().err)["code"] == "REFRESH_FAILED"
