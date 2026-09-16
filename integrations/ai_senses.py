"""ai_senses — jedno hasło ze słowników → po jednej notatce na każde znaczenie.

Panel trzyma już otwarte strony słowników w QWebEngineView (diki, Cambridge
EN-PL, Oxford, LDoCE — komplet z `link_templates`), więc
tekst bierzemy z nich (`toPlainText`), a nie z kolejnego scrapera: HTML tych
stron zmienia się częściej niż nasza chęć poprawiania parserów.

Model DOPASOWUJE, nie tłumaczy — polskie znaczenia ze źródeł PL do angielskich
definicji ze źródeł EN. `en` i `example` muszą być DOSŁOWNYM cytatem ze
wskazanego w `src` źródła EN, a każdy polski odpowiednik cytatem ze źródła PL.
Substring sprawdza pochodzenie tekstu, nie poprawność dopasowania znaczeń.

Które zakładki są PL, a które EN, mówi konfiguracja (`ai_pl_sources`,
`ai_en_sources`) — Cambridge EN-PL jest na obu listach, bo ta sama strona niesie
polskie odpowiedniki i angielskie definicje.

Brak dopasowania nie jest błędem. Znaczenie bez angielskiej definicji dalej
zasługuje na kartę EN-PL — wymuszanie 1:1 produkowałoby definicje UDAJĄCE
słownikowe, a to gorsze niż puste pole. Tagi są ROZŁĄCZNE: `exact` dostaje
`ai_tag`, wszystko poza nim `ai_review_tag` i ląduje w Browserze do
przejrzenia. Jeden tag na kartę, więc filtr `tag:ai-review` to dokładnie
robota do zrobienia, a nie podzbiór `tag:ai-auto`.

Dostawcę AI bierzemy z AI Generatora (ten sam, który masz skonfigurowany,
łącznie z Codex/Claude CLI na subskrypcji) — nie duplikujemy klienta HTTP.
Konfiguracja: config.json → "word_queue" → klucze "ai_*".
"""

from html import escape
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

# Domyślne źródła PL — używane tylko wtedy, gdy konfiguracja milczy (stary
# profil bez `ai_pl_sources`). Prawdziwe listy siedzą w config.json.
_PL_SOURCES = ("diki",)

_PROMPT = """Jesteś asystentem budującym fiszki angielsko-polskie.

Hasło: {word}

Poniżej surowy tekst stron słownikowych. Dopasuj znaczenia TEGO hasła:
polskie odpowiedniki (źródła PL: {pl_sources})
do angielskich definicji (źródła EN: {en_sources}).

Zwróć WYŁĄCZNIE JSON, bez markdown i komentarzy:
{{"senses": [{{"pl": "...", "en": "...", "example": "...", "src": "...", "match": "..."}}]}}

Zasady:
1. Jeden obiekt = jedno odrębne znaczenie. Maksymalnie {max_senses}, w kolejności z {primary}.
2. "en" oraz "example" MUSZĄ być skopiowane DOSŁOWNIE z tekstu poniżej — bez
   parafrazy, skracania i tłumaczenia. Cytat, którego nie ma w tekście, odrzucam.
3. Kilka polskich odpowiedników tego samego znaczenia scal w "pl" po przecinku.
   KAŻDY fragment po przecinku sprawdzam osobno w źródle PL, więc nie dopisuj
   własnych słów, kwalifikatorów ani nawiasów — jeden dopisek unieważnia całe znaczenie.
4. Brak angielskiej definicji dla znaczenia → "en": "", "example": "", "match": "none".
   Nie wymyślaj definicji i nie podpinaj cudzej. Puste pole jest poprawnym wynikiem,
   zmyślone nie.
5. "match": "exact" TYLKO wtedy, gdy angielska definicja opisuje dokładnie to
   znaczenie, które niesie "pl". Definicja szersza, węższa albo obok — "approx".
   W razie wątpliwości "approx".
6. "src" to dokładna etykieta źródła EN, z którego pochodzą "en" i "example" —
   jedna z: {en_sources}. Każdy polski odpowiednik w "pl" musi być cytatem ze
   źródła PL ({pl_sources}).
7. To samo znaczenie opisane w kilku słownikach zwróć RAZ, z jedną definicją.
   Nie rób osobnego obiektu dla każdego słownika.
8. Bierz WYŁĄCZNIE treść hasła {word}. Poniższy tekst to surowe strony: są tam
   menu, reklamy, listy „podobne słówka", sąsiednie hasła i przykłady spoza hasła.
   Nie cytuj stamtąd niczego, nawet jeśli pasuje tematycznie.

{pages}
"""


# ---------------------------------------------------------------------------
# czysta logika — bez Anki, bez sieci
# ---------------------------------------------------------------------------

def build_prompt(word: str, texts: dict, max_senses: int, include_example: bool = True,
                 pl_sources=_PL_SOURCES, en_sources=()) -> str:
    pages = "\n\n".join(
        f"=== {label} ===\n{text[:MAX_PAGE_CHARS]}"
        for label, text in texts.items() if (text or "").strip()
    )
    # Brak listy EN w konfiguracji → wszystko, co nie jest polskie. Model i tak
    # dostaje etykiety z nagłówków stron, więc lista ma mu je tylko uporządkować.
    polish = {_norm(label) for label in pl_sources}
    en_sources = list(en_sources) or [label for label in texts if _norm(label) not in polish]
    prompt = _PROMPT.format(word=word, max_senses=max_senses, pages=pages,
                            pl_sources=", ".join(pl_sources) or "—",
                            en_sources=", ".join(en_sources) or "—",
                            primary=(list(pl_sources) or ["diki"])[0])
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


def parse_senses(raw: str, texts: dict, max_senses: int = 3,
                 pl_sources=_PL_SOURCES, en_sources=()) -> tuple[list[dict], str | None]:
    """Odpowiedź modelu → lista znaczeń. Cytaty są sprawdzane w zadeklarowanym źródle."""
    data = _json_object(raw)
    if not isinstance(data, dict) or not isinstance(data.get("senses"), list):
        return [], "model nie zwrócił JSON-a ze znaczeniami"

    sources = {_norm(label): _norm(text[:MAX_PAGE_CHARS]) for label, text in texts.items()}
    # Jeden worek na polskie cytaty: przy Cambridge EN-PL odpowiednik bywa tam,
    # a nie w diki — sprawdzamy pochodzenie tekstu, nie to, która strona wygrała.
    polish = " ".join(sources.get(_norm(label), "") for label in pl_sources)
    # Bez listy EN: wszystko poza źródłami PL, czyli zachowanie sprzed Cambridge.
    english = {_norm(label) for label in en_sources} or (
        set(sources) - {_norm(label) for label in pl_sources})
    senses = []
    for item in data["senses"][:max_senses]:
        if not isinstance(item, dict):
            continue
        pl = _flat(item.get("pl"))
        if not pl or any(not _norm(part) or _norm(part) not in polish
                         for part in re.split(r"[,;]", pl)):
            continue  # karta bez polskiego znaczenia nie ma czego uczyć
        src = _flat(item.get("src"))
        haystack = sources.get(_norm(src), "") if _norm(src) in english else ""
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
# dostawca AI — ten sam, który konfigurujesz w zakładce „AI Generator”
# ---------------------------------------------------------------------------

def _providers():
    """Import leniwy: pakiet providers ciągnie aqt, a testy logiki go nie mają."""
    from ..ai_generator import providers
    return providers


def _provider_settings(name: str) -> dict:
    from ..common import get_module_config
    return dict((get_module_config("ai_generator").get("providers") or {}).get(name) or {})


def provider_label(cfg: dict) -> str:
    """„Claude CLI · opus" — czym policzone. Kolejka ma JEDEN własny wybór
    dostawcy; modele per pole z AI Generatora dotyczą tamtego generatora."""
    name = (cfg.get("ai_provider") or "").strip()
    if not name:
        return ""
    label = getattr(_providers(), "PROVIDER_LABELS", {}).get(name, name)
    model = cfg.get("ai_model") or _provider_settings(name).get("model") or "model domyślny dostawcy"
    return f"{label} · {model}"


def prepare_provider(cfg: dict):
    """(dostawca, błąd). WYŁĄCZNIE na głównym wątku — czyta konfigurację profilu."""
    name = (cfg.get("ai_provider") or "").strip()
    if not name:
        return None, "wybierz dostawcę AI w Ustawieniach (np. claude_cli)"
    provider_cfg = _provider_settings(name)
    if not provider_cfg:
        return None, f"dostawca „{name}” nie jest skonfigurowany w zakładce AI Generator"
    if cfg.get("ai_model"):
        provider_cfg["model"] = cfg["ai_model"]
    try:
        return _providers().get_provider(name, provider_cfg, timeout=cfg.get("ai_timeout", 120)), None
    except Exception as error:  # noqa: BLE001 — zły provider w configu to komunikat, nie crash
        return None, str(error)


def generate(provider, word: str, texts: dict, cfg: dict) -> tuple[list[dict], str | None]:
    """Wątek roboczy: strony → model → zweryfikowane znaczenia.

    Dostawcę dostajemy gotowego z `prepare_provider` — w tle zostaje samo
    wywołanie modelu i obróbka tekstu, bez importów i cudzych konfiguracji.
    """
    include_example = bool((cfg.get("ai_fields") or {}).get("example", "").strip())
    pl_sources = cfg.get("ai_pl_sources") or _PL_SOURCES
    en_sources = cfg.get("ai_en_sources") or ()
    # Etykieta z konfiguracji musi pasować do etykiety zakładki, inaczej polski
    # worek jest pusty i KAŻDE znaczenie wylatuje — z komunikatem o niczym.
    if not any(_norm(label) in {_norm(tab) for tab in texts} for label in pl_sources):
        return [], (f"żadna zakładka nie pasuje do źródeł PL ({', '.join(pl_sources)}) — "
                    "popraw ai_pl_sources albo etykiety w link_templates")
    limit = cfg.get("ai_max_senses", 3)
    raw = provider.call_api(build_prompt(word, texts, limit, include_example, pl_sources, en_sources))
    if not raw:
        return [], provider.last_error or "brak odpowiedzi modelu"
    senses, error = parse_senses(raw, texts, limit, pl_sources, en_sources)
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


def source_links(sense: dict, urls: dict, pl_sources=_PL_SOURCES) -> str:
    links = []
    labels = {_norm(label) for label in pl_sources} | {_norm(sense.get("src", ""))}
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


# Wyszukiwarka Anki traktuje te znaki specjalnie także w cudzysłowie.
_SEARCH_SPECIAL = re.compile(r'([\\"*_])')


def existing_senses(word: str, cfg: dict) -> list[str]:
    """Polskie znaczenia kart, które JUŻ masz z tym hasłem.

    Notatki z `add_notes` omijają kontrolę duplikatów okna „Dodaj" (nie idą
    przez nie), więc pytamy kolekcję sami i pokazujemy wynik w SensePickerze.
    To ostrzeżenie, nie blokada: kilka znaczeń jednego hasła jest zamierzone.
    """
    field = cfg.get("word_field") or "ang"
    pl_field = (cfg.get("ai_fields") or {}).get("pl") or ""
    if not word or mw is None:
        return []
    try:
        escaped = _SEARCH_SPECIAL.sub(r"\\\1", word)
        notes = [mw.col.get_note(nid) for nid in mw.col.find_notes(f'"{field}:{escaped}"')]
    except Exception:  # noqa: BLE001 — ostrzeżenie nie może wysadzić dodawania kart
        log.exception("ai_senses: kontrola duplikatów nie powiodła się")
        return []
    return [_flat(note[pl_field]) if pl_field in note else "(bez tłumaczenia)" for note in notes]


class SensePicker(QDialog):
    """Podgląd przed zapisem: co pójdzie na karty i co model dopasował na siłę.

    Przyjmuje PACZKĘ propozycji — jedno hasło albo kilkanaście. Każda pozycja to
    `{"word", "senses", "urls", "existing"}`; hasła są sekcjami jednego okna,
    więc listę z „+ lista" zatwierdzasz raz, a nie N razy.
    """

    _MATCH = {"exact": "✓ dopasowane", "approx": "≈ przybliżone", "none": "✗ bez definicji"}

    def __init__(self, proposals: list[dict], parent, cfg=None):
        super().__init__(parent)
        cfg = cfg or {}
        include_example = bool((cfg.get("ai_fields") or {}).get("example", "").strip())
        pl_sources = cfg.get("ai_pl_sources") or _PL_SOURCES
        words = [proposal["word"] for proposal in proposals]
        self.setWindowTitle(f"AI: znaczenia „{words[0]}”" if len(words) == 1
                            else f"AI: znaczenia — {len(words)} haseł")
        self.resize(720, 700)
        self._boxes = []

        layout = QVBoxLayout(self)
        hint = QLabel("Wybierz znaczenia i popraw treść przed zapisem. Polskie znaczenie jest wymagane. "
                      "Ręczne poprawki nie są ponownie sprawdzane jako cytaty i dostają tag do weryfikacji.")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        source = provider_label(cfg)
        if source:
            who = QLabel(f"Policzone przez: {escape(source)}")
            who.setStyleSheet("color: gray;")
            layout.addWidget(who)

        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        for proposal in proposals:
            word = proposal["word"]
            if len(proposals) > 1:
                header = QLabel(f"<b>{escape(word)}</b>")
                header.setWordWrap(True)
                inner_layout.addWidget(header)
            existing = proposal.get("existing") or ()
            if existing:
                # Ostrzeżenie, nie blokada — nowe znaczenie istniejącego hasła jest OK.
                known = QLabel("⚠ Masz już {} kart(y) z hasłem „{}”: {}".format(
                    len(existing), escape(word), escape(" · ".join(filter(None, existing)))))
                known.setWordWrap(True)
                known.setStyleSheet("color: #c0392b;")
                inner_layout.addWidget(known)
            for index, sense in enumerate(proposal["senses"], 1):
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
                links = source_links(sense, proposal.get("urls") or {}, pl_sources)
                if links:
                    source = QLabel(links)
                    source.setOpenExternalLinks(True)
                    source.setWordWrap(True)
                    inner_layout.addWidget(source)
                self._boxes.append((box, word, sense, fields))
        inner_layout.addStretch()
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setWidget(inner)

        if len(self._boxes) > 1:
            self._all = QCheckBox(f"Zaznacz wszystkie ({len(self._boxes)})")
            self._all.setChecked(True)
            self._all.toggled.connect(self._toggle_all)
            layout.addWidget(self._all)
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

    def _toggle_all(self, checked: bool) -> None:
        for box, _word, _sense, _fields in self._boxes:
            box.setChecked(checked)

    def _accept_selected(self):
        if any(box.isChecked() and not fields["pl"].toPlainText().strip()
               for box, _word, _sense, fields in self._boxes):
            self._error.setText("Uzupełnij polskie znaczenie lub odznacz tę propozycję.")
            return
        self.accept()

    def selected(self) -> list[tuple[str, dict]]:
        """[(hasło, znaczenie)] — pary, bo jedno okno obsługuje kilka haseł."""
        return [(word, edited_sense(sense, {"example": "", **{key: edit.toPlainText()
                                                             for key, edit in fields.items()}}))
                for box, word, sense, fields in self._boxes if box.isChecked()]


def pick_senses(proposals: list[dict], parent, cfg=None) -> list[tuple[str, dict]]:
    dialog = SensePicker(proposals, parent, cfg)
    return dialog.selected() if dialog.exec() else []


def add_notes(addcards, chosen: list[tuple[str, dict]], cfg: dict) -> tuple[int, object]:
    """Po jednej notatce na znaczenie, w talii i typie wybranym w oknie „Dodaj".

    `chosen` to pary (hasło, znaczenie) — cała paczka, także z kilku haseł,
    idzie jedną transakcją i jednym krokiem cofania.
    """
    if not chosen:
        return 0, None  # pusty wybór nie zasługuje na wpis w historii cofania
    notetype = addcards.editor.note.note_type()
    chooser = addcards.deck_chooser
    deck_id = getattr(chooser, "selected_deck_id", None) or chooser.selectedId()
    # Pole angielskie bierzemy z `word_field` — panel wpisuje tam hasło, więc
    # druga kopia tej nazwy w `ai_fields` mogłaby się z nim rozjechać.
    mapping = dict(cfg.get("ai_fields") or {}, en=cfg.get("word_field", "ang"))

    # Sprawdzamy PRZED pętlą: inaczej zła mapa pól zostawia połowę kart dodanych.
    known = {field["name"] for field in notetype["flds"]}
    unknown = sorted({name for word, sense in chosen
                      for name in note_fields(sense, mapping, word)} - known)
    if unknown:
        return 0, f"typ notatki nie ma pól: {', '.join(unknown)} — popraw ai_fields w config.json"

    exact = parse_tags(cfg.get("ai_tag"))            # tylko pewne dopasowanie
    review = parse_tags(cfg.get("ai_review_tag"))    # tylko niepewne dopasowanie
    from anki.collection import AddNoteRequest

    requests = []
    for word, sense in chosen:
        note = mw.col.new_note(notetype)
        for field, value in note_fields(sense, mapping, word).items():
            note[field] = value
        note.tags.extend(exact if sense["match"] == "exact" else review)
        requests.append(AddNoteRequest(note=note, deck_id=deck_id))
    # One backend transaction and one undo step; collection access stays on the main thread.
    changes = mw.col.add_notes(requests)
    return len(requests), changes
