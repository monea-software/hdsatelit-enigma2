#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# hds-actualizare-intrerupta.py: termina la pornire o actualizare prin pachete oprita la jumatate (0.7.4).
#
# De ce (LinuxSat 164125 #969426, SF8008 cu radacina pe stick, 10.11.2026): opkg ruleaza ca proces copil al enigma2
# (Components/Ipkg.py, eConsoleAppContainer), iar la orice iesire a enigma2 (repornirea interfetei, o cadere) destructorul
# lui trimite SIGKILL grupului copilului (lib/base/console.cpp). opkg a murit la jumatatea dezarhivarii pachetului
# enigma2-hdsatelit: status-ul opkg (scris de opkg numai la iesire) a ramas pe versiunea veche, /etc/image-version si
# Components/* erau noi, Screens/* vechi, deci enigma2 cadea la fiecare pornire, si in modul sigur.
#
# Cine il porneste: tools/enigma2.sh, inainte de enigma2, numai cand vede un semn (scriptul si acest program sunt printre
# primele fisiere din arhiva pachetului, ./usr/bin, deci sunt cei noi si dupa o dezarhivare oprita devreme):
#   - semnul SEMN, scris de Components/HdsActualizari.py inainte de opkg si scos cand opkg iese singur;
#   - pachete .ipk ramase in DOSAR_PACHETE (/tmp, deci numai fara repornirea receptorului; acolo raman numai fisierele
#     deja verificate, cele neterminate sunt .partial);
#   - versiunea din /etc/image-version (fisierul pachetului principal, primul din arhiva) alta decat versiunea pachetului
#     principal din status-ul opkg, sau pachetul principal nu e "installed".
#
# Ce face (o singura data pe pornirea receptorului, semnul PE_PORNIRE din /tmp; iese mereu cu 0, pornirea nu depinde de el;
# dupa o descarcare cazuta, de obicei reteaua inca nepornita, se reia la urmatoarea rulare a lui enigma2.sh, cel mult
# MAX_DESCARCARI_PE_PORNIRE incercari pe pornire, ca omul sa nu trebuiasca sa reporneasca receptorul):
#   1. asteapta un opkg pornit din alta parte (lacatul lui), cel mult ASTEPTARE_LACAT_S;
#   2. `opkg configure` (un pachet dezarhivat, dar neconfigurat); daca acum totul e la zi, gata;
#   3. altfel pachetele tinta se instaleaza din nou, numai din ce e semnat de HD Satelit, printr-un singur lant: listele
#      feedului din /var/lib/opkg/lists trebuie sa aiba chiar sha256 si marimea tinute minte din stare.json semnat la
#      ultima cautare (/etc/enigma2/hds-indexuri-semnate.json, Components/HdsActualizari.tine_minte_indexurile); un .ipk
#      ramas in /tmp se foloseste numai daca suma lui e SHA256sum din aceste liste; altfel opkg il descarca dupa nume,
#      cu o configurare proprie care are numai sursele verificate (opkg verifica SHA256sum la descarcare); inainte de o
#      descarcare se asteapta o ruta implicita (IPv4 sau IPv6), cel mult RETEA_ASTEPTARE_S;
#   4. fiecare pachet tinta se verifica apoi in status: versiunea ceruta si "installed". Un pachet ramas pe versiunea veche
#      cu cod 0 (opkg cu libsolv il poate tine pe loc fara eroare) e tot esec;
#   5. rezultatul (REZULTAT, in /tmp) il arata enigma2 pe televizor si in pagina web (HdsActualizari.porneste); randurile
#      lui opkg merg in jurnalul actualizarilor (acelasi cu cel din meniu).
# opkg nu se opreste niciodata la un termen (asta a facut defectul). Incercarile cu opkg ajuns la pachete (sau iesit cu 0
# fara sa le schimbe) se numara in SEMN; dupa MAX_INCERCARI semnul ramane cu renuntat=1 (nu se mai incearca, nu se mai
# arata nimic) pana la o actualizare reusita din meniu. O descarcare cazuta (fara retea, ceasul in urma dupa o repornire
# dura) nu se numara.
#
# Numai biblioteca standard Python (fara module enigma2 si fara alte module HD Satelit: acelea pot fi chiar fisierele
# amestecate). Variabilele HDS_AI_* sunt numai pentru probele de pe PC (teste/test_actualizare_intrerupta_074.py).

import gzip
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import time

RADACINA = os.environ.get('HDS_AI_RADACINA', '')
# probele dau aici programul lor, cu argumentele despartite prin |
OPKG = [x for x in os.environ.get('HDS_AI_OPKG', 'opkg').split('|') if x]
AFISAJ = os.environ.get('HDS_AI_AFISAJ', '/dev/dbox/oled0')

SEMN = '/etc/enigma2/hds-actualizare.in-curs'
DOSAR_PACHETE = '/tmp/hds-actualizare'
IMAGE_VERSION = '/etc/image-version'
OPKG_CONF = '/etc/opkg/opkg.conf'
ARCH_CONF = '/etc/opkg/arch.conf'
CONF_CANAL = {'public': '/etc/opkg/hdsatelit-feed.conf', 'proba': '/etc/opkg/hdsatelit-proba-feed.conf'}
INDEXURI = '/etc/enigma2/hds-indexuri-semnate.json'
DOSAR_JURNALE = '/home/root/logs'
JURNAL = DOSAR_JURNALE + '/hds-actualizari.log'
MARIME_JURNAL = 128 * 1024
REZULTAT = '/tmp/hds-actualizare-intrerupta.rezultat'
RULEAZA = '/tmp/hds-actualizare-intrerupta.ruleaza'
PE_PORNIRE = '/tmp/hds-actualizare-intrerupta.incercata'
# lacatul lui opkg 0.10 din imagine: /run/opkg.lock (vazut pe .122 in timpul unei instalari); /var/run e alt dosar
# (/var/volatile/run). Calea veche ramane a doua.
LACAT = '/run/opkg.lock'
LACATE = (LACAT, '/var/run/opkg.lock')
LUCRU = '/tmp/hds-reparare-opkg'
LISTE_IMPLICIT = '/var/lib/opkg/lists'
STATUS_IMPLICIT = '/var/lib/opkg/status'
PACHET_PRINCIPAL = 'enigma2-hdsatelit'
# partea a doua pe stick (Components/HdsParteaDoua.py, receptoarele cu NAND): legaturile din /usr spre stick se scot pe
# durata lui opkg, ca baza sa nu se scrie pe stick prin ele (ca detaseazaPentruBaza din meniu), si se pun la loc dupa
# cu motorul ei (aceeasi comanda ca scriptul de pornire rc3 S05)
PARTEA_DOUA_CONF = '/etc/hdsatelit-partea-doua.conf'
PARTEA_DOUA_LEGATURI = '/etc/hdsatelit-partea-doua/legaturi'
PARTEA_DOUA_MOTOR = '/usr/lib/enigma2/python/Components/HdsParteaDoua.py'
PYTHON = os.environ.get('HDS_AI_PYTHON', '/usr/bin/python3')
MAX_INCERCARI = 3
ASTEPTARE_LACAT_S = 600
# o descarcare cazuta (reteaua inca nepornita la prima rulare a lui enigma2.sh) se reia in aceeasi pornire, la rularile
# urmatoare ale lui enigma2.sh (dupa fiecare cadere a interfetei), de cel mult atatea ori pe pornire
MAX_DESCARCARI_PE_PORNIRE = 3
# inainte de o descarcare: cat se asteapta o ruta implicita; tabelele de rute care nu se pot citi = nu se asteapta
RETEA_ASTEPTARE_S = int(os.environ.get('HDS_AI_RETEA_S', '60'))
RUTE = ('/proc/net/route', '/proc/net/ipv6_route')
_descarcari_inainte = 0      # descarcarile cazute la rularile de dinainte ale acestei porniri (pornire())
_ADRESA = re.compile(r'^https://stb\.hdsatelit\.com/feed/(proba|public)/([0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3})/'
	r'([a-z0-9][a-z0-9_\-]{0,63})/?\Z')
_NUME = re.compile(r'^[a-z0-9][a-z0-9+.\-]{0,127}\Z')
_PAROLA_IN_ADRESA = re.compile(r'(?i)\b((?:https?|ftps?)://)[^/\s@]+@')
# randurile lui opkg care arata ca a ajuns la pachete (nu numai la descarcare): numai atunci se numara incercarea
_A_LUCRAT = re.compile(r'^(Upgrading|Installing|Configuring|Removing obsolete) ')


def c(cale):
	return RADACINA + cale


# ---------------------------------------------------------------- jurnal si fisiere mici

def jurnal(rand):
	"""Un rand in jurnalul actualizarilor (rotit ca HdsPachete.scrie_jurnal_rotit), fara parole din adrese"""
	rand = _PAROLA_IN_ADRESA.sub(r'\1', u'%s' % rand)
	rand = ''.join(x for x in rand if x >= ' ' or x == '\t')[:400]
	text = '%s pornire: %s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), rand)
	cale = c(JURNAL)
	try:
		if not os.path.isdir(os.path.dirname(cale)):
			os.makedirs(os.path.dirname(cale))
		if os.path.exists(cale) and os.path.getsize(cale) + len(text) > MARIME_JURNAL:
			os.replace(cale, cale + '.1')
		with open(cale, 'a', encoding='utf-8') as f:
			f.write(text)
			f.flush()
			os.fsync(f.fileno())
	except (IOError, OSError):
		pass
	sys.stdout.write('[hds-actualizare-intrerupta] %s' % text)


def scrie_atomic(cale, text, sincron=True):
	nou = cale + '.nou'
	with open(nou, 'w', encoding='utf-8') as f:
		f.write(text)
		f.flush()
		if sincron:
			os.fsync(f.fileno())
	os.replace(nou, cale)


def sterge(cale):
	try:
		os.remove(cale)
	except OSError:
		pass


def afisaj(text):
	"""Patru semne pe afisajul din fata, ca tools/hds-rezerva.sh (numai unde exista)"""
	try:
		if stat.S_ISCHR(os.stat(AFISAJ).st_mode) or os.path.isfile(AFISAJ):
			with open(AFISAJ, 'w') as f:
				f.write(('%-4.4s' % text))
	except (IOError, OSError):
		pass


# ---------------------------------------------------------------- citirile

def strofe(cale):
	"""Strofele unui fisier de control opkg (status sau lista), ca dictionare cu chei mici; [] fara fisier"""
	try:
		if cale.endswith('.gz'):
			f = gzip.open(cale, 'rt', encoding='utf-8', errors='replace')
		else:
			f = open(cale, 'r', encoding='utf-8', errors='replace')
		with f:
			text = f.read()
	except (IOError, OSError, EOFError, ValueError):
		return []
	rez = []
	d = {}
	cheie = None
	for rand in text.splitlines():
		if not rand.strip():
			if d:
				rez.append(d)
			d, cheie = {}, None
			continue
		if rand[:1] in (' ', '\t'):
			if cheie:
				d[cheie] += '\n' + rand
			continue
		k, semn, v = rand.partition(':')
		if semn:
			cheie = k.strip().lower()
			d[cheie] = v.strip()
	if d:
		rez.append(d)
	return rez


def configurarea():
	"""(optiuni din opkg.conf, randurile arch din arch.conf)"""
	optiuni = {}
	randuri = []
	try:
		with open(c(OPKG_CONF), 'r', encoding='utf-8', errors='replace') as f:
			for rand in f:
				p = rand.split()
				if len(p) >= 3 and p[0] == 'option':
					optiuni[p[1]] = p[2]
				if p and p[0] in ('option', 'dest'):
					randuri.append(rand.strip())
	except (IOError, OSError):
		pass
	arh = []
	try:
		with open(c(ARCH_CONF), 'r', encoding='utf-8', errors='replace') as f:
			arh = [r.strip() for r in f if r.split()[:1] == ['arch']]
	except (IOError, OSError):
		pass
	return optiuni, randuri, arh


def instalate(optiuni):
	"""{nume: (versiune, instalat)} din status-ul opkg"""
	rez = {}
	for s in strofe(c(optiuni.get('status_file', STATUS_IMPLICIT))):
		nume = s.get('package')
		if not nume:
			continue
		st = s.get('status', '').split()
		rez[nume] = (s.get('version', ''), 'installed' in st and 'not-installed' not in st)
	return rez


def versiunea_imaginii():
	"""imageversion= din /etc/image-version (0.7.4), sau '' """
	try:
		with open(c(IMAGE_VERSION), 'r', encoding='utf-8', errors='replace') as f:
			for rand in f.read(4096).splitlines():
				if rand.startswith('imageversion='):
					v = rand.split('=', 1)[1].strip()
					if re.match(r'^[0-9]{1,2}\.[0-9]{1,2}\.[0-9]{1,2}\Z', v):
						return v
	except (IOError, OSError):
		pass
	return ''


def versiune_scurta(versiune):
	"""0.7.3+git0+8f5d312fdc-r0 -> 0.7.3 (partea vazuta de om)"""
	v = (versiune or '').split(':', 1)[-1]
	return re.split(r'[+\-~]', v, maxsplit=1)[0]


def citeste_semnul():
	try:
		with open(c(SEMN), 'r', encoding='utf-8') as f:
			d = json.load(f)
	except (IOError, OSError, ValueError):
		return None if not os.path.exists(c(SEMN)) else {}
	return d if isinstance(d, dict) else {}


def pachete_ramase():
	"""Caile .ipk ramase in DOSAR_PACHETE (fara .partial)"""
	try:
		nume = sorted(os.listdir(c(DOSAR_PACHETE)))
	except OSError:
		return []
	return [os.path.join(c(DOSAR_PACHETE), n) for n in nume if n.endswith('.ipk') and
		os.path.isfile(os.path.join(c(DOSAR_PACHETE), n))]


def sha256(cale, dezarhiveaza=False):
	h = hashlib.sha256()
	n = 0
	f = gzip.open(cale, 'rb') if dezarhiveaza else open(cale, 'rb')
	with f:
		while True:
			b = f.read(1 << 16)
			if not b:
				break
			h.update(b)
			n += len(b)
	return h.hexdigest(), n


def surse_verificate(optiuni):
	"""[(nume, adresa, cale_lista)] ale canalului din indexurile semnate, numai cu lista egala (sha256 si marime) cu indexul
	semnat al arhitecturii ei; plus lista greselilor, pentru jurnal"""
	try:
		with open(c(INDEXURI), 'r', encoding='utf-8') as f:
			tinute = json.load(f)
	except (IOError, OSError, ValueError):
		return [], ['indexurile semnate lipsesc (%s)' % INDEXURI]
	if not isinstance(tinute, dict) or tinute.get('canal') not in CONF_CANAL or not isinstance(tinute.get('indexuri'),
			dict):
		return [], ['indexurile semnate nu se pot citi']
	canal, baza = tinute['canal'], tinute.get('baza')
	dosar = c(optiuni.get('lists_dir', LISTE_IMPLICIT))
	bune, greseli = [], []
	try:
		with open(c(CONF_CANAL[canal]), 'r', encoding='utf-8', errors='replace') as f:
			randuri = f.read().splitlines()
	except (IOError, OSError):
		return [], ['sursele canalului %s lipsesc' % canal]
	for rand in randuri:
		p = rand.split()
		if len(p) < 3 or p[0] not in ('src', 'src/gz'):
			continue
		m = _ADRESA.match(p[2])
		if not m or m.group(1) != canal or m.group(2) != baza:
			greseli.append('sursa %s nu e a canalului %s/%s' % (p[1], canal, baza))
			continue
		x = tinute['indexuri'].get(m.group(3))
		cale = None
		for cand in (os.path.join(dosar, p[1]), os.path.join(dosar, p[1] + '.gz')):
			if os.path.isfile(cand):
				cale = cand
				break
		if cale is None or not isinstance(x, dict):
			greseli.append('lista %s lipseste sau nu are index semnat' % p[1])
			continue
		try:
			bun = sha256(cale, cale.endswith('.gz')) == (x.get('sha256'), x.get('marime'))
		except (IOError, OSError, EOFError, ValueError):
			bun = False
		if bun:
			bune.append((p[1], p[2], cale))
		else:
			greseli.append('lista %s nu e cea semnata' % p[1])
	return bune, greseli


def intrari_verificate(surse):
	"""Pachetele din listele verificate: [{nume, versiune, sha256, fisier}]"""
	rez = []
	for _nume, _adresa, cale in surse:
		for s in strofe(cale):
			if s.get('package') and s.get('version') and s.get('sha256sum'):
				rez.append({'nume': s['package'], 'versiune': s['version'], 'sha256': s['sha256sum'].lower(),
					'fisier': s.get('filename', '')})
	return rez


def compara_versiuni(a, b):
	"""Comparatia lui opkg/dpkg, suficienta pentru versiunile noastre (epoca, apoi bucati de cifre si litere)"""
	def epoca(v):
		e, semn, rest = v.partition(':')
		return (int(e), rest) if semn and e.isdigit() else (0, v)

	def bucati(s):
		return [int(x) if x.isdigit() else x for x in re.findall(r'[0-9]+|[A-Za-z]+|[^0-9A-Za-z]', s)]
	ea, ra = epoca(a)
	eb, rb = epoca(b)
	if ea != eb:
		return -1 if ea < eb else 1
	for x, y in zip(bucati(ra), bucati(rb)):
		if x == y:
			continue
		if isinstance(x, int) and isinstance(y, int):
			return -1 if x < y else 1
		return -1 if str(x) < str(y) else 1
	return (len(bucati(ra)) > len(bucati(rb))) - (len(bucati(ra)) < len(bucati(rb)))


# ---------------------------------------------------------------- hotararea

def neterminata(semn, ramase, inst, img):
	"""Motivul pentru care actualizarea pare neterminata, sau '' cand nu e nimic de facut"""
	if semn is not None:
		return 'semnul actualizarii in curs'
	if ramase:
		return 'pachete ramase in %s' % DOSAR_PACHETE
	principal = inst.get(PACHET_PRINCIPAL)
	if principal is None:
		return ''
	if not principal[1]:
		return '%s nu e instalat de tot in status' % PACHET_PRINCIPAL
	if img and versiune_scurta(principal[0]) != img:
		return 'imaginea spune %s, iar status-ul opkg %s' % (img, versiune_scurta(principal[0]))
	return ''


def tinte(semn, ramase_verificate, inst, img, intrari):
	"""{nume: versiune} de instalat: din semn, din pachetele ramase si verificate, iar fara ele pachetul principal cu
	versiunea din /etc/image-version (cea mai mare intrare verificata cu partea scurta egala)"""
	rez = {}
	for nume, versiune in ((semn or {}).get('pachete') or {}).items():
		if _NUME.match(u'%s' % nume) and isinstance(versiune, str) and versiune:
			rez[nume] = versiune
	for _cale, x in ramase_verificate:
		rez.setdefault(x['nume'], x['versiune'])
	principal = inst.get(PACHET_PRINCIPAL)
	if PACHET_PRINCIPAL not in rez and img and principal is not None and \
			(not principal[1] or versiune_scurta(principal[0]) != img):
		potrivite = [x['versiune'] for x in intrari if x['nume'] == PACHET_PRINCIPAL and versiune_scurta(x['versiune']) == img]
		if potrivite:
			best = potrivite[0]
			for v in potrivite[1:]:
				if compara_versiuni(v, best) > 0:
					best = v
			rez[PACHET_PRINCIPAL] = best
	return rez


def nesatisfacute(tinta, inst):
	return sorted(n for n, v in tinta.items() if inst.get(n) != (v, True))


def principal_coerent(inst, img):
	p = inst.get(PACHET_PRINCIPAL)
	return p is None or (p[1] and (not img or versiune_scurta(p[0]) == img))


# ---------------------------------------------------------------- opkg

def opkg_ocupat():
	tinute = lacate_tinute(c('/proc/locks'))
	return any(_lacat_tinut(c(cale), tinute) for cale in LACATE)


def lacate_tinute(cale):
	"""{(major, minor, inode)} ale fisierelor cu un lacat tinut acum (/proc/locks), sau None cand nu se poate citi"""
	try:
		with open(cale, 'r', encoding='ascii', errors='replace') as f:
			text = f.read(1 << 16)
	except (IOError, OSError):
		return None
	rez = set()
	for rand in text.splitlines():
		p = rand.replace('->', ' ').split()
		if len(p) >= 6 and p[1] in ('POSIX', 'OFDLCK', 'FLOCK'):
			d = p[5].split(':')
			try:
				rez.add((int(d[0], 16), int(d[1], 16), int(d[2])))
			except (ValueError, IndexError):
				pass
	return rez


def _lacat_tinut(cale, tinute=None):
	"""Cu /proc/locks (tinute) fara sa ia lacatul; numai fara el (probele de pe PC), cu lockf o clipa"""
	if not os.path.exists(cale):
		return False
	if tinute is not None and hasattr(os, 'major'):
		try:
			st = os.stat(cale)
		except OSError:
			return False
		return (os.major(st.st_dev), os.minor(st.st_dev), st.st_ino) in tinute
	try:
		import fcntl
		fd = os.open(cale, os.O_RDWR)
	except (ImportError, OSError):
		return False
	try:
		try:
			fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
		except (IOError, OSError):
			return True
		fcntl.lockf(fd, fcntl.LOCK_UN)
		return False
	finally:
		os.close(fd)


def are_ruta():
	"""True: o ruta implicita IPv4 sau IPv6 (nu pe lo); False: niciuna; None: tabelele nu se pot citi"""
	citit = False
	for cale in RUTE:
		try:
			with open(c(cale), 'r', encoding='ascii', errors='replace') as f:
				randuri = f.read(1 << 16).splitlines()
		except (IOError, OSError):
			continue
		citit = True
		for rand in randuri:
			p = rand.split()
			if cale.endswith('ipv6_route'):
				# destinatia, prefixul, sursa, prefixul ei, urmatorul pas, metrica, ref, folosiri, steagurile, interfata
				if len(p) >= 10 and p[0] == '0' * 32 and p[1] == '00' and p[9] != 'lo':
					return True
			elif len(p) >= 3 and p[0] != 'Iface' and p[0] != 'lo' and p[1] == '00000000':
				return True
	return False if citit else None


def asteapta_reteaua():
	"""Inainte de o descarcare: cel mult RETEA_ASTEPTARE_S pana apare o ruta implicita (reteaua porneste uneori dupa
	enigma2.sh). Nu se asteapta cand tabelele de rute nu se pot citi."""
	t = 0
	while are_ruta() is False and t < RETEA_ASTEPTARE_S:
		if t == 0:
			jurnal('nicio ruta spre internet inca; astept reteaua cel mult %d s' % RETEA_ASTEPTARE_S)
		time.sleep(2)
		t += 2
	if t:
		jurnal('reteaua %s dupa %d s' % ('a pornit' if are_ruta() else 'tot nu are ruta', t))


def descarcari_cazute():
	"""Cate descarcari au cazut la pornirea aceasta, la rularile de dinainte ale programului (PE_PORNIRE)"""
	try:
		with open(c(PE_PORNIRE), 'r', encoding='utf-8', errors='replace') as f:
			for rand in f.read(256).splitlines():
				k, semn, v = rand.partition('=')
				if semn and k.strip() == 'descarcari' and v.strip().isdigit():
					return int(v.strip())
	except (IOError, OSError):
		pass
	return 0


def scrie_pe_pornire(descarcari):
	try:
		scrie_atomic(c(PE_PORNIRE), '%d\ndescarcari=%d\n' % (int(time.time()), descarcari), sincron=False)
	except (IOError, OSError):
		pass


def ruleaza_opkg(argumente):
	"""(cod, a_lucrat): opkg cu randurile in jurnal, fara termen (nu se opreste niciodata la jumatate)"""
	jurnal('opkg %s' % ' '.join(argumente))
	a_lucrat = False
	try:
		p = subprocess.Popen(OPKG + list(argumente), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
			stderr=subprocess.STDOUT)
	except OSError as e:
		jurnal('opkg nu porneste: %s' % e)
		return 127, False
	for rand in p.stdout:
		rand = rand.decode('utf-8', 'replace').rstrip()
		if rand:
			if _A_LUCRAT.match(rand):
				a_lucrat = True
			jurnal(rand)
	cod = p.wait()
	try:
		os.sync()
	except (AttributeError, OSError):
		pass
	return cod, a_lucrat


def configurare_proprie(randuri, arh, surse):
	"""O configurare opkg cu numai sursele verificate (copii ale listelor lor in LUCRU/lists): pachetele cerute dupa nume
	nu pot veni din alta lista"""
	dosar = c(LUCRU)
	liste = os.path.join(dosar, 'lists')
	if not os.path.isdir(liste):
		os.makedirs(liste)
	text = []
	text.extend(arh)
	text.extend(r for r in randuri if not r.startswith('option lists_dir'))
	text.append('option lists_dir %s' % liste)
	for nume, adresa, cale in surse:
		tinta = os.path.join(liste, nume)
		if cale.endswith('.gz'):
			with gzip.open(cale, 'rb') as f, open(tinta, 'wb') as g:
				g.write(f.read())
		else:
			with open(cale, 'rb') as f, open(tinta, 'wb') as g:
				g.write(f.read())
		text.append('src/gz %s %s' % (nume, adresa))
	cale_conf = os.path.join(dosar, 'opkg.conf')
	scrie_atomic(cale_conf, '\n'.join(text) + '\n', sincron=False)
	return cale_conf


def detaseaza_partea_doua():
	"""Scoate legaturile partii a doua (numai cele din inventarul ei care sunt inca legaturi spre tinta scrisa acolo) si
	le scoate si din inventar, ca HdsParteaDoua.reconciliaza(numai_scoate=True). True cand receptorul are partea a doua
	(atunci reataseaza_partea_doua o pune la loc dupa opkg)."""
	if not os.path.isfile(c(PARTEA_DOUA_CONF)):
		return False
	cale = c(PARTEA_DOUA_LEGATURI)
	try:
		with open(cale, 'r', encoding='utf-8') as f:
			randuri = f.read().splitlines()
	except (IOError, OSError):
		randuri = []
	ramase, scoase = [], 0
	for rand in randuri:
		p = rand.split('\t')
		if len(p) != 2 or not p[0] or not p[1]:
			continue
		plin = c('/' + p[0].lstrip('/'))
		try:
			if os.path.islink(plin) and os.readlink(plin) == p[1]:
				os.remove(plin)
				scoase += 1
				continue
		except OSError:
			pass
		ramase.append(rand)
	if scoase:
		try:
			scrie_atomic(cale, ''.join(r + '\n' for r in ramase))
		except (IOError, OSError) as e:
			jurnal('partea a doua: inventarul nu se poate scrie: %s' % e)
	jurnal('partea a doua: %d legaturi spre stick scoase pe durata lui opkg' % scoase)
	return True


def reataseaza_partea_doua():
	"""Legaturile partii a doua puse la loc de motorul ei (monteaza stickul si reconciliaza), cu termenul scriptului de
	pornire; nu e opkg, deci termenul nu lasa nimic la jumatate"""
	if not os.path.isfile(c(PARTEA_DOUA_MOTOR)):
		jurnal('partea a doua: motorul lipseste; legaturile se pun la loc la pornirea urmatoare')
		return
	try:
		r = subprocess.run([PYTHON, c(PARTEA_DOUA_MOTOR), 'porneste'], stdin=subprocess.DEVNULL,
			stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
		jurnal('partea a doua: legaturile puse la loc (cod %s, %s)' % (r.returncode,
			r.stdout.decode('utf-8', 'replace').strip()[-120:]))
	except (OSError, subprocess.TimeoutExpired) as e:
		jurnal('partea a doua: legaturile nu s-au putut pune la loc: %s' % e)


def goleste_lucrul():
	dosar = c(LUCRU)
	for sub, _d, fisiere in os.walk(dosar, topdown=False):
		for n in fisiere:
			sterge(os.path.join(sub, n))
		try:
			os.rmdir(sub)
		except OSError:
			pass


def scrie_rezultat(stare, versiune, detaliu, ramase=()):
	try:
		scrie_atomic(c(REZULTAT), 'stare=%s\nversiune=%s\nramase=%s\ndetaliu=%s\nora=%d\n' % (stare, versiune,
			' '.join(ramase), detaliu.replace('\n', ' ')[:300], int(time.time())), sincron=False)
	except (IOError, OSError) as e:
		jurnal('rezultatul nu se poate scrie: %s' % e)


def scrie_semnul(semn):
	try:
		scrie_atomic(c(SEMN), json.dumps(semn, sort_keys=True) + '\n')
	except (IOError, OSError, TypeError, ValueError) as e:
		jurnal('semnul nu se poate scrie: %s' % e)


# ---------------------------------------------------------------- pornirea

def pornire():
	optiuni, randuri, arh = configurarea()
	semn = citeste_semnul()
	ramase = pachete_ramase()
	inst = instalate(optiuni)
	img = versiunea_imaginii()
	motiv = neterminata(semn, ramase, inst, img)
	if not motiv:
		return 0
	if semn and semn.get('renuntat') and not ramase:
		return 0
	global _descarcari_inainte
	_descarcari_inainte = 0
	if os.path.exists(c(PE_PORNIRE)):
		# o singura data pe pornire; numai dupa o descarcare cazuta (reteaua) se mai incearca, de cel mult
		# MAX_DESCARCARI_PE_PORNIRE ori
		_descarcari_inainte = descarcari_cazute()
		if not 0 < _descarcari_inainte < MAX_DESCARCARI_PE_PORNIRE:
			return 0
		jurnal('descarcarea a cazut de %d ori la pornirea aceasta; incerc din nou' % _descarcari_inainte)
	# descarcari=0 pana se dovedeste altfel: o rulare oprita la jumatate nu se reia la nesfarsit
	scrie_pe_pornire(0)
	try:
		scrie_atomic(c(RULEAZA), '%d\n' % os.getpid(), sincron=False)
	except (IOError, OSError):
		pass
	try:
		return _termina(optiuni, randuri, arh, semn, ramase, inst, img, motiv)
	finally:
		sterge(c(RULEAZA))
		goleste_lucrul()


def _termina(optiuni, randuri, arh, semn, ramase, inst, img, motiv):
	jurnal('actualizare neterminata: %s' % motiv)
	afisaj('UPD')
	t = 0
	while opkg_ocupat() and t < ASTEPTARE_LACAT_S:
		if t == 0:
			jurnal('alt opkg ruleaza; astept sa termine')
		time.sleep(5)
		t += 5
	if opkg_ocupat():
		jurnal('alt opkg ruleaza de %d s; nu ating nimic acum' % t)
		return 0
	detasat = detaseaza_partea_doua()
	try:
		return _termina_opkg(optiuni, randuri, arh, semn, ramase, inst, img)
	finally:
		if detasat:
			reataseaza_partea_doua()


def _termina_opkg(optiuni, randuri, arh, semn, ramase, inst, img):
	semn = dict(semn or {})
	versiune = semn.get('versiune') or img
	inainte = inst
	ruleaza_opkg(['configure'])
	inst = instalate(optiuni)
	surse, greseli = surse_verificate(optiuni)
	for g in greseli:
		jurnal(g)
	intrari = intrari_verificate(surse)
	dupa_suma = {}
	for x in intrari:
		dupa_suma.setdefault(x['sha256'], x)
	verificate = []
	for cale in ramase:
		try:
			suma, _n = sha256(cale)
		except (IOError, OSError):
			continue
		x = dupa_suma.get(suma)
		if x is None:
			jurnal('%s nu e in listele semnate; nu se foloseste' % os.path.basename(cale))
		else:
			verificate.append((cale, x))
	tinta = tinte(semn, verificate, inst, img, intrari)
	lipsa = nesatisfacute(tinta, inst)
	if not lipsa and principal_coerent(inst, img):
		if nesatisfacute(tinta, inainte) or not principal_coerent(inainte, img):
			return _gata(semn, versiune, tinta, 'opkg configure')
		# nimic de terminat (opkg a apucat sa iasa singur, sau pachetele ramase nu sunt in listele semnate): numai curatenie
		jurnal('nimic de terminat; semnul si pachetele ramase se scot')
		sterge(c(SEMN))
		for cale in pachete_ramase():
			sterge(cale)
		return 0
	if not lipsa:
		# imaginea si status-ul nu se potrivesc, dar listele semnate nu au pachetul principal cu versiunea imaginii
		jurnal('listele semnate nu au %s %s; nu se poate termina aici' % (PACHET_PRINCIPAL, img))
		semn['renuntat'] = 1
		scrie_semnul(semn)
		return 0
	fisiere, nume = [], []
	for n in lipsa:
		cale = next((cl for cl, x in verificate if x['nume'] == n and x['versiune'] == tinta[n]), None)
		if cale:
			fisiere.append(cale)
		elif any(x['nume'] == n and x['versiune'] == tinta[n] for x in intrari):
			nume.append(n)
		else:
			jurnal('%s %s nu e in listele semnate' % (n, tinta[n]))
	if not fisiere and not nume:
		semn.update({'renuntat': 1, 'pachete': tinta})
		scrie_semnul(semn)
		scrie_rezultat('esuata', versiune, 'pachetele nu sunt in listele semnate', lipsa)
		return 0
	try:
		conf = configurare_proprie(randuri, arh, surse)
	except (IOError, OSError) as e:
		jurnal('configurarea opkg nu se poate scrie: %s' % e)
		return 0
	if nume:
		asteapta_reteaua()
	cod, a_lucrat = ruleaza_opkg(['-f', conf, 'install'] + fisiere + nume)
	inst = instalate(optiuni)
	lipsa = nesatisfacute(tinta, inst)
	jurnal('instalare la pornire: cod %s, ramase %s' % (cod, lipsa))
	if not lipsa and principal_coerent(inst, img):
		return _gata(semn, versiune, tinta, 'opkg install')
	# se numara orice incercare in care opkg a ajuns la pachete sau a iesit cu 0 fara sa le schimbe (libsolv tine un
	# pachet pe loc: se va intampla la fel data viitoare); nu se numara o descarcare cazuta (retea, ceas)
	if a_lucrat or cod == 0:
		semn['incercari'] = int(semn.get('incercari') or 0) + 1
	else:
		# descarcarea a cazut: rularea urmatoare a lui enigma2.sh (dupa caderea interfetei) mai incearca o data
		scrie_pe_pornire(_descarcari_inainte + 1)
		if _descarcari_inainte + 1 < MAX_DESCARCARI_PE_PORNIRE:
			jurnal('descarcarea a cazut; incerc din nou la urmatoarea pornire a interfetei')
	semn['pachete'] = tinta
	if int(semn.get('incercari') or 0) >= MAX_INCERCARI:
		semn['renuntat'] = 1
		jurnal('actualizarea nu s-a putut termina dupa %d incercari; nu mai incerc' % MAX_INCERCARI)
	scrie_semnul(semn)
	scrie_rezultat('esuata', versiune, 'cod %s' % cod if (a_lucrat or cod == 0) else 'pachetele nu s-au descarcat', lipsa)
	return 0


def _gata(semn, versiune, tinta, cum):
	jurnal('actualizarea %s s-a terminat la pornire (%s): %s' % (versiune or '?', cum,
		' '.join('%s %s' % kv for kv in sorted(tinta.items())) or PACHET_PRINCIPAL))
	sterge(c(SEMN))
	for cale in pachete_ramase():
		sterge(cale)
	scrie_rezultat('terminata', versiune, cum)
	return 0


def main(argv):
	if argv[1:2] != ['pornire']:
		sys.stderr.write('folosire: hds-actualizare-intrerupta.py pornire\n')
		return 0
	try:
		return pornire() or 0
	except Exception as e:  # pornirea interfetei nu depinde de acest program
		jurnal('eroare neprevazuta: %r' % (e,))
		return 0


if __name__ == '__main__':
	sys.exit(main(sys.argv))
