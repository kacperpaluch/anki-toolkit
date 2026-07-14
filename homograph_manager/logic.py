"""Homograph suspension — core logic.

Sibling Manager groups cards of ONE note (ang-pol <-> pol-ang). This module
groups DIFFERENT notes that share the same word in a key field (default
``ang``) — e.g. four separate "assault" notes (napaść / atak wojskowy /
atak-krytyka / napadać). Anki's built-in "bury siblings" and the Sibling
Manager both miss these, because they are separate notes.

Goal: never study two meanings of the same word at once. Exactly ONE meaning
is "active" (its NEW cards available); every other meaning's NEW cards stay
suspended until the active meaning matures (any card ivl >= threshold). Then
exactly ONE next meaning is released — not all at once, otherwise several
fronts would become available and interfere again.

This is orthogonal to Sibling Manager: it only ever touches NEW cards of the
OTHER notes in the group, never the answered note's own cards. Together:
Sibling Manager staggers the two sides of one meaning; Homograph Manager
staggers the meanings.

process_reactive: after a card is answered (desktop reviewer hook).
process_group_sync: batch reconstruction of the invariant after phone reviews.
"""

from anki.cards import CARD_TYPE_NEW, QUEUE_TYPE_SUSPENDED


def note_key(note, field):
    """Normalized group key from *note*'s *field* (trim + lowercase), or None."""
    if field not in note.keys():
        return None
    value = note[field].strip().lower()
    return value or None


def _esc(value):
    """Escape a field value for an exact Anki `field:value` search."""
    for ch in ("\\", '"', "*", "_"):
        value = value.replace(ch, "\\" + ch)
    return value


def group_nids(col, field, key, exclude_nid=None):
    """Note IDs whose *field* equals *key* exactly (confirmed in Python)."""
    found = col.find_notes('"%s:%s"' % (field, _esc(key)))
    out = []
    for nid in found:
        if nid == exclude_nid:
            continue
        if note_key(col.get_note(nid), field) == key:
            out.append(nid)
    return out


def _cards(col, nid):
    return [col.get_card(cid) for cid in col.card_ids_of_note(nid)]


def _is_matured(cards, threshold):
    # NEW/learning cards have ivl 0, so a plain ivl check can't false-positive.
    return any(c.ivl >= threshold for c in cards)


def _is_learning(cards, threshold):
    return any(c.type != CARD_TYPE_NEW and c.ivl < threshold for c in cards)


def _new_cards(cards, suspended):
    q = QUEUE_TYPE_SUSPENDED
    return [c for c in cards
            if c.type == CARD_TYPE_NEW and (c.queue == q) == suspended]


def _set_tag(col, note, tag, want):
    """Ensure *note* has (want=True) or lacks (want=False) *tag*; return changed."""
    if want and not note.has_tag(tag):
        note.add_tag(tag)
        col.update_note(note)
        return True
    if not want and note.has_tag(tag):
        note.remove_tag(tag)
        col.update_note(note)
        return True
    return False


# ---------------------------------------------------------------------------
# Reactive path — reviewer_did_answer_card hook
# ---------------------------------------------------------------------------

def process_reactive(col, note_id, answered_card_id, threshold, tag,
                     field="ang", ignore_tag=None):
    """After answering a card of *note_id*, manage the other meanings.

    Immature answered card -> suspend NEW cards of every other meaning.
    Matured answered card  -> release exactly one next meaning.
    Returns (suspended, unsuspended) counts.
    """
    note = col.get_note(note_id)
    if ignore_tag and note.has_tag(ignore_tag):
        return 0, 0
    key = note_key(note, field)
    if not key:
        return 0, 0
    others = group_nids(col, field, key, exclude_nid=note_id)
    if not others:
        return 0, 0

    answered = col.get_card(answered_card_id)
    if answered.ivl < threshold:
        return _suspend_others(col, others, tag, ignore_tag), 0
    return 0, _release_one(col, others, threshold, tag, ignore_tag)


def _suspend_others(col, nids, tag, ignore_tag):
    to_suspend = []
    for nid in nids:
        note = col.get_note(nid)
        if ignore_tag and note.has_tag(ignore_tag):
            continue
        available = _new_cards(_cards(col, nid), suspended=False)
        if available:
            to_suspend += [c.id for c in available]
            _set_tag(col, note, tag, True)
    if to_suspend:
        col.sched.suspend_cards(to_suspend)
    return len(to_suspend)


def _release_one(col, nids, threshold, tag, ignore_tag):
    """Unsuspend NEW cards of exactly one waiting meaning — unless a meaning
    is already occupying the active slot (learning, or has available NEW cards).
    """
    candidates = []
    for nid in nids:
        note = col.get_note(nid)
        if ignore_tag and note.has_tag(ignore_tag):
            continue
        cards = _cards(col, nid)
        if _is_learning(cards, threshold) or _new_cards(cards, suspended=False):
            return 0  # a meaning already occupies the active slot
        if _is_matured(cards, threshold):
            continue  # already done
        suspended = _new_cards(cards, suspended=True)
        if suspended:
            candidates.append((nid, [c.id for c in suspended]))
    if not candidates:
        return 0
    candidates.sort()  # deterministic: smallest nid next
    nid, card_ids = candidates[0]
    col.sched.unsuspend_cards(card_ids)
    _set_tag(col, col.get_note(nid), tag, False)
    return len(card_ids)


# ---------------------------------------------------------------------------
# Batch path — sync catch-up (no specific answered card)
# ---------------------------------------------------------------------------

def process_group_sync(col, nids, threshold, tag, field="ang", ignore_tag=None):
    """Reconstruct the invariant for a full group: at most one non-matured
    meaning is active (NEW cards unsuspended); the rest suspended.

    Active meaning = one currently learning, else the smallest-nid remaining.
    Returns (suspended, unsuspended) counts.
    """
    remaining = []  # (nid, note, cards) not matured, still has NEW cards
    for nid in nids:
        note = col.get_note(nid)
        if ignore_tag and note.has_tag(ignore_tag):
            continue
        cards = _cards(col, nid)
        if _is_matured(cards, threshold):
            _set_tag(col, note, tag, False)  # done — drop stale tag
            continue
        if any(c.type == CARD_TYPE_NEW for c in cards):
            remaining.append((nid, note, cards))

    if not remaining:
        return 0, 0

    learners = [r for r in remaining if _is_learning(r[2], threshold)]
    active_nid = (min(learners) if learners else min(remaining))[0]

    suspended = unsuspended = 0
    for nid, note, cards in remaining:
        if nid == active_nid:
            # Only release a meaning WE suspended (tagged). If the active note
            # isn't ours, its NEW cards belong to sibling_manager (it keeps one
            # side suspended until the other matures) — unsuspending them here
            # causes a suspend/unsuspend ping-pong on every sync.
            if note.has_tag(tag):
                ids = [c.id for c in _new_cards(cards, suspended=True)]
                if ids:
                    col.sched.unsuspend_cards(ids)
                    unsuspended += len(ids)
                _set_tag(col, note, tag, False)
        else:
            ids = [c.id for c in _new_cards(cards, suspended=False)]
            if ids:
                col.sched.suspend_cards(ids)
                suspended += len(ids)
                _set_tag(col, note, tag, True)
    return suspended, unsuspended
