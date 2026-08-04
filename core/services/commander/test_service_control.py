import json
from pathlib import Path

import pytest
from service_control import get_core_service_states, set_core_service_enabled


def write_startup_config(path: Path, environment: list[str] | dict[str, str]) -> None:
    path.write_text(json.dumps({"core": {"environment": environment}}), encoding="utf-8")


def test_service_states_follow_disabled_services_list(tmp_path: Path) -> None:
    startup_path = tmp_path / "startup.json"
    write_startup_config(startup_path, ["EXISTING=value", "BLUEOS_DISABLE_SERVICES=wifi,ping"])

    assert get_core_service_states(startup_path) == {"ping": False, "recorder": True}

    assert set_core_service_enabled(startup_path, "recorder", False) == {"ping": False, "recorder": False}
    config = json.loads(startup_path.read_text(encoding="utf-8"))
    assert config["core"]["environment"] == [
        "EXISTING=value",
        "BLUEOS_DISABLE_SERVICES=ping,recorder,wifi",
    ]

    assert set_core_service_enabled(startup_path, "ping", True) == {"ping": True, "recorder": False}
    config = json.loads(startup_path.read_text(encoding="utf-8"))
    assert config["core"]["environment"] == [
        "EXISTING=value",
        "BLUEOS_DISABLE_SERVICES=recorder,wifi",
    ]


def test_service_states_support_environment_object(tmp_path: Path) -> None:
    startup_path = tmp_path / "startup.json"
    write_startup_config(startup_path, {"EXISTING": "value", "BLUEOS_DISABLE_SERVICES": "recorder"})

    assert get_core_service_states(startup_path) == {"ping": True, "recorder": False}

    set_core_service_enabled(startup_path, "recorder", True)
    config = json.loads(startup_path.read_text(encoding="utf-8"))
    assert config["core"]["environment"] == {"EXISTING": "value"}


def test_rejects_unmanaged_service(tmp_path: Path) -> None:
    startup_path = tmp_path / "startup.json"
    write_startup_config(startup_path, [])

    with pytest.raises(ValueError, match="Unsupported managed service"):
        set_core_service_enabled(startup_path, "autopilot", False)
