import os
import sys
from setuptools import setup

# Since we're importing `redbot` package, we have to ensure that it's in sys.path.
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from redbot import VersionInfo

version, _ = VersionInfo._get_version(ignore_installed=True)
python_requires = ">=3.8.1,<3.10"

if os.getenv("TOX_RED", False) and sys.version_info >= (3, 10):
    # We want to be able to test Python versions that we do not support yet.
    python_requires = python_requires.rsplit(",", maxsplit=1)[0]

# Metadata and options defined in pyproject.toml
setup(python_requires=python_requires, version=version)
