import os
import subprocess
import sys
from pathlib import Path

import pytest
from config import DEFAULT_MANIFESTS
from manifest.exceptions import ManifestOperationNotAllowed
from manifest.manifest import ManifestManager


@pytest.mark.parametrize("version", ["v1", "v2"])
def test_api_root_redirects_to_relative_docs(version: str, tmp_path: Path) -> None:
    service_path = Path(__file__).parent
    environment = {key: value for key, value in os.environ.items() if not key.startswith("COV_CORE_")} | {
        "PYTHONPATH": str(service_path / "api" / version / "routers"),
        "XDG_CONFIG_HOME": str(tmp_path),
    }
    script = 'import asyncio; from index import root; print(asyncio.run(root()).headers["location"])'

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=service_path,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.stdout == "docs\n"


def test_jackskellet_manifest_is_protected() -> None:
    source = next(source for source in DEFAULT_MANIFESTS if source["identifier"] == "jackskellet-extensions")
    assert source["url"] == "https://jackskellet.github.io/Jacks_BlueOS_Extension_Repo/manifest.json"

    manager = object.__new__(ManifestManager)
    with pytest.raises(ManifestOperationNotAllowed):
        manager._raise_in_default_source(source["identifier"])
