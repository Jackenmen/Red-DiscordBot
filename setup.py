import os
import sys
from pathlib import Path
from setuptools import setup

ROOT_FOLDER = Path(__file__).parent.absolute()
REQUIREMENTS_FOLDER = ROOT_FOLDER / "requirements"

# Since we're importing `redbot` package, we have to ensure that it's in sys.path.
sys.path.insert(0, str(ROOT_FOLDER))

from redbot import VersionInfo

version, _ = VersionInfo._get_version(ignore_installed=True)


def extras_combined(*extra_names):
    return list(
        {
            req
            for extra_name, extra_reqs in extras_require.items()
            if not extra_names or extra_name in extra_names
            for req in extra_reqs
        }
    )


with open(REQUIREMENTS_FOLDER / "base.txt", encoding="utf-8") as fp:
    install_requires = fp.read().splitlines()

extras_require = {}
for file in REQUIREMENTS_FOLDER.glob("extra-*.txt"):
    with file.open(encoding="utf-8") as fp:
        extras_require[file.stem[len("extra-") :]] = fp.read().splitlines()

extras_require["dev"] = extras_combined()
extras_require["all"] = extras_combined("postgres")


setup_kwargs = {
    "version": version,
    "install_requires": install_requires,
    "extras_require": extras_require,
}
if os.getenv("TOX_RED", False) and sys.version_info >= (3, 11):
    # We want to be able to test Python versions that we do not support yet.
    setup(python_requires=">=3.8.1", **setup_kwargs)
else:
    # Metadata and options defined in setup.cfg
    setup(**setup_kwargs)
