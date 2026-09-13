# Anki Toolkit: Workload

Pomaga utrzymać spokojne tempo nauki, także w słabsze dni. Otwórz
**Narzędzia → Anki Toolkit: Workload…**: na początku zobaczysz plan na dziś,
a szczegóły rozwiniesz przyciskiem **Pokaż szczegóły raportu**.

## Elastyczny czas, spokojne tempo

Domyślnie celujesz w **15 minut**, z górną granicą zwykłego dnia **30 minut**,
i zaczynasz od **3 nowych kart dziennie łącznie**.
Istniejące ustawienia czasu pozostają zachowane. To ostrożny punkt startowy,
nie gwarancja przyszłego obciążenia ani obowiązek wykorzystania całego czasu.

- **Dziś mam łącznie** zmienia czas tylko w otwartym oknie. To czas całego dnia,
  nie dodatkowa sesja. Krótszy dzień (np. 5 minut) oznacza zero nowych kart.
  Zero minut pozwala zaplanować przerwę.
- Dłuższy dzień nie podnosi tempa nowych kart. Nie nadrabiamy opuszczonych porcji.
- Najpierw należne powtórki i nauka rozpoczętych kart; nowe tylko, jeśli zostanie
  zapas. Plan rezerwuje 20% czasu i odejmuje zapisany czas odpowiedzi z dzisiaj.
- Wprowadzone dziś nowe karty odejmują się od dziennej porcji, również po
  ponownym otwarciu okna. **Odśwież** ponownie odczytuje kolekcję.
- Każda zaległość w kartach powtórkowych wstrzymuje nowe. Możesz odrabiać ją
  stopniowo — ograniczenie sesji nie usuwa kart czekających po terminie.
- Podział porcji między talie może wynosić zero. Jego suma nie przekracza porcji
  na dziś. Nadal obowiązują limity i dostępność kart w Anki.

**Dodatek tylko doradza. Nie zatrzymuje sesji, nie zmienia limitów, presetów,
harmonogramu ani kart.** Po osiągnięciu swojego czasu kończysz naukę sam.
Tempo można zmienić w **Ustawienia… → Spokojne tempo nowych/dzień (łącznie)**;
limity Anki pozostają osobnymi ustawieniami w Opcjach talii.

## Propozycja tempa na tydzień

Zwiększenie wymaga dwóch pełnych tygodni kalendarzowych (poniedziałek–niedziela),
z co najmniej pięcioma dniami nauki w każdym. Każdy dzień musi mieścić się w 80%
zwykłego czasu, a tempo wprowadzania musi odpowiadać ustawionemu tempu, bez
jednorazowej dużej porcji. Wtedy raport proponuje **+1**, do ręcznego rozważenia.
Dodatkowa karta nie trafia automatycznie do planu na dziś. Zmiana czasu na dziś
nie zmienia propozycji tygodniowej.

Przekroczenie górnej granicy czasu w którymkolwiek z ostatnich siedmiu
zakończonych dni daje propozycję **−1**. Czas między 15 a 30 minutami nie
jest powodem do zwiększania tempa. Jeśli obecna kolejka zajmuje już 80%
górnej granicy, plan wstrzymuje nowe. Zaległości oznaczają zero nowych. Po tygodniu bez nauki
powrót zaczyna się od najwyżej trzech nowych dziennie. Są to ostrożne heurystyki.

Historia odpowiedzi nie dowodzi, że kończyłeś należne powtórki. Dlatego propozycja
zwiększenia jest warunkowa: skorzystaj z niej tylko, jeśli rzeczywiście kończyłeś
kolejkę bez wysiłku. Dodatek nie przechowuje historycznych stanów zaległości.

## Gdy słówka trudno wchodzą

Plan reaguje przed powstaniem zaległości także na odpowiedzi **Ponownie**.
Przy co najmniej 20 odpowiedziach w ostatnich siedmiu zakończonych dniach:

- od 30% odpowiedzi „Ponownie” proponuje zmniejszenie tempa o jedną kartę,
- od 50% proponuje chwilowo zero nowych.

Wzrost tempa wymaga najwyżej 20% odpowiedzi „Ponownie” w każdym z dwóch
pełnych tygodni. Dzisiejsze rozpoczęte karty zajmują miejsce w budżecie,
a raport pokazuje też czas nauki i ponownej nauki z ostatniego tygodnia.
Te progi są ostrożnymi heurystykami, nie diagnozą jakości kart ani gwarancją,
że nigdy nie pojawi się górka powtórek. Pojedyncza trudna odpowiedź nie
wstrzymuje dopływu.

## Szczegóły i ograniczenia

**Kopiuj raport** kopiuje aktualny plan i tekstowe podsumowanie. Rozwijany raport
pokazuje talie, źródła oszacowań i już zaplanowane terminy.

- Historia i czasy dotyczą wybranych talii; karty z talii filtrowanych są
  przypisane do talii macierzystej. Historia jest przypisywana według obecnego
  położenia kart; usunięte karty nie są uwzględniane.
- Czas z Anki to suma zarejestrowanych czasów odpowiedzi. Nie obejmuje wszystkich
  przerw i może być ograniczony ustawieniami timera. To nie stoper całej sesji.
- Pierwszy wpis nauki w dostępnej historii wyznacza wprowadzenie nowej karty.
  Niepełna historia lub reset kart mogą zaburzać ten pomiar.
- Nauka wewnątrz dnia jest uwzględniana osobno; jej czas jest przybliżeniem.
- Suma `1/interwał` jest wskaźnikiem przy założeniu stałych interwałów, nie
  pomiarem przyszłego obciążenia.
- Scenariusz z sumy limitów i mnożnika powtórek jest orientacyjny. Nie uwzględnia
  ograniczania dopływu przez rodzica. Historyczny iloraz powtórek i nowych kart
  nie jest wiarygodnym kosztem przyszłych kart; nie steruje spokojnym planem.
- Tabela terminów pokazuje każdą kartę tylko raz, bez jej następnych powrotów
  i bez nowych kart wprowadzonych w przyszłości. Do porównania dalszych
  scenariuszy służy wbudowany symulator w Opcjach talii Anki.

## Ustawienia

| Klucz `config.json` | Znaczenie |
|---|---|
| `minutes_per_day` | Zwykły czas jako punkt odniesienia; domyślnie 15 minut. |
| `max_minutes_per_day` | Górna granica zwykłego dnia; domyślnie 30 minut, nie mniej niż zwykły cel. |
| `new_cards_per_day` | Spokojne tempo nowych kart łącznie; domyślnie 3, zero wstrzymuje nowe. |
| `seconds_per_card` | Czas powtórki; `0` = mediana z 30 dni, bez danych 9 s. |
| `learn_seconds_per_card` | Czas odpowiedzi w nauce; `0` = mediana z 30 dni, bez danych 12 s. |
| `learn_answers_per_new_card` | Odpowiedzi w nauce na wprowadzoną kartę; `0` = historia, bez danych 2,5. |
| `reviews_per_new_card` | Mnożnik wyłącznie do scenariusza w szczegółach; `0` = historia od 60 aktywnych dni, wcześniej ×10. |
| `forecast_days` | Okno tabeli już zaplanowanych terminów. |
| `split_strategy` | `proportional` dzieli porcję proporcjonalnie do limitów, `heaviest_first` najpierw zmniejsza największy. Obie strategie dopuszczają zero. |
| `decks` | Talie objęte planem i historią; puste = wszystkie, rodzic obejmuje podtalie. |

Zapis ustawień zachowuje nieznane klucze. Nie powstają dodatkowe pliki z historią
ani nowe zależności produkcyjne.

## Automatyczne limity przez synchronizację

[Workload Service](../workload_service/README.md) to niezależny klient dla AnkiWeb lub własnego
serwera Anki: codziennie analizuje historię i ustawia porcję nowych kart.
Dodatek macOS pozostaje doradczy.

## Co zabiera czas?

W szczegółach raportu i w **Kopiuj raport** znajdziesz pomiar z ostatnich
7 zakończonych dni Anki (bez dzisiaj): łączny czas odpowiedzi oraz czas i udział
kart wprowadzonych w ostatnich 14 zakończonych dniach. Liczymy ich naukę,
powtórki i ponowną naukę, a nie tylko pierwsze pokazanie.

Lista pięciu najbardziej czasochłonnych kart obejmuje wszystkie karty wybranych
talii, także starsze. Pokazuje minuty, liczbę odpowiedzi, liczbę „Ponownie”
i oznaczenie niedawno wprowadzonej karty. Wklej `cid:123…` z raportu do
wyszukiwarki przeglądarki Anki, aby obejrzeć konkretną kartę. Przy częstym
„Ponownie” rozważ uproszczenie pytania, dodanie kontekstu lub rozdzielenie znaczeń.

To diagnostyka, nie nowy próg sterowania limitami. Ranking sam nie dowodzi, że
karta wymaga poprawy. Mierzymy zapisany czas odpowiedzi, nie cały czas sesji
ani przyszły koszt nowej karty. Karty mają różny czas obserwacji. Wprowadzenie
rozpoznajemy, gdy pierwszy dostępny wpis odpowiedzi jest nauką; niepełna historia
może zafałszować wynik. Reset nie odmładza karty z zachowaną starszą historią.
