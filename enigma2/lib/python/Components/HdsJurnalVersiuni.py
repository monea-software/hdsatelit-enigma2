# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Jurnalul de versiuni al imaginii HD Satelit: ce s-a schimbat de la o versiune la alta, scris pe intelesul
utilizatorului.

Datele stau intr-un singur fisier, instalat langa restul datelor imaginii:
  /usr/share/enigma2/jurnal-versiuni.json   (in depozit: data/jurnal-versiuni.json)
Forma lui:
  {"versiuni": [{"versiune": "0.2.0", "build": "0010202609241212", "data": "24.09.2026",
    "intrari": [{"fel": "nou|reparat|imbunatatit", "ro": "text", "en": "text"}]}]}
Lista e de la cea mai noua versiune la cea mai veche. „build" e chiar randul version= din /etc/image-version al
acelui build (Makefile.am), in una din doua forme:
  16 cifre  fiecare parte a versiunii are o cifra (0.3.9): 0 + XYZ + AAAALLZZhhmm, de pilda 0039202610121200;
  19 cifre  o parte are doua cifre (0.3.10): 0 + XX + YY + ZZ + AAAALLZZhhmm, de pilda 0000310202610131200.
Prima cifra e felul (0 versiune, 1 de incercare). Doua build-uri se compara prin cheie_build() (felul, x, y, z,
data), nu ca siruri: intre doua build-uri de 16 cifre ordinea e aceeasi ca a sirurilor, iar 0.3.9 < 0.3.10.

Modulul e singura sursa pentru ecranul din interfata si pentru interfata web. Nu scrie nimic in fisier si nu arunca
exceptii spre ecran: un fisier lipsa, gol sau stricat inseamna liste goale. Nu importa nimic din enigma la
incarcare, ca sa poata fi incercat si pe PC (teste/test_jurnal_versiuni.py); config-ul se atinge numai prin
ultima_vazuta() si retine_vazuta(), care il importa abia la apel."""
import io
import json
import os

FISIER = 'jurnal-versiuni.json'
IMAGE_VERSION = '/etc/image-version'
# cat de lung e un build (version= din Makefile.am): 0<major><minor><revizie><AAAALLZZhhmm> cu o cifra pe parte, si
# forma cu doua cifre pe fiecare parte, cand una din ele trece de 9 (0.3.10)
LUNGIME_BUILD = 16
LUNGIME_BUILD_LUNG = 19
# felurile de intrari, in ordinea in care se arata pe ecran
FELURI = ('nou', 'reparat', 'imbunatatit')


def N_(text):
	"""Marcheaza un text pentru xgettext (--keyword=N_) fara sa-l traduca acum."""
	return text


# numele felurilor: romana si engleza (pagina web, probele); pe televizor numele romanesc trece prin traducere
# (eticheta_tradusa), ca sa fie in limba interfetei
ETICHETE = {
	'nou': (N_('Nou'), 'New'),
	'reparat': (N_('Reparat'), 'Fixed'),
	'imbunatatit': (N_('Îmbunătățit'), 'Improved'),
}
# cheia din config in care ecranul tine ultima versiune vazuta de utilizator (build-ul, nu numele versiunii)
CHEIE_CONFIG = 'config.hdsatelit.jurnal.ultimaVazuta'


def _cale_implicita():
	"""Unde se cauta fisierul: intai locul din imagine, apoi dosarul data/ al depozitului (PC si emulator)."""
	cai = []
	try:
		from Tools.Directories import resolveFilename, SCOPE_SKIN
		cai.append(resolveFilename(SCOPE_SKIN, FISIER))
	except Exception:
		cai.append(os.path.join('/usr/share/enigma2', FISIER))
	aici = os.path.dirname(os.path.abspath(__file__))
	cai.append(os.path.normpath(os.path.join(aici, '..', '..', '..', 'data', FISIER)))
	for c in cai:
		if c and os.path.exists(c):
			return c
	return cai[0]


def desparte_build(build):
	"""(fel, x, y, z, data) dintr-un build de 16 sau 19 cifre (vezi sus): numerele ca int, data ca sir de 12 cifre.
	None pentru orice alta forma (si pentru 17 cifre, ca imaginea veche 0.1.10: 0.1.10 sau 0.11.0 nu se poate
	spune)."""
	if not isinstance(build, str) or not build.isdigit() or not build.isascii():
		return None
	if len(build) == LUNGIME_BUILD:
		return int(build[0]), int(build[1]), int(build[2]), int(build[3]), build[4:]
	if len(build) == LUNGIME_BUILD_LUNG:
		return int(build[0]), int(build[1:3]), int(build[3:5]), int(build[5:7]), build[7:]
	return None


def build_bun(build):
	"""True daca build-ul are una din cele doua forme"""
	return desparte_build(build) is not None


def cheie_build(build):
	"""Cheia de ordine a unui build: (felul, x, y, z, data). Un build stricat sau gol are cheia cea mai mica."""
	d = desparte_build(build)
	return d if d is not None else (-1,)


def versiune_din_build(build):
	"""Versiunea scrisa "0.3.10" dintr-un build; sir gol pentru un build de incercare sau stricat."""
	d = desparte_build(build)
	if d is None or d[0] != 0:
		return ''
	return '%d.%d.%d' % d[1:4]


def build_curent(cale=None):
	"""Build-ul care ruleaza acum, citit din /etc/image-version. Sir gol daca fisierul lipseste sau randul
	version= nu are una din cele doua forme (16 sau 19 cifre)."""
	cale = cale or IMAGE_VERSION
	try:
		with io.open(cale, 'r', encoding='utf-8', errors='replace') as f:
			text = f.read(4096)
	except Exception:
		return ''
	for rand in text.splitlines():
		if not rand.startswith('version'):
			continue
		cheie, _semn, valoare = rand.partition('=')
		if cheie.strip() != 'version':
			continue
		valoare = valoare.strip()
		return valoare if build_bun(valoare) else ''
	return ''


def _intrare_buna(x):
	if not isinstance(x, dict):
		return False
	if x.get('fel') not in FELURI:
		return False
	for cheie in ('ro', 'en'):
		v = x.get(cheie)
		if not isinstance(v, str) or not v.strip():
			return False
	return True


def _versiune_buna(v):
	if not isinstance(v, dict):
		return False
	if not build_bun(v.get('build')):
		return False
	if not isinstance(v.get('versiune'), str) or not v.get('versiune'):
		return False
	if not isinstance(v.get('intrari'), list):
		return False
	return True


def versiuni(cale=None):
	"""Lista versiunilor, de la cea mai noua la cea mai veche. Lista goala daca fisierul lipseste sau e stricat.
	Versiunile si intrarile carora le lipseste ceva sunt sarite, restul raman."""
	cale = cale or _cale_implicita()
	try:
		with io.open(cale, 'r', encoding='utf-8') as f:
			date = json.load(f)
	except Exception:
		return []
	if not isinstance(date, dict):
		return []
	brute = date.get('versiuni')
	if not isinstance(brute, list):
		return []
	rez = []
	for v in brute:
		if not _versiune_buna(v):
			continue
		rez.append({
			'versiune': v['versiune'],
			'build': v['build'],
			'data': v.get('data') if isinstance(v.get('data'), str) else '',
			'intrari': [
				{'fel': x['fel'], 'ro': x['ro'], 'en': x['en']}
				for x in v['intrari'] if _intrare_buna(x)
			],
		})
	# ordinea din fisier e deja de la nou la vechi; o asiguram, ca lista sa nu depinda de cine scrie fisierul
	rez.sort(key=lambda v: cheie_build(v['build']), reverse=True)
	return rez


def versiunea_care_ruleaza(lista=None, curent=None):
	"""Versiunea instalata acum: cea mai noua din lista al carei build nu e mai nou decat cel care ruleaza.
	None daca nu se stie build-ul sau daca lista nu are nicio versiune potrivita."""
	if lista is None:
		lista = versiuni()
	if curent is None:
		curent = build_curent()
	if not curent or not build_bun(curent):
		return None
	c = cheie_build(curent)
	for v in lista:
		if cheie_build(v['build']) <= c:
			return v
	return None


def _instalate(lista, curent):
	"""Versiunile din lista care nu sunt mai noi decat build-ul care ruleaza (toate, cand nu se stie build-ul)."""
	if not curent or not build_bun(curent):
		return list(lista)
	c = cheie_build(curent)
	return [v for v in lista if not cheie_build(v['build']) > c]


def versiuni_noi(lista=None, vazut=None, curent=None):
	"""Versiunile pe care utilizatorul nu le-a vazut inca, de la cea mai noua la cea mai veche.
	  vazut  build-ul retinut in config. Gol, None sau stricat inseamna setari noi (receptor proaspat scris sau
	         setari sterse): atunci e noua numai versiunea care ruleaza, nu tot jurnalul de la prima versiune;
	  curent build-ul care ruleaza; gol sau None inseamna „nu se stie", si atunci nu se pune margine de sus."""
	if lista is None:
		lista = versiuni()
	if curent is None:
		curent = build_curent()
	instalate = _instalate(lista, curent)
	if vazut and build_bun(vazut):
		# vazut poate fi de 16 cifre (tinut minte de o versiune de pana la 0.3.9) iar lista de 19: se compara cheile
		cv = cheie_build(vazut)
		return [v for v in instalate if cheie_build(v['build']) > cv]
	return instalate[:1]


def intrari_noi(lista=None, vazut=None, curent=None):
	"""Ce e nou fata de ultima versiune vazuta de utilizator: [(versiune, intrare), ...], de la versiunea cea mai
	noua la cea mai veche, intrarile in ordinea din fisier. Versiunile socotite noi le alege versiuni_noi()."""
	rez = []
	for v in versiuni_noi(lista, vazut, curent):
		for x in v['intrari']:
			rez.append((v, x))
	return rez


def sectiuni(lista=None, vazut=None, curent=None):
	"""Cele doua parti ale ecranului „Ce e nou" (si ale paginii web): (sus, jos).
	  sus  versiunile nevazute inca; cand utilizatorul le-a vazut pe toate, versiunea care ruleaza;
	  jos  celelalte versiuni instalate, de la cea mai noua la cea mai veche (fara cele de sus)."""
	if lista is None:
		lista = versiuni()
	if curent is None:
		curent = build_curent()
	instalate = _instalate(lista, curent)
	sus = versiuni_noi(lista, vazut, curent) or instalate[:1]
	builduri = set(v['build'] for v in sus)
	return sus, [v for v in instalate if v['build'] not in builduri]


def numar_intrari_noi(lista=None, vazut=None, curent=None):
	"""Cate intrari noi are utilizatorul de vazut (0 daca e la zi)."""
	return len(intrari_noi(lista, vazut, curent))


def text(intrare, limba='ro'):
	"""Textul unei intrari in limba ceruta; daca lipseste, engleza, apoi romana."""
	if not isinstance(intrare, dict):
		return ''
	for cheie in (limba, 'en', 'ro'):
		v = intrare.get(cheie)
		if isinstance(v, str) and v.strip():
			return v
	return ''


def eticheta(fel, limba='ro'):
	"""Numele grupei („Nou", „Reparat", „Îmbunătățit") in limba ceruta."""
	ro, en = ETICHETE.get(fel, ('', ''))
	return ro if limba == 'ro' else en


def eticheta_tradusa(fel):
	"""Numele felului in limba interfetei (traducerea enigma2 a numelui romanesc); pe PC numele romanesc."""
	ro = ETICHETE.get(fel, ('', ''))[0]
	if not ro:
		return ''
	try:
		return _(ro)  # noqa: F821
	except NameError:
		return ro


def pe_feluri(intrari):
	"""Intrarile grupate pe fel, in ordinea din FELURI: [(fel, [intrari]), ...]; grupele goale nu apar."""
	rez = []
	for fel in FELURI:
		bucata = [x for x in intrari if x.get('fel') == fel]
		if bucata:
			rez.append((fel, bucata))
	return rez


def _config_jurnal():
	"""Ramura de config a jurnalului, creata la prima cerere. None daca nu rulam in interfata (PC, teste)."""
	try:
		from Components.config import config, ConfigSubsection, ConfigText
	except Exception:
		return None
	try:
		# hasattr(config, ...) NU e sigur: ConfigSubsection.__getattr__ arunca KeyError (nu AttributeError)
		# pentru o cheie lipsa, iar hasattr() din Python 3 prinde doar AttributeError. Se cauta direct in
		# content.items, ca in Components/UsageConfig.py.
		if 'hdsatelit' not in config.content.items:
			config.hdsatelit = ConfigSubsection()
		if 'jurnal' not in config.hdsatelit.content.items:
			config.hdsatelit.jurnal = ConfigSubsection()
		if 'ultimaVazuta' not in config.hdsatelit.jurnal.content.items:
			config.hdsatelit.jurnal.ultimaVazuta = ConfigText(default='', fixed_size=False)
		return config.hdsatelit.jurnal
	except Exception:
		return None


def ultima_vazuta():
	"""Build-ul jurnalului vazut ultima data de utilizator; sir gol daca nu l-a vazut niciodata."""
	jurnal = _config_jurnal()
	if jurnal is None:
		return ''
	try:
		v = jurnal.ultimaVazuta.value or ''
	except Exception:
		return ''
	return v if build_bun(v) else ''


def retine_vazuta(build=None):
	"""Tine minte ca utilizatorul a vazut jurnalul pana la build-ul dat (din oficiu, cel care ruleaza).
	True daca s-a putut salva."""
	if build is None:
		build = build_curent()
	if not build:
		return False
	jurnal = _config_jurnal()
	if jurnal is None:
		return False
	try:
		from Components.config import configfile
		jurnal.ultimaVazuta.value = build
		jurnal.ultimaVazuta.save()
		# .save() muta valoarea doar in memorie; fara configfile.save(), o scoatere din priza ar arata jurnalul
		# a doua oara (asa se scrie si in celelalte ecrane ale imaginii)
		configfile.save()
		return True
	except Exception:
		return False
