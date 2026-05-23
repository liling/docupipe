from __future__ import annotations

from pathlib import Path

import pytest

from docupipe.plugins import (
    CONVENTION_DIRS,
    _PLUGIN_REGISTRY,
    _load_from_directory,
    _load_from_entry_points,
    _loaded_paths,
    load_config_plugins,
)


class TestRegisterConflictDetection:
    def test_source_conflict_raises(self):
        from docupipe.sources import SOURCES, register_source

        assert "dingtalk" in SOURCES
        with pytest.raises(ValueError, match="source 'dingtalk' 已注册"):
            register_source("dingtalk")(type("X", (), {}))

    def test_destination_conflict_raises(self):
        from docupipe.destinations import DESTINATIONS, register_destination

        assert "hindsight" in DESTINATIONS
        with pytest.raises(ValueError, match="destination 'hindsight' 已注册"):
            register_destination("hindsight")(type("X", (), {}))

    def test_step_conflict_raises(self):
        from docupipe.steps import STEPS, register_step

        assert "convert" in STEPS
        with pytest.raises(ValueError, match="step 'convert' 已注册"):
            register_step("convert")(type("X", (), {}))

    def test_converter_conflict_raises(self):
        from docupipe.converters import CONVERTERS, register_converter

        assert "markitdown" in CONVERTERS
        with pytest.raises(ValueError, match="converter 'markitdown' 已注册"):
            register_converter("markitdown")(type("X", (), {}))

    def test_source_attribution_in_error(self):
        from docupipe.sources import SOURCES, register_source

        existing = SOURCES["dingtalk"]
        existing._plugin_source = "built-in"
        try:
            register_source("dingtalk")(type("X", (), {}))
        except ValueError as e:
            assert "built-in" in str(e)

    def test_plugin_source_tagged_on_builtins(self):
        from docupipe.sources import SOURCES

        for cls in SOURCES.values():
            assert hasattr(cls, "_plugin_source")
            assert cls._plugin_source == "built-in"


class TestLoadFromDirectory:
    def test_load_py_file(self, tmp_path: Path):
        plugin_file = tmp_path / "my_source.py"
        plugin_file.write_text(
            "from docupipe.sources import register_source\n"
            "from docupipe.sources.base import SourceBase\n"
            "@register_source('my_source_test')\n"
            "class MySource(SourceBase):\n"
            "    name = 'my_source_test'\n"
            "    def list(self): return []\n"
            "    def fetch(self, meta): raise NotImplementedError\n"
        )
        loaded = _load_from_directory(tmp_path)
        assert len(loaded) == 1
        assert loaded[0][1] >= 1

        from docupipe.sources import SOURCES

        assert "my_source_test" in SOURCES
        assert SOURCES["my_source_test"]._plugin_source == f"file:{plugin_file}"

    def test_skip_private_files(self, tmp_path: Path):
        private_file = tmp_path / "_helper.py"
        private_file.write_text("# helper")
        loaded = _load_from_directory(tmp_path)
        assert len(loaded) == 0

    def test_skip_init_py(self, tmp_path: Path):
        init_file = tmp_path / "__init__.py"
        init_file.write_text("# package")
        loaded = _load_from_directory(tmp_path)
        assert len(loaded) == 0

    def test_skip_non_py(self, tmp_path: Path):
        txt_file = tmp_path / "data.txt"
        txt_file.write_text("data")
        loaded = _load_from_directory(tmp_path)
        assert len(loaded) == 0

    def test_skip_pycache(self, tmp_path: Path):
        pycache = tmp_path / "__pycache__"
        pycache.mkdir()
        loaded = _load_from_directory(tmp_path)
        assert len(loaded) == 0

    def test_dedup_same_directory(self, tmp_path: Path):
        plugin_file = tmp_path / "dedup_test.py"
        plugin_file.write_text(
            "from docupipe.steps import register_step\n"
            "from docupipe.steps.base import Step\n"
            "@register_step('dedup_step')\n"
            "class DedupStep(Step):\n"
            "    def process(self, bundle): return bundle\n"
        )
        first = _load_from_directory(tmp_path)
        assert len(first) == 1
        second = _load_from_directory(tmp_path)
        assert len(second) == 0

    def test_bad_file_skipped(self, tmp_path: Path):
        bad = tmp_path / "bad.py"
        bad.write_text("this is not python syntax {{{")
        loaded = _load_from_directory(tmp_path)
        assert len(loaded) == 0

    def test_directory_missing(self):
        loaded = _load_from_directory(Path("/nonexistent/path"))
        assert len(loaded) == 0

    def test_loaded_paths_maintained(self, tmp_path: Path):
        _loaded_paths.clear()
        plugin_file = tmp_path / "track.py"
        plugin_file.write_text(
            "from docupipe.sources import register_source\n"
            "from docupipe.sources.base import SourceBase\n"
            "@register_source('track_test')\n"
            "class TrackSource(SourceBase):\n"
            "    def list(self): return []\n"
            "    def fetch(self, meta): raise NotImplementedError\n"
        )
        _load_from_directory(tmp_path)
        assert tmp_path in _loaded_paths

    def test_load_package(self, tmp_path: Path):
        pkg_dir = tmp_path / "mypkg"
        pkg_dir.mkdir()
        (pkg_dir / "__init__.py").write_text(
            "from docupipe.destinations import register_destination\n"
            "from docupipe.destinations.base import DestinationBase\n"
            "@register_destination('pkg_dest')\n"
            "class PkgDest(DestinationBase):\n"
            "    def write(self, bundle): return ''\n"
            "    def remove(self, doc_id): pass\n"
        )
        loaded = _load_from_directory(tmp_path)
        assert len(loaded) == 1


class TestLoadConfigPlugins:
    def test_type_error_on_string(self):
        with pytest.raises(TypeError, match="必须是列表"):
            load_config_plugins("./plugins")

    def test_type_error_on_none(self):
        with pytest.raises(TypeError, match="必须是列表"):
            load_config_plugins(None)

    def test_empty_list_ok(self):
        load_config_plugins([])

    def test_missing_dir_skipped(self, tmp_path: Path):
        load_config_plugins([str(tmp_path / "_nonexistent")])


class TestLoadFromEntryPoints:
    def test_empty_when_no_eps(self, mocker):
        mocker.patch(
            "importlib.metadata.entry_points",
            return_value=[],
        )
        result = _load_from_entry_points()
        assert result == []

    def test_bad_entry_point_skipped(self, mocker):
        def failing_load():
            raise RuntimeError("broken")

        mock_ep = mocker.MagicMock()
        mock_ep.name = "broken_plugin"
        mock_ep.load.return_value = failing_load
        mocker.patch(
            "importlib.metadata.entry_points",
            return_value=[mock_ep],
        )
        result = _load_from_entry_points()
        assert len(result) == 0

    def test_entry_point_counts(self, mocker):
        from docupipe.sources import register_source
        from docupipe.sources.base import SourceBase

        def working_load():
            @register_source("ep_source")
            class EPSource(SourceBase):
                def list(self): return []
                def fetch(self, meta): raise NotImplementedError
            return

        mock_ep = mocker.MagicMock()
        mock_ep.name = "working_plugin"
        mock_ep.load.return_value = working_load
        mock_ep.dist = None
        mocker.patch(
            "importlib.metadata.entry_points",
            return_value=[mock_ep],
        )
        result = _load_from_entry_points()
        assert len(result) == 1
        assert result[0][0] == "working_plugin"
        assert result[0][1] >= 1


class TestPluginRegistry:
    def test_plugin_registry_populated(self, tmp_path: Path):
        _PLUGIN_REGISTRY.clear()
        plugin_file = tmp_path / "reg_source.py"
        plugin_file.write_text(
            "from docupipe.sources import register_source\n"
            "from docupipe.sources.base import SourceBase\n"
            "@register_source('reg_test')\n"
            "class RegSource(SourceBase):\n"
            "    def list(self): return []\n"
            "    def fetch(self, meta): raise NotImplementedError\n"
        )
        _load_from_directory(tmp_path)
        assert str(plugin_file) in _PLUGIN_REGISTRY
        components = _PLUGIN_REGISTRY[str(plugin_file)]
        assert ("source", "reg_test") in components


class TestIntegration:
    def test_convention_dirs_loaded_on_import(self):
        from docupipe import plugins

        assert hasattr(plugins, "load_plugins")

    def test_load_config_triggers_convention_dirs(self):
        _loaded_paths.clear()
        _PLUGIN_REGISTRY.clear()
        load_config_plugins([])

    def test_runner_imports_load_config_plugins(self):
        from docupipe import runner
        assert hasattr(runner, "load_config_plugins")
