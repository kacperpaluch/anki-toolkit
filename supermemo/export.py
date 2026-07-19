"""Zrzut notatek SuperMemo z kolekcji → user_files/supermemo.json.

Uruchom raz (Anki + AnkiConnect muszą działać), potem możesz usunąć notatki
SuperMemo z kolekcji — moduł czyta już z JSON, nie z kolekcji. Odpal ponownie
po każdym nowym imporcie bazy SM.

    python3 supermemo/export.py

Klucz JSON: English (lower, strip). Wartość: lista znaczeń (homonimy).
Zapisywane tylko pola z KEEP — bez audio, obrazków, przykładów.
"""
import json
import os
import urllib.request

URL = "http://127.0.0.1:8765"
NOTE_TYPE = "SuperMemo Extreme"
KEEP = ["Translation", "Definition", "Synonyms", "PartOfSpeech"]
OUT = os.path.join(os.path.dirname(__file__), "..", "user_files", "supermemo.json")


def call(action, **params):
    req = json.dumps({"action": action, "version": 6, "params": params}).encode()
    r = urllib.request.urlopen(URL, data=req, timeout=120)
    d = json.loads(r.read().decode())
    if d.get("error"):
        raise RuntimeError(d["error"])
    return d["result"]


def main():
    nids = call("findNotes", query=f'note:"{NOTE_TYPE}"')
    print(f"notatek: {len(nids)}")

    db = {}
    for i in range(0, len(nids), 1000):
        for n in call("notesInfo", notes=nids[i:i + 1000]):
            f = n["fields"]
            key = f["English"]["value"].strip().lower()
            if not key:
                continue
            entry = {k: f[k]["value"].strip() for k in KEEP if f[k]["value"].strip()}
            if entry:  # pomiń wpisy bez żadnej treści tekstowej
                entry["English"] = f["English"]["value"].strip()
                db.setdefault(key, []).append(entry)
        print(f"  {min(i + 1000, len(nids))}/{len(nids)}")

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(db, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"kluczy: {len(db)}  znaczeń: {sum(len(v) for v in db.values())}")
    print(f"rozmiar: {os.path.getsize(OUT) // 1024} KB → {OUT}")


if __name__ == "__main__":
    main()
