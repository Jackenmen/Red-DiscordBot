from __future__ import annotations

import asyncio
import inspect
from typing import TYPE_CHECKING, Awaitable, Callable, Dict, List, Optional, TypeVar, Union
from typing_extensions import TypeAlias

import discord
from discord.app_commands import BotMissingPermissions, check

from redbot.core.commands.requires import (
    PermState,
    PrivilegeLevel,
    RequiresBase,
    TransitionResult,
    transition_permstate_to,
    _validate_perms_dict,
)

if TYPE_CHECKING:
    from redbot.core.bot import Red

__all__ = [
    "AppCommandRequires",
]

_T = TypeVar("_T")
Interaction: TypeAlias = discord.Interaction["Red"]
CheckPredicate = Callable[[Interaction], Union[Optional[bool], Awaitable[Optional[bool]]]]


class AppCommandRequires(RequiresBase):
    """
    This class describes the requirements for executing a specific app command.

    The permissions described include both bot permissions and user
    permissions.

    Attributes
    ----------
    checks : List[Callable[[Interaction], Union[bool, Awaitable[bool]]]]
        A list of checks which can be overridden by rules. Use
        `Command.checks` if you would like them to never be overridden.

    """

    def __init__(
        self,
        privilege_level: Optional[PrivilegeLevel],
        user_perms: Union[Dict[str, bool], discord.Permissions, None],
        bot_perms: Union[Dict[str, bool], discord.Permissions],
        checks: List[CheckPredicate],
    ):
        super().__init__(privilege_level, user_perms, bot_perms)
        self.checks: List[CheckPredicate] = checks
        # this is used for permissions cog which does not currently support app commands
        self.ready_event.set()

    @staticmethod
    def get_decorator(
        privilege_level: Optional[PrivilegeLevel], user_perms: Optional[Dict[str, bool]]
    ) -> Callable[[_T], _T]:
        if not user_perms:
            user_perms = None

        def decorator(func: _T) -> _T:
            if inspect.iscoroutinefunction(func):
                func.__red_app_command_requires_privilege_level__ = privilege_level
                if user_perms is None:
                    func.__red_app_command_requires_user_perms__ = None
                else:
                    _validate_perms_dict(user_perms)
                    if getattr(func, "__red_app_command_requires_user_perms__", None) is None:
                        func.__red_app_command_requires_user_perms__ = discord.Permissions.none()
                    func.__red_app_command_requires_user_perms__.update(**user_perms)
            else:
                func.red_app_command_requires.privilege_level = privilege_level
                if user_perms is None:
                    func.red_app_command_requires.user_perms = None
                else:
                    _validate_perms_dict(user_perms)
                    if func.red_app_command_requires.user_perms is None:
                        func.red_app_command_requires.user_perms = discord.Permissions.none()
                    func.red_app_command_requires.user_perms.update(**user_perms)
            return func

        return decorator

    async def verify(self, interaction: Interaction) -> bool:
        """
        Check if the given app command interaction passes the requirements.

        This will check the bot permissions, overrides, user permissions
        and privilege level.

        Parameters
        ----------
        interaction : discord.Interaction
            The app command's interaction to check with.

        Returns
        -------
        bool
            ``True`` if the interaction passes the requirements.

        Raises
        ------
        BotMissingPermissions
            If the bot is missing required permissions to run the
            command.
        CommandError
            Propagated from any permissions checks.
        """
        if not self.ready_event.is_set():
            await self.ready_event.wait()
        await self._verify_bot(interaction)

        # Owner should never be locked out of commands for user permissions.
        if await interaction.client.is_owner(interaction.user):
            return True
        # Owner-only commands are non-overrideable, and we already checked for owner.
        if self.privilege_level is PrivilegeLevel.BOT_OWNER:
            return False

        hook_result = await interaction.client.verify_app_command_permissions_hooks(interaction)
        if hook_result is not None:
            return hook_result

        return await self._transition_state(interaction)

    async def _verify_bot(self, interaction: Interaction) -> None:
        bot_perms = interaction.app_permissions
        if not (bot_perms.administrator or bot_perms >= self.bot_perms):
            missing_perms = self._missing_perms(self.bot_perms, bot_perms)
            missing = [perm for perm, value in missing_perms if value is True]
            raise BotMissingPermissions(missing)

    async def _transition_state(self, interaction: Interaction) -> bool:
        should_invoke, next_state = self._get_transitioned_state(interaction)
        if should_invoke is None:
            # NORMAL invocation, we simply follow standard procedure
            should_invoke = await self._verify_user(interaction)
        elif isinstance(next_state, dict):
            # NORMAL to PASSIVE_ALLOW; should we proceed as normal or transition?
            # We must check what would happen normally, if no explicit rules were set.
            would_invoke = self._get_would_invoke(interaction.guild_id)
            if would_invoke is None:
                would_invoke = await self._verify_user(interaction)
            next_state = next_state[would_invoke]

        assert isinstance(next_state, PermState)
        interaction.extras["red_permission_state"] = next_state
        return should_invoke

    def _get_transitioned_state(self, interaction: discord.Interaction[Red]) -> TransitionResult:
        prev_state = interaction.extras["red_permission_state"]
        cur_state = self._get_rule_from_interaction(interaction)
        return transition_permstate_to(prev_state, cur_state)

    async def _verify_user(self, interaction: Interaction) -> bool:
        checks_pass = await self._verify_checks(interaction)
        if checks_pass is False:
            return False

        if self.user_perms is not None:
            user_perms = interaction.permissions
            if user_perms.administrator or user_perms >= self.user_perms:
                return True

        if self.privilege_level is not None:
            privilege_level = await PrivilegeLevel.from_interaction(interaction)
            if privilege_level >= self.privilege_level:
                return True

        return False

    def _get_rule_from_interaction(self, interaction: discord.Interaction[Red]) -> PermState:
        author = interaction.user
        guild = discord.Object(id=interaction.guild_id) if interaction.guild_id else None
        if guild is None:
            # We only check the user for DM channels
            rule = self._global_rules.get(author.id)
            if rule is not None:
                return rule
            return self.get_rule(self.DEFAULT, self.GLOBAL)

        rules_chain = [self._global_rules]
        guild_rules = self._guild_rules.get(guild.id)
        if guild_rules:
            rules_chain.append(guild_rules)

        channels = []
        if author.voice is not None:
            channels.append(author.voice.channel)
        if isinstance(interaction.channel, discord.Thread):
            channels.append(interaction.channel.parent)
        else:
            channels.append(interaction.channel)
        category = interaction.channel.category
        if category is not None:
            channels.append(category)

        # We want author roles sorted highest to lowest, and exclude the @everyone role
        author_roles = reversed(author.roles[1:])

        model_chain = [author, *channels, *author_roles, guild]

        for rules in rules_chain:
            for model in model_chain:
                rule = rules.get(model.id)
                if rule is not None:
                    return rule
            del model_chain[-1]  # We don't check for the guild in guild rules

        default_rule = self.get_rule(self.DEFAULT, guild.id)
        if default_rule is PermState.NORMAL:
            default_rule = self.get_rule(self.DEFAULT, self.GLOBAL)
        return default_rule

    async def _verify_checks(self, interaction: Interaction) -> bool:
        if not self.checks:
            return True
        return await discord.utils.async_all(check(interaction) for check in self.checks)


# check decorators


def permissions_check(predicate: CheckPredicate) -> Callable[[_T], _T]:
    """An overwriteable version of `discord.ext.commands.check`.

    This has the same behaviour as `discord.ext.commands.check`,
    however this check can be ignored if the command is allowed
    through a permissions cog.
    """

    def decorator(func: _T) -> _T:
        if hasattr(func, "red_app_command_requires"):
            func.red_app_command_requires.checks.append(predicate)
        else:
            if not hasattr(func, "__red_app_command_requires_checks__"):
                func.__red_app_command_requires_checks__ = []
            func.__red_app_command_requires_checks__.append(predicate)
        return func

    return decorator


def bot_has_permissions(**perms: bool) -> Callable[[_T], _T]:
    """Complain if the bot is missing permissions.

    If the user tries to run the command, but the bot is missing the
    permissions, it will send a message describing which permissions
    are missing.

    This check cannot be overridden by rules.
    """

    def decorator(func: _T) -> _T:
        if asyncio.iscoroutinefunction(func):
            if not hasattr(func, "__red_app_command_requires_bot_perms__"):
                func.__red_app_command_requires_bot_perms__ = discord.Permissions.none()
            _validate_perms_dict(perms)
            func.__red_app_command_requires_bot_perms__.update(**perms)
        else:
            _validate_perms_dict(perms)
            func.red_app_command_requires.bot_perms.update(**perms)
        return func

    return decorator


def bot_in_a_guild() -> Callable[[_T], _T]:
    """Deny the command if the bot is not in a guild."""

    async def predicate(interaction: Interaction):
        return len(interaction.client.guilds) > 0

    return check(predicate)


def bot_can_manage_channel(*, allow_thread_owner: bool = False) -> Callable[[_T], _T]:
    """
    Complain if the bot is missing permissions to manage channel.

    This check properly resolves the permissions for `discord.Thread` as well.

    Parameters
    ----------
    allow_thread_owner: bool
        If ``True``, the command will also be allowed to run if the bot is a thread owner.
        This can, for example, be useful to check if the bot can edit a channel/thread's name
        as that, in addition to members with manage channel/threads permission,
        can also be done by the thread owner.
    """

    def predicate(interaction: Interaction) -> bool:
        if interaction.guild_id is None:
            return False

        perms = interaction.app_permissions
        channel = interaction.channel
        obj = interaction.user
        if isinstance(channel, discord.Thread):
            if not (perms.manage_threads or (allow_thread_owner and channel.owner_id == obj.id)):
                # This is a slight lie - thread owner *might* also be allowed
                # but we just say that bot is missing the Manage Threads permission.
                raise BotMissingPermissions(["manage_threads"])
        elif not perms.manage_channels:
            raise BotMissingPermissions(["manage_channels"])

        return True

    return check(predicate)


def bot_can_react() -> Callable[[_T], _T]:
    """
    Complain if the bot is missing permissions to react.

    This check properly resolves the permissions for `discord.Thread` as well.
    """

    async def predicate(interaction: Interaction) -> bool:
        return not (
            isinstance(interaction.channel, discord.Thread) and interaction.channel.archived
        )

    def decorator(func: _T) -> _T:
        func = bot_has_permissions(read_message_history=True, add_reactions=True)(func)
        func = check(predicate)(func)
        return func

    return decorator


def _can_manage_channel_deco(
    *, privilege_level: Optional[PrivilegeLevel] = None, allow_thread_owner: bool = False
) -> Callable[[_T], _T]:
    async def predicate(interaction: Interaction) -> bool:
        perms = interaction.permissions
        channel = interaction.channel
        obj = interaction.user
        if isinstance(channel, discord.Thread):
            if perms.manage_threads or (allow_thread_owner and channel.owner_id == obj.id):
                # This is a slight lie - thread owner *might* also be allowed
                # but we just say that bot is missing the Manage Threads permission.
                return True
        elif perms.manage_channels:
            return True

        if privilege_level is not None:
            if await PrivilegeLevel.from_interaction(interaction) >= privilege_level:
                return True

        return False

    return permissions_check(predicate)


def has_permissions(**perms: bool):
    """Restrict the command to users with these permissions.

    This check can be overridden by rules.
    """
    if perms is None:
        raise TypeError("Must provide at least one keyword argument to has_permissions")
    return AppCommandRequires.get_decorator(None, perms)


def can_manage_channel(*, allow_thread_owner: bool = False) -> Callable[[_T], _T]:
    """Restrict the command to users with permissions to manage channel.

    This check properly resolves the permissions for `discord.Thread` as well.

    This check can be overridden by rules.

    Parameters
    ----------
    allow_thread_owner: bool
        If ``True``, the command will also be allowed to run if the author is a thread owner.
        This can, for example, be useful to check if the author can edit a channel/thread's name
        as that, in addition to members with manage channel/threads permission,
        can also be done by the thread owner.
    """
    return _can_manage_channel_deco(allow_thread_owner=allow_thread_owner)


def is_owner():
    """Restrict the command to bot owners.

    This check cannot be overridden by rules.
    """
    return AppCommandRequires.get_decorator(PrivilegeLevel.BOT_OWNER, {})


def guildowner_or_permissions(**perms: bool):
    """Restrict the command to the guild owner or users with these permissions.

    This check can be overridden by rules.
    """
    return AppCommandRequires.get_decorator(PrivilegeLevel.GUILD_OWNER, perms)


def guildowner_or_can_manage_channel(*, allow_thread_owner: bool = False) -> Callable[[_T], _T]:
    """Restrict the command to the guild owner or user with permissions to manage channel.

    This check properly resolves the permissions for `discord.Thread` as well.

    This check can be overridden by rules.

    Parameters
    ----------
    allow_thread_owner: bool
        If ``True``, the command will also be allowed to run if the author is a thread owner.
        This can, for example, be useful to check if the author can edit a channel/thread's name
        as that, in addition to members with manage channel/threads permission,
        can also be done by the thread owner.
    """
    return _can_manage_channel_deco(
        privilege_level=PrivilegeLevel.GUILD_OWNER, allow_thread_owner=allow_thread_owner
    )


def guildowner():
    """Restrict the command to the guild owner.

    This check can be overridden by rules.
    """
    return guildowner_or_permissions()


def admin_or_permissions(**perms: bool):
    """Restrict the command to users with the admin role or these permissions.

    This check can be overridden by rules.
    """
    return AppCommandRequires.get_decorator(PrivilegeLevel.ADMIN, perms)


def admin_or_can_manage_channel(*, allow_thread_owner: bool = False) -> Callable[[_T], _T]:
    """Restrict the command to users with the admin role or permissions to manage channel.

    This check properly resolves the permissions for `discord.Thread` as well.

    This check can be overridden by rules.

    Parameters
    ----------
    allow_thread_owner: bool
        If ``True``, the command will also be allowed to run if the author is a thread owner.
        This can, for example, be useful to check if the author can edit a channel/thread's name
        as that, in addition to members with manage channel/threads permission,
        can also be done by the thread owner.
    """
    return _can_manage_channel_deco(
        privilege_level=PrivilegeLevel.ADMIN, allow_thread_owner=allow_thread_owner
    )


def admin():
    """Restrict the command to users with the admin role.

    This check can be overridden by rules.
    """
    return admin_or_permissions()


def mod_or_permissions(**perms: bool):
    """Restrict the command to users with the mod role or these permissions.

    This check can be overridden by rules.
    """
    return AppCommandRequires.get_decorator(PrivilegeLevel.MOD, perms)


def mod_or_can_manage_channel(*, allow_thread_owner: bool = False) -> Callable[[_T], _T]:
    """Restrict the command to users with the mod role or permissions to manage channel.

    This check properly resolves the permissions for `discord.Thread` as well.

    This check can be overridden by rules.

    Parameters
    ----------
    allow_thread_owner: bool
        If ``True``, the command will also be allowed to run if the author is a thread owner.
        This can, for example, be useful to check if the author can edit a channel/thread's name
        as that, in addition to members with manage channel/threads permission,
        can also be done by the thread owner.
    """
    return _can_manage_channel_deco(
        privilege_level=PrivilegeLevel.MOD, allow_thread_owner=allow_thread_owner
    )


def mod():
    """Restrict the command to users with the mod role.

    This check can be overridden by rules.
    """
    return mod_or_permissions()
