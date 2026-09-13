# Anki Toolkit: Integrations

Pełna integracja z kolejką n8n: panel 📚 przy oknie Dodaj, adres domowy i
fallback Tailscale, odhaczanie wierszy po dodaniu karty, zakładki słowników oraz
lokalny Web Bridge wpisujący dane do otwartej notatki.

Ustawienia: **Narzędzia → Anki Toolkit: Integrations → Ustawienia…**.

Mostek zapisuje bufor edytora przed wypełnieniem pól. Żądanie jest związane
z konkretną notatką i profilem; timeout anuluje oczekującą zmianę.
Przy zmianie słowa w rozpoczętej notatce panel pyta o zgodę i zachowuje inne pola.
Tasowanie i odświeżanie zachowują aktualnie wybraną pozycję, jeśli nadal istnieje.

Wiersz jest automatycznie odhaczany tylko po dodaniu notatki powiązanej z tą
pozycją i z odpowiadającym jej hasłem. Jeśli zmienisz formę hasła, np. z
„sprawling” na „sprawl”, użyj ręcznie **Zrobione →**. Checkbox jest blokowany
na czas zapisu; brak trafionego wiersza jest błędem, a nie sukcesem.
Odświeżenie listy jest dostępne po zakończeniu zapisów. Po zmianie ustawień
zamknij całe okno Dodaj i otwórz panel ponownie; zapamiętany adres n8n jest
używany wyłącznie, jeśli nadal znajduje się w aktualnej konfiguracji.
