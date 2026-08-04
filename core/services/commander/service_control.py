import json
from pathlib import Path
from typing import Any, Dict, Set

DISABLED_SERVICES_ENVIRONMENT_VARIABLE = "BLUEOS_DISABLE_SERVICES"
MANAGED_CORE_SERVICES = ("ping", "recorder")


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


def set_core_service_enabled(path: Path, service: str, enabled: bool) -> Dict[str, bool]:
    if service not in MANAGED_CORE_SERVICES:
        raise ValueError(f"Unsupported managed service: {service}")

    config = _load_startup_config(path)
    disabled_services = _disabled_services(config)
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
