"""Manual isolated smoke check: python tests/workload_dashboard_smoke.py (port 8080, anki installed)."""
import json, os, re, subprocess, sys, tempfile, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

URL = 'http://localhost:8080'


def post(path, form, expect=200):
    try:
        response = urllib.request.urlopen(URL + path, data=urllib.parse.urlencode(form, doseq=True).encode())
        status, body = response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        status, body = error.code, error.read().decode()
    assert status == expect, (path, status)
    return body


with tempfile.TemporaryDirectory() as folder:
    data = Path(folder)
    (data / 'decks.json').write_text(json.dumps(['English', 'English::Words']))
    process = subprocess.Popen([sys.executable, str(Path(__file__).resolve().parents[1] / 'workload_service' / 'worker.py'),
                                'dashboard', '--data', folder], env=os.environ.copy())
    try:
        for _ in range(50):
            try:
                html = urllib.request.urlopen(URL + '/').read().decode(); break
            except OSError: time.sleep(.1)
        token = re.search('name="token" value="([^"]+)"', html)[1]
        assert 'Pierwsze kroki' in html and 'value="English::Words"' in html
        post('/run', {'token': 'bad'}, 403)
        plan = {'token': token, 'deck': ['English'], 'run_at': '06:30', 'minutes_per_day': '15',
                'max_minutes_per_day': '30', 'new_cards_per_day': '3', 'split_strategy': 'proportional',
                'seconds_per_card': '0', 'learn_seconds_per_card': '0', 'learn_answers_per_new_card': '0'}
        assert 'Zapisano ustawienia planu' in post('/plan', plan)
        settings = json.loads((data / 'settings.json').read_text())
        assert settings['run_at'] == '06:30' and settings['decks'] == ['English'] and not settings['apply']
        assert 'Górna granica czasu nie może' in post('/plan', {**plan, 'max_minutes_per_day': '10'}, 400)
        assert 'Podaj hasło Anki' in post('/account', {'token': token, 'url': 'ankiweb', 'username': 'me'}, 400)
        mail = {'token': token, 'host': 'smtp.test', 'port': '587', 'security': 'starttls',
                'sender': 'a@example.test', 'recipient': 'b@example.test', 'password': 'mail-secret'}
        post('/mail', mail)
        assert (data / 'mail.json').stat().st_mode & 0o777 == 0o600
        assert 'mail-secret' not in urllib.request.urlopen(URL + '/').read().decode()
        post('/run', {'token': token})
        for _ in range(100):
            if (data / 'history.json').exists(): break
            time.sleep(.1)
        history = json.loads((data / 'history.json').read_text())
        assert history[-1]['status'] == 'error' and history[-1]['error'] == 'Najpierw połącz konto Anki'
        assert json.loads(urllib.request.urlopen(URL + '/status').read())['running'] is False
        print('PASS: onboarding, plan validation, account, mail, CSRF, run button, status')
    finally:
        process.terminate(); process.wait()
