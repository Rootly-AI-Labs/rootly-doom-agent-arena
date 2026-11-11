"""Runtime regressions found while enabling repository quality checks."""

import json

import doom_arena_mcp as mcp
import pytest
import smoke_docker_setup as docker_smoke


def test_wall_lookup_uses_shared_map_bounds(tmp_path, monkeypatch):
    map_path = tmp_path / "map.txt"
    map_path.write_text("#.\n.#\n", encoding="utf-8")
    monkeypatch.setattr(mcp, "MAP_ASCII_PATH", map_path)
    monkeypatch.setattr(mcp, "MAP_BOUNDS", {"x_min": 0, "y_max": 128})

    assert mcp.point_hits_static_wall(32, 96)
    assert not mcp.point_hits_static_wall(96, 96)
    assert mcp.point_hits_static_wall(96, 32)
    assert not mcp.point_hits_static_wall(-32, 96)


@pytest.mark.parametrize("expose_debug", [False, True])
def test_participant_observation_debug_controls_are_explicit(monkeypatch, expose_debug):
    monkeypatch.setattr(mcp, "EXPOSE_LOW_LEVEL_PARTICIPANT_MCP", expose_debug)
    observation = mcp.make_participant_observation([], "player_1")

    assert observation["participant_id"] == "player_1"
    assert ("debug_allowed_controls" in observation) is expose_debug


def test_docker_smoke_prepares_mounts_without_overwriting_tokens(tmp_path, monkeypatch):
    monkeypatch.setattr(docker_smoke, "REPO_ROOT", tmp_path)
    (tmp_path / "src").mkdir()
    docker_smoke.ensure_runtime_paths()
    tokens_path = tmp_path / "src" / "arena_controller_tokens.local.json"
    assert json.loads(tokens_path.read_text()) == {}
    assert (tmp_path / "benchmarks" / "results").is_dir()

    tokens_path.write_text('{"run_id": "active-run"}', encoding="utf-8")
    docker_smoke.ensure_runtime_paths()
    assert json.loads(tokens_path.read_text()) == {"run_id": "active-run"}


def test_docker_smoke_rejects_directory_mount(tmp_path, monkeypatch):
    monkeypatch.setattr(docker_smoke, "REPO_ROOT", tmp_path)
    (tmp_path / "src" / "arena_controller_tokens.local.json").mkdir(parents=True)
    with pytest.raises(RuntimeError, match="must be a file"):
        docker_smoke.ensure_runtime_paths()
