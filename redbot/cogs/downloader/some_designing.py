import asyncio
import logging
import os
from typing import NamedTuple, Optional, Tuple

GitCommandNotFound = Exception
log = logging.getLogger("red.downloader")


class CompletedProcess(NamedTuple):
    returncode: int
    stdout: bytes
    stderr: bytes


# will figure out later if it's gonna be a mixin
class GitMixin:
    GIT_EXECUTABLE = "git"

    def __init__(self):
        # this lock ONLY ensures 2 git processes don't run at the same time on one repo directory
        self.lock = asyncio.Lock()

    @classmethod
    async def refresh_git_executable(cls) -> None:
        # has to be called in RepoManager.initialize() (or before)
        git_executable = os.environ.get("RED_GIT_EXECUTABLE", "git")
        # doing it this way is impossible if it's a mixin but shush
        old_git = cls.GIT_EXECUTABLE
        cls.GIT_EXECUTABLE = git_executable
        try:
            await cls().version()
        except (GitCommandNotFound, PermissionError):
            cls.GIT_EXECUTABLE = old_git
            # maybe different error, idk, this text will be useful
            raise GitCommandNotFound(
                "Bad git executable.\n"
                "The git executable must be specified in of the following ways:\n"
                "    - be included in your $PATH\n"
                "    - be set via $RED_GIT_EXECUTABLE"
            )

    async def version(self) -> str:
        p = await self.git("--version")
        return p.stdout.decode()

    async def git(
        self,
        *args: str,
        valid_exit_codes: Tuple[int, ...] = (0,),
        debug_only: bool = False,
        work_dir: Optional[str] = None,
    ) -> CompletedProcess:
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        env.pop("GIT_ASKPASS", None)
        # attempt to force all output to plain ascii english
        # some methods that parse output may expect it
        # according to gettext manual both variables have to be set:
        # https://www.gnu.org/software/gettext/manual/gettext.html#Locale-Environment-Variables
        env["LC_ALL"] = "C"
        env["LANGUAGE"] = "C"
        async with self.lock:
            try:
                process = await asyncio.subprocess.create_subprocess_exec(
                    self.GIT_EXECUTABLE,
                    *args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                )
            except FileNotFoundError:
                raise GitCommandNotFound()
            stdout, stderr = await process.communicate()
            decoded_stderr = stderr.decode().strip()
            if decoded_stderr:
                if debug_only or process.returncode in valid_exit_codes:
                    log.debug(decoded_stderr)
                else:
                    log.error(decoded_stderr)
        # possibly raise on code that isn't in `valid_exit_codes`
        # maybe auto-convert stdout/stderr as string (kwarg option)
        return CompletedProcess(process.returncode, stdout, stderr)
