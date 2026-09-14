"""SMTP reports for every completed run; no Anki or Qt dependencies."""
from datetime import datetime
from html import escape
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



def summary_html(event):
    ok = event['status'] == 'success'
    confirmed = ok and event.get('apply')
    changes = event.get('changes', [])
    finished = datetime.fromisoformat(event['finished']).strftime('%d.%m.%Y · %H:%M')
    parts = ['<!doctype html><html lang="pl"><head><meta name="viewport" content="width=device-width, initial-scale=1"></head>'
             '<body style="margin:0;padding:16px;background:#f3f5f7;color:#17212b;font-family:Arial,sans-serif">'
             '<div style="max-width:600px;margin:auto;background:#fff;padding:16px;border-radius:12px">',
             '<h1 style="font-size:22px;margin:0 0 8px">Anki Workload</h1>',
             f'<p style="color:#526170">{escape(finished)}</p>',
             '<p><strong>' + ('Przebieg zakończony' if ok else 'Błąd przebiegu') + '</strong> · '
             + ('zapis limitów' if event.get('apply') else 'symulacja') + '</p>',
             f"<p>Operacja: {escape(event['command'])}</p>",
             f"<p>{escape(event.get('reason', ''))}</p>"]
    if not ok:
        parts.append(f"<p>{escape(event.get('error', 'Nieznany błąd'))}</p>"
                     '<p>Zmiany nie są potwierdzone; część mogła trafić na serwer.</p>')
    elif not changes:
        parts.append('<p>Brak zmian limitów. Usługa wykonała przebieg.</p>')
    if changes:
        parts.append('<h2 style="font-size:18px">' + ('Zmiany potwierdzone' if confirmed else 'Planowane zmiany') + '</h2>'
                     '<table style="width:100%;table-layout:fixed;border-collapse:collapse;font-size:14px">'
                     '<tr><th scope="col" style="width:54%;text-align:left;padding:8px 4px">Talia</th>'
                     '<th scope="col" style="width:23%">Przed</th><th scope="col" style="width:23%">Po</th></tr>')
        names = {change['deck'] for change in changes}
        zero_base = all(change[key].get('newLimit') == 0 for change in changes for key in ('before', 'after'))
        for change in changes:
            name = change['deck']
            parent, separator, leaf = name.rpartition('::')
            label = '↳ ' + leaf if separator and parent in names else name
            parts.append(f'<tr><th scope="row" style="text-align:left;padding:12px 4px;border-top:1px solid #e2e7ec;overflow-wrap:anywhere;word-wrap:break-word">{escape(label)}</th>')
            for key in ('before', 'after'):
                value = change[key]
                daily = value.get('newLimitToday')
                text = escape(str(daily['limit'])) if daily else 'brak'
                if not zero_base:
                    base = value.get('newLimit')
                    text += '<br><small>Bazowy: ' + escape(str(base) if base is not None else 'z presetu') + '</small>'
                parts.append(f'<td style="text-align:center;padding:12px 4px;border-top:1px solid #e2e7ec;overflow-wrap:anywhere">{text}</td>')
            parts.append('</tr>')
        parts.append('</table><p style="font-size:12px;color:#526170">Dzienne limity nowych kart. '
                     + ('Limit bazowy wszystkich pokazanych talii: 0. ' if zero_base else '')
                     + '„brak” oznacza brak nadpisania dziennego.</p>')
        if confirmed:
            parts.append('<p>Zsynchronizuj Anki na swoim urządzeniu, aby pobrać limity.</p>')
    parts.append('</div></body></html>')
    return ''.join(parts)


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
    message.add_alternative(summary_html(event), subtype='html')
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
