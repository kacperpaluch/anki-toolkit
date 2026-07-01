"""Deck Router — pure rule matching (no Anki imports, unit-testable).

A rule is a dict:
    {"tag": "abc123", "template": "pol-ang", "deck": "Angielski::Osobne"}

`template` omitted / empty / "*" matches every card of the note (tag = own
property of a note, so all its cards share it). First matching rule wins: its
tag must be present on the note AND its template must match the card's
template name.
"""


def match_deck(tags, template_name, rules):
    """Return the target deck name for a card, or None if no rule matches.

    tags: iterable of the note's tags. template_name: the card's template name.
    """
    tagset = tags if isinstance(tags, (set, frozenset)) else set(tags)
    for rule in rules:
        tag = rule.get("tag")
        if not tag or tag not in tagset:
            continue
        tmpl = rule.get("template") or "*"
        if tmpl == "*" or tmpl == template_name:
            deck = rule.get("deck")
            if deck:
                return deck
    return None
