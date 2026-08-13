import json
import struct
import subprocess
from pathlib import Path
from typing import List

import pytest
from pytest import MonkeyPatch
from service_control import (
    get_core_service_states,
    get_radio_states,
    get_topside_internet_enabled,
    restore_topside_internet,
    set_core_service_states,
    set_radio_states,
    set_topside_internet_enabled,
)


def write_startup_config(path: Path, environment: list[str] | dict[str, str]) -> None:
    path.write_text(json.dumps({"core": {"environment": environment}}), encoding="utf-8")


def test_service_states_follow_disabled_services_list(tmp_path: Path) -> None:
    startup_path = tmp_path / "startup.json"
    write_startup_config(startup_path, ["EXISTING=value", "BLUEOS_DISABLE_SERVICES=wifi,ping"])

    assert get_core_service_states(startup_path) == {"ping": False, "recorder": True, "video": True}

    assert set_core_service_states(startup_path, {"recorder": False, "ping": True}) == {
        "ping": True,
        "recorder": False,
        "video": True,
    }
    config = json.loads(startup_path.read_text(encoding="utf-8"))
    assert config["core"]["environment"] == [
        "EXISTING=value",
        "BLUEOS_DISABLE_SERVICES=recorder,wifi",
    ]


def test_service_states_support_environment_object(tmp_path: Path) -> None:
    startup_path = tmp_path / "startup.json"
    write_startup_config(startup_path, {"EXISTING": "value", "BLUEOS_DISABLE_SERVICES": "recorder"})

    assert get_core_service_states(startup_path) == {"ping": True, "recorder": False, "video": True}

    set_core_service_states(startup_path, {"recorder": True})
    config = json.loads(startup_path.read_text(encoding="utf-8"))
    assert config["core"]["environment"] == {"EXISTING": "value"}


def test_rejects_unmanaged_service(tmp_path: Path) -> None:
    startup_path = tmp_path / "startup.json"
    write_startup_config(startup_path, [])

    with pytest.raises(ValueError, match="Unsupported managed service"):
        set_core_service_states(startup_path, {"autopilot": False})


def write_radio_state(sysfs_path: Path, index: int, radio_type: str, soft_blocked: bool) -> None:
    radio_path = sysfs_path / f"rfkill{index}"
    radio_path.mkdir()
    (radio_path / "type").write_text(f"{radio_type}\n", encoding="utf-8")
    (radio_path / "soft").write_text(f"{int(soft_blocked)}\n", encoding="utf-8")


def test_radio_states_use_rfkill_events(tmp_path: Path) -> None:
    sysfs_path = tmp_path / "sysfs"
    sysfs_path.mkdir()
    write_radio_state(sysfs_path, 0, "wlan", True)
    write_radio_state(sysfs_path, 1, "bluetooth", False)
    device_path = tmp_path / "rfkill"

    assert get_radio_states(sysfs_path) == {"wifi": False, "bluetooth": True}
    assert set_radio_states(
        {"wifi": True, "bluetooth": False},
        device_path=device_path,
        sysfs_path=sysfs_path,
    ) == {"wifi": True, "bluetooth": False}
    assert device_path.read_bytes() == b"".join(
        (
            struct.pack("<IBBBB", 0, 1, 3, 0, 0),
            struct.pack("<IBBBB", 0, 2, 3, 1, 0),
        )
    )


def test_radio_states_require_both_radios(tmp_path: Path) -> None:
    write_radio_state(tmp_path, 0, "wlan", False)
    with pytest.raises(RuntimeError, match="Radio not found: bluetooth"):
        get_radio_states(tmp_path)


def test_topside_internet_route_is_persisted_and_restored(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    settings_path = tmp_path / "topside_internet.json"
    commands: List[List[str]] = []

    def run_ip_command(arguments: List[str]) -> subprocess.CompletedProcess[str]:
        commands.append(arguments)
        output = "192.168.2.1 dev eth0 src 192.168.2.2\n" if arguments[:2] == ["route", "get"] else ""
        return subprocess.CompletedProcess(arguments, 0, output, "")

    monkeypatch.setattr("service_control._run_ip_command", run_ip_command)
    assert not get_topside_internet_enabled(settings_path)
    assert set_topside_internet_enabled(settings_path, True, "192.168.2.1")
    assert get_topside_internet_enabled(settings_path)

    restore_topside_internet(settings_path)
    assert commands == [
        ["route", "get", "192.168.2.1"],
        ["route", "replace", "default", "via", "192.168.2.1", "dev", "eth0", "metric", "50"],
        ["route", "replace", "default", "via", "192.168.2.1", "dev", "eth0", "metric", "50"],
    ]

    assert not set_topside_internet_enabled(settings_path, False)
    assert not get_topside_internet_enabled(settings_path)
    assert commands[-1] == [
        "route",
        "flush",
        "default",
        "via",
        "192.168.2.1",
        "dev",
        "eth0",
    ]
