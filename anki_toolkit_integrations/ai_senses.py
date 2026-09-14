"""ai_senses — jedno hasło ze słowników → po jednej notatce na każde znaczenie.

Panel trzyma już otwarte strony diki / Longman / Oxford w QWebEngineView, więc
tekst bierzemy z nich (`toPlainText`), a nie z kolejnego scrapera: HTML tych
stron zmienia się częściej niż nasza chęć poprawiania parserów.

Model DOPASOWUJE, nie tłumaczy — polskie znaczenia z diki do angielskich
definicji z Oxforda/Longmana/Cambridge. `en` i `example` muszą być DOSŁOWNYM
cytatem ze wskazanego źródła. Polskie odpowiedniki sprawdzamy w diki.
Substring sprawdza pochodzenie tekstu, nie poprawność dopasowania znaczeń.

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

from html import escape
import importlib
import json
import logging
import re
from urllib.parse import urlsplit

try:
    from aqt import mw
    from aqt.qt import (
        QCheckBox,
        QDialog,
        QDialogButtonBox,
        QFormLayout,
        QPlainTextEdit,
        QLabel,
        QScrollArea,
        QVBoxLayout,
        QWidget,
    )
except ImportError:  # pozwala odpalić testy bez Anki
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
6. "src" to dokładna etykieta angielskiego słownika, z którego pochodzą "en" i "example".
   Każdy polski odpowiednik w "pl" musi być cytatem z diki.
7. Pomiń znaczenia dotyczące innego hasła niż {word}.

{pages}
"""


# ---------------------------------------------------------------------------
# czysta logika — bez Anki, bez sieci
# ---------------------------------------------------------------------------

def build_prompt(word: str, texts: dict, max_senses: int, include_example: bool = True) -> str:
    pages = "\n\n".join(
        f"=== {label} ===\n{text[:MAX_PAGE_CHARS]}"
        for label, text in texts.items() if (text or "").strip()
    )
    prompt = _PROMPT.format(word=word, max_senses=max_senses, pages=pages)
    if not include_example:
        prompt += '\nPole przykładu jest wyłączone. Nie wybieraj ani nie generuj przykładów; zwróć "example": "".'
    return prompt


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


def parse_senses(raw: str, texts: dict, max_senses: int = 3) -> tuple[list[dict], str | None]:
    """Odpowiedź modelu → lista znaczeń. Cytaty są sprawdzane w zadeklarowanym źródle."""
    data = _json_object(raw)
    if not isinstance(data, dict) or not isinstance(data.get("senses"), list):
        return [], "model nie zwrócił JSON-a ze znaczeniami"

    sources = {_norm(label): _norm(text[:MAX_PAGE_CHARS]) for label, text in texts.items()}
    polish = sources.get("diki", "")
    senses = []
    for item in data["senses"][:max_senses]:
        if not isinstance(item, dict):
            continue
        pl = _flat(item.get("pl"))
        if not pl or any(not _norm(part) or _norm(part) not in polish
                         for part in re.split(r"[,;]", pl)):
            continue  # karta bez polskiego znaczenia nie ma czego uczyć
        src = _flat(item.get("src"))
        haystack = sources.get(_norm(src), "") if _norm(src) != "diki" else ""
        en = _flat(item.get("en"))
        example = _flat(item.get("example"))
        if en and _norm(en) not in haystack:
            log.info("ai_senses: odrzucony cytat (brak w słowniku): %r", en)
            en = example = ""
        if example and _norm(example) not in haystack:
            example = ""
        match = _flat(item.get("match")).lower()
        if not en:
            example = src = ""
            match = "none"
        elif match not in ("exact", "approx"):
            match = "approx"  # nieznana etykieta → traktuj jak niepewne, nie jak pewne
        senses.append({"pl": pl, "en": en, "example": example,
                       "src": src, "match": match})

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
    return {field: escape(value) for field, value in values.items() if field and value}


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
    include_example = bool((cfg.get("ai_fields") or {}).get("example", "").strip())
    raw = provider.call_api(build_prompt(word, texts, cfg.get("ai_max_senses", 3), include_example))
    if not raw:
        return [], provider.last_error or "brak odpowiedzi modelu"
    senses, error = parse_senses(raw, texts, cfg.get("ai_max_senses", 3))
    if not include_example:
        for sense in senses:
            sense["example"] = ""
    return senses, error


# ---------------------------------------------------------------------------
# wybór znaczeń i zapis notatek — wątek główny
# ---------------------------------------------------------------------------

def edited_sense(original: dict, values: dict) -> dict:
    result = {**original, **{key: values[key].strip() for key in ("pl", "en", "example")}}
    if not result["pl"]:
        raise ValueError("Polskie znaczenie jest wymagane")
    if any(result[key] != original.get(key, "") for key in ("pl", "en", "example")):
        result["match"] = "approx" if result["en"] else "none"
    return result


def source_links(sense: dict, urls: dict) -> str:
    links = []
    labels = {"diki", _norm(sense.get("src", ""))}
    for label, url in urls.items():
        if _norm(label) not in labels or not url:
            continue
        try:
            parsed = urlsplit(url)
        except ValueError:
            continue
        if parsed.scheme not in ("https", "http") or not parsed.hostname:
            continue
        links.append(f'<a href="{escape(url, quote=True)}">{escape(label)}</a>')
    return "Źródło: " + " · ".join(links) if links else ""


class SensePicker(QDialog):
    """Podgląd przed zapisem: co pójdzie na karty i co model dopasował na siłę."""

    _MATCH = {"exact": "✓ dopasowane", "approx": "≈ przybliżone", "none": "✗ bez definicji"}

    def __init__(self, senses: list[dict], word: str, parent, urls=None, include_example=True):
        super().__init__(parent)
        self.setWindowTitle(f"AI: znaczenia „{word}”")
        self.resize(720, 640)
        self._boxes = []

        layout = QVBoxLayout(self)
        hint = QLabel("Wybierz znaczenia i popraw treść przed zapisem. Polskie znaczenie jest wymagane. "
                      "Ręczne poprawki nie są ponownie sprawdzane jako cytaty i dostają tag do weryfikacji.")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        for index, sense in enumerate(senses, 1):
            box = QCheckBox(f"{index}. Dodaj znaczenie — {self._MATCH.get(sense['match'], sense['match'])}")
            box.setChecked(True)
            inner_layout.addWidget(box)
            form = QFormLayout()
            fields = {}
            for key, label in (("pl", "Polskie znaczenie"), ("en", "Definicja angielska"),
                               ("example", "Przykład")):
                if key == "example" and not include_example:
                    continue
                edit = QPlainTextEdit()
                edit.setPlainText(sense.get(key, ""))
                edit.setFixedHeight(64)
                form.addRow(label, edit)
                fields[key] = edit
            inner_layout.addLayout(form)
            links = source_links(sense, urls or {})
            if links:
                source = QLabel(links)
                source.setOpenExternalLinks(True)
                source.setWordWrap(True)
                inner_layout.addWidget(source)
            self._boxes.append((box, sense, fields))
        inner_layout.addStretch()
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setWidget(inner)
        layout.addWidget(area)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._error = QLabel()
        self._error.setWordWrap(True)
        layout.addWidget(self._error)
        buttons.accepted.connect(self._accept_selected)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept_selected(self):
        if any(box.isChecked() and not fields["pl"].toPlainText().strip()
               for box, _, fields in self._boxes):
            self._error.setText("Uzupełnij polskie znaczenie lub odznacz tę propozycję.")
            return
        self.accept()

    def selected(self) -> list[dict]:
        return [edited_sense(sense, {"example": "", **{key: edit.toPlainText() for key, edit in fields.items()}})
                for box, sense, fields in self._boxes if box.isChecked()]


def pick_senses(senses: list[dict], word: str, parent, urls=None, include_example=True) -> list[dict]:
    dialog = SensePicker(senses, word, parent, urls, include_example)
    return dialog.selected() if dialog.exec() else []


def add_notes(addcards, word: str, senses: list[dict], cfg: dict) -> tuple[int, object]:
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
    from anki.collection import AddNoteRequest

    requests = []
    for sense in senses:
        note = mw.col.new_note(notetype)
        for field, value in note_fields(sense, mapping, word).items():
            note[field] = value
        note.tags.extend(exact if sense["match"] == "exact" else review)
        requests.append(AddNoteRequest(note=note, deck_id=deck_id))
    # One backend transaction and one undo step; collection access stays on the main thread.
    changes = mw.col.add_notes(requests)
    return len(requests), changes
