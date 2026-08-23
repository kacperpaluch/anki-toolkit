# LLM Context — Anki Toolkit: Learning

## Zakres

Dodatek zawiera tylko presety talii filtrowanych. Homograph Manager został
świadomie usunięty z zakresu migracji.

## Niezmienniki

- Presety przeszukują całą kolekcję i używają `reschedule=false`.
- Istniejąca talia filtrowana o tej samej nazwie jest aktualizowana, nie duplikowana.
- Główne menu otwiera bezpośrednio wybór presetu; dodatkowe ustawienia są
  przyciskiem w tym dialogu. Zapis zachowuje nieznane klucze.

`__init__.py` zawiera presety, dialog wyboru i rebuild talii; `settings.py`
edytuje nazwę bazową. **Narzędzia → Anki Toolkit: Learning…** otwiera wybór
presetu, a „Dodatkowe ustawienia…” jest przyciskiem w tym samym dialogu.
