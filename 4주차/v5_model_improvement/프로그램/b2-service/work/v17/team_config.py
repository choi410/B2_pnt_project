"""Four-person LAN trial. Empty workspace; existing v1.6 data is never opened."""
import ipaddress,os

PORT=int(os.environ.get('B2_PORT','8776'))
LAN_IP=os.environ.get('B2_TEAM_LAN_IP','').strip()
LAN_CIDR=os.environ.get('B2_TEAM_LAN_CIDR','').strip()
NETWORK=None
if bool(LAN_IP)!=bool(LAN_CIDR):raise RuntimeError('Set both B2_TEAM_LAN_IP and B2_TEAM_LAN_CIDR.')
if LAN_IP:
 address=ipaddress.IPv4Address(LAN_IP);NETWORK=ipaddress.IPv4Network(LAN_CIDR,strict=False)
 private=[ipaddress.IPv4Network(x) for x in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')]
 if not any(NETWORK.subnet_of(x) for x in private) or address not in NETWORK:raise RuntimeError('A matching private LAN address and subnet are required.')

HOSTS=['127.0.0.1','localhost']+([LAN_IP] if LAN_IP else [])
ORIGINS={f'http://{h}:{PORT}' for h in HOSTS}
# Temporary team demo through an HTTPS tunnel (e.g. a Cloudflare quick tunnel that
# forwards to 127.0.0.1). Only this exact host is accepted; unset means loopback only.
PUBLIC_HOST=os.environ.get('B2_PUBLIC_HOST','').strip().lower()
if PUBLIC_HOST:
 import re as _re
 if not _re.fullmatch(r'[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+',PUBLIC_HOST):raise RuntimeError('B2_PUBLIC_HOST must be a bare host name such as abc.trycloudflare.com.')
 HOSTS.append(PUBLIC_HOST);ORIGINS.add(f'https://{PUBLIC_HOST}')
if os.environ.get('B2_TEAM_TESTING')=='1':HOSTS+=['testserver'];ORIGINS.add('http://testserver')

def allowed_client(value):
 if value=='testclient':return os.environ.get('B2_TEAM_TESTING')=='1'
 try:
  address=ipaddress.ip_address(value)
  return address.is_loopback or bool(NETWORK and address in NETWORK)
 except ValueError:return False

PEOPLE=[
 {'id':'team1','name':'김양일','department':'마스-1','position':'PM','level':'leader'},
 {'id':'team2','name':'진효창','department':'마스-1','position':'담당자','level':'staff'},
 {'id':'team3','name':'배근우','department':'마스-1','position':'담당자','level':'staff'},
 {'id':'team4','name':'최인혁','department':'마스-1','position':'담당자','level':'staff'},
]

def initialize_people(w,c):
 c.execute('CREATE TABLE IF NOT EXISTS workspace_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
 if c.execute("SELECT 1 FROM workspace_meta WHERE key='team_initialized'").fetchone():return
 # Refuse an unintended existing workspace rather than resetting or mixing its data.
 if c.execute('SELECT COUNT(*) FROM records').fetchone()[0]:raise RuntimeError('The team trial needs a separate empty database.')
 for person in PEOPLE:
  w.save(c,'person',person)
  salt=w.secrets.token_hex(16)
  c.execute('INSERT INTO users VALUES(?,?,?)',(person['id'],salt,w.digest(w.secrets.token_urlsafe(32),salt)))
 c.execute("INSERT INTO workspace_meta VALUES('team_initialized','1')")
