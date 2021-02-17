import os
import re
import sys

import redbot

new_stable_version = os.environ["NEW_STABLE_VERSION"]

version_info = redbot.VersionInfo.from_str(new_stable_version)

if int(os.environ.get("DEV_BUMP", 0)):
    version_info.micro += 1
    version_info.dev_release = 1

with open("redbot/__init__.py", encoding="utf-8") as fp:
    new_contents, found = re.subn(
        pattern=r'^__version__ = "[^"]*"$',
        repl=f'__version__ = "{version_info}"',
        string=fp.read(),
        count=1,
        flags=re.MULTILINE,
    )

if not found:
    print("Couldn't find `__version__` line!")
    sys.exit(1)

with open("redbot/__init__.py", "w", encoding="utf-8") as fp:
    fp.write(new_contents)

print(f"::set-output name=new_version::{version_info}")
