from __future__ import annotations

import pytest

from docupipe.sources.base import SourceBase
from tests.conftest import FakeSource


class TestRegistration:
    def test_sources_registered(self):
        from docupipe.sources import SOURCES
        assert "dingtalk" in SOURCES
        assert "localdrive" in SOURCES

    def test_destinations_registered(self):
        from docupipe.destinations import DESTINATIONS
        assert "hindsight" in DESTINATIONS

    def test_localdrive_registered(self):
        from docupipe.destinations import DESTINATIONS
        assert "localdrive" in DESTINATIONS

    def test_get_source_unknown_raises(self):
        from docupipe.sources import get_source
        with pytest.raises(ValueError, match="未知的 source"):
            get_source("nonexistent")

    def test_get_destination_unknown_raises(self):
        from docupipe.destinations import get_destination
        with pytest.raises(ValueError, match="未知的 destination"):
            get_destination("nonexistent")

    def test_mineru_converter_registered(self):
        from docupipe.converters import CONVERTERS
        assert "mineru" in CONVERTERS


class TestSourceBaseInterface:
    def test_supported_change_detection_default_empty(self):
        assert SourceBase.supported_change_detection is not None

    def test_delete_default_raises(self, tmp_path):
        source = FakeSource([])
        with pytest.raises(NotImplementedError):
            source.delete("some_id")


class TestCLIConfig:
    def test_parse_mode_from_config(self, tmp_path):
        import yaml
        config = {
            "pipelines": [{
                "name": "test",
                "mode": "incremental",
                "source": {"fake": {}},
                "destination": {"fake": {}},
            }]
        }
        path = tmp_path / "test.yaml"
        path.write_text(yaml.dump(config), encoding="utf-8")
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert raw["pipelines"][0]["mode"] == "incremental"

    def test_parse_post_steps_from_config(self, tmp_path):
        import yaml
        config = {
            "pipelines": [{
                "name": "test",
                "post_steps": ["some_post_step"],
                "source": {"fake": {}},
                "destination": {"fake": {}},
            }]
        }
        path = tmp_path / "test.yaml"
        path.write_text(yaml.dump(config), encoding="utf-8")
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert raw["pipelines"][0]["post_steps"] == ["some_post_step"]

    def test_parse_state_file_from_config(self, tmp_path):
        import yaml
        config = {
            "pipelines": [{
                "name": "test",
                "state_file": "custom_state.json",
                "source": {"fake": {}},
                "destination": {"fake": {}},
            }]
        }
        path = tmp_path / "test.yaml"
        path.write_text(yaml.dump(config), encoding="utf-8")
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert raw["pipelines"][0]["state_file"] == "custom_state.json"
