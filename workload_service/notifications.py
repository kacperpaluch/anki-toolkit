"""SMTP reports for every completed run; no Anki or Qt dependencies."""
from email.message import EmailMessage
from email.utils import parseaddr
import smtplib
import ssl


def settings_from(form, previous):
    get = lambda name: form.get(name, [''])[0].strip()
    config = {**previous, 'enabled': 'enabled' in form,
              'host': get('host'), 'port': int(get('port') or 587),
              'security': get('security') or 'starttls', 'username': get('username'),
              'sender': get('sender'), 'recipient': get('recipient')}
    password = form.get('password', [''])[0]
    if password:
        config['password'] = password
    if 'clear_password' in form:
        config['password'] = ''
    if not 1 <= config['port'] <= 65535 or config['security'] not in ('starttls', 'ssl', 'none'):
        raise ValueError('Niepoprawny port lub tryb SMTP')
    if config['enabled']:
        if not config['host']:
            raise ValueError('Podaj host SMTP')
        for key in ('sender', 'recipient'):
            value = config[key]
            if '\r' in value or '\n' in value or '@' not in parseaddr(value)[1]:
                raise ValueError('Podaj poprawny adres nadawcy i odbiorcy')
    return config


def limit_text(value):
    base = value.get('newLimit')
    daily = value.get('newLimitToday')
    return (f"bazowy: {base if base is not None else 'z presetu'}, "
            f"limit dnia: {daily['limit'] if daily else 'brak nadpisania'}")


def send_summary(config, event):
    if not config.get('enabled') or event['command'] not in ('run', 'restore'):
        return 'not_needed'
    message = EmailMessage()
    ok = event['status'] == 'success'
    message['Subject'] = 'Anki Workload — ' + ('przebieg zakończony' if ok else 'błąd przebiegu')
    message['From'] = config['sender']
    message['To'] = config['recipient']
    lines = [f"Zakończenie: {event['finished']}", f"Operacja: {event['command']}",
             'Wynik: ' + ('sukces' if ok else 'błąd'),
             'Tryb: ' + ('zapis limitów' if event.get('apply') else 'symulacja'),
             event.get('reason', ''), '']
    if not ok:
        lines.extend([event.get('error', 'Nieznany błąd'),
                      'Zmiany nie są potwierdzone; część mogła trafić na serwer.', ''])
    elif not event.get('changes'):
        lines.append('Brak zmian limitów. Usługa wykonała przebieg.')
    lines.append('Zmiany potwierdzone:' if ok and event.get('apply') else 'Planowane zmiany:')
    for change in event.get('changes', []):
        lines.extend([change['deck'], f"Przed: {limit_text(change['before'])}",
                      f"Po: {limit_text(change['after'])}", ''])
    if ok and event.get('apply') and event.get('changes'):
        lines.append('Zmiany zostały zsynchronizowane. Zsynchronizuj Anki na swoim urządzeniu, aby je pobrać.')
    message.set_content('\n'.join(lines))
    context = ssl.create_default_context()
    smtp = smtplib.SMTP_SSL if config['security'] == 'ssl' else smtplib.SMTP
    kwargs = {'timeout': 20}
    if config['security'] == 'ssl':
        kwargs['context'] = context
    with smtp(config['host'], config['port'], **kwargs) as client:
        if config['security'] == 'starttls':
            client.starttls(context=context)
        if config.get('username'):
            client.login(config['username'], config.get('password', ''))
        refused = client.send_message(message)
        if refused:
            raise smtplib.SMTPRecipientsRefused(refused)
    return 'sent'
