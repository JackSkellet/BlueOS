from pathlib import Path

import pytest
from parameter_profiles import (
    create_parameter_profile,
    delete_parameter_profile,
    load_parameter_profiles,
    rename_parameter_profile,
)


def test_parameter_profile_lifecycle(tmp_path: Path) -> None:
    profiles_path = tmp_path / "parameter_profiles.json"

    profile = create_parameter_profile(profiles_path, "Dive setup", {"FRAME_CONFIG": 1, "JS_GAIN_DEFAULT": 0.5})

    assert load_parameter_profiles(profiles_path) == [profile]
    renamed_profile = rename_parameter_profile(profiles_path, profile["id"], "Survey setup")
    assert renamed_profile["name"] == "Survey setup"

    delete_parameter_profile(profiles_path, profile["id"])
    assert load_parameter_profiles(profiles_path) == []


def test_parameter_profiles_reject_empty_names_and_unknown_ids(tmp_path: Path) -> None:
    profiles_path = tmp_path / "parameter_profiles.json"

    with pytest.raises(ValueError, match="cannot be empty"):
        create_parameter_profile(profiles_path, "  ", {})
    with pytest.raises(KeyError):
        rename_parameter_profile(profiles_path, "missing", "New name")
    with pytest.raises(KeyError):
        delete_parameter_profile(profiles_path, "missing")
