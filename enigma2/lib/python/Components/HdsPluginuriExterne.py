# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Feedul pluginurilor externe (0.6.6): pluginuri luate de la altii, construite de Monea
Software din sursa lor publica si tinute pe moneasoftware.com, cate un dosar pe arhitectura procesorului:
  https://moneasoftware.com/apps/hdsatelit-enigma2/feed/<arhitectura>   (si feed-proba/<arhitectura>, numai pentru probe)
Feedul pluginurilor noastre ramane pe stb.hdsatelit.com (Components/HdsActualizari.py, reteta hdsatelit-feed).

Imaginea il pune singura in /etc/opkg/hds-pluginuri-externe.conf, la pornirea interfetei (mytest.py): asa vine si printr-o
actualizare prin pachete, fara flash (stratul imaginii nu se schimba printr-o actualizare, iar dupa instalare interfata
reporneste oricum), si in orice imagine urmatoare. Arhitectura nu e scrisa in cod: e cea a pachetelor de baza instalate
(python3-core, libc6, busybox, opkg; in OE = TUNE_PKGARCH, aceeasi pe Amiko Viper 4K V10, V20, V30 si V40:
cortexa15hf-neon-vfpv4), verificata in lista `arch` a lui opkg. Un receptor cu alt procesor primeste dosarul lui.

Fara surse dublate (opkg da eroare la doua surse cu acelasi nume): nu se scrie cand acelasi nume sau aceeasi adresa e deja
in alt fisier din /etc/opkg (adaugat de om din Extensii > Surse sau cu o comanda); atunci un fisier al nostru ramas se
sterge. Un fisier fara randul nostru de inceput nu se atinge. opkg-ul imaginii nu verifica semnaturi: feedul se ia numai
prin https; Extensii il arata separat, cu numele lui (Components/HdsExtensiiLucru.py).
Modulul nu depinde de enigma, ca sa poata fi incercat si pe PC (parametrul radacina)."""
import os
import re
try:
	from urllib.parse import urlsplit
except ImportError:  # Python 2 (doar pentru teste vechi)
	from urlparse import urlsplit

try:
	from Components import HdsPachete as P
except ImportError:  # probe pe PC: modulul incarcat singur, din dosarul Components
	import HdsPachete as P

FISIER = '/etc/opkg/hds-pluginuri-externe.conf'
NUME_SURSA = 'pluginuri-externe'
GAZDA = 'moneasoftware.com'
DOSAR = '/apps/hdsatelit-enigma2/feed'
ADRESA = 'https://' + GAZDA + DOSAR
ANTET = '# HD Satelit: feedul pluginurilor externe (Monea Software, moneasoftware.com). Il scrie imaginea la pornire.'
# pachetele de baza ale imaginii, construite pentru procesor (nu pentru masina sau pentru toate): Architecture lor e
# arhitectura procesorului; primul gasit hotaraste
PACHETE_PROCESOR = ('python3-core', 'libc6', 'busybox', 'opkg')
FARA_PROCESOR = ('all', 'any', 'noarch')
_ARH = re.compile(r'^[a-z0-9][a-z0-9_\-]{0,63}\Z')
# calea unui dosar al feedului: /apps/hdsatelit-enigma2/feed/<arh> (public) sau feed-proba/<arh>
_CALE = re.compile(r'^/apps/hdsatelit-enigma2/feed(-proba)?/([a-z0-9][a-z0-9_\-]{0,63})/?\Z')


def _jurnal(text):
	print('[HdsPluginuriExterne] %s' % text)


def _potrivire(adresa):
	try:
		parti = urlsplit(adresa or '')
		gazda = (parti.hostname or '').lower()
	except ValueError:
		return None
	if parti.scheme != 'https' or gazda != GAZDA or parti.query or parti.fragment:
		return None
	return _CALE.match(parti.path or '')


def e_feed_extern(adresa):
	"""True pentru adresa unui dosar al feedului pluginurilor externe (public sau de proba), numai prin https"""
	return _potrivire(adresa) is not None


def e_feed_extern_public(adresa):
	"""True pentru un dosar al feedului public (nu feed-proba)"""
	m = _potrivire(adresa)
	return m is not None and not m.group(1)


def adresa_pentru(arhitectura):
	return '%s/%s' % (ADRESA, arhitectura)


def text_fisier(arhitectura):
	return '%s\nsrc/gz %s %s\n' % (ANTET, NUME_SURSA, adresa_pentru(arhitectura))


def arhitectura_procesorului(radacina='/', conf=None):
	"""Arhitectura procesorului pentru pachetele opkg (de pilda cortexa15hf-neon-vfpv4), din starea pachetelor de baza
	instalate (PACHETE_PROCESOR), sau None cand nu se poate afla sigur. Numai citire."""
	conf = conf or P.citeste_configurarea(radacina)
	try:
		with open(P._cale(radacina, conf.status_file), 'r', encoding='utf-8', errors='replace') as fh:
			text = fh.read()
	except (IOError, OSError):
		return None
	gasite = {}
	for strofa in text.split('\n\n'):
		cap = strofa.lstrip('\n')
		if not cap.startswith('Package: '):
			continue
		nume = cap[9:].split('\n', 1)[0].strip()
		if nume not in PACHETE_PROCESOR or nume in gasite:
			continue
		campuri = {}
		for rand in cap.split('\n'):
			if ':' in rand and rand[:1] not in ' \t':
				k, v = rand.split(':', 1)
				campuri[k.strip().lower()] = v.strip()
		stare = campuri.get('status', '').split()
		if 'installed' in stare and 'not-installed' not in stare:
			gasite[nume] = campuri.get('architecture', '')
	for nume in PACHETE_PROCESOR:
		arh = gasite.get(nume, '')
		if arh and arh not in FARA_PROCESOR and _ARH.match(arh) and (not conf.arhitecturi or arh in conf.arhitecturi):
			return arh
	return None


def _surse_din_alte_fisiere(radacina):
	"""[(nume, adresa, fisier)] din toate fisierele de configurare opkg, afara de FISIER (fara deduplicare: doua surse
	cu acelasi nume in fisiere diferite trebuie vazute amandoua)"""
	rez = []
	fisiere = []
	for p in ('/etc/opkg/opkg.conf', '/etc/opkg.conf'):
		if os.path.isfile(P._cale(radacina, p)):
			fisiere.append(P._cale(radacina, p))
	dosar = P._cale(radacina, '/etc/opkg')
	try:
		for f in sorted(os.listdir(dosar)):
			p = os.path.join(dosar, f)
			if f.endswith('.conf') and p not in fisiere and os.path.isfile(p):
				fisiere.append(p)
	except OSError:
		pass
	al_nostru = os.path.basename(FISIER)
	for p in fisiere:
		if os.path.basename(p) == al_nostru and os.path.dirname(p) == dosar:
			continue
		try:
			with open(p, 'r', encoding='utf-8', errors='replace') as fh:
				randuri = fh.read().splitlines()
		except (IOError, OSError):
			continue
		for r in randuri:
			parti = r.split()
			if len(parti) >= 3 and parti[0] in ('src', 'src/gz'):
				rez.append((parti[1], parti[2], p))
	return rez


def _scrie(cale, text):
	nou = cale + '.nou'
	try:
		dosar = os.path.dirname(cale)
		if not os.path.isdir(dosar):
			os.makedirs(dosar)
		with open(nou, 'w', encoding='utf-8') as fh:
			fh.write(text)
			fh.flush()
			os.fsync(fh.fileno())
		os.replace(nou, cale)
		return None
	except (IOError, OSError) as e:
		try:
			os.remove(nou)
		except OSError:
			pass
		return str(getattr(e, 'strerror', None) or e)


def pune_feedul(radacina='/'):
	"""Pune (sau tine la zi) FISIER. Intoarce (fel, detaliu): fel 'scris', 'la-zi', 'dublat' (aceeasi sursa e in alt
	fisier; un FISIER al nostru ramas a fost sters), 'strain' (FISIER exista fara ANTET: neatins), 'fara-arhitectura'
	sau 'eroare'. Nu porneste nimic (lista se descarca la urmatorul opkg update: Extensii la deschidere, verificarea
	zilnica a actualizarilor)."""
	cale = P._cale(radacina, FISIER)
	try:
		with open(cale, 'r', encoding='utf-8', errors='replace') as fh:
			acum = fh.read()
	except (IOError, OSError):
		acum = None
	if acum is not None and not acum.startswith(ANTET):
		return 'strain', ''
	for nume, adresa, fisier in _surse_din_alte_fisiere(radacina):
		if nume == NUME_SURSA or e_feed_extern_public(adresa):
			if acum is not None:
				try:
					os.remove(cale)
				except OSError as e:
					return 'eroare', str(e)
			return 'dublat', fisier
	conf = P.citeste_configurarea(radacina)
	arh = arhitectura_procesorului(radacina, conf)
	if not arh:
		return 'fara-arhitectura', ''
	text = text_fisier(arh)
	if acum == text:
		return 'la-zi', arh
	eroare = _scrie(cale, text)
	if eroare:
		return 'eroare', eroare
	return 'scris', arh


def porneste(radacina='/'):
	"""Din mytest.py, la pornire. Pornirea nu depinde de el."""
	try:
		fel, detaliu = pune_feedul(radacina)
	except Exception as e:
		_jurnal('eroare: %s' % e)
		return None
	if fel != 'la-zi':
		_jurnal('%s %s' % (fel, detaliu))
	return fel
