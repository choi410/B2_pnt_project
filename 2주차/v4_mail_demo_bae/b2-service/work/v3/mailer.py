"""Outgoing mail for customer approval requests.

MAIL_MODE=console (default) prints the mail to the server window instead of sending it.
Settings come from environment variables; b2-service/.env is read when present.
"""
import os, smtplib, ssl, sys
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path

ENV_FILE=Path(__file__).resolve().parents[2]/'.env'


class MailError(Exception):
    """Shown to the PM as-is."""


def load_env(path=ENV_FILE):
    # Real environment variables win; no extra dependency for a KEY=VALUE file.
    if not path.is_file():return
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        line=line.strip()
        if not line or line.startswith('#') or '=' not in line:continue
        key,value=line.split('=',1);key=key.strip();value=value.strip()
        if len(value)>=2 and value[0]==value[-1] and value[0] in '"\'':value=value[1:-1]
        if key:os.environ.setdefault(key,value)


load_env()


def setting(key,default=''):
    return os.environ.get(key,default).strip()


def mode():
    return 'smtp' if setting('MAIL_MODE','console').lower()=='smtp' else 'console'


def send(to,subject,text,html=None):
    if mode()!='smtp':
        out='\n'.join(['','='*60,'[메일 미발송 · MAIL_MODE=console]','받는 사람: '+to,'제목: '+subject,'-'*60,text,'='*60,''])
        encoding=sys.stdout.encoding or 'utf-8'
        print(out.encode(encoding,'replace').decode(encoding),flush=True)
        return
    host,user,password=setting('SMTP_HOST'),setting('SMTP_USER'),setting('SMTP_PASSWORD')
    sender=setting('MAIL_FROM') or user
    try:port=int(setting('SMTP_PORT','587'))
    except ValueError:raise MailError('SMTP_PORT 값을 숫자로 입력해 주세요.')
    if not (host and user and password and sender):
        raise MailError('메일 설정이 비어 있습니다. b2-service/.env 의 SMTP_HOST, SMTP_USER, SMTP_PASSWORD를 확인해 주세요.')
    message=EmailMessage()
    message['Subject']=subject
    message['From']=formataddr((setting('MAIL_FROM_NAME','PNT 회의록 서비스'),sender))
    message['To']=to
    message.set_content(text)
    if html:message.add_alternative(html,subtype='html')
    context=ssl.create_default_context()
    try:
        # 465 is implicit TLS; other ports upgrade with STARTTLS.
        server=smtplib.SMTP_SSL(host,port,timeout=15,context=context) if port==465 else smtplib.SMTP(host,port,timeout=15)
        with server:
            if port!=465:server.starttls(context=context)
            server.login(user,password)
            server.send_message(message)
    except smtplib.SMTPAuthenticationError:
        raise MailError('메일 서버 로그인에 실패했습니다. 계정과 앱 비밀번호, SMTP 사용 설정을 확인해 주세요.')
    except smtplib.SMTPRecipientsRefused:
        raise MailError('받는 사람 주소를 메일 서버가 거부했습니다. 주소를 확인해 주세요.')
    except (smtplib.SMTPException,OSError) as exc:
        raise MailError(f'메일을 보내지 못했습니다. ({exc})')
