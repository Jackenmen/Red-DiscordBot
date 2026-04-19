from __future__ import annotations

import inspect
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Coroutine,
    Dict,
    List,
    MutableMapping,
    Optional,
    TypeVar,
    Union,
)

import discord
from discord import app_commands as dpy_app_commands
from typing_extensions import Concatenate, ParamSpec, TypeAlias
from redbot.core import commands
from redbot.core.commands.requires import PermState, PrivilegeLevel

from .requires import AppCommandRequires

if TYPE_CHECKING:
    from redbot.core.bot import Red

T = TypeVar("T")
P = ParamSpec("P")
Binding = Union["Group", "commands.Cog"]
GroupT = TypeVar("GroupT", bound=Binding)
Coro = Coroutine[Any, Any, T]
Interaction: TypeAlias = discord.Interaction["Red"]
Check = Callable[[Interaction], Union[bool, Coro[bool]]]
CommandCallback = Union[
    Callable[Concatenate[GroupT, Interaction, P], Coro[T]],
    Callable[Concatenate[Interaction, P], Coro[T]],
]
ContextMenuCallback = Union[
    Callable[[Interaction, discord.Member], Coro[Any]],
    Callable[[Interaction, discord.User], Coro[Any]],
    Callable[[Interaction, discord.Message], Coro[Any]],
    Callable[[Interaction, Union[discord.Member, discord.User]], Coro[Any]],
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
        self.red_app_command_requires = AppCommandRequires(
            privilege_level=getattr(
                callback, "__red_app_command_requires_privilege_level__", PrivilegeLevel.NONE
            ),
            user_perms=getattr(callback, "__red_app_command_requires_user_perms__", {}),
            bot_perms=getattr(callback, "__red_app_command_requires_bot_perms__", {}),
            checks=getattr(callback, "__red_app_command_requires_checks__", []),
        )

    def _copy_with(
        self,
        *,
        parent: Optional[Group],
        binding: GroupT,
        bindings: MutableMapping[GroupT, GroupT] = discord.utils.MISSING,
        set_on_binding: bool = True,
    ) -> Command:
        copy = super()._copy_with(
            parent=parent, binding=binding, bindings=bindings, set_on_binding=set_on_binding
        )
        copy.red_app_command_requires = self.red_app_command_requires

        return copy

    async def _check_can_run(self, interaction: Interaction) -> bool:
        if not await super()._check_can_run(interaction):
            return False

        to_check = [self]
        parent = self
        while (parent := parent.parent) is not None:
            to_check.append(parent)
        if self.binding is not None and self.binding not in to_check:
            to_check.append(self.binding)

        interaction.extras["red_permission_state"] = PermState.NORMAL
        for thing in reversed(to_check):
            app_command_requires: Optional[AppCommandRequires] = getattr(
                thing, "red_app_command_requires", None
            )
            if app_command_requires is not None:
                ret = await app_command_requires.verify(interaction)
                if ret is False:
                    return False

        return True


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

    @discord.utils.copy_doc(dpy_app_commands.ContextMenu.__init__)
    def __init__(
        self,
        *,
        name: Union[str, dpy_app_commands.locale_str],
        callback: ContextMenuCallback,
        type: dpy_app_commands.AppCommandType = discord.utils.MISSING,
        nsfw: bool = False,
        guild_ids: Optional[List[int]] = None,
        allowed_contexts: Optional[dpy_app_commands.AppCommandContext] = None,
        allowed_installs: Optional[dpy_app_commands.AppInstallationType] = None,
        auto_locale_strings: bool = True,
        extras: Dict[Any, Any] = discord.utils.MISSING,
    ):
        super().__init__(
            name=name,
            callback=callback,
            type=type,
            nsfw=nsfw,
            guild_ids=guild_ids,
            allowed_contexts=allowed_contexts,
            allowed_installs=allowed_installs,
            auto_locale_strings=auto_locale_strings,
            extras=extras,
        )
        self.red_app_command_requires = AppCommandRequires(
            privilege_level=getattr(
                callback, "__red_app_command_requires_privilege_level__", PrivilegeLevel.NONE
            ),
            user_perms=getattr(callback, "__red_app_command_requires_user_perms__", {}),
            bot_perms=getattr(callback, "__red_app_command_requires_bot_perms__", {}),
            checks=getattr(callback, "__red_app_command_requires_checks__", []),
        )

    async def _check_can_run(self, interaction: Interaction) -> bool:
        if not await super()._check_can_run(interaction):
            return False

        interaction.extras["red_permission_state"] = PermState.NORMAL

        return await self.red_app_command_requires.verify(interaction)


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

    @discord.utils.copy_doc(dpy_app_commands.Group.__init__)
    def __init__(
        self,
        *,
        name: Union[str, dpy_app_commands.locale_str] = discord.utils.MISSING,
        description: Union[str, dpy_app_commands.locale_str] = discord.utils.MISSING,
        parent: Optional[Group] = None,
        guild_ids: Optional[List[int]] = None,
        guild_only: bool = discord.utils.MISSING,
        allowed_contexts: Optional[dpy_app_commands.AppCommandContext] = discord.utils.MISSING,
        allowed_installs: Optional[dpy_app_commands.AppInstallationType] = discord.utils.MISSING,
        nsfw: bool = discord.utils.MISSING,
        auto_locale_strings: bool = True,
        default_permissions: Optional[discord.Permissions] = discord.utils.MISSING,
        extras: Dict[Any, Any] = discord.utils.MISSING,
    ):
        super().__init__(
            name=name,
            description=description,
            parent=parent,
            guild_ids=guild_ids,
            guild_only=guild_only,
            allowed_contexts=allowed_contexts,
            allowed_installs=allowed_installs,
            nsfw=nsfw,
            auto_locale_strings=auto_locale_strings,
            default_permissions=default_permissions,
            extras=extras,
        )
        self.red_app_command_requires = AppCommandRequires(
            privilege_level=getattr(
                self, "__red_app_command_requires_privilege_level__", PrivilegeLevel.NONE
            ),
            user_perms=getattr(self, "__red_app_command_requires_user_perms__", {}),
            bot_perms=getattr(self, "__red_app_command_requires_bot_perms__", {}),
            checks=getattr(self, "__red_app_command_requires_checks__", []),
        )

    def _copy_with(
        self,
        *,
        parent: Optional[Group],
        binding: Binding,
        bindings: MutableMapping[Group, Group] = discord.utils.MISSING,
        set_on_binding: bool = True,
    ) -> Group:
        copy = super()._copy_with(
            parent=parent, binding=binding, bindings=bindings, set_on_binding=set_on_binding
        )
        copy.red_app_command_requires = self.red_app_command_requires

        return copy

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
