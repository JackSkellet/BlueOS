# This file is used to define general configurations for the app

SERVICE_NAME = "kraken"

DEFAULT_MANIFESTS = [
    {
        "identifier": "bluerobotics-production",
        "name": "BlueOS Extensions Repository",
        "url": "https://bluerobotics.github.io/BlueOS-Extensions-Repository/manifest.json",
    },
    {
        "identifier": "jackskellet-extensions",
        "name": "Jack's BlueOS Extensions Repository",
        "url": "https://jackskellet.github.io/Jacks_BlueOS_Extension_Repo/manifest.json",
    },
]

DEFAULT_EXTENSIONS = [
    {
        "identifier": "blueos.major_tom",
        "url": "https://blueos.cloud/major_tom/install",
    },
]

DEFAULT_INJECTED_ENV_VARIABLES = [
    "MAV_SYSTEM_ID",
]

__all__ = ["SERVICE_NAME", "DEFAULT_MANIFESTS", "DEFAULT_EXTENSIONS", "DEFAULT_INJECTED_ENV_VARIABLES"]
