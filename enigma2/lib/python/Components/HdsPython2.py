# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Pachetele facute numai pentru Python 2 (0.6.8): recunoasterea inainte de instalare si inlocuitorul din feedurile
noastre. Doar in imaginea HDSatelit.

Imaginea are Python 3. Un plugin facut pentru imaginile vechi, cu Python 2, nu porneste aici; instalat, ramanea pe
receptor fara sa mearga (sau aducea cu el pachete Python 2 dintr-un feed vechi). Extensii (ecranul de pe televizor si
pagina web, prin Components/HdsExtensiiLucru.py) intreaba modulul acesta INAINTE de opkg si, la un pachet numai pentru
Python 2, nu instaleaza nimic: spune de ce si propune inlocuitorul pentru Python 3 din feedurile noastre, daca exista.

Semnele (un semn sigur opreste instalarea; "nu stiu" nu o opreste niciodata):
  - TARI, din control (lista feedului sau fisierul .ipk): Depends / Pre-Depends cer numai pachete Python 2 (python,
    python-core, python-twisted-web, python2.7, libpython2.7 ...; numele python3-* sunt bune), sau pachetul insusi e o
    biblioteca Python 2 (python-<nume>);
  - TARE, din lista: pachetul vine dintr-un feed al imaginilor cu Python 2 (o sursa al carei grup, aceeasi adresa fara
    ultimul dosar, are Python 2 insusi: python-core 2.x), numai la felurile cu cod Python (FELURI_COD) si cand nu cere
    nimic din Python 3;
  - TARI, din continutul unui fisier .ipk (numai citit, in memorie, fara nimic scris pe disc si fara nimic rulat):
    fisiere sub /usr/lib/python2.x, fisiere .pyo/.pyc cu numarul magic al lui Python 2 (primii doi octeti, little
    endian, de la 20000 in sus; Python 3 are 3000-3999), biblioteci .so legate de libpython2;
  - SLABE, din continut (opresc numai cand pachetul nu are nimic pentru Python 3, masurat pe pachete reale): sursa .py
    care nu se compileaza in Python 3 (print fara paranteze, except X, e ...), importuri de module care nu mai exista
    in Python 3 (urllib2, urlparse, cookielib ...) facute fara rezerva (un import dintr-un try sau dintr-un if nu se
    socoteste: acolo e de obicei varianta pentru cealalta versiune).
Un pachet din feed se judeca intai dupa lista. Unul dintr-o sursa straina, de un fel cu cod, care dupa lista nu e nici
Python 2, nici Python 3, se descarca intai (opkg --download-only) si se citeste din cache-ul opkg inainte de instalare
(Components/HdsExtensiiLucru.Lucrare). Un fisier .ipk se citeste pe firul cautarii fisierelor
(Components/HdsPachete.CautareIpk), cu limite de timp, de octeti si de fisiere.

Inlocuitorul: acelasi nume, numele fara sufixul vechi (-py2, -python2 ...), numele cu sufixul nou (-py3, -python3),
tabelul INLOCUITORI (nume vechi -> nume nou) si tabelul DOSARE (dosarul pluginului din fisier -> pachetul nostru),
facute din date cu o unealta din afara imaginii (fa_tabel_inlocuitori.py).
Alegerea dintre candidati (numai din feedurile noastre, numai pentru Python 3) o face Components/HdsExtensiiLucru.py,
care stie feedurile.
Modulul nu depinde de enigma, ca sa poata fi incercat si pe PC."""
import ast
import io
import os
import re
import struct
import tarfile
import time
import warnings
import zlib

_ceas = getattr(time, 'monotonic', time.time)

# ---------------------------------------------------------------- semnele (codurile motivelor)
DEPENDINTA = 'dependinta'       # Depends / Pre-Depends cer pachete Python 2 (detaliul: numele)
BIBLIOTECA = 'biblioteca'       # pachetul insusi e o biblioteca Python 2 (python-<nume>)
DOSAR = 'dosar'                 # fisiere sub /usr/lib/python2.x (detaliul: calea)
COMPILAT = 'compilat'           # .pyo/.pyc cu numarul magic al lui Python 2 (detaliul: fisierul)
LEGAT = 'legat'                 # .so legat de libpython2 (detaliul: fisierul)
SURSA = 'sursa'                 # .py care nu se compileaza in Python 3 (detaliul: fisierul si randul)
MODULE = 'module'               # importuri de module scoase din Python 3, fara rezerva (detaliul: modulul)
FEED = 'feed'                   # vine dintr-un feed al imaginilor cu Python 2 (detaliul: numele sursei)

# felurile de pachete (Components/HdsPachete.CATEGORII) care au cod Python: numai la ele se judeca dupa feed si se
# citeste pachetul inainte de instalare (listele de canale, siglele, driverele nu au cod Python)
FELURI_COD = ('extensions', 'systemplugins', 'skins')
# felurile care, dintr-o sursa straina si fara raspuns dupa lista, se descarca si se citesc inainte de instalare
# (extensiile si pluginurile de sistem sunt cod; un skin e mai ales XML si imagini)
FELURI_VERIFICATE = ('extensions', 'systemplugins')

# numele pachetelor Python 2: python, python2, python2.7, python-<ceva> (python-core, python-twisted-web ...),
# libpython2.7 (si -1.0); niciodata python3*
_PY2_PACHET = re.compile(r'^(?:python(?:2(?:\.[0-9]+)?)?(?:-[a-z0-9+.\-]+)?|libpython2(?:\.[0-9]+)?(?:-[0-9.]+)?)\Z')
_PY2_CALE = re.compile(r'(?:^|/)usr/lib/python2(?:\.[0-9]+)?/')

# modulele care nu mai exista in Python 3 (au alt nume sau au fost scoase)
MODULE_PY2 = frozenset((
	'urllib2', 'urlparse', 'cookielib', 'httplib', 'HTMLParser', 'htmlentitydefs', 'Queue', 'ConfigParser',
	'cPickle', 'cStringIO', 'StringIO', 'commands', '__builtin__', 'xmlrpclib', 'SimpleXMLRPCServer', 'SocketServer',
	'BaseHTTPServer', 'SimpleHTTPServer', 'CGIHTTPServer', 'Cookie', 'thread', 'dummy_thread', 'exceptions', 'sets',
	'md5', 'sha', 'new', 'popen2', 'anydbm', 'dbhash', 'whichdb', 'dumbdbm', 'gdbm', 'UserDict', 'UserList',
	'UserString', 'copy_reg', 'repr', 'robotparser', 'Tkinter', 'tkMessageBox', 'ttk', 'mimetools', 'rfc822',
	'mimify', 'MimeWriter', 'multifile', 'htmllib', 'sgmllib', 'compiler', 'imputil', 'ihooks', 'statvfs', 'user',
	'fpformat', 'dircache', 'mhlib', 'stringold'))
# numele luate direct din urllib in Python 2 (in Python 3 sunt in urllib.request / urllib.parse)
URLLIB_PY2 = frozenset(('urlopen', 'urlencode', 'quote', 'quote_plus', 'unquote', 'unquote_plus', 'urlretrieve',
	'urlcleanup', 'URLopener', 'FancyURLopener', 'pathname2url', 'url2pathname', 'getproxies', 'splittype',
	'splithost', 'basejoin'))

# limitele citirii unui fisier .ipk (pe firul cautarii; o lipsa de raspuns nu tine interfata)
_IPK_MAXIM = 64 * 1024 * 1024        # cat se citeste cel mult dintr-un fisier .ipk (octeti comprimati)
_DATE_MAXIM = 96 * 1024 * 1024       # cat se dezarhiveaza cel mult din data.tar
_MEMBRI_MAXIM = 20000
_PY_MAXIM = 60                       # cate fisiere .py se compileaza cel mult
_PY_OCTETI = 512 * 1024              # un fisier .py mai mare se sare
_SO_OCTETI = 8 * 1024 * 1024         # un .so mai mare se sare
TIMP_MAXIM = 6.0                     # secunde pentru un fisier (apoi "nu stiu")
GRAMATICA = (3, 13)                  # gramatica cu care se compileaza sursa .py (vezi din_sursa)

_ERORI = (tarfile.TarError, OSError, EOFError, ValueError, zlib.error, struct.error)
try:
	import lzma
	_ERORI += (lzma.LZMAError,)
except ImportError:
	pass


# ---------------------------------------------------------------- verdictul

class Verdict(object):
	"""python2: True (sigur numai pentru Python 2), False (sigur pentru Python 3) sau None (nu se stie: se instaleaza
	ca pana acum). motive: [(cod, detaliu)], primul e cel aratat. dosare: dosarele pluginurilor din fisier
	('Extensions/Nume'), pentru inlocuitor. taiat: citirea s-a oprit la o limita. slabe: semnele care opresc numai
	cand pachetul nu are nimic pentru Python 3 (sursa care nu se compileaza, importurile): un pachet construit pentru
	Python 3 poate avea scripturi vechi pe langa (masurat pe pachete reale, unelte/recunoastere.py)."""
	__slots__ = ('python2', 'motive', 'dosare', 'taiat', 'python3', 'alt3', 'fisiere', 'slabe')

	def __init__(self):
		self.python2 = None
		self.motive = []
		self.dosare = []
		self.taiat = False
		self.python3 = False         # s-a vazut ceva facut pentru Python 3 (dependinta python3-*, .pyc de Python 3)
		self.alt3 = ''               # un .pyc facut pentru alta versiune de Python 3 (numai pentru jurnal si masuratori)
		self.fisiere = 0
		self.slabe = []

	def adauga(self, cod, detaliu):
		self.python2 = True
		if (cod, detaliu) not in self.motive and len(self.motive) < 8:
			self.motive.append((cod, detaliu))

	@property
	def motiv(self):
		return self.motive[0] if self.motive else (None, '')

	def __repr__(self):
		return 'Verdict(python2=%r, motive=%r, dosare=%r, taiat=%r)' % (self.python2, self.motive, self.dosare, self.taiat)


# ---------------------------------------------------------------- control: dependintele si numele

def _alternative(text):
	"""[[nume, ...], ...]: grupele lui Depends (despartite prin virgula), fiecare cu alternativele ei (|), fara versiuni"""
	rez = []
	for parte in (text or '').split(','):
		grupa = []
		for alt in parte.split('|'):
			n = alt.strip().split(' ', 1)[0].split('(', 1)[0].strip().lower()
			if n:
				grupa.append(n)
		if grupa:
			rez.append(grupa)
	return rez


def e_pachet_python2(nume):
	"""True pentru numele unui pachet Python 2 (python-core, python2.7, libpython2.7 ...)"""
	return bool(nume) and _PY2_PACHET.match(nume.strip().lower()) is not None


def e_pachet_python3(nume):
	n = (nume or '').strip().lower()
	return n.startswith('python3') or n.startswith('libpython3')


def din_dependinte(text, verdict=None):
	"""verdictul dupa Depends (sau Pre-Depends): Python 2 cand o grupa are numai alternative Python 2"""
	v = verdict if verdict is not None else Verdict()
	for grupa in _alternative(text):
		if all(e_pachet_python2(n) for n in grupa):
			v.adauga(DEPENDINTA, grupa[0])
		elif any(e_pachet_python3(n) for n in grupa):
			v.python3 = True
	return v


def din_control(strofa, verdict=None):
	"""verdictul dupa campurile din control (dict cu cheile cu litere mici, ca in Components/HdsPachete.py)"""
	v = verdict if verdict is not None else Verdict()
	strofa = strofa or {}
	nume = (strofa.get('package') or '').strip().lower()
	if nume.startswith('python-') and e_pachet_python2(nume):
		v.adauga(BIBLIOTECA, nume)
	for camp in ('pre-depends', 'depends'):
		din_dependinte(strofa.get(camp, ''), v)
	if v.python3 and v.python2 is None:
		v.python2 = False
	return v


def e_python2_insusi(strofa):
	"""strofa din lista e chiar Python 2 (python-core, python sau python2.7 cu versiunea 2.x): feedul ei e al unei
	imagini cu Python 2"""
	n = (strofa.get('package') or '').strip().lower()
	if n not in ('python-core', 'python', 'python2.7', 'python2.7-core'):
		return False
	v = (strofa.get('version') or '').split(':')[-1].strip()
	return v.startswith('2.')


def grup_sursa(adresa):
	"""adresa fara ultimul dosar: sursele aceluiasi feed (all, procesorul, modelul) au acelasi grup"""
	a = (adresa or '').strip().rstrip('/')
	return a.rsplit('/', 1)[0] if '/' in a.split('://', 1)[-1] else a


# ---------------------------------------------------------------- numarul magic al fisierelor compilate

def versiune_compilat(cap):
	"""2 sau 3 dupa primii 4 octeti ai unui .pyc/.pyo (numarul magic, little endian, apoi \\r\\n); None altfel"""
	if not cap or len(cap) < 4 or cap[2:4] != b'\r\n':
		return None
	m = struct.unpack('<H', cap[:2])[0]
	if m >= 20000:
		return 2
	if 3000 <= m < 4000:
		return 3
	return None


def _magic_curent():
	try:
		import importlib.util
		return importlib.util.MAGIC_NUMBER
	except Exception:
		return b''


# ---------------------------------------------------------------- sursa: compilarea si importurile

class _Importuri(ast.NodeVisitor):
	"""importurile de module scoase din Python 3, in afara unui try sau a unui if (acolo e de obicei rezerva)"""

	def __init__(self):
		self.gasite = []

	def _nimic(self, _nod):
		pass

	visit_Try = visit_If = _nimic
	if hasattr(ast, 'TryStar'):
		visit_TryStar = _nimic

	def visit_Import(self, nod):
		for a in nod.names:
			if a.name.split('.', 1)[0] in MODULE_PY2:
				self.gasite.append(a.name.split('.', 1)[0])

	def visit_ImportFrom(self, nod):
		if nod.level:
			return
		m = (nod.module or '').split('.', 1)[0]
		if m in MODULE_PY2:
			self.gasite.append(m)
		elif nod.module == 'urllib':
			for a in nod.names:
				if a.name in URLLIB_PY2:
					self.gasite.append('urllib.%s' % a.name)
					break

	def visit_Attribute(self, nod):
		# urllib.urlencode(...), urllib.quote(...) dupa "import urllib" (in Python 3 sunt in urllib.parse)
		if isinstance(nod.value, ast.Name) and nod.value.id == 'urllib' and nod.attr in URLLIB_PY2:
			self.gasite.append('urllib.%s' % nod.attr)
		self.generic_visit(nod)


def din_sursa(date, nume='plugin.py'):
	"""(cod, detaliu) cand sursa .py (octeti) e numai pentru Python 2, altfel None. Numai se compileaza (in arbore, fara
	sa ruleze nimic); o eroare care nu e de sintaxa (octeti nuli, recursie prea adanca) nu spune nimic."""
	if (b'\x00' if isinstance(date, bytes) else '\x00') in date:
		# octetii nuli dau SyntaxError de la Python 3.12 (inainte ValueError): un fisier stricat, nu cod Python 2
		return None
	try:
		with warnings.catch_warnings():
			warnings.simplefilter('ignore')
			# gramatica lui Python 3.13 (a receptorului), si cand ruleaza unul mai nou: Python 3.14 primeste iar
			# "except A, B:" fara paranteze (ca un tuplu), deci vechiul "except X, e:" din Python 2 nu mai e greseala
			arbore = ast.parse(date, nume, 'exec', feature_version=GRAMATICA)
	except SyntaxError as e:
		return SURSA, '%s:%s' % (os.path.basename(nume), getattr(e, 'lineno', '') or '?')
	except (ValueError, TypeError, RecursionError, MemoryError, UnicodeError):
		return None
	try:
		v = _Importuri()
		v.visit(arbore)
	except RecursionError:
		return None
	if v.gasite:
		return MODULE, v.gasite[0]
	return None


# ---------------------------------------------------------------- fisierul .ipk

class _Felie(object):
	"""o bucata dintr-un fisier deschis (membrul data.tar.* din arhiva ar), citita in flux, pana la `marime` octeti"""

	def __init__(self, fh, marime):
		self.fh = fh
		self.ramas = marime

	def read(self, n=-1):
		if self.ramas <= 0:
			return b''
		if n is None or n < 0 or n > self.ramas:
			n = self.ramas
		b = self.fh.read(n)
		self.ramas -= len(b)
		return b


def _dosar_plugin(cale):
	"""'Extensions/Nume' pentru un fisier dintr-un plugin enigma2, altfel ''"""
	m = re.search(r'/enigma2/python/Plugins/([A-Za-z0-9_]+)/([A-Za-z0-9_.\-]+)/', cale)
	return '%s/%s' % (m.group(1), m.group(2)) if m else ''


def _citeste(t, m, maxim):
	fh = t.extractfile(m)
	if fh is None:
		return b''
	return fh.read(maxim)


def _din_data_tar(sursa, v, inceput, timp_maxim):
	"""parcurge data.tar (flux) si completeaza verdictul; se opreste la primul semn sigur sau la o limita"""
	py = 0
	magic = _magic_curent()
	with tarfile.open(fileobj=sursa, mode='r|*') as t:
		for k, m in enumerate(t):
			if k >= _MEMBRI_MAXIM or m.offset_data > _DATE_MAXIM or _ceas() - inceput > timp_maxim:
				v.taiat = True
				return
			if not m.isfile():
				continue
			v.fisiere += 1
			cale = '/' + m.name.lstrip('./')
			d = _dosar_plugin(cale)
			if d and d not in v.dosare and len(v.dosare) < 8:
				v.dosare.append(d)
			nume = cale.rsplit('/', 1)[-1]
			if _PY2_CALE.search(cale):
				v.adauga(DOSAR, cale)
				return
			if nume.endswith('.pyo') or nume.endswith('.pyc'):
				cap = _citeste(t, m, 16)
				ver = versiune_compilat(cap)
				if ver == 2:
					v.adauga(COMPILAT, nume)
					return
				if ver == 3:
					v.python3 = True
					if magic and cap[:4] != magic and not v.alt3:
						v.alt3 = nume
			elif nume.endswith('.so') or '.so.' in nume:
				if m.size <= _SO_OCTETI:
					date = _citeste(t, m, _SO_OCTETI)
					if b'libpython2.' in date:
						v.adauga(LEGAT, nume)
						return
					if b'libpython3.' in date:
						v.python3 = True
			elif nume.endswith('.py') and not v.slabe:
				# un semn slab nu opreste citirea: se cauta mai departe ce e facut pentru Python 3 (.pyc, .so)
				if py < _PY_MAXIM and m.size <= _PY_OCTETI:
					py += 1
					r = din_sursa(_citeste(t, m, _PY_OCTETI), cale)
					if r is not None:
						v.slabe.append(r)
				elif py >= _PY_MAXIM:
					v.taiat = True


def din_ipk(cale, verdict=None, timp_maxim=TIMP_MAXIM, cu_control=True):
	"""verdictul unui fisier .ipk dupa control si dupa continut (arhiva ar ca la Debian sau tar.gz ca la opkg-build
	vechi). Nimic despachetat pe disc, nimic rulat; orice eroare de citire lasa ce s-a aflat pana atunci.
	`cu_control`=False: numai continutul (masuratorile semnelor, una cate una)."""
	v = verdict if verdict is not None else Verdict()
	inceput = _ceas()
	try:
		if os.path.getsize(cale) > _IPK_MAXIM:
			v.taiat = True
			return v
		with open(cale, 'rb') as fh:
			cap = fh.read(8)
			if cap == b'!<arch>\n':
				for _k in range(16):
					antet = fh.read(60)
					if len(antet) < 60:
						break
					nume = antet[:16].strip().rstrip(b'/').decode('ascii', 'replace')
					try:
						marime = int(antet[48:58].strip() or b'0')
					except ValueError:
						break
					if nume.startswith('control.tar') and 0 < marime <= 1024 * 1024 and cu_control:
						din_control(_control(fh.read(marime)), v)
						if marime % 2:
							fh.read(1)
						if v.python2:
							return v
						continue
					if nume.startswith('data.tar') and marime > 0:
						_din_data_tar(_Felie(fh, marime), v, inceput, timp_maxim)
						break
					fh.seek(marime + (marime % 2), 1)
			else:
				fh.seek(0)
				with tarfile.open(fileobj=fh, mode='r:*') as t:
					membri = dict((m.name.lstrip('./'), m) for m in t.getmembers()[:16])
					c = membri.get('control.tar.gz')
					if c is not None and 0 < c.size <= 1024 * 1024 and cu_control:
						din_control(_control(t.extractfile(c).read()), v)
					d = next((membri[n] for n in membri if n.startswith('data.tar')), None)
					if not v.python2 and d is not None:
						_din_data_tar(t.extractfile(d), v, inceput, timp_maxim)
	except _ERORI:
		pass
	except (RecursionError, MemoryError):
		v.taiat = True
	return _incheie(v)


def _incheie(v):
	if v.python2 is None and v.slabe and not v.python3:
		for m in v.slabe:
			v.adauga(*m)
	if v.python2 is None and v.python3:
		v.python2 = False
	return v


def _control(date):
	"""campurile din control.tar.* (dict cu cheile cu litere mici), {} daca nu se poate citi"""
	try:
		with tarfile.open(fileobj=io.BytesIO(date), mode='r:*') as t:
			for m in t:
				if m.isfile() and m.name.lstrip('./') == 'control' and m.size <= 65536:
					text = t.extractfile(m).read().decode('utf-8', 'replace')
					return _strofa(text)
	except _ERORI:
		pass
	return {}


def _strofa(text):
	cur = {}
	ultima = None
	for r in text.split('\n'):
		if not r.strip():
			if cur:
				break
			continue
		if r[0] in ' \t':
			if ultima is not None:
				cur[ultima] += '\n' + r.strip()
			continue
		if ':' in r:
			k, val = r.split(':', 1)
			ultima = k.strip().lower()
			cur[ultima] = val.strip()
	return cur


# ---------------------------------------------------------------- inlocuitorul: numele candidatilor

# sufixele puse de unele feeduri pachetelor vechi, respectiv celor noi
SUFIXE_VECHI = ('-py2', '-python2', '-py27', '-python27')
SUFIXE_NOI = ('-py3', '-python3')

# nume vechi -> nume nou (pachetul pentru Python 3 din feedurile noastre). Facut din date de unealta
# fa_tabel_inlocuitori.py (vezi mai sus): pachetele feedurilor vechi cu Python 2 care pun plugin.py* in acelasi
# dosar de plugin ca un pachet din feedurile noastre, sub alt nume. Acum nu e niciunul: singurul plugin
# enigma2 din feedurile noastre (interfata web din feedul Monea Software) are in feedurile vechi acelasi nume, pe care
# candidati() il incearca oricum; adaosurile lui din feed nu pun plugin.py in dosarul lui si nu intra in tabel.
INLOCUITORI = {
}
# dosarul pluginului (din fisierul .ipk) -> pachetul nostru, din aceeasi unealta (dosarele in care pachetul nostru
# pune plugin.py*). Acum gol: acelasi singur plugin, cu acelasi nume si in fisierele vechi (numele lui nu se
# scrie in codul imaginii, ca orice nume strain).
DOSARE = {
}


def candidati(nume, dosare=()):
	"""numele pachetelor care ar putea inlocui pachetul `nume` (fara el insusi la sfarsit), in ordinea incercarii"""
	n = (nume or '').strip().lower()
	rez = []

	def pune(x):
		if x and x not in rez:
			rez.append(x)
	pune(INLOCUITORI.get(n))
	baza = n
	for s in SUFIXE_VECHI:
		if n.endswith(s):
			baza = n[:-len(s)]
			pune(baza)
			break
	for s in SUFIXE_NOI:
		pune(baza + s)
	for d in dosare or ():
		pune(DOSARE.get(d))
	pune(n)
	return rez
