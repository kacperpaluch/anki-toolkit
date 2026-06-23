"""Dynamic sibling suspension — core logic.

After a card is answered:
- Immature (interval < threshold): suspend all other NEW siblings.
- Mature (interval >= threshold): release ALL suspended NEW siblings.

Unlike SibPush which pre-suspends by card order, this is reactive: only
acts after the user answers a card. Whichever card Anki shows first
becomes the active one; the rest are suspended until it matures.

When the active card matures, all siblings are released at once — Anki
then picks the next one to show (more random than fixed template order),
and after the user answers it, the rest are suspended again.

If a mature card is forgotten (interval drops below threshold), any
still-NEW siblings get re-suspended. Cards already in learning or review
are never touched — only CARD_TYPE_NEW siblings are managed.

process_note_sync is the batch variant for sync catch-up: it doesn't
know which card was answered, so it checks ALL non-NEW cards — if any
is immature, suspend; if all are mature, release.
"""

from anki.cards import CARD_TYPE_NEW, QUEUE_TYPE_SUSPENDED


def process_note(col, note_id, answered_card_id, threshold, tag, ignore_tag=None):
    """Manage siblings of *note_id* after *answered_card_id* was answered.

    Reactive path — called from reviewer_did_answer_card hook on desktop.
    """
    note = col.get_note(note_id)
    if ignore_tag and note.has_tag(ignore_tag):
        return

    card_ids = col.card_ids_of_note(note_id)
    if len(card_ids) <= 1:
        return

    siblings = [col.get_card(cid) for cid in card_ids]
    answered = next((s for s in siblings if s.id == answered_card_id), None)
    if answered is None:
        return

    others = [s for s in siblings if s.id != answered_card_id]
    new_available = [s for s in others
                     if s.type == CARD_TYPE_NEW and s.queue != QUEUE_TYPE_SUSPENDED]
    new_suspended = [s for s in others
                     if s.type == CARD_TYPE_NEW and s.queue == QUEUE_TYPE_SUSPENDED]

    changed = False

    if answered.ivl < threshold:
        if new_available:
            if not note.has_tag(tag):
                note.add_tag(tag)
                col.update_note(note)
            col.sched.suspend_cards([s.id for s in new_available])
            changed = True
    else:
        if new_suspended:
            col.sched.unsuspend_cards([s.id for s in new_suspended])
            changed = True

    _cleanup_tag(col, note, card_ids, tag, changed)


def process_note_sync(col, note_id, threshold, tag, ignore_tag=None):
    """Batch variant for sync catch-up — no specific answered card.

    Checks ALL non-NEW siblings: if any is immature → suspend NEW siblings.
    If all non-NEW are mature → release suspended NEW siblings.
    If all cards are NEW (no reviews yet) → do nothing.
    """
    note = col.get_note(note_id)
    if ignore_tag and note.has_tag(ignore_tag):
        return

    card_ids = col.card_ids_of_note(note_id)
    if len(card_ids) <= 1:
        return

    siblings = [col.get_card(cid) for cid in card_ids]
    new_cards = [s for s in siblings if s.type == CARD_TYPE_NEW]
    non_new = [s for s in siblings if s.type != CARD_TYPE_NEW]

    # No NEW cards — nothing to manage, but clean up stale tag
    if not new_cards:
        if note.has_tag(tag):
            suspended = [s for s in siblings if s.queue == QUEUE_TYPE_SUSPENDED]
            if not suspended:
                note.remove_tag(tag)
                col.update_note(note)
        return

    new_available = [s for s in new_cards if s.queue != QUEUE_TYPE_SUSPENDED]
    new_suspended = [s for s in new_cards if s.queue == QUEUE_TYPE_SUSPENDED]

    changed = False

    if non_new:
        has_immature = any(s.ivl < threshold for s in non_new)
        if has_immature:
            if new_available:
                if not note.has_tag(tag):
                    note.add_tag(tag)
                    col.update_note(note)
                col.sched.suspend_cards([s.id for s in new_available])
                changed = True
        else:
            if new_suspended:
                col.sched.unsuspend_cards([s.id for s in new_suspended])
                changed = True

    _cleanup_tag(col, note, card_ids, tag, changed)


def _cleanup_tag(col, note, card_ids, tag, changed):
    """Remove the suspension tag if no cards are still suspended."""
    if not changed:
        return
    fresh = [col.get_card(cid) for cid in card_ids]
    if not any(c.queue == QUEUE_TYPE_SUSPENDED for c in fresh):
        if note.has_tag(tag):
            note.remove_tag(tag)
            col.update_note(note)
