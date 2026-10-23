# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsActualizari.py: "Actualizare software" prin pachete opkg, din feedul imaginii.
# Ecranul e Screens/HdsActualizari.py, pagina web HdsWebControl/actualizari_web.py; amandoua citesc si pornesc totul
# de aici (o singura stare, o singura lucrare odata).
#
# Feedul: https://stb.hdsatelit.com/feed/<canal>/<baza>/<arh>/ (Packages.gz si .ipk) si .../<baza>/stare.json, unde
# <baza> e imaginea scrisa pe receptor (version= din /etc/hdsatelit-model, pus de reteta imaginii si neatins de
# pachete). Sursele opkg: /etc/opkg/hdsatelit-feed.conf (canalul public, din imagine) si
# /etc/opkg/hdsatelit-proba-feed.conf (canalul de proba, numai pe receptoarele noastre, pus de trusa impreuna cu
# parola din /home/root/.netrc). Parola nu sta in adrese: opkg ar scrie-o in "Downloading ..."; wget-ul pornit de opkg
# o ia din $HOME/.netrc (enigma2 are HOME=/, de aceea si legatura /.netrc), iar stare.json se cere de aici cu ea.
#
# Cautarea: stare.json (pe un fir separat), apoi `opkg update`, apoi planul (pe un fir separat): pachetele instalate
# pentru care sursele HD Satelit ale canalului au o versiune mai noua, cu dependintele verificate fata de ce e
# instalat. Instalarea: `opkg install <fisier>` (Semnatura), numai la cererea omului si numai daca verdictul o lasa;
# dupa ea interfata trebuie repornita (fisierele enigma2 de pe disc s-au schimbat sub interfata care ruleaza), deci
# nimic altceva nu mai porneste de aici pana atunci.
#
# Verdictul "imagine noua" (nu se instaleaza, se spune de ce): stare.json o cere, baza feedului alta decat baza
# receptorului, imaginea minima mai mare, un pachet de nucleu, drivere sau biblioteci de baza in plan, o dependinta
# pe care imaginea nu o are, sau mai mult de PRAG_PACHETE pachete. Nu exista "continua totusi".
#
# Versiunile: omul vede numai versiunea (0.3.2), adica partea dinaintea lui "+git"
# din versiunea pachetului enigma2-hdsatelit instalat si campul "versiune" din stare.json; fiecare actualizare prin
# pachete are urmatorul numar (construieste-pachete.sh). Baza (imaginea scrisa de pe stick, /etc/hdsatelit-model) e
# numai a feedului si se arata ca detaliu ("Imaginea de bază" in "Despre" si la avertizarea de imagine noua). Campul
# "actualizare" din stare.json e un numar intern (creste la fiecare publicare): leaga pagina web de rezultatul vazut.
#
# Verificarea zilnica (VerificareZilnica, pornita din mytest.py): numai stare.json, la 5 minute dupa pornire si apoi o
# data pe zi; anunta o singura data fiecare actualizare noua (sau imagine noua), nu instaleaza nimic; se opreste din
# ecran sau din pagina web (config.hds_actualizari.zilnic).
#
# "Ce e nou": stare.json are si campul "versiuni" (scris de oe-build/feed_actualizare.py din
# jurnalul imaginii): noutatile fiecarei versiuni publicate pe baza aceasta, in romana si in engleza. La cautare se
# pastreaza numai versiunile mai noi decat cea instalata, pana la cea de pe server (de la 0.3.2 la 0.3.5: 0.3.5, 0.3.4
# si 0.3.3), iar ecranul si pagina web le arata grupate, in limba receptorului (noutati, text_noutati). Un stare.json
# fara camp (feedurile de dinainte) sau cu el stricat arata "ce_e_nou" al versiunii de pe server, ca pana acum.
#
# Semnatura: receptorul instaleaza numai ce e semnat de HD Satelit, chiar daca
# serverul feedului ar fi spart. stare.json se primeste numai cu stare.json.sig de langa el, verificata pe octetii
# primiti cu cheile din Components/HdsSemnatura.py; stare.json semnat tine sha256 pentru fiecare <arh>/Packages
# ("indexuri") si pentru fiecare .ipk. Dupa `opkg update`, listele feedului trebuie sa fie chiar cele semnate (altfel se
# sterg). La instalare, pachetele planului se descarca aici, in DOSAR_PACHETE, se verifica (marimea si sha256 semnate)
# si abia apoi le instaleaza opkg din fisier (`opkg install <cale>`: fisierul local are intaietate, deci se instaleaza
# chiar octetii verificati, nu o versiune mai mare din alta sursa). Orice nepotrivire da starea NESEMNATA ("Actualizarea
# nu e semnată de HD Satelit; nu se instalează.") si nimic nu ajunge la opkg. Dupa un `opkg update` al Extensiilor,
# pazeste_listele sterge listele HD Satelit care nu sunt cele din ultima stare.json semnata. opkg 0.8.0 din imagine stie
# semnaturi numai prin gpg (nu e compilat cu el), de aceea verificarea e aici.
#
# "Actualizează rapid" (pagina web, actualizeazaRapid): un singur clic cauta, instaleaza daca e o actualizare de
# instalat si reporneste interfata, totul aici, pe receptor (pagina se poate inchide dupa apasare). Cautarea si
# instalarea sunt chiar cauta() si instaleaza(), cu aceleasi verificari (semnatura, pachetele, verdictul); orice alt
# rezultat (la zi, imagine noua, nesemnata, fara retea, o eroare) opreste modul rapid si lasa mesajul obisnuit.
# Repornirea o da pagina web (TryQuitMainloop 3, calea sigura), numai cand nu ar intreba pe televizor: cat o
# inregistrare e in curs sau incepe in mai putin de 6 minute, cat merge o lucrare in fundal sau cat o intrebare de
# repornire e pe ecran, se asteapta si se incearca din nou, apoi interfata se reporneste singura (ca TryQuitMainloop
# cand nu raspunde nimeni la intrebare).
#
# Modulul nu importa nimic din enigma la incarcare (probele de pe PC: teste/test_actualizari_pachete_*.py,
# teste/test_semnare_actualizari.py si teste/test_actualizare_rapida.py).

import base64
import hashlib
import json
import os
import re
import shutil
import socket
import time
from functools import cmp_to_key

try:
	from urllib.request import Request, urlopen
	from urllib.error import HTTPError, URLError
except ImportError:  # Python 2 (probe vechi)
	from urllib2 import Request, urlopen, HTTPError, URLError

try:
	from Components import HdsPachete as P
except ImportError:  # probele de pe PC: modulul incarcat singur, din dosarul Components
	import HdsPachete as P


def N_(text):
	"""Marcheaza un text pentru xgettext (--keyword=N_) fara sa-l traduca acum."""
	return text


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi pe PC."""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


ADRESA_FEED = 'https://stb.hdsatelit.com/feed'
GAZDA_FEED = 'stb.hdsatelit.com'
FISIER_MODEL = '/etc/hdsatelit-model'
CONF_PUBLIC = '/etc/opkg/hdsatelit-feed.conf'
CONF_PROBA = '/etc/opkg/hdsatelit-proba-feed.conf'
NETRC = ('/home/root/.netrc', '/.netrc')
LACAT_OPKG = '/var/run/opkg.lock'
JURNAL = '/tmp/hds-actualizari.log'
PACHET_PRINCIPAL = 'enigma2-hdsatelit'
PRAG_PACHETE = 150
MARIME_STARE_MAX = 256 * 1024
TIMP_STARE = 20
PRIMA_VERIFICARE = 300
ZI = 24 * 3600
REINCERCARE = 3 * 3600
UA = 'hdsatelit-receptor/1'
FORMAT = 1
RANDURI_JURNAL = 200
# campul "versiuni" din stare.json: aceleasi margini ca in oe-build/feed_actualizare.py (verifica_stare)
MAX_VERSIUNI = 30
MAX_RANDURI_VERSIUNE = 60
MAX_SEMNE_NOUTATE = 400
MAX_DATA = 20
LIMBI_NOUTATI = ('ro', 'en')
# semnatura lui stare.json (langa el), pachetele verificate inainte de opkg si indexurile
# din ultima stare.json semnata (pentru Extensii, pazeste_listele)
NUME_SEMNATURA = 'stare.json.sig'
MARIME_SEMNATURA_MAX = 8 * 1024
SCOP_STARE = 'stare.json'
DOSAR_PACHETE = '/tmp/hds-actualizare'
LOC_IN_PLUS = 16 * 1024 * 1024
TIMP_PACHET = 60
INDEXURI_SEMNATE = '/etc/enigma2/hds-indexuri-semnate.json'
# actualizarea rapida: repornirea porneste la atatea ms dupa instalare (pagina web apuca sa vada pasul inainte sa cada
# interfata); cat ar intreba pe televizor, se incearca din nou la atatea ms
REPORNIRE_RAPIDA_MS = 3000
REINCERCARE_RAPIDA_MS = 30000
# de ce asteapta repornirea rapida (raspunsul functiei de repornire) si ce se scrie atunci
TEXTE_ASTEPTARE = {
	'inregistrare': N_('Actualizarea s-a instalat. Interfața se repornește singură după înregistrare.'),
	'lucrare': N_('Actualizarea s-a instalat. Interfața se repornește singură după ce se termină lucrarea din fundal.'),
	'intrebare': N_('Actualizarea s-a instalat. Pe televizor se așteaptă un răspuns la întrebarea de repornire.'),
}

_BAZA = re.compile(r'^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\Z')
# versiunea vazuta de om (si vechile nume x.y.z.N de dinainte de versiunile simple)
_VERSIUNE = re.compile(r'^[0-9]{1,3}(?:\.[0-9]{1,3}){2,3}\Z')
_ADRESA_FEED = re.compile(r'^https://stb\.hdsatelit\.com/feed/(proba|public)/([0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3})/'
	r'([a-z0-9][a-z0-9_\-]{0,63})/?\Z')
_PAROLA_IN_ADRESA = re.compile(r'(https?://)[^/\s@]+@')
_SHA256 = re.compile(r'^[0-9a-f]{64}\Z')
_FISIER_IPK = re.compile(r'^[A-Za-z0-9][A-Za-z0-9+._~\-]{0,200}\.ipk\Z')
_ARH = re.compile(r'^[a-z0-9][a-z0-9_\-]{0,63}\Z')

# pachetele care nu se schimba prin actualizare (nucleul, driverele, bibliotecile de baza); aceeasi lista o are si
# scriptul care face feedul, deci ele nu ajung niciodata in feed
TIPARE_IMAGINE_NOUA = (
	# driverele inaintea nucleului: kernel-module-* incepe si el cu kernel-
	('drivere', re.compile(r'^(kernel-module-|dinobot-|.*-dvb-modules|firmware-|v4l-dvb-)')),
	('nucleu', re.compile(r'^(kernel$|kernel-|linux-|uimage)')),
	('biblioteci', re.compile(r'^(libc6|libc-|glibc|ld-linux|libgcc|libstdc\+\+|busybox|opkg|update-alternatives|'
		r'python3-core|python3$|libpython3|openssl|libssl|libcrypto|base-files|base-passwd|sysvinit|initscripts|'
		r'eudev|udev|netbase|libz1|zlib)')),
)

# motivele "imagine noua", in ordinea in care se arata
MOTIVE = (
	('baza', N_('Actualizările de pe server sunt pentru altă imagine decât cea de pe receptor.')),
	('imagine-minima', N_('Actualizarea cere o imagine mai nouă decât cea de pe receptor.')),
	('nucleu', N_('Actualizarea schimbă nucleul Linux.')),
	('drivere', N_('Actualizarea schimbă driverele receptorului.')),
	('biblioteci', N_('Actualizarea cere biblioteci de bază pe care imaginea de acum nu le are.')),
	('prea-multe', N_('Actualizarea are prea multe pachete pentru o instalare din meniu.')),
	('alt-motiv', N_('Pentru această actualizare trebuie pusă imaginea nouă.')),
)
TEXT_MOTIV = dict(MOTIVE)
TEXT_IMAGINE_NOUA = N_('Trebuie pusă imaginea nouă de la zero, din „Imagine nouă de pe stick”. Instalată din meniu peste '
	'imaginea de acum, actualizarea poate face receptorul instabil, de aceea aici nu se instalează.')

# starea cautarii (rezultat['stare']) si textul ei
NECAUTAT, LA_ZI, DISPONIBILA, IMAGINE_NOUA, FARA_RETEA, FARA_RASPUNS, FARA_SURSA, FARA_CHEIE, EROARE = (
	'necautat', 'la-zi', 'disponibila', 'imagine-noua', 'fara-retea', 'fara-raspuns', 'fara-sursa', 'fara-cheie',
	'eroare')
# stare.json, listele sau un pachet nu sunt cele semnate de HD Satelit
NESEMNATA = 'nesemnata'
TEXTE_STARE = {
	NECAUTAT: N_('Actualizările nu au fost căutate încă.'),
	LA_ZI: N_('Software-ul este la zi.'),
	DISPONIBILA: N_('Este disponibilă o actualizare.'),
	IMAGINE_NOUA: N_('Actualizarea nu se poate instala din meniu.'),
	FARA_RETEA: N_('Receptorul nu este conectat la internet acum, deci actualizările nu se pot căuta.'),
	FARA_RASPUNS: N_('Serverul de actualizări (stb.hdsatelit.com) nu a răspuns.'),
	FARA_SURSA: N_('Imaginea de pe receptor nu are sursa actualizărilor.'),
	FARA_CHEIE: N_('Canalul de probă cere parola receptorului, care lipsește sau nu mai este bună.'),
	NESEMNATA: N_('Actualizarea nu e semnată de HD Satelit; nu se instalează.'),
	EROARE: N_('Căutarea actualizărilor nu a reușit.'),
}


# ---------------------------------------------------------------- texte si curatenie

def curata(text):
	"""Un rand de opkg sau o eroare, fara nume si parola din adrese (https://nume:parola@gazda -> https://gazda) si
	fara caractere de control."""
	text = _PAROLA_IN_ADRESA.sub(r'\1', u'%s' % (text or ''))
	return ''.join(c for c in text if c >= ' ' or c == '\t')[:400]


def motiv_eroare(linii, implicit):
	"""Motivul unei erori opkg, numai din ce scrie opkg (fara presupuneri, fara trimiteri la tastele altor ecrane)"""
	t = '\n'.join(linii).lower()
	if 'no space left' in t or ('only have' in t and 'available' in t):
		return _t('Nu mai este loc în memoria receptorului.')
	if 'could not obtain administrative lock' in t or 'could not lock' in t:
		return _t('Alt program instalează pachete acum.')
	try:
		ceas = P._ceas_scurt(linii)
	except Exception:
		ceas = None
	if ceas:
		return ceas
	if 'unknown package' in t or 'cannot find package' in t or 'no candidates to install' in t:
		return _t('Un pachet nu se mai află pe server.')
	if 'incompatible with the architectures' in t or 'not compatible with' in t:
		return _t('Un pachet nu este făcut pentru acest receptor.')
	if 'mismatch' in t:
		return _t('Un fișier descărcat nu se potrivește cu suma din lista serverului.')
	if 'failed to download' in t or 'wget returned' in t:
		return _t('Un fișier nu s-a putut descărca de pe server.')
	if 'clash' in t or 'file conflicts' in t:
		return _t('Un pachet ar scrie peste fișierele altui pachet.')
	if 'malformed' in t or 'error unpacking' in t or 'not a valid' in t or 'failed to extract' in t:
		return _t('Un fișier descărcat nu se poate citi.')
	return implicit


def motiv_imagine_noua(nume):
	for motiv, tipar in TIPARE_IMAGINE_NOUA:
		if tipar.match(nume or ''):
			return motiv
	return None


def versiune_scurta(versiune):
	"""0.3.2+git0+20d834b510-r0 -> 0.3.2 (20d834b510); 0.1.0-r0.hds2 -> 0.1.0-r0.hds2"""
	v = (versiune or '').split(':', 1)[-1]
	m = re.match(r'^([0-9.]+)\+git[0-9]*\+([0-9a-f]{7,40})(?:-.*)?\Z', v)
	if m:
		return '%s (%s)' % (m.group(1), m.group(2)[:10])
	return v


def versiunea_starii(stare):
	"""Versiunea vazuta de om dintr-un stare.json: campul "versiune" (0.3.2); la un stare.json fara el, baza (fara
	actualizari) sau baza.N, cum se numeau inainte de versiunile simple"""
	v = stare.get('versiune')
	if isinstance(v, str) and _VERSIUNE.match(v):
		return v
	n = stare.get('actualizare') or 0
	baza = u'%s' % (stare.get('baza') or '')
	return baza if not n else '%s.%d' % (baza, n)


# ---------------------------------------------------------------- receptorul

def _cale(radacina, cale):
	return P._cale(radacina, cale)


def baza_receptorului(radacina='/'):
	"""Imaginea scrisa pe receptor (version= din /etc/hdsatelit-model), '' daca nu se stie"""
	try:
		with open(_cale(radacina, FISIER_MODEL), 'r', encoding='utf-8', errors='replace') as f:
			for rand in f:
				if rand.startswith('version='):
					v = rand.split('=', 1)[1].strip()
					return v if _BAZA.match(v) else ''
	except (IOError, OSError):
		pass
	return ''


def instalate(radacina='/', conf=None):
	"""{nume: versiune} ale pachetelor instalate (status-ul opkg)"""
	conf = conf or P.citeste_configurarea(radacina)
	rez = {}
	for s in P.citeste_strofe(_cale(radacina, conf.status_file)):
		n = s.get('package', '')
		st = s.get('status', '').split()
		if n and 'installed' in st and 'not-installed' not in st:
			rez[n] = s.get('version', '')
	return rez


def versiune_din_pachet(versiune):
	"""Versiunea vazuta de om din versiunea pachetului: 0.3.2+git0+ab-r0 -> 0.3.2 (0.3.0+git0+.. -> 0.3.0, imaginea
	fara actualizari); None cand pachetul nu e facut din git (nu se stie)"""
	v = (versiune or '').split(':', 1)[-1]
	m = re.match(r'^([0-9]{1,3}(?:\.[0-9]{1,3}){2,3})\+git', v)
	return m.group(1) if m else None


def imaginea(radacina='/', conf=None):
	"""{'baza' (imaginea de pe stick), 'versiune' (vazuta de om, None daca nu se stie), 'pachet' (enigma2-hdsatelit)}"""
	baza = baza_receptorului(radacina)
	v = instalate(radacina, conf).get(PACHET_PRINCIPAL, '')
	return {'baza': baza, 'versiune': versiune_din_pachet(v), 'pachet': v}


def baza_pentru_despre(radacina='/'):
	"""Imaginea de baza, pentru randul "Imaginea de bază" din "Despre imagine": numai cand difera de versiunea care
	ruleaza (s-au instalat actualizari prin pachete; versiunea o arata randul "Versiune HD Satelit"); '' altfel"""
	i = imaginea(radacina)
	if not i['baza'] or not i['versiune'] or i['versiune'] == i['baza']:
		return ''
	return i['baza']


def fara_retea(radacina='/'):
	"""True cand receptorul nu are nicio ruta implicita (IPv4 sau IPv6): fara retea sau fara router"""
	try:
		with open(_cale(radacina, '/proc/net/route'), 'r', encoding='utf-8', errors='replace') as f:
			for rand in f.readlines()[1:]:
				c = rand.split()
				if len(c) > 3 and c[1] == '00000000' and int(c[3], 16) & 2:
					return False
	except (IOError, OSError, ValueError):
		pass
	try:
		with open(_cale(radacina, '/proc/net/ipv6_route'), 'r', encoding='utf-8', errors='replace') as f:
			for rand in f:
				c = rand.split()
				if len(c) > 9 and c[0] == '0' * 32 and c[1] == '00' and c[9] != 'lo' and int(c[8], 16) & 2:
					return False
	except (IOError, OSError, ValueError):
		pass
	return True


def opkg_ocupat(radacina='/'):
	"""True cand ruleaza alt opkg (are lacatul lui, lockf pe /var/run/opkg.lock); fara fisier, nimic nu ruleaza"""
	cale = _cale(radacina, LACAT_OPKG)
	if not os.path.exists(cale):
		return False
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


# ---------------------------------------------------------------- sursele si parola

def citeste_netrc(radacina='/'):
	"""(nume, parola) pentru stb.hdsatelit.com din /home/root/.netrc sau /.netrc; None daca lipseste.
	Python-ul imaginii nu are netrc.py: jetoanele se citesc de mana (machine, login, password, default)."""
	for cale in NETRC:
		try:
			with open(_cale(radacina, cale), 'r', encoding='utf-8', errors='replace') as f:
				jetoane = f.read().split()
		except (IOError, OSError):
			continue
		intrari = []
		i = 0
		while i < len(jetoane):
			j = jetoane[i]
			if j == 'default':
				intrari.append({'gazda': '*'})
				i += 1
			elif j in ('machine', 'login', 'password', 'account') and i + 1 < len(jetoane):
				if j == 'machine':
					intrari.append({'gazda': jetoane[i + 1]})
				elif intrari:
					intrari[-1][j] = jetoane[i + 1]
				i += 2
			else:
				i += 1
		for x in intrari:
			if x.get('gazda') == GAZDA_FEED and x.get('login') and x.get('password'):
				return x['login'], x['password']
	return None


def surse_feed(radacina='/', conf=None):
	"""{'proba': [(nume, adresa, arh)], 'public': [...]}: sursele opkg ale feedului HD Satelit, pe canale, numai cu
	adrese de forma https://stb.hdsatelit.com/feed/<canal>/<baza>/<arh>"""
	conf = conf or P.citeste_configurarea(radacina)
	rez = {'proba': [], 'public': []}
	for nume, adresa in conf.surse:
		m = _ADRESA_FEED.match(adresa or '')
		if m:
			rez[m.group(1)].append((nume, adresa, m.group(3), m.group(2)))
	return rez


def canalul(radacina='/', conf=None):
	"""(canal, surse, baza_feedului): canalul de proba cand are surse si parola, altfel cel public, altfel (None, [], '')"""
	s = surse_feed(radacina, conf)
	if s['proba']:
		if citeste_netrc(radacina) is None:
			return 'proba-fara-cheie', s['proba'], s['proba'][0][3]
		return 'proba', s['proba'], s['proba'][0][3]
	if s['public']:
		return 'public', s['public'], s['public'][0][3]
	return None, [], ''


def adresa_stare(canal, baza):
	return '%s/%s/%s/stare.json' % (ADRESA_FEED, canal, baza)


# ---------------------------------------------------------------- stare.json

def valideaza_stare(d):
	"""Lista greselilor (goala = bun); aceleasi reguli ca oe-build/feed_actualizare.verifica_stare"""
	g = []
	if not isinstance(d, dict):
		return ['nu e obiect JSON']
	if d.get('format') != FORMAT:
		g.append('format')
	if not _BAZA.match(u'%s' % d.get('baza', '')):
		g.append('baza')
	n = d.get('actualizare')
	if not isinstance(n, int) or isinstance(n, bool) or n < 0 or n > 999:
		g.append('actualizare')
	if not _BAZA.match(u'%s' % d.get('imagine_minima', '')):
		g.append('imagine_minima')
	if not isinstance(d.get('imagine_noua'), bool):
		g.append('imagine_noua')
	if 'versiune' in d and not _VERSIUNE.match(u'%s' % d.get('versiune')):
		g.append('versiune')
	if not isinstance(d.get('motive'), list) or not all(isinstance(m, str) for m in d.get('motive') or []):
		g.append('motive')
	ce = d.get('ce_e_nou')
	if not isinstance(ce, list) or len(ce) > 40 or not all(isinstance(x, str) and len(x) <= 300 for x in ce):
		g.append('ce_e_nou')
	if 'canal' in d and d.get('canal') not in ('proba', 'public'):
		g.append('canal')
	indexuri = d.get('indexuri')
	if 'indexuri' in d and (not isinstance(indexuri, dict) or not all(isinstance(a, str) and _ARH.match(a) and
			isinstance(x, dict) and _SHA256.match(u'%s' % x.get('sha256', '')) and isinstance(x.get('marime'), int)
			for a, x in indexuri.items())):
		g.append('indexuri')
	pachete = d.get('pachete')
	if not isinstance(pachete, list):
		g.append('pachete')
	else:
		for p in pachete:
			if not isinstance(p, dict) or not P.nume_valid(p.get('nume')) or not isinstance(p.get('versiune'), str):
				g.append('pachete')
				break
	return g


def _cere(adresa, credentiale=None, timp=TIMP_STARE, deschide=None, maxim=MARIME_STARE_MAX, accept='application/json'):
	"""(corp, None) sau (None, (cod, eroare)) pentru o cerere GET de cel mult `maxim` octeti; cod: FARA_CHEIE (401,
	403), FARA_RASPUNS (retea, 5xx) sau EROARE"""
	antete = {'User-Agent': UA, 'Accept': accept, 'Cache-Control': 'no-cache'}
	if credentiale:
		antete['Authorization'] = 'Basic ' + base64.b64encode(('%s:%s' % credentiale).encode('utf-8')).decode('ascii')
	try:
		cerere = Request(adresa, headers=antete)
		r = (deschide or urlopen)(cerere, timeout=timp)
		try:
			corp = r.read(maxim + 1)
		finally:
			try:
				r.close()
			except Exception:
				pass
	except HTTPError as e:
		if e.code in (401, 403):
			return None, (FARA_CHEIE, 'HTTP %d' % e.code)
		return None, (FARA_RASPUNS if e.code >= 500 else EROARE, 'HTTP %d' % e.code)
	except (URLError, socket.timeout, socket.error, OSError, ValueError) as e:
		return None, (FARA_RASPUNS, curata(getattr(e, 'reason', e)))
	if len(corp) > maxim:
		return None, (EROARE, 'prea mare')
	return corp, None


def _semnatura():
	"""Components/HdsSemnatura (cheile de incredere si verificarea); pe PC, modulul din acelasi dosar"""
	try:
		from Components import HdsSemnatura as S
	except ImportError:
		import HdsSemnatura as S
	return S


def descarca_stare(adresa, credentiale=None, timp=TIMP_STARE, deschide=None):
	"""(stare, cod): cod None = bun: stare.json semnat de HD Satelit (stare.json.sig de langa el, verificat pe octetii
	primiti cu cheile din Components/HdsSemnatura.py) si cu forma buna; altfel FARA_RASPUNS, FARA_CHEIE, NESEMNATA sau
	EROARE (cu textul in stare['eroare']). O semnatura care nu se potriveste se cere inca o data, impreuna cu
	stare.json: publicarea se poate schimba intre cele doua cereri. `deschide` (probele) inlocuieste urlopen."""
	S = _semnatura()
	motiv = ''
	for _incercare in range(2):
		corp, problema = _cere(adresa, credentiale, timp, deschide)
		if problema:
			return {'eroare': 'stare.json prea mare' if problema[1] == 'prea mare' else problema[1]}, problema[0]
		semnatura, problema = _cere(adresa + '.sig', credentiale, timp, deschide, MARIME_SEMNATURA_MAX, 'text/plain')
		if problema and problema[1] != 'HTTP 404':
			return {'eroare': '%s: %s' % (NUME_SEMNATURA, problema[1])}, problema[0]
		bun, cod_motiv, ident = S.verifica(corp, semnatura, SCOP_STARE)
		if bun:
			break
		motiv = S.text_motiv(cod_motiv, ident)
		if cod_motiv == S.FARA_VERIFICARE:
			break
	if not bun:
		print('[HdsActualizari] stare.json refuzat: %s' % motiv)
		return {'eroare': motiv}, NESEMNATA
	try:
		d = json.loads(corp.decode('utf-8'))
	except (ValueError, UnicodeDecodeError):
		return {'eroare': 'stare.json nu e JSON'}, EROARE
	g = valideaza_stare(d)
	if g:
		return {'eroare': 'stare.json: %s' % ', '.join(g)}, EROARE
	return d, None


# ---------------------------------------------------------------- "Ce e nou" pe versiuni

def _randuri_bune(randuri):
	return isinstance(randuri, list) and len(randuri) <= MAX_RANDURI_VERSIUNE and \
		all(isinstance(t, str) and len(t) <= MAX_SEMNE_NOUTATE for t in randuri)


def versiuni_stare(stare):
	"""Campul "versiuni" din stare.json, verificat: [{versiune, data, ro, en}], de la cea mai noua versiune; None cand
	lipseste sau nu respecta regulile feedului (oe-build/feed_actualizare.verifica_stare: cel mult MAX_VERSIUNI
	versiuni, fiecare o singura data, mai noua decat baza si nu mai noua decat versiunea lui stare.json, randuri text
	cel mult MAX_RANDURI_VERSIUNE de cel mult MAX_SEMNE_NOUTATE semne). Un camp stricat nu opreste cautarea: atunci se
	arata "ce_e_nou", ca la un feed vechi."""
	brute = stare.get('versiuni') if isinstance(stare, dict) else None
	if not isinstance(brute, list) or len(brute) > MAX_VERSIUNI:
		return None
	baza = u'%s' % (stare.get('baza') or '')
	pe_server = versiunea_starii(stare)
	rez = []
	vazute = set()
	for x in brute:
		if not isinstance(x, dict):
			return None
		v = x.get('versiune')
		if not isinstance(v, str) or not _VERSIUNE.match(v) or v in vazute:
			return None
		if P.compara_versiuni(v, baza) <= 0 or P.compara_versiuni(v, pe_server) > 0:
			return None
		data = x.get('data', '')
		if not isinstance(data, str) or len(data) > MAX_DATA:
			return None
		intrare = {'versiune': v, 'data': data}
		for limba in LIMBI_NOUTATI:
			randuri = x.get(limba, [])
			if not _randuri_bune(randuri):
				return None
			intrare[limba] = [t.strip() for t in randuri if t.strip()]
		vazute.add(v)
		rez.append(intrare)
	rez.sort(key=cmp_to_key(lambda a, b: P.compara_versiuni(b['versiune'], a['versiune'])))
	return rez


def versiuni_noi(stare, instalata):
	"""Versiunile din stare.json mai noi decat cea instalata (toate, cand nu se stie), pana la cea de pe server, de la
	cea mai noua; None cand stare.json nu are noutatile pe versiuni (sau le are stricate)."""
	toate = versiuni_stare(stare)
	if toate is None:
		return None
	pe_server = versiunea_starii(stare)
	return [v for v in toate if P.compara_versiuni(v['versiune'], pe_server) <= 0 and
		(not instalata or P.compara_versiuni(v['versiune'], instalata) > 0)]


def limba_noutati():
	"""'ro' cand interfata e in romana, altfel 'en' (noutatile au textele in cele doua limbi, ca jurnalul versiunilor)"""
	try:
		from Components.Language import language
		return 'ro' if str(language.getLanguage() or '').startswith('ro') else 'en'
	except Exception:
		return 'ro'


def noutati(server, limba=None):
	"""Ce e nou, grupat pe versiuni, pentru ecran si pagina web: [(versiune, [randuri])], de la cea mai noua.
	Din server['versiuni'] (alese la cautare), in limba data (engleza, apoi romana, cand lipseste); fara ele, sau cand
	nu ramane nimic, "ce_e_nou" al versiunii de pe server (feedurile de dinainte)."""
	server = server or {}
	limba = limba or limba_noutati()
	rez = []
	for v in server.get('versiuni') or []:
		randuri = v.get(limba) or v.get('en') or v.get('ro') or []
		if randuri:
			rez.append((v.get('versiune', ''), list(randuri)))
	if not rez and server.get('ce_e_nou'):
		rez = [(server.get('versiune', ''), list(server['ce_e_nou']))]
	return rez


def text_noutati(server, limba=None):
	"""noutati() ca text: "Ce e nou în 0.3.5:", randurile cu buline, un rand gol intre versiuni"""
	return '\n\n'.join(_t('Ce e nou în %s:') % v + '\n' + '\n'.join(u'• %s' % r for r in randuri)
		for v, randuri in noutati(server, limba))


# ---------------------------------------------------------------- planul si verdictul

def _dependinte(text):
	rez = []
	for parte in (text or '').split(','):
		alternative = []
		for alt in parte.split('|'):
			m = re.match(r'^\s*([A-Za-z0-9+.\-]+)\s*(?:\(\s*(<<|<=|>=|>>|=|<|>)\s*([^)\s]+)\s*\))?\s*$', alt)
			if m:
				alternative.append((m.group(1), m.group(2) or '', m.group(3) or ''))
		if alternative:
			rez.append(alternative)
	return rez


def _satisface(versiune, operator, ceruta):
	r = P.compara_versiuni(versiune, ceruta)
	return {'<<': r < 0, '<=': r <= 0, '<': r <= 0, '=': r == 0, '>=': r >= 0, '>': r >= 0, '>>': r > 0}.get(operator, False)


def pachete_din_feed(radacina, surse, conf=None):
	"""{nume: strofa} cu cea mai noua versiune din listele surselor feedului (cele descarcate de opkg update)"""
	conf = conf or P.citeste_configurarea(radacina)
	dosar = _cale(radacina, conf.lists_dir)
	rez = {}
	for nume_sursa, _adresa, _arh, _b in surse:
		for s in P.citeste_strofe(os.path.join(dosar, nume_sursa)):
			n = s.get('package', '')
			if not P.nume_valid(n):
				continue
			arh = s.get('architecture', '')
			if conf.arhitecturi and arh not in conf.arhitecturi:
				continue
			vechi = rez.get(n)
			if vechi is None or P.compara_versiuni(s.get('version', ''), vechi.get('version', '')) > 0:
				rez[n] = s
	return rez


def planul(feed, inst):
	"""Pachetele instalate pentru care feedul are o versiune mai noua: [{nume, titlu, de_la, la, marime, depends}],
	dupa nume. Cele neinstalate (extensii numai in feed) nu intra: se pun din Extensii."""
	rez = []
	for n, s in feed.items():
		if n in inst and P.compara_versiuni(s.get('version', ''), inst[n]) > 0:
			rez.append({'nume': n, 'titlu': P.nume_scurt(n) if n.startswith(P.PREFIX) else n, 'de_la': inst[n],
				'la': s.get('version', ''), 'marime': P._int(s.get('size')), 'depends': s.get('depends', '')})
	rez.sort(key=lambda x: x['nume'])
	return rez


def dependinte_lipsa(plan, inst, feed):
	"""Dependintele planului care nu sunt nici instalate, nici in feed, sau nu au versiunea ceruta: ['nume cere ...']"""
	disponibile = dict(inst)
	for n, s in feed.items():
		if n not in disponibile or P.compara_versiuni(s.get('version', ''), disponibile[n]) > 0:
			disponibile[n] = s.get('version', '')
	for x in plan:
		disponibile[x['nume']] = x['la']
	rez = []
	for x in plan:
		for alternative in _dependinte(x.get('depends')):
			if not any(n in disponibile and (not op or _satisface(disponibile[n], op, v)) for n, op, v in alternative):
				rez.append('%s: %s' % (x['nume'], ' | '.join('%s%s' % (n, ' (%s %s)' % (op, v) if op else '')
					for n, op, v in alternative)))
	return rez


def verdict(stare, baza, plan, lipsa=()):
	"""{'motive': [...], 'detalii': [...], 'imagine_noua': bool, 'poate_instala': bool}"""
	motive = []
	detalii = []

	def adauga(m, detaliu=None):
		if m not in motive:
			motive.append(m)
		if detaliu:
			detalii.append(detaliu)
	if stare.get('baza') != baza:
		adauga('baza', '%s / %s' % (stare.get('baza'), baza))
	elif P.compara_versiuni(stare.get('imagine_minima') or baza, baza) > 0:
		adauga('imagine-minima', stare.get('imagine_minima'))
	if stare.get('imagine_noua'):
		for m in stare.get('motive') or ['alt-motiv']:
			adauga(m if m in TEXT_MOTIV else 'alt-motiv')
		for d in stare.get('detalii') or []:
			detalii.append(u'%s' % d)
	for x in plan:
		m = motiv_imagine_noua(x['nume'])
		if m:
			adauga(m, x['nume'])
	if lipsa:
		adauga('biblioteci')
		detalii.extend(lipsa)
	if len(plan) > PRAG_PACHETE:
		adauga('prea-multe', '%d' % len(plan))
	ordine = [m for m, _t in MOTIVE]
	motive.sort(key=lambda m: ordine.index(m) if m in ordine else len(ordine))
	return {'motive': motive, 'detalii': detalii[:20], 'imagine_noua': bool(motive),
		'poate_instala': bool(plan) and not motive}


def rezultat_cautare(stare, img, plan, lipsa, cand=None):
	"""Rezultatul unei cautari reusite, cum il arata ecranul si pagina web"""
	v = verdict(stare, img['baza'], plan, lipsa)
	if v['imagine_noua']:
		cod = IMAGINE_NOUA
	elif plan:
		cod = DISPONIBILA
	else:
		cod = LA_ZI
	pachete = [{'nume': x['nume'], 'titlu': x['titlu'], 'de_la': x['de_la'], 'la': x['la'], 'marime': x['marime'],
		'de_la_scurt': versiune_scurta(x['de_la']), 'la_scurt': versiune_scurta(x['la'])} for x in plan]
	# planul trebuie sa fie chiar actualizarea din stare.json: altfel listele si stare.json vin din publicari diferite
	din_stare = dict((p.get('nume'), p.get('versiune')) for p in stare.get('pachete') or [])
	nepotrivite = [x['nume'] for x in plan if din_stare.get(x['nume']) != x['la']]
	r = {
		'stare': cod,
		'server': {'baza': stare.get('baza'), 'actualizare': stare.get('actualizare'),
			'versiune': versiunea_starii(stare),
			'data': stare.get('data') or '', 'ce_e_nou': list(stare.get('ce_e_nou') or []),
			# alese acum, fata de versiunea instalata la cautare: dupa instalare ea e deja cea noua, iar "Ce e nou"
			# trebuie sa ramana cel vazut inainte
			'versiuni': versiuni_noi(stare, img.get('versiune')),
			'imagine_recomandata': stare.get('imagine_recomandata') or ''},
		'pachete': pachete,
		'marime': sum(x['marime'] for x in plan),
		'motive': v['motive'],
		'texte_motive': [TEXT_MOTIV.get(m, TEXT_MOTIV['alt-motiv']) for m in v['motive']],
		'detalii': v['detalii'],
		'poate_instala': v['poate_instala'] and not nepotrivite,
		'nepotrivite': nepotrivite,
		'cautat_la': int(cand or time.time()),
	}
	return r


# ---------------------------------------------------------------- semnatura: listele si pachetele

def _sha256_fisier(cale):
	"""(sha256, marime) ale unui fisier; o lista tinuta comprimata de opkg (.gz) se socoteste dezarhivata"""
	h = hashlib.sha256()
	n = 0
	if cale.endswith('.gz'):
		import gzip
		f = gzip.open(cale, 'rb')
	else:
		f = open(cale, 'rb')
	with f:
		while True:
			bucata = f.read(1 << 16)
			if not bucata:
				break
			h.update(bucata)
			n += len(bucata)
	return h.hexdigest(), n


def _lista(dosar, nume):
	"""calea listei descarcate a unei surse (si .gz, cand opkg are compress_list_files), None cand lipseste"""
	for cale in (os.path.join(dosar, nume), os.path.join(dosar, nume + '.gz')):
		if os.path.isfile(cale):
			return cale
	return None


def verifica_listele(radacina, surse, stare, conf=None):
	"""Listele surselor feedului descarcate de `opkg update` (Packages, octet cu octet) fata de "indexuri" din stare.json
	semnat: lista greselilor (goala = bune). Un stare.json fara indexuri sau o sursa fara lista ori fara index semnat e o
	greseala: nimic nesemnat nu ajunge in plan."""
	conf = conf or P.citeste_configurarea(radacina)
	dosar = _cale(radacina, conf.lists_dir)
	indexuri = stare.get('indexuri') if isinstance(stare, dict) else None
	if not isinstance(indexuri, dict):
		return ['stare.json nu are indexurile semnate ale listelor']
	g = []
	for nume, _adresa, arh, _baza in surse:
		x = indexuri.get(arh)
		cale = _lista(dosar, nume)
		if not isinstance(x, dict) or cale is None:
			g.append('lista %s nu are index semnat' % arh)
			continue
		try:
			bun = _sha256_fisier(cale) == (x.get('sha256'), x.get('marime'))
		except (IOError, OSError, EOFError, ValueError):
			bun = False
		if not bun:
			g.append('lista pachetelor %s nu e cea semnata' % arh)
	return g


def sterge_listele(radacina, surse, conf=None):
	"""Sterge listele descarcate ale surselor date (si .gz): pachetele lor nu se mai vad in opkg"""
	conf = conf or P.citeste_configurarea(radacina)
	dosar = _cale(radacina, conf.lists_dir)
	for nume, _a, _arh, _b in surse:
		for cale in (os.path.join(dosar, nume), os.path.join(dosar, nume + '.gz')):
			try:
				os.remove(cale)
			except OSError:
				pass


def tine_minte_indexurile(radacina, canal, baza, stare):
	"""Indexurile din stare.json semnat (canalul, baza, sha256 si marimea fiecarei liste), pentru pazeste_listele"""
	indexuri = stare.get('indexuri') if isinstance(stare, dict) else None
	if canal not in ('proba', 'public') or not _BAZA.match(u'%s' % baza) or not isinstance(indexuri, dict):
		return False
	cale = _cale(radacina, INDEXURI_SEMNATE)
	try:
		with open(cale + '.nou', 'w', encoding='utf-8') as f:
			json.dump({'canal': canal, 'baza': baza, 'actualizare': stare.get('actualizare'), 'indexuri': indexuri}, f,
				sort_keys=True)
		os.replace(cale + '.nou', cale)
	except (IOError, OSError, TypeError, ValueError) as e:
		print('[HdsActualizari] indexurile semnate: %s' % e)
		return False
	return True


def pazeste_listele(radacina='/'):
	"""Dupa un `opkg update` pornit din alta parte (Extensii): listele surselor feedului HD Satelit care nu sunt chiar
	cele din ultima stare.json semnata (tinute minte de tine_minte_indexurile la cautare si la verificarea zilnica) se
	sterg, ca un pachet pus pe server de altcineva sa nu se vada si sa nu se instaleze de acolo. Intoarce numele
	surselor sterse."""
	conf = P.citeste_configurarea(radacina)
	dosar = _cale(radacina, conf.lists_dir)
	try:
		with open(_cale(radacina, INDEXURI_SEMNATE), 'r', encoding='utf-8') as f:
			tinute = json.load(f)
	except (IOError, OSError, ValueError):
		tinute = {}
	if not isinstance(tinute, dict):
		tinute = {}
	sterse = []
	for canal, surse in surse_feed(radacina, conf).items():
		for nume, _a, arh, baza in surse:
			cale = _lista(dosar, nume)
			if cale is None:
				continue
			x = None
			if tinute.get('canal') == canal and tinute.get('baza') == baza and isinstance(tinute.get('indexuri'), dict):
				x = tinute['indexuri'].get(arh)
			try:
				bun = isinstance(x, dict) and _sha256_fisier(cale) == (x.get('sha256'), x.get('marime'))
			except (IOError, OSError, EOFError, ValueError):
				bun = False
			if not bun:
				sterge_listele(radacina, [(nume, '', arh, baza)], conf)
				sterse.append(nume)
	if sterse:
		print('[HdsActualizari] liste HD Satelit nesemnate, sterse: %s' % ', '.join(sterse))
	return sterse


def pachete_semnate(semnat, rezultat):
	"""([{nume, versiune, arhitectura, fisier, marime, sha256}], None) pentru pachetele planului, din stare.json semnat
	al cautarii; (None, motiv) cand unul nu are acolo chiar versiunea din plan, fisierul, marimea si suma."""
	stare = (semnat or {}).get('stare')
	if not isinstance(stare, dict) or stare.get('actualizare') != (rezultat.get('server') or {}).get('actualizare'):
		return None, 'starea semnata a cautarii lipseste'
	din_stare = dict((p.get('nume'), p) for p in stare.get('pachete') or [] if isinstance(p, dict))
	arhitecturi = stare.get('arhitecturi') or []
	rez = []
	for x in rezultat.get('pachete') or []:
		p = din_stare.get(x.get('nume'))
		if not p or p.get('versiune') != x.get('la'):
			return None, 'pachetul %s nu e in stare.json semnat' % x.get('nume')
		fisier, arh, marime, sha = p.get('fisier'), p.get('arhitectura'), p.get('marime'), p.get('sha256')
		if not isinstance(fisier, str) or not _FISIER_IPK.match(fisier) or not isinstance(arh, str) or \
				not _ARH.match(arh) or arh not in arhitecturi or not isinstance(marime, int) or isinstance(marime, bool) or \
				marime <= 0 or not isinstance(sha, str) or not _SHA256.match(sha):
			return None, 'pachetul %s nu are fisierul, marimea sau suma semnate' % x.get('nume')
		rez.append({'nume': x['nume'], 'versiune': p['versiune'], 'arhitectura': arh, 'fisier': fisier, 'marime': marime,
			'sha256': sha})
	if not rez:
		return None, 'niciun pachet de instalat'
	return rez, None


def goleste_dosarul(dosar=None):
	"""sterge dosarul pachetelor descarcate (dupa instalare sau la o greseala)"""
	try:
		shutil.rmtree(dosar or DOSAR_PACHETE)
	except OSError:
		pass


def loc_liber(dosar):
	"""octetii liberi in sistemul de fisiere al dosarului, None cand nu se stie"""
	try:
		s = os.statvfs(dosar)
	except (AttributeError, OSError):
		return None
	return s.f_bavail * s.f_frsize


def descarca_pachete(intrari, adresa_baza, credentiale=None, dosar=None, deschide=None, timp=TIMP_PACHET):
	"""Descarca pachetele (pachete_semnate) in `dosar` (golit intai) si le verifica: (cai, None) sau (None, (fel,
	detaliu)); fel: 'nesemnat' (un pachet nu e chiar cel semnat: alta marime sau alta suma), 'loc' (nu incap) sau
	'descarcare'. Fiecare pachet se scrie in <fisier>.partial, cu sha256 socotit pe drum si cel mult marimea semnata plus
	un octet, si ramane numai daca e chiar cel semnat; la orice greseala dosarul se goleste."""
	dosar = dosar or DOSAR_PACHETE
	goleste_dosarul(dosar)
	try:
		os.makedirs(dosar, 0o700)
	except OSError as e:
		return None, ('descarcare', curata(e))
	nevoie = sum(x['marime'] for x in intrari) + LOC_IN_PLUS
	liber = loc_liber(dosar)
	if liber is not None and liber < nevoie:
		goleste_dosarul(dosar)
		return None, ('loc', '%d MB liberi, trebuie %d MB' % (liber // 1048576, nevoie // 1048576 + 1))
	antete = {'User-Agent': UA, 'Accept': 'application/octet-stream', 'Cache-Control': 'no-cache'}
	if credentiale:
		antete['Authorization'] = 'Basic ' + base64.b64encode(('%s:%s' % credentiale).encode('utf-8')).decode('ascii')
	cai = []
	for x in intrari:
		cale = os.path.join(dosar, x['fisier'])
		h = hashlib.sha256()
		n = 0
		try:
			r = (deschide or urlopen)(Request('%s/%s/%s' % (adresa_baza, x['arhitectura'], x['fisier']), headers=antete),
				timeout=timp)
			try:
				with open(cale + '.partial', 'wb') as f:
					while n <= x['marime']:
						bucata = r.read(min(1 << 16, x['marime'] + 1 - n))
						if not bucata:
							break
						n += len(bucata)
						h.update(bucata)
						f.write(bucata)
			finally:
				try:
					r.close()
				except Exception:
					pass
		except HTTPError as e:
			goleste_dosarul(dosar)
			return None, ('descarcare', '%s: HTTP %d' % (x['fisier'], e.code))
		except (URLError, socket.timeout, socket.error, OSError, ValueError) as e:
			goleste_dosarul(dosar)
			return None, ('descarcare', '%s: %s' % (x['fisier'], curata(getattr(e, 'reason', e))))
		if n != x['marime'] or h.hexdigest() != x['sha256']:
			goleste_dosarul(dosar)
			return None, ('nesemnat', 'pachetul %s nu e cel semnat (%s)' % (x['nume'], 'alta marime' if n != x['marime']
				else 'alta suma'))
		os.replace(cale + '.partial', cale)
		cai.append(cale)
	return cai, None


def argumente_instalare(cai, dosar=None):
	"""Argumentele opkg pentru pachetele verificate (install <cale>...), primite numai din dosarul lor: pe receptor /tmp
	e o legatura spre /var/volatile/tmp, iar radacinile implicite din Components/Ipkg.py n-ar primi calea reala. None
	cand o cale e refuzata."""
	from Components.Ipkg import opkgArguments
	radacina = os.path.join(os.path.realpath(dosar or DOSAR_PACHETE), '')
	return opkgArguments('install', list(cai), (), (radacina,))


# ---------------------------------------------------------------- config

def config_actualizari():
	"""config.hds_actualizari: zilnic (verificarea zilnica, pornita din fabrica) si anuntat (ce s-a anuntat deja)"""
	from Components.config import config, ConfigSubsection, ConfigYesNo, ConfigText
	# nu hasattr(config, ...): Config.__getattr__ din enigma2 arunca KeyError, nu AttributeError, iar hasattr din
	# Python 3 prinde numai AttributeError (gasit in emulator la integrarea 0.3.0.2); ca HdsAfisaj si HdsCalitateImagine
	if 'hds_actualizari' not in config.content.items:
		config.hds_actualizari = ConfigSubsection()
		config.hds_actualizari.zilnic = ConfigYesNo(default=True)
		config.hds_actualizari.anuntat = ConfigText(default='', fixed_size=False)
	return config.hds_actualizari


def zilnic_pornit():
	try:
		return bool(config_actualizari().zilnic.value)
	except Exception:
		return True


def seteaza_zilnic(pornit):
	c = config_actualizari()
	c.zilnic.value = bool(pornit)
	c.zilnic.save()
	try:
		from Components.config import configfile
		configfile.save()
	except Exception:
		pass
	return bool(c.zilnic.value)


# ---------------------------------------------------------------- lucrarea (o singura data, pentru ecran si web)

class Actualizari(object):
	"""Starea comuna a ecranului si a paginii web. Toate metodele ruleaza pe firul enigma2; citirile de retea si de
	fisiere merg pe fire separate (HdsPazaModel.LucrareFundal), opkg prin Components/Ipkg.py (lista de argumente)."""

	def __init__(self, radacina='/'):
		self.radacina = radacina
		self.faza = 'liber'          # liber | caut | instalez
		self.pas = ''
		self.progres = (0, 0)
		self.rezultat = {'stare': NECAUTAT}
		self.mesaj = ''
		self.jurnal = []
		self.repornire = False
		self.canal = None
		self.ascultatori = []
		self._lucrari = []
		self._ipkg = None
		self._lista_ipkg = []
		self._de_instalat = []
		# stare.json semnat al ultimei cautari (pachetele se verifica cu el la instalare),
		# adresa lui si baza feedului
		self._semnat = None
		self._adresa = ''
		self._baza_feed = ''
		# actualizarea rapida: rapid cat merge (de la apasare pana cade interfata, sau pana se opreste), rapid_pas unde
		# a ajuns (caut, instalez, repornesc, inregistrare, lucrare, intrebare, refuzata); ramane dupa oprire, ca
		# pagina sa vada unde
		self.rapid = False
		self.rapid_pas = ''
		self._reporneste_rapid = None
		self._ceas_rapid = None
		self._legatura_rapid = None
		self.fabrica_ceas = None        # eTimer; probele de pe PC dau altul

	# ---- ascultatorii (ecranul si pagina web se reimprospateaza singure)
	def _schimbat(self):
		for f in self.ascultatori[:]:
			try:
				f()
			except Exception as e:
				print('[HdsActualizari] ascultator: %s' % e)

	def _jurnal(self, rand):
		rand = curata(rand)
		self.jurnal.append(rand)
		del self.jurnal[:-RANDURI_JURNAL]
		try:
			with open(JURNAL, 'a', encoding='utf-8', errors='replace') as f:
				f.write('%s %s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), rand))
		except (IOError, OSError):
			pass

	def ocupat(self):
		return self.faza != 'liber'

	def poate_porni(self):
		"""('' daca se poate porni o cautare sau o instalare, altfel textul de ce nu)"""
		if self.repornire:
			return _t('Actualizarea s-a instalat. Repornește interfața înainte de altceva.')
		if self.faza != 'liber':
			return _t('Așteaptă să se termine operația de acum.')
		if opkg_ocupat(self.radacina):
			return _t('Alt program instalează sau descarcă pachete acum. Încearcă după ce termină.')
		from Components.Ipkg import opkgProgram
		if not opkgProgram():
			return _t('Instalarea pachetelor nu este disponibilă în această imagine.')
		return ''

	def _lucrare(self, functie, gata):
		from Components.HdsPazaModel import LucrareFundal
		pastrata = []

		def la_sfarsit(rez, eroare):
			for x in pastrata:
				if x in self._lucrari:
					self._lucrari.remove(x)
			gata(rez, eroare)
		lucrare = LucrareFundal(functie, la_sfarsit)
		pastrata.append(lucrare)
		self._lucrari.append(lucrare)

	# ---- cautarea
	def cauta(self):
		motiv = self.poate_porni()
		if motiv:
			self.mesaj = motiv
			self._schimbat()
			return False
		self.mesaj = ''
		canal, surse, baza_feed = canalul(self.radacina)
		self.canal = canal
		img = imaginea(self.radacina)
		if canal is None:
			self.rezultat = {'stare': FARA_SURSA}
			self._schimbat()
			return False
		if canal == 'proba-fara-cheie':
			self.rezultat = {'stare': FARA_CHEIE}
			self._schimbat()
			return False
		self.faza, self.pas, self.progres = 'caut', _t('Se citește starea actualizărilor de pe server...'), (1, 3)
		self._schimbat()
		credentiale = citeste_netrc(self.radacina) if canal == 'proba' else None
		adresa = adresa_stare(canal, baza_feed or img['baza'])
		self._semnat, self._adresa, self._baza_feed = None, adresa, baza_feed or img['baza']
		radacina = self.radacina

		def citeste():
			return descarca_stare(adresa, credentiale), fara_retea(radacina)

		def gata(rez, eroare):
			if eroare or rez is None:
				return self._cautare_gata({'stare': EROARE, 'eroare': curata(eroare)})
			(stare, cod), fara = rez
			if cod == FARA_RASPUNS and fara:
				return self._cautare_gata({'stare': FARA_RETEA})
			if cod:
				return self._cautare_gata({'stare': cod, 'eroare': curata(stare.get('eroare'))})
			# semnat, dar pentru alt canal (de pilda o publicare de proba data receptoarelor de pe canalul public)
			if stare.get('canal') and stare.get('canal') != canal:
				return self._cautare_gata({'stare': NESEMNATA, 'eroare': 'stare.json e al canalului %s, nu %s' % (
					curata(stare.get('canal')), canal)})
			self._opkg_update(stare, surse)
		self._lucrare(citeste, gata)
		return True

	def _opkg_update(self, stare, surse):
		from Components.Ipkg import IpkgComponent
		self.pas, self.progres = _t('Se descarcă lista pachetelor (opkg update)...'), (2, 3)
		self._schimbat()
		self._lista_ipkg = []
		ipkg = self._ipkg = IpkgComponent()
		inceput = time.time()

		def eveniment(e, param):
			if e == IpkgComponent.EVENT_LINE:
				self._lista_ipkg.append(curata(param))
				self._jurnal(param)
			elif e == IpkgComponent.EVENT_DONE:
				ipkg.removeCallback(eveniment)
				self._ipkg = None
				self._dupa_update(stare, surse, param, inceput)
		ipkg.addCallback(eveniment)
		self._jurnal('opkg update')
		ipkg.startCmd(IpkgComponent.CMD_UPDATE)

	def _dupa_update(self, stare, surse, cod, inceput):
		# opkg update da cod 255 si cand cade numai o sursa a utilizatorului: conteaza listele feedului nostru
		conf = P.citeste_configurarea(self.radacina)
		dosar = _cale(self.radacina, conf.lists_dir)
		proaspete = []
		for nume, _a, _arh, _b in surse:
			try:
				proaspete.append(os.path.getmtime(os.path.join(dosar, nume)) >= inceput - 2)
			except OSError:
				proaspete.append(False)
		if not proaspete or not all(proaspete):
			motiv = motiv_eroare(self._lista_ipkg, implicit=_t('Lista pachetelor nu s-a putut descărca.'))
			return self._cautare_gata({'stare': EROARE if not fara_retea(self.radacina) else FARA_RETEA,
				'eroare': curata(motiv)})
		self.pas, self.progres = _t('Se compară pachetele...'), (3, 3)
		self._schimbat()
		radacina = self.radacina
		canal, adresa, baza = self.canal, self._adresa, self._baza_feed

		def calculeaza():
			c = P.citeste_configurarea(radacina)
			semnata = stare
			# listele descarcate de opkg trebuie sa fie chiar cele din stare.json semnat (indexuri)
			g = verifica_listele(radacina, surse, semnata, c)
			if g:
				# publicarea s-a putut schimba intre stare.json si opkg update: stare.json (semnat) se cere inca o data
				noua, cod = descarca_stare(adresa, citeste_netrc(radacina) if canal == 'proba' else None)
				if cod is None and noua.get('canal') in (None, canal) and not verifica_listele(radacina, surse, noua, c):
					semnata, g = noua, []
			if g:
				sterge_listele(radacina, surse, c)
				return {'stare': NESEMNATA, 'eroare': curata('; '.join(g[:3]))}, None
			tine_minte_indexurile(radacina, canal, baza, semnata)
			inst = instalate(radacina, c)
			img = imaginea(radacina, c)
			feed = pachete_din_feed(radacina, surse, c)
			plan = planul(feed, inst)
			return rezultat_cautare(semnata, img, plan, dependinte_lipsa(plan, inst, feed)), semnata

		def gata(rez, eroare):
			if rez and not eroare:
				rezultat, semnata = rez
				self._semnat = {'stare': semnata} if semnata is not None else None
				return self._cautare_gata(rezultat)
			self._cautare_gata({'stare': EROARE, 'eroare': curata(eroare)})
		self._lucrare(calculeaza, gata)

	def _cautare_gata(self, rezultat):
		rezultat.setdefault('cautat_la', int(time.time()))
		self.rezultat = rezultat
		self.faza, self.pas, self.progres = 'liber', '', (0, 0)
		self._jurnal('cautare: %s' % rezultat.get('stare'))
		self._schimbat()
		if self.rapid:
			self._rapid_dupa_cautare(rezultat)

	# ---- instalarea
	def instaleaza(self, actualizare=None):
		"""Instaleaza planul cautarii: pachetele se descarca si se verifica aici (marimea si sha256 din stare.json semnat,
		descarca_pachete), apoi `opkg install <fisier>`. `actualizare` (numarul intern al publicarii, trimis de pagina
		web odata cu versiunea pe care o arata) trebuie sa fie cel din rezultat, ca o pagina veche din browser sa nu
		instaleze altceva decat a vazut."""
		motiv = self.poate_porni()
		r = self.rezultat
		if not motiv and not r.get('poate_instala'):
			motiv = _t('Nu este nimic de instalat sau actualizarea nu se poate instala din meniu.')
		if not motiv and actualizare is not None and actualizare != (r.get('server') or {}).get('actualizare'):
			motiv = _t('Starea s-a schimbat între timp. Caută din nou.')
		nume = [p['nume'] for p in r.get('pachete') or [] if P.nume_valid(p['nume'])]
		from Components.Ipkg import opkgArguments
		if not motiv and (not nume or opkgArguments('upgrade', nume) is None):
			motiv = _t('Un nume de pachet nu este valid. Nu se instalează.')
		if motiv:
			self.mesaj = motiv
			self._schimbat()
			return False
		intrari, problema = pachete_semnate(self._semnat, r)
		if problema:
			self._jurnal('instalare refuzata: %s' % problema)
			self.mesaj = ''
			self.rezultat = dict(r, stare=NESEMNATA, poate_instala=False, eroare=curata(problema))
			self._schimbat()
			return False
		self.mesaj = ''
		self._de_instalat = list(r.get('pachete') or [])
		self.faza, self.pas, self.progres = 'instalez', _t('Se descarcă și se verifică pachetele...'), (0, len(nume))
		self._lista_ipkg = []
		self._schimbat()
		canal = self.canal
		credentiale = citeste_netrc(self.radacina) if canal == 'proba' else None
		adresa = '%s/%s/%s' % (ADRESA_FEED, canal, self._baza_feed)
		self._jurnal('descarc si verific: %s' % ' '.join('%s %s' % (x['nume'], x['versiune']) for x in intrari))

		def descarca():
			return descarca_pachete(intrari, adresa, credentiale)

		def gata(rez, eroare):
			cai, problema = rez if rez and not eroare else (None, ('descarcare', curata(eroare)))
			if problema:
				return self._descarcare_cazuta(problema, nume)
			self._porneste_opkg(cai, nume)
		self._lucrare(descarca, gata)
		return True

	def _descarcare_cazuta(self, problema, nume):
		"""Pachetele nu ajung la opkg: unul nu e cel semnat (NESEMNATA), nu incap sau nu s-au descarcat"""
		fel, detaliu = problema
		goleste_dosarul()
		self._jurnal('pachetele nu se instaleaza (%s): %s' % (fel, detaliu))
		self.faza, self.pas, self.progres = 'liber', '', (0, 0)
		if fel == 'nesemnat':
			self.mesaj = ''
			self.rezultat = dict(self.rezultat, stare=NESEMNATA, poate_instala=False, eroare=curata(detaliu))
		else:
			motiv = _t('Nu mai este loc în memoria receptorului.') if fel == 'loc' else \
				_t('Un fișier nu s-a putut descărca de pe server.')
			self.rezultat = dict(self.rezultat, stare='eroare-instalare', poate_instala=False, ramase=list(nume))
			self.mesaj = _t('Instalarea s-a oprit cu eroare: %s. Jurnalul: %s') % (curata(motiv), JURNAL)
		self._sfarsit_rapid('pachetele nu s-au instalat (%s)' % fel)
		self._schimbat()

	def _porneste_opkg(self, cai, nume):
		"""opkg install pe pachetele verificate (fisierele din DOSAR_PACHETE)"""
		from Components.Ipkg import IpkgComponent
		argumente = argumente_instalare(cai)
		if argumente is None:
			return self._descarcare_cazuta(('descarcare', 'opkg nu primeste pachetele descarcate'), nume)
		self.pas = _t('Se pregătește instalarea...')
		self._schimbat()
		ipkg = self._ipkg = IpkgComponent()
		facute = set()

		def eveniment(e, param):
			if e == IpkgComponent.EVENT_LINE:
				self._lista_ipkg.append(curata(param))
				self._jurnal(param)
				_fel, text = P.linie_jurnal(curata(param))
				if text:
					self.pas = curata(text)
				m = re.match(r'^(?:Upgrading|Installing|Configuring) (\S+?)\.?(?:\s|$)', param or '')
				if m and m.group(1) in nume and param.startswith('Configuring'):
					facute.add(m.group(1))
				self.progres = (len(facute), len(nume))
				self._schimbat()
			elif e == IpkgComponent.EVENT_DONE:
				ipkg.removeCallback(eveniment)
				self._ipkg = None
				self._dupa_instalare(param)
		ipkg.addCallback(eveniment)
		self._jurnal('opkg %s' % ' '.join(argumente))
		ipkg.setCurrentCommand(IpkgComponent.CMD_INSTALL)
		ipkg.runCmd(argumente)

	def _dupa_instalare(self, cod):
		radacina = self.radacina
		planificate = self._de_instalat

		def verifica():
			inst = instalate(radacina)
			return [p['nume'] for p in planificate if inst.get(p['nume']) != p['la']]

		def gata(ramase, eroare):
			goleste_dosarul()
			schimbat = len(ramase or []) < len(planificate)
			self.faza, self.progres = 'liber', (0, 0)
			if eroare is None and cod == 0 and not ramase:
				self.pas = ''
				self.repornire = True
				self.rezultat = dict(self.rezultat, stare='instalata', poate_instala=False)
				self.mesaj = _t('Actualizarea s-a instalat. Interfața trebuie repornită ca să o folosească.')
			else:
				motiv = motiv_eroare(self._lista_ipkg, implicit=_t('Instalarea nu a reușit.'))
				self.pas = ''
				# fisierele unor pachete s-au schimbat: interfata trebuie repornita oricum, inainte de alta operatie
				self.repornire = schimbat
				self.rezultat = dict(self.rezultat, stare='eroare-instalare', poate_instala=False,
					ramase=list(ramase or []))
				self.mesaj = _t('Instalarea s-a oprit cu eroare: %s. Jurnalul: %s') % (curata(motiv), JURNAL)
			self._jurnal('instalare: cod %s, ramase %s' % (cod, ramase))
			if self.rapid:
				# numai dupa o instalare reusita; una cazuta (chiar cu repornirea ceruta) opreste modul rapid
				if self.rezultat.get('stare') == 'instalata':
					self.rapid_pas = 'repornesc'
					self.mesaj = _t('Actualizarea s-a instalat. Interfața se repornește acum.')
					self._programeaza_repornirea(REPORNIRE_RAPIDA_MS)
				else:
					self._sfarsit_rapid('instalare: %s' % self.rezultat.get('stare'))
			self._schimbat()
		self._lucrare(verifica, gata)

	# ---- actualizarea rapida (pagina web: butonul de actualizare rapida)
	def actualizeazaRapid(self, reporneste):
		"""Cauta; daca e o actualizare de instalat, o instaleaza (numarul publicarii gasite de cautare) si reporneste
		interfata cu reporneste(la_refuz), totul aici. reporneste intoarce 'pornita' (TryQuitMainloop deschis; la_refuz()
		e chemat daca nu reporneste, adica pe televizor s-a raspuns Nu), 'inregistrare', 'lucrare' sau 'intrebare'
		(repornirea ar intreba pe televizor: se incearca din nou la REINCERCARE_RAPIDA_MS) sau '' (nu se poate). False,
		cu mesajul, cand nu porneste: alta operatie in lucru, o actualizare instalata care asteapta repornirea, modul
		rapid deja pornit."""
		if self.rapid:
			self.mesaj = _t('Actualizarea rapidă este deja în lucru.')
			self._schimbat()
			return False
		self.rapid, self.rapid_pas, self._reporneste_rapid = True, 'caut', reporneste
		self._jurnal('actualizare rapida: caut')
		# cu lucrarile sincrone ale probelor, tot drumul se poate termina inainte sa se intoarca cauta(): dupa ea nu
		# se mai schimba nimic aici
		if not self.cauta():
			self._sfarsit_rapid('cautarea nu a pornit')
			self._schimbat()
			return False
		return True

	def _rapid_dupa_cautare(self, rezultat):
		if rezultat.get('stare') != DISPONIBILA or not rezultat.get('poate_instala'):
			self._sfarsit_rapid('cautare: %s' % rezultat.get('stare'))
			self._schimbat()
			return
		self.rapid_pas = 'instalez'
		if not self.instaleaza((rezultat.get('server') or {}).get('actualizare')):
			self._sfarsit_rapid('instalarea nu a pornit')
			self._schimbat()

	def _sfarsit_rapid(self, motiv):
		"""Modul rapid se opreste, fara repornire; rapid_pas ramane"""
		if self.rapid:
			self._jurnal('actualizare rapida oprita: %s' % motiv)
		self.rapid, self._reporneste_rapid = False, None
		if self._ceas_rapid is not None:
			self._ceas_rapid.stop()

	def _programeaza_repornirea(self, ms):
		"""Un singur ceas pentru repornire, pastrat aici (pornit din nou si din chemarea lui)"""
		if self._ceas_rapid is None:
			fabrica = self.fabrica_ceas
			if fabrica is None:
				from enigma import eTimer as fabrica
			t = fabrica()
			try:
				self._legatura_rapid = t.timeout.connect(self._incearca_repornirea)
			except AttributeError:
				t.callback.append(self._incearca_repornirea)
			self._ceas_rapid = t
		self._ceas_rapid.stop()
		self._ceas_rapid.start(int(ms), True)

	def _incearca_repornirea(self):
		if not self.rapid:
			return
		f = self._reporneste_rapid
		try:
			rez = f(self._repornire_refuzata) if f is not None else ''
		except Exception as e:
			print('[HdsActualizari] repornirea rapida: %s' % e)
			rez = ''
		if rez == 'pornita':
			self.rapid_pas = 'repornesc'
			self.mesaj = _t('Actualizarea s-a instalat. Interfața se repornește acum.')
			try:
				# cu memoria decodorului farmitata repornirea a fost a receptorului intreg (HdsMemorieDriver)
				from Components import HdsMemorieDriver
				if HdsMemorieDriver.ultimulCod() == HdsMemorieDriver.COD_RECEPTOR:
					self.mesaj = HdsMemorieDriver.textRepornire(HdsMemorieDriver.COD_RECEPTOR)
			except Exception:
				pass
			self._jurnal('actualizare rapida: repornesc interfata')
		elif rez in TEXTE_ASTEPTARE:
			if rez != self.rapid_pas:
				self._jurnal('actualizare rapida: repornirea asteapta (%s)' % rez)
			self.rapid_pas = rez
			self.mesaj = _t(TEXTE_ASTEPTARE[rez])
			self._programeaza_repornirea(REINCERCARE_RAPIDA_MS)
		else:
			self._sfarsit_rapid('repornirea nu s-a putut porni')
			self.mesaj = _t('Actualizarea s-a instalat. Interfața trebuie repornită ca să o folosească.')
		self._schimbat()

	def _repornire_refuzata(self, *_a):
		"""TryQuitMainloop s-a inchis fara repornire: pe televizor s-a raspuns Nu"""
		if not self.rapid:
			return
		self._sfarsit_rapid('repornirea refuzata pe televizor')
		self.rapid_pas = 'refuzata'
		self.mesaj = _t('Repornirea a fost refuzată pe televizor. Actualizarea se folosește după ce repornești interfața.')
		self._schimbat()

	# ---- pentru ecran si web
	def stare_publica(self):
		"""Starea ca dict JSON (pagina web si probele): fara adrese, fara parole"""
		img = imaginea(self.radacina)
		return {
			'faza': self.faza,
			'pas': self.pas,
			'progres': list(self.progres),
			'canal': self.canal if self.canal else canalul(self.radacina)[0],
			'imagine': img,
			'imagine_text': img['versiune'] or img['baza'] or '',
			'rezultat': self.rezultat,
			'text_stare': _t(TEXTE_STARE.get(self.rezultat.get('stare'), '')) if self.rezultat.get('stare') in
				TEXTE_STARE else '',
			'mesaj': self.mesaj,
			'repornire': self.repornire,
			'rapid': self.rapid,
			'rapid_pas': self.rapid_pas,
			'zilnic': zilnic_pornit(),
			'jurnal': self.jurnal[-30:],
		}


actualizari = Actualizari()


# ---------------------------------------------------------------- verificarea zilnica (numai anunta)

def text_anunt(stare, img):
	"""Textul anuntului zilnic, sau None cand nu e nimic nou de spus; cheia lui (anuntat o singura data). O versiune
	e noua cand e mai mare (ca la opkg) decat versiunea care ruleaza."""
	if stare.get('baza') != img['baza'] or not img['versiune']:
		return None, None
	v = versiunea_starii(stare)
	if stare.get('imagine_noua'):
		cheie = '%s/%s/imagine' % (stare['baza'], v)
		return _t('Actualizare software: pentru noutățile HD Satelit trebuie pusă imaginea nouă de la zero. Detalii '
			'în Actualizare software.'), cheie
	if P.compara_versiuni(v, img['versiune']) > 0:
		cheie = '%s/%s' % (stare['baza'], v)
		return _t('Actualizare software: este disponibilă versiunea %s. O instalezi din Actualizare software.') % v, cheie
	return None, None


class VerificareZilnica(object):
	"""La 5 minute dupa pornire si apoi o data pe zi: stare.json al canalului; un anunt pentru fiecare actualizare
	noua (o singura data). Nu porneste opkg si nu instaleaza nimic."""

	def __init__(self, radacina='/'):
		from enigma import eTimer
		self.radacina = radacina
		self.ceas = eTimer()
		try:
			self._legatura = self.ceas.timeout.connect(self.verifica)
		except AttributeError:
			self.ceas.callback.append(self.verifica)
		self._lucrare = None

	def porneste(self, intarziere=PRIMA_VERIFICARE):
		self.ceas.startLongTimer(int(intarziere))

	def verifica(self):
		self.ceas.stop()
		if not zilnic_pornit():
			return self.porneste(ZI)
		canal, _surse, baza_feed = canalul(self.radacina)
		if canal not in ('proba', 'public'):
			return self.porneste(ZI)
		img = imaginea(self.radacina)
		credentiale = citeste_netrc(self.radacina) if canal == 'proba' else None
		adresa = adresa_stare(canal, baza_feed or img['baza'])
		from Components.HdsPazaModel import LucrareFundal

		def gata(rez, eroare):
			self._lucrare = None
			stare, cod = rez if rez and not eroare else ({}, EROARE)
			if not cod and stare.get('canal') and stare.get('canal') != canal:
				stare, cod = {'eroare': 'stare.json e al canalului %s' % curata(stare.get('canal'))}, NESEMNATA
			if cod:
				print('[HdsActualizari] verificarea zilnica: %s' % (curata(stare.get('eroare')) or cod))
				return self.porneste(REINCERCARE)
			tine_minte_indexurile(self.radacina, canal, baza_feed or img['baza'], stare)
			text, cheie = text_anunt(stare, img)
			c = config_actualizari()
			if text and cheie != c.anuntat.value:
				c.anuntat.value = cheie
				c.anuntat.save()
				try:
					from Tools import Notifications
					from Screens.MessageBox import MessageBox
					Notifications.AddPopup(text, MessageBox.TYPE_INFO, 20, 'HdsActualizari')
				except Exception as e:
					print('[HdsActualizari] anuntul: %s' % e)
			self.porneste(ZI)
		self._lucrare = LucrareFundal(lambda: descarca_stare(adresa, credentiale), gata)


_verificare = []


def porneste():
	"""Din mytest.py, dupa ce s-a facut sesiunea: config-ul si verificarea zilnica. Pornirea nu depinde de el."""
	config_actualizari()
	if not _verificare:
		v = VerificareZilnica()
		_verificare.append(v)
		v.porneste()
