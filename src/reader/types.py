import dataclasses
import re
import warnings
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any
from typing import Callable
from typing import cast
from typing import Dict
from typing import Iterable
from typing import List
from typing import Mapping
from typing import Optional
from typing import Sequence
from typing import Tuple
from typing import Type
from typing import TypeVar
from typing import Union

from typing_extensions import Literal
from typing_extensions import Protocol
from typing_extensions import runtime_checkable


_T = TypeVar('_T')


class _namedtuple_compat:

    """Add namedtuple-like methods to a dataclass."""

    # TODO: can we get rid of _namedtuple_compat?

    @classmethod
    def _make(cls: Type[_T], iterable: Iterable[Any]) -> _T:
        iterable = tuple(iterable)
        attrs_len = len(dataclasses.fields(cls))
        if len(iterable) != attrs_len:
            raise TypeError(
                'Expected %d arguments, got %d' % (attrs_len, len(iterable))
            )
        return cls(*iterable)

    _replace = dataclasses.replace

    # FIXME: this recurses, unlike namedtuple._asdict; remove it
    _asdict = dataclasses.asdict


# See https://github.com/lemon24/reader/issues/159 for a discussion
# of how feed- and entry-like objects are uniquely identified, and
# how to keep it consistent.


# Public API


@dataclass(frozen=True)
class Feed(_namedtuple_compat):

    """Data type representing a feed."""

    #: The URL of the feed.
    url: str

    #: The date the feed was last updated.
    updated: Optional[datetime] = None

    #: The title of the feed.
    title: Optional[str] = None

    #: The URL of a page associated with the feed.
    link: Optional[str] = None

    #: The author of the feed.
    author: Optional[str] = None

    #: User-defined feed title.
    user_title: Optional[str] = None


@dataclass(frozen=True)
class Entry(_namedtuple_compat):

    """Data type representing an entry."""

    # WARNING: When changing attributes, keep Entry and EntryData in sync.

    @property
    def feed_url(self) -> str:
        """The feed url."""
        return self.feed.url

    #: The entry id.
    id: str

    #: The date the entry was last updated.
    updated: datetime

    #: The title of the entry.
    title: Optional[str] = None

    #: The URL of a page associated with the entry.
    link: Optional[str] = None

    #: The author of the feed.
    author: Optional[str] = None

    #: The date the entry was first published.
    published: Optional[datetime] = None

    #: A summary of the entry.
    summary: Optional[str] = None

    #: Full content of the entry.
    #: A sequence of :class:`Content` objects.
    content: Sequence['Content'] = ()

    #: External files associated with the entry.
    #: A sequence of :class:`Enclosure` objects.
    enclosures: Sequence['Enclosure'] = ()

    #: Whether the entry was read or not.
    read: bool = False

    #: Whether the entry is important or not.
    important: bool = False

    # feed should not have a default, but I'd prefer objects that aren't
    # entry data to be at the end, and dataclasses don't support keyword-only
    # arguments yet.
    #
    # We could use a null object as the default (Feed('')), but None
    # increases the chance we'll catch feed= not being set at runtime;
    # we don't check for it in __post_init__ because it's still useful
    # to have it None in tests. The cast is to please mypy.

    #: The entry's feed.
    feed: Feed = cast(Feed, None)


@dataclass(frozen=True)
class Content(_namedtuple_compat):

    """Data type representing a piece of content."""

    #: The content value.
    value: str

    #: The content type.
    type: Optional[str] = None

    #: The content language.
    language: Optional[str] = None


@dataclass(frozen=True)
class Enclosure(_namedtuple_compat):

    """Data type representing an external file."""

    #: The file URL.
    href: str

    #: The file content type.
    type: Optional[str] = None

    #: The file length.
    length: Optional[int] = None


_HS = TypeVar('_HS', bound='HighlightedString')


@dataclass(frozen=True)
class HighlightedString:

    """A string that has some of its parts highlighted."""

    # TODO: show if we're at the start/end of the value

    #: The underlying string.
    value: str = ''

    #: The highlights; non-overlapping slices with positive start/stop
    #: and None step.
    highlights: Sequence[slice] = ()

    def __post_init__(self) -> None:
        for highlight in self.highlights:
            reason = ''

            if highlight.start is None or highlight.stop is None:
                reason = 'start and stop must not be None'
            elif highlight.step is not None:
                reason = 'step must be None'
            elif highlight.start < 0 or highlight.stop < 0:
                reason = 'start and stop must be equal to or greater than 0'
            elif highlight.start > len(self.value) or highlight.stop > len(self.value):
                reason = (
                    'start and stop must be less than or equal to the string length'
                )
            elif highlight.start > highlight.stop:
                reason = 'start must be not be greater than stop'

            if reason:
                raise ValueError(f'invalid highlight: {reason}: {highlight}')

        highlights = sorted(self.highlights, key=lambda s: (s.start, s.stop))

        prev_highlight = None
        for highlight in highlights:
            if not prev_highlight:
                prev_highlight = highlight
                continue

            if prev_highlight.stop > highlight.start:
                raise ValueError(
                    f'highlights must not overlap: {prev_highlight}, {highlight}'
                )

        object.__setattr__(self, 'highlights', tuple(highlights))

    def __str__(self) -> str:
        return self.value

    @classmethod
    def extract(cls: Type[_HS], text: str, before: str, after: str) -> _HS:
        """Extract highlights with before/after markers from text.

        >>> HighlightedString.extract( '>one< two', '>', '<')
        HighlightedString(value='one two', highlights=(slice(0, 3, None),))

        Args:
            text (str): The original text, with highlights marked by ``before`` and ``after``.
            before (str): Highlight start marker.
            after (str): Highlight stop marker.

        Returns:
            HighlightedString: A highlighted string.

        """
        pattern = f"({'|'.join(re.escape(s) for s in (before, after))})"

        parts = []
        slices = []

        index = 0
        start = None

        for part in re.split(pattern, text):
            if part == before:
                if start is not None:
                    raise ValueError("highlight start marker in highlight")
                start = index
                continue

            if part == after:
                if start is None:
                    raise ValueError("unmatched highlight end marker")
                slices.append(slice(start, index))
                start = None
                continue

            parts.append(part)
            index += len(part)

        if start is not None:
            raise ValueError("highlight is never closed")

        return cls(''.join(parts), tuple(slices))

    def split(self) -> Iterable[str]:
        """Split the highlighted string into parts.

        >>> list(HighlightedString('abcd', [slice(1, 3)]))
        ['a', 'bc', 'd']

        Yields:
            str: The parts. Parts with even indexes are highlighted,
            parts with odd indexes are not.

        """
        start = 0

        for highlight in self.highlights:
            yield self.value[start : highlight.start]
            yield self.value[highlight]
            start = highlight.stop

        yield self.value[start:]

    def apply(
        self, before: str, after: str, func: Optional[Callable[[str], str]] = None,
    ) -> str:
        """Apply before/end markers on the highlighted string.

        The opposite of :meth:`extract`.

        >>> HighlightedString('abcd', [slice(1, 3)]).apply('>', '<')
        'a>bc<d'
        >>> HighlightedString('abcd', [slice(1, 3)]).apply('>', '<', str.upper)
        'A>BC<D'

        Args:
            before (str): Highlight start marker.
            after (str): Highlight stop marker.
            func (callable((str), str) or none): If given, a function
                to apply to the string parts before adding the markers.

        Returns:
            str: The string, with highlights marked by ``before`` and ``after``.

        """

        def inner() -> Iterable[str]:
            for index, part in enumerate(self.split()):
                if index % 2 == 1:
                    yield before
                if func:
                    part = func(part)
                yield part
                if index % 2 == 1:
                    yield after

        return ''.join(inner())


@dataclass(frozen=True)
class EntrySearchResult:

    """Data type representing the result of an entry search.

    .. todo::

        Explain what .metadata and .content are keyed by.

    """

    #: The feed URL.
    feed_url: str

    #: The entry id.
    id: str

    #: Matching entry metadata, in arbitrary order.
    #: Currently entry.title and entry.feed.user_title/.title.
    metadata: Mapping[str, HighlightedString] = MappingProxyType({})

    #: Matching entry content, sorted by relevance.
    #: Content is any of entry.summary and entry.content[].value.
    content: Mapping[str, HighlightedString] = MappingProxyType({})

    @property
    def feed(self) -> str:
        """The feed URL.

        :deprecated: Use :attr:`feed_url` instead.

        """
        # TODO: remove me after 0.22
        warnings.warn(
            "EntrySearchResult.feed is deprecated and will be removed after "
            "reader 0.22. Use EntrySearchResult.feed_url instead.",
            DeprecationWarning,
        )
        return self.feed_url

    # TODO: entry: Optional[Entry]; model it through typing if possible


# Semi-public API (typing support)


# TODO: Could we use some kind of str-compatible enum here?
_FeedSortOrder = Literal['title', 'added']


# https://github.com/python/typing/issues/182
JSONValue = Union[str, int, float, bool, None, Dict[str, Any], List[Any]]
JSONType = Union[Dict[str, JSONValue], List[JSONValue]]


# Using protocols here so we have both duck typing and type checking.
# Simply catching AttributeError (e.g. on feed.url) is not enough for mypy,
# see https://github.com/python/mypy/issues/8056.


@runtime_checkable
class FeedLike(Protocol):

    # We don't use "url: str" because we don't care if url is writable.

    @property
    def url(self) -> str:  # pragma: no cover
        ...


@runtime_checkable
class EntryLike(Protocol):
    @property
    def id(self) -> str:  # pragma: no cover
        ...

    @property
    def feed_url(self) -> str:  # pragma: no cover
        ...


_FeedInput = Union[str, FeedLike]
_EntryInput = Union[Tuple[str, str], EntryLike]


def _feed_argument(feed: _FeedInput) -> str:
    if isinstance(feed, FeedLike):
        return feed.url
    if isinstance(feed, str):
        return feed
    raise ValueError(f'invalid feed argument: {feed!r}')


def _entry_argument(entry: _EntryInput) -> Tuple[str, str]:
    if isinstance(entry, EntryLike):
        return _feed_argument(entry.feed_url), entry.id
    if isinstance(entry, tuple) and len(entry) == 2:
        feed_url, entry_id = entry
        if isinstance(feed_url, str) and isinstance(entry_id, str):
            return entry
    raise ValueError(f'invalid entry argument: {entry!r}')
