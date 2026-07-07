// ==UserScript==
// @name         Słowniki → Anki (otwarte okno „Dodaj")
// @namespace    kacper.paluch.cc
// @version      4.4
// @description  Przyciski na diki.pl / Oxford / LDOCE / Cambridge wpisują hasło / tłumaczenie / definicję / przykłady (doklejane) do JUŻ OTWARTEGO okna „Dodaj" w Anki (mostek anki-toolkit na 127.0.0.1:8766). Nic nie zapisuje się samo.
// @match        https://www.diki.pl/slownik-angielskiego*
// @match        https://www.diki.pl/slownik-*
// @match        https://www.oxfordlearnersdictionaries.com/definition/*
// @match        https://www.ldoceonline.com/dictionary/*
// @match        https://dictionary.cambridge.org/*/dictionary/*
// @grant        GM_xmlhttpRequest
// @grant        GM.xmlHttpRequest
// @connect      127.0.0.1
// @connect      localhost
// @noframes
// ==/UserScript==

(function () {
  'use strict';

  // ── KONFIG — nazwy pól w Twoim typie notatki ────────────────────────────────
  const FIELDS = {
    headword:   'ang',       // hasło (angielskie)
    meaning:    'pol',       // polskie tłumaczenie (diki)
    definition: 'def',       // angielska definicja (Oxford / LDOCE)
    example:    'przyklad',  // przykładowe zdania (Oxford / LDOCE) — DOKLEJANE przez <br><br>
  };
  const ENDPOINT = 'http://127.0.0.1:8766';
  // ─────────────────────────────────────────────────────────────────────────────

  // normalizacja białych znaków + obcięcie końcowego dwukropka (Cambridge kończy definicje na ":")
  const clean = (s) => (s || '').replace(/\s+/g, ' ').trim().replace(/\s*:$/, '');

  // Menedżery userscriptów: GM_xmlhttpRequest (Tampermonkey) lub GM.xmlHttpRequest
  // (Userscripts na Safari). Obie omijają CORS i mixed content (https→http://127.0.0.1).
  const gmXHR =
    (typeof GM_xmlhttpRequest !== 'undefined' && GM_xmlhttpRequest) ||
    (typeof GM !== 'undefined' && GM.xmlHttpRequest && GM.xmlHttpRequest.bind(GM)) ||
    null;

  // Wpisuje {pole: wartość, ...} do otwartego okna „Dodaj". Zwraca komunikat błędu lub ''.
  // opts.append === true → mostek dokleja do istniejącej treści pola (separator <br><br>).
  function send(fields, opts = {}) {
    const body = { fields };
    if (opts.append) body.append = true;
    const payload = JSON.stringify(body);
    if (gmXHR) {
      return new Promise((resolve) => {
        gmXHR({
          method: 'POST', url: ENDPOINT, data: payload,
          headers: { 'Content-Type': 'application/json' },
          onload: (r) => {
            try { const j = JSON.parse(r.responseText); resolve(j.ok ? '' : (j.error || 'nieznany błąd')); }
            catch (e) { resolve('zła odpowiedź Anki'); }
          },
          onerror: () => resolve('brak połączenia z Anki (uruchomione? okno „Dodaj" otwarte?)'),
          ontimeout: () => resolve('Anki nie odpowiada'),
        });
      });
    }
    return fetch(ENDPOINT, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: payload })
      .then((r) => r.json()).then((j) => (j.ok ? '' : (j.error || 'nieznany błąd')))
      .catch((ex) => 'brak połączenia z Anki? ' + (ex.message || ex));
  }

  // getFields: funkcja zwracająca {pole: tekst, ...} w chwili kliknięcia
  // opts przekazywane do send() (np. {append:true} dla przykładów)
  function makeBtn(label, getFields, opts = {}) {
    const btn = document.createElement('button');
    btn.className = 'ankiBtn';
    btn.textContent = label;
    btn.style.cssText =
      'margin-left:8px;padding:0 6px;font-size:12px;line-height:1.4;cursor:pointer;' +
      'border:1px solid #3b7ddd;color:#3b7ddd;background:#fff;border-radius:4px;vertical-align:middle;' +
      'display:inline-block;white-space:nowrap';
    btn.addEventListener('click', async (e) => {
      e.preventDefault(); e.stopPropagation();
      const fields = getFields();
      const empty = Object.values(fields).every((v) => !v);
      const err = empty ? 'pusty tekst' : await send(fields, opts);
      btn.textContent = err ? '✗' : '✓';
      btn.style.color = btn.style.borderColor = err ? '#c0392b' : '#27ae60';
      btn.title = err || Object.entries(fields).map(([k, v]) => `${k}: ${v}`).join('  |  ');
      setTimeout(() => { btn.textContent = label; btn.style.color = btn.style.borderColor = '#3b7ddd'; }, 1600);
    });
    return btn;
  }

  // ── diki.pl ─────────────────────────────────────────────────────────────────
  function injectDiki() {
    document.querySelectorAll('.dictionaryEntity .hws').forEach((hws) => {
      const hw = hws.querySelector('.hw');
      if (!hw || hws.querySelector('.ankiBtn')) return;
      hw.after(makeBtn('→ hasło', () => ({ [FIELDS.headword]: clean(hw.textContent) })));
    });
    document.querySelectorAll('.foreignToNativeMeanings > li').forEach((li) => {
      if (li.querySelector('.ankiBtn')) return;
      const spans = [...li.querySelectorAll(':scope > span.hw')];
      if (!spans.length) return;
      const meaning = () => spans.map((s) => clean(s.textContent)).join(', ');
      const headword = () => {
        const hw = li.closest('.dictionaryEntity')?.querySelector('.hws .hw');
        return hw ? clean(hw.textContent) : '';
      };
      const last = spans[spans.length - 1];
      last.after(makeBtn('→ oba', () => ({ [FIELDS.headword]: headword(), [FIELDS.meaning]: meaning() })));
      last.after(makeBtn('→ Anki', () => ({ [FIELDS.meaning]: meaning() })));
    });
  }

  // ── Oxford / LDOCE — przycisk przy każdym elemencie pasującym do selektora ───
  // Oxford: definicja .def (w .sensetop), przykład .x; LDOCE: definicja .DEF, przykład .EXAMPLE.
  // opts.append=true dla przykładów → doklejane z separatorem po stronie mostka.
  function injectButtons(selector, label, field, opts, getText) {
    document.querySelectorAll(selector).forEach((el) => {
      if (el.dataset.ankiDone) return;      // dataset = pewny znacznik, niezależny od sąsiadów
      el.dataset.ankiDone = '1';
      const text = getText ? getText(el) : clean(el.textContent);
      if (!text) return;
      el.after(makeBtn(label, () => ({ [field]: text }), opts));
    });
  }

  function inject() {
    const host = location.hostname;
    if (host.includes('diki.pl')) {
      injectDiki();
    } else if (host.includes('oxfordlearnersdictionaries.com')) {
      injectButtons('h1.headword', '→ hasło', FIELDS.headword);
      // Oxford: „(of a person)” siedzi w osobnym .dis-g tuż przed .def — doklej go jako prefiks
      injectButtons('.def', '→ def', FIELDS.definition, {}, (el) => {
        const dis = el.previousElementSibling;
        const prefix = dis && dis.classList.contains('dis-g') ? clean(dis.textContent) + ' ' : '';
        return prefix + clean(el.textContent);
      });
      injectButtons('.x', '+ przykład', FIELDS.example, { append: true });
    } else if (host.includes('ldoceonline.com')) {
      injectButtons('.HWD', '→ hasło', FIELDS.headword);
      injectButtons('.DEF', '→ def', FIELDS.definition);
      injectButtons('.EXAMPLE', '+ przykład', FIELDS.example, { append: true });
    } else if (host.includes('dictionary.cambridge.org')) {
      injectButtons('.hw.dhw', '→ hasło', FIELDS.headword);
      injectButtons('.def', '→ def', FIELDS.definition);           // Cambridge: definicja + końcowy ":" ucinany w clean()
      injectButtons('.eg', '+ przykład', FIELDS.example, { append: true });
      injectButtons('.dtrans-se', '→ pol', FIELDS.meaning);        // tłumaczenie PL (tylko wersja EN-PL)
    }
  }

  inject();
  new MutationObserver(inject).observe(document.body, { childList: true, subtree: true });
})();
