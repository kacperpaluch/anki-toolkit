"""Manual isolated smoke check: python tests/workload_dashboard_smoke.py (port 8080, anki installed)."""
import subprocess, sys, tempfile, os, time, urllib.request, urllib.error, urllib.parse, re, json
from pathlib import Path
with tempfile.TemporaryDirectory() as folder:
    env={**os.environ,'WORKLOAD_CONFIG':'{"decks":["test"]}','ANKI_SYNC_URL':'invalid'}
    process=subprocess.Popen([sys.executable,str(Path(__file__).resolve().parents[1] / 'workload_service' / 'worker.py'),'dashboard','--data',folder],env=env)
    try:
        for _ in range(50):
            try:
                html=urllib.request.urlopen('http://localhost:8080/').read().decode(); break
            except OSError: time.sleep(.1)
        token=re.search('name="token" value="([^"]+)"',html)[1]
        try: urllib.request.urlopen('http://localhost:8080/run',data=b'token=bad'); raise AssertionError('CSRF accepted')
        except urllib.error.HTTPError as e: assert e.code==403
        form={'token':token,'url':'ankiweb','username':'test@example.com','password':'',
              'run_at':'06:30','minutes_per_day':'15','max_minutes_per_day':'30',
              'new_cards_per_day':'3','decks':'English'}
        urllib.request.urlopen('http://localhost:8080/settings',data=urllib.parse.urlencode(form).encode()).read()
        settings=json.loads((Path(folder)/'settings.json').read_text())
        assert settings['run_at']=='06:30' and settings['decks']==['English']
        assert 'password' not in (Path(folder)/'connection.json').read_text()
        mail={'token':token,'host':'smtp.test','port':'587','security':'starttls',
              'sender':'a@example.test','recipient':'b@example.test','password':'mail-secret'}
        urllib.request.urlopen('http://localhost:8080/mail',data=urllib.parse.urlencode(mail).encode()).read()
        assert json.loads((Path(folder)/'mail.json').read_text())['password']=='mail-secret'
        assert (Path(folder)/'mail.json').stat().st_mode & 0o777 == 0o600
        assert 'mail-secret' not in urllib.request.urlopen('http://localhost:8080/').read().decode()
        urllib.request.urlopen('http://localhost:8080/run',data=('token='+token).encode()).read()
        for _ in range(50):
            if (Path(folder)/'history.json').exists(): break
            time.sleep(.1)
        history=json.loads((Path(folder)/'history.json').read_text())
        assert history[-1]['status']=='error'
        assert history[-1]['command']=='run'
        print('PASS: dashboard, CSRF rejection, button starts worker, error recorded')
    finally: process.terminate(); process.wait()
