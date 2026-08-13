import json
import struct
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

DISABLED_SERVICES_ENVIRONMENT_VARIABLE = "BLUEOS_DISABLE_SERVICES"
MANAGED_CORE_SERVICES = ("ping", "recorder", "video")
MANAGED_RADIOS = {"wifi": 1, "bluetooth": 2}
RFKILL_CHANGE_ALL_OPERATION = 3
RFKILL_DEVICE_PATH = Path("/dev/rfkill")
RFKILL_SYSFS_PATH = Path("/sys/class/rfkill")
TOPSIDE_ROUTE_METRIC = 50


def _parse_disabled_services(value: str) -> Set[str]:
    return {service.strip() for service in value.replace(" ", ",").split(",") if service.strip()}


def _disabled_services(config: Dict[str, Any]) -> Set[str]:
    environment = config["core"].get("environment", [])
    if isinstance(environment, dict):
        return _parse_disabled_services(str(environment.get(DISABLED_SERVICES_ENVIRONMENT_VARIABLE, "")))
    if not isinstance(environment, list):
        raise ValueError("core.environment must be a list or object")

    disabled_services: Set[str] = set()
    prefix = f"{DISABLED_SERVICES_ENVIRONMENT_VARIABLE}="
    for entry in environment:
        if not isinstance(entry, str):
            raise ValueError("core.environment list entries must be strings")
        if entry.startswith(prefix):
            disabled_services.update(_parse_disabled_services(entry.removeprefix(prefix)))
    return disabled_services


def _load_startup_config(path: Path) -> Dict[str, Any]:
    with path.open(encoding="utf-8") as startup_file:
        config = json.load(startup_file)
    if not isinstance(config, dict) or not isinstance(config.get("core"), dict):
        raise ValueError("startup.json must contain a core object")
    return config


def get_core_service_states(path: Path) -> Dict[str, bool]:
    disabled_services = _disabled_services(_load_startup_config(path))
    return {service: service not in disabled_services for service in MANAGED_CORE_SERVICES}


def set_core_service_states(path: Path, states: Dict[str, bool]) -> Dict[str, bool]:
    unsupported_services = set(states) - set(MANAGED_CORE_SERVICES)
    if unsupported_services:
        raise ValueError(f"Unsupported managed service: {sorted(unsupported_services)[0]}")

    config = _load_startup_config(path)
    disabled_services = _disabled_services(config)
    for service, enabled in states.items():
        if enabled:
            disabled_services.discard(service)
        else:
            disabled_services.add(service)

    environment = config["core"].setdefault("environment", [])
    value = ",".join(sorted(disabled_services))
    if isinstance(environment, dict):
        if value:
            environment[DISABLED_SERVICES_ENVIRONMENT_VARIABLE] = value
        else:
            environment.pop(DISABLED_SERVICES_ENVIRONMENT_VARIABLE, None)
    else:
        prefix = f"{DISABLED_SERVICES_ENVIRONMENT_VARIABLE}="
        config["core"]["environment"] = [entry for entry in environment if not entry.startswith(prefix)]
        if value:
            config["core"]["environment"].append(f"{prefix}{value}")

    with path.open("w", encoding="utf-8") as startup_file:
        json.dump(config, startup_file, indent=4)
        startup_file.write("\n")

    return {managed_service: managed_service not in disabled_services for managed_service in MANAGED_CORE_SERVICES}


def get_radio_states(sysfs_path: Path = RFKILL_SYSFS_PATH) -> Dict[str, bool]:
    radio_states: Dict[str, List[bool]] = {radio: [] for radio in MANAGED_RADIOS}
    type_names = {"wlan": "wifi", "bluetooth": "bluetooth"}
    for type_path in sysfs_path.glob("rfkill*/type"):
        radio = type_names.get(type_path.read_text(encoding="utf-8").strip())
        if radio is None:
            continue
        soft_blocked = type_path.with_name("soft").read_text(encoding="utf-8").strip() == "1"
        radio_states[radio].append(not soft_blocked)

    missing_radios = [radio for radio, states in radio_states.items() if not states]
    if missing_radios:
        raise RuntimeError(f"Radio not found: {missing_radios[0]}")
    return {radio: all(states) for radio, states in radio_states.items()}


def set_radio_states(
    states: Dict[str, bool],
    device_path: Path = RFKILL_DEVICE_PATH,
    sysfs_path: Path = RFKILL_SYSFS_PATH,
) -> Dict[str, bool]:
    unsupported_radios = set(states) - set(MANAGED_RADIOS)
    if unsupported_radios:
        raise ValueError(f"Unsupported radio: {sorted(unsupported_radios)[0]}")

    current_states = get_radio_states(sysfs_path)
    events = [
        struct.pack("<IBBBB", 0, MANAGED_RADIOS[radio], RFKILL_CHANGE_ALL_OPERATION, int(not enabled), 0)
        for radio, enabled in states.items()
        if current_states[radio] != enabled
    ]
    if events:
        with device_path.open("wb", buffering=0) as rfkill_device:
            for event in events:
                rfkill_device.write(event)
    return states


def _run_ip_command(arguments: List[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/usr/sbin/ip", *arguments],
        check=False,
        capture_output=True,
        text=True,
    )


def _topside_internet_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"enabled": False}
    config = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or not isinstance(config.get("enabled"), bool):
        raise ValueError("Topside Internet settings must contain an enabled state")
    return config


def get_topside_internet_enabled(path: Path) -> bool:
    return bool(_topside_internet_config(path)["enabled"])


def _write_topside_internet_config(path: Path, config: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{json.dumps(config, indent=4)}\n", encoding="utf-8")


def _interface_for_gateway(gateway: str) -> str:
    result = _run_ip_command(["route", "get", gateway])
    if result.returncode != 0:
        raise RuntimeError(f"Unable to reach topside gateway {gateway}: {result.stderr.strip()}")
    route = result.stdout.split()
    if "dev" not in route or route.index("dev") + 1 >= len(route):
        raise RuntimeError(f"Unable to determine the interface for topside gateway {gateway}")
    return route[route.index("dev") + 1]


def _replace_topside_route(gateway: str, interface: str) -> None:
    result = _run_ip_command(
        ["route", "replace", "default", "via", gateway, "dev", interface, "metric", str(TOPSIDE_ROUTE_METRIC)]
    )
    if result.returncode != 0:
        raise RuntimeError(f"Unable to enable Topside Internet: {result.stderr.strip()}")


def set_topside_internet_enabled(path: Path, enabled: bool, gateway: Optional[str] = None) -> bool:
    config = _topside_internet_config(path)
    if enabled:
        if gateway is None:
            raise ValueError("A topside gateway is required")
        interface = _interface_for_gateway(gateway)
        _replace_topside_route(gateway, interface)
        _write_topside_internet_config(path, {"enabled": True, "gateway": gateway, "interface": interface})
        return True

    stored_gateway = config.get("gateway")
    stored_interface = config.get("interface")
    if isinstance(stored_gateway, str) and isinstance(stored_interface, str):
        result = _run_ip_command(
            [
                "route",
                "flush",
                "default",
                "via",
                stored_gateway,
                "dev",
                stored_interface,
            ]
        )
        if result.returncode != 0:
            raise RuntimeError(f"Unable to disable Topside Internet: {result.stderr.strip()}")
    _write_topside_internet_config(path, {"enabled": False})
    return False


def restore_topside_internet(path: Path) -> None:
    config = _topside_internet_config(path)
    if not config["enabled"]:
        return
    gateway = config.get("gateway")
    interface = config.get("interface")
    if not isinstance(gateway, str) or not isinstance(interface, str):
        raise ValueError("Enabled Topside Internet settings must contain a gateway and interface")
    _replace_topside_route(gateway, interface)
