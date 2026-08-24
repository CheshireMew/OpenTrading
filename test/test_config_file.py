from __future__ import annotations

import pytest

import app.services.config_file as config_file


def test_json_config_write_is_atomic_when_replace_fails(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    config_file.write_json_object(path, {"revision": 1})
    original = path.read_bytes()

    def fail_replace(_source, _target):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(config_file.os, "replace", fail_replace)

    with pytest.raises(OSError, match="simulated replace failure"):
        config_file.write_json_object(path, {"revision": 2})

    assert path.read_bytes() == original
    assert config_file.read_json_object(path) == {"revision": 1}
    assert list(tmp_path.glob(".config.json.*.tmp")) == []
