"""Sentence unlocker — progressive gap-fill card gating (core logic).

Once the two main cards of a note mature (ivl >= threshold), unlock the
first gap-fill sentence by writing a marker into its ``-tak`` field —
which makes Anki generate that card. Each further sentence unlocks only
after the *previous* sentence's own card matures: a staggered chain.

One-way only. A marker is never removed: clearing a ``-tak`` field would
delete the already-generated card together with its review history.

Pure logic — takes an Anki ``col`` and works via its public API, so it is
unit-testable with light fakes (see tests/).
"""


def _tmpl_cards(col, note):
    """Map template-name -> Card for the note's *existing* cards.

    A gap-fill card only exists after its ``-tak`` field was set, so
    presence in this map is itself the "unlocked" signal, and the card's
    ivl is what gates the next slot.
    """
    model = col.models.get(note.mid)
    tmpls = model["tmpls"]
    out = {}
    for cid in col.card_ids_of_note(note.id):
        card = col.get_card(cid)
        out[tmpls[card.ord]["name"]] = card
    return out


def process_note(col, note_id, threshold, main_templates, chain, marker,
                 ignore_tag=None, done_tag=None):
    """Unlock the next eligible gap-fill sentence for *note_id*.

    ``main_templates`` — names of the two recognition cards that gate the
    first sentence. ``chain`` — ordered list of ``{"nauka_field", "tak_field"}``;
    a slot's own card (template name == ``nauka_field``) gates the next slot.

    Returns the number of ``-tak`` fields newly set (0 or 1 — staggered).
    """
    note = col.get_note(note_id)
    if ignore_tag and note.has_tag(ignore_tag):
        return 0

    fields = set(note.keys())
    cards = _tmpl_cards(col, note)

    def mature(tmpl_name):
        c = cards.get(tmpl_name)
        return c is not None and c.ivl >= threshold

    # Only sentences that actually have content participate in the chain.
    slots = [s for s in chain
             if s["nauka_field"] in fields and note[s["nauka_field"]].strip()
             and s["tak_field"] in fields]
    if not slots:
        return _finish(col, note, slots, 0, done_tag)

    # Gate for the first slot: both recognition cards mature.
    gate = all(mature(t) for t in main_templates)

    unlocked = 0
    for slot in slots:
        if note[slot["tak_field"]].strip():
            # already unlocked — its card's maturity gates the next slot
            gate = mature(slot["nauka_field"])
            continue
        # first not-yet-unlocked slot: unlock iff the gate holds, then stop —
        # the next slot's card does not exist yet, so it cannot be evaluated.
        if gate:
            note[slot["tak_field"]] = marker
            unlocked = 1
        break

    return _finish(col, note, slots, unlocked, done_tag)


def _finish(col, note, slots, unlocked, done_tag):
    """Persist changes and tag the note done once every slot is unlocked."""
    done = bool(slots) and all(note[s["tak_field"]].strip() for s in slots)
    # A note with no sentences is trivially "done" — tag it so batch scans skip it.
    if not slots:
        done = True
    need_tag = done and done_tag and not note.has_tag(done_tag)
    if unlocked or need_tag:
        if need_tag:
            note.add_tag(done_tag)
        col.update_note(note)
    return unlocked
