from __future__ import annotations

import contextlib
import functools
import io
import os
import logging
import discord

from pathlib import Path
from typing import Any, Callable, TYPE_CHECKING, Union, Dict, Optional, TypeVar, overload
from contextvars import ContextVar

import babel.localedata
from babel.core import Locale

if TYPE_CHECKING:
    from redbot.core.bot import Red


__all__ = [
    "get_locale",
    "get_regional_format",
    "get_locale_from_guild",
    "get_regional_format_from_guild",
    "set_contextual_locales_from_guild",
    "Translator",
    "get_babel_locale",
    "get_babel_regional_format",
    "cog_i18n",
]

log = logging.getLogger("red.i18n")

_current_locale = ContextVar("_current_locale", default="en-US")
_current_regional_format = ContextVar("_current_regional_format", default=None)

WAITING_FOR_MSGID = 1
IN_MSGID = 2
WAITING_FOR_MSGSTR = 3
IN_MSGSTR = 4
IN_MSGCTXT = 5

MSGCTXT = 'msgctxt "'
MSGID = 'msgid "'
MSGID_PLURAL = 'msgid_plural "'
MSGSTR = 'msgstr'
MSGSTR_SINGULAR = 'msgstr "'
MSGSTR_PLURAL = 'msgstr['

_translators = []


def get_locale() -> str:
    """
    Get locale in a current context.

    Returns
    -------
    str
        Current locale's language code with country code included, e.g. "en-US".
    """
    return str(_current_locale.get())


def set_locale(locale: str) -> None:
    global _current_locale
    _current_locale = ContextVar("_current_locale", default=locale)
    reload_locales()


def set_contextual_locale(locale: str) -> None:
    _current_locale.set(locale)
    reload_locales()


def get_regional_format() -> str:
    """
    Get regional format in a current context.

    Returns
    -------
    str
        Current regional format's language code with country code included, e.g. "en-US".
    """
    if _current_regional_format.get() is None:
        return str(_current_locale.get())
    return str(_current_regional_format.get())


def set_regional_format(regional_format: Optional[str]) -> None:
    global _current_regional_format
    _current_regional_format = ContextVar("_current_regional_format", default=regional_format)


def set_contextual_regional_format(regional_format: Optional[str]) -> None:
    _current_regional_format.set(regional_format)


def reload_locales() -> None:
    for translator in _translators:
        translator.load_translations()


async def get_locale_from_guild(bot: Red, guild: Optional[discord.Guild]) -> str:
    """
    Get locale set for the given guild.

    Parameters
    ----------
    bot: Red
         The bot's instance.
    guild: Optional[discord.Guild]
         The guild contextual locale is set for.
         Use `None` if the context doesn't involve guild.

    Returns
    -------
    str
        Guild locale's language code with country code included, e.g. "en-US".
    """
    return await bot._i18n_cache.get_locale(guild)


async def get_regional_format_from_guild(bot: Red, guild: Optional[discord.Guild]) -> str:
    """
    Get regional format for the given guild.

    Parameters
    ----------
    bot: Red
         The bot's instance.
    guild: Optional[discord.Guild]
         The guild contextual locale is set for.
         Use `None` if the context doesn't involve guild.

    Returns
    -------
    str
        Guild regional format's language code with country code included, e.g. "en-US".
    """
    return await bot._i18n_cache.get_regional_format(guild)


async def set_contextual_locales_from_guild(bot: Red, guild: Optional[discord.Guild]) -> None:
    """
    Set contextual locales (locale and regional format) for given guild context.

    Parameters
    ----------
    bot: Red
         The bot's instance.
    guild: Optional[discord.Guild]
         The guild contextual locale is set for.
         Use `None` if the context doesn't involve guild.
    """
    locale = await get_locale_from_guild(bot, guild)
    regional_format = await get_regional_format_from_guild(bot, guild)
    set_contextual_locale(locale)
    set_contextual_regional_format(regional_format)


def _parse(translation_file: io.TextIOWrapper) -> Dict[str, str]:
    """
    Custom gettext parsing of translation files.

    Parameters
    ----------
    translation_file : io.TextIOWrapper
        An open text file containing translations.

    Returns
    -------
    Dict[str, str]
        A dict mapping the original strings to their translations. Empty
        translated strings are omitted.

    """
    step = None
    context = None
    plurals = None
    plural_index = None
    untranslated = ""
    translated = ""
    translations = {}
    locale = get_locale()

    translations[locale] = {}

    for line in translation_file:
        line = line.strip()

        if line.startswith(MSGCTXT):
            # record next context
            step = IN_MSGCTXT
            context = line[len(MSGCTXT) : -1]
        elif line.startswith(MSGID):
            # New msgid
            if step is not IN_MSGCTXT:
                context = None

            if step in (IN_MSGCTXT, IN_MSGSTR) and translated:
                # Store the last translation
                msg_id = _unescape(untranslated)
                if context is not None:
                    msg_id = f"{_unescape(context)}\x04{msg_id}"

                if plurals is not None:
                    last_index = max(plurals.keys())
                    value = tuple(_unescape(plurals[idx]) for idx in range(last_index + 1))
                else:
                    value = _unescape(translated)

                translations[locale][msg_id] = value

            step = IN_MSGID
            untranslated = line[len(MSGID) : -1]
            plurals = None
            plural_index = None
        elif line.startswith(MSGID_PLURAL):
            plurals = {}
        elif line.startswith('"') and line.endswith('"'):
            if step is IN_MSGID:
                # Line continuing on from msgid
                untranslated += line[1:-1]
            elif step is IN_MSGSTR:
                # Line continuing on from msgstr
                if plurals is not None:
                    plurals[plural_index] += line[1:-1]
                else:
                    translated += line[1:-1]
            elif step is IN_MSGCTXT:
                # Line continuing on from msgctxt
                context += line[1:-1]
        elif line.startswith(MSGSTR):
            # New msgstr
            step = IN_MSGSTR

            if plurals is None:
                translated = line[len(MSGSTR_SINGULAR) : -1]
            else:
                plural_start = len(MSGSTR_PLURAL)
                plural_end = line.find("]", plural_start) - 1
                plural_index = int(line[plural_start:plural_end])
                plurals[plural_index] = line[plural_end + len(']: "') : -1]

    if step is IN_MSGSTR and translated:
        # Store the final translation
        translations[locale][_unescape(untranslated)] = _unescape(translated)
    return translations


def _unescape(string):
    string = string.replace(r"\\", "\\")
    string = string.replace(r"\t", "\t")
    string = string.replace(r"\r", "\r")
    string = string.replace(r"\n", "\n")
    string = string.replace(r"\"", '"')
    return string


def get_locale_path(cog_folder: Path, extension: str) -> Path:
    """
    Gets the folder path containing localization files.

    :param Path cog_folder:
        The cog folder that we want localizations for.
    :param str extension:
        Extension of localization files.
    :return:
        Path of possible localization file, it may not exist.
    """
    return cog_folder / "locales" / "{}.{}".format(get_locale(), extension)


class Translator(Callable[[str], str]):
    """Function to get translated strings at runtime."""

    def __init__(self, name: str, file_location: Union[str, Path, os.PathLike]):
        """
        Initializes an internationalization object.

        Parameters
        ----------
        name : str
            Your cog name.
        file_location : `str` or `pathlib.Path`
            This should always be ``__file__`` otherwise your localizations
            will not load.

        """
        self.cog_folder = Path(file_location).resolve().parent
        self.cog_name = name
        self.translations = {}

        _translators.append(self)

        self.load_translations()

    @overload
    def __call__(self, message: str, /) -> str:
        ...

    @overload
    def __call__(self, context: str, message: str, /) -> str:
        ...

    @overload
    def __call__(self, singular: str, plural: str, number: int, /) -> str:
        ...

    @overload
    def __call__(self, context: str, singular: str, plural: str, number: int, /) -> str:
        ...

    def __call__(self, *args: Any) -> str:
        """TODO: docstring"""
        funcs = (None, self.gettext, self.pgettext, self.ngettext, self.npgettext)
        return funcs[len(args)](*args)  # type: ignore

    def gettext(self, message: str, /) -> str:
        """TODO: docstring"""
        locale = get_locale()
        catalog = self.translations[locale]

        translated = catalog.get(message)
        if translated is None:
            # TODO: replace `0` with plural function for the locale
            translated = catalog.get((message, 0))

        if translated is None:
            return message

        return translated

    def pgettext(self, context: str, message: str, /) -> str:
        """TODO: docstring"""
        locale = get_locale()
        catalog = self.translations[locale]
        msg_id = f"{context}\x04{message}"

        translated = catalog.get(msg_id)
        if translated is None:
            # TODO: replace `0` with plural function for the locale
            translated = catalog.get((msg_id, 0))

        if translated is None:
            return message

        return translated

    def ngettext(self, singular: str, plural: str, number: int, /) -> str:
        """TODO: docstring"""
        locale = get_locale()
        catalog = self.translations[locale]

        try:
            # replace `number != 1` with plural function for the locale
            return catalog[(singular, number != 1)]
        except KeyError:
            if number == 1:
                return singular
            return plural

    def npgettext(self, context: str, singular: str, plural: str, number: int, /) -> str:
        """TODO: docstring"""
        locale = get_locale()
        catalog = self.translations[locale]
        msg_id = f"{context}\x04{singular}"

        try:
            # replace `number != 1` with plural function for the locale
            return catalog[(msg_id, number != 1)]
        except KeyError:
            if number == 1:
                return singular
            return plural

    def load_translations(self):
        """
        Loads the current translations.
        """
        locale = get_locale()

        if locale.lower() == "en-us":
            # Red is written in en-US, no point in loading it
            return
        if locale in self.translations:
            # Locales cannot be loaded twice as they have an entry in
            # self.translations
            return

        locale_path = get_locale_path(self.cog_folder, "po")
        with contextlib.suppress(IOError, FileNotFoundError):
            with locale_path.open(encoding="utf-8") as file:
                self._parse(file)

    def _parse(self, translation_file):
        self.translations.update(_parse(translation_file))

    def _add_translation(self, untranslated, translated):
        untranslated = _unescape(untranslated)
        translated = _unescape(translated)
        if translated:
            self.translations[untranslated] = translated


@functools.lru_cache()
def _get_babel_locale(red_locale: str) -> babel.core.Locale:
    supported_locales = babel.localedata.locale_identifiers()
    try:  # Handles cases where red_locale is already Babel supported
        babel_locale = Locale(*babel.parse_locale(red_locale))
    except (ValueError, babel.core.UnknownLocaleError):
        try:
            babel_locale = Locale(*babel.parse_locale(red_locale, sep="-"))
        except (ValueError, babel.core.UnknownLocaleError):
            # ValueError is Raised by `parse_locale` when an invalid Locale is given to it
            # Lets handle it silently and default to "en_US"
            try:
                # Try to find a babel locale that's close to the one used by red
                babel_locale = Locale(Locale.negotiate([red_locale], supported_locales, sep="-"))
            except (ValueError, TypeError, babel.core.UnknownLocaleError):
                # If we fail to get a close match we will then default to "en_US"
                babel_locale = Locale("en", "US")
    return babel_locale


def get_babel_locale(locale: Optional[str] = None) -> babel.core.Locale:
    """Function to convert a locale to a `babel.core.Locale`.

    Parameters
    ----------
    locale : Optional[str]
        The locale to convert, if not specified it defaults to the bot's locale.

    Returns
    -------
    babel.core.Locale
        The babel locale object.
    """
    if locale is None:
        locale = get_locale()
    return _get_babel_locale(locale)


def get_babel_regional_format(regional_format: Optional[str] = None) -> babel.core.Locale:
    """Function to convert a regional format to a `babel.core.Locale`.

    If ``regional_format`` parameter is passed, this behaves the same as `get_babel_locale`.

    Parameters
    ----------
    regional_format : Optional[str]
        The regional format to convert, if not specified it defaults to the bot's regional format.

    Returns
    -------
    babel.core.Locale
        The babel locale object.
    """
    if regional_format is None:
        regional_format = get_regional_format()
    return _get_babel_locale(regional_format)


# This import to be down here to avoid circular import issues.
# This will be cleaned up at a later date
# noinspection PyPep8
from . import commands

_TypeT = TypeVar("_TypeT", bound=type)


def cog_i18n(translator: Translator) -> Callable[[_TypeT], _TypeT]:
    """Get a class decorator to link the translator to this cog."""

    def decorator(cog_class: _TypeT) -> _TypeT:
        cog_class.__translator__ = translator
        for name, attr in cog_class.__dict__.items():
            if isinstance(attr, (commands.Group, commands.Command)):
                attr.translator = translator
                setattr(cog_class, name, attr)
        return cog_class

    return decorator
