import json
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4


def load_parameter_profiles(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    profiles = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(profiles, list):
        raise ValueError("Parameter profiles file must contain a list")
    return profiles


def _write_parameter_profiles(path: Path, profiles: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{json.dumps(profiles, indent=4)}\n", encoding="utf-8")


def create_parameter_profile(path: Path, name: str, parameters: Dict[str, float]) -> Dict[str, Any]:
    profile = {
        "id": str(uuid4()),
        "name": name.strip(),
        "parameters": parameters,
    }
    if not profile["name"]:
        raise ValueError("Profile name cannot be empty")

    profiles = load_parameter_profiles(path)
    profiles.append(profile)
    _write_parameter_profiles(path, profiles)
    return profile


def rename_parameter_profile(path: Path, profile_id: str, name: str) -> Dict[str, Any]:
    new_name = name.strip()
    if not new_name:
        raise ValueError("Profile name cannot be empty")

    profiles = load_parameter_profiles(path)
    for profile in profiles:
        if profile.get("id") == profile_id:
            profile["name"] = new_name
            _write_parameter_profiles(path, profiles)
            return profile
    raise KeyError(profile_id)


def delete_parameter_profile(path: Path, profile_id: str) -> None:
    profiles = load_parameter_profiles(path)
    remaining_profiles = [profile for profile in profiles if profile.get("id") != profile_id]
    if len(remaining_profiles) == len(profiles):
        raise KeyError(profile_id)
    _write_parameter_profiles(path, remaining_profiles)
