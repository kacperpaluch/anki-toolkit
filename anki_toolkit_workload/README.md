# Anki Toolkit: Workload

Odpowiada na jedno pytanie: **czy przy obecnych limitach nie zafunduję sobie
lawiny powtórek?** Otwórz **Narzędzia → Anki Toolkit: Workload…**, a dodatek
zmierzy obecne obciążenie, porówna je z Twoim czasem i wypisze, co warto
zmienić.

Dodatek **tylko czyta** kolekcję. Nie zmienia limitów, presetów, harmonogramu
ani kart — proponuje liczby, które wpisujesz sam w Opcjach talii. Przycisk
**Kopiuj raport** zapisuje wersję tekstową do schowka.

## Dwie liczby, których nie należy mieszać

- **Teraz — pomiar.** Suma odwrotności interwałów wszystkich kart powtórkowych:
  karta z interwałem 10 dni kosztuje 0,1 powtórki dziennie. To nie prognoza, to
  właściwość Twojej kolekcji, prawdziwa od pierwszego dnia nauki.
- **Docelowo — projekcja.** Dopływ nowych kart przemnożony przez „ile powtórek
  generuje jedna nowa karta". Raport zawsze podaje, skąd ten współczynnik
  pochodzi: z Twojej historii czy z reguły ×10 z manuala Anki.

## Budżet czasu

Sufit nie jest zwykłym dzieleniem czasu przez czas powtórki, bo **nowe karty nie
są darmowe**. Przy krokach nauki 1 min / 10 min każda nowa karta kosztuje kilka
odpowiedzi tego samego dnia. Dodatek odejmuje ten koszt od budżetu, a potem
liczy, ile powtórek zostaje.

Największy dopływ nowych kart wychodzi z zamkniętego wzoru: jedna nowa karta
dziennie kosztuje dziennie `powtórki_na_kartę × czas_powtórki` plus
`odpowiedzi_w_nauce × czas_odpowiedzi`.

## Co mierzy z historii

| Wielkość | Skąd |
|---|---|
| Czas powtórki | Mediana czasu odpowiedzi (typy revlog 1 i 2) z 30 dni. |
| Czas odpowiedzi w nauce | Mediana czasu odpowiedzi w nauce (typ 0) z 30 dni. |
| Odpowiedzi na nową kartę | Liczba odpowiedzi w nauce ÷ liczba wprowadzonych kart. |
| Powtórki na nową kartę | Powtórki ÷ wprowadzone karty, ale **tylko od 60 dni z faktyczną nauką** — krócej wynik jest zaniżony, bo karty nie zdążyły wrócić. |
| Trend | Nachylenie prostej z ostatnich 28 dni, od 10 dni z faktyczną nauką. Dni bez nauki wchodzą jako zera. |

Liczone są dni z nauką, nie dni kalendarzowe — miesiąc przerwy nie udaje
historii. Każdą z tych wielkości możesz nadpisać w ustawieniach; zero oznacza
„policz z historii".

## Co raportuje

- **Budżet** — czas powtórki, koszt nowej karty, sufit powtórek po odjęciu tego
  kosztu, największy sensowny dopływ nowych kart.
- **Teraz** — obciążenie strukturalne z interwałów, zaległości, trend dziennej
  liczby powtórek i data przebicia sufitu, jeśli rośnie.
- **Docelowo** — stan stacjonarny z obecnego dopływu, zapas nowych kart i na ile
  dni wystarczy.
- **Tabela talii** — limity, propozycje obu limitów, obciążenie dzienne, zapas,
  karty na dziś. Gwiazdka oznacza talię, z której się uczysz.
- **Prognoza** — karty wypadające za 1, 3, 7, 14, 30, 60, 90, 180 i 365 dni,
  z paskiem i sumą narastającą oraz największym dniem w oknie.
- **Uwagi** — patrz niżej.

## Uwagi, które potrafi zgłosić

- **Brak sufitu powtórek** — z rozróżnieniem talii nadrzędnej i podtalii. Ta
  sama liczba wpisana w każdą podtalię **nie ogranicza sumy**: pięć presetów po
  200 daje 1000 powtórek dziennie. Pełną wartość dostaje talia, z której się
  uczysz, a podtalie swój udział proporcjonalny do dopływu.
- **Nowe karty zjadają cały czas** — sam koszt wprowadzania przekracza budżet.
- **Już teraz powyżej sufitu** — pomiar z interwałów przewyższa sufit.
- **Zaległości** — kart po terminie więcej niż dzienny sufit.
- **Dopływ nowych kart za wysoki** — z podziałem propozycji per talia.
- **Obciążenie rośnie** — z tempem wzrostu i datą przebicia sufitu.
- **Górka w prognozie** — najgorszy dzień w oknie powyżej sufitu.
- **Hamulec działa / wyłączony** — stan „nowe karty ignorują limit powtórek".
  Przy wyłączonej opcji raport wyjaśnia, że to ona sama reguluje dopływ.
- **Dni łatwe zmieniają sufit**, **FSRS wyłączone**, **Load balancer wyłączony**,
  **Talia nadrzędna szersza niż podtalie** (tylko przy „limitach od góry").
- **Nie odczytano ustawień kolekcji** — gdy odczyt klucza się wywali, raport to
  mówi, zamiast po cichu pominąć powiązane uwagi.
- **Część liczb jest oszacowana** — lista wielkości wziętych z wartości
  domyślnych zamiast z Twoich danych.

Klucz nieobecny w konfiguracji kolekcji nie generuje uwagi — brak odpowiedzi nie
jest traktowany jak wyłączona opcja.

## Ustawienia

Przycisk **Ustawienia…** w oknie raportu:

| Klucz `config.json` | Znaczenie |
|---|---|
| `minutes_per_day` | Ile minut dziennie chcesz poświęcać. Jedyna wartość, której dodatek nie zgadnie. |
| `seconds_per_card` | Czas powtórki; `0` = mediana z historii, bez historii 9 s. |
| `learn_seconds_per_card` | Czas odpowiedzi w nauce; `0` = mediana z historii, bez historii 12 s. |
| `learn_answers_per_new_card` | Odpowiedzi na nową kartę w dniu wprowadzenia; `0` = policz z historii, bez historii 2,5. |
| `reviews_per_new_card` | Powtórki generowane przez nową kartę; `0` = policz z historii, bez historii reguła ×10. |
| `forecast_days` | Okno prognozy w dniach. |
| `split_strategy` | `proportional` zachowuje proporcje talii, `heaviest_first` ścina najpierw największą i zostawia małe w spokoju. |
| `decks` | Talie objęte raportem; puste = wszystkie. Wpisanie talii nadrzędnej obejmuje jej podtalie. |

## Ograniczenia

Raport to arytmetyka na Twoich danych, nie symulacja schedulera. Prognoza
pokazuje terminy już zaplanowanych kart — nie przewiduje powtórek, które
powstaną z kart wprowadzonych w przyszłości; to pokazuje osobno stan
stacjonarny. Karty zaległe liczą się w dniu 0, bo czekają już teraz. Stan
stacjonarny zależy od współczynnika, który przy krótkiej historii jest regułą, a
nie pomiarem — dlatego obciążenie „teraz” i „docelowo” są podane osobno.
