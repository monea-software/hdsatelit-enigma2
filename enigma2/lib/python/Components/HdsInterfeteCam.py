# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Interfetele web ale cam-urilor de pe receptor, aflate la rulare. Doar in imaginea HDSatelit.

Singura sursa pentru pagina „Interfețe CAM” din interfata web (HdsWebControl) si pentru orice ecran de pe televizor
care ar arata aceeasi lista.

Regula de baza: in fisierul acesta nu se scrie numele niciunui cam, niciun port al vreunui cam si nicio cale care
tine de un anumit cam. Un cam se recunoaste dupa semne pe care le are orice cam, iar numele aratat il da cam-ul insusi.
Semnele unui proces:
  S1  asculta pe /tmp/camd.socket: enigma2 se leaga acolo ca client ca sa ceara decriptarea (lib/dvb/pmt.cpp);
  S2  tine deschis cititorul de card (/dev/sci*) sau /dev/dvb/adapter*/ca*, fara sa tina un frontend (un cam nu
      acordeaza tunerul; un server de flux care acordeaza singur nu e cam);
  S3  executabilul lui e un fisier al unui pachet instalat din categoria opkg a modulelor de acces sau al pachetului
      care a pus un script de modul in /etc/init.d (<fel>.<x>, felurile dupa forma, vezi DOSAR_SCRIPTURI);
  S4  executabilul lui e scris (cu variabilele simple desfacute) intr-un script de modul /etc/init.d/<fel>.<x>,
      altul decat locul gol, si nu e al unui pachet strain de cam-uri.
Se scot mereu: procesul in care rulam (enigma2), pid 1 si firele nucleului. Copiii unui cam intra cu el. Apar si
cam-urile instalate, dar oprite (scripturile si pachetele de mai sus), fara interfete.

Porturile: /proc/net/tcp si tcp6, starea 0A (asculta), legate de proces prin inode-urile din /proc/<pid>/fd. Porturile
procesului propriu (deci si ale interfetei noastre) nu intra.

Proba HTTP, pe fiecare port, pe un fir al ei, numai spre adresa receptorului insusi, numai citire:
  1. conectare cu limita de timp;
  2. asteptare fara sa trimitem nimic: un port care vorbeste primul (partajare de card) nu e web si nu primeste
     niciun octet de la noi (asa nu apare in jurnalul cam-ului nicio logare gresita);
  3. un singur GET /, cel mult 16 KB, cu termen;
  4. o reincercare TLS, cand raspunsul e o alerta TLS sau conexiunea se inchide;
  5. cel mult o redirectionare, pe aceeasi gazda si acelasi port.
Numele unei interfete: titlul paginii la 2xx; la 401/403 antetul Server, apoi realm (titlul unei pagini de eroare nu
spune ce program e); altfel Server. Numele cam-ului: titlul paginii lui (2xx); apoi descrierea din scriptul lui de
pornire sau din pachetul lui; apoi Server sau realm de la o interfata care cere parola; apoi sufixul scriptului,
numele pachetului, numele procesului (/proc/<pid>/comm). Descrierea trece inaintea antetelor pentru ca, la o
interfata cu parola, antetele sunt de obicei generice. E text
venit din alt program: se arata numai ca text, niciodata ca HTML.

Nu porneste si nu opreste nimic, nu scrie nimic pe disc, nu citeste fisierele de configurare ale cam-urilor si nu
trimite nimic in afara receptorului. Tot ce e lent se face pe un fir separat (cautare()), cu limite de timp, iar
rezultatul se tine cateva secunde. Modulul nu depinde de enigma, ca sa poata fi incercat pe PC (clasa Sistem)."""
import copy
import html
import os
import posixpath
import re
import socket
import struct
import sys
import threading
import time
try:
	from urllib.parse import urljoin, urlsplit
except ImportError:  # Python 2 (doar pentru teste vechi)
	from urlparse import urljoin, urlsplit
try:
	from Components.HdsPachete import Configurare, categorie_din_nume, citeste_configurarea, nume_scurt, nume_valid, \
		strofe_din_text
except ImportError:  # probe pe PC: modulul incarcat singur, din dosarul Components
	from HdsPachete import Configurare, categorie_din_nume, citeste_configurarea, nume_scurt, nume_valid, strofe_din_text

# ceasul pentru termene: ora receptorului sare la pornire (TDT, NTP)
_ceas = getattr(time, 'monotonic', time.time)

# ---------------------------------------------------------------- caile: ale sistemului si ale enigma2, niciuna a unui cam

# enigma2 se leaga aici ca client ca sa ceara decriptarea (lib/dvb/pmt.cpp); cam-ul care decripteaza asculta aici
SOCKET_DECRIPTARE = '/tmp/camd.socket'
# exista cand un cam decripteaza acum (il scriu cam-urile; nu spune care)
FISIER_ECM = '/tmp/ecm.info'
# Felurile modulelor de acces (conventia OE-A), gasite dupa forma, fara niciun nume scris aici: in DOSAR_SCRIPTURI un
# fel e un nume N pentru care imaginea a pus locul gol N.<SUFIX_GOL> sau pentru care N e legatura alegerii spre un
# script N.<x> din acelasi dosar; modulele felului sunt scripturile N.<x> (x altul decat SUFIX_GOL), puse de pachetele
# lor. Numele felurilor le da receptorul, la rulare (feluri, feluri_din_nume). Felul al carui nume se termina in "cam"
# (TIPAR_FEL_PRINCIPAL, ca regula numelor din HdsImportSurse) e al modulelor obisnuite si vine primul; celelalte
# (serverele de carduri) dupa el, in ordinea numelui.
DOSAR_SCRIPTURI = '/etc/init.d'
SUFIX_GOL = 'None'
TIPAR_FEL_PRINCIPAL = re.compile(r'cam$', re.I)
_NUME_FEL = re.compile(r'^[A-Za-z][A-Za-z0-9_-]{0,31}$')
# categoria pachetelor modulelor de acces (cheia data de Components/HdsPachete.py, categorie_din_nume, care o
# recunoaste dupa forma cuvantului din numele pachetului)
CATEGORIE_ACCES = 'acces'
PREFIX_PLUGIN = 'enigma2-plugin-'
DOSAR_PLUGINURI = '/usr/lib/enigma2/python/Plugins/'

_CITITOR_CARD = re.compile(r'^/dev/sci\d+$')
_CA = re.compile(r'^/dev/dvb/adapter\d+/ca\d+$')
_FRONTEND = re.compile(r'^/dev/dvb/adapter\d+/frontend\d+$')

# ---------------------------------------------------------------- limite

LIMITA_CONECTARE = 0.5       # secunde, conectarea la un port
ASTEPTARE_TACERE = 0.3       # secunde de asteptare fara sa trimitem nimic (un port care vorbeste primul nu e web)
LIMITA_CITIRE = 1.5          # secunde pentru raspuns (si pentru reincercarea TLS, si pentru redirectionare)
LIMITA_CAUTARE = 8.0         # secunde pentru toata cautarea; ce nu apuca sa fie verificat ramane „neverificat”
MEMORARE = 20.0              # secunde cat se foloseste rezultatul fara o cautare noua
OCTETI_MAXIM = 16 * 1024     # cat se citeste cel mult dintr-un raspuns
PORTURI_MAXIM = 12           # cate porturi se verifica cel mult intr-o cautare
NUME_MAXIM = 80              # semne intr-un nume aratat
PROCESE_MAXIM = 4000
FD_MAXIM = 4096              # descriptori cititi cel mult pe proces
SCRIPT_MAXIM = 64 * 1024
LISTA_MAXIM = 1024 * 1024    # un fisier info/<pachet>.list
TEXT_MAXIM = 4 * 1024 * 1024  # /proc/net/*, starea opkg

_REDIRECTARI = (301, 302, 303, 307, 308)
_PORT_IMPLICIT = {'http': 80, 'https': 443}
_GAZDE_LOCALE = ('127.0.0.1', '::1', 'localhost')


def _cale(radacina, p):
	if not radacina or radacina == '/':
		return p
	return os.path.join(radacina, p.lstrip('/'))


class Sistem(object):
	"""Toate citirile din sistem trec pe aici. Pe receptor: radacina '/', pid_propriu = procesul in care rulam
	(enigma2). La probe se inlocuieste cu un sistem fals (un /proc din dictionare)."""

	def __init__(self, radacina='/', pid_propriu=None):
		self.radacina = radacina or '/'
		self.pid_propriu = os.getpid() if pid_propriu is None else pid_propriu

	def cale(self, p):
		return _cale(self.radacina, p)

	def listeaza(self, p):
		return os.listdir(self.cale(p))

	def legatura(self, p):
		return os.readlink(self.cale(p))

	def citeste(self, p, maxim=TEXT_MAXIM):
		with open(self.cale(p), 'rb') as fh:
			return fh.read(maxim).decode('utf-8', 'replace')

	def exista(self, p):
		return os.path.lexists(self.cale(p))

	def executabil(self, p):
		c = self.cale(p)
		return os.path.isfile(c) and os.access(c, os.X_OK)

	def tinta(self, p):
		"""calea fara legaturi, ca os.path.realpath, dar prin legatura(): merge si cu sistemul fals"""
		parti = [x for x in p.split('/') if x]
		rez = '/'
		sarituri = 0
		while parti:
			x = parti.pop(0)
			if x == '.':
				continue
			if x == '..':
				rez = posixpath.dirname(rez)
				continue
			urm = posixpath.join(rez, x)
			try:
				t = self.legatura(urm)
			except (OSError, ValueError):
				rez = urm
				continue
			sarituri += 1
			if sarituri > 32:  # bucla de legaturi
				return urm
			if t.startswith('/'):
				rez = '/'
			parti = [y for y in t.split('/') if y] + parti
		return rez


# ---------------------------------------------------------------- /proc

def adresa_din_hex(h, ordine=None):
	"""Adresa din /proc/net/tcp si tcp6. Nucleul scrie fiecare cuvant de 32 de biti in ordinea procesorului
	(pe un receptor ARM: 127.0.0.1 = 0100007F)."""
	f = '<I' if (ordine or sys.byteorder) == 'little' else '>I'
	if len(h) == 8:
		return socket.inet_ntop(socket.AF_INET, struct.pack(f, int(h, 16)))
	if len(h) == 32:
		octeti = b''.join(struct.pack(f, int(h[i:i + 8], 16)) for i in range(0, 32, 8))
		return socket.inet_ntop(socket.AF_INET6, octeti)
	raise ValueError(h)


def porturi_in_ascultare(sistem, ordine=None):
	"""{inode: (adresa, port)} pentru socket-urile TCP care asculta (starea 0A), din /proc/net/tcp si tcp6"""
	rez = {}
	for f in ('/proc/net/tcp', '/proc/net/tcp6'):
		try:
			text = sistem.citeste(f)
		except (OSError, IOError):
			continue
		for r in text.splitlines()[1:]:
			c = r.split()
			if len(c) < 10 or c[3] != '0A':
				continue
			try:
				h, p = c[1].split(':')
				inode = int(c[9])
				if inode:
					rez[inode] = (adresa_din_hex(h, ordine), int(p, 16))
			except (ValueError, OSError, struct.error):
				continue
	return rez


def inode_decriptare(sistem):
	"""inode-urile socket-urilor unix cu calea SOCKET_DECRIPTARE: cel care asculta si cele acceptate de la enigma2
	(capatul enigma2 al legaturii n-are cale)"""
	rez = set()
	try:
		text = sistem.citeste('/proc/net/unix')
	except (OSError, IOError):
		return rez
	for r in text.splitlines()[1:]:
		c = r.split()
		if len(c) >= 8 and c[7] == SOCKET_DECRIPTARE:
			try:
				rez.add(int(c[6]))
			except ValueError:
				pass
	return rez


class Proces(object):
	__slots__ = ('pid', 'ppid', 'exe', 'comm', 'socketuri', 'dispozitive')

	def __init__(self, pid):
		self.pid = pid
		self.ppid = 0
		self.exe = ''
		self.comm = ''
		self.socketuri = set()     # inode-uri
		self.dispozitive = set()   # /dev/...


def _ppid(stat):
	# /proc/<pid>/stat: "pid (comm) stare ppid ..."; comm poate avea spatii si paranteze
	try:
		return int(stat[stat.rindex(')') + 1:].split()[1])
	except (ValueError, IndexError):
		return 0


def citeste_proces(sistem, pid):
	"""Procesul, sau None pentru firele nucleului (fara exe) si pentru procesele care au iesit intre timp."""
	baza = '/proc/%d' % pid
	try:
		exe = sistem.legatura(baza + '/exe')
	except (OSError, ValueError):
		return None
	p = Proces(pid)
	if exe.endswith(' (deleted)'):
		exe = exe[:-len(' (deleted)')]
	p.exe = exe
	try:
		p.comm = sistem.citeste(baza + '/comm', 256).strip()
	except (OSError, IOError):
		pass
	try:
		p.ppid = _ppid(sistem.citeste(baza + '/stat', 4096))
	except (OSError, IOError):
		pass
	try:
		fds = sistem.listeaza(baza + '/fd')
	except OSError:
		fds = []
	for fd in fds[:FD_MAXIM]:
		try:
			t = sistem.legatura(baza + '/fd/' + fd)
		except (OSError, ValueError):
			continue
		if t.startswith('socket:['):
			try:
				p.socketuri.add(int(t[8:-1]))
			except ValueError:
				pass
		elif t.startswith('/dev/'):
			p.dispozitive.add(t)
	return p


def citeste_procese(sistem):
	"""{pid: Proces}, fara pid 1 si fara firele nucleului (procesul propriu e inclus: de la el se iau porturile de scos)"""
	try:
		pids = sorted(int(x) for x in sistem.listeaza('/proc') if x.isdigit())
	except OSError:
		return {}
	rez = {}
	for pid in pids[:PROCESE_MAXIM]:
		if pid == 1:
			continue
		p = citeste_proces(sistem, pid)
		if p is not None:
			rez[pid] = p
	return rez


# ---------------------------------------------------------------- felurile si scripturile modulelor (<fel>.<x>)

_ANTET = re.compile(r'^#[ \t]*(Short-Description|Description)[ \t]*:[ \t]*(.*)$', re.M)
_ATRIBUIRE = re.compile(r'''^[ \t]*(?:export[ \t]+|readonly[ \t]+|local[ \t]+)?([A-Za-z_][A-Za-z0-9_]*)=("[^"\n]*"|'[^'\n]*'|[^\s;&|#]*)''', re.M)
_VARIABILA = re.compile(r'\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))')
_CALE_ABSOLUTA = re.compile(r'(?<![A-Za-z0-9_./$-])(/[A-Za-z0-9_.+-][A-Za-z0-9_.+/-]*)')


def feluri_din_nume(nume, legatura):
	"""Felurile modulelor de acces, in ordinea de aratat, din numele aflate in DOSAR_SCRIPTURI (vezi DOSAR_SCRIPTURI).
	`legatura(n)`: tinta legaturii DOSAR_SCRIPTURI/n, sau None cand n nu e o legatura. Un nume N e fel cand exista
	N.<SUFIX_GOL> sau cand N arata spre un script N.<x>; scripturile altor programe (rc.local, *.sh, inetd.busybox)
	nu au nici locul gol, nici legatura, deci nu intra."""
	toate = set(nume)
	candidati = set()
	for n in toate:
		c = n.split('.', 1)[0]       # prefixul unui script N.<x> sau legatura N insasi
		if _NUME_FEL.match(c):
			candidati.add(c)
	rez = []
	for c in candidati:
		if c + '.' + SUFIX_GOL in toate:
			rez.append(c)
			continue
		t = legatura(c)
		if t:
			b = posixpath.basename(t)
			if b.startswith(c + '.') and len(b) > len(c) + 1:
				rez.append(c)
	rez.sort(key=lambda f: (not TIPAR_FEL_PRINCIPAL.search(f), f.lower(), f))
	return rez


def feluri(sistem):
	"""Felurile modulelor de acces de pe receptor (feluri_din_nume pe DOSAR_SCRIPTURI); [] cand dosarul nu se citeste."""
	try:
		nume = sistem.listeaza(DOSAR_SCRIPTURI)
	except OSError:
		return []

	def legatura(n):
		try:
			return sistem.legatura(DOSAR_SCRIPTURI + '/' + n)
		except (OSError, ValueError):
			return None
	return feluri_din_nume(nume, legatura)


def e_script_modul(nume, feluri_):
	"""<fel>.<x> pentru un fel din `feluri_`, altul decat locul gol"""
	for f in feluri_:
		if nume.startswith(f + '.') and len(nume) > len(f) + 1:
			return nume[len(f) + 1:] != SUFIX_GOL
	return False


def _desface(text, valori):
	return _VARIABILA.sub(lambda m: valori.get(m.group(1) or m.group(2), m.group(0)), text)


def variabile_script(text):
	"""atribuirile simple din script (VAR=valoare, fara $( ) si fara `), cu variabilele de dinainte desfacute"""
	valori = {}
	for m in _ATRIBUIRE.finditer(text):
		v = m.group(2)
		simplu = v[:1] == "'"
		if v[:1] in ('"', "'"):
			v = v[1:-1]
		if '$(' in v or '`' in v:
			continue
		valori[m.group(1)] = v if simplu else _desface(v, valori)
	return valori


class Script(object):
	__slots__ = ('nume', 'cale', 'sufix', 'descriere', 'cai', 'interpretor', 'ales')

	def __init__(self, nume):
		self.nume = nume
		self.cale = DOSAR_SCRIPTURI + '/' + nume
		self.sufix = nume.split('.', 1)[1]
		self.descriere = ''
		self.cai = {}              # calea scrisa in script (executabila) -> calea fara legaturi
		self.interpretor = ''      # #!: calea fara legaturi
		self.ales = False          # legatura alegerii felului lui arata spre el


def citeste_script(sistem, nume):
	s = Script(nume)
	try:
		text = sistem.citeste(s.cale, SCRIPT_MAXIM)
	except (OSError, IOError):
		return s
	antet = {}
	for m in _ANTET.finditer(text):
		if m.group(2).strip():
			antet.setdefault(m.group(1), m.group(2).strip())
	valori = variabile_script(text)
	s.descriere = antet.get('Short-Description') or antet.get('Description') or valori.get('DESC', '')
	cai = set()
	for m in _CALE_ABSOLUTA.finditer(_desface(text, valori)):
		c = m.group(1).rstrip('/')
		if c:
			cai.add(c)
		if len(cai) >= 200:
			break
	for c in sorted(cai):
		if sistem.executabil(c):
			s.cai[c] = sistem.tinta(c)
	if text.startswith('#!'):
		prima = text[2:].split('\n', 1)[0].split()
		if prima:
			s.interpretor = sistem.tinta(prima[0])
	return s


def citeste_scripturi(sistem, feluri_=None):
	"""{nume: Script} pentru scripturile modulelor /etc/init.d/<fel>.<x>, fara locul gol; `ales` dupa legatura
	alegerii fiecarui fel. `feluri_`: feluri(sistem) cand lipseste."""
	if feluri_ is None:
		feluri_ = feluri(sistem)
	try:
		nume = sorted(n for n in sistem.listeaza(DOSAR_SCRIPTURI) if e_script_modul(n, feluri_))
	except OSError:
		return {}
	rez = dict((n, citeste_script(sistem, n)) for n in nume)
	for l in feluri_:
		try:
			t = posixpath.basename(sistem.legatura(DOSAR_SCRIPTURI + '/' + l))
		except (OSError, ValueError):
			continue
		if t in rez:
			rez[t].ales = True
	return rez


def _scriptul_porneste(script, proces):
	"""True cand procesul e unul pornit de script: executabilul lui e scris in script. O cale care e o legatura spre
	executabil se socoteste numai cand procesul poarta numele ei (comm): o unealta cu mai multe nume (/bin/sleep ->
	busybox) nu face din orice alt proces al ei un cam."""
	if proces.exe == script.interpretor:
		return False
	for scris, tinta in script.cai.items():
		if scris == proces.exe:
			return True
		if tinta == proces.exe and posixpath.basename(scris)[:15] == proces.comm[:15]:
			return True
	return False


# ---------------------------------------------------------------- pachetele (fisierele opkg, fara sa pornim opkg)

def _dependente(text):
	rez = []
	for parte in (text or '').split(','):
		n = parte.split('|', 1)[0].strip().split(' ', 1)[0].split('(', 1)[0].strip()
		if n and n not in rez:
			rez.append(n)
	return rez


def _e_executabil(sistem, cale, mod):
	if cale.startswith(DOSAR_SCRIPTURI + '/'):
		return False
	if mod:
		try:
			m = int(mod, 8)
		except ValueError:
			m = None
		if m is not None:
			return (m & 0o170000) == 0o100000 and bool(m & 0o111)
	return sistem.executabil(cale)


class Opkg(object):
	"""Ce trebuie aici din fisierele opkg: pachetele instalate, cine tine caile cautate, pachetele de cam-uri."""

	def __init__(self):
		self.instalate = {}         # nume -> [dependente]
		self.proprietar = {}        # cale (doar cele cautate) -> pachet
		self.pachete_cam = set()    # din categoria modulelor de acces sau care au pus un script de modul (<fel>.<x>)
		self.executabile = {}       # pachet cam -> {cai}
		self.scripturi = {}         # pachet cam -> {nume de script}
		self.dependinte_cam = set()  # pachetele de care depind pachetele de cam-uri
		self.info_dir = Configurare().info_dir

	def descriere(self, sistem, pachet):
		"""primul rand din Description (info/<pachet>.control), scris de pachetul insusi"""
		try:
			strofe = strofe_din_text(sistem.citeste(posixpath.join(self.info_dir, pachet + '.control'), 65536))
		except (OSError, IOError):
			return ''
		if not strofe:
			return ''
		return strofe[0].get('description', '').split('\n', 1)[0].strip()


def citeste_opkg(sistem, cautate, feluri_=None):
	if feluri_ is None:
		feluri_ = feluri(sistem)
	o = Opkg()
	try:
		conf = citeste_configurarea(sistem.radacina)
	except Exception:
		conf = Configurare()
	o.info_dir = conf.info_dir
	try:
		text = sistem.citeste(conf.status_file)
	except (OSError, IOError):
		return o
	for s in strofe_din_text(text):
		n = s.get('package', '')
		st = s.get('status', '').split()
		if not nume_valid(n) or 'installed' not in st or 'not-installed' in st:
			continue
		o.instalate[n] = _dependente(s.get('depends', ''))
	for n in sorted(o.instalate):
		try:
			linii = sistem.citeste(posixpath.join(conf.info_dir, n + '.list'), LISTA_MAXIM).splitlines()
		except (OSError, IOError):
			continue
		e_cam = categorie_din_nume(n) == CATEGORIE_ACCES
		fisiere = []
		for r in linii:
			parti = r.split('\t')
			cale = parti[0].strip()
			if not cale:
				continue
			if cale in cautate:
				o.proprietar.setdefault(cale, n)
			if posixpath.dirname(cale) == DOSAR_SCRIPTURI and e_script_modul(posixpath.basename(cale), feluri_):
				e_cam = True
				o.scripturi.setdefault(n, set()).add(posixpath.basename(cale))
			fisiere.append((cale, parti[1].strip() if len(parti) > 1 else ''))
		if e_cam:
			o.pachete_cam.add(n)
			o.executabile[n] = set(c for c, m in fisiere if _e_executabil(sistem, c, m))
	for n in o.pachete_cam:
		o.dependinte_cam.update(o.instalate.get(n, ()))
	return o


# ---------------------------------------------------------------- proba HTTP

def curata_nume(text, maxim=NUME_MAXIM):
	"""Un nume venit de la alt program, bun de aratat: fara etichete HTML, cu entitatile desfacute, fara caractere de
	control, cu spatiile stranse, cel mult `maxim` semne."""
	text = re.sub(r'<[^>]*>', ' ', text or '')
	text = html.unescape(text)
	text = ''.join(ch if ch.isprintable() else ' ' for ch in text)
	text = ' '.join(text.split())
	if len(text) > maxim:
		text = text[:maxim - 1].rstrip() + '…'
	return text


_TITLU = re.compile(br'<title[^>]*>(.*?)</title', re.I | re.S)
_SET_CARACTERE = re.compile(br'''charset\s*=\s*["']?([A-Za-z0-9_.:-]+)''', re.I)
_REALM = re.compile(r'''realm\s*=\s*(?:"([^"]*)"|([^,\s]+))''', re.I)


def titlu_pagina(corp, tip=''):
	m = _TITLU.search(corp)
	if not m:
		return ''
	brut = m.group(1)
	coduri = []
	for sursa in (tip.encode('latin-1', 'replace'), corp[:m.start()]):
		c = _SET_CARACTERE.search(sursa)
		if c:
			coduri.append(c.group(1).decode('ascii', 'replace'))
	coduri.append('utf-8')
	for cod in coduri:
		try:
			return curata_nume(brut.decode(cod))
		except (LookupError, UnicodeDecodeError):
			continue
	return curata_nume(brut.decode('cp1252', 'replace'))


def analizeaza_raspuns(date):
	"""(cod, antete, corp) sau None cand nu e un raspuns HTTP. Antetele: numele cu litere mici, prima valoare."""
	if not date.startswith(b'HTTP/'):
		return None
	cap, sep, corp = date.partition(b'\r\n\r\n')
	if not sep:
		cap, sep, corp = date.partition(b'\n\n')
	linii = cap.decode('latin-1').replace('\r', '').split('\n')
	m = re.match(r'HTTP/\d(?:\.\d)?\s+(\d{3})', linii[0])
	if not m:
		return None
	antete = {}
	for l in linii[1:]:
		k, sep, v = l.partition(':')
		if sep and k.strip():
			antete.setdefault(k.strip().lower(), v.strip())
	return int(m.group(1)), antete, corp


def nume_din_raspuns(cod, antete, corp):
	"""(nume, sursa): la 2xx titlul paginii, apoi Server; la 401/403 Server, apoi realm (titlul unei pagini de eroare
	nu spune ce program e); altfel Server"""
	server = curata_nume(antete.get('server', ''))
	if 200 <= cod < 300:
		t = titlu_pagina(corp, antete.get('content-type', ''))
		if t:
			return t, 'titlu'
	elif cod in (401, 403):
		if server:
			return server, 'server'
		m = _REALM.search(antete.get('www-authenticate', ''))
		r = curata_nume(m.group(1) if m and m.group(1) is not None else (m.group(2) if m else ''))
		if r:
			return r, 'realm'
		return '', ''
	if server:
		return server, 'server'
	return '', ''


def _gazda_antet(gazda, port):
	return ('[%s]:%d' if ':' in gazda else '%s:%d') % (gazda, port)


def _cale_redirectare(locatie, gazda, port, schema):
	"""(schema, cale) de urmat, sau ('', '') cand redirectionarea duce in alta parte (alta gazda, alt port). Schema
	se poate schimba: o interfata pusa numai pe TLS raspunde la http cu o redirectionare spre https pe acelasi port
	(asa face un cam de proba)."""
	if not locatie:
		return '', ''
	try:
		u = urlsplit(urljoin('%s://%s/' % (schema, _gazda_antet(gazda, port)), locatie))
		p = u.port if u.port is not None else _PORT_IMPLICIT.get(u.scheme)
	except ValueError:
		return '', ''
	if u.scheme not in _PORT_IMPLICIT or p != port or (u.hostname or '') not in (gazda,) + _GAZDE_LOCALE:
		return '', ''
	cale = (u.path or '/') + ('?' + u.query if u.query else '')
	if not re.match(r'^/[\x21-\x7e]*$', cale) or len(cale) > 512:
		return '', ''
	return u.scheme, cale


def _context_tls():
	import ssl
	ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
	ctx.check_hostname = False
	ctx.verify_mode = ssl.CERT_NONE   # doar titlul unei pagini de pe receptorul insusi; certificatele cam-urilor sunt facute de ele
	try:
		ctx.set_ciphers('DEFAULT:@SECLEVEL=0')
	except ssl.SSLError:
		pass
	return ctx


def _are_tls():
	try:
		import ssl  # noqa: F401
		return True
	except ImportError:
		return False


def _citeste_raspuns(s, termen):
	"""(date, motiv): citeste pana la OCTETI_MAXIM, pana se inchide conexiunea sau pana la termen. O conexiune
	inchisa fara niciun octet de raspuns e 'inchis' (poate fi un port TLS care nu stie ce sa faca cu textul nostru)."""
	date = b''
	while len(date) < OCTETI_MAXIM:
		ramas = termen - _ceas()
		if ramas <= 0:
			return date, 'termen'
		s.settimeout(ramas)
		try:
			bucata = s.recv(OCTETI_MAXIM - len(date))
		except socket.timeout:
			return date, 'termen'
		except (OSError, ValueError):
			return date, 'inchis'
		if not bucata:
			return date, 'gata' if date else 'inchis'
		date += bucata
	return date, 'gata'


def _o_cerere(gazda, port, cale, tls, tacere, conectare, citire):
	"""O conexiune si cel mult un GET. (date, motiv), motiv: 'vorbeste_primul' (a trimis ceva inainte sa trimitem noi:
	nu i-am trimis niciun octet), 'refuzat', 'inchis', 'termen', 'gata'."""
	s = socket.socket(socket.AF_INET6 if ':' in gazda else socket.AF_INET, socket.SOCK_STREAM)
	try:
		s.settimeout(conectare)
		try:
			s.connect((gazda, port))
		except (OSError, ValueError):
			return b'', 'refuzat'
		if tacere > 0:
			s.settimeout(tacere)
			try:
				primit = s.recv(1)
			except socket.timeout:
				primit = None
			except OSError:
				return b'', 'inchis'
			if primit:
				return b'', 'vorbeste_primul'
			if primit is not None:
				return b'', 'inchis'
		termen = _ceas() + citire
		if tls:
			s.settimeout(citire)
			try:
				s = _context_tls().wrap_socket(s)
			except (OSError, ValueError):  # ssl.SSLError e tot OSError
				return b'', 'inchis'
		cerere = ('GET %s HTTP/1.0\r\nHost: %s\r\nUser-Agent: HDSatelit\r\nAccept: text/html\r\nConnection: close\r\n\r\n'
			% (cale, _gazda_antet(gazda, port))).encode('ascii')
		try:
			s.settimeout(max(0.05, termen - _ceas()))
			s.sendall(cerere)
		except (OSError, ValueError):
			return b'', 'inchis'
		return _citeste_raspuns(s, termen)
	finally:
		try:
			s.close()
		except OSError:
			pass


def _pare_tls(date):
	return date[:1] in (b'\x15', b'\x16')


def proba_http(gazda, port, conectare=LIMITA_CONECTARE, tacere=ASTEPTARE_TACERE, citire=LIMITA_CITIRE, cerere=None):
	"""Proba unui port. {'stare', 'schema', 'cod_http', 'nume', 'sursa_nume'}; stare: 'web', 'nu_e_web' (vorbeste
	primul sau raspunde altceva decat HTTP), 'nu_raspunde'. `cerere`: _o_cerere, sau alta cu aceeasi forma (la
	probe: raspunsurile citite pe receptor)."""
	cerere = cerere or _o_cerere
	rez = {'stare': 'nu_raspunde', 'schema': 'http', 'cod_http': None, 'nume': '', 'sursa_nume': ''}
	date, motiv = cerere(gazda, port, '/', False, tacere, conectare, citire)
	if motiv == 'vorbeste_primul':
		rez['stare'] = 'nu_e_web'
		return rez
	schema = 'http'
	parea_tls = _pare_tls(date)
	if parea_tls or (not date and motiv == 'inchis'):
		if not _are_tls():
			rez['stare'] = 'nu_e_web' if parea_tls else 'nu_raspunde'
			return rez
		date, motiv = cerere(gazda, port, '/', True, 0, conectare, citire)
		schema = 'https'
	if not date:
		rez['stare'] = 'nu_e_web' if parea_tls else 'nu_raspunde'
		return rez
	raspuns = analizeaza_raspuns(date)
	if raspuns is None:
		rez['stare'] = 'nu_e_web'
		return rez
	cod, antete, corp = raspuns
	if cod in _REDIRECTARI:
		schema2, cale = _cale_redirectare(antete.get('location', ''), gazda, port, schema)
		if cale:
			date2, _motiv = cerere(gazda, port, cale, schema2 == 'https', 0, conectare, citire)
			r2 = analizeaza_raspuns(date2) if date2 else None
			if r2 is not None:
				cod, antete, corp = r2
				schema = schema2
	rez['stare'] = 'web'
	rez['schema'] = schema
	rez['cod_http'] = cod
	rez['nume'], rez['sursa_nume'] = nume_din_raspuns(cod, antete, corp)
	return rez


def _probeaza(tinte, termen, conectare, tacere, citire, sonda=None):
	"""Fiecare port pe firul lui, toate deodata; {cheie: rezultat} numai pentru cele terminate pana la termen.
	`sonda`: proba_http, sau alta cu aceeasi forma (la probe: rezultatele citite pe receptor)."""
	sonda = sonda or proba_http
	rezultate = {}
	lacat = threading.Lock()
	fire = []
	for tinta in tinte:
		cheie, gazda, port = tinta[:3]
		rezerva = tinta[3] if len(tinta) > 3 else None

		def lucru(cheie=cheie, gazda=gazda, port=port, rezerva=rezerva):
			try:
				r = sonda(gazda, port, conectare, tacere, citire)
				# un port care asculta pe '::' (IPv6 si IPv4 pe acelasi socket) se probeaza intai pe ::1; un receptor fara
				# adresa IPv6 de loopback ("Cannot assign requested address") ii raspunde numai pe 127.0.0.1
				if rezerva and r.get('stare') == 'nu_raspunde':
					r = sonda(rezerva, port, conectare, tacere, citire)
			except Exception:
				r = {'stare': 'nu_raspunde', 'schema': 'http', 'cod_http': None, 'nume': '', 'sursa_nume': ''}
			with lacat:
				rezultate[cheie] = r
		t = threading.Thread(target=lucru)
		t.daemon = True
		t.start()
		fire.append(t)
	for t in fire:
		ramas = termen - _ceas()
		if ramas <= 0:
			break
		t.join(ramas)
	with lacat:
		return dict(rezultate)


# ---------------------------------------------------------------- adresa receptorului

def ip_receptor(sistem=None, ordine=None):
	"""Adresa IPv4 a receptorului in reteaua locala, cea spre poarta implicita din /proc/net/route. Nu trimite nimic:
	un socket UDP conectat doar alege adresa sursa. '' cand nu se stie."""
	sistem = sistem or Sistem()
	try:
		text = sistem.citeste('/proc/net/route')
	except (OSError, IOError):
		return ''
	for r in text.splitlines()[1:]:
		c = r.split()
		if len(c) < 3 or c[1] != '00000000' or c[2] == '00000000':
			continue
		s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		try:
			s.connect((adresa_din_hex(c[2], ordine), 9))
			return s.getsockname()[0]
		except (OSError, ValueError, struct.error):
			return ''
		finally:
			s.close()
	return ''


def adresa(interfata, gazda):
	"""Adresa de deschis din browser (schema://gazda:port/), sau '' cand interfata nu e web sau asculta doar pe
	receptor. `gazda`: adresa receptorului asa cum o stie cel care deschide (pe web, cea din bara browserului)."""
	if not interfata.get('web') or interfata.get('doar_local'):
		return ''
	g = interfata.get('gazda') or gazda
	if not g:
		return ''
	if ':' in g and not g.startswith('['):
		g = '[' + g + ']'
	return '%s://%s:%d/' % (interfata.get('schema') or 'http', g, interfata['port'])


def cu_adrese(rezultat, gazda=None):
	"""O copie a rezultatului cu 'adresa' pe fiecare interfata; gazda implicita: ip_receptor din rezultat."""
	r = copy.deepcopy(rezultat)
	g = gazda or r.get('ip_receptor') or ''
	for c in r.get('cam_uri', ()):
		for i in c.get('interfete', ()):
			i['adresa'] = adresa(i, g)
	return r


# ---------------------------------------------------------------- cautarea

class _Cam(object):
	def __init__(self, cheie):
		self.cheie = cheie          # ('pachet', nume), ('script', nume) sau ('proces', exe)
		self.pachet = ''
		self.script = None
		self.procese = []
		self.semne = set()
		self.porturi = {}           # port -> {adrese pe care asculta}


def _al(cam_uri, cheie):
	c = cam_uri.get(cheie)
	if c is None:
		c = cam_uri[cheie] = _Cam(cheie)
	return c


def _e_local(adresa_ascultare):
	return adresa_ascultare.startswith('127.') or adresa_ascultare == '::1' or adresa_ascultare.startswith('::ffff:127.')


def _fara_prefix_v4(adresa_ascultare):
	return adresa_ascultare[7:] if adresa_ascultare.startswith('::ffff:') else adresa_ascultare


def _gazda_proba(adrese):
	"""(gazda pentru proba, doar_local, adresa anume sau ''), din adresele pe care asculta un port"""
	if '0.0.0.0' in adrese:
		return '127.0.0.1', False, ''
	if '::' in adrese:
		return '::1', False, ''
	anume = sorted(a for a in adrese if not _e_local(a))
	if anume:
		a = _fara_prefix_v4(anume[0])
		return a, False, a
	return _fara_prefix_v4(sorted(adrese)[0]), True, ''


def _nume_cam(sistem, opkg, c, interfete):
	"""(nume, sursa): titlul unei pagini (2xx); descrierea din script sau din pachet; Server sau realm; sufixul
	scriptului; numele pachetului; numele procesului"""
	web = [i for i in interfete if i['stare'] == 'web' and i['nume']]
	web.sort(key=lambda i: (i['doar_local'], not (200 <= (i['cod_http'] or 0) < 300), i['port']))
	for i in web:
		if i['sursa_nume'] == 'titlu':
			return i['nume'], 'titlu'
	if c.script is not None and curata_nume(c.script.descriere):
		return curata_nume(c.script.descriere), 'script'
	if c.pachet:
		d = curata_nume(opkg.descriere(sistem, c.pachet))
		if d:
			return d, 'pachet'
	if web:
		return web[0]['nume'], web[0]['sursa_nume']
	if c.script is not None:
		return curata_nume(c.script.sufix), 'script'
	if c.pachet:
		return curata_nume(nume_scurt(c.pachet)), 'pachet'
	for p in c.procese:
		n = curata_nume(p.comm or posixpath.basename(p.exe))
		if n:
			return n, 'proces'
	return '', ''


def _fel(opkg, c):
	"""'emulator' (in lista modulelor de acces: script de modul sau pachet de modul), 'plugin' (pachet sau dosar de
	extensie enigma2) sau 'program'"""
	if c.script is not None or c.pachet in opkg.pachete_cam:
		return 'emulator'
	if c.pachet.startswith(PREFIX_PLUGIN) or any(p.exe.startswith(DOSAR_PLUGINURI) for p in c.procese):
		return 'plugin'
	return 'program'


def cauta(sistem=None, porturi_excluse=(), limita=LIMITA_CAUTARE, conectare=LIMITA_CONECTARE,
		tacere=ASTEPTARE_TACERE, citire=LIMITA_CITIRE, ordine=None, sonda=None):
	"""Cautarea intreaga. Blocheaza cateva secunde: se cheama numai pe un fir separat (vezi cautare()).

	Rezultatul:
	  {'result': True, 'cautat_la', 'durata', 'decripteaza_acum', 'ip_receptor', 'neverificate',
	   'cam_uri': [{'nume', 'sursa_nume' (titlu|server|realm|script|pachet|proces), 'fel' (emulator|plugin|program),
	                'pornit', 'ales', 'semne', 'pachet', 'script',
	                'interfete': [{'port', 'schema', 'doar_local', 'gazda', 'stare' (web|nu_e_web|nu_raspunde|
	                               neverificat), 'web', 'verificat', 'cod_http', 'cere_parola', 'nume', 'sursa_nume'}]}]}
	Numele si porturile vin toate de la cam-uri, la rulare. Adresa de deschis: adresa() sau cu_adrese()."""
	inceput = _ceas()
	termen = inceput + limita
	sistem = sistem or Sistem()

	procese = citeste_procese(sistem)
	propriu = procese.pop(sistem.pid_propriu, None)
	ascultare = porturi_in_ascultare(sistem, ordine)
	decriptare = inode_decriptare(sistem)
	feluri_ = feluri(sistem)
	scripturi = citeste_scripturi(sistem, feluri_)
	cautate = set()
	for p in procese.values():
		cautate.add(p.exe)
	for s in scripturi.values():
		cautate.add(s.cale)
		cautate.update(s.cai)
		cautate.update(s.cai.values())
	opkg = citeste_opkg(sistem, cautate, feluri_)

	cam_uri = {}
	# 1. scripturile: ale unui pachet de cam-uri (cel care a pus scriptul sau cel care tine executabilul scris in el)
	#    sau puse de mana
	cheie_script = {}
	for s in sorted(scripturi.values(), key=lambda s: (not s.ales, s.nume)):
		prop = opkg.proprietar.get(s.cale)
		if prop not in opkg.pachete_cam:
			prop = None
			for c in sorted(s.cai):
				for cale in (c, s.cai[c]):
					if opkg.proprietar.get(cale) in opkg.pachete_cam:
						prop = opkg.proprietar[cale]
						break
				if prop:
					break
		cheie = ('pachet', prop) if prop else ('script', s.nume)
		cam = _al(cam_uri, cheie)
		cam.pachet = prop or ''
		if cam.script is None:
			cam.script = s
		cheie_script[s.nume] = cheie
	# 2. pachetele de cam-uri care au ceva de pornit (un executabil sau un script); cele numai cu date nu
	for n in sorted(opkg.pachete_cam):
		if opkg.executabile.get(n) or opkg.scripturi.get(n):
			_al(cam_uri, ('pachet', n)).pachet = n
	# 3. procesele cu semne
	pe_proces = {}
	for p in sorted(procese.values(), key=lambda p: p.pid):
		semne = set()
		if p.socketuri & decriptare:
			semne.add('S1')
		if any(_CITITOR_CARD.match(d) or _CA.match(d) for d in p.dispozitive) and \
				not any(_FRONTEND.match(d) for d in p.dispozitive):
			semne.add('S2')
		prop = opkg.proprietar.get(p.exe)
		if prop in opkg.pachete_cam:
			semne.add('S3')
		gasit = None
		if prop is None or prop in opkg.pachete_cam or prop in opkg.dependinte_cam:
			for s in sorted(scripturi.values(), key=lambda s: (not s.ales, s.nume)):
				if _scriptul_porneste(s, p):
					gasit = s
					semne.add('S4')
					break
		if not semne:
			continue
		if gasit is not None:
			cheie = cheie_script[gasit.nume]
		elif prop:
			cheie = ('pachet', prop)
		else:
			cheie = ('proces', p.exe)
		cam = _al(cam_uri, cheie)
		if cheie[0] == 'pachet':
			cam.pachet = cheie[1]
		cam.procese.append(p)
		cam.semne |= semne
		pe_proces[p.pid] = cheie
	# 4. copiii unui cam si celelalte procese cu acelasi executabil intra cu el
	for _runda in range(8):
		exe_cam = dict((procese[pid].exe, cheie) for pid, cheie in pe_proces.items())
		adaugat = False
		for p in sorted(procese.values(), key=lambda p: p.pid):
			if p.pid in pe_proces:
				continue
			cheie = pe_proces.get(p.ppid) or exe_cam.get(p.exe)
			if cheie:
				pe_proces[p.pid] = cheie
				cam_uri[cheie].procese.append(p)
				adaugat = True
		if not adaugat:
			break

	# 5. porturile pe care asculta; fara cele ale procesului propriu si fara cele cerute
	excluse = set(porturi_excluse or ())
	if propriu is not None:
		for i in propriu.socketuri:
			if i in ascultare:
				excluse.add(ascultare[i][1])
	for cam in cam_uri.values():
		for p in cam.procese:
			for i in p.socketuri:
				if i in ascultare and ascultare[i][1] not in excluse:
					cam.porturi.setdefault(ascultare[i][1], set()).add(ascultare[i][0])

	ordonate = sorted(cam_uri.values(), key=lambda c: (not c.procese, not (c.script is not None and c.script.ales),
		c.cheie))
	tinte = []
	gazde = {}
	for cam in ordonate:
		for port in sorted(cam.porturi):
			gazde[(cam.cheie, port)] = _gazda_proba(cam.porturi[port])
			rezerva = '127.0.0.1' if gazde[(cam.cheie, port)][0] == '::1' and '::' in cam.porturi[port] else None
			tinte.append(((cam.cheie, port), gazde[(cam.cheie, port)][0], port, rezerva))
	verificate = _probeaza(tinte[:PORTURI_MAXIM], termen, conectare, tacere, citire, sonda)

	lista = []
	for cam in ordonate:
		interfete = []
		for port in sorted(cam.porturi):
			gazda, doar_local, anume = gazde[(cam.cheie, port)]
			r = verificate.get((cam.cheie, port))
			stare = r['stare'] if r else 'neverificat'
			interfete.append({
				'port': port,
				'schema': r['schema'] if r else 'http',
				'doar_local': doar_local,
				'gazda': anume,
				'stare': stare,
				'web': stare == 'web',
				'verificat': r is not None,
				'cod_http': r['cod_http'] if r else None,
				'cere_parola': bool(r and r['cod_http'] == 401),
				'nume': r['nume'] if r else '',
				'sursa_nume': r['sursa_nume'] if r else '',
			})
		nume, sursa = _nume_cam(sistem, opkg, cam, interfete)
		lista.append({
			'nume': nume,
			'sursa_nume': sursa,
			'fel': _fel(opkg, cam),
			'pornit': bool(cam.procese),
			'ales': bool(cam.script is not None and cam.script.ales),
			'semne': sorted(cam.semne),
			'pachet': cam.pachet,
			'script': cam.script.nume if cam.script is not None else '',
			'interfete': interfete,
		})
	return {
		'result': True,
		'cautat_la': int(time.time()),
		'durata': round(_ceas() - inceput, 2),
		'decripteaza_acum': sistem.exista(FISIER_ECM),
		'ip_receptor': ip_receptor(sistem, ordine),
		'neverificate': max(0, len(tinte) - PORTURI_MAXIM),
		'cam_uri': lista,
	}


# ---------------------------------------------------------------- pe fir separat, o singura cautare deodata

class CautareCam(object):
	"""O cautare pe un fir separat. Firul nu atinge nimic din interfata: la sfarsit pune `rezultat` si apoi semnalul
	`gata`. Pe televizor se citeste cu un eTimer; pe web, firul cererii asteapta cu asteapta()."""

	def __init__(self, **argumente):
		self.argumente = argumente
		self.pornit = _ceas()
		self.terminat_la = None
		self.rezultat = None
		self.eroare = None
		self._gata = threading.Event()

	@property
	def gata(self):
		return self._gata.is_set()

	def porneste(self):
		t = threading.Thread(target=self._lucreaza)
		t.daemon = True
		t.start()
		return self

	def _lucreaza(self):
		try:
			self.rezultat = cauta(**self.argumente)
		except Exception as e:
			self.eroare = '%s: %s' % (e.__class__.__name__, e)
			self.rezultat = {'result': False, 'message': self.eroare, 'cam_uri': []}
		self.terminat_la = _ceas()
		self._gata.set()

	def asteapta(self, secunde=None):
		"""rezultatul, dupa cel mult `secunde`; None daca nu s-a terminat"""
		self._gata.wait(secunde)
		return self.rezultat if self.gata else None


_lacat = threading.Lock()
_ultima = [None]


def cautare(reincarca=False, memorare=MEMORARE, **argumente):
	"""Cautarea de folosit acum, fara sa astepte: cea in curs (una singura deodata: doua browsere care cer in acelasi
	timp primesc aceeasi), cea terminata de cel mult `memorare` secunde (cand nu se cere reincarcarea), altfel una
	noua, pornita acum pe un fir separat."""
	with _lacat:
		c = _ultima[0]
		if c is not None:
			if not c.gata:
				return c
			if not reincarca and c.eroare is None and _ceas() - c.terminat_la < memorare:
				return c
		c = _ultima[0] = CautareCam(**argumente).porneste()
		return c


def rezultat(reincarca=False, asteptare=LIMITA_CAUTARE + 2, **argumente):
	"""Pentru un fir de lucru (cererea web): rezultatul, dupa cel mult `asteptare` secunde; None daca nu s-a terminat.
	Nu se cheama pe firul principal al enigma2."""
	return cautare(reincarca, **argumente).asteapta(asteptare)
