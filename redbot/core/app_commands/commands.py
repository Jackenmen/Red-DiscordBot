from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any, Callable, Coroutine, Dict, List, Optional, TypeVar, Union

import discord
from discord import app_commands as dpy_app_commands
from typing_extensions import Concatenate, ParamSpec

if TYPE_CHECKING:
    from redbot.core import commands

T = TypeVar("T")
P = ParamSpec("P")
Binding = Union["Group", "commands.Cog"]
GroupT = TypeVar("GroupT", bound=Binding)
Coro = Coroutine[Any, Any, T]
CommandCallback = Union[
    Callable[Concatenate[GroupT, discord.Interaction[Any], P], Coro[T]],
    Callable[Concatenate[discord.Interaction[Any], P], Coro[T]],
]
ContextMenuCallback = Union[
    Callable[[discord.Interaction[Any], discord.Member], Coro[Any]],
    Callable[[discord.Interaction[Any], discord.User], Coro[Any]],
    Callable[[discord.Interaction[Any], discord.Message], Coro[Any]],
    Callable[[discord.Interaction[Any], Union[discord.Member, discord.User]], Coro[Any]],
]


def _reset_init_subclass_attrs(cls: T) -> T:
    to_remove = [attr for attr in cls.__dict__ if attr.startswith("__discord_app_commands_")]
    for attr in to_remove:
        delattr(cls, attr)
    return cls


class Command(dpy_app_commands.Command[GroupT, P, T]):
    """
    A class that implements an application command for Red.

    This class inherits from `discord.app_commands.Command`. The
    attributes listed below are simply additions to the ones listed
    with that class.

    These are usually not created manually, instead they are created using
    one of the following decorators:

    - `command()`
    - `Group.command()`
    - `RedTree.command()`

    .. warning::

        Making subclasses of this class is not supported.
    """

    @discord.utils.copy_doc(dpy_app_commands.Command.__init__)
    def __init__(
        self,
        *,
        name: Union[str, dpy_app_commands.locale_str],
        description: Union[str, dpy_app_commands.locale_str],
        callback: CommandCallback[GroupT, P, T],
        nsfw: bool = False,
        parent: Optional[Group] = None,
        guild_ids: Optional[List[int]] = None,
        allowed_contexts: Optional[dpy_app_commands.AppCommandContext] = None,
        allowed_installs: Optional[dpy_app_commands.AppInstallationType] = None,
        auto_locale_strings: bool = True,
        extras: Dict[Any, Any] = discord.utils.MISSING,
    ) -> None:
        super().__init__(
            name=name,
            description=description,
            callback=callback,
            nsfw=nsfw,
            parent=parent,
            guild_ids=guild_ids,
            allowed_contexts=allowed_contexts,
            allowed_installs=allowed_installs,
            auto_locale_strings=auto_locale_strings,
            extras=extras,
        )


@_reset_init_subclass_attrs
class Group(dpy_app_commands.Group):
    """
    A class that implements an application command group for Red.

    This class inherits from `discord.app_commands.Group`. The
    attributes listed below are simply additions to the ones listed
    with that class.

    This class is usually inherited rather than created manually.

    Decorators such as `guild_only() <discord.app_commands.guild_only>`,
    `guilds() <discord.app_commands.guilds>`,
    and `default_permissions <discord.app_commands.default_permissions>`
    will apply to the group if used on top of a subclass. For example:

    .. code::

        from redbot.core import app_commands

        @app_commands.guild_only()
        class MyGroup(app_commands.Group):
            pass
    """

    @discord.utils.copy_doc(dpy_app_commands.Group.command)
    def command(
        self,
        *,
        name: Union[str, dpy_app_commands.locale_str] = discord.utils.MISSING,
        description: Union[str, dpy_app_commands.locale_str] = discord.utils.MISSING,
        nsfw: bool = False,
        auto_locale_strings: bool = True,
        extras: Dict[Any, Any] = discord.utils.MISSING,
    ) -> Callable[[CommandCallback[GroupT, P, T]], Command[GroupT, P, T]]:
        def decorator(func: CommandCallback[GroupT, P, T]) -> Command[GroupT, P, T]:
            # TODO: replace with iscoroutinefunction internal util from Red-DiscordBot#6744
            if not inspect.iscoroutinefunction(func):
                raise TypeError("command function must be a coroutine function")

            if description is discord.utils.MISSING:
                if func.__doc__ is None:
                    desc = "\N{HORIZONTAL ELLIPSIS}"
                else:
                    desc = discord.utils._shorten(func.__doc__)
            else:
                desc = description

            command = Command(
                name=name if name is not discord.utils.MISSING else func.__name__,
                description=desc,
                callback=func,
                nsfw=nsfw,
                parent=self,
                auto_locale_strings=auto_locale_strings,
                extras=extras,
            )
            self.add_command(command)
            return command

        return decorator


class ContextMenu(dpy_app_commands.ContextMenu):
    """
    A class that implements a context menu application command for Red.

    This class inherits from `discord.app_commands.ContextMenu`. The
    attributes listed below are simply additions to the ones listed
    with that class.

    These are usually not created manually, instead they are created using
    one of the following decorators:

    - `context_menu()`
    - `RedTree.context_menu()`

    .. warning::

        Making subclasses of this class is not supported.
    """


@discord.utils.copy_doc(dpy_app_commands.command)
def command(
    *,
    name: Union[str, dpy_app_commands.locale_str] = discord.utils.MISSING,
    description: Union[str, dpy_app_commands.locale_str] = discord.utils.MISSING,
    nsfw: bool = False,
    auto_locale_strings: bool = True,
    extras: Dict[Any, Any] = discord.utils.MISSING,
) -> Callable[[CommandCallback[GroupT, P, T]], Command[GroupT, P, T]]:
    def decorator(func: CommandCallback[GroupT, P, T]) -> Command[GroupT, P, T]:
        # TODO: replace with iscoroutinefunction internal util from Red-DiscordBot#6744
        if not inspect.iscoroutinefunction(func):
            raise TypeError("command function must be a coroutine function")

        if description is discord.utils.MISSING:
            if func.__doc__ is None:
                desc = "\N{HORIZONTAL ELLIPSIS}"
            else:
                desc = discord.utils._shorten(func.__doc__)
        else:
            desc = description

        return Command(
            name=name if name is not discord.utils.MISSING else func.__name__,
            description=desc,
            callback=func,
            parent=None,
            nsfw=nsfw,
            auto_locale_strings=auto_locale_strings,
            extras=extras,
        )

    return decorator


@discord.utils.copy_doc(dpy_app_commands.context_menu)
def context_menu(
    *,
    name: Union[str, dpy_app_commands.locale_str] = discord.utils.MISSING,
    nsfw: bool = False,
    auto_locale_strings: bool = True,
    extras: Dict[Any, Any] = discord.utils.MISSING,
) -> Callable[[ContextMenuCallback], ContextMenu]:
    def decorator(func: ContextMenuCallback) -> ContextMenu:
        # TODO: replace with iscoroutinefunction internal util from Red-DiscordBot#6744
        if not inspect.iscoroutinefunction(func):
            raise TypeError("context menu function must be a coroutine function")

        actual_name = func.__name__.title() if name is discord.utils.MISSING else name
        return ContextMenu(
            name=actual_name,
            nsfw=nsfw,
            callback=func,
            auto_locale_strings=auto_locale_strings,
            extras=extras,
        )

    return decorator
