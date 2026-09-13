"""ai_senses — jedno hasło ze słowników → po jednej notatce na każde znaczenie.

Panel trzyma już otwarte strony diki / Longman / Oxford w QWebEngineView, więc
tekst bierzemy z nich (`toPlainText`), a nie z kolejnego scrapera: HTML tych
stron zmienia się częściej niż nasza chęć poprawiania parserów.

Model DOPASOWUJE, nie tłumaczy — polskie znaczenia z diki do angielskich
definicji z Oxforda/Longmana/Cambridge. `en` i `example` muszą być DOSŁOWNYM
cytatem ze stron; sprawdzamy to zwykłym substringiem, więc zmyślona definicja
po prostu nie przechodzi (jest czyszczona, znaczenie dostaje `match: none`).

Brak dopasowania nie jest błędem. Znaczenie bez angielskiej definicji dalej
zasługuje na kartę EN-PL — wymuszanie 1:1 produkowałoby definicje UDAJĄCE
słownikowe, a to gorsze niż puste pole. Tagi są ROZŁĄCZNE: `exact` dostaje
`ai_tag`, wszystko poza nim `ai_review_tag` i ląduje w Browserze do
przejrzenia. Jeden tag na kartę, więc filtr `tag:ai-review` to dokładnie
robota do zrobienia, a nie podzbiór `tag:ai-auto`.

Dostawcę AI pożyczamy z dodatku Content (ten sam, który masz skonfigurowany,
łącznie z Codex/Claude CLI na subskrypcji) — nie duplikujemy klienta HTTP.
Konfiguracja: config.json → "word_queue" → klucze "ai_*".
"""

import importlib
import json
import logging
import re

try:
    from aqt import mw
    from aqt.qt import (
        QCheckBox,
        QDialog,
        QDialogButtonBox,
        QLabel,
        QScrollArea,
        QVBoxLayout,
        QWidget,
    )
except ImportError:  # pozwala odpalić self-check i testy bez Anki
    mw = None
    QCheckBox = QDialogButtonBox = QLabel = QScrollArea = QVBoxLayout = QWidget = None
    QDialog = object

log = logging.getLogger(__name__)

# Ile tekstu strony idzie do modelu. Hasło ze wszystkimi znaczeniami mieści się
# w kilku tysiącach znaków; reszta diki to menu, reklamy i "podobne słówka".
# ponytail: ucinamy od końca, bez patrzenia gdzie kończy się hasło. Gdyby
# któryś słownik wypychał treść niżej, zwiększ limit — nie pisz parsera.
MAX_PAGE_CHARS = 6000

_PROMPT = """Jesteś asystentem budującym fiszki angielsko-polskie.

Hasło: {word}

Poniżej surowy tekst stron słownikowych. Dopasuj polskie znaczenia (diki) do
angielskich definicji (Oxford / Longman / Cambridge) TEGO hasła.

Zwróć WYŁĄCZNIE JSON, bez markdown i komentarzy:
{{"senses": [{{"pl": "...", "en": "...", "example": "...", "src": "...", "match": "exact"}}]}}

Zasady:
1. Jeden obiekt = jedno odrębne znaczenie. Maksymalnie {max_senses}, w kolejności z diki.
2. "en" oraz "example" MUSZĄ być skopiowane DOSŁOWNIE z tekstu poniżej — bez
   parafrazy, skracania i tłumaczenia. Cytat, którego nie ma w tekście, odrzucam.
3. Kilka polskich odpowiedników tego samego znaczenia scal w "pl" po przecinku.
4. Brak angielskiej definicji dla znaczenia → "en": "", "example": "", "match": "none".
   Nie wymyślaj definicji i nie podpinaj cudzej.
5. "match": "exact" gdy definicja pokrywa się ze znaczeniem, "approx" gdy z grubsza.
6. "src" to nazwa słownika, z którego pochodzi "en".
7. Pomiń znaczenia dotyczące innego hasła niż {word}.

{pages}
"""


# ---------------------------------------------------------------------------
# czysta logika — bez Anki, bez sieci (self-check na dole pliku)
# ---------------------------------------------------------------------------

def build_prompt(word: str, texts: dict, max_senses: int) -> str:
    pages = "\n\n".join(
        f"=== {label} ===\n{text[:MAX_PAGE_CHARS]}"
        for label, text in texts.items() if (text or "").strip()
    )
    return _PROMPT.format(word=word, max_senses=max_senses, pages=pages)


def _flat(value) -> str:
    """Wartość z JSON-a → jedna linia tekstu. Model bywa, że zwraca listę."""
    if isinstance(value, list):
        value = ", ".join(str(item) for item in value)
    return " ".join(str(value if value is not None else "").split())


def _norm(text: str) -> str:
    """Do porównania cytatu ze stroną: bez różnic w spacjach, apostrofach i wielkości liter."""
    return " ".join(re.sub(r"[‘’ʼ]", "'", text or "").split()).casefold()


def _json_object(raw: str):
    """Wyłuskaj obiekt JSON z odpowiedzi modelu (bywa w ```json ... ```)."""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except ValueError:
        return None


def parse_senses(raw: str, page_text: str, max_senses: int = 3) -> tuple[list[dict], str | None]:
    """Odpowiedź modelu → lista znaczeń. Cytaty spoza `page_text` są kasowane."""
    data = _json_object(raw)
    if not isinstance(data, dict) or not isinstance(data.get("senses"), list):
        return [], "model nie zwrócił JSON-a ze znaczeniami"

    haystack = _norm(page_text)
    senses = []
    for item in data["senses"][:max_senses]:
        if not isinstance(item, dict):
            continue
        pl = _flat(item.get("pl"))
        if not pl:
            continue  # karta bez polskiego znaczenia nie ma czego uczyć
        en = _flat(item.get("en"))
        example = _flat(item.get("example"))
        if en and _norm(en) not in haystack:
            log.info("ai_senses: odrzucony cytat (brak w słowniku): %r", en)
            en = example = ""
        if example and _norm(example) not in haystack:
            example = ""
        match = _flat(item.get("match")).lower()
        if not en:
            match = "none"
        elif match not in ("exact", "approx"):
            match = "approx"  # nieznana etykieta → traktuj jak niepewne, nie jak pewne
        senses.append({"pl": pl, "en": en, "example": example,
                       "src": _flat(item.get("src")), "match": match})

    if not senses:
        return [], "model nie znalazł żadnego znaczenia"
    return senses, None


def parse_tags(value: str) -> list[str]:
    """Pole tekstowe → lista tagów. Rozdziela spacja i przecinek, jak w Anki
    (tag ze spacją w środku i tak rozpadłby się na dwa przy zapisie)."""
    return [tag for tag in re.split(r"[\s,]+", (value or "").strip()) if tag]


def note_fields(sense: dict, mapping: dict, word: str) -> dict:
    """Znaczenie → {pole notatki: wartość}. Puste wartości nie trafiają do notatki."""
    values = {
        mapping.get("en"): word,
        mapping.get("pl"): sense.get("pl", ""),
        mapping.get("definition"): sense.get("en", ""),
        mapping.get("example"): sense.get("example", ""),
    }
    return {field: value for field, value in values.items() if field and value}


# ---------------------------------------------------------------------------
# dostawca AI — pożyczony z dodatku Content
# ---------------------------------------------------------------------------

def providers_module() -> tuple[object, str]:
    """(moduł providers, nazwa dodatku). Z AnkiWeb folder Contentu bywa numerem."""
    names = ["anki_toolkit_content"]
    if mw is not None:
        names += [name for name in mw.addonManager.allAddons() if name not in names]
    for name in names:
        try:
            return importlib.import_module(f"{name}.ai_generator.providers"), name
        except ImportError:
            continue
    return None, ""


def _provider(cfg: dict):
    providers, addon = providers_module()
    if providers is None:
        return None, "brak dodatku Anki Toolkit: Content (to on trzyma dostawców AI)"
    name = (cfg.get("ai_provider") or "").strip()
    if not name:
        return None, "wybierz dostawcę AI w Ustawieniach (np. claude_cli)"
    generator = (mw.addonManager.getConfig(addon) or {}).get("ai_generator", {})
    provider_cfg = dict((generator.get("providers") or {}).get(name) or {})
    if not provider_cfg:
        return None, f"dostawca „{name}” nie jest skonfigurowany w dodatku Content"
    if cfg.get("ai_model"):
        provider_cfg["model"] = cfg["ai_model"]
    try:
        return providers.get_provider(name, provider_cfg, timeout=cfg.get("ai_timeout", 120)), None
    except Exception as error:  # noqa: BLE001 — zły provider w configu to komunikat, nie crash
        return None, str(error)


def generate(word: str, texts: dict, cfg: dict) -> tuple[list[dict], str | None]:
    """Wątek roboczy: strony → model → zweryfikowane znaczenia."""
    provider, error = _provider(cfg)
    if error:
        return [], error
    raw = provider.call_api(build_prompt(word, texts, cfg.get("ai_max_senses", 3)))
    if not raw:
        return [], provider.last_error or "brak odpowiedzi modelu"
    return parse_senses(raw, "\n".join(texts.values()), cfg.get("ai_max_senses", 3))


# ---------------------------------------------------------------------------
# wybór znaczeń i zapis notatek — wątek główny
# ---------------------------------------------------------------------------

class SensePicker(QDialog):
    """Podgląd przed zapisem: co pójdzie na karty i co model dopasował na siłę."""

    _MATCH = {"exact": "✓ dopasowane", "approx": "≈ przybliżone", "none": "✗ bez definicji"}

    def __init__(self, senses: list[dict], word: str, parent):
        super().__init__(parent)
        self.setWindowTitle(f"AI: znaczenia „{word}”")
        self.resize(720, 460)
        self._boxes = []

        layout = QVBoxLayout(self)
        hint = QLabel("Jedno znaczenie = jedna karta. Definicje są dosłownymi cytatami ze "
                      "słownika; „przybliżone” i „bez definicji” dostaną tag do przejrzenia.")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        for sense in senses:
            box = QCheckBox(self._describe(sense))
            box.setChecked(True)
            self._boxes.append((box, sense))
            inner_layout.addWidget(box)
        inner_layout.addStretch()
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setWidget(inner)
        layout.addWidget(area)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @classmethod
    def _describe(cls, sense: dict) -> str:
        lines = [f"{sense['pl']}   [{cls._MATCH.get(sense['match'], sense['match'])}]"]
        if sense["en"]:
            lines.append(sense["en"] + (f"   ({sense['src']})" if sense["src"] else ""))
        if sense["example"]:
            lines.append(f"„{sense['example']}”")
        return "\n".join(lines)

    def selected(self) -> list[dict]:
        return [sense for box, sense in self._boxes if box.isChecked()]


def pick_senses(senses: list[dict], word: str, parent) -> list[dict]:
    dialog = SensePicker(senses, word, parent)
    return dialog.selected() if dialog.exec() else []


def add_notes(addcards, word: str, senses: list[dict], cfg: dict) -> tuple[int, str | None]:
    """Po jednej notatce na znaczenie, w talii i typie wybranym w oknie „Dodaj"."""
    notetype = addcards.editor.note.note_type()
    chooser = addcards.deck_chooser
    deck_id = getattr(chooser, "selected_deck_id", None) or chooser.selectedId()
    # Pole angielskie bierzemy z `word_field` — panel wpisuje tam hasło, więc
    # druga kopia tej nazwy w `ai_fields` mogłaby się z nim rozjechać.
    mapping = dict(cfg.get("ai_fields") or {}, en=cfg.get("word_field", "ang"))

    # Sprawdzamy PRZED pętlą: inaczej zła mapa pól zostawia połowę kart dodanych.
    known = {field["name"] for field in notetype["flds"]}
    unknown = sorted({name for sense in senses for name in note_fields(sense, mapping, word)} - known)
    if unknown:
        return 0, f"typ notatki nie ma pól: {', '.join(unknown)} — popraw ai_fields w config.json"

    exact = parse_tags(cfg.get("ai_tag"))            # tylko pewne dopasowanie
    review = parse_tags(cfg.get("ai_review_tag"))    # tylko niepewne dopasowanie
    added = 0
    for sense in senses:
        note = mw.col.new_note(notetype)
        for field, value in note_fields(sense, mapping, word).items():
            note[field] = value
        note.tags.extend(exact if sense["match"] == "exact" else review)
        mw.col.add_note(note, deck_id)
        added += 1
    return added, None


if __name__ == "__main__":  # self-check czystej logiki (bez Anki i bez sieci)
    page = ("=== diki ===\nrozległy, rozciągnięty\n"
            "=== Oxford ===\ncovering a large area\n"
            "a sprawling city on the edge of the desert")

    ok, error = parse_senses(
        '{"senses":[{"pl":["rozległy","rozciągnięty"],"en":"covering a large area",'
        '"example":"a sprawling city","src":"Oxford","match":"exact"}]}', page)
    assert error is None
    assert ok == [{"pl": "rozległy, rozciągnięty", "en": "covering a large area",
                   "example": "a sprawling city", "src": "Oxford", "match": "exact"}], ok

    # zmyślona definicja nie przechodzi — zostaje karta EN-PL do przejrzenia
    faked, error = parse_senses(
        '{"senses":[{"pl":"rozległy","en":"extending over a big region",'
        '"example":"a sprawling city","match":"exact"}]}', page)
    assert error is None
    assert faked[0]["en"] == "" and faked[0]["example"] == "" and faked[0]["match"] == "none", faked

    # sam przykład zmyślony → definicja zostaje, przykład leci
    partial, _ = parse_senses(
        '{"senses":[{"pl":"rozległy","en":"covering a large area",'
        '"example":"a sprawling meadow","match":"exact"}]}', page)
    assert partial[0]["en"] and partial[0]["example"] == "", partial

    # cytat różniący się tylko spacjami/apostrofem to wciąż cytat
    spaced, _ = parse_senses(
        '{"senses":[{"pl":"rozległy","en":"Covering  a   large area","match":"exact"}]}', page)
    assert spaced[0]["en"] == "Covering a large area", spaced

    # kilka znaczeń: kolejność zachowana, limit przycina
    many = json.dumps({"senses": [{"pl": f"z{i}", "en": "", "match": "none"} for i in range(5)]})
    capped, _ = parse_senses(many, page, max_senses=3)
    assert [s["pl"] for s in capped] == ["z0", "z1", "z2"], capped
    assert all(s["match"] == "none" for s in capped)

    # nieznana etykieta match traktowana jako niepewna, nie jako pewna
    fuzzy, _ = parse_senses(
        '{"senses":[{"pl":"rozległy","en":"covering a large area","match":"świetne"}]}', page)
    assert fuzzy[0]["match"] == "approx", fuzzy

    # znaczenie bez "pl" nie ma czego uczyć
    empty, error = parse_senses('{"senses":[{"pl":"","en":"covering a large area"}]}', page)
    assert empty == [] and error is not None

    # model owinął JSON w markdown
    fenced, error = parse_senses(
        '```json\n{"senses":[{"pl":"rozległy","en":"","match":"none"}]}\n```', page)
    assert error is None and fenced[0]["pl"] == "rozległy"

    assert parse_senses("przepraszam, nie wiem", page)[0] == []
    assert parse_senses("", page)[1] is not None

    assert parse_tags(" ai-auto,  nowe ") == ["ai-auto", "nowe"]
    assert parse_tags("") == [] and parse_tags(None) == []

    fields = note_fields(ok[0], {"en": "ang", "pl": "pol", "definition": "def",
                                 "example": "przyklad"}, "sprawling")
    assert fields == {"ang": "sprawling", "pol": "rozległy, rozciągnięty",
                      "def": "covering a large area", "przyklad": "a sprawling city"}, fields
    # puste pola nie nadpisują niczego, brak mapowania nie wysadza zapisu
    assert note_fields(faked[0], {"en": "ang", "pl": "pol"}, "x") == {"ang": "x", "pol": "rozległy"}

    prompt = build_prompt("sprawling", {"diki": "x" * 9000, "pusta": "  "}, 3)
    assert "sprawling" in prompt and "=== diki ===" in prompt and "pusta" not in prompt
    assert len(prompt) < 9000, "strona musi być przycięta do MAX_PAGE_CHARS"

    print("ai_senses self-check OK")
