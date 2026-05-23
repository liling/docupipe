from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from docupipe.render import render_template


class TestSimpleVariable:
    def test_single_variable(self):
        assert render_template("hello {{ name }}", {"name": "world"}) == "hello world"

    def test_multiple_variables(self):
        assert render_template("{{ a }}/{{ b }}", {"a": "x", "b": "y"}) == "x/y"

    def test_unicode_value(self):
        assert render_template("/path/{{ space_name }}/file", {"space_name": "我的空间"}) == "/path/我的空间/file"


class TestStrictUndefined:
    def test_missing_variable_raises(self):
        with pytest.raises(ValueError, match="模板渲染错误"):
            render_template("{{ missing }}", {})

    def test_default_filter(self):
        assert render_template("{{ author | default('unknown') }}", {}) == "unknown"

    def test_default_filter_not_used_when_present(self):
        assert render_template("{{ author | default('unknown') }}", {"author": "张三"}) == "张三"


class TestFilters:
    def test_date_format_from_timestamp_ms(self):
        ts = datetime(2026, 3, 15, 10, 30, 0, tzinfo=timezone(timedelta(hours=8))).timestamp() * 1000
        result = render_template("{{ ts | date_format('%Y-%m') }}", {"ts": ts})
        assert result == "2026-03"

    def test_date_format_from_datetime(self):
        dt = datetime(2026, 5, 1)
        result = render_template("{{ dt | date_format('%Y/%m/%d') }}", {"dt": dt})
        assert result == "2026/05/01"

    def test_basename(self):
        assert render_template("{{ p | basename }}", {"p": "folder/sub/doc.md"}) == "doc.md"

    def test_extension(self):
        assert render_template("{{ f | extension }}", {"f": "report.pdf"}) == "pdf"

    def test_extension_no_dot(self):
        assert render_template("{{ f | extension }}", {"f": "README"}) == ""

    def test_replace(self):
        assert render_template("{{ title | replace(' ', '-') }}", {"title": "hello world"}) == "hello-world"


class TestRecursiveRendering:
    def test_dict_recursive(self):
        config = {"key": "{{ name }}", "nested": {"k2": "{{ name }}/path"}}
        result = render_template(config, {"name": "hello"})
        assert result == {"key": "hello", "nested": {"k2": "hello/path"}}

    def test_list_recursive(self):
        assert render_template(["{{ a }}", "plain"], {"a": "val"}) == ["val", "plain"]

    def test_non_string_passthrough(self):
        assert render_template(42, {}) == 42
        assert render_template(True, {}) is True
        assert render_template(None, {}) is None


class TestConditional:
    def test_if_true(self):
        tpl = "{% if type == 'doc' %}{{ title }}{% else %}{{ filename }}{% endif %}"
        assert render_template(tpl, {"type": "doc", "title": "My Doc", "filename": "f.md"}) == "My Doc"

    def test_if_false(self):
        tpl = "{% if type == 'doc' %}{{ title }}{% else %}{{ filename }}{% endif %}"
        assert render_template(tpl, {"type": "sheet", "title": "My Doc", "filename": "f.xlsx"}) == "f.xlsx"


class TestNoJinjaSyntax:
    def test_plain_string_unchanged(self):
        assert render_template("plain text", {}) == "plain text"

    def test_env_var_syntax_unchanged(self):
        assert render_template("${MY_VAR}", {}) == "${MY_VAR}"

    def test_mixed_env_and_jinja(self):
        assert render_template("${MY_VAR} {{ name }}", {"name": "x"}) == "${MY_VAR} x"
