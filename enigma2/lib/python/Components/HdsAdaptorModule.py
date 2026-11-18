# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Modulele de acces puse ca scripturi in /usr/camscript apar in Acces conditionat ca orice modul (0.7.7). Doar in imaginea
HDSatelit.

Conventia aceea o folosesc managerele de module din Extensii si pachetele de module facute pentru ele: un script
/usr/camscript/<id>.sh care stie cuvintele cam_up (pornire), cam_down (oprire) si cam_res (repornire), iar programul modulului
sta in alt loc (de obicei /usr/bin). Lista din Acces conditionat (Components/HdsModuleAcces.py) citeste numai conventia OE-A,
/etc/init.d/<fel>.<x> cu start, stop si restart, deci un astfel de modul nu aparea deloc, desi era instalat.

Aici imaginea scrie, pentru fiecare /usr/camscript/<id>.sh fara pereche, un script al ei, /etc/init.d/<fel>.<id> (fel = felul
modulelor obisnuite, primul din HdsInterfeteCam.feluri), care trece start, stop si restart in cam_up, cam_down si cam_res. Restul
merge ca la orice modul, fara nimic nou: lista si alegerea (legatura <fel>), pornirea la pornirea receptorului (rc), pagina web,
diagnosticul modulului care nu porneste (Components/HdsModulNepornit.py).

Reguli:
  - se citesc numai fisierele obisnuite (nu legaturi) aflate chiar in DOSAR, cu numele <id>.sh, id de forma buna si cuvintele
    pornirii si opririi in ele (CERUTE); un fisier mai mare decat SCRIPT_MAXIM nu intra;
  - scriptul nostru are SEMN pe al doilea rand; numai scripturile cu SEMN se scriu din nou sau se sterg. Un <fel>.<id> pus de
    altcineva (de pilda chiar pachetul modulului, cu scriptul lui OE-A) nu se atinge niciodata;
  - programele scrise in scriptul din DOSAR (caile absolute catre fisiere executabile, fara interpretorul lui si fara uneltele
    sistemului) trec in scriptul nostru ca PROGRAM= (apoi P2_PROGRAM=...), ca lista sa vada procesul pornit
    (HdsInterfeteCam._scriptul_porneste) si ca diagnosticul modulului care nu porneste sa gaseasca programul
    (HdsModulNepornit.programe: variabilele ...PROGRAM);
  - iesirea scriptului din DOSAR (si a programului pe care il lasa in fundal cu &) merge in /dev/null, nu in teava ecranului:
    altfel teava ar ramane deschisa cat ruleaza modulul, iar ecranul ar astepta pana la termen; in JURNAL scriem numai un rand
    pe comanda (ora, cuvantul, scriptul), ca jurnalul sa nu creasca cu iesirea modulului;
  - cand scriptul din DOSAR dispare (pachetul lui scos), scriptul nostru se sterge; daca legatura felului arata spre el, trece pe
    <fel>.None, ca la alegerea Niciunul;
  - nimic nu se porneste si nu se opreste aici; configurarea modulului nu se citeste.
Se cheama din HdsModuleAcces (inainte de lista aratata si dupa pornirea interfetei). Merge si pe PC (probele: `sistem` cu o
radacina de proba). Nu arunca."""
import os
import posixpath
import re
import threading

try:
	from Components.HdsInterfeteCam import DOSAR_SCRIPTURI, SCRIPT_MAXIM, SUFIX_GOL, TIPAR_FEL_PRINCIPAL, Sistem, \
		_CALE_ABSOLUTA, _desface, curata_nume, feluri, variabile_script
except ImportError:  # probe pe PC: modulul incarcat din dosarul Components
	from HdsInterfeteCam import DOSAR_SCRIPTURI, SCRIPT_MAXIM, SUFIX_GOL, TIPAR_FEL_PRINCIPAL, Sistem, \
		_CALE_ABSOLUTA, _desface, curata_nume, feluri, variabile_script

DOSAR = '/usr/camscript'
EXTENSIE = '.sh'
SEMN = '# hdsatelit-adaptor: '
JURNAL = '/tmp/hds-module-adaptor.log'
INTERPRETOR_IMPLICIT = '/bin/sh'
# cuvintele conventiei: start, stop, restart (OE-A) -> cuvantul scriptului din DOSAR
CUVINTE = (('start', 'cam_up'), ('stop', 'cam_down'), ('restart|reload|force-reload', 'cam_res'))
CERUTE = ('cam_up', 'cam_down')
SCRIPTURI_MAXIM = 32
PROGRAME_MAXIM = 4
DESCRIERE_MAXIM = 60
CAP_MAXIM = 256              # cat se citeste din scripturile felului ca sa se vada SEMN-ul
_ID_BUN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$')        # acelasi tipar ca sufixul din HdsModuleAcces
_CALE_BUNA = re.compile(r'^/[A-Za-z0-9_.+/-]{1,200}$')              # fara spatii, $, ghilimele: se scrie in script asa cum e
_DESCRIERE = re.compile(r'''^[ \t]*OSD[ \t]*=[ \t]*["']?([^"'\n]*)''', re.M)
_SEMNE_DESCRIERE = re.compile(r'[^A-Za-z0-9 ._+()-]')
_lacat = threading.Lock()


def _jurnal(text):
	print("[HdsAdaptorModule] %s" % text)


def _fel_principal(sistem):
	lista = feluri(sistem)
	if lista and TIPAR_FEL_PRINCIPAL.search(lista[0]):
		return lista[0]
	return ''


def _interpretor(sistem, text):
	"""calea din #! a scriptului, daca e un program de pe receptor cu forma buna; altfel INTERPRETOR_IMPLICIT"""
	if text.startswith('#!'):
		prima = text[2:].split('\n', 1)[0].split()
		if prima and _CALE_BUNA.match(prima[0]) and sistem.executabil(prima[0]):
			return prima[0]
	return INTERPRETOR_IMPLICIT


def programe(sistem, text):
	"""Caile absolute din script (cu variabilele simple desfacute) care sunt fisiere executabile pe receptor, fara
	interpretorul scriptului, fara uneltele sistemului (aceeasi tinta ca interpretorul, adica busybox) si fara scripturi."""
	interpretor = sistem.tinta(_interpretor(sistem, text))
	rez = []
	for m in _CALE_ABSOLUTA.finditer(_desface(text, variabile_script(text))):
		c = m.group(1).rstrip('/')
		if not c or c in rez or not _CALE_BUNA.match(c):
			continue
		if posixpath.dirname(c) in (DOSAR, DOSAR_SCRIPTURI) or c.endswith(EXTENSIE):
			continue
		if not sistem.executabil(c):
			continue
		t = sistem.tinta(c)
		if t == interpretor or posixpath.basename(t).startswith('busybox'):
			continue
		rez.append(c)
		if len(rez) >= PROGRAME_MAXIM:
			break
	return rez


def descriere(text, ident):
	"""numele aratat: OSD="..." din script (conventia managerelor), curatat; altfel id-ul"""
	m = _DESCRIERE.search(text)
	d = _SEMNE_DESCRIERE.sub('', curata_nume(m.group(1), DESCRIERE_MAXIM)).strip() if m else ''
	return d or ident


def text_adaptor(cale, descriere_, programe_, interpretor=INTERPRETOR_IMPLICIT):
	"""Scriptul nostru /etc/init.d/<fel>.<id> pentru scriptul `cale` din DOSAR. Toate valorile scrise au forma verificata
	(_CALE_BUNA, _SEMNE_DESCRIERE), deci nu pot schimba sensul scriptului."""
	r = ['#!/bin/sh',
		SEMN + cale,
		'# Short-Description: ' + descriere_,
		'# Scris de imagine pentru modulul de mai sus: start, stop si restart trec in cam_up, cam_down si cam_res.',
		'# Se sterge singur cand scriptul acela dispare.',
		'SCRIPT=' + cale]
	for i, p in enumerate(programe_):
		r.append('%sPROGRAM=%s' % ('P%d_' % (i + 1) if i else '', p))
	r.append('case "$1" in')
	for oe, cuvant in CUVINTE:
		r.append('\t%s) CUVANT=%s ;;' % (oe, cuvant))
	r += ['\t*) echo "Usage: $0 {start|stop|restart}"; exit 1 ;;',
		'esac',
		'[ -f "$SCRIPT" ] || { echo "$SCRIPT: not found"; exit 1; }',
		'echo "$(date \'+%Y-%m-%d %H:%M:%S\') $1: $SCRIPT $CUVANT" >> ' + JURNAL,
		'exec %s "$SCRIPT" "$CUVANT" < /dev/null > /dev/null 2>&1' % interpretor,
		'']
	return '\n'.join(r)


def scripturi_dosar(sistem):
	"""{id: (cale, text)} pentru scripturile bune din DOSAR (vezi Regulile)"""
	try:
		nume = sorted(sistem.listeaza(DOSAR))
	except (OSError, IOError):
		return {}
	rez = {}
	for n in nume:
		if len(rez) >= SCRIPTURI_MAXIM:
			break
		if not n.endswith(EXTENSIE):
			continue
		ident = n[:-len(EXTENSIE)]
		if not _ID_BUN.match(ident) or ident == SUFIX_GOL:
			continue
		c = DOSAR + '/' + n
		real = sistem.cale(c)
		try:
			if os.path.islink(real) or not os.path.isfile(real) or os.path.getsize(real) > SCRIPT_MAXIM:
				continue
			text = sistem.citeste(c, SCRIPT_MAXIM)
		except (OSError, IOError):
			continue
		if all(cuvant in text for cuvant in CERUTE):
			rez[ident] = (c, text)
	return rez


def ale_noastre(sistem, fel):
	"""{id: text} pentru scripturile noastre <fel>.<id> din DOSAR_SCRIPTURI (cele cu SEMN pe al doilea rand)"""
	try:
		nume = sorted(sistem.listeaza(DOSAR_SCRIPTURI))
	except (OSError, IOError):
		return {}
	rez = {}
	for n in nume:
		if not n.startswith(fel + '.') or n == fel + '.' + SUFIX_GOL:
			continue
		c = DOSAR_SCRIPTURI + '/' + n
		real = sistem.cale(c)
		try:
			if os.path.islink(real) or not os.path.isfile(real):
				continue
			randuri = sistem.citeste(c, CAP_MAXIM).split('\n', 2)
			if len(randuri) > 1 and randuri[1].startswith(SEMN):
				rez[n[len(fel) + 1:]] = sistem.citeste(c, SCRIPT_MAXIM)
		except (OSError, IOError):
			continue
	return rez


def _scrie(sistem, p, text):
	"""fisierul `p` (executabil) dintr-o bucata: fisier nou langa el, apoi os.replace"""
	c = sistem.cale(p)
	dosar, nume = os.path.split(c)
	nou = os.path.join(dosar, '.%s.hds-%d' % (nume, os.getpid()))
	try:
		with open(nou, 'w', encoding='utf-8', newline='\n') as fh:
			fh.write(text)
		os.chmod(nou, 0o755)
		os.replace(nou, c)
	except (OSError, IOError):
		try:
			os.remove(nou)
		except OSError:
			pass
		raise


def _leaga(sistem, p, tinta):
	"""legatura `p` spre `tinta` dintr-o bucata (ca SistemAcces.pune_legatura)"""
	pune = getattr(sistem, 'pune_legatura', None)
	if pune is not None:
		pune(p, tinta)
		return
	c = sistem.cale(p)
	dosar, nume = os.path.split(c)
	nou = os.path.join(dosar, '.' + nume + '.nou')
	if os.path.lexists(nou):
		os.remove(nou)
	os.symlink(tinta, nou)
	os.replace(nou, c)


def _sincronizeaza(sistem):
	fel = _fel_principal(sistem)
	if not fel:
		return []
	dorite = scripturi_dosar(sistem)
	noastre = ale_noastre(sistem, fel)
	facute = []
	for ident in sorted(dorite):
		cale, text = dorite[ident]
		dorit = text_adaptor(cale, descriere(text, ident), programe(sistem, text), _interpretor(sistem, text))
		p = DOSAR_SCRIPTURI + '/' + fel + '.' + ident
		if ident in noastre:
			if noastre[ident] == dorit:
				continue
		elif sistem.exista(p):
			continue   # al altcuiva (de pilda scriptul OE-A al aceluiasi pachet): nu se atinge
		_scrie(sistem, p, dorit)
		facute.append(('scris', fel + '.' + ident))
	for ident in sorted(noastre):
		if ident in dorite:
			continue
		nume = fel + '.' + ident
		try:
			ales = posixpath.basename(sistem.legatura(DOSAR_SCRIPTURI + '/' + fel)) == nume
		except (OSError, ValueError):
			ales = False
		if ales and sistem.exista(DOSAR_SCRIPTURI + '/' + fel + '.' + SUFIX_GOL):
			_leaga(sistem, DOSAR_SCRIPTURI + '/' + fel, fel + '.' + SUFIX_GOL)
			facute.append(('legatura', fel + '.' + SUFIX_GOL))
		os.remove(sistem.cale(DOSAR_SCRIPTURI + '/' + nume))
		facute.append(('sters', nume))
	return facute


def sincronizeaza(sistem=None):
	"""Scrie, rescrie sau sterge scripturile noastre dupa ce e in DOSAR. Intoarce [(fapta, nume)]: ('scris', <fel>.<id>),
	('sters', <fel>.<id>), ('legatura', <fel>.None). Cand DOSAR lipseste (cazul obisnuit) citeste numai capetele scripturilor
	felului (CAP_MAXIM), ca sa stearga scripturile noastre ramase. Nu arunca."""
	try:
		with _lacat:
			facute = _sincronizeaza(sistem or Sistem())
	except Exception as e:
		_jurnal("sincronizarea: %r" % (e,))
		return []
	for fapta, nume in facute:
		_jurnal("%s %s" % (fapta, nume))
	return facute
