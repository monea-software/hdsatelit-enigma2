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
niciun port al vreunuia.

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
import os
import posixpath
import re

try:
	from Components.HdsInterfeteCam import DOSAR_SCRIPTURI, FISIER_ECM, PROCESE_MAXIM, SUFIX_GOL, \
		Proces, Sistem, _scriptul_porneste, citeste_scripturi, curata_nume, e_script_modul, feluri as _feluri
except ImportError:  # probe pe PC: modulul incarcat din dosarul Components
	from HdsInterfeteCam import DOSAR_SCRIPTURI, FISIER_ECM, PROCESE_MAXIM, SUFIX_GOL, \
		Proces, Sistem, _scriptul_porneste, citeste_scripturi, curata_nume, e_script_modul, feluri as _feluri

ACTIUNI = ('start', 'stop', 'restart')
CERERI = ('alege', 'porneste', 'opreste', 'reporneste')

LIMITA_SCRIPT = 60.0     # secunde; dupa atat se spune ca scriptul nu a terminat (scriptul nu se opreste)
VERIFICARI = 6           # dupa script: de cate ori se mai cauta procesul, la o secunda
IESIRE_MAXIM = 8192      # cat se tine din ce scrie scriptul
IESIRE_RANDURI = 3       # cate randuri din raspunsul scriptului se arata
PROGRAME_MAXIM = 64
ECM_MAXIM = 4096
DESCRIERE_MAXIM = 120

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
	__slots__ = ('fel', 'sufix', 'script', 'cale', 'descriere', 'ales', 'pids', 'verificabil')

	def __init__(self, fel, script):
		self.fel = fel
		self.sufix = script.sufix
		self.script = script.nume        # <fel>.<x>
		self.cale = script.cale          # /etc/init.d/<fel>.<x>
		self.descriere = curata_nume(script.descriere, DESCRIERE_MAXIM)
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
		st.emulatoare.append(e)
	st.emulatoare.sort(key=lambda e: (e.sufix.lower(), e.sufix))
	st.fara_script = programe_fara_script(sistem, citeste_scripturi(sistem).values(), fel) if fel else []
	st.ecm = randuri_ecm(sistem)
	return st


def feluri_de_aratat(sistem=None):
	"""[Stare]: primul fel (al modulelor obisnuite) mereu, celelalte (serverele de carduri) numai cand au macar un
	script"""
	sistem = sistem or SistemAcces()
	rez = []
	for i, fel in enumerate(feluri(sistem)):
		st = citeste(sistem, fel)
		if i == 0 or st.emulatoare:
			rez.append(st)
	return rez


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


def in_curs():
	o = _curenta[0]
	return o if o is not None and not o.gata else None


class Executor(object):
	"""porneste(argv, la_final) -> True daca scriptul a pornit; la_final(cod, iesire) vine pe firul enigma2 cand
	scriptul termina. argv = (cale, cale, actiune): program, argv0, argument, fara interpretor de comenzi."""

	def porneste(self, argv, la_final):
		from enigma import eConsoleAppContainer
		c = eConsoleAppContainer()
		lucru = {'container': c, 'iesire': [], 'marime': 0}

		def date(text):
			if isinstance(text, bytes):
				text = text.decode('utf-8', 'replace')
			if lucru['marime'] < IESIRE_MAXIM:
				lucru['iesire'].append(text[:IESIRE_MAXIM - lucru['marime']])
				lucru['marime'] += len(text)

		def inchis(cod):
			del c.appClosed[:]
			del c.dataAvail[:]
			if lucru in _in_lucru:
				_in_lucru.remove(lucru)
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
	nimic_pornit, niciunul_ales, ocupat, necunoscut, nu_e_legatura, legatura, nu_a_pornit, nu_s_a_oprit, termen."""

	def __init__(self, cerere, fel=None, sufix=None, sistem=None, executor=None, temporizator=None,
			la_pas=None, la_final=None, limita=LIMITA_SCRIPT, verificari=VERIFICARI):
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

	# ------------------------------------------------ planul
	def porneste(self):
		"""True daca a inceput; altfel rezultatul e deja dat prin la_final"""
		if in_curs() is not None:
			self._termina(False, 'ocupat')
			return False
		st = citeste(self.sistem, self.fel)
		if not self._planifica(st):
			return False
		_curenta[0] = self
		self._urmatorul()
		return True

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
		if fel_pas == 'leaga':
			if sufix != SUFIX_GOL and argv_script(self.sistem, self.fel, sufix, 'start') is None:
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
		argv = argv_script(self.sistem, self.fel, sufix, actiune)
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
		sufix, actiune = self._pas
		asteptat = actiune != 'stop'
		e = citeste(self.sistem, self.fel).emulator(sufix)
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
		self.rezultat = {'ok': ok, 'motiv': motiv, 'fel': self.fel, 'nume': '', 'cod': None, 'raspuns': '',
			'eroare': '', 'secunde': 0, 'ramane_ales': False}
		self.rezultat.update(extra)
		if _curenta[0] is self:
			_curenta[0] = None
		f = self.la_final
		if f is not None:
			f(self.rezultat)

	def desprinde(self, la_final=None):
		"""ecranul se inchide: pasii merg mai departe, rezultatul merge la `la_final` (sau nicaieri)"""
		self.la_pas = None
		self.la_final = la_final
