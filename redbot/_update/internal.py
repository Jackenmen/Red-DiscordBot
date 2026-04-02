import click
import subprocess
import shutil
import sys
import tempfile
from pathlib import Path

from . import common, runner


@click.group(invoke_without_command=True)
@click.option("--debug")
def cli(debug: bool) -> None:
    common.configure_logging(debug=debug)


@cli.command()
def finish_update() -> None:
    print("Received result!")
    print(runner.get_request_output())
    backup_dir = Path(sys.prefix) / ".redbot-update-backup"
    new_backup_dir = Path(tempfile.mkdtemp())
    print(
        "Backup of the original venv is available at:",
        shutil.move(str(backup_dir), str(new_backup_dir)),
    )


@cli.command()
def reinstall_example() -> None:
    venv_dir = Path(sys.prefix)
    rel_executable = Path(sys.executable).relative_to(venv_dir)
    backup_dir = venv_dir / ".redbot-update-backup"
    # TODO: show nice error when a backup already exists
    backup_dir.mkdir()
    wrapper_exe = runner.get_wrapper_executable()
    # TODO: maybe try moving python.exe first?
    for path in venv_dir.iterdir():
        if path == backup_dir or path == wrapper_exe:
            continue
        path.rename(backup_dir / path.name)
    new_executable = backup_dir / rel_executable
    runner.make_exec_request(str(new_executable), "reinstall", str(venv_dir), sys.executable)


@cli.command()
@click.argument("venv_dir")
@click.argument("old_executable")
def reinstall(venv_dir: str, old_executable: str) -> None:
    print("Received result!")
    print(runner.get_request_output())
    # TODO: do not use sys._base_executable!!!
    subprocess.check_call((sys._base_executable, "-m", "venv", venv_dir))
    subprocess.check_call((old_executable, "-m", "pip", "install", "-e", "."))
    runner.make_exec_request(old_executable, "finish-update")


if __name__ == "__main__":
    cli()
