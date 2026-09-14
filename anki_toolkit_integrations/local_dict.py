"""local_dict — lokalny słownik StarDict jako czytnik w panelu „Dodaj".

Baza (`user_files/stardict.sqlite`) powstaje raz, offline, z plików StarDict:

    python local_dict.py ~/Słowniki/slownik/dictionary.ifo

Plików źródłowych nie ruszamy — czytamy je tylko przy konwersji. W Anki mostek
serwuje `GET /dict?word=X`, a ta strona renderuje artykuł rozbity na znaczenia,
każde z własnym przyciskiem wysyłającym JEDNO znaczenie do otwartej notatki.
Wysyłką zajmuje się ten sam endpoint POST, z którego korzysta userscript.

Rozbijanie artykułu jest dostrojone do słownika skonwertowanego z .mobi
(znaczniki `<b>N.</b>`, części mowy `<b><i>n</i></b>`, zwroty w `<blockquote>`).
Inny słownik StarDict, którego tu nie rozpoznamy, trafia na stronę w całości
jako jeden blok — bez przycisków per znaczenie, ale nadal czytelny.
"""

from __future__ import annotations

import gzip
import html
import re
import sqlite3
import struct
import sys
import urllib.parse
from pathlib import Path
from typing import Iterator

DB_NAME = "stardict.sqlite"
_TEXT_TYPES = set("mlgtxykwhr")  # typy bloków .dict, które są tekstem

_BLOCKQUOTE = re.compile(r"<blockquote>(.*?)</blockquote>", re.S)
_MARKER = re.compile(r"(<b><sub>\d+</sub></b>|<b><i>[^<]*</i></b>|<b>\d+\.</b>)")
_XREF = re.compile(r"<a\s[^>]*filepos[^>]*>(.*?)</a>", re.S)
_TAGS = re.compile(r"<[^>]+>")
_HEADWORD = re.compile(r'<b style="font-size:1\.18em">(.*?)</b>', re.S)
_IPA = re.compile(r'<span style="font-size:\.9em;font-style:italic">(.*?)</span>', re.S)


# --- konwerter StarDict → SQLite ------------------------------------------

def _read(base: str, exts: tuple[str, ...]) -> bytes | None:
    for ext in exts:
        path = Path(base + ext)
        if path.is_file():
            raw = path.read_bytes()
            return gzip.decompress(raw) if path.suffix in (".gz", ".dz") else raw
    return None


def _blocks(block: bytes, same: str) -> list[tuple[str, bytes]]:
    """Rozbij blok .dict na pary (typ, bajty) wg sametypesequence albo prefiksów typu."""
    seq, out, i, k = list(same), [], 0, 0
    while i < len(block):
        if seq:
            if k >= len(seq):
                break
            kind, k = seq[k], k + 1
            last = k == len(seq)
        else:
            kind, i, last = chr(block[i]), i + 1, False
        if last:
            chunk, i = block[i:], len(block)
        elif kind.isupper():
            size, = struct.unpack(">I", block[i:i + 4])
            i += 4
            chunk, i = block[i:i + size], i + size
        else:
            end = block.index(0, i)
            chunk, i = block[i:end], end + 1
        out.append((kind, chunk))
    return out


def _entry_html(block: bytes, same: str) -> str:
    parts = [c.decode("utf8", "replace") for kind, c in _blocks(block, same) if kind.lower() in _TEXT_TYPES]
    text = "\n".join(part for part in parts if part.strip()).strip()
    return text if "<" in text else text.replace("\n", "<br>")


def _index(blob: bytes, fmt: str) -> list[tuple[str, int, int]]:
    """Trójki (hasło, offset, długość) z .idx — kolejność jest istotna, .syn adresuje po numerze."""
    width, out, pos = struct.calcsize(fmt), [], 0
    while pos < len(blob):
        end = blob.index(0, pos)
        offset, = struct.unpack(fmt, blob[end + 1:end + 1 + width])
        size, = struct.unpack(">I", blob[end + 1 + width:end + 5 + width])
        out.append((blob[pos:end].decode("utf8", "replace"), offset, size))
        pos = end + 5 + width
    return out


def walk(ifo) -> Iterator[tuple[str, int, str]]:
    """(hasło, offset bloku, definicja HTML) — hasła główne oraz aliasy z .syn.

    Offset identyfikuje definicję: alias „dogs" wskazuje na ten sam blok co „dog",
    więc w bazie definicja leży raz.
    """
    base = str(ifo)[:-4] if str(ifo).endswith(".ifo") else str(ifo)
    info = dict(re.findall(r"^(\w+)=(.*)$", Path(base + ".ifo").read_text("utf8"), re.M))
    same = info.get("sametypesequence", "")
    fmt = ">Q" if info.get("idxoffsetbits") == "64" else ">I"
    index = _index(_read(base, (".idx", ".idx.gz")), fmt)
    data = _read(base, (".dict", ".dict.dz"))
    syn, aliases, pos = _read(base, (".syn",)) or b"", [], 0
    while pos < len(syn):
        end = syn.index(0, pos)
        target, = struct.unpack(">I", syn[end + 1:end + 5])
        alias, pos = syn[pos:end].decode("utf8", "replace"), end + 5
        if target < len(index):
            aliases.append((alias, index[target][1], index[target][2]))
    for word, offset, size in index + aliases:
        yield word, offset, _entry_html(data[offset:offset + size], same)


def build_sqlite(ifo, target) -> int:
    """`defs` = definicje (klucz: offset bloku), `words` = hasła i aliasy wskazujące na nie."""
    Path(target).unlink(missing_ok=True)
    db = sqlite3.connect(str(target))
    db.execute("create table defs(id integer primary key, entry text)")
    db.execute("create table words(word text, id integer)")
    seen_defs, seen_words = set(), set()
    for word, offset, entry in walk(ifo):
        word = word.strip().lower()
        if not word or not entry:
            continue
        if offset not in seen_defs:
            seen_defs.add(offset)
            db.execute("insert into defs values(?,?)", (offset, entry))
        if (word, offset) not in seen_words:
            seen_words.add((word, offset))
            db.execute("insert into words values(?,?)", (word, offset))
    db.execute("create index word_idx on words(word)")
    db.commit()
    count = db.execute("select count(*) from words").fetchone()[0]
    db.close()
    return count


# --- odczyt ----------------------------------------------------------------

def db_path() -> Path:
    return Path(__file__).resolve().parent / "user_files" / DB_NAME


_conn = None


def _db():
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(str(db_path()), check_same_thread=False)
    return _conn


def lookup(word: str, db=None) -> list[str]:
    db = db or _db()
    rows = db.execute("select entry from defs join words using(id) where word=?", (word.strip().lower(),))
    return [row[0] for row in rows]


def suggest(prefix: str, limit: int = 20, db=None) -> list[str]:
    db = db or _db()
    prefix = prefix.strip().lower()
    if not prefix:
        return []
    rows = db.execute(
        "select distinct word from words where word like ? order by length(word), word limit ?",
        (prefix.replace("%", "").replace("_", "") + "%", limit))
    return [row[0] for row in rows]


# --- rozbijanie artykułu na znaczenia --------------------------------------

def _plain(fragment: str) -> str:
    return re.sub(r"\s+", " ", _TAGS.sub("", fragment)).replace("\xa0", " ").strip()


_LEADING_LABELS = re.compile(r"^(?:\s*<small>.*?</small>\s*,?\s*)+", re.S)


def _card_text(fragment: str) -> str:
    """Co ma trafić do pola notatki: samo tłumaczenie.

    Na ekranie zostaje wszystko, ale na kartę nie wchodzą kwalifikatory
    („pot.", „tech."), przykłady po ➤ ani odsyłacze po = i ↘ — to kontekst
    do czytania, nie treść karty.
    """
    text = _LEADING_LABELS.sub("", fragment.strip())
    text = _plain(text)
    for cut in ("\u27a4", "\u2198"):
        text = text.split(cut)[0]
    return re.sub(r"\s*=\s*$", "", text.split(" = ")[0]).strip(" ,;")


def _links(fragment: str) -> str:
    """Odsyłacze .mobi (`filepos`) → linki czytnika, żeby dało się skakać po hasłach."""
    def repl(match):
        text = _plain(match.group(1))
        return f'<a href="/dict?word={urllib.parse.quote(text)}">{match.group(1)}</a>' if text else ""
    return _XREF.sub(repl, fragment)


def parse(entry: str) -> dict:
    """Artykuł → {headword, ipa, grammar, senses, phrases}. Bloki mają `html` i `text`."""
    phrases = []
    for raw in _BLOCKQUOTE.findall(entry):
        text = _plain(raw)
        if text:
            head = re.match(r"\s*<b>(.*?)</b>(.*)", raw, re.S)
            phrases.append({"title": _plain(head.group(1)) if head else "",
                            "html": _links((head.group(2) if head else raw).strip()),
                            "text": _card_text(head.group(2) if head else raw)})
    main = _BLOCKQUOTE.sub("", entry)
    headword = _plain(_HEADWORD.search(main).group(1)) if _HEADWORD.search(main) else ""
    ipa = _plain(_IPA.search(main).group(1)) if _IPA.search(main) else ""
    if "display:block" in main:
        main = main.split("</span></span>", 1)[-1]

    parts = _MARKER.split(main)
    senses, pos, homograph, note = [], "", "", ""
    for marker, body in zip(parts[1::2], parts[2::2]):
        if marker.startswith("<b><sub>"):
            homograph, pos, note = _plain(marker), "", _plain(body)
            continue
        if marker.startswith("<b><i>"):
            pos = _plain(marker)
            note = (note + " " + _plain(body)).strip()
            continue
        text = _card_text(body)
        if text:
            senses.append({"num": _plain(marker), "pos": pos, "homograph": homograph, "note": note,
                           "html": _links(body.strip()), "text": text})
    if not senses and _plain(main):
        senses = [{"num": "", "pos": "", "homograph": "", "note": "",
                   "html": _links(main.strip()), "text": _card_text(main)}]
    return {"headword": headword, "ipa": ipa, "grammar": _plain(parts[0]), "senses": senses, "phrases": phrases}


# --- strona ----------------------------------------------------------------

_CSS = """
:root{color-scheme:light dark}
body{font:15px/1.5 -apple-system,Segoe UI,sans-serif;margin:0;padding:12px 16px 40px;background:Canvas;color:CanvasText}
form{position:sticky;top:0;background:Canvas;padding:8px 0;display:flex;gap:8px;align-items:center;
     border-bottom:1px solid color-mix(in srgb,CanvasText 20%,transparent);z-index:2}
input[type=search]{flex:1;max-width:320px;padding:5px 8px;font-size:14px}
h1{font-size:24px;margin:16px 0 2px;display:flex;align-items:baseline;gap:8px;flex-wrap:wrap}
.ipa{font-size:15px;font-style:italic;opacity:.7;font-weight:400}
.gram{margin:0 0 10px;opacity:.7;font-size:13px}
.pos{display:inline-block;margin:14px 0 4px;font-weight:600;font-style:italic;opacity:.75}
.sense,.phrase{display:flex;gap:8px;align-items:baseline;padding:3px 6px;border-radius:6px}
.sense:hover,.phrase:hover{background:color-mix(in srgb,CanvasText 8%,transparent)}
.num{min-width:2.2em;text-align:right;opacity:.6;font-variant-numeric:tabular-nums}
.t{flex:1}
.phrase .title{font-weight:600;margin-right:6px}
button{font:12px/1.4 inherit;padding:1px 7px;cursor:pointer;border:1px solid #3b7ddd;color:#3b7ddd;
       background:transparent;border-radius:4px;white-space:nowrap}
.sense button,.phrase button{opacity:0}
.sense:hover button,.phrase:hover button,button:focus{opacity:1}
h2{font-size:14px;text-transform:uppercase;letter-spacing:.06em;opacity:.6;margin:26px 0 6px}
hr{border:0;border-top:1px solid color-mix(in srgb,CanvasText 20%,transparent);margin:24px 0}
.empty{margin-top:32px;opacity:.7}
.empty a{display:inline-block;margin:2px 10px 2px 0}
a{color:#3b7ddd}
"""

_JS = """
const appendBox=document.getElementById('append');
async function send(field,text,btn){
  const body={fields:{[field]:text},append:appendBox.checked};
  const label=btn.textContent;
  try{
    const r=await fetch('/',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const j=await r.json();
    btn.textContent=j.ok?'✓':'✗';btn.title=j.error||text;
  }catch(e){btn.textContent='✗';btn.title=String(e);}
  setTimeout(()=>{btn.textContent=label;btn.title='';},1500);
}
document.addEventListener('click',e=>{
  const btn=e.target.closest('button[data-field]');
  if(!btn)return;
  e.preventDefault();
  const key=btn.dataset.from==='head'?'head':'text';
  const host=btn.closest('[data-'+key+']');
  send(btn.dataset.field,host?host.dataset[key]:'',btn);
});
"""


def _buttons(fields: list[str], headword_field: str = "") -> str:
    """Przycisk na pole. `headword_field` bierze treść z data-head (hasło/zwrot), reszta z data-text."""
    out = [f'<button data-field="{html.escape(headword_field, quote=True)}" data-from="head">'
           f'→ {html.escape(headword_field)}</button>'] if headword_field else []
    out += [f'<button data-field="{html.escape(f, quote=True)}">→ {html.escape(f)}</button>' for f in fields]
    return "".join(out)


def _entry_page(entry: str, fields: list[str], headword_field: str) -> str:
    art = parse(entry)
    out = [f'<h1><span>{html.escape(art["headword"])}</span>']
    if art["ipa"]:
        out.append(f'<span class="ipa">{html.escape(art["ipa"])}</span>')
    if headword_field and art["headword"]:
        out.append(f'<span data-head="{html.escape(art["headword"], quote=True)}">{_buttons([], headword_field)}</span>')
    out.append("</h1>")
    if art["grammar"]:
        out.append(f'<p class="gram">{html.escape(art["grammar"])}</p>')
    last_pos = None
    for sense in art["senses"]:
        head = " ".join(x for x in (sense["homograph"], sense["pos"], sense.get("note", "")) if x)
        if head and head != last_pos:
            out.append(f'<div class="pos">{html.escape(head)}</div>')
            last_pos = head
        out.append(f'<div class="sense" data-text="{html.escape(sense["text"], quote=True)}">'
                   f'<span class="num">{html.escape(sense["num"])}</span>'
                   f'<span class="t">{sense["html"]}</span>{_buttons(fields)}</div>')
    if art["phrases"]:
        out.append("<h2>Zwroty i złożenia</h2>")
        for phrase in art["phrases"]:
            out.append(f'<div class="phrase" data-text="{html.escape(phrase["text"], quote=True)}" '
                       f'data-head="{html.escape(phrase["title"], quote=True)}">'
                       f'<span class="t"><span class="title">{html.escape(phrase["title"])}</span>'
                       f'{phrase["html"]}</span>{_buttons(fields, headword_field)}</div>')
    return "".join(out)


def page(word: str, entries: list[str], suggestions: list[str], fields: list[str], headword_field: str = "") -> str:
    """Cała strona czytnika. `word` pochodzi z URL-a, więc wszędzie leci przez escape."""
    safe = html.escape(word, quote=True)
    body = ["<!doctype html><html lang=pl><head><meta charset=utf-8>",
            f"<title>{safe or 'Słownik'}</title><style>{_CSS}</style></head><body>",
            f'<form action="/dict"><input type="search" name="word" value="{safe}" placeholder="szukaj hasła…" autofocus>'
            '<button type="submit">Szukaj</button>'
            f'<label><input type="checkbox" id="append" checked> dokleja do pola</label></form>']
    if entries:
        body.append('<hr>'.join(_entry_page(entry, fields, headword_field) for entry in entries))
    elif suggestions:
        links = " ".join(f'<a href="/dict?word={urllib.parse.quote(s)}">{html.escape(s)}</a>' for s in suggestions)
        body.append(f'<p class="empty">Brak hasła <b>{safe}</b>. Może chodziło o:<br>{links}</p>')
    elif word:
        body.append(f'<p class="empty">Brak hasła <b>{safe}</b> w słowniku.</p>')
    else:
        body.append('<p class="empty">Wpisz hasło albo wybierz słówko z listy po lewej.</p>')
    body.append(f"<script>{_JS}</script></body></html>")
    return "".join(body)


def render(word: str, config: dict) -> str:
    """Punkt wejścia dla mostka: wyszukaj i zbuduj stronę. Brak bazy → komunikat, nie wyjątek."""
    fields = config.get("fields") or ["pol"]
    headword_field = config.get("headword_field") or ""
    if not db_path().is_file():
        return page(word, [], [], fields, headword_field).replace(
            "Wpisz hasło albo wybierz słówko z listy po lewej.",
            f"Brak bazy słownika ({html.escape(str(db_path()))}). Zbuduj ją poleceniem "
            "<code>python local_dict.py &lt;plik.ifo&gt;</code>.")
    entries = lookup(word) if word else []
    return page(word, entries, [] if entries else suggest(word), fields, headword_field)


if __name__ == "__main__":
    source = sys.argv[1]
    target = sys.argv[2] if len(sys.argv) > 2 else db_path()
    Path(target).parent.mkdir(parents=True, exist_ok=True)
    print(f"{build_sqlite(source, target)} haseł → {target}")
