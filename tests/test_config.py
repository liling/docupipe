from __future__ import annotations

import pytest

from docupipe.config import (
    resolve_env_vars, resolve_context_vars,
    execute_variables_script, deep_merge, parse_component_config,
)


class TestEnvInterpolation:
    def test_resolve_simple(self, monkeypatch):
        monkeypatch.setenv("MY_KEY", "secret123")
        assert resolve_env_vars("${MY_KEY}") == "secret123"

    def test_resolve_with_default(self, monkeypatch):
        monkeypatch.delenv("MISSING_KEY", raising=False)
        assert resolve_env_vars("${MISSING_KEY:-fallback}") == "fallback"

    def test_resolve_existing_overrides_default(self, monkeypatch):
        monkeypatch.setenv("MY_KEY", "actual")
        assert resolve_env_vars("${MY_KEY:-fallback}") == "actual"

    def test_resolve_missing_no_default_keeps_original(self):
        assert resolve_env_vars("${NONEXISTENT_VAR_XYZ}") == "${NONEXISTENT_VAR_XYZ}"

    def test_resolve_nested_dict(self, monkeypatch):
        monkeypatch.setenv("URL", "http://localhost")
        config = {"api_url": "${URL}", "nested": {"key": "${URL}/path"}}
        result = resolve_env_vars(config)
        assert result == {"api_url": "http://localhost", "nested": {"key": "http://localhost/path"}}

    def test_resolve_in_list(self, monkeypatch):
        monkeypatch.setenv("KEY", "val")
        assert resolve_env_vars(["${KEY}", "plain"]) == ["val", "plain"]

    def test_resolve_non_string_unchanged(self):
        assert resolve_env_vars(42) == 42
        assert resolve_env_vars(True) is True
        assert resolve_env_vars(None) is None

    def test_resolve_python_vars_override_env(self, monkeypatch):
        monkeypatch.setenv("MY_KEY", "from_env")
        result = resolve_env_vars("${MY_KEY}", variables={"MY_KEY": "from_python"})
        assert result == "from_python"

    def test_resolve_python_vars_without_env(self):
        result = resolve_env_vars("${MY_VAR}", variables={"MY_VAR": "python_value"})
        assert result == "python_value"

    def test_resolve_python_vars_with_default(self):
        result = resolve_env_vars("${MISSING:-fallback}", variables={"MISSING": "from_python"})
        assert result == "from_python"

    def test_resolve_python_vars_fallback_to_env(self, monkeypatch):
        monkeypatch.setenv("ENV_ONLY", "env_val")
        result = resolve_env_vars("${ENV_ONLY}", variables={"OTHER": "val"})
        assert result == "env_val"

    def test_resolve_python_vars_in_dict(self):
        config = {"key": "${my_var}", "nested": {"k2": "${my_var}/path"}}
        result = resolve_env_vars(config, variables={"my_var": "hello"})
        assert result == {"key": "hello", "nested": {"k2": "hello/path"}}

    def test_resolve_no_variables_same_behavior(self, monkeypatch):
        monkeypatch.setenv("KEY", "val")
        assert resolve_env_vars("${KEY}") == "val"
        assert resolve_env_vars("${MISSING}") == "${MISSING}"


class TestContextInterpolation:
    def test_simple_field(self):
        result = resolve_context_vars("hello ${context.name}", {"name": "world"})
        assert result == "hello world"

    def test_field_with_slash(self):
        result = resolve_context_vars("/path/${context.space_name}/file", {"space_name": "我的空间"})
        assert result == "/path/我的空间/file"

    def test_multiple_fields(self):
        result = resolve_context_vars("${context.a}/${context.b}", {"a": "x", "b": "y"})
        assert result == "x/y"

    def test_missing_field_keeps_original(self):
        result = resolve_context_vars("${context.missing}", {})
        assert result == "${context.missing}"

    def test_missing_field_with_default(self):
        result = resolve_context_vars("${context.missing:-fallback}", {})
        assert result == "fallback"

    def test_existing_field_overrides_default(self):
        result = resolve_context_vars("${context.name:-default}", {"name": "actual"})
        assert result == "actual"

    def test_none_value_keeps_original(self):
        result = resolve_context_vars("${context.val}", {"val": None})
        assert result == "${context.val}"

    def test_value_converted_to_string(self):
        result = resolve_context_vars("${context.num}", {"num": 42})
        assert result == "42"

    def test_dict_recursive(self):
        config = {"key": "${context.name}", "nested": {"k2": "${context.name}/path"}}
        result = resolve_context_vars(config, {"name": "hello"})
        assert result == {"key": "hello", "nested": {"k2": "hello/path"}}

    def test_list_recursive(self):
        result = resolve_context_vars(["${context.a}", "plain"], {"a": "val"})
        assert result == ["val", "plain"]

    def test_non_string_unchanged(self):
        assert resolve_context_vars(42, {}) == 42
        assert resolve_context_vars(True, {}) is True
        assert resolve_context_vars(None, {}) is None

    def test_no_context_template_unchanged(self):
        assert resolve_context_vars("plain text", {}) == "plain text"
        assert resolve_context_vars("${ENV_VAR}", {}) == "${ENV_VAR}"

    def test_env_var_not_touched(self):
        result = resolve_context_vars("${MY_VAR} ${context.name}", {"name": "x"})
        assert result == "${MY_VAR} x"


class TestExecuteVariablesScript:
    def test_inline_script_returns_dict(self):
        raw = {"variables": {"script": "return {'today': '2026-01-01'}"}}
        result = execute_variables_script(raw)
        assert result == {"today": "2026-01-01"}

    def test_inline_script_with_import(self):
        raw = {"variables": {"script": "import datetime\nreturn {'day': datetime.date(2026, 1, 1).isoformat()}"}}
        result = execute_variables_script(raw)
        assert result == {"day": "2026-01-01"}

    def test_script_file_reads_external_file(self, tmp_path):
        script = tmp_path / "vars.py"
        script.write_text("return {'key': 'from_file'}\n", encoding="utf-8")
        raw = {"variables": {"script_file": str(script)}}
        result = execute_variables_script(raw)
        assert result == {"key": "from_file"}

    def test_script_file_not_found_raises(self):
        raw = {"variables": {"script_file": "/nonexistent/vars.py"}}
        with pytest.raises(FileNotFoundError, match="script_file"):
            execute_variables_script(raw)

    def test_returns_non_dict_raises(self):
        raw = {"variables": {"script": "return 'not a dict'"}}
        with pytest.raises(TypeError, match="dict"):
            execute_variables_script(raw)

    def test_non_string_key_raises(self):
        raw = {"variables": {"script": "return {1: 'value'}"}}
        with pytest.raises(TypeError, match="key.*字符串"):
            execute_variables_script(raw)

    def test_value_converted_to_string(self):
        raw = {"variables": {"script": "return {'num': 42, 'flag': True}"}}
        result = execute_variables_script(raw)
        assert result == {"num": "42", "flag": "True"}

    def test_empty_dict_returns_empty(self):
        raw = {"variables": {"script": "return {}"}}
        result = execute_variables_script(raw)
        assert result == {}

    def test_no_variables_block_returns_empty(self):
        assert execute_variables_script({}) == {}
        assert execute_variables_script({"pipelines": []}) == {}

    def test_no_script_or_file_returns_empty(self):
        raw = {"variables": {}}
        assert execute_variables_script(raw) == {}

    def test_both_script_and_file_prefers_file(self, tmp_path):
        script = tmp_path / "vars.py"
        script.write_text("return {'source': 'file'}\n", encoding="utf-8")
        raw = {"variables": {"script": "return {'source': 'inline'}", "script_file": str(script)}}
        result = execute_variables_script(raw)
        assert result == {"source": "file"}

    def test_script_exception_propagates(self):
        raw = {"variables": {"script": "raise ValueError('boom')"}}
        with pytest.raises(ValueError, match="boom"):
            execute_variables_script(raw)


class TestDeepMerge:
    def test_simple_override(self):
        assert deep_merge({"a": 1, "b": 2}, {"b": 3}) == {"a": 1, "b": 3}

    def test_nested_merge(self):
        base = {"api_url": "http://default", "bank_id": "default_bank", "nested": {"a": 1, "b": 2}}
        override = {"bank_id": "my_bank", "nested": {"b": 3, "c": 4}}
        result = deep_merge(base, override)
        assert result == {"api_url": "http://default", "bank_id": "my_bank", "nested": {"a": 1, "b": 3, "c": 4}}

    def test_empty_override(self):
        assert deep_merge({"a": 1}, {}) == {"a": 1}


class TestParseComponentConfig:
    def test_simple_parse(self):
        type_name, config = parse_component_config(
            {"source": {"localdrive": {"input_dir": "./docs"}}},
            {},
            "source",
        )
        assert type_name == "localdrive"
        assert config == {"input_dir": "./docs"}

    def test_merge_with_global(self):
        type_name, config = parse_component_config(
            {"destination": {"hindsight": {"bank_id": "my_bank"}}},
            {"hindsight": {"api_url": "http://default", "api_key": "secret"}},
            "destination",
        )
        assert type_name == "hindsight"
        assert config == {"api_url": "http://default", "api_key": "secret", "bank_id": "my_bank"}

    def test_missing_component_raises(self):
        with pytest.raises(ValueError, match="缺少"):
            parse_component_config({}, {}, "source")


class TestUpdateConfig:
    def test_destination_update_config(self):
        from docupipe.destinations.localdrive import LocalDriveDestination
        dest = LocalDriveDestination(output_dir="/old", path_template="old/path")
        dest.update_config({"path_template": "new/path"})
        assert dest._path_template == "new/path"

    def test_update_config_skips_unknown_keys(self):
        from docupipe.destinations.localdrive import LocalDriveDestination
        dest = LocalDriveDestination(output_dir="/old", path_template="old/path")
        dest.update_config({"path_template": "new/path", "unknown_key": "value"})
        assert dest._path_template == "new/path"
        assert not hasattr(dest, "_unknown_key")

    def test_update_config_no_attr_noop(self):
        from docupipe.destinations.localdrive import LocalDriveDestination
        dest = LocalDriveDestination(output_dir="/old")
        dest.update_config({"nonexistent": "value"})
        assert str(dest._output_dir) == "/old"

    def test_hindsight_config_keys(self):
        from docupipe.destinations.hindsight import HindsightDestination
        dest = HindsightDestination()
        assert "document_id_template" in dest._config_keys
        assert "context_template" in dest._config_keys
        assert "extra_tags" in dest._config_keys
        assert "extra_metadata" in dest._config_keys
        assert "context_prefix" in dest._config_keys
