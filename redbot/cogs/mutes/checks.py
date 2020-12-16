import logging

from redbot.core import commands, i18n

_ = i18n.Translator("Mutes", __file__)
log = logging.getLogger("red.cogs.mutes")


async def mfa_check():
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.guild is not None and ctx.guild.mfa_level == 1 and not ctx.bot.user.mfa_enabled:
            log.error(
                "Unmute/mute has been attempted in a guild (%s) with 2FA requirement,"
                " but the bot owner doesn't have 2FA enabled.",
                ctx.guild.id,
            )
            raise commands.CheckFailure(
                _("The action couldn't have been taken due to an unexpected error.")
            )
        return True

    return commands.check(predicate)
