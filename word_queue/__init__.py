"""word_queue — kolejka słówek z n8n DataTable + słowniki wewnątrz Anki.

Panel (przycisk 📚 w oknie „Dodaj" albo Narzędzia → Anki Toolkit) dokleja się
do okna „Dodaj": bierze wiersz z DataTable, wpisuje słówko do pola notatki
i pokazuje diki / Longman / Oxford w zakładkach. Klikasz przyciski userscripta
(te same, co w przeglądarce — gadają z mostkiem web_bridge), Enter, i wiersz
jest odhaczany w n8n po `id`. Panel ZOSTAJE na słówku — jedno hasło bywa
kilkoma kartami; dalej idziesz sam („Zrobione →" albo klik na liście).

Bez otwartego panelu hook nadal odhacza — dopasowując `word_column` do
zawartości pola `word_field` (eq, wrażliwe na wielkość liter). To zawodzi,
gdy wpiszesz formę inną niż w tabeli (Oxford: „sprawl" vs tabela: „sprawling"),
dlatego panel patchuje po `id` i jest wersją pewną.

Notatki spoza tabeli są cicho pomijane (log) — karty dodajesz też poza kolejką.
Błąd sieci krzyczy tooltipem: cichy rozjazd Anki↔n8n wyszedłby dopiero przy
następnym przeglądzie tabeli.

Konfiguracja w config.json → "word_queue" (klucz API trzymaj w meta.json).
"""

import json
import logging
import urllib.parse

try:
    import aqt
    from aqt import mw
    from aqt.qt import QAction
    from aqt.utils import tooltip

    from ..common import clean_html_normalized, fetch_url, get_module_config, post_json
except ImportError:  # pozwala odpalić self-check (__main__) bez Anki
    aqt = mw = QAction = tooltip = None
    clean_html_normalized = fetch_url = get_module_config = post_json = None

log = logging.getLogger(__name__)

_MODULE_KEY = "word_queue"
_DEFAULTS = {
    "n8n_url": "",             # adres w sieci domowej (próbowany pierwszy)
    "fallback_url": "",        # np. Tailscale MagicDNS — gdy jesteś poza domem
    "api_key": "",
    "table_id": "",
    "word_field": "ang",       # pole notatki, do którego wpisujemy słówko
    "word_column": "Slowko",   # kolumna z hasłem
    "flag_column": "Anki",     # kolumna boolean: false = do zrobienia
    "link_columns": {          # etykieta zakładki → kolumna z URL-em (kolejność ma znaczenie)
        "diki": "URL",
        "Longman": "Longman",
        "Oxford": "Oxford",
    },
    "page_size": 250,          # maksimum, jakie przyjmuje n8n
    "max_rows": 5000,          # bezpiecznik pętli stronicowania
    "random_order": False,     # startowy stan checkboxa „Losowo"
}

_panel = None       # aktywny WordQueuePanel albo None
_active_url = None  # host, który ostatnio odpowiedział — próbowany jako pierwszy


def _get_config() -> dict:
    return get_module_config(_MODULE_KEY, _DEFAULTS)


def _configured(cfg: dict) -> bool:
    return bool(_base_urls(cfg) and cfg["api_key"] and cfg["table_id"])


def _base_urls(cfg: dict) -> list[str]:
    """Adresy do wypróbowania: ostatni działający, potem domowy, potem fallback."""
    urls = []
    for url in (_active_url, cfg["n8n_url"], cfg.get("fallback_url", "")):
        url = (url or "").rstrip("/")
        if url and url not in urls:
            urls.append(url)
    return urls


def _via_hosts(cfg: dict, call):
    """call(base) → (wartość, błąd). Pierwszy host bez błędu wygrywa i zostaje zapamiętany.

    ponytail: nie rozróżniamy „host padł" od „żądanie było złe" — przy 4xx
    pukamy niepotrzebnie do drugiego hosta i dostajemy ten sam błąd. Tanie.
    Zapamiętany host trzyma się do pierwszej porażki, więc wróciwszy do domu
    jedziesz przez Tailscale aż coś się wywali. Bez znaczenia: to ten sam n8n.
    """
    global _active_url
    error = "brak skonfigurowanego adresu n8n"
    for base in _base_urls(cfg):
        value, error = call(base)
        if error is None:
            _active_url = base
            return value, None
        log.warning("word_queue: %s nie odpowiada (%s)", base, error)
    _active_url = None
    return None, error


def _rows_url(base: str, cfg: dict, suffix: str = "") -> str:
    return f"{base}/api/v1/data-tables/{cfg['table_id']}/rows{suffix}"


def _headers(cfg: dict) -> dict:
    return {"Content-Type": "application/json", "X-N8N-API-KEY": cfg["api_key"]}


def _get_json(url: str, cfg: dict):
    # Jedna próba, krótki timeout: gdy host padł, chcemy SZYBKO przejść na
    # kolejny (_via_hosts), a nie mielić 3 retry × 10 s zanim spróbujemy Tailscale.
    raw = fetch_url(url, headers=_headers(cfg), max_retries=1, timeout=5)
    if raw is None:
        return None, "brak odpowiedzi (szczegóły w Logach)"
    try:
        return json.loads(raw), None
    except ValueError as e:
        return None, f"zła odpowiedź n8n: {e}"


def fetch_tables(cfg: dict) -> tuple[list[dict], str | None]:
    """Lista tabel do rozwijanki w Ustawieniach: [{'id':…, 'name':…}, …]."""
    def call(base):
        data, error = _get_json(f"{base}/api/v1/data-tables?limit=250", cfg)
        if error:
            return None, error
        return [{"id": t["id"], "name": t["name"]} for t in data.get("data", [])], None

    tables, error = _via_hosts(cfg, call)
    return tables or [], error


# ---------------------------------------------------------------------------
# klient n8n — wołany z wątku roboczego (mw.taskman.run_in_background)
# ---------------------------------------------------------------------------

def _payload(filters: list[dict], flag_column: str, value: bool) -> bytes:
    """Body PATCH-a do /rows/update. returnData → odpowiedź to lista trafionych wierszy."""
    return json.dumps({
        "filter": {"type": "and", "filters": filters},
        "data": {flag_column: value},
        "returnData": True,  # pusta lista w odpowiedzi = nic nie trafiono
    }).encode()


def _set_flag(filters: list[dict], cfg: dict, value: bool) -> tuple[int, str | None]:
    """Ustaw flag_column na wierszach pasujących do filtrów. Zwraca (trafione, błąd)."""
    def call(base):
        body, error = post_json(
            _rows_url(base, cfg, "/update"),
            _payload(filters, cfg["flag_column"], value),
            _headers(cfg),
            method="PATCH",
            max_retries=2,  # 429/5xx warte ponowienia — utrata PATCH-a to rozjazd z n8n
            timeout=8,
            log=log,
        )
        if error:
            return None, error
        try:
            rows = json.loads(body)
        except ValueError as e:
            return None, f"zła odpowiedź n8n: {e}"
        if not isinstance(rows, list):
            return None, f"zła odpowiedź n8n: oczekiwano listy, jest {type(rows).__name__}"
        return len(rows), None

    matched, error = _via_hosts(cfg, call)
    return (matched or 0), error


def mark_row_done(row_id, cfg: dict, done: bool = True) -> tuple[int, str | None]:
    """Ustaw flagę po `id` — pewne, niezależne od tego, co wpisałeś w pole notatki.

    done=False cofa odhaczenie (odznaczenie ptaszka w panelu).
    """
    return _set_flag([{"columnName": "id", "condition": "eq", "value": row_id}], cfg, done)


def mark_word_done(word: str, cfg: dict) -> tuple[int, str | None]:
    """Odhacz po treści hasła — fallback, gdy panel nie jest otwarty."""
    return _set_flag(
        [{"columnName": cfg["word_column"], "condition": "eq", "value": word}], cfg, True
    )


def _queue_query(page_size: int, cursor: str | None = None) -> str:
    """Query string dla GET /rows. Kursor to base64 z {limit, offset}, więc
    `sortBy` trzeba powtarzać przy każdej stronie — w kursorze go nie ma.

    Bez filtra po fladze: panel bierze CAŁĄ tabelę i sam chowa zrobione. Inaczej
    „Odśwież" gubiłby wiersze odhaczone w tej sesji i nie dało się cofnąć pomyłki.
    """
    params = {"limit": page_size, "sortBy": "id:asc"}
    if cursor:
        params["cursor"] = cursor
    return urllib.parse.urlencode(params, quote_via=urllib.parse.quote)


def fetch_queue(cfg: dict) -> tuple[list[dict], str | None]:
    """Pobierz WSZYSTKIE wiersze tabeli, stronicując po kursorze.

    n8n tnie `limit` na 250, więc ~1000 wierszy to 4 żądania. `max_rows` jest
    bezpiecznikiem przed pętlą bez końca, gdyby kursor kiedyś zaczął zapętlać.
    """
    def call(base):
        rows: list[dict] = []
        cursor = None
        while True:
            query = _queue_query(cfg["page_size"], cursor)
            page, error = _get_json(_rows_url(base, cfg, f"?{query}"), cfg)
            if error:
                return None, error  # cała paczka od nowa na kolejnym hoście
            rows.extend(page.get("data", []))
            cursor = page.get("nextCursor")
            if not cursor or not page.get("data") or len(rows) >= cfg["max_rows"]:
                break
        return rows, None

    rows, error = _via_hosts(cfg, call)
    if error:
        return [], error
    left = sum(1 for row in rows if not row.get(cfg["flag_column"]))
    log.info("word_queue: pobrano %d wierszy (%d do zrobienia) z %s", len(rows), left, _active_url)
    return rows, None


# ---------------------------------------------------------------------------
# hooki i menu
# ---------------------------------------------------------------------------

def on_add_note(note) -> None:
    """add_cards_did_add_note — odhacz świeżo dodane słówko."""
    cfg = _get_config()
    if not _configured(cfg):
        return  # nieskonfigurowany → moduł śpi

    # Widoczny panel wie, który wiersz robisz → patch po id. Uwaga: gdy panel jest
    # otwarty, KAŻDA dodana notatka odhacza bieżący wiersz, także dodana
    # obok kolejki. ponytail: w praktyce panel otwierasz po to, żeby robić
    # kolejkę; gdyby to gryzło — porównaj pole z wierszem przed patchem.
    if _panel is not None and _panel.isVisible():
        _panel.note_added()
        return

    field = cfg["word_field"]
    word = clean_html_normalized(note[field]) if field in note else ""
    if not word:
        return

    def on_done(future) -> None:
        try:
            matched, error = future.result()
        except Exception:  # noqa: BLE001 — nie wysadzaj dodawania kart
            log.exception("word_queue: PATCH rzucił wyjątkiem")
            return
        if error:
            tooltip(f'n8n: nie odhaczono „{word}" — {error}', parent=mw, period=5000)
        elif matched == 0:
            log.info('word_queue: „%s" nie występuje w tabeli — pomijam', word)
        else:
            log.info('word_queue: odhaczono „%s" (%d wiersz(e))', word, matched)

    mw.taskman.run_in_background(lambda: mark_word_done(word, cfg), on_done)


def _toggle_panel(addcards) -> None:
    """Doklej panel do tego okna „Dodaj", a jeśli już wisi — zwiń go."""
    global _panel
    cfg = _get_config()
    if not _configured(cfg):
        tooltip("word_queue: uzupełnij n8n_url, api_key i table_id w config.json",
                parent=mw, period=6000)
        return

    if _panel is not None:
        _panel.setVisible(not _panel.isVisible())
        return

    from .panel import WordQueuePanel

    _panel = WordQueuePanel(addcards, cfg, fetch_queue, mark_row_done)
    _panel.destroyed.connect(_forget_panel)  # okno „Dodaj" zamknięte → wracamy do fallbacku


def open_queue() -> None:
    """Narzędzia → Kolejka słówek: otwórz okno „Dodaj" i doklej panel."""
    _toggle_panel(aqt.dialogs.open("AddCards", mw))


def _forget_panel(*_args) -> None:
    global _panel
    _panel = None


def on_editor_buttons_init(buttons, editor):
    """editor_did_init_buttons — przycisk 📚 tylko w oknie „Dodaj" (panel nie ma sensu w przeglądarce)."""
    if not getattr(editor, "addMode", False):
        return buttons
    buttons.append(
        editor.addButton(
            icon=None,
            cmd="wq_toggle",
            func=lambda _ed: _toggle_panel(_ed.parentWindow),
            tip="Kolejka słówek z n8n (pokaż/ukryj)",
            label="📚",
        )
    )
    return buttons


def setup_menu(parent_menu=None) -> None:
    menu = parent_menu or mw.form.menuTools
    action = QAction("Kolejka słówek (n8n)...", mw)
    action.triggered.connect(lambda _checked=False: open_queue())
    menu.addAction(action)


if __name__ == "__main__":  # self-check budowania zapytań (bez Anki i bez sieci)
    cfg = dict(_DEFAULTS, n8n_url="http://h:5678/", table_id="T")

    assert _rows_url("http://h:5678", cfg) == "http://h:5678/api/v1/data-tables/T/rows"
    assert _rows_url("http://h:5678", cfg, "/update").endswith("/rows/update")

    # --- failover -----------------------------------------------------------
    home, away = "http://192.168.1.50:5678", "https://n8n.ts.net"
    fcfg = dict(cfg, n8n_url=home + "/", fallback_url=away)  # rstrip('/') po drodze

    _active_url = None
    assert _base_urls(fcfg) == [home, away]                  # domowy pierwszy
    assert _base_urls(dict(fcfg, n8n_url="")) == [away]      # sam fallback wystarczy
    assert _configured(dict(fcfg, n8n_url="", api_key="k"))

    tried = []
    def only_away(base):
        tried.append(base)
        return ("ok", None) if base == away else (None, "Connection error")

    value, error = _via_hosts(fcfg, only_away)
    assert (value, error) == ("ok", None) and tried == [home, away], tried
    assert _active_url == away                               # zapamiętany

    tried.clear()                                            # kolejne wywołanie: od razu Tailscale
    _via_hosts(fcfg, only_away)
    assert tried == [away], tried

    _active_url = None
    value, error = _via_hosts(fcfg, lambda _b: (None, "padło"))
    assert value is None and error == "padło" and _active_url is None  # oba padły → zapomnij host

    p = json.loads(_payload([{"columnName": "id", "condition": "eq", "value": 15}], "Anki", True))
    assert p["data"] == {"Anki": True}
    assert p["returnData"] is True
    assert p["filter"] == {"type": "and",
                           "filters": [{"columnName": "id", "condition": "eq", "value": 15}]}

    # cofanie odhaczenia to ten sam PATCH z false — inaczej nie da się odkliknąć pomyłki
    undo = json.loads(_payload([{"columnName": "id", "condition": "eq", "value": 15}], "Anki", False))
    assert undo["data"] == {"Anki": False}

    # nazwy kolumn są konfigurowalne — nie mogą być zaszyte w body
    q = json.loads(_payload([{"columnName": "Word", "condition": "eq", "value": "x"}], "Done", True))
    assert q["data"] == {"Done": True}
    assert q["filter"]["filters"][0]["columnName"] == "Word"

    # nieskonfigurowany moduł musi spać, nawet gdy część pól jest wypełniona
    assert not _configured(dict(_DEFAULTS))
    assert not _configured(dict(cfg))                       # brak api_key
    assert _configured(dict(cfg, api_key="k"))

    query = _queue_query(250)
    assert "sortBy=id%3Aasc" in query, query                # dwukropek musi być zakodowany
    assert "cursor" not in query                           # pierwsza strona idzie bez kursora
    # Brak filtra jest celowy: panel chowa zrobione sam, żeby „Odśwież" ich nie gubił.
    assert "filter" not in query, query

    # kolejne strony: kursor doklejony, ale sortBy MUSI się powtórzyć
    # (kursor niesie tylko limit+offset — bez sortBy n8n zwróci inne wiersze)
    page2 = urllib.parse.parse_qs(_queue_query(250, "eyJsaW1pdCI6MjUwfQ=="))
    assert page2["cursor"] == ["eyJsaW1pdCI6MjUwfQ=="]
    assert page2["sortBy"] == ["id:asc"]

    print("word_queue self-check OK")
