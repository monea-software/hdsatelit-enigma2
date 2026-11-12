# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Paznicul porturilor: doua servicii care cer acelasi port, un port cerut pe care il tine alt program, un port cerut
pe care il foloseste receptorul. Doar in imaginea HDSatelit (din 0.7.4).

De unde a pornit: doua module de acces cu interfata web pe acelasi port; numai unul poate asculta, iar legatura
"interfata web a modulului" din panou ducea la celalalt.

Ce se citeste:
  - porturile cerute: interfetele web ale modulelor de acces (orice <nume>.conf din DOSAR_CONFIG si din subdosarele lui,
    numai httpport din [webif], "+" = HTTPS, prin HdsModuleAcces.port_web_din_randuri; nicio alta setare a modulului nu
    se citeste, nu se intoarce si nu se scrie in jurnal) si interfetele web ale extensiilor care isi tin portul in
    setarile lor de sus, config.<Extensie>.port si (cu https_enabled) config.<Extensie>.https_port, unde <Extensie> e
    numele dosarului extensiei instalate (numele vine de pe receptor, la rulare; enabled=false = oprita);
  - porturile receptorului (porturi_imagine): interfata web (80 sau portul ales, plus 8080), fluxul canalelor (8001),
    releele DVB-T2 si DAB+ din satelit (8889, 8890, 8898), FTP (21), SSH (22), Telnet (23) si portul Stream Relay
    (17999 din fabrica, setarea config.misc.acces_streamrelay_port: il asculta modulul, receptorul se leaga la el);
  - cine asculta acum: /proc/net/tcp si tcp6, starea 0A, inode -> /proc/<pid>/fd (HdsInterfeteCam).
Fisierele de configurare se leaga de module prin dosarul lor (HdsModuleAcces.dosare_configurare: din linia de comanda
a procesului sau din scriptul modulului). Cand toate modulele instalate au dosarul stiut, conteaza numai fisierele din
acele dosare (copiile vechi ramase alaturi nu sunt folosite de nimeni); cand macar unul are dosarul nestiut, conteaza
toate fisierele. Fara niciun modul instalat nu conteaza niciun fisier.

Conflictele (conflicte()), cate unul pe port, numai intre serviciile care cer portul acum: extensiile pornite si modulele
de acces care ruleaza sau sunt alese sa porneasca (modulele instalate si oprite nu fac niciun conflict):
  imagine        un serviciu cere un port al receptorului: se muta serviciul (niciodata receptorul);
  acelasi_port   doua sau mai multe servicii cer acelasi port: ramane cel care il tine acum (sau primul, cel pornit,
                 cand nu-l tine niciunul dintre ele), ceilalti se muta; cand il tine alt program, se muta toate;
  ocupat         portul cerut de un serviciu il tine acum alt program, cunoscut: se muta serviciul.
Un port pe care asculta cineva neaflat (fara proces gasit) nu se da drept "alt program".
Portul nou (port_liber): primul de dupa cel in conflict pe care nu-l cere niciun serviciu, nu asculta nimeni si nu e
al receptorului; doua servicii mutate deodata primesc porturi diferite.

Schimbarea (schimba): analiza din nou, chiar atunci, apoi numai cifrele portului din randul httpport din [webif] (cu
"+" si restul randului pastrate, restul fisierului octet cu octet, scris alaturi si pus cu os.replace); extensia prin
setarea ei (pe firul enigma2, termina_pe_principal). Modulul mutat care ruleaza se reporneste cum il reporneste
ecranul modulelor (HdsModuleAcces.Operatie "reporneste"); extensia ia portul nou dupa repornirea interfetei.

Pe televizor (porneste, dupa_schimbare): la pornirea interfetei (dupa INTARZIERE_PORNIRE_MS, cand modulul de acces a
apucat sa porneasca), dupa ce un modul a fost ales, pornit sau repornit (HdsModuleAcces) si dupa o instalare din
Extensii (HdsExtensiiLucru), o singura intrebare: ce servicii se bat pe ce port si ce se propune, cu "Schimbă portul"
(OK) si "Nu acum". Dupa "Nu acum" (sau EXIT) aceleasi conflicte nu se mai arata pana se schimba ceva (amprenta lor, in
FISIER_STARE). In interfata web: porturi_web.py (randul de avertizare din panou si aceeasi schimbare).

Fisierul nu importa enigma la incarcare: functiile de citire si de schimbare se incearca pe PC (un sistem fals)."""
import hashlib
import itertools
import json
import os
import posixpath
import re
import threading
import time

try:
	from Components.HdsInterfeteCam import Sistem, citeste_proces, citeste_procese, curata_nume, porturi_in_ascultare
	from Components import HdsModuleAcces as M
except ImportError:  # probe pe PC: modulul incarcat din dosarul Components
	from HdsInterfeteCam import Sistem, citeste_proces, citeste_procese, curata_nume, porturi_in_ascultare
	import HdsModuleAcces as M

DOSAR_CONFIG = '/etc/tuxbox/config'
FISIER_SETARI = '/etc/enigma2/settings'
FISIER_PORT_INTERFATA = '/var/run/hdswebcontrol.port'   # portul pe care asculta interfata acum (HdsWebControl)
DOSAR_EXTENSII = '/usr/lib/enigma2/python/Plugins/Extensions'
EXTENSII_MAXIM = 300
_NUME_EXTENSIE = re.compile(r'^[A-Za-z][A-Za-z0-9_]{0,63}$')
FISIER_STARE = '/etc/enigma2/hds-porturi.json'           # amprenta conflictelor amanate cu "Nu acum"

ADANCIME = 2            # subdosarele lui DOSAR_CONFIG: doua niveluri
FISIERE_MAXIM = 200
SETARI_MAXIM = 2 * 1024 * 1024
MEMORARE = 15.0         # secunde cat se foloseste o analiza fara una noua (web)

INTARZIERE_PORNIRE_MS = 60000     # dupa pornirea interfetei: modulul de acces a pornit si si-a deschis porturile
INTARZIERE_SCHIMBARE_MS = 15000   # dupa ce un modul a pornit sau s-a instalat ceva
ACELASI_DUPA_REPARARE_S = 120     # aceleasi conflicte, imediat dupa o schimbare facuta de aici: nu se intreaba iar

# setarile citite (cheia din settings, valoarea din fabrica)
SETARE_INTERFATA_ACTIVA = ('config.plugins.hdswebcontrol.activ', 'true')
SETARE_INTERFATA_PORT = ('config.plugins.hdswebcontrol.port', '80')
SETARE_RELEU_PORT = ('config.misc.acces_streamrelay_port', '17999')
# ale unei extensii (%s = dosarul ei); portul fara valoare cunoscuta (nici vie, nici in settings) nu se socoteste
SETARE_EXTENSIE_PORNITA = ('config.%s.enabled', 'true')
SETARE_EXTENSIE_PORT = ('config.%s.port', '')
SETARE_EXTENSIE_HTTPS = ('config.%s.https_enabled', 'false')
SETARE_EXTENSIE_HTTPS_PORT = ('config.%s.https_port', '')
PORT_INTERFATA_REZERVA = 8080     # adresa veche a interfetei (trimite spre 80) si locul ei cand 80 e ocupat


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_), fara efect: textul se traduce la folosire."""
	return text


def _t(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


TEXT_INTERFATA = N_("interfața web a receptorului")
TEXT_RELEU = N_("Stream Relay")
# porturile fixe ale receptorului si la ce le foloseste (cautate in imagine: vsftpd, dropbear si inetd din strat,
# Hds/DabT2/server8001.py, Hds/DabT2/profil.py)
PORTURI_FIXE = (
	(21, N_("FTP")),
	(22, N_("SSH")),
	(23, N_("Telnet")),
	(8001, N_("fluxul canalelor")),
	(8889, N_("DVB-T2 din satelit")),
	(8890, N_("DVB-T2 din satelit")),
	(8898, N_("DAB+ din satelit")),
)

TITLU = N_("Porturi în conflict")
BUTON_SCHIMBA = N_("Schimbă portul")
BUTON_NU_ACUM = N_("Nu acum")
TEXT_ACELASI = N_("Portul %(port)d e cerut de mai multe servicii: %(nume)s.")
TEXT_TINE = N_("Acum îl ține %s.")
TEXT_OCUPAT = N_("%(nume)s cere portul %(port)d, dar acum îl ține %(alt)s.")
TEXT_IMAGINE = N_("%(nume)s cere portul %(port)d, pe care receptorul îl folosește pentru %(ce)s.")
TEXT_PROPUNERE = N_("Propunere: %s.")
TEXT_MUTARE = N_("%(nume)s trece pe portul %(port)d")
TEXT_MUTAT = N_("%(nume)s e acum pe portul %(port)d.")
TEXT_REPORNESTE = N_("%s repornește acum.")
TEXT_LA_PORNIRE = N_("%s ia portul nou la următoarea pornire.")
TEXT_DUPA_INTERFATA = N_("%s ia portul nou după repornirea interfeței.")
TEXT_NU_S_A_PUTUT = N_("Portul lui %(nume)s nu s-a putut schimba: %(motiv)s.")
MOTIV_SCHIMBAT = N_("fișierul s-a schimbat între timp")
MOTIV_SCRIERE = N_("fișierul nu se poate scrie")
MOTIV_FARA_PORT = N_("nu mai e niciun port liber")
TEXT_FARA_CONFLICTE = N_("Nu mai e niciun conflict de porturi.")


def _jurnal(text):
	print("[HdsPorturi] %s" % text)


# ---------------------------------------------------------------- setarile

def citeste_setari(sistem, cale=FISIER_SETARI):
	"""{cheie: valoare} din settings (numai randurile config.x=y). Fisier lipsa -> {}."""
	try:
		text = sistem.citeste(cale, SETARI_MAXIM)
	except (OSError, IOError):
		return {}
	rez = {}
	for rand in text.splitlines():
		if rand.startswith('config.') and '=' in rand:
			cheie, valoare = rand.split('=', 1)
			rez[cheie.strip()] = valoare.strip()
	return rez


def _din_config(config_, cheie):
	"""valoarea vie din obiectul config al enigma2 (config.a.b.value), ca text; None cand setarea nu exista"""
	if config_ is None:
		return None
	o = config_
	try:
		for parte in cheie.split('.')[1:]:
			o = getattr(o, parte)
		v = o.value
	except Exception:
		return None
	if isinstance(v, bool):
		return 'true' if v else 'false'
	return str(v)


def setare(setari, setarea, config_=None):
	"""Valoarea unei setari (cheie, valoare din fabrica): cea vie din config, apoi cea din settings, apoi cea din
	fabrica (settings nu tine valorile din fabrica)."""
	cheie, implicit = setarea
	v = _din_config(config_, cheie)
	if v is None:
		v = setari.get(cheie)
	return implicit if v in (None, '') else v


def _numar(text, implicit=None):
	try:
		n = int(str(text).strip())
	except (TypeError, ValueError):
		return implicit
	return n if 0 < n < 65536 else implicit


def _da(text):
	return str(text).strip().lower() in ('true', '1', 'yes', 'da', 'on')


def port_interfata_acum(sistem):
	try:
		return _numar(sistem.citeste(FISIER_PORT_INTERFATA, 64))
	except (OSError, IOError):
		return None


def porturi_imagine(setari, interfata_acum=None, config_=None):
	"""{port: text (msgid)} porturile pe care le foloseste receptorul insusi."""
	rez = dict(PORTURI_FIXE)
	if _da(setare(setari, SETARE_INTERFATA_ACTIVA, config_)) or interfata_acum:
		web = _numar(setare(setari, SETARE_INTERFATA_PORT, config_), 80)
		rez[web] = TEXT_INTERFATA
		rez[PORT_INTERFATA_REZERVA] = TEXT_INTERFATA
		if interfata_acum:
			rez[interfata_acum] = TEXT_INTERFATA
	releu = _numar(setare(setari, SETARE_RELEU_PORT, config_), 17999)
	rez.setdefault(releu, TEXT_RELEU)
	return rez


# ---------------------------------------------------------------- serviciile si porturile cerute

def module_instalate(sistem):
	"""[{'fel', 'sufix', 'dosar' (fara / la capat, '' = nestiut), 'pids', 'ales'}] pentru fiecare modul de acces instalat;
	'ales' = cel ales sa porneasca (legatura /etc/init.d/<fel> arata spre el), chiar daca nu ruleaza acum."""
	stari = M.feluri_de_aratat(sistem)
	pids = {}
	alese = set()
	for st in stari:
		for e in st.emulatoare:
			pids[(st.fel, e.sufix)] = list(e.pids)
			if e.ales:
				alese.add((st.fel, e.sufix))
	rez = []
	for d in M.dosare_configurare(sistem, stari):
		rez.append({'fel': d['fel'], 'sufix': d['sufix'], 'dosar': (d.get('dosar') or '').rstrip('/'),
			'pids': pids.get((d['fel'], d['sufix']), []), 'ales': (d['fel'], d['sufix']) in alese})
	return rez


def fisiere_configurare(sistem, dosar=DOSAR_CONFIG, adancime=ADANCIME):
	"""Caile .conf din `dosar` si din subdosarele lui (cel mult `adancime` niveluri), sortate. Fara legaturi (nici spre
	fisiere, nici spre dosare: aceeasi configurare nu se numara de doua ori), fara dosare si fisiere ascunse (copiile
	facute la actualizarea unui modul)."""
	rez = []

	def din(d, nivel):
		try:
			nume = sorted(os.listdir(sistem.cale(d)))
		except OSError:
			return
		for n in nume:
			if len(rez) >= FISIERE_MAXIM:
				return
			if n.startswith('.'):
				continue
			c = posixpath.join(d, n)
			real = sistem.cale(c)
			if os.path.islink(real):
				continue
			if os.path.isdir(real):
				if nivel < adancime:
					din(c, nivel + 1)
			elif n.endswith('.conf') and os.path.isfile(real):
				rez.append(c)

	din(dosar.rstrip('/') or '/', 0)
	return rez


def _proces(sistem, pid):
	"""(comm, exe, dosarul de configurare din linia de comanda sau None) al unui proces; (None, None, None) daca a iesit"""
	baza = '/proc/%d' % pid
	try:
		comm = sistem.citeste(baza + '/comm', 256).strip()
		exe = sistem.legatura(baza + '/exe')
	except (OSError, IOError, ValueError):
		return None, None, None
	if exe.endswith(' (deleted)'):
		exe = exe[:-len(' (deleted)')]
	try:
		dosar = M.dosar_configurare_web(sistem.citeste(baza + '/cmdline', 8192).split('\0')[1:])
	except (OSError, IOError, ValueError):
		dosar = None
	return comm, exe, dosar


def _radacina(sufix):
	return re.split(r'[-_.]', sufix or '')[0]


def servicii_module(sistem, module, fisiere=None):
	"""Serviciile din configurarile modulelor de acces: [{'id', 'fel': 'modul', 'nume', 'port', 'protocol', 'cale',
	'dosar', 'module': [(fel, sufix)], 'pids', 'ruleaza', 'ales'}], unul pe fisier. `module` vine din module_instalate."""
	if not module:
		return []
	if fisiere is None:
		fisiere = fisiere_configurare(sistem)
	porturi = {}
	for c in fisiere:
		p = M._port_web_configurare(sistem, c)
		if p:
			porturi[c] = p
	revendicate = {}
	for m in module:
		if not m['dosar']:
			continue
		in_dosar = [c for c in sorted(porturi) if posixpath.dirname(c) == m['dosar']]
		if not in_dosar:
			continue
		cautate = []
		for pid in m['pids']:
			comm, exe, _d = _proces(sistem, pid)
			if comm is not None:
				cautate.extend(M.nume_configurari_web(comm, exe))
		cautate.extend([m['sufix'] + '.conf', _radacina(m['sufix']) + '.conf'])
		ales = None
		for n in cautate:
			for c in in_dosar:
				if posixpath.basename(c) == n:
					ales = c
					break
			if ales:
				break
		if ales is None and len(in_dosar) == 1:
			ales = in_dosar[0]
		if ales is not None:
			revendicate.setdefault(ales, []).append(m)
	if all(m['dosar'] for m in module):
		alese = sorted(revendicate)
	else:
		alese = sorted(porturi)
	# un fisier pe care nu-l revendica niciun modul poate fi al unui modul cu dosarul nestiut: conteaza (e „ales”) cat
	# timp un asemenea modul ruleaza sau e ales
	nestiut_activ = any(m.get('ales') or m['pids'] for m in module if not m['dosar'])
	rez = []
	for c in alese:
		ale = revendicate.get(c, [])
		dosar = posixpath.dirname(c)
		if ale:
			nume = ', '.join(sorted(set(m['sufix'] for m in ale)))
		elif dosar.rstrip('/') != DOSAR_CONFIG:
			nume = posixpath.basename(dosar)
		else:
			nume = posixpath.basename(c)[:-len('.conf')]
		pids = sorted(set(p for m in ale for p in m['pids']))
		rez.append({'id': 'fisier:' + c, 'fel': 'modul', 'nume': curata_nume(nume), 'port': porturi[c]['port'],
			'protocol': porturi[c]['protocol'], 'cale': c, 'dosar': dosar,
			'module': [(m['fel'], m['sufix']) for m in ale], 'pids': pids, 'ruleaza': bool(pids),
			'ales': any(m.get('ales') for m in ale) if ale else nestiut_activ})
	# doua servicii cu acelasi nume (fisiere nerevendicate cu acelasi nume): se deosebesc prin cale
	numar = {}
	for s in rez:
		numar[s['nume']] = numar.get(s['nume'], 0) + 1
	for s in rez:
		if numar[s['nume']] > 1:
			s['nume'] = curata_nume('%s (%s)' % (s['nume'], s['cale'][len(DOSAR_CONFIG) + 1:]))
	return rez


def servicii_extensii(sistem, setari, config_=None):
	"""Interfetele web ale extensiilor instalate care isi tin portul in setarile lor de sus (config.<Extensie>.port si,
	cu https_enabled, config.<Extensie>.https_port; <Extensie> = numele dosarului extensiei, de pe receptor). Ruleaza in
	procesul enigma2 (pid_propriu). Fara valoare cunoscuta a portului (nici vie, nici in settings) nu se socoteste."""
	try:
		nume = sorted(os.listdir(sistem.cale(DOSAR_EXTENSII)))[:EXTENSII_MAXIM]
	except OSError:
		return []
	rez = []
	for d in nume:
		if not _NUME_EXTENSIE.match(d) or not os.path.isdir(sistem.cale(posixpath.join(DOSAR_EXTENSII, d))):
			continue
		if not _da(setare(setari, _a(SETARE_EXTENSIE_PORNITA, d), config_)):
			continue
		felurile = [('port', 'http', d)]
		if _da(setare(setari, _a(SETARE_EXTENSIE_HTTPS, d), config_)):
			felurile.append(('https_port', 'https', '%s (HTTPS)' % d))
		for cheie, protocol, nume_aratat in felurile:
			port = _numar(setare(setari, _a(SETARE_EXTENSIE_PORT if cheie == 'port' else SETARE_EXTENSIE_HTTPS_PORT,
				d), config_))
			if port:
				rez.append({'id': 'extensie:%s:%s' % (d, cheie), 'fel': 'extensie', 'extensie': d, 'cheie': cheie,
					'nume': curata_nume(nume_aratat), 'port': port, 'protocol': protocol, 'cale': '', 'module': [],
					'pids': [sistem.pid_propriu], 'ruleaza': True})
	return rez


def _a(setarea, extensie):
	return (setarea[0] % extensie, setarea[1])

# ---------------------------------------------------------------- cine asculta

def cine_asculta(sistem, ordine=None, dorite=None, pids_intai=()):
	"""{port: [pid, ...]} pentru porturile TCP pe care asculta cineva acum ([] = nu s-a aflat procesul, sau portul nu e
	intre cele `dorite`), cu procesul propriu (enigma2) inclus: el tine interfata web, fluxul canalelor si serverele web
	ale extensiilor. Procesele `pids_intai` (enigma2 si modulele) se citesc intai; toate procesele din /proc se citesc
	numai cand un port dorit pe care asculta cineva ramane fara proces (asa, fara conflicte, se citesc cateva procese)."""
	ascultare = porturi_in_ascultare(sistem, ordine)
	rez = dict((port, set()) for (_adresa, port) in ascultare.values())
	cautate = set(rez) if dorite is None else set(rez) & set(dorite)

	def adauga(pid, p):
		for i in p.socketuri:
			if i in ascultare and ascultare[i][1] in cautate:
				rez[ascultare[i][1]].add(pid)
	if cautate:
		vazute = set()
		for pid in sorted(set(pids_intai)):
			p = citeste_proces(sistem, pid)
			if p is not None:
				adauga(pid, p)
				vazute.add(pid)
		if any(not rez[port] for port in cautate):
			for pid, p in citeste_procese(sistem).items():
				if pid not in vazute:
					adauga(pid, p)
	return dict((port, sorted(pids)) for port, pids in rez.items())

def _al_serviciului(sistem, s, pid):
	"""procesul `pid` e serviciul `s`? (un pid al modulului; altfel dosarul din linia de comanda a procesului e dosarul
	fisierului, sau procesul n-are dosar si numele lui da numele fisierului; asa se recunoaste si un modul al carui
	proces nu l-a gasit ecranul modulelor)"""
	if pid in s['pids']:
		return True
	if s['fel'] != 'modul':
		return False
	comm, exe, dosar = _proces(sistem, pid)
	if comm is None:
		return False
	if dosar is not None:
		return dosar.rstrip('/') == s['dosar']
	return posixpath.basename(s['cale']) in M.nume_configurari_web(comm, exe)


def detinator(sistem, port, pids, servicii, rezervate, interfata_acum=None):
	"""Cine tine portul: {'cheie' (stabila, pentru amprenta), 'nume' (de aratat), 'serviciu' (id sau None),
	'imagine' (msgid sau None)}; None cand nu s-a aflat niciun proces."""
	if not pids:
		return None
	propriu = sistem.pid_propriu in pids
	for s in servicii:
		if s['fel'] == 'extensie':
			continue
		if any(_al_serviciului(sistem, s, p) for p in pids if p != sistem.pid_propriu):
			return {'cheie': s['id'], 'nume': s['nume'], 'serviciu': s['id'], 'imagine': None}
	if propriu:
		# interfata noastra si extensiile au acelasi proces: portul pe care asculta interfata acum (scris de ea) e al ei
		if port == interfata_acum:
			return {'cheie': 'imagine:%d' % port, 'nume': _t(TEXT_INTERFATA), 'serviciu': None, 'imagine': TEXT_INTERFATA}
		for s in servicii:
			if s['fel'] == 'extensie' and s['port'] == port:
				return {'cheie': s['id'], 'nume': s['nume'], 'serviciu': s['id'], 'imagine': None}
		if port in rezervate:
			return {'cheie': 'imagine:%d' % port, 'nume': _t(rezervate[port]), 'serviciu': None,
				'imagine': rezervate[port]}
	pid = [p for p in pids if p != sistem.pid_propriu][:1] or [sistem.pid_propriu]
	comm, exe, _d = _proces(sistem, pid[0])
	if comm is None:
		return None
	nume = curata_nume(comm or posixpath.basename(exe or ''))
	if not nume:
		return None
	return {'cheie': 'proces:' + nume, 'nume': nume, 'serviciu': None, 'imagine': rezervate.get(port)}


def activ(s):
	"""Serviciul cere portul acum: o extensie (pornita, altfel nu e serviciu), un modul care ruleaza sau unul ales sa
	porneasca (care poate nici n-a putut porni, tocmai din cauza portului)."""
	return s['fel'] != 'modul' or bool(s.get('ruleaza')) or bool(s.get('ales'))


def conflicte(sistem, servicii, ascultare, rezervate, interfata_acum=None):
	"""[{'port', 'tip' (imagine|acelasi_port|ocupat), 'servicii': [id], 'tine': detinator sau None,
	'ce': msgid (la imagine), 'de_mutat': [id]}], dupa port. Un modul de acces conteaza numai cand ruleaza sau e ales sa
	porneasca (activ()): modulele instalate si oprite nu fac conflict (de obicei ruleaza unul singur odata, iar cele
	ramase pe portul din fabrica, 8888, nu se bat cu nimeni); cand unul e ales sau pornit, analiza se face din nou."""
	pe_port = {}
	for s in servicii:
		if activ(s):
			pe_port.setdefault(s['port'], []).append(s)
	rez = []
	for port in sorted(pe_port):
		ss = sorted(pe_port[port], key=lambda s: (not s['ruleaza'], s['fel'] != 'modul', s['nume'].lower(), s['id']))
		tine = detinator(sistem, port, ascultare.get(port, []), servicii, rezervate, interfata_acum)
		ids = [s['id'] for s in ss]
		al_cui = tine['serviciu'] if tine and tine['serviciu'] in ids else None
		if port in rezervate:
			tip, de_mutat = 'imagine', ids
		elif len(ss) > 1:
			tip = 'acelasi_port'
			if al_cui:
				de_mutat = [i for i in ids if i != al_cui]
			elif tine is not None:
				de_mutat = ids          # il tine alt program sau alt serviciu: niciunul dintre ele nu-l poate lua
			else:
				de_mutat = ids[1:]
		elif tine is not None and al_cui is None:
			tip, de_mutat = 'ocupat', ids
		else:
			continue
		rez.append({'port': port, 'tip': tip, 'servicii': ids, 'tine': tine, 'ce': rezervate.get(port),
			'de_mutat': de_mutat})
	return rez


def port_liber(de_la, folosite):
	"""primul port de dupa `de_la` care nu e in `folosite`; dupa 65535 se cauta de la 1025; None daca nu e niciunul"""
	for p in itertools.chain(range(de_la + 1, 65536), range(1025, de_la)):
		if p not in folosite:
			return p
	return None


def plan(conflicte_, servicii, ascultare, rezervate):
	"""[{'id', 'nume', 'de', 'la'}]: unde trece fiecare serviciu de mutat; porturi diferite pentru fiecare."""
	folosite = set(ascultare) | set(rezervate) | set(s['port'] for s in servicii)
	dupa_id = dict((s['id'], s) for s in servicii)
	rez = []
	for c in conflicte_:
		for i in c['de_mutat']:
			nou = port_liber(c['port'], folosite)
			if nou is None:
				continue
			folosite.add(nou)
			rez.append({'id': i, 'nume': dupa_id[i]['nume'], 'de': c['port'], 'la': nou})
	return rez


def amprenta(conflicte_):
	"""Semnul conflictelor, din campuri care nu se schimba de la o pornire la alta (fara pid-uri); '' = niciunul. Cine
	tine portul intra numai cand e din afara conflictului: intre serviciile aceluiasi conflict il tine cel pornit
	primul, iar asta nu schimba conflictul (dupa "Nu acum" nu se intreaba iar la fiecare schimbare de modul)."""
	if not conflicte_:
		return ''
	parti = []
	for c in conflicte_:
		tine = c['tine'] or {}
		din_afara = tine.get('serviciu') not in c['servicii']
		parti.append('%s|%d|%s|%s' % (c['tip'], c['port'], ','.join(sorted(c['servicii'])),
			tine.get('cheie', '') if din_afara else ''))
	return hashlib.sha1('\n'.join(sorted(parti)).encode('utf-8')).hexdigest()[:20]


# ---------------------------------------------------------------- analiza intreaga

def analiza(sistem=None, config_=None, ordine=None, module=None):
	"""Totul, citit acum (cateva fisiere mici si /proc; pe un fir separat pe receptor):
	{'servicii', 'conflicte', 'plan', 'amprenta', 'rezervate', 'ascultare'}."""
	sistem = sistem or M.SistemAcces()
	setari = citeste_setari(sistem)
	acum = port_interfata_acum(sistem)
	rezervate = porturi_imagine(setari, acum, config_)
	if module is None:
		module = module_instalate(sistem)
	servicii = servicii_module(sistem, module) + servicii_extensii(sistem, setari, config_)
	ascultare = cine_asculta(sistem, ordine, dorite=set(s['port'] for s in servicii),
		pids_intai=[sistem.pid_propriu] + [p for s in servicii for p in s['pids']])
	c = conflicte(sistem, servicii, ascultare, rezervate, acum)
	return {'servicii': servicii, 'conflicte': c, 'plan': plan(c, servicii, ascultare, rezervate),
		'amprenta': amprenta(c), 'rezervate': rezervate, 'ascultare': ascultare}


def _lista_nume(ids, dupa_id):
	return ', '.join(dupa_id[i]['nume'] for i in ids if i in dupa_id)


def texte_conflict(c, servicii):
	"""Fraza conflictului, tradusa."""
	dupa_id = dict((s['id'], s) for s in servicii)
	tine = c['tine']
	if c['tip'] == 'imagine':
		return _t(TEXT_IMAGINE) % {'nume': _lista_nume(c['servicii'], dupa_id), 'port': c['port'], 'ce': _t(c['ce'])}
	if c['tip'] == 'acelasi_port':
		text = _t(TEXT_ACELASI) % {'port': c['port'], 'nume': _lista_nume(c['servicii'], dupa_id)}
		if tine is not None:
			text += ' ' + _t(TEXT_TINE) % tine['nume']
		return text
	return _t(TEXT_OCUPAT) % {'nume': _lista_nume(c['servicii'], dupa_id), 'port': c['port'], 'alt': tine['nume']}


def text_propunere(mutari):
	if not mutari:
		return ''
	return _t(TEXT_PROPUNERE) % '; '.join(_t(TEXT_MUTARE) % {'nume': m['nume'], 'port': m['la']} for m in mutari)


def pentru_om(a):
	"""Conflictele ca text de aratat: [{'port', 'text', 'propunere'}]."""
	rez = []
	for c in a['conflicte']:
		mutari = [m for m in a['plan'] if m['de'] == c['port']]
		rez.append({'port': c['port'], 'tip': c['tip'], 'text': texte_conflict(c, a['servicii']),
			'propunere': text_propunere(mutari)})
	return rez


# ---------------------------------------------------------------- schimbarea portului

_RAND_PORT = re.compile(br'^([ \t]*httpport[ \t]*=[ \t]*\+?)([0-9]{1,5})', re.I)


def port_in_octeti(date, port_vechi, port_nou):
	"""Continutul unei configurari (octeti) cu portul din httpport din [webif] schimbat: numai cifrele, "+", spatiile,
	restul randului si restul fisierului raman octet cu octet. ValueError daca portul de acum nu e `port_vechi`, daca
	randul nu are forma simpla sau daca rezultatul nu da portul nou cu acelasi protocol."""
	vechi = M.port_web_din_randuri(date.splitlines(True))
	if not vechi or vechi['port'] != port_vechi:
		raise ValueError('schimbat')
	randuri = date.splitlines(True)
	sectiune = b''
	for i, rand in enumerate(randuri):
		r = rand.split(b'#', 1)[0].split(b';', 1)[0].strip()
		if r.startswith(b'[') and r.endswith(b']'):
			sectiune = r[1:-1].strip().lower()
		elif sectiune == b'webif' and re.match(br'^httpport\s*=', r, re.I):
			m = _RAND_PORT.match(rand)
			if not m or int(m.group(2)) != port_vechi:
				raise ValueError('forma')
			randuri[i] = rand[:m.start(2)] + str(int(port_nou)).encode('ascii') + rand[m.end(2):]
			break
	nou = b''.join(randuri)
	verificat = M.port_web_din_randuri(nou.splitlines(True))
	if not verificat or verificat['port'] != port_nou or verificat['protocol'] != vechi['protocol']:
		raise ValueError('verificare')
	return nou


def schimba_port_fisier(sistem, cale, port_vechi, port_nou):
	"""Scrie portul nou in configurarea `cale`: fisier nou alaturi (aceleasi drepturi si acelasi proprietar), golit pe
	disc, pus cu os.replace. ValueError('schimbat'|'forma'|'verificare'|'legatura'|'mare') sau OSError."""
	c = sistem.cale(cale)
	if os.path.islink(c):
		raise ValueError('legatura')
	if os.path.getsize(c) > M.CONFIG_WEB_MAXIM:
		raise ValueError('mare')
	with open(c, 'rb') as f:
		date = f.read(M.CONFIG_WEB_MAXIM + 1)
	nou = port_in_octeti(date, port_vechi, port_nou)
	st = os.stat(c)
	temporar = c + '.hds-port'
	try:
		with open(temporar, 'wb') as f:
			f.write(nou)
			f.flush()
			os.fsync(f.fileno())
		os.chmod(temporar, st.st_mode & 0o7777)
		if hasattr(os, 'chown'):
			try:
				os.chown(temporar, st.st_uid, st.st_gid)
			except OSError:
				pass
		os.replace(temporar, c)
	except Exception:
		try:
			os.remove(temporar)
		except OSError:
			pass
		raise


def seteaza_extensie(extensie, cheie, port, config_, configfile_):
	"""Pe firul enigma2: config.<extensie>.<cheie> = port, salvat. Cand extensia nu e incarcata inca (instalata acum),
	valoarea se pune intre setarile pastrate (enigma2 rescrie settings din memorie: o scriere directa s-ar pierde)."""
	if not _NUME_EXTENSIE.match(extensie or '') or cheie not in ('port', 'https_port'):
		raise ValueError(extensie)
	element = None
	try:
		element = getattr(getattr(config_, extensie), cheie)
	except Exception:
		element = None
	if element is not None:
		element.value = int(port)
		element.save()
	else:
		config_.content.stored_values.setdefault(extensie, {})[cheie] = str(int(port))
	configfile_.save()


def schimba(sistem=None, port=None, config_=None, ocupat=None, ordine=None, module=None):
	"""Pe un fir separat: analiza din nou, planul (numai conflictul de pe `port`, altfel toate) si scrierea
	configurarilor. Ce trebuie facut pe firul enigma2 (setarea unei extensii, repornirea modulelor) se intoarce in
	'extensii' si 'de_repornit' (termina_pe_principal). `ocupat()` spune daca ruleaza acum o comanda a modulelor
	(HdsModuleAcces.in_curs). -> {'ok', 'mesaj', 'mutate': [...], 'extensii': [(extensie, cheie, port)], 'de_repornit':
	[(fel, sufix)], 'amprenta'}"""
	sistem = sistem or M.SistemAcces()
	a = analiza(sistem, config_, ordine, module)
	mutari = [m for m in a['plan'] if port is None or m['de'] == port]
	dupa_id = dict((s['id'], s) for s in a['servicii'])
	rez = {'ok': True, 'mesaj': '', 'mutate': [], 'extensii': [], 'de_repornit': [], 'amprenta': a['amprenta']}
	if not mutari:
		fara_port = [i for c in a['conflicte'] if port is None or c['port'] == port for i in c['de_mutat']]
		if fara_port:
			rez['ok'] = False
			rez['mesaj'] = ' '.join(_t(TEXT_NU_S_A_PUTUT) % {'nume': dupa_id[i]['nume'], 'motiv': _t(MOTIV_FARA_PORT)}
				for i in fara_port)
		else:
			rez['mesaj'] = _t(TEXT_FARA_CONFLICTE)
		return rez
	texte = []
	ocupat_acum = bool(ocupat and ocupat())
	for m in mutari:
		s = dupa_id[m['id']]
		if s['fel'] == 'extensie':
			rez['extensii'].append((s['extensie'], s['cheie'], m['la']))
			rez['mutate'].append(m)
			texte.append(_t(TEXT_MUTAT) % {'nume': s['nume'], 'port': m['la']})
			texte.append(_t(TEXT_DUPA_INTERFATA) % s['extensie'])
			continue
		try:
			schimba_port_fisier(sistem, s['cale'], m['de'], m['la'])
		except ValueError as e:
			_jurnal('%s: portul nu s-a schimbat (%s)' % (s['cale'], e))
			rez['ok'] = False
			texte.append(_t(TEXT_NU_S_A_PUTUT) % {'nume': s['nume'], 'motiv': _t(MOTIV_SCHIMBAT)})
			continue
		except (OSError, IOError) as e:
			_jurnal('%s: portul nu s-a scris (%s)' % (s['cale'], e.__class__.__name__))
			rez['ok'] = False
			texte.append(_t(TEXT_NU_S_A_PUTUT) % {'nume': s['nume'], 'motiv': _t(MOTIV_SCRIERE)})
			continue
		_jurnal('%s: portul %d -> %d' % (s['cale'], m['de'], m['la']))
		rez['mutate'].append(m)
		texte.append(_t(TEXT_MUTAT) % {'nume': s['nume'], 'port': m['la']})
		if s['ruleaza'] and s['module'] and not ocupat_acum:
			for fel_sufix in s['module']:
				if fel_sufix not in rez['de_repornit']:
					rez['de_repornit'].append(fel_sufix)
			texte.append(_t(TEXT_REPORNESTE) % s['nume'])
		else:
			texte.append(_t(TEXT_LA_PORNIRE) % s['nume'])
	rez['mesaj'] = ' '.join(texte)
	return rez


# ---------------------------------------------------------------- amanarea ("Nu acum")

def citeste_amanat(sistem=None):
	sistem = sistem or Sistem()
	try:
		d = json.loads(sistem.citeste(FISIER_STARE, 4096))
	except (OSError, IOError, ValueError):
		return ''
	return d.get('amanat', '') if isinstance(d, dict) else ''


def scrie_amanat(sistem=None, valoare=''):
	"""Tine minte amprenta conflictelor amanate; '' sterge fisierul (nimic amanat)."""
	sistem = sistem or Sistem()
	c = sistem.cale(FISIER_STARE)
	try:
		if not valoare:
			if os.path.exists(c):
				os.remove(c)
			return True
		with open(c + '.nou', 'w') as f:
			json.dump({'amanat': valoare}, f)
		os.replace(c + '.nou', c)
		return True
	except (OSError, IOError) as e:
		_jurnal('starea: %s' % e.__class__.__name__)
		return False


def de_aratat(a, amanat):
	"""Se intreaba omul? Numai cand sunt conflicte, e ceva de propus si nu le-a amanat chiar pe acestea."""
	return bool(a['conflicte'] and a['plan'] and a['amprenta'] != amanat)


# ---------------------------------------------------------------- pe receptor: firul separat si firul enigma2

def _pe_principal(functie):
	from twisted.internet import reactor
	reactor.callFromThread(functie)


def pe_fir(lucru, la_final):
	"""lucru() pe un fir separat; la_final(rezultat) pe firul enigma2. Exceptiile raman in jurnal (rezultat None)."""
	def fir():
		try:
			r = lucru()
		except Exception as e:
			_jurnal('eroare pe fir: %s: %s' % (e.__class__.__name__, e))
			r = None
		_pe_principal(lambda: la_final(r))
	t = threading.Thread(target=fir)
	t.daemon = True
	t.start()


def _config():
	try:
		from Components.config import config, configfile
		return config, configfile
	except ImportError:
		return None, None


def termina_pe_principal(rezultat, la_final=None, operatie=None):
	"""Pe firul enigma2, dupa schimba(): setarea extensiilor mutate si repornirea modulelor mutate care ruleaza, una dupa
	alta.
	`operatie` (probele) inlocuieste HdsModuleAcces.Operatie."""
	if rezultat and rezultat.get('extensii'):
		config_, configfile_ = _config()
		for extensie, cheie, port in rezultat['extensii']:
			try:
				seteaza_extensie(extensie, cheie, port, config_, configfile_)
			except Exception as e:
				_jurnal('setarea extensiei %s: %s' % (extensie, e.__class__.__name__))
	if rezultat and rezultat.get('mutate'):
		_STARE['reparat'] = (time.time(), set(m['id'] for m in rezultat['mutate']))
	ramase = list((rezultat or {}).get('de_repornit') or [])
	Operatie = operatie or M.Operatie

	def urmatorul(*_a):
		if not ramase:
			if la_final is not None:
				la_final()
			return
		fel, sufix = ramase.pop(0)
		try:
			o = Operatie('reporneste', fel=fel, sufix=sufix, la_final=urmatorul)
			o.porneste()
		except Exception as e:
			_jurnal('repornirea %s: %s' % (sufix, e.__class__.__name__))
			urmatorul()
	urmatorul()


_STARE = {'sesiune': None, 'ceas': None, 'lucru': False, 'intrebare': None, 'reparat': None, 'web': None,
	'web_la': 0.0, 'web_lucru': False}
_lacat = threading.Lock()


def porneste(session):
	"""Din mytest.py, dupa crearea sesiunii: prima verificare dupa INTARZIERE_PORNIRE_MS."""
	_STARE['sesiune'] = session
	_programeaza(INTARZIERE_PORNIRE_MS)


def dupa_schimbare():
	"""Un modul a pornit sau s-a instalat ceva (HdsModuleAcces, HdsExtensiiLucru): o verificare peste putin. Fara
	sesiune (probele, alta imagine) nu face nimic."""
	if _STARE['sesiune'] is not None:
		_programeaza(INTARZIERE_SCHIMBARE_MS)


def _programeaza(ms):
	try:
		from enigma import eTimer
	except ImportError:
		return
	if _STARE['ceas'] is None:
		_STARE['ceas'] = eTimer()
		_STARE['ceas'].callback.append(_verifica)
	_STARE['ceas'].start(ms, True)


_SISTEM = [None]   # probele pun aici un sistem fals; pe receptor, HdsModuleAcces.SistemAcces()


def _sistem():
	return _SISTEM[0] or M.SistemAcces()


def _analiza_vie():
	config_, _cf = _config()
	return analiza(sistem=_sistem(), config_=config_)


def _verifica():
	if _STARE['lucru']:
		_programeaza(INTARZIERE_SCHIMBARE_MS)
		return
	_STARE['lucru'] = True

	def gata(a):
		_STARE['lucru'] = False
		if a is not None:
			_tine_minte_web(a)
			_arata(a)
	pe_fir(_analiza_vie, gata)


def _arata(a):
	sistem = _sistem()
	if not a['conflicte']:
		if citeste_amanat(sistem):
			scrie_amanat(sistem, '')
		return
	amanat = citeste_amanat(sistem)
	if not de_aratat(a, amanat):
		return
	reparat = _STARE['reparat']
	if reparat and time.time() - reparat[0] < ACELASI_DUPA_REPARARE_S and \
			set(i for c in a['conflicte'] for i in c['de_mutat']) & reparat[1]:
		# chiar acum am mutat aceste servicii si conflictul a ramas: nu intrebam in bucla
		_jurnal('conflictul ramane dupa schimbare: nu intreb din nou acum')
		return
	try:
		from Tools import Notifications
		from Screens.MessageBox import MessageBox
	except ImportError:
		return
	# o intrebare deja in coada (neaparuta) se inlocuieste; una deschisa pe ecran ramane
	in_coada = [n for n in Notifications.notifications if n[0] is _raspuns]
	if _STARE['intrebare'] is not None and not in_coada:
		return
	for n in in_coada:
		try:
			Notifications.notifications.remove(n)
		except ValueError:
			pass
	texte = pentru_om(a)
	text = '\n'.join(t['text'] for t in texte) + '\n' + text_propunere(a['plan'])
	_STARE['intrebare'] = a['amprenta']
	Notifications.AddNotificationWithCallback(_raspuns, MessageBox, text, type=MessageBox.TYPE_YESNO,
		list=[(_t(BUTON_SCHIMBA), True), (_t(BUTON_NU_ACUM), False)], titlu=_t(TITLU))
	_jurnal('conflicte de porturi: %s' % ', '.join('%s %d' % (c['tip'], c['port']) for c in a['conflicte']))


def _raspuns(da=None):
	amprenta_ = _STARE['intrebare']
	_STARE['intrebare'] = None
	if not da:
		# "Nu acum" sau EXIT: aceleasi conflicte nu se mai arata pana se schimba ceva
		if amprenta_:
			scrie_amanat(_sistem(), amprenta_)
		return
	scrie_amanat(_sistem(), '')

	def gata(r):
		if r is None:
			return
		uita_analiza_web()    # analiza tinuta pentru web nu mai e adevarata
		termina_pe_principal(r)
		try:
			from Tools import Notifications
			from Screens.MessageBox import MessageBox
			Notifications.AddPopup(r['mesaj'], MessageBox.TYPE_INFO if r['ok'] else MessageBox.TYPE_WARNING, 15,
				'HdsPorturi', titlu=_t(TITLU))
		except Exception as e:
			_jurnal('mesajul: %s' % e.__class__.__name__)
	pe_fir(schimba_viu, gata)


def schimba_viu(port=None):
	"""schimba() pe receptor, cu setarile vii (pe un fir separat; televizorul si web-ul)."""
	config_, _cf = _config()
	return schimba(sistem=_sistem(), port=port, config_=config_, ocupat=M.in_curs)


# ---------------------------------------------------------------- pentru interfata web (porturi_web.py)

def _tine_minte_web(a):
	with _lacat:
		_STARE['web'] = a
		_STARE['web_la'] = time.time()


def analiza_web(reincarca=False):
	"""Pe firul cererii web (nu pe firul enigma2): analiza tinuta cel mult MEMORARE secunde, altfel una noua."""
	with _lacat:
		a = _STARE['web']
		if a is not None and not reincarca and time.time() - _STARE['web_la'] < MEMORARE:
			return a
	a = _analiza_vie()
	_tine_minte_web(a)
	return a


def uita_analiza_web():
	with _lacat:
		_STARE['web'] = None
