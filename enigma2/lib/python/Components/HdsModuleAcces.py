# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Modulele de acces instalate pe receptor: lista, alegerea, pornirea, oprirea si repornirea lor. Doar in imaginea
HDSatelit.

Il folosesc ecranul „Module de acces condiționat” (Screens/CamSetup.py) si pagina web /acces-conditionat
(Plugins/Extensions/HdsWebControl/acces_conditionat_web.py). Citirea (felurile, scripturile instalate, legatura aleasa,
ce proces porneste un script) vine din Components/HdsInterfeteCam.py; aici se adauga numai ce schimba ceva: legatura
aleasa si comenzile scripturilor.

Conventia pachetelor de module din feedurile enigma2 (OE-A): fiecare modul instalat pune un script
/etc/init.d/<fel>.<nume> care stie start, stop si restart; <fel>.None e locul gol pus de imagine; legatura
/etc/init.d/<fel> arata spre scriptul ales, iar la pornirea receptorului legatura rc a felului o cheama. Felurile
(al modulelor obisnuite, al serverelor de carduri) se afla dupa forma, la rulare (HdsInterfeteCam.feluri), iar
programele unui fel stau in /usr/<fel>s (dosar_programe). Numele felurilor, ale modulelor si caile lor le dau
receptorul si scripturile, la rulare: in fisierul acesta nu e scris niciun nume de fel sau de modul, nicio cale si
niciun port al vreunuia. Singura exceptie, voita: NUME_MODULE_CUNOSCUTE (MDA, 14.11.2026, la coada fisierului), ca sa se
vada modulul pornit de alt manager; numele modulelor sunt permise din nou in imagine (Eduard, 12.11.2026 05:18).

Reguli:
  - singurul lucru pornit vreodata e un script <fel>.<x> (fel din feluri()) din /etc/init.d, cu unul din cuvintele
    start, stop, restart, fara interpretor de comenzi: eConsoleAppContainer.execute(cale, cale, cuvant) = execvp;
  - un script se porneste numai daca e un fisier executabil care sta chiar in /etc/init.d (nu o legatura spre alt
    loc) si numai daca apare in lista citita chiar atunci;
  - niciun proces nu primeste vreun semnal de la noi; ce ruleaza se afla din /proc/<pid>/exe si comm, comparate cu
    executabilele scrise in script (HdsInterfeteCam._scriptul_porneste);
  - alegerea = legatura schimbata dintr-o bucata: legatura noua langa ea, apoi os.replace;
  - nimic nu blocheaza firul enigma2: scripturile ruleaza in eConsoleAppContainer, cu termen. Containerul se tine in
    viata pana termina scriptul, fiindca distrugerea lui ar opri cu forta tot grupul de procese al scriptului (si un
    emulator pornit de el fara sesiune proprie). Un script care nu termina nu se opreste: se spune doar ca nu a
    terminat.
Modulul se incarca si pe PC (probele): enigma se cere numai cand chiar se porneste un script sau un ceas."""
import codecs
import json
import os
import posixpath
import re
import time

try:
	from Components.HdsInterfeteCam import DOSAR_SCRIPTURI, FISIER_ECM, PROCESE_MAXIM, SUFIX_GOL, \
		Proces, Sistem, _scriptul_porneste, citeste_scripturi, curata_nume, e_script_modul, feluri as _feluri, \
		_CA, _CITITOR_CARD, _FRONTEND, citeste_proces, inode_decriptare, porturi_in_ascultare
except ImportError:  # probe pe PC: modulul incarcat din dosarul Components
	from HdsInterfeteCam import DOSAR_SCRIPTURI, FISIER_ECM, PROCESE_MAXIM, SUFIX_GOL, \
		Proces, Sistem, _scriptul_porneste, citeste_scripturi, curata_nume, e_script_modul, feluri as _feluri, \
		_CA, _CITITOR_CARD, _FRONTEND, citeste_proces, inode_decriptare, porturi_in_ascultare

ACTIUNI = ('start', 'stop', 'restart')
CERERI = ('alege', 'porneste', 'opreste', 'reporneste')

LIMITA_SCRIPT = 60.0     # secunde; dupa atat se spune ca scriptul nu a terminat (scriptul nu se opreste)
VERIFICARI = 6           # dupa script: de cate ori se mai cauta procesul, la o secunda
IESIRE_MAXIM = 8192      # cat se tine din ce scrie scriptul
IESIRE_RANDURI = 3       # cate randuri din raspunsul scriptului se arata
PROGRAME_MAXIM = 64
ECM_MAXIM = 4096
DESCRIERE_MAXIM = 120
CONFIG_WEB_MAXIM = 256 * 1024
SCRIPT_CONFIG_MAXIM = 64 * 1024
VERSIUNE_MAXIM = 64
INFORMATII_MAXIM = 4096
# Pachetele modulelor din feedul nostru pun aici <sufix>.json, cu "versiune" = versiunea reala a autorului (ca la
# „15.8+ (git 10909, 91d9ec1)” sau „2.26.11-11975”). Dosarul e al imaginii si al feedului ei, nu al vreunui
# modul; un modul din alt feed nu are fisierul si versiunea se cauta in titlul scriptului lui.
DOSAR_INFORMATII = '/usr/share/hdsatelit/cam'

_SUFIX_BUN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$')
_STERS = ' (deleted)'


class SistemAcces(Sistem):
	"""Sistemul din HdsInterfeteCam (toate citirile) plus singura scriere a modulului: legatura aleasa."""

	def e_legatura(self, p):
		return os.path.islink(self.cale(p))

	def pune_legatura(self, p, tinta):
		"""p devine legatura spre `tinta` (un nume din acelasi dosar), dintr-o bucata: legatura noua langa ea, apoi
		os.replace. Cine citeste in acelasi timp vede legatura veche sau pe cea noua, niciodata un gol."""
		c = self.cale(p)
		dosar, nume = os.path.split(c)
		nou = os.path.join(dosar, '.' + nume + '.nou')
		if os.path.lexists(nou):
			os.remove(nou)
		os.symlink(tinta, nou)
		try:
			os.replace(nou, c)
		except OSError:
			try:
				os.remove(nou)
			except OSError:
				pass
			raise


# ---------------------------------------------------------------- citirea

def feluri(sistem=None):
	"""Felurile modulelor de pe receptor, in ordinea din ecran (HdsInterfeteCam.feluri): intai al modulelor obisnuite,
	apoi celelalte (serverele de carduri). Numele lor le da receptorul."""
	return _feluri(sistem or SistemAcces())


def dosar_programe(fel):
	"""Dosarul in care pachetele unui fel isi pun programele (conventia OE-A: numele felului la plural, in /usr); numai
	citit, ca sa spunem ce program nu are script."""
	return '/usr/' + fel + 's'


class Emulator(object):
	__slots__ = ('fel', 'sufix', 'script', 'cale', 'descriere', 'versiune', 'ales', 'pids', 'verificabil')

	def __init__(self, fel, script):
		self.fel = fel
		self.sufix = script.sufix
		self.script = script.nume        # <fel>.<x>
		self.cale = script.cale          # /etc/init.d/<fel>.<x>
		self.descriere = curata_nume(script.descriere, DESCRIERE_MAXIM)
		self.versiune = ''               # versiunea reala a modulului (versiune_modul), aratata langa nume
		self.ales = bool(script.ales)
		self.pids = []
		self.verificabil = bool(script.cai)  # scriptul scrie un executabil: se poate vedea daca ruleaza


class Stare(object):
	"""Ce e instalat si ce ruleaza pentru un fel (un fel din feluri())."""

	def __init__(self, fel):
		self.fel = fel
		self.emulatoare = []      # Emulator, dupa sufix
		self.ales = ''            # sufixul spre care arata legatura (SUFIX_GOL sau '' = niciunul)
		self.legatura = 'lipsa'   # 'legatura', 'lipsa' sau 'fisier' (un fisier adevarat in locul ei: nu se atinge)
		self.are_gol = False      # exista <fel>.None
		self.fara_script = []     # programele din dosar_programe(fel) pe care nu le porneste niciun script
		self.ecm = []             # randurile din FISIER_ECM (le scrie emulatorul care decripteaza acum)

	def emulator(self, sufix):
		for e in self.emulatoare:
			if e.sufix == sufix:
				return e
		return None

	def ales_emulator(self):
		for e in self.emulatoare:
			if e.ales:
				return e
		return None

	def pornite(self):
		return [e for e in self.emulatoare if e.pids]


def _script_sigur(sistem, s):
	"""un fisier executabil care sta chiar in dosarul scripturilor, cu un sufix fara semne ciudate"""
	if not _SUFIX_BUN.match(s.sufix) or not sistem.executabil(s.cale):
		return False
	return posixpath.dirname(sistem.tinta(s.cale)) == sistem.tinta(DOSAR_SCRIPTURI)


def scripturile(sistem, fel):
	"""[Script] pentru <fel>.<x> (fara .None), numai cele bune de pornit; cel ales primul, apoi dupa nume"""
	toate = citeste_scripturi(sistem)
	bune = [s for n, s in toate.items() if n.startswith(fel + '.') and _script_sigur(sistem, s)]
	bune.sort(key=lambda s: (not s.ales, s.sufix.lower(), s.sufix))
	return bune


def pornite(sistem, scripturi):
	"""{nume script: [pid]}: procesele pornite de scripturi, din /proc/<pid>/exe si comm. Un proces se da primului
	script (in ordinea primita) care il porneste. Procesul propriu (enigma2) si pid 1 nu intra."""
	tinte = set()
	for s in scripturi:
		tinte.update(s.cai)
		tinte.update(s.cai.values())
	rez = {}
	if not tinte:
		return rez
	try:
		pids = sorted(int(x) for x in sistem.listeaza('/proc') if x.isdigit())
	except OSError:
		return rez
	for pid in pids[:PROCESE_MAXIM]:
		if pid == 1 or pid == sistem.pid_propriu:
			continue
		baza = '/proc/%d' % pid
		try:
			exe = sistem.legatura(baza + '/exe')
		except (OSError, ValueError):
			continue
		if exe.endswith(_STERS):
			exe = exe[:-len(_STERS)]
		if exe not in tinte:
			continue
		p = Proces(pid)
		p.exe = exe
		try:
			p.comm = sistem.citeste(baza + '/comm', 256).strip()
		except (OSError, IOError):
			pass
		for s in scripturi:
			if _scriptul_porneste(s, p):
				rez.setdefault(s.nume, []).append(pid)
				break
	return rez


def programe_fara_script(sistem, scripturi, fel):
	"""numele programelor din dosar_programe(fel) pe care nu le scrie niciun script (nu se pot porni din ecran)"""
	dosar = dosar_programe(fel)
	try:
		nume = sorted(sistem.listeaza(dosar))
	except OSError:
		return []
	folosite = set()
	for s in scripturi:
		folosite.update(s.cai)
		folosite.update(s.cai.values())
	rez = []
	for n in nume[:PROGRAME_MAXIM]:
		c = dosar + '/' + n
		if sistem.executabil(c) and c not in folosite and sistem.tinta(c) not in folosite:
			rez.append(curata_nume(n))
	return rez


def randuri_ecm(sistem):
	try:
		text = sistem.citeste(FISIER_ECM, ECM_MAXIM)
	except (OSError, IOError):
		return []
	return [r for r in (curata_nume(x, DESCRIERE_MAXIM) for x in text.splitlines()) if r]


def memorie(sistem, pid):
	"""randurile VmRSS si Threads din /proc/<pid>/status, cum le scrie nucleul"""
	try:
		text = sistem.citeste('/proc/%d/status' % int(pid), 4096)
	except (OSError, IOError, ValueError):
		return []
	return [' '.join(r.split()) for r in text.splitlines() if r.startswith(('VmRSS:', 'Threads:'))]


def _versiune_buna(text, sufix):
	text = curata_nume(text, VERSIUNE_MAXIM)
	if not text or not any(c.isdigit() for c in text) or text.lower() in sufix.lower():
		return ''
	return text


def versiune_modul(sistem, sufix, descriere=''):
	"""Versiunea reala a modulului, de aratat langa nume (ecranul si pagina web): "versiune" din
	DOSAR_INFORMATII/<sufix>.json (pachetele noastre), altfel primul cuvant din titlul scriptului care incepe cu o cifra
	(„Modul 2.26.11-11975” -> 2.26.11-11975). '' cand nu se afla sau cand numele o are deja (un script modul_15.8).
	Numai citire, fara rularea modulului."""
	if not _SUFIX_BUN.match(sufix or ''):
		return ''
	try:
		date = json.loads(sistem.citeste('%s/%s.json' % (DOSAR_INFORMATII, sufix), INFORMATII_MAXIM))
		v = date.get('versiune') if isinstance(date, dict) else None
		if isinstance(v, str) and _versiune_buna(v, sufix):
			return _versiune_buna(v, sufix)
	except (OSError, IOError, ValueError):
		pass
	for cuvant in (descriere or '').split():
		cuvant = cuvant.strip(',;:()[]')
		if len(cuvant) >= 2 and re.match(r'^[vV]?[0-9]', cuvant):
			return _versiune_buna(cuvant, sufix)
	return ''


def citeste(sistem=None, fel=None, procese=True):
	"""Stare pentru un fel (fara fel: primul din feluri()). Rapid (cateva fisiere mici si /proc/*/exe), deci merge si
	pe firul enigma2."""
	sistem = sistem or SistemAcces()
	if fel is None:
		fel = (feluri(sistem) or [''])[0]
	st = Stare(fel)
	leg = DOSAR_SCRIPTURI + '/' + fel
	try:
		b = posixpath.basename(sistem.legatura(leg))
		st.legatura = 'legatura'
		if b.startswith(fel + '.'):
			st.ales = b[len(fel) + 1:]
	except (OSError, ValueError):
		st.legatura = 'fisier' if sistem.exista(leg) else 'lipsa'
	st.are_gol = sistem.executabil(leg + '.' + SUFIX_GOL)
	scripturi = scripturile(sistem, fel)
	pids = pornite(sistem, scripturi) if procese else {}
	for s in scripturi:
		e = Emulator(fel, s)
		e.ales = st.legatura == 'legatura' and s.sufix == st.ales
		e.pids = pids.get(s.nume, [])
		e.versiune = versiune_modul(sistem, s.sufix, e.descriere)
		st.emulatoare.append(e)
	st.emulatoare.sort(key=lambda e: (e.sufix.lower(), e.sufix))
	st.fara_script = programe_fara_script(sistem, citeste_scripturi(sistem).values(), fel) if fel else []
	st.ecm = randuri_ecm(sistem)
	return st


def pregateste_scripturi(sistem):
	"""0.7.7, inainte de citirea listei: (1) modulele puse ca scripturi ale unui manager de module din Extensii (in afara
	/etc/init.d) primesc scriptul lor <fel>.<id> scris de imagine, ca sa apara in lista ca orice modul
	(Components/HdsAdaptorModule.py); (2) scripturile modulelor instalate din pachete, sterse de scoaterea altui pachet, se pun
	la loc din copia lor (Components/HdsPazaScripturi.py). Nu arunca."""
	for nume in ('HdsPazaScripturi', 'HdsAdaptorModule'):
		try:
			try:
				m = __import__('Components.' + nume, fromlist=[nume])
			except ImportError:  # probe pe PC: modulul incarcat din dosarul Components
				m = __import__(nume)
			m.sincronizeaza(sistem)
		except Exception as e:
			_jurnal("%s: %r" % (nume, e))


def feluri_de_aratat(sistem=None, pregateste=True):
	"""[Stare]: primul fel (al modulelor obisnuite) mereu, celelalte (serverele de carduri) numai cand au macar un
	script. `pregateste`=False: fara pregateste_scripturi (citirea de pe un fir, vezi CitirePeFir; scripturile le pregateste
	firul enigma2)."""
	sistem = sistem or SistemAcces()
	if pregateste:
		pregateste_scripturi(sistem)
	rez = []
	for i, fel in enumerate(feluri(sistem)):
		st = citeste(sistem, fel)
		if i == 0 or st.emulatoare:
			rez.append(st)
	return rez


def dosar_configurare_web(argumente):
	"""Aceeasi conventie ca intrare_cam: -c DOSAR, --config-dir DOSAR sau --config-dir=DOSAR."""
	dosar = None
	for i, a in enumerate(argumente):
		if a in ('-c', '--config-dir') and i + 1 < len(argumente):
			dosar = argumente[i + 1]
		elif a.startswith('--config-dir='):
			dosar = a.split('=', 1)[1]
	if not dosar or not dosar.startswith('/') or any(ord(c) < 32 or ord(c) == 127 for c in dosar):
		return None
	return posixpath.normpath(dosar)


_SPATII_SCRIPT = ' \t\r\n'
_SEMNE_SCRIPT = ';&|<>'
# Randurile care nu pornesc modulul: utilitarele scripturilor si interpretoarele de comenzi, recunoscute dupa nume
# (sh si toate cele care se termina in sh), ca argumentul lor -c (o comanda) sa nu fie luat drept dosar.
_UNELTE_SCRIPT = ('echo', 'printf', 'test', '[', 'cat', 'env')
_INTERPRETOR_SCRIPT = re.compile(r'^[a-z]{0,3}sh$')


def _imparte_cuvinte(text):
	"""Imparte un rand de script in cuvinte, fara sa-l ruleze: spatiile despart cuvintele, un sir de semne ;&|<> e un
	cuvant al lui, '...' pastreaza tot, in "..." backslash scapa numai " si backslash, afara backslash scapa orice semn,
	# in afara ghilimelelor incepe un comentariu (si in mijlocul unui cuvant: _cuvinte_config_script scapa dinainte #
	care in shell nu ar incepe un comentariu). Ghilimele neinchise sau backslash la sfarsit -> ValueError.
	Aceleasi reguli ca shlex.shlex(text, posix=True, punctuation_chars=';&|<>') cu whitespace_split, pe care regula
	ecranului CAM nu il lasa in acest fisier (proba de echivalenta: teste/test_module_cuvinte_script_071.py)."""
	cuvinte, cuvant, are_cuvant, i, n = [], [], False, 0, len(text)
	while i < n:
		c = text[i]
		if c in _SPATII_SCRIPT:
			if are_cuvant:
				cuvinte.append(''.join(cuvant))
				cuvant, are_cuvant = [], False
			i += 1
		elif c in _SEMNE_SCRIPT:
			if are_cuvant:
				cuvinte.append(''.join(cuvant))
				cuvant, are_cuvant = [], False
			j = i
			while j < n and text[j] in _SEMNE_SCRIPT:
				j += 1
			cuvinte.append(text[i:j])
			i = j
		elif c == '#':
			break
		elif c == '\\':
			if i + 1 >= n:
				raise ValueError('No escaped character')
			cuvant.append(text[i + 1])
			are_cuvant = True
			i += 2
		elif c == "'":
			j = text.find("'", i + 1)
			if j < 0:
				raise ValueError('No closing quotation')
			cuvant.append(text[i + 1:j])
			are_cuvant = True
			i = j + 1
		elif c == '"':
			i += 1
			while True:
				if i >= n:
					raise ValueError('No closing quotation')
				d = text[i]
				if d == '"':
					i += 1
					break
				if d == '\\' and i + 1 < n and text[i + 1] in '"\\':
					cuvant.append(text[i + 1])
					i += 2
				else:
					cuvant.append(d)
					i += 1
			are_cuvant = True
		else:
			cuvant.append(c)
			are_cuvant = True
			i += 1
	if are_cuvant:
		cuvinte.append(''.join(cuvant))
	return cuvinte


_PARTI_SHELL = re.compile(r"""'[^']*'|"(?:\\.|[^"\\])*"|\\.|[^'"\\]+""")
_EXPANSIUNE_SHELL = re.compile(r'\\.|\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))|\$|`')
_ATRIBUIRE_CONFIG = re.compile(r'^([A-Za-z_][A-Za-z0-9_]*)=')
_MARCA_CONFIG = re.compile('\x01([0-9]+)\x02')


def _cuvinte_config_script(linie, valori):
	"""Numai cuvinte si variabile simple; fara evaluarea shellului sau a substituirilor de comenzi."""
	if '\x01' in linie or '\x02' in linie:
		return []
	inlocuiri = []
	atribuire = re.match(r'^\s*(?:(?:export|readonly|local)\s+)?[A-Za-z_][A-Za-z0-9_]*=', linie)
	def parte(m):
		text = m.group(0)
		if text.startswith(("'", '\\')):
			return text
		if not text.startswith('"'):
			# _imparte_cuvinte (ca shlex) ia orice # ca inceput de comentariu; shellul numai la inceput de cuvant.
			text = ''.join('\\#' if c == '#' and m.start() + i > 0 and
				linie[m.start() + i - 1] not in ' \t\r\n;&|<>()' else c for i, c in enumerate(text))
		def expansiune(v):
			if v.group(0).startswith('\\'):
				return v.group(0)
			valoare = valori.get(v.group(1) or v.group(2))
			# Fara citate, shellul poate desparti valoarea sau extinde un tipar de fisiere.
			if not atribuire and not text.startswith('"') and valoare is not None and re.search(r'[\s*?\[]', valoare):
				valoare = None
			inlocuiri.append(valoare)
			return '\x01%d\x02' % (len(inlocuiri) - 1)
		return _EXPANSIUNE_SHELL.sub(expansiune, text)
	try:
		cuvinte = _imparte_cuvinte(_PARTI_SHELL.sub(parte, linie))
		for i, cuvant in enumerate(cuvinte):
			if any(inlocuiri[int(m.group(1))] is None for m in _MARCA_CONFIG.finditer(cuvant)):
				return []
			cuvinte[i] = _MARCA_CONFIG.sub(lambda m: inlocuiri[int(m.group(1))], cuvant)
		return cuvinte
	except ValueError:
		return []


# Scripturile modulelor din feedul nostru (din 13.11.2026) aleg dosarul abia la pornire, CONFDIR=$(choose_confdir):
# dosarul pachetului (OWNDIR, unde instalarea pune configurarea de inceput) sau locul original in care omul isi tine
# fisierele (unul din ORIGDIRS); pe cel ales la ultima pornire il scriu in LASTDIR. Fara rularea scriptului (aici se
# pornesc numai start, stop si restart), cele trei se citesc ca atribuiri simple.
_ALEGERE_LA_PORNIRE = re.compile(r'''^[ \t]*CONFDIR=["']?\$\([ \t]*choose_confdir[ \t]*\)["']?[ \t]*$''', re.M)


def _dosar_bun(dosar):
	return dosar_configurare_web(['--config-dir', dosar]) if isinstance(dosar, str) else None


def _citeste_script_config(text):
	"""(dosarele din pornirile scriptului, atribuirile simple de la nivelul de sus)"""
	valori, dosare, nivel = {}, set(), 0
	for linie in text[:SCRIPT_CONFIG_MAXIM].replace('\\\r\n', '').replace('\\\n', '').splitlines():
		if re.match(r'^\s*(if|case|for|while|until)\b', linie):
			nivel += 1
		elif re.match(r'^\s*(fi|esac|done)\b', linie):
			nivel = max(0, nivel - 1)
		cuvinte = _cuvinte_config_script(linie, valori)
		if not cuvinte:
			# O atribuire dinamica ulterioara nu trebuie sa lase valabila vechea valoare.
			atribuire = re.match(r'^\s*(?:(?:export|readonly|local)\s+)?([A-Za-z_][A-Za-z0-9_]*)=', linie)
			if atribuire:
				valori.pop(atribuire.group(1), None)
			continue
		for i, cuvant in enumerate(cuvinte):
			if cuvant and all(c in ';&|<>' for c in cuvant):
				if any(_ATRIBUIRE_CONFIG.match(c) for c in cuvinte[i + 1:]):
					# Nu evaluam comenzi in lant sau atribuiri conditionate prin && / ||.
					for c in cuvinte:
						m = _ATRIBUIRE_CONFIG.match(c)
						if m:
							valori.pop(m.group(1), None)
					cuvinte = []
				else:
					cuvinte = cuvinte[:i]
				break
		if cuvinte and cuvinte[0] in ('export', 'readonly', 'local'):
			cuvinte = cuvinte[1:]
		while cuvinte and _ATRIBUIRE_CONFIG.match(cuvinte[0]):
			nume, valoare = cuvinte.pop(0).split('=', 1)
			if nivel:
				valori.pop(nume, None)
			else:
				valori[nume] = valoare
		if cuvinte and cuvinte[0] == 'exec':
			cuvinte = cuvinte[1:]
		if not cuvinte:
			continue
		program = cuvinte[0]
		nume_program = posixpath.basename(program)
		if nume_program in _UNELTE_SCRIPT or _INTERPRETOR_SCRIPT.match(nume_program):
			continue
		if posixpath.basename(program) == 'start-stop-daemon':
			# Optiunile modulului sunt dupa --; cele ale uneltei nu sunt configurarea modulului.
			if '--start' not in cuvinte or '--' not in cuvinte:
				continue
			if 'DAEMON' in valori:
				if '--exec' not in cuvinte or cuvinte[cuvinte.index('--exec') + 1:][:1] != [valori['DAEMON']]:
					continue
			cuvinte = cuvinte[cuvinte.index('--') + 1:]
		elif not program.startswith('/'):
			continue
		elif 'DAEMON' in valori and program != valori['DAEMON']:
			continue
		dosar = dosar_configurare_web(cuvinte)
		if dosar is not None:
			dosare.add(dosar)
	return dosare, valori


def dosare_alese_din_script(text):
	"""Pentru un script care alege dosarul la pornire (_ALEGERE_LA_PORNIRE): (OWNDIR, [locurile permise], LASTDIR);
	altfel None."""
	text = text[:SCRIPT_CONFIG_MAXIM]
	if not _ALEGERE_LA_PORNIRE.search(text):
		return None
	_dosare, valori = _citeste_script_config(text)
	propriu = _dosar_bun(valori.get('OWNDIR'))
	if propriu is None:
		return None
	locuri = [propriu] + [d for d in (_dosar_bun(x) for x in valori.get('ORIGDIRS', '').split()) if d]
	ultimul = valori.get('LASTDIR')
	ultimul = ultimul if isinstance(ultimul, str) and ultimul.startswith('/') else None
	return propriu, locuri, ultimul


def dosar_configurare_din_script(text):
	"""Argumentele unei porniri directe sau start-stop-daemon, cu atribuiri simple. Ambiguu -> necunoscut. Un script
	care alege dosarul la pornire da dosarul pachetului (OWNDIR)."""
	dosare, _valori = _citeste_script_config(text)
	if len(dosare) == 1:
		return next(iter(dosare))
	if not dosare:
		ales = dosare_alese_din_script(text)
		if ales:
			return ales[0]
	return None


def dosar_ales_ultima_data(sistem, text):
	"""Dosarul citit la ultima pornire de un script care alege dosarul la pornire (LASTDIR), numai daca e unul din
	locurile scrise in script; altfel None."""
	ales = dosare_alese_din_script(text)
	if not ales or not ales[2]:
		return None
	try:
		dosar = _dosar_bun(sistem.citeste(ales[2], 256).strip())
	except (OSError, IOError, ValueError):
		return None
	return dosar if dosar in ales[1] else None


def dosare_configurare(sistem=None, stari=None):
	"""Dosarul fiecarui modul, inclusiv oprit/neales. Numai argumente, scripturi si stat, pe fir separat."""
	sistem = sistem or SistemAcces()
	stari = feluri_de_aratat(sistem) if stari is None else stari
	rez = []
	for st in stari:
		for e in st.emulatoare:
			dosar = None
			for pid in e.pids[:PROGRAME_MAXIM]:
				try:
					argumente = sistem.citeste('/proc/%d/cmdline' % pid, 8192).split('\0')[1:]
					dosar = dosar_configurare_web(argumente)
				except (OSError, IOError, ValueError):
					continue
				if dosar is not None:
					break
			if dosar is None:
				try:
					text = sistem.citeste(e.cale, SCRIPT_CONFIG_MAXIM)
					dosar = dosar_ales_ultima_data(sistem, text) or dosar_configurare_din_script(text)
				except (OSError, IOError, ValueError):
					pass
			rez.append({'fel': st.fel, 'sufix': e.sufix, 'dosar': dosar.rstrip('/') + '/' if dosar else '',
				'exista': bool(dosar and os.path.isdir(sistem.cale(dosar)))})
	return rez


def nume_configurari_web(comm, exe):
	"""Nume de proces/executabil si radacina lor, in aceeasi ordine ca navigatorul; fara nume de module in cod. La
	coada si aceleasi nume cu litere mici (un program redenumit cu majuscule citeste tot configurarea cu litere mici)."""
	rez = []
	for nume in (comm, posixpath.basename(exe or '')):
		for n in (nume, re.split(r'[-_.]', nume or '')[0]):
			if n and _SUFIX_BUN.match(n) and n + '.conf' not in rez:
				rez.append(n + '.conf')
	for n in list(rez):
		if n.lower() not in rez:
			rez.append(n.lower())
	return rez


def port_web_din_randuri(randuri):
	"""Numai httpport din [webif]. Nu pastreaza si nu intoarce alte setari; + inseamna HTTPS."""
	sectiune = ''
	for rand in randuri:
		r = rand.decode('utf-8', 'replace') if isinstance(rand, bytes) else rand
		r = r.split('#', 1)[0].split(';', 1)[0].strip()
		if r.startswith('[') and r.endswith(']'):
			sectiune = r[1:-1].strip().lower()
		elif sectiune == 'webif' and re.match(r'^httpport\s*=', r, re.IGNORECASE):
			valoare = r.split('=', 1)[1].strip()
			if not re.match(r'^\+?[0-9]{1,5}$', valoare):
				return None
			port = int(valoare)
			return {'port': port, 'protocol': 'https' if valoare.startswith('+') else 'http'} if 0 < port < 65536 else None
	return None


def _port_web_configurare(sistem, cale):
	"""Citire limitata, rand cu rand; continutul configurarii nu se copiaza si nu se scrie in jurnal."""
	def randuri(fisier):
		ramas = CONFIG_WEB_MAXIM
		while ramas > 0:
			rand = fisier.readline(ramas + 1)
			if not rand or len(rand) > ramas:
				return
			ramas -= len(rand)
			yield rand
	try:
		with open(sistem.cale(cale), 'rb') as fisier:
			return port_web_din_randuri(randuri(fisier))
	except (OSError, IOError, ValueError):
		return None


def eticheta_modul(e):
	"""Numele modulului de aratat: sufixul, cu versiunea reala langa el cand se stie
	(„modul 15.8+ (git 10909, 91d9ec1)”)."""
	return e.sufix + (' ' + e.versiune if e.versiune else '')


# Unde se cauta configurarea unui modul pornit FARA -c / --config-dir (atunci modulul citeste dosarul scris in programul
# lui, pe care nu-l putem afla fara sa-l rulam): intai dosarele din scriptul lui, apoi locurile obisnuite ale modulelor
# din feedurile enigma2, fiecare si cu dosarul numelui modulului in el (<loc>/<nume>, ca /etc/tuxbox/config/<nume>).
# Exceptie voita de la regula fara cai din capul fisierului, ca NUME_MODULE_CUNOSCUTE. Un dosar gasit asa se crede numai
# daca procesele modulului chiar asculta pe portul citit (porturi_procese); numai httpport se citeste, ca pana acum.
DOSARE_CONFIG_OBISNUITE = ('/etc/tuxbox/config', '/var/tuxbox/config', '/usr/keys', '/var/keys', '/var/etc',
	'/usr/local/etc', '/etc')
DOSARE_GHICITE_MAXIM = 64


def porturi_procese(sistem, pids, ascultare=None):
	"""Porturile TCP pe care asculta procesele `pids` ale unui modul (paznicul si copilul lui: socket-ul il tine de obicei
	copilul), din /proc/net/tcp, /proc/net/tcp6 si /proc/<pid>/fd. `ascultare` = {inode: (adresa, port)} citit o data de
	cel care cheama, sau None. Numai citire, nicio conexiune."""
	if ascultare is None:
		ascultare = porturi_in_ascultare(sistem)
	rez = set()
	for pid in pids[:PROGRAME_MAXIM]:
		try:
			p = citeste_proces(sistem, pid)
		except Exception:
			p = None
		if p is None:
			continue
		for inode in p.socketuri:
			if inode in ascultare:
				rez.add(ascultare[inode][1])
	return rez


def dosare_ghicite(nume_conf, dosare_script=()):
	"""Dosarele in care se cauta configurarea unui modul pornit fara -c, in ordine: cele din scriptul lui, apoi
	DOSARE_CONFIG_OBISNUITE, fiecare intai cu dosarul numelui modulului (numele din `nume_conf` si inceputurile lor pana la
	o liniuta: un program redenumit <nume>-<ceva> isi tine de obicei configurarea in dosarul <nume>). Fara dubluri, cel
	mult DOSARE_GHICITE_MAXIM."""
	radacini = []
	for n in nume_conf:
		r = n[:-len('.conf')] if n.endswith('.conf') else n
		parti = r.split('-')
		for i in range(len(parti), 0, -1):
			p = '-'.join(parti[:i])
			if p and p not in radacini:
				radacini.append(p)
	rez = []
	for d in list(dosare_script or ()) + [posixpath.join(b, r) for b in DOSARE_CONFIG_OBISNUITE for r in radacini + ['']]:
		d = posixpath.normpath(d) if d else ''
		if d.startswith('/') and d not in rez:
			rez.append(d)
	return rez[:DOSARE_GHICITE_MAXIM]


def _interfata_din_dosar(sistem, dosar, nume_conf):
	"""{port, protocol} din prima configurare <dosar>/<nume> care exista (ordinea din `nume_conf`), sau None."""
	for nume in nume_conf:
		cale = posixpath.join(dosar, nume)
		if os.path.isfile(sistem.cale(cale)):
			return _port_web_configurare(sistem, cale)
	return None


def _dosare_din_script(sistem, cale):
	"""Dosarul ales la ultima pornire si cel scris in scriptul modulului (ca dosare_configurare), fara rularea lui."""
	try:
		text = sistem.citeste(cale, SCRIPT_CONFIG_MAXIM)
	except (OSError, IOError, ValueError):
		return []
	return [d for d in (dosar_ales_ultima_data(sistem, text), dosar_configurare_din_script(text)) if d]


def interfata_modul(sistem, pids, cale_script=None, citite=None):
	"""{port, protocol} al interfetei web a unui modul care ruleaza (procesele lui `pids`), sau None. Dosarul din linia de
	comanda (-c, --config-dir) se crede ca pana acum. Cand niciun proces nu are dosarul in linia de comanda, se cauta
	in dosare_ghicite (intai dosarele scriptului `cale_script`), iar portul gasit se crede numai daca procesele modulului
	chiar asculta pe el. `citite` = {} tinut de cel care cheama, ca /proc/net/tcp sa se citeasca o singura data."""
	citite = {} if citite is None else citite
	nume_toate, are_dosar = [], False
	for pid in pids[:PROGRAME_MAXIM]:
		baza = '/proc/%d' % pid
		try:
			argumente = sistem.citeste(baza + '/cmdline', 8192).split('\0')[1:]
			comm = sistem.citeste(baza + '/comm', 256).strip()
			exe = sistem.legatura(baza + '/exe')
		except (OSError, IOError, ValueError):
			continue
		if exe.endswith(_STERS):
			exe = exe[:-len(_STERS)]
		nume_conf = nume_configurari_web(comm, exe)
		dosar = dosar_configurare_web(argumente)
		if dosar is None:
			nume_toate.extend(n for n in nume_conf if n not in nume_toate)
			continue
		are_dosar = True
		interfata = _interfata_din_dosar(sistem, dosar, nume_conf)
		if interfata:
			return interfata
	if are_dosar or not nume_toate:
		return None
	porturi = None
	dosare = _dosare_din_script(sistem, cale_script) if cale_script else []
	for dosar in dosare_ghicite(nume_toate, dosare):
		interfata = _interfata_din_dosar(sistem, dosar, nume_toate)
		if not interfata:
			continue
		if porturi is None:
			if 'ascultare' not in citite:
				citite['ascultare'] = porturi_in_ascultare(sistem)
			porturi = porturi_procese(sistem, pids, citite['ascultare'])
		if interfata['port'] in porturi:
			return interfata
	return None


def interfete_web(sistem=None, stari=None):
	"""Modulele active care au interfata web: [{fel, sufix, versiune, eticheta, protocol, port}], portul/protocolul din
	configurarea lor, fara conexiuni. Se cheama pe un fir separat. O singura sursa pentru ecran, pagina Acces
	condiționat, prima pagina web si bara de sus (GET /api/acces-conditionat-interfete); adresa o face fiecare din
	adresa receptorului: <protocol>://<gazda>:<port>/. Intai modulele din lista (felurile in ordinea lor), apoi cele
	pornite de alt program (pornite_de_alt_program): acestea au fel '', sufixul si eticheta = numele procesului si
	pid = primul lor PID (al randului lor din ecran si din pagina Acces condiționat)."""
	sistem = sistem or SistemAcces()
	stari = feluri_de_aratat(sistem) if stari is None else stari
	rez = []
	citite = {}
	for st in stari:
		for e in st.emulatoare:
			if not e.pids:
				continue
			interfata = interfata_modul(sistem, e.pids, e.cale, citite)
			if interfata:
				rez.append(dict(interfata, fel=st.fel, sufix=e.sufix, versiune=e.versiune, eticheta=eticheta_modul(e)))
	for a in pornite_de_alt_program(sistem, stari, descriptori=False):
		interfata = interfata_modul(sistem, a['pids'], None, citite)
		if interfata:
			rez.append(dict(interfata, fel='', sufix=a['nume'], versiune='', eticheta=a['nume'], pid=a['pids'][0]))
	return rez


# ---------------------------------------------------------------- parola din reteaua de acasa
# Interfetele web ale modulelor de acces pornesc fara utilizator si fara parola in casa (asa vin
# configurarile noastre: numai httpallowed cu retelele de acasa). Numai daca omul isi pune parola locala si bifeaza
# "Interfețele web ale modulelor de acces" (Components/HdsParolaLocala.py), in sectiunea [webif] a fiecarei configurari
# se scriu httpuser = root si httppwd = parola lui, dupa randul MARCA_PAROLA; fara bifa se scot numai randurile de dupa
# marca (cele puse de om cu mana raman). Modulul le citeste la urmatoarea pornire.
MARCA_PAROLA = '# parola din reteaua de acasa (Setari > Retea > Parola receptorului)'


def parola_web_in_randuri(randuri, parola):
	"""Randurile unei configurari cu parola pusa (parola text) sau scoasa (None) in [webif]. Intoarce lista noua, sau
	None cand fisierul nu are [webif] (nu e configurarea unei interfete web) ori nu se schimba nimic."""
	iesire, sectiune, are_webif, sari = [], '', False, False
	for rand in randuri:
		r = rand.strip()
		if r.startswith('[') and r.endswith(']'):
			if sectiune == 'webif' and parola is not None:
				iesire.extend([MARCA_PAROLA, 'httpuser = root', 'httppwd = %s' % parola])
			sectiune = r[1:-1].strip().lower()
			are_webif = are_webif or sectiune == 'webif'
			iesire.append(rand)
			continue
		if r == MARCA_PAROLA:
			sari = True
			continue
		if sari and re.match(r'^(httpuser|httppwd)\s*=', r, re.IGNORECASE):
			continue
		sari = False
		if sectiune == 'webif' and parola is not None and re.match(r'^(httpuser|httppwd)\s*=', r, re.IGNORECASE):
			continue  # parola omului inlocuieste ce era scris aici
		iesire.append(rand)
	if sectiune == 'webif' and parola is not None:
		while iesire and not iesire[-1].strip():
			iesire.pop()
		iesire.extend([MARCA_PAROLA, 'httpuser = root', 'httppwd = %s' % parola, ''])
	if not are_webif or iesire == list(randuri):
		return None
	return iesire


def puneParolaWeb(parola, sistem=None):
	"""Pune (text) sau scoate (None) parola din [webif] a configurarilor tuturor modulelor gasite (si oprite).
	Intoarce True daca n-a fost nicio eroare de scriere."""
	sistem = sistem or SistemAcces()
	bine = True
	vazute = set()
	for d in dosare_configurare(sistem):
		dosar = d.get('dosar')
		if not dosar or dosar in vazute or not d.get('exista'):
			continue
		vazute.add(dosar)
		try:
			nume_fisiere = sorted(os.listdir(sistem.cale(dosar)))
		except OSError:
			continue
		for nume in nume_fisiere:
			if not nume.endswith('.conf'):
				continue
			cale = sistem.cale(posixpath.join(dosar, nume))
			try:
				if os.path.islink(cale) or not os.path.isfile(cale) or os.path.getsize(cale) > CONFIG_WEB_MAXIM:
					continue
				with open(cale, 'r', encoding='utf-8', errors='surrogateescape') as f:
					text = f.read()
				noi = parola_web_in_randuri(text.split('\n'), parola)
				if noi is None:
					continue
				mod = os.stat(cale).st_mode & 0o7777
				nou = cale + '.nou'
				with open(nou, 'w', encoding='utf-8', errors='surrogateescape') as f:
					f.write('\n'.join(noi))
				os.chmod(nou, mod)
				os.replace(nou, cale)
			except (OSError, IOError, ValueError):
				bine = False
	return bine


def argv_script(sistem, fel, sufix, actiune):
	"""(cale, cale, actiune) pentru execvp, sau None cand nu e un script bun de pornit chiar acum"""
	if actiune not in ACTIUNI or not fel or not _SUFIX_BUN.match(sufix or '') or fel not in feluri(sistem):
		return None
	nume = fel + '.' + sufix
	if not e_script_modul(nume, (fel,)):
		return None
	for s in scripturile(sistem, fel):
		if s.nume == nume:
			cale = sistem.cale(s.cale)
			return (cale, cale, actiune)
	return None


# ---------------------------------------------------------------- pornirea scripturilor, fara sa blocheze

_in_lucru = []      # scripturile care nu au terminat: containerul tinut in viata pana la appClosed
_curenta = [None]   # o singura operatie deodata (ecranul si pagina web)
_generatie = [0]    # 0.7.7: creste la sfarsitul fiecarei operatii (generatie())


def in_curs():
	o = _curenta[0]
	return o if o is not None and not o.gata else None


def generatie():
	"""0.7.7: un numar care creste la sfarsitul fiecarei operatii (Operatie._termina). O citire pe fir (CitirePeFir) pornita
	inainte ca el sa creasca e veche: ecranul o arunca si citeste din nou."""
	return _generatie[0]


class Executor(object):
	"""porneste(argv, la_final) -> True daca scriptul a pornit; la_final(cod, iesire) vine pe firul enigma2 cand
	scriptul termina. argv = (cale, cale, actiune): program, argv0, argument, fara interpretor de comenzi."""

	def porneste(self, argv, la_final):
		from enigma import eConsoleAppContainer
		c = eConsoleAppContainer()
		# eConsoleAppContainer da octeti: decodati pe masura ce vin (un caracter taiat intre doua citiri iese intreg)
		lucru = {'container': c, 'iesire': [], 'marime': 0,
			'decodor': codecs.getincrementaldecoder('utf-8')('replace')}

		def date(text):
			if isinstance(text, (bytes, bytearray)):
				text = lucru['decodor'].decode(text)
			if lucru['marime'] < IESIRE_MAXIM:
				lucru['iesire'].append(text[:IESIRE_MAXIM - lucru['marime']])
				lucru['marime'] += len(text)

		def inchis(cod):
			del c.appClosed[:]
			del c.dataAvail[:]
			if lucru in _in_lucru:
				_in_lucru.remove(lucru)
			date(lucru['decodor'].decode(b'', True))
			la_final(cod, ''.join(lucru['iesire']))

		c.dataAvail.append(date)
		c.appClosed.append(inchis)
		_in_lucru.append(lucru)
		if c.execute(*argv):
			del c.appClosed[:]
			del c.dataAvail[:]
			_in_lucru.remove(lucru)
			return False
		return True


class Temporizator(object):
	"""un eTimer cu o singura declansare; opreste() il anuleaza"""

	def __init__(self, secunde, functie):
		from enigma import eTimer
		self.ceas = eTimer()
		self.ceas.callback.append(functie)
		self.ceas.start(int(secunde * 1000), True)

	def opreste(self):
		self.ceas.stop()


def raspuns_scurt(iesire):
	"""ultimele randuri scrise de script, curatate, ca text de aratat (nu trece prin traducere)"""
	randuri = [r for r in (curata_nume(x, DESCRIERE_MAXIM) for x in (iesire or '').splitlines()) if r]
	return ' / '.join(randuri[-IESIRE_RANDURI:])


class Operatie(object):
	"""O cerere a omului, facuta pas cu pas, fiecare script dupa ce a terminat cel dinainte:
	  alege <sufix>     opreste emulatorul ales si pe cele care ruleaza, schimba legatura, porneste emulatorul nou
	                    (SUFIX_GOL = niciunul: numai oprire si legatura spre <fel>.None);
	  porneste <sufix>  scriptul lui cu start;
	  opreste           scripturile celor care ruleaza cu stop (sau al celui ales, cand nu se vede niciunul pornit);
	  reporneste        scriptul celui ales (sau al celui dat) cu restart.
	Dupa fiecare script se verifica in /proc starea asteptata (cel mult VERIFICARI secunde). la_pas(actiune, nume)
	spune ce incepe; la_final(rezultat) vine o singura data, cu {'ok', 'motiv', 'fel', 'nume', 'cod', 'raspuns',
	'eroare', 'secunde', 'ramane_ales'}. Motivele: ales, niciunul, pornit, oprit, repornit, ruleaza_deja,
	nimic_pornit, niciunul_ales, ocupat, necunoscut, nu_e_legatura, legatura, nu_a_pornit, nu_s_a_oprit, termen.
	0.7.7: pe receptor (sistemul adevarat, citire_pe_fir) starea de la pornire, scriptul fiecarui pas si starea de dupa
	fiecare script se citesc pe un fir (_pe_fir); `cititor` (CitirePeFir) se da la probe."""

	def __init__(self, cerere, fel=None, sufix=None, sistem=None, executor=None, temporizator=None,
			la_pas=None, la_final=None, limita=LIMITA_SCRIPT, verificari=VERIFICARI, cititor=None):
		sistem = sistem or SistemAcces()
		lista = feluri(sistem)
		if fel is None and lista:
			fel = lista[0]
		if cerere not in CERERI or fel not in lista:
			raise ValueError(cerere)
		self.cerere = cerere
		self.fel = fel
		self.sufix = sufix
		self.sistem = sistem
		self.executor = executor or Executor()
		self.temporizator = temporizator or Temporizator
		self.la_pas = la_pas
		self.la_final = la_final
		self.limita = limita
		self.verificari = verificari
		self.gata = False
		self.rezultat = None
		self._pasi = []
		self._pas = None
		self._ceas = None
		self._ramase = 0
		self._cod = None
		self._iesire = ''
		self._final = ('', '')
		self._ramane_ales = False
		self.cititor = cititor
		self._citiri = 0

	# ------------------------------------------------ citirea pe un fir (0.7.7)
	# Starea unui fel (citeste: legatura, scripturile, /proc pentru fiecare proces) si scriptul unui pas (argv_script) fac pe
	# receptor cateva sute de apeluri de sistem. Pe firul enigma2, cat calcula alt fir Python (importul ghidului IPTV in minutele
	# de dupa pornirea interfetei), fiecare apel astepta lacatul Python ~5 ms: Verde, Rosu si alegerea facuta de paza tineau
	# interfata 3-4,5 s (receptorul de probe, cu ghidul fara pauze). Acum citirile merg pe un fir (CitirePeFir), iar planul,
	# scriptul si legatura raman pe firul enigma2, in aceeasi ordine: in aceeasi proba apasarea Verde raspunde in ~1 s si
	# interfata nu mai sta. Pe un sistem de proba (o radacina intr-un dosar) totul merge pe loc, ca pana acum.
	def _pe_fir(self, lucru, mai_departe, nume=''):
		"""lucru(sistem) pe un fir, apoi mai_departe(rezultat) pe firul enigma2. Rezultatul venit dupa sfarsitul operatiei (sau al
		unei citiri mai vechi) se arunca; o citire care cade sau nu se termina in `limita` secunde termina operatia."""
		sistem = self.sistem
		if not citire_pe_fir(sistem):
			mai_departe(lucru(sistem))
			return
		self._citiri += 1
		semn = self._citiri

		def gata(rezultat, eroare):
			if self.gata or semn != self._citiri:
				return
			self._opreste_ceasul()
			if eroare is not None:
				_jurnal("%s %s: citirea starii: %r" % (self.cerere, self.fel, eroare))
				self._termina(False, 'necunoscut', nume=curata_nume(nume))
				return
			mai_departe(rezultat)
		try:
			if self.cititor is None:
				self.cititor = CitirePeFir()
			self._ceas = self.temporizator(self.limita, lambda: self._termen_citire(semn, nume))
			pornita = self.cititor.porneste(lambda: lucru(SistemCuMemorie(sistem)), gata)
		except Exception as e:
			# citirea n-a pornit (firul, ceasul): operatia se termina, ca zavorul operatiilor (in_curs) sa nu ramana luat
			_jurnal("%s %s: citirea pe fir nu a pornit: %r" % (self.cerere, self.fel, e))
			self._termina(False, 'necunoscut', nume=curata_nume(nume))
			return
		if not pornita:
			# nu se intampla (o singura citire a operatiei odata); ca inainte, pe loc
			self._opreste_ceasul()
			mai_departe(lucru(sistem))

	def _termen_citire(self, semn, nume):
		if self.gata or semn != self._citiri:
			return
		self._ceas = None
		self._termina(False, 'termen', nume=curata_nume(nume), secunde=int(self.limita))

	# ------------------------------------------------ planul
	def porneste(self):
		"""True daca a inceput; altfel rezultatul e deja dat prin la_final. Pe receptor starea se citeste pe un fir: atunci
		porneste() intoarce True, iar un plan care nu se poate face (ruleaza deja, modul necunoscut) vine tot prin la_final,
		putin mai tarziu. Operatia e in curs (in_curs) chiar de la porneste()."""
		if in_curs() is not None:
			self._termina(False, 'ocupat')
			return False
		fel = self.fel
		if citire_pe_fir(self.sistem):
			_curenta[0] = self
			self._pe_fir(lambda s: citeste(s, fel), self._dupa_citire, self.sufix or '')
			return True
		st = citeste(self.sistem, fel)
		if not self._planifica(st):
			return False
		_curenta[0] = self
		self._urmatorul()
		return True

	def _dupa_citire(self, st):
		if self._planifica(st):
			self._urmatorul()

	def _planifica(self, st):
		ales = st.ales_emulator()
		if self.cerere in ('alege', 'porneste') and self.sufix not in (None, '', SUFIX_GOL):
			tinta = st.emulator(self.sufix)
			if tinta is None:
				self._termina(False, 'necunoscut', nume=curata_nume(self.sufix))
				return False
		else:
			tinta = None
		if self.cerere == 'alege' and tinta is not None and tinta is ales:
			self.cerere = 'porneste'
		if self.cerere == 'porneste':
			if tinta is None:
				self._termina(False, 'necunoscut', nume=curata_nume(self.sufix or ''))
				return False
			if tinta.pids:
				self._termina(True, 'ruleaza_deja', nume=tinta.sufix)
				return False
			self._pasi = [('script', tinta.sufix, 'start')]
			self._final = ('pornit', tinta.sufix)
			self._ramane_ales = tinta.ales
			return True
		if self.cerere == 'alege':
			if st.legatura == 'fisier':
				self._termina(False, 'nu_e_legatura', nume=DOSAR_SCRIPTURI + '/' + self.fel)
				return False
			de_oprit = []
			for e in ([ales] if ales is not None else []) + st.pornite():
				if e is not tinta and e not in de_oprit:
					de_oprit.append(e)
			self._pasi = [('script', e.sufix, 'stop') for e in de_oprit]
			self._pasi.append(('leaga', tinta.sufix if tinta is not None else SUFIX_GOL, ''))
			if tinta is not None:
				self._pasi.append(('script', tinta.sufix, 'start'))
				self._final = ('ales', tinta.sufix)
			else:
				self._final = ('niciunul', '')
			return True
		if self.cerere == 'opreste':
			if self.sufix:
				e = st.emulator(self.sufix)
				de_oprit = [e] if e is not None else []
			else:
				de_oprit = st.pornite() or ([ales] if ales is not None else [])
			if not de_oprit:
				self._termina(False, 'nimic_pornit')
				return False
			self._pasi = [('script', e.sufix, 'stop') for e in de_oprit]
			self._final = ('oprit', ', '.join(e.sufix for e in de_oprit))
			self._ramane_ales = any(e.ales for e in de_oprit)
			return True
		# reporneste
		e = st.emulator(self.sufix) if self.sufix else ales
		if e is None:
			self._termina(False, 'niciunul_ales')
			return False
		self._pasi = [('script', e.sufix, 'restart')]
		self._final = ('repornit', e.sufix)
		return True

	# ------------------------------------------------ pasii
	def _urmatorul(self):
		if self.gata:
			return
		if not self._pasi:
			self._termina(True, self._final[0], nume=self._final[1], ramane_ales=self._ramane_ales)
			return
		fel_pas, sufix, actiune = self._pasi.pop(0)
		if fel_pas == 'leaga' and sufix == SUFIX_GOL:
			self._fa_pasul(fel_pas, sufix, actiune, None)
			return
		fel = self.fel
		cuvant = 'start' if fel_pas == 'leaga' else actiune
		self._pe_fir(lambda s: argv_script(s, fel, sufix, cuvant),
			lambda argv: self._fa_pasul(fel_pas, sufix, actiune, argv), sufix)

	def _fa_pasul(self, fel_pas, sufix, actiune, argv):
		"""Pe firul enigma2: legatura sau scriptul pasului; `argv` = argv_script citit chiar inainte (None: nu e bun de pornit)."""
		if fel_pas == 'leaga':
			if sufix != SUFIX_GOL and argv is None:
				# scriptul nou a disparut intre timp: legatura nu se muta spre un script care nu mai e
				self._termina(False, 'necunoscut', nume=curata_nume(sufix))
				return
			try:
				self.sistem.pune_legatura(DOSAR_SCRIPTURI + '/' + self.fel, self.fel + '.' + sufix)
			except (OSError, ValueError) as e:
				self._termina(False, 'legatura', eroare=curata_nume(getattr(e, 'strerror', None) or str(e)))
				return
			self._urmatorul()
			return
		self._pas = (sufix, actiune)
		if argv is None:
			self._termina(False, 'necunoscut', nume=curata_nume(sufix))
			return
		if self.la_pas is not None:
			self.la_pas(actiune, sufix)
		self._cod, self._iesire = None, ''
		self._ceas = self.temporizator(self.limita, self._termen)
		pas = self._pas
		if not self.executor.porneste(argv, lambda cod, iesire: self._script_gata(pas, cod, iesire)):
			self._opreste_ceasul()
			self._termina(False, 'nu_s_a_oprit' if actiune == 'stop' else 'nu_a_pornit', nume=sufix)

	def _script_gata(self, pas, cod, iesire):
		if self.gata or pas is not self._pas:
			return   # terminat intre timp (termen): scriptul a mers mai departe singur
		self._opreste_ceasul()
		self._cod, self._iesire = cod, iesire
		self._ramase = self.verificari
		self._verifica()

	def _verifica(self):
		if self.gata:
			return
		fel = self.fel
		self._pe_fir(lambda s: citeste(s, fel), self._dupa_verificare, self._pas[0])

	def _dupa_verificare(self, st):
		sufix, actiune = self._pas
		asteptat = actiune != 'stop'
		e = st.emulator(sufix)
		if e is not None and not e.verificabil:
			# scriptul nu scrie niciun executabil: nu se poate vedea procesul, ramane codul scriptului
			ok = self._cod == 0
		else:
			ok = bool(e is not None and e.pids) == asteptat
		if ok:
			self._urmatorul()
			return
		if self._ramase > 0 and (e is None or e.verificabil):
			self._ramase -= 1
			self._ceas = self.temporizator(1.0, self._verifica)
			return
		self._termina(False, 'nu_s_a_oprit' if actiune == 'stop' else 'nu_a_pornit', nume=sufix, cod=self._cod,
			raspuns=raspuns_scurt(self._iesire))

	def _termen(self):
		if self.gata or self._pas is None:
			return
		self._ceas = None
		self._termina(False, 'termen', nume=self._pas[0], secunde=int(self.limita))

	def _opreste_ceasul(self):
		c, self._ceas = self._ceas, None
		if c is not None:
			c.opreste()

	def _termina(self, ok, motiv, **extra):
		if self.gata:
			return
		self.gata = True
		self._opreste_ceasul()
		c = self.cititor
		if c is not None and c.in_curs():
			c.opreste()      # o citire pe fir inca in curs: rezultatul ei se arunca
		self.rezultat = {'ok': ok, 'motiv': motiv, 'fel': self.fel, 'nume': '', 'cod': None, 'raspuns': '',
			'eroare': '', 'secunde': 0, 'ramane_ales': False}
		self.rezultat.update(extra)
		if _curenta[0] is self:
			_curenta[0] = None
		_generatie[0] += 1   # 0.7.7: o citire pornita inainte (ecranul, pagina web) e veche
		tine_minte_oprirea(self.rezultat, self.sistem)   # 0.7.5: Rosu pe modulul ales nu e pornit din nou dupa interfata
		f = self.la_final
		if f is not None:
			f(self.rezultat)
		_dupa_operatie(self.rezultat)

	def desprinde(self, la_final=None):
		"""ecranul se inchide: pasii merg mai departe, rezultatul merge la `la_final` (sau nicaieri)"""
		self.la_pas = None
		self.la_final = la_final


def _dupa_operatie(rezultat):
	"""0.7.4: dupa ce un modul a fost ales, pornit sau repornit (de pe televizor sau din web), paznicul porturilor
	(Components/HdsPorturi.py) se uita din nou, peste putin, daca doua servicii cer acelasi port. Nu arunca.
	0.7.4 (P4): un modul care nu a pornit fiindca programului lui ii lipseste o biblioteca pe care o are feedul extern (OpenSSL
	1.0/1.1/3, libcrypt.so.1, /lib/ld-linux.so.3) o primeste singur si porneste din nou (Components/HdsBibliotecaLipsa.py)."""
	if not rezultat.get('ok') and rezultat.get('motiv') == 'nu_a_pornit':
		try:
			from Components import HdsBibliotecaLipsa
			HdsBibliotecaLipsa.dupaCadereModul(rezultat.get('fel'), rezultat.get('nume'))
		except Exception:
			pass
		return
	if not rezultat.get('ok') or rezultat.get('motiv') not in ('ales', 'pornit', 'repornit'):
		return
	try:
		from Components import HdsPorturi
		HdsPorturi.dupa_schimbare()
	except Exception:
		pass


# ---------------------------------------------------------------- citirea pe un fir (0.7.7)
# Blocajul de 4-7 s al ecranului modulelor, masurat pe doua receptoare (0.7.6, Python 3.14): o reimprospatare a ecranului
# (la 5 s) si o cerere a paginii web /acces-conditionat (la 5 s) fac pe firul enigma2 ~1200 de apeluri de sistem (felurile,
# scripturile citite de doua ori, /proc pentru trei cautari). Singure tin 0,3-0,4 s; cat alt fir Python calculeaza (in primele
# minute dupa pornirea interfetei, importul ghidului IPTV, HdsIptvEpg, ~3 minute la ~97%), fiecare apel asteapta lacatul Python
# ~5 ms, deci 4,8-7,4 s. Acum: (1) o citire tine minte ce a citit (SistemCuMemorie), deci aceleasi legaturi, dosare si fisiere
# se cer o singura data; (2) ecranul si pagina web citesc pe un fir separat (CitirePeFir) si scriu rezultatul pe firul enigma2.
# Alegerea, pornirea si oprirea (Operatie) raman pe firul enigma2, ca pana acum.
class SistemCuMemorie(object):
	"""Un sistem (SistemAcces sau unul de proba) ale carui citiri se tin minte cat traieste obiectul (o singura citire a
	ecranului sau a paginii web). Numai citire: alegerea si scrierile nu trec pe aici."""

	def __init__(self, sistem):
		self._sistem = sistem
		self._tinute = {}
		self.radacina = getattr(sistem, 'radacina', '/')
		self.pid_propriu = sistem.pid_propriu

	def _tine(self, cheie, functie, *argumente):
		try:
			bun, valoare = self._tinute[cheie]
		except KeyError:
			try:
				bun, valoare = True, functie(*argumente)
			except (OSError, IOError, ValueError) as e:
				bun, valoare = False, e
			self._tinute[cheie] = (bun, valoare)
		if bun:
			return valoare
		raise type(valoare)(*valoare.args)

	def cale(self, p):
		return self._sistem.cale(p)

	def listeaza(self, p):
		return list(self._tine(('listeaza', p), self._sistem.listeaza, p))

	def legatura(self, p):
		return self._tine(('legatura', p), self._sistem.legatura, p)

	def citeste(self, p, *argumente):
		return self._tine(('citeste', p) + argumente, self._sistem.citeste, p, *argumente)

	def exista(self, p):
		return self._tine(('exista', p), self._sistem.exista, p)

	def executabil(self, p):
		return self._tine(('executabil', p), self._sistem.executabil, p)

	def tinta(self, p):
		return Sistem.tinta(self, p)

	def __getattr__(self, nume):
		# orice altceva (scrierile, ajutoarele sistemelor de proba) merge direct la sistemul de dedesubt
		return getattr(self._sistem, nume)


def semn_scripturi(sistem):
	"""Ce se schimba cand apare, dispare sau e inlocuit un script de modul: ora si inode-ul dosarului scripturilor si ale
	dosarului adaptorului (Components/HdsAdaptorModule.DOSAR). Doua apeluri de sistem: ecranul il intreaba la fiecare
	reimprospatare si cheama pregateste_scripturi (pe firul enigma2) numai cand s-a schimbat."""
	dosare = [DOSAR_SCRIPTURI]
	try:
		try:
			from Components import HdsAdaptorModule as A
		except ImportError:  # probe pe PC
			import HdsAdaptorModule as A
		dosare.append(A.DOSAR)
	except Exception:
		pass
	semn = []
	for d in dosare:
		try:
			st = os.stat(sistem.cale(d))
			semn.append((d, st.st_ino, st.st_mtime_ns))
		except (OSError, AttributeError):
			semn.append((d, None))
	return tuple(semn)


class ModuleCitite(object):
	"""In locul modulului HdsModuleAcces pentru Components/HdsStreamRelay.stare(H=...): starile deja citite pe fir (ecranul,
	pagina web), ca motivul releului (care modul ruleaza sau e ales) sa nu mai citeasca o data modulele pe firul enigma2.
	Pe receptorul de probe, cu ecranul deschis, numai citirea aceasta mai tinea firul principal 3-7 s la fiecare reimprospatare."""

	def __init__(self, stari):
		self.stari = stari

	def SistemAcces(self):
		return None

	def feluri_de_aratat(self, sistem=None, pregateste=True):
		return self.stari


_pregatite = {'semn': None}


def pregateste_la_schimbare(sistem):
	"""pregateste_scripturi pe firul enigma2, numai cand s-a schimbat ceva in dosarele scripturilor (semn_scripturi, doua apeluri
	de sistem): ecranul modulelor, pagina web si Informatii despre decriptare citesc apoi pe un fir, fara pregatire (o
	pregatire pe fir n-ar putea porni reinstalarea scripturilor sterse, HdsPazaScripturi). Nu arunca."""
	try:
		semn = semn_scripturi(sistem)
		if semn != _pregatite['semn']:
			_pregatite['semn'] = semn
			pregateste_scripturi(sistem)
	except Exception as e:
		_jurnal("pregatirea scripturilor: %r" % (e,))


def citire_pe_fir(sistem):
	"""True cand citirea merge pe un fir: sistemul adevarat al receptorului (radacina /). Un sistem de proba (o radacina
	intr-un dosar) se citeste pe loc, ca probele sa vada rezultatul imediat."""
	return getattr(sistem, 'radacina', '/') in ('/', '')


class CitirePeFir(object):
	"""porneste(lucru, la_sfarsit): lucru() pe un fir separat; la_sfarsit(rezultat, eroare) vine pe firul enigma2, dintr-un
	eTimer care se uita la PAS_MS. Una singura odata: cat merge, porneste() intoarce False. opreste() (ecranul se inchide):
	rezultatul care vine se arunca. `fir(functie)` si `fabrica_ceas` se dau la probe."""
	PAS_MS = 100

	def __init__(self, fir=None, fabrica_ceas=None):
		self._fir = fir
		self._fabrica_ceas = fabrica_ceas
		self._lucru = None
		self._ceas = None

	def in_curs(self):
		return self._lucru is not None

	def porneste(self, lucru, la_sfarsit):
		if self._lucru is not None:
			return False
		stare = {'la_sfarsit': la_sfarsit}

		def ruleaza():
			try:
				stare['rezultat'] = lucru()
			except Exception as e:
				stare['eroare'] = e
			stare['gata'] = True

		if self._ceas is None:
			fabrica = self._fabrica_ceas
			if fabrica is None:
				from enigma import eTimer as fabrica
			self._ceas = fabrica()
			self._ceas.callback.append(self._verifica)
		self._lucru = stare
		try:
			if self._fir is not None:
				self._fir(ruleaza)
			else:
				import threading
				t = threading.Thread(target=ruleaza, name='HdsModuleCitire')
				t.daemon = True
				t.start()
			self._ceas.start(self.PAS_MS, False)
		except Exception:
			self._lucru = None
			raise
		return True

	def _verifica(self):
		stare = self._lucru
		if stare is None or not stare.get('gata'):
			return
		self._ceas.stop()
		self._lucru = None
		stare['la_sfarsit'](stare.get('rezultat'), stare.get('eroare'))

	def opreste(self):
		self._lucru = None
		if self._ceas is not None:
			self._ceas.stop()
			del self._ceas.callback[:]
			self._ceas = None

# ---------------------------------------------------------------- paza modulelor (0.7.7)
# Doua lucruri cerute dupa ce s-au comparat managerii de module ai altora, pornite din fabrica, fara setare si fara texte noi:
#   (1) ALEGEREA SINGURA: un modul instalat din Extensii, din pagina web, cu opkg sau din alt manager devine singur cel ales si
#       pornit (aceeasi operatie ca Verde), cand felul lui nu are niciun modul ales si omul nu a ales el Niciunul (SEMN_NICIUNUL,
#       pus de tine_minte_oprirea, pastrat peste reporniri). Numai un script NOU: fata de lista celor vazute (FISIER_STIUTE; la
#       prima rulare se face lista fara sa se aleaga nimic, ca un receptor adus la zi cu Niciunul ales inainte de semn sa nu
#       porneasca singur un modul), vazut la doua verificari la rand, cu opkg liber, fara alta comanda a modulelor in curs, fara
#       semnul Rosu si fara alt modul care ruleaza. Doua noi deodata: primul dupa nume. Un script evaluat intra in lista, ales sau
#       nu, ca sa nu porneasca mult mai tarziu, pe neasteptate.
#   (2) PAZA LA CADERE: modulul ales, vazut ruland, care a disparut la doua verificari la rand fara oprirea noastra, e pornit din
#       nou (Operatie porneste), cu un rand in jurnal, cel mult INCERCARI_PE_ORA incercari in ultimele 60 de minute (tinute in
#       /tmp, peste repornirea interfetei). Deosebirea de oprirea voita: fisierul pid al modulului (din linia lui de comanda,
#       altfel un *.pid care contine pid-ul lui). Familia OSCam (si NCam) il sterge la iesirea curata (oprit din pagina lui web, cu
#       scriptul, cu SIGTERM din alt manager) si il lasa la cadere (SIGKILL de la lipsa de memorie, SIGABRT, SIGSEGV fara paznicul
#       lui intern). Fisierul pid ramas = cadere; sters = oprit voit, nu se reporneste; fara fisier pid nu se poate deosebi, deci
#       nu se reporneste. Nici cand: semnul Rosu, o comanda in curs, opkg lucreaza, acelasi program sau alt modul ruleaza pornit de
#       alt program (alt manager l-a inlocuit).
# Verificarea usoara, pe firul enigma2, la PAS_PAZA_S: doua stat-uri (semn_scripturi) si cate o legatura /proc/<pid>/exe a
# modulelor vazute ruland. Citirea intreaga (aceeasi ca a ecranului, plus fisierele pid) merge pe un fir (CitirePeFir) numai cand
# s-a schimbat ceva: un script, un proces disparut, o comanda terminata, sau o data la PAS_COMPLET_S.
SEMN_NICIUNUL = '/etc/enigma2/.hds-modul-niciunul.'      # + fel
FISIER_STIUTE = '/etc/enigma2/.hds-module-stiute.json'
FISIER_INCERCARI = '/tmp/.hds-paza-module.json'
PAS_PAZA_S = 15.0
PAS_COMPLET_S = 120.0
INCERCARI_PE_ORA = 3
DOSARE_PID = ('/var/run', '/run', '/tmp')
DOSARE_PID_MAXIM = 64
STIUTE_MAXIM = 64 * 1024


def _ceas_monoton():
	return time.monotonic()


def _scrie_json(sistem, cale, date):
	c = sistem.cale(cale)
	nou = c + '.nou'
	with open(nou, 'w') as fh:
		json.dump(date, fh, sort_keys=True)
	os.replace(nou, c)


def _citeste_json(sistem, cale):
	try:
		date = json.loads(sistem.citeste(cale, STIUTE_MAXIM))
		return date if isinstance(date, dict) else None
	except (OSError, IOError, ValueError):
		return None


def _pid_in_fisier(sistem, cale, pids):
	try:
		return int(sistem.citeste(cale, 64).split()[0]) in pids
	except (OSError, IOError, ValueError, IndexError):
		return False


def fisier_pid(sistem, pids):
	"""Fisierul pid al modulului care ruleaza cu `pids`: cel din linia de comanda (--pidfile FIS, --pidfile=FIS, -B FIS), daca
	contine unul din pid-uri; altfel un *.pid din DOSARE_PID sau din /tmp/.<x>/ care contine unul din ele. None cand nu are."""
	pids = set(pids or [])
	for pid in sorted(pids):
		try:
			argv = sistem.citeste('/proc/%d/cmdline' % pid, 4096).split('\0')
		except (OSError, IOError):
			continue
		for i, a in enumerate(argv):
			cale = None
			if a in ('--pidfile', '-B') and i + 1 < len(argv):
				cale = argv[i + 1]
			elif a.startswith('--pidfile='):
				cale = a.split('=', 1)[1]
			if cale and cale.startswith('/') and _pid_in_fisier(sistem, posixpath.normpath(cale), pids):
				return posixpath.normpath(cale)
	dosare = list(DOSARE_PID)
	try:
		dosare += ['/tmp/' + n for n in sorted(sistem.listeaza('/tmp')) if n.startswith('.') and _SUFIX_BUN.match(n[1:])]
	except OSError:
		pass
	for d in dosare[:DOSARE_PID_MAXIM]:
		try:
			nume = sorted(sistem.listeaza(d))
		except OSError:
			continue
		for n in nume[:PROGRAME_MAXIM]:
			if n.endswith('.pid') and _pid_in_fisier(sistem, d + '/' + n, pids):
				return d + '/' + n
	return None


def citeste_paza(sistem=None, fisiere_pid=None):
	"""Citirea intreaga a pazei (pe un fir): pentru fiecare fel, scripturile, cel ales, daca ruleaza (pid-uri, executabil, fisierul
	pid), daca ruleaza ceva al lui pornit de alt program; existenta fisierelor pid tinute minte (`fisiere_pid`), opkg, semnele.
	Numai citire."""
	sistem = SistemCuMemorie(sistem or SistemAcces())
	stari = feluri_de_aratat(sistem, pregateste=False)
	alte = pornite_de_alt_program(sistem, stari, descriptori=False)
	rez = {'feluri': {}, 'fisiere_pid': {}, 'opkg': False}
	for i, st in enumerate(stari):
		e = st.ales_emulator()
		f = {'scripturi': sorted(x.script for x in st.emulatoare), 'ales': e.sufix if e is not None else None,
			'legatura': st.legatura, 'pornite': sorted(x.sufix for x in st.pornite()), 'pids': [], 'exe': '', 'pid_fisier': None,
			'verificabil': bool(e is not None and e.verificabil), 'niciunul': sistem.exista(SEMN_NICIUNUL + st.fel),
			'oprit': oprit_de_om(sistem, st.fel)}
		if e is not None and e.pids:
			f['pids'] = list(e.pids)
			f['exe'] = _exe_proces(sistem, e.pids[0])
			f['pid_fisier'] = fisier_pid(sistem, e.pids)
		scripturi = scripturile(sistem, st.fel)
		f['alt_program'] = bool(alt_program_pornit(sistem, st.fel, scripturi)) or (i == 0 and bool(alte))
		rez['feluri'][st.fel] = f
	for cale in fisiere_pid or ():
		rez['fisiere_pid'][cale] = sistem.exista(cale)
	try:
		try:
			from Components import HdsPazaScripturi as P
		except ImportError:  # probe pe PC
			import HdsPazaScripturi as P
		rez['opkg'] = bool(P.opkg_lucreaza(sistem))
	except Exception:
		pass
	return rez


def _import_ocupat():
	"""True cat merge un import de setari (Components/HdsImportSurse.ocupat); False cand nu se poate afla"""
	try:
		try:
			from Components import HdsImportSurse as I
		except ImportError:  # probe pe PC
			import HdsImportSurse as I
		return bool(I.ocupat())
	except Exception:
		return False


class PazaModule(object):
	"""Paza (1) si (2) de mai sus. pas() = verificarea usoara (din ceas); acum() = citirea intreaga, de pilda la deschiderea
	ecranului modulelor. `sistem`, `operatie`, `cititor`, `ceas`, `fabrica_ceas` si `import_ocupat` se dau la probe.
	Cat merge un import de setari (Components/HdsImportSurse.ocupat: copia pusa pe receptor reinstaleaza pachetele modulelor si
	alege ea modulul din copie) si la prima citire de dupa el, paza nu face nimic si scripturile de acum intra in lista celor
	vazute: modulele puse de import nu sunt luate drept instalate de om."""

	def __init__(self, sistem=None, operatie=None, cititor=None, ceas=None, fabrica_ceas=None, import_ocupat=None):
		self.sistem = sistem or SistemAcces()
		self.import_ocupat = import_ocupat or _import_ocupat
		self.dupa_import = False
		self.Op = operatie or Operatie
		self.cititor = cititor or CitirePeFir()
		self.ceas = ceas or _ceas_monoton
		self.fabrica_ceas = fabrica_ceas
		self.ceas_pas = None
		self.vii = {}          # fel -> {'sufix', 'pids', 'exe', 'pid_fisier', 'lipsa'}: modulul ales vazut ruland
		self.vazute = {}       # fel -> scripturile noi vazute la citirea de dinainte
		self.semn = None
		self.generatie = None
		self.ultima = None
		self.in_lucru = False   # o operatie pornita de paza, pana la la_final

	# ------------------------------------------------ ceasul
	def porneste(self):
		if self.ceas_pas is not None:
			return
		fabrica = self.fabrica_ceas
		if fabrica is None:
			from enigma import eTimer as fabrica
		self.ceas_pas = fabrica()
		self.ceas_pas.callback.append(self.pas)
		self.ceas_pas.start(int(PAS_PAZA_S * 1000), False)

	def pas(self):
		"""Verificarea usoara; citirea intreaga numai cand s-a schimbat ceva. Nu arunca."""
		try:
			if self.trebuie_citit():
				self.acum()
		except Exception as e:
			_jurnal("paza: %r" % (e,))

	def trebuie_citit(self):
		if self.cititor.in_curs() or self.in_lucru:
			return False
		if self.import_ocupat() or self.dupa_import:
			return True
		if self.ultima is None or self.ceas() - self.ultima >= PAS_COMPLET_S or generatie() != self.generatie:
			return True
		if semn_scripturi(self.sistem) != self.semn or any(self.vazute.values()):
			return True
		for v in self.vii.values():
			if not any(self._viu(pid, v['exe']) for pid in v['pids']):
				return True
		return False

	def _viu(self, pid, exe):
		e = _exe_proces(self.sistem, pid)
		return bool(e) and e == exe

	def acum(self):
		"""Citirea intreaga pe un fir (pe loc pe un sistem de proba), apoi hotararea pe firul enigma2. Nu arunca."""
		if self.cititor.in_curs() or self.in_lucru:
			return
		g = generatie()
		semn = semn_scripturi(self.sistem)
		pid_uri = [v['pid_fisier'] for v in self.vii.values() if v.get('pid_fisier')]
		sistem = self.sistem

		def lucru():
			return citeste_paza(sistem, pid_uri)

		def gata(rezultat, eroare):
			if eroare is not None:
				_jurnal("paza: citirea %r" % (eroare,))
			elif rezultat is not None and g == generatie():
				self.semn, self.generatie, self.ultima = semn, g, self.ceas()
				self.hotaraste(rezultat)
		try:
			if citire_pe_fir(sistem):
				self.cititor.porneste(lucru, gata)
			else:
				gata(lucru(), None)
		except Exception as e:
			_jurnal("paza: %r" % (e,))

	# ------------------------------------------------ hotararea
	def hotaraste(self, c):
		"""Pe firul enigma2, din citirea intreaga `c` (citeste_paza): cel mult o operatie pornita. Cu o comanda a modulelor in
		curs, nimic (nici starea nu se schimba): citirea de dupa ea hotaraste."""
		if in_curs() is not None or self.in_lucru:
			return
		if self.import_ocupat() or self.dupa_import:
			self.dupa_import = self.import_ocupat()
			self.vii = {}
			self.vazute = {}
			self._scrie_stiute(dict((fel, f['scripturi']) for fel, f in c['feluri'].items()))
			return
		actiuni = []
		self._caderi(c, actiuni)
		self._alegeri(c, actiuni)
		if actiuni and in_curs() is None:
			cerere, fel, sufix = actiuni[0]
			self._operatie(cerere, fel, sufix)

	def _caderi(self, c, actiuni):
		for fel, f in sorted(c['feluri'].items()):
			v = self.vii.get(fel)
			if f['ales'] is not None and f['pids']:
				self.vii[fel] = {'sufix': f['ales'], 'pids': f['pids'], 'exe': f['exe'], 'pid_fisier': f['pid_fisier'], 'lipsa': 0}
				continue
			if v is None:
				continue
			if f['ales'] != v['sufix']:
				del self.vii[fel]          # omul (sau alt program) a ales altceva
				continue
			v['lipsa'] += 1
			if v['lipsa'] < 2:
				continue
			nume = '%s.%s' % (fel, v['sufix'])
			del self.vii[fel]
			if f['oprit']:
				continue                   # Rosu: oprit de om
			motiv = None
			if c['opkg']:
				motiv = 'opkg lucreaza'
			elif f['alt_program']:
				motiv = 'ruleaza un modul pornit de alt program'
			elif f['pornite']:
				motiv = 'ruleaza alt modul al felului'
			elif not v['pid_fisier']:
				motiv = 'fara fisier pid nu se poate deosebi caderea de oprirea voita'
			elif not c['fisiere_pid'].get(v['pid_fisier']):
				motiv = 'oprit curat (fisierul pid %s a fost sters)' % v['pid_fisier']
			if motiv:
				_jurnal("paza: %s nu mai ruleaza; nu il pornesc: %s" % (nume, motiv))
				continue
			if not self._incercare_permisa(nume):
				_jurnal("paza: %s a cazut, dar a fost pornit de %d ori in ultima ora: astept" % (nume, INCERCARI_PE_ORA))
				continue
			_jurnal("paza: %s a cazut (fisierul pid %s a ramas): il pornesc din nou" % (nume, v['pid_fisier']))
			actiuni.append(('porneste', fel, v['sufix']))

	def _alegeri(self, c, actiuni):
		stiute = _citeste_json(self.sistem, FISIER_STIUTE)
		feluri = c['feluri']
		if stiute is None or not isinstance(stiute.get('feluri'), dict):
			self._scrie_stiute(dict((fel, f['scripturi']) for fel, f in feluri.items()))
			self.vazute = {}
			return
		lista = dict((fel, set(x for x in s if isinstance(x, str))) for fel, s in stiute['feluri'].items() if isinstance(s, list))
		schimbat = False
		vazute = {}
		for fel, f in sorted(feluri.items()):
			acum = set(f['scripturi'])
			vechi = lista.get(fel, set())
			if not c['opkg'] and vechi - acum:
				lista[fel] = vechi & acum      # scripturile scoase ies din lista (o instalare noua e din nou noua)
				schimbat = True
			noi = acum - lista.get(fel, set())
			if not noi:
				continue
			gata = noi & self.vazute.get(fel, set())
			vazute[fel] = noi - gata
			if not gata:
				continue
			if c['opkg'] or in_curs() is not None or self.in_lucru or actiuni:
				vazute[fel] = noi             # trecator (sau alta operatie pornita acum): data viitoare
				continue
			lista.setdefault(fel, set()).update(gata)
			schimbat = True
			motiv = None
			if f['ales'] is not None:
				motiv = 'e ales %s.%s' % (fel, f['ales'])
			elif f['legatura'] == 'fisier':
				motiv = 'legatura alegerii e un fisier'
			elif f['niciunul']:
				motiv = 'omul a ales Niciunul'
			elif f['oprit']:
				motiv = 'oprit de om'
			elif f['pornite'] or f['alt_program']:
				motiv = 'ruleaza alt modul'
			nou = sorted(gata)[0]
			if motiv:
				_jurnal("paza: modulul nou %s nu e ales singur: %s" % (', '.join(sorted(gata)), motiv))
				continue
			_jurnal("paza: modulul nou %s, niciun modul ales: il aleg si il pornesc" % nou)
			actiuni.append(('alege', fel, nou[len(fel) + 1:]))
		self.vazute = vazute
		if schimbat:
			self._scrie_stiute(dict((fel, sorted(s)) for fel, s in lista.items()))

	def _scrie_stiute(self, feluri):
		try:
			_scrie_json(self.sistem, FISIER_STIUTE, {'feluri': feluri})
		except (OSError, IOError, ValueError) as e:
			_jurnal("paza: lista modulelor stiute: %r" % (e,))

	def _incercare_permisa(self, nume):
		"""Cel mult INCERCARI_PE_ORA incercari in ultimele 3600 s (ceas monoton al sistemului, la fel peste repornirea interfetei);
		incercarea se scrie acum in FISIER_INCERCARI."""
		acum = self.ceas()
		date = _citeste_json(self.sistem, FISIER_INCERCARI) or {}
		toate = date.get('incercari') if isinstance(date.get('incercari'), dict) else {}
		ale_lui = [t for t in toate.get(nume, []) if isinstance(t, (int, float)) and 0 <= acum - t < 3600]
		if len(ale_lui) >= INCERCARI_PE_ORA:
			return False
		toate[nume] = ale_lui + [acum]
		try:
			_scrie_json(self.sistem, FISIER_INCERCARI, {'incercari': toate})
		except (OSError, IOError, ValueError) as e:
			_jurnal("paza: incercarile: %r" % (e,))
		return True

	def _operatie(self, cerere, fel, sufix):
		self.in_lucru = True

		def gata(rezultat):
			self.in_lucru = False
			_jurnal("paza: %s %s.%s: %s" % (cerere, fel, sufix, rezultat.get('motiv')))
		try:
			if not self.Op(cerere, fel=fel, sufix=sufix, sistem=self.sistem, la_final=gata).porneste():
				self.in_lucru = False
		except Exception as e:
			self.in_lucru = False
			_jurnal("paza: %s %s.%s: %r" % (cerere, fel, sufix, e))


_paza = [None]


def paza():
	"""Paza modulelor a imaginii (una pe proces), pornita la prima chemare. Nu arunca."""
	try:
		if _paza[0] is None:
			_paza[0] = PazaModule()
		_paza[0].porneste()
	except Exception as e:
		_jurnal("paza: %r" % (e,))
	return _paza[0]


def paza_acum():
	"""Citirea intreaga a pazei chiar acum (deschiderea ecranului modulelor): un modul instalat chiar inainte e vazut indata."""
	p = paza()
	if p is not None:
		p.acum()


# ---------------------------------------------------------------- dupa repornirea interfetei (0.7.5)
# darog69, forum 789 #2047 (Vu+ Duo 4K, 12.11.2026): modulul de acces ales si pornit din ecranul modulelor se oprea la fiecare repornire a
# interfetei. Nu il oprea imaginea: un manager de module din Extensii, ramas instalat cu acelasi modul ales, face la oprirea
# interfetei „killall” pe numele modulului (deci si pe al nostru), iar la pornire nu-l mai poate porni din caile lui. La pornirea
# receptorului merge, fiindca rc porneste modulul ales inainte de interfata. Acum, la fel ca la pornirea receptorului: dupa
# fiecare pornire a interfetei, modulul ales al fiecarui fel care nu ruleaza e pornit din nou, o data, prin scriptul lui (Operatie
# „porneste”, la fel ca Verde), cu trei exceptii:
#   - omul l-a oprit el insusi (Rosu, din ecran sau din web) de la ultima pornire a receptorului: semnul MARCAJ_OPRIT + <fel>,
#     in /tmp, deci uitat la pornirea receptorului, cand rc il porneste oricum;
#   - un proces cu numele unui program al felului ruleaza din alt loc decat programele noastre (acelasi modul pornit de alt
#     manager, de pilda cu programul pe stick): nu pornim al doilea modul peste el;
#   - un script care nu scrie niciun program (nu se poate vedea daca ruleaza).
# Limita: daca omul tine doua managere pe acelasi modul, cu cai bune in amandoua, la pornirea receptorului castiga al imaginii, iar
# dupa repornirea interfetei poate castiga celalalt (el se uita la 2 s dupa incarcare, noi la INTARZIERE_INTERFATA). Merge si asa;
# raspunsul pentru om ramane „un singur manager”.
MARCAJ_OPRIT = '/tmp/.hds-modul-oprit.'   # + fel
INTARZIERE_INTERFATA = 5.0                # secunde: modulul oprit de la vechea interfata a avut timp sa iasa de tot
_SUFIX_FEL = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$')
_dupa_interfata = []                      # ceasurile in asteptare (tinute in viata)
_citiri_dupa_interfata = []               # 0.7.7: citirile pe fir in curs (tinute in viata pana la apelul inapoi)


def _jurnal(text):
	print("[HdsModuleAcces] %s" % text)


def oprit_de_om(sistem, fel):
	"""True cand omul a oprit modulul ales al felului de la ultima pornire a receptorului"""
	return bool(_SUFIX_FEL.match(fel or '')) and sistem.exista(MARCAJ_OPRIT + fel)


def tine_minte_oprirea(rezultat, sistem=None):
	"""Din Operatie._termina: Rosu pe modulul ales pune semnul; orice alegere sau pornire reusita il sterge. Nu arunca."""
	try:
		if not rezultat.get('ok'):
			return
		fel = rezultat.get('fel') or ''
		motiv = rezultat.get('motiv')
		if not _SUFIX_FEL.match(fel):
			return
		if motiv == 'oprit':
			if not rezultat.get('ramane_ales'):
				return
			oprit = True
		elif motiv in ('ales', 'niciunul', 'pornit', 'repornit', 'ruleaza_deja'):
			oprit = False
		else:
			return
		sistem = sistem or SistemAcces()
		cale = sistem.cale(MARCAJ_OPRIT + fel)
		if oprit:
			with open(cale, 'w'):
				pass
		elif os.path.lexists(cale):
			os.remove(cale)
		# 0.7.7: Niciunul ales de om (ecranul, pagina web) e tinut minte peste reporniri: paza nu alege singura un modul nou;
		# un modul ales de om sterge semnul
		niciunul = sistem.cale(SEMN_NICIUNUL + fel)
		if motiv == 'niciunul':
			with open(niciunul, 'w'):
				pass
		elif motiv == 'ales' and os.path.lexists(niciunul):
			os.remove(niciunul)
	except (OSError, IOError, AttributeError, ValueError):
		pass


def alt_program_pornit(sistem, fel, scripturi=None):
	"""[pid] ale proceselor care poarta numele unui program al felului (din dosar_programe(fel), scris sau nu intr-un script),
	dar nu ruleaza din programele noastre: acelasi modul pornit de altcineva. Numele vine din /proc/<pid>/comm (15 semne)."""
	if scripturi is None:
		scripturi = scripturile(sistem, fel)
	dosar = dosar_programe(fel)
	nume = set()
	ale_noastre = set()
	for s in scripturi:
		for scris, tinta in s.cai.items():
			if posixpath.dirname(scris) == dosar or posixpath.dirname(tinta) == dosar:
				nume.add(posixpath.basename(scris)[:15])
				nume.add(posixpath.basename(tinta)[:15])
				ale_noastre.update((scris, tinta))
	try:
		for n in sorted(sistem.listeaza(dosar))[:PROGRAME_MAXIM]:
			c = dosar + '/' + n
			if sistem.executabil(c):
				nume.add(n[:15])
				ale_noastre.update((c, sistem.tinta(c)))
	except OSError:
		pass
	nume.discard('')
	rez = []
	if not nume:
		return rez
	try:
		pids = sorted(int(x) for x in sistem.listeaza('/proc') if x.isdigit())
	except OSError:
		return rez
	for pid in pids[:PROCESE_MAXIM]:
		if pid == 1 or pid == sistem.pid_propriu:
			continue
		baza = '/proc/%d' % pid
		try:
			comm = sistem.citeste(baza + '/comm', 256).strip()
		except (OSError, IOError):
			continue
		if comm[:15] not in nume:
			continue
		try:
			exe = sistem.legatura(baza + '/exe')
		except (OSError, ValueError):
			continue   # proces care iese chiar acum sau al nucleului
		if exe.endswith(_STERS):
			exe = exe[:-len(_STERS)]
		if exe not in ale_noastre:
			rez.append(pid)
	return rez


def de_pornit_dupa_interfata(sistem=None, pregateste=True):
	"""[(fel, sufix)]: modulul ales al fiecarui fel care nu ruleaza acum si trebuie pornit din nou (vezi mai sus). `pregateste`=False:
	fara pregateste_scripturi (0.7.7: citirea de pe un fir din dupa_pornirea_interfetei; scripturile le pregateste firul enigma2)."""
	sistem = sistem or SistemAcces()
	if pregateste:
		pregateste_scripturi(sistem)
	rez = []
	for fel in feluri(sistem):
		st = citeste(sistem, fel)
		e = st.ales_emulator()
		if e is None or not e.verificabil or e.pids or oprit_de_om(sistem, fel):
			continue
		scripturi = scripturile(sistem, fel)
		altele = alt_program_pornit(sistem, fel, scripturi)
		if altele:
			_jurnal("%s.%s nu ruleaza, dar acelasi program ruleaza din alt loc (pid %s): nu pornesc al doilea"
				% (fel, e.sufix, ' '.join(str(p) for p in altele[:4])))
			continue
		rez.append((fel, e.sufix))
	return rez


def dupa_pornirea_interfetei(sistem=None, operatie=None, temporizator=None, intarziere=INTARZIERE_INTERFATA, cititor=None):
	"""Din HdsModuleLipsa.porneste (dupa crearea sesiunii, la fiecare pornire a interfetei): peste `intarziere` secunde,
	modulele alese care nu ruleaza pornesc din nou, unul dupa altul. Daca alta comanda a modulelor ruleaza chiar atunci
	(„ocupat”, de pilda biblioteca lipsa adusa din feed), inca o incercare peste 10 s. `operatie` si `temporizator` sunt
	pentru probe, ca si `cititor` (clasa CitirePeFir). Pe receptor (citire_pe_fir) starea modulelor se citeste pe un fir (0.7.7).
	Nu arunca."""
	Op = operatie or Operatie
	ceas = temporizator or Temporizator

	def pune_ceas(secunde, functie):
		loc = []

		def bate():
			if loc and loc[0] in _dupa_interfata:
				_dupa_interfata.remove(loc[0])
			functie()
		loc.append(ceas(secunde, bate))
		_dupa_interfata.append(loc[0])

	def verifica(incercari):
		try:
			s = sistem or SistemAcces()
			pe_fir = citire_pe_fir(s)
			if not pe_fir:
				ramase = de_pornit_dupa_interfata(sistem)
		except Exception as e:
			_jurnal("dupa pornirea interfetei: %r" % (e,))
			return
		if not pe_fir:
			porneste_pe_rand(ramase, incercari)
			return
		# 0.7.7: pe receptor scripturile se pregatesc pe firul enigma2 (numai cand s-a schimbat ceva), iar citirea felurilor si a lui
		# /proc (fiecare fel, plus alt_program_pornit) merge pe un fir; pornirile raman pe firul enigma2, in apelul inapoi. Pe
		# receptorul de probe citirea tinea firul enigma2 0,47 s la 5 s dupa pornirea interfetei (cat lucreaza firele pornirii, fiecare
		# apel de sistem asteapta lacatul Python). Cititorul sta in _citiri_dupa_interfata pana la apelul inapoi (ceasul lui nu are alt
		# stapan), unul nou la fiecare verificare.
		pregateste_la_schimbare(s)
		c = None
		try:
			c = (cititor or CitirePeFir)()
			_citiri_dupa_interfata.append(c)

			def gata(rezultat, eroare):
				if c in _citiri_dupa_interfata:
					_citiri_dupa_interfata.remove(c)
				if eroare is not None:
					_jurnal("dupa pornirea interfetei: %r" % (eroare,))
					return
				porneste_pe_rand(rezultat or [], incercari)
			c.porneste(lambda: de_pornit_dupa_interfata(SistemCuMemorie(s), pregateste=False), gata)
		except Exception as e:
			if c in _citiri_dupa_interfata:
				_citiri_dupa_interfata.remove(c)
			_jurnal("dupa pornirea interfetei: %r" % (e,))

	def porneste_pe_rand(ramase, incercari):
		curent = ['']

		def urmatorul(rezultat=None):
			if rezultat is not None:
				_jurnal("%s: %s" % (curent[0], rezultat.get('motiv')))
				if rezultat.get('motiv') == 'ocupat' and incercari > 1:
					pune_ceas(10.0, lambda: verifica(incercari - 1))
					return
			if not ramase:
				return
			fel, sufix = ramase.pop(0)
			curent[0] = fel + '.' + sufix
			_jurnal("%s.%s e ales, dar nu ruleaza dupa pornirea interfetei: il pornesc din nou" % (fel, sufix))
			try:
				Op('porneste', fel=fel, sufix=sufix, sistem=sistem, la_final=urmatorul).porneste()
			except Exception as e:
				_jurnal("pornirea %s.%s: %r" % (fel, sufix, e))
				urmatorul()
		urmatorul()

	try:
		pune_ceas(intarziere, lambda: verifica(2))
	except Exception as e:
		_jurnal("dupa pornirea interfetei: %r" % (e,))
	if sistem is None and operatie is None:
		paza()   # 0.7.7: paza modulelor (alegerea singura, paza la cadere), o singura data pe proces


# ---------------------------------------------------------------- ce ruleaza in afara listei (MDA, 14.11.2026)
# darog69 (forum 479 #2447, AX HD51): OSCam pornit de alt manager de module, cu programul pe stick, si un modul CI in
# slot. Lista arata numai scripturile din /etc/init.d, deci ecranul spunea "Niciunul (ales)" si "Nu este instalat niciun
# modul", desi un modul decripta. Ecranul si pagina web spun acum ce ruleaza: numele procesului (comm), executabilul si
# PID-ul, nimic altceva (nici argumentele, unde stau dosarele setarilor, nici configurarea). Semnele, ca la
# HdsInterfeteCam.cauta: numele unui modul de acces cunoscut (merge si cu modulele legate ca client la soclul enigma2, cu
# protocolul 3, care nu tin nicio cale vazuta in /proc/net/unix); altfel, numai cand nu ruleaza niciun modul din lista
# si ceva decripteaza (soclul de decriptare sau FISIER_ECM), procesul care tine soclul (S1) ori un cititor de carduri /
# un dispozitiv CA fara tuner (S2). Nimic nu se porneste, nu se opreste si nu se trimite procesului.
NUME_MODULE_CUNOSCUTE = re.compile(r'^(oscam|ncam|cccam|mgcamd|wicardd|gbox|doscam|newcs|camd3|evocamd|rqcamd|mbox|'
	r'softcam)', re.I)
ALTE_MAXIM = 4
# Citirea descriptorilor (cazul rar, fara nume cunoscut) se tine minte atat: /tmp/ecm.info ramane si dupa oprirea
# modulului, iar ecranul si pagina web intreaba din 5 in 5 secunde.
TINUT_DESCRIPTORI_S = 60.0
_descriptori = {'t': None, 'sistem': None, 'rez': {}}


def _exe_proces(sistem, pid):
	try:
		exe = sistem.legatura('/proc/%d' % pid + '/exe')
	except (OSError, ValueError):
		return ''
	return exe[:-len(_STERS)] if exe.endswith(_STERS) else exe


def _pare_modul(p, decriptare):
	"""S1 sau S2 din HdsInterfeteCam.cauta"""
	if p.socketuri & decriptare:
		return True
	return any(_CITITOR_CARD.match(d) or _CA.match(d) for d in p.dispozitive) and \
		not any(_FRONTEND.match(d) for d in p.dispozitive)


def pornite_de_alt_program(sistem=None, stari=None, descriptori=True):
	"""[{'nume', 'cale', 'pids'}]: modulele de acces care ruleaza, dar nu din scripturile din lista (pornite de alt manager
	de module sau de mana, de pilda cu programul pe stick). Procesul propriu, pid 1 si procesele scripturilor din `stari`
	nu intra; procesele cu acelasi executabil (paznicul si copilul) sunt un singur rand. Rapid: comm si exe la toate
	procesele; descriptorii se citesc numai in cazul rar de mai sus, si numai cu `descriptori` (interfete_web, cerut des
	de prima pagina web, ramane la numele cunoscute). Nu arunca."""
	try:
		sistem = sistem or SistemAcces()
		if stari is None:
			stari = feluri_de_aratat(sistem)
		ale_noastre = set()
		for st in stari:
			for e in st.emulatoare:
				ale_noastre.update(e.pids)
		pids = sorted(int(x) for x in sistem.listeaza('/proc') if x.isdigit())[:PROCESE_MAXIM]
	except Exception:
		return []
	pids = [pid for pid in pids if pid != 1 and pid != sistem.pid_propriu and pid not in ale_noastre]
	gasite = {}
	for pid in pids:
		try:
			comm = sistem.citeste('/proc/%d' % pid + '/comm', 256).strip()
		except (OSError, IOError):
			continue
		if not NUME_MODULE_CUNOSCUTE.match(comm):
			continue
		exe = _exe_proces(sistem, pid)
		if exe:
			gasite.setdefault(exe, {'nume': curata_nume(comm), 'cale': curata_nume(exe, DESCRIERE_MAXIM), 'pids': []})
			gasite[exe]['pids'].append(pid)
	if descriptori and not gasite and not ale_noastre:
		gasite = _dupa_descriptori(sistem, pids)
	return sorted(gasite.values(), key=lambda a: (a['pids'][0], a['cale']))[:ALTE_MAXIM]


def _dupa_descriptori(sistem, pids):
	"""{exe: rand} dupa semnele S1 / S2, numai cand ceva decripteaza; tinut minte TINUT_DESCRIPTORI_S pentru acelasi
	sistem (fiecare proces cu toti descriptorii lui e citirea cea mai scumpa de aici)."""
	acum = time.time()
	t = _descriptori['t']
	if _descriptori['sistem'] is sistem and t is not None and 0 <= acum - t < TINUT_DESCRIPTORI_S:
		return dict(_descriptori['rez'])
	gasite = {}
	try:
		decriptare = inode_decriptare(sistem)
		semne = bool(decriptare) or sistem.exista(FISIER_ECM)
	except Exception:
		decriptare, semne = set(), False
	for pid in pids if semne else []:
		try:
			p = citeste_proces(sistem, pid)
		except Exception:
			p = None
		if p is None or not p.exe or not _pare_modul(p, decriptare):
			continue
		gasite.setdefault(p.exe, {'nume': curata_nume(p.comm or posixpath.basename(p.exe)),
			'cale': curata_nume(p.exe, DESCRIERE_MAXIM), 'pids': []})
		gasite[p.exe]['pids'].append(pid)
	_descriptori.update(t=acum, sistem=sistem, rez=dict(gasite))
	return gasite


def sloturi_ci(ui=None, interfete=None):
	"""[(slot, stare, nume)] pentru sloturile CI cu un modul introdus: stare 1 = se porneste, 2 = gata (cu numele dat de
	modul), 3 = slot oprit din ecranul Common Interface. Sloturile goale (0) si cele care nu exista (-1) nu intra.
	`ui` = eDVBCI_UI, `interfete` = eDVBCIInterfaces (probele dau unele false). Fara enigma (PC): []. Nu arunca."""
	try:
		if ui is None or interfete is None:
			from enigma import eDVBCI_UI, eDVBCIInterfaces
			ui = ui or eDVBCI_UI.getInstance()
			interfete = interfete or eDVBCIInterfaces.getInstance()
		n = int(interfete.getNumOfSlots() or 0)
	except Exception:
		return []
	rez = []
	for slot in range(n):
		try:
			cod = int(ui.getState(slot))
			if cod in (1, 2, 3):
				rez.append((slot, cod, curata_nume(ui.getAppName(slot) or '') if cod == 2 else ''))
		except Exception:
			continue
	return rez
