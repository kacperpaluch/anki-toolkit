"""SMTP summaries for confirmed limit changes; no Anki or Qt dependencies."""
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
    if not config.get('enabled') or event['status'] != 'success' or not event.get('apply') or not event.get('changes'):
        return 'not_needed'
    message = EmailMessage()
    message['Subject'] = 'Anki Workload — zmieniono limity nowych kart'
    message['From'] = config['sender']
    message['To'] = config['recipient']
    lines = [f"Zakończenie: {event['finished']}", f"Operacja: {event['command']}", event.get('reason', ''), '']
    for change in event['changes']:
        lines.extend([change['deck'], f"Przed: {limit_text(change['before'])}",
                      f"Po: {limit_text(change['after'])}", ''])
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
