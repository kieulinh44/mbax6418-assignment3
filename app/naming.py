"""Collection-wide naming checks and process-local pending-name reservations."""
from __future__ import annotations

from collections import Counter, deque
from difflib import SequenceMatcher
import random
import re
import threading
import unicodedata
from typing import Callable

from . import library

_STOP_WORDS = frozenset('a an the and or of in on at to for from with by my your our i you we it is are'.split())

TITLE_FORMS = (
    'one concrete, evocative word from the story (1 word)',
    'a natural conversational fragment, not a poetic adjective-noun pair (3-7 words)',
    'a short unanswered question (2-6 words)',
    'a verb-led instruction or invitation (2-5 words)',
    'a precise everyday detail involving an object, time or place (2-6 words)',
    'an unexpected pairing of two concrete nouns (2 words)',
    'an understated, plainspoken full sentence (4-8 words)',
    'a small physical action with emotional significance (2-4 words)',
)
ARTIST_FORMS = (
    'a fictional solo performer with an invented given name and surname (2 words)',
    'a pronounceable invented mononym with no obvious genre buzzwords (1 word)',
    'a playful band name built around an unexpected everyday detail (2-4 words)',
    'a duo of two different invented surnames (2-3 words)',
    'a compact band name inspired by an invented place (1-3 words)',
    'a short, concrete plural-noun band identity, not a mood label (1-2 words)',
    'an invented stage alias using an initial and an unusual surname (2 words)',
    'an unusual literal phrase as a band identity, without an adjective opening (3-5 words)',
)


def _words(value: str) -> list[str]:
    value = unicodedata.normalize('NFKD', str(value).casefold())
    value = ''.join(c for c in value if not unicodedata.combining(c))
    words = re.findall(r'[^\W_]+', value)
    if any(not word.isdigit() for word in words):
        words = [word for word in words if not word.isdigit()]
    return [word for word in words if word not in _STOP_WORDS]


def _stem(word: str) -> str:
    if word.endswith('echoes'):
        return word[:-2]
    if len(word) > 4 and word.endswith('ies'):
        return word[:-3] + 'y'
    if len(word) > 5 and word.endswith('ed'):
        return word[:-2]
    if len(word) > 4 and word.endswith('s') and not word.endswith(('ss', 'us')):
        return word[:-1]
    return word


def _key(value: str) -> str:
    return ''.join(_stem(word) for word in _words(value))


def _similar(first: str, second: str) -> bool:
    a, b = _key(first), _key(second)
    if not a or not b:
        return False
    if a == b:
        return True
    if min(len(a), len(b)) >= 6 and SequenceMatcher(None, a, b).ratio() >= .86:
        return True
    left, right = { _stem(w) for w in _words(first) }, { _stem(w) for w in _words(second) }
    overlap = left & right
    return len(overlap) >= 2 and len(overlap) / len(left | right) >= .6


def _overused(records: list[dict]) -> list[str]:
    counts = Counter(word for track in records for field in ('title', 'artist')
                     for word in {_stem(w) for w in _words(track.get(field, ''))}
                     if not word.isdigit())
    return [word for word, count in counts.most_common() if count >= 2]


def _signature_words(value: str) -> set[str]:
    grammar = set('be been was were if as not no so but do does did can could would should who what when where why how me us them their his her its than then into out up down off still just let'.split())
    return {_stem(w) for w in _words(value)
            if len(w) >= 3 and not w.isdigit() and w not in grammar}


def _artist_avoid_words(records: list[dict]) -> set[str]:
    return {word for record in records for field in ('title', 'artist')
            for word in _signature_words(record.get(field, ''))}


class NamingDirector:
    """Keep saved and not-yet-saved names from repeating across all genres.

    Saved names are read on every attempt, so a restart still considers the
    collection. Accepted specs are reserved under a lock before audio generation,
    covering tracks in one set and simultaneous requests in this process.
    """

    def __init__(self, history: Callable[[], list[dict]] | None = None,
                 rng: random.Random | None = None):
        self._history = history if history is not None else lambda: library.list_tracks()
        self._rng = rng if rng is not None else random.SystemRandom()
        self._lock = threading.Lock()
        self._accepted: deque[dict] = deque(maxlen=200)
        self._bags: dict[str, list[str]] = {}
        self._last: dict[str, str] = {}

    def _records(self, saved: list[dict]) -> list[dict]:
        # Saved and in-flight copies of the same spec must not count twice.
        records = {}
        for track in list(reversed(saved)) + list(self._accepted):
            pair = (_key(track.get('title', '')), _key(track.get('artist', '')))
            records[pair] = track
        return list(records.values())

    def brief(self) -> dict:
        saved = self._history()
        with self._lock:
            records = self._records(saved)
            brief = {}
            for field, pool in (('title_form', TITLE_FORMS), ('artist_form', ARTIST_FORMS)):
                bag = self._bags.setdefault(field, [])
                if not bag:
                    bag.extend(pool)
                    self._rng.shuffle(bag)
                    if bag[-1] == self._last.get(field):
                        bag[-1], bag[0] = bag[0], bag[-1]
                brief[field] = bag.pop()
                self._last[field] = brief[field]
            brief['recent_titles'] = [r.get('title', '') for r in records[-40:]]
            brief['recent_artists'] = [r.get('artist', '') for r in records[-40:]]
            brief['overused_words'] = _overused(records)[:30]
            brief['artist_words_to_avoid'] = sorted(_artist_avoid_words(records))[:100]
            return brief

    def reserve(self, track: dict, theme: str = '') -> list[str]:
        saved = self._history()
        with self._lock:
            records = self._records(saved)
            reasons = []
            if _similar(track.get('title', ''), track.get('artist', '')):
                reasons.append('artist identity is too close to this song title')
            repeated = set(_overused(records))
            artist_words = _artist_avoid_words(records)
            requested = {_stem(w) for w in _words(theme)}
            for field in ('title', 'artist'):
                value = str(track.get(field) or '').strip()
                if not _key(value) or _key(value) in ('untitled', 'aijukebox', 'unknown'):
                    reasons.append(f'{field} needs an original name, not a placeholder')
                    continue
                for old in records:
                    previous = old.get(field, '')
                    if _similar(value, previous):
                        reasons.append(f'{field} is too close to an existing name: {previous!r}')
                        break
                worn_words = {_stem(w) for w in _words(value)} & repeated
                if field == 'title':
                    worn_words -= requested
                if worn_words:
                    reasons.append(f'{field} reuses overworked vocabulary: {", ".join(sorted(worn_words))}')
                if field == 'artist':
                    reused = _signature_words(value) & artist_words
                    if reused:
                        reasons.append(f'artist recycles signature words from another name: {", ".join(sorted(reused))}')
            if not reasons:
                self._accepted.append({field: str(track[field]) for field in ('title', 'artist')})
            return reasons


director = NamingDirector()
