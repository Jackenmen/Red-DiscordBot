import asyncio
import logging
import os
from typing import Literal, NamedTuple, Optional, Tuple, Union, cast, overload

GitCommandNotFound = Exception
BadGitVersion = Exception
InvalidExitCode = Exception
log = logging.getLogger("red.downloader")


# we'll figure out the names for these types later
# generic NamedTuple could be nice here but mypy doesn't support those
class RawCompletedProcess(NamedTuple):
    returncode: int
    stdout: bytes
    stderr: bytes


class ProcessedCompletedProcess(NamedTuple):
    returncode: int
    stdout: str
    stderr: str


# will figure out later if it's gonna be a mixin
class GitMixin:
    GIT_EXECUTABLE = "git"
    REQUIRED_GIT_VERSION = (2, 11)

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
            version, raw_version = await cls().version()
        except (GitCommandNotFound, PermissionError):
            cls.GIT_EXECUTABLE = old_git
            # maybe different error, idk, this text will be useful
            raise GitCommandNotFound(
                "Bad git executable.\n"
                "The git executable must be specified in of the following ways:\n"
                "    - be included in your $PATH\n"
                "    - be set via $RED_GIT_EXECUTABLE"
            )
        if version < cls.REQUIRED_GIT_VERSION:
            raise BadGitVersion(f"Red requires Git 2.11+ and you're using Git {raw_version}")

    async def version(self) -> Tuple[Tuple[int, int], str]:
        """returns tuple of tuple (major, minor) and raw version string"""
        raw_version = await self.raw_version()
        # we're only interested in major and minor version if we will ever need micro
        # there's more handling needed for versions like `2.25.0-rc1` and `2.25.0.windows.1`
        version = tuple(int(n) for n in raw_version.split(".", maxsplit=3)[:2])
        # first 2 parts of the version are guaranteed here so we can do such cast safely
        return (cast(Tuple[int, int], version), raw_version)

    async def raw_version(self) -> str:
        p = await self.git("version")
        # "git version " takes 12 characters, format of string returned by `git version` is stable
        return p.stdout[12:]

    @overload
    async def git(
        self,
        *args: str,
        valid_exit_codes: Tuple[int, ...] = (0,),
        debug_only: bool = False,
        work_dir: Optional[str] = None,
        process_output: Literal[True] = True,
    ) -> ProcessedCompletedProcess:
        ...

    @overload
    async def git(
        self,
        *args: str,
        valid_exit_codes: Tuple[int, ...] = (0,),
        debug_only: bool = False,
        work_dir: Optional[str] = None,
        process_output: Literal[False],
    ) -> RawCompletedProcess:
        ...

    async def git(
        self,
        *args: str,
        valid_exit_codes: Tuple[int, ...] = (0,),
        debug_only: bool = False,
        work_dir: Optional[str] = None,
        process_output: bool = True,
    ) -> Union[RawCompletedProcess, ProcessedCompletedProcess]:
        env = os.environ.copy()
        # these should be made configurable later
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
            is_valid = process.returncode in valid_exit_codes
            if decoded_stderr:
                if debug_only or is_valid:
                    log.debug(decoded_stderr)
                else:
                    log.error(decoded_stderr)
        # maybe auto-convert stdout/stderr as string (kwarg option)
        ret: Union[RawCompletedProcess, ProcessedCompletedProcess]
        if process_output:
            decoded_stdout = stdout.decode().strip()
            ret = ProcessedCompletedProcess(process.returncode, decoded_stdout, decoded_stderr)
        else:
            ret = RawCompletedProcess(process.returncode, stdout, stderr)
        # possibly add arg that disables raising
        if not is_valid:
            # maybe this should not be here? we put custom messages for raised exceptions
            # but we could possibly just catch it and reraise with proper error message
            # or maybe pass what should be error message to the function call
            # (while this sounds convienent, it doesn't seem very clean)
            # yeah, this error is not gonna be very helpful
            # unless something wasn't handled I guess
            raise InvalidExitCode(ret)
        return ret
