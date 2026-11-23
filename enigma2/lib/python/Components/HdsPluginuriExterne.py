# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Feedul pluginurilor externe (0.6.6): pluginuri luate de la altii, construite de Monea
Software din sursa lor publica, cate un dosar pe arhitectura procesorului, pe serverul nostru (unde sta si feedul imaginii).
Fiecare baza a imaginii are dosarul ei, fiindca pachetele unei baze nu merg pe alta (aceeasi arhitectura opkg):
  0.7.x (OE-Alliance 6.0, Python 3.14, OpenSSL 4):  https://stb.hdsatelit.com/feed/externe/feed-070/<arhitectura>
                                                    (si feed-070-proba/<arhitectura>, numai pentru probe)
  0.6.x (Python 3.13, libssl.so.3), DOSARE_VECHI:   https://moneasoftware.com/apps/hdsatelit-enigma2/feed/<arhitectura>
                                                    si feed-proba/<arhitectura>
Imaginea aceasta nu foloseste niciodata un dosar vechi: o sursa cu adresa lui, adaugata de om sau venita dintr-o copie
a setarilor facuta pe 0.6.x, se scoate din fisierul surselor omului (inlocuirea_vechilor), iar o lista descarcata de la
o adresa veche se sterge, ca opkg sa nu instaleze din ea inainte de urmatorul opkg update.
Feedul pluginurilor noastre ramane pe stb.hdsatelit.com (Components/HdsActualizari.py, reteta hdsatelit-feed).

Adresa de pana in 0.7.7 (ADRESA_MONEA): https://moneasoftware.com/apps/hdsatelit-enigma2/feed-070/<arhitectura>, pe
gazduirea partajata. Filtrul anti-robot al gazduirii punea uneori adresa unui om pe lista lui de verificare, iar opkg
primea 403: lista pluginurilor nu se mai descarca, iar fiecare cerere noua a receptorului il tinea pe lista. Din 0.7.8
imaginea scrie numai adresa serverului nostru (aceleasi fisiere, puse la fiecare publicare de
unelte/pluginuri-externe/feed_vps.py) si nu mai atinge gazduirea; fisierul nostru scris de o imagine mai veche (cu
ADRESA_MONEA, sau cu adresa serverului dupa trecerea pe rezerva de atunci) e rescris la prima pornire, iar lista
descarcata ramane cand arhitectura e aceeasi (acelasi index pe ambele gazde; opkg ia pachetele de la adresa sursei).
ADRESA_MONEA ramane recunoscuta ca feed extern (o sursa pusa de om cu ea nu e dublata de a noastra). Nu mai exista o
adresa de rezerva: o rezerva pe gazduire ar duce receptorul iar la filtrul ei, iar cand cade serverul nostru cade si
feedul imaginii. dupa_update ramane pentru cei care il cheama (Extensii, asistenta) si nu mai schimba nimic.

Imaginea il pune singura in /etc/opkg/hds-pluginuri-externe.conf, la pornirea interfetei (mytest.py): asa vine si printr-o
actualizare prin pachete, fara flash (stratul imaginii nu se schimba printr-o actualizare, iar dupa instalare interfata
reporneste oricum), si in orice imagine urmatoare. Arhitectura nu e scrisa in cod: e cea a pachetelor de baza instalate
(python3-core, libc6, busybox, opkg; in OE = TUNE_PKGARCH, aceeasi pe Amiko Viper 4K V10, V20, V30 si V40:
cortexa15hf-neon-vfpv4), verificata in lista `arch` a lui opkg. Un receptor cu alt procesor primeste dosarul lui, numai daca
dosarul exista pe server (ARHITECTURI_FEED, 0.7.9); altfel sursa nu se scrie.

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
# adresa pe care o scrie imaginea: serverul nostru
GAZDA = 'stb.hdsatelit.com'
DOSAR = '/feed/externe/feed-070'
ADRESA = 'https://' + GAZDA + DOSAR
# adresa scrisa pana in 0.7.7, pe gazduirea moneasoftware.com: recunoscuta, nu mai scrisa
GAZDA_MONEA = 'moneasoftware.com'
DOSAR_MONEA = '/apps/hdsatelit-enigma2/feed-070'
ADRESA_MONEA = 'https://' + GAZDA_MONEA + DOSAR_MONEA
# dosarele bazelor vechi (0.6.x) de pe GAZDA_MONEA, pe care imaginea aceasta nu le foloseste
DOSARE_VECHI = ('/apps/hdsatelit-enigma2/feed', '/apps/hdsatelit-enigma2/feed-proba')
# semnul fisierului nostru: neschimbat, ca fisierele scrise de imaginile de dinainte sa fie recunoscute si rescrise
ANTET = '# HD Satelit: feedul pluginurilor externe (Monea Software, moneasoftware.com). Il scrie imaginea la pornire.'
# pachetele de baza ale imaginii, construite pentru procesor (nu pentru masina sau pentru toate): Architecture lor e
# arhitectura procesorului; primul gasit hotaraste
PACHETE_PROCESOR = ('python3-core', 'libc6', 'busybox', 'opkg')
FARA_PROCESOR = ('all', 'any', 'noarch')
# 0.7.9 (EXA7): dosarele de procesor care exista in feedul de pe server. Pe un procesor din afara listei sursa nu se scrie (iar un
# fisier al nostru ramas se sterge): o sursa spre un dosar care nu exista facea opkg update sa iasa cu eroare la fiecare
# descarcare (ZGEMMA H8.2H Plus, cortexa7hf-vfp, in 0.7.8: 404), iar omul citea „Verifică legătura la internet”. Un dosar
# nou pe server intra aici, si ajunge pe receptoare cu actualizarea imaginii.
ARHITECTURI_FEED = ('cortexa15hf-neon-vfpv4', 'mips32el', 'cortexa7hf-vfp')
_ARH = re.compile(r'^[a-z0-9][a-z0-9_\-]{0,63}\Z')
# calea unui dosar al feedului: DOSAR/<arh> (public) sau DOSAR-proba/<arh>; la fel pe GAZDA_MONEA, cu DOSAR_MONEA
_CALE = re.compile(r'^' + re.escape(DOSAR) + r'(-proba)?/([a-z0-9][a-z0-9_\-]{0,63})/?\Z')
_CALE_MONEA = re.compile(r'^' + re.escape(DOSAR_MONEA) + r'(-proba)?/([a-z0-9][a-z0-9_\-]{0,63})/?\Z')
# adresele din randurile de eroare ale lui opkg (wget: "Failed to download <adresa>, wget returned 8.")
_ADRESA_IN_RAND = re.compile(r'https?://[^\s,\'"]+')
_CALE_VECHE = re.compile(r'^(?:%s)/[a-z0-9][a-z0-9_\-]{0,63}/?\Z' % '|'.join(re.escape(d) for d in DOSARE_VECHI))


def _jurnal(text):
	print('[HdsPluginuriExterne] %s' % text)


def _potrivire(adresa):
	try:
		parti = urlsplit(adresa or '')
		gazda = (parti.hostname or '').lower()
	except ValueError:
		return None
	if parti.scheme != 'https' or parti.query or parti.fragment:
		return None
	if gazda == GAZDA:
		return _CALE.match(parti.path or '')
	if gazda == GAZDA_MONEA:
		return _CALE_MONEA.match(parti.path or '')
	return None


def e_feed_extern(adresa):
	"""True pentru adresa unui dosar al feedului pluginurilor externe (public sau de proba, pe serverul nostru sau la
	adresa de pana in 0.7.7), numai prin https"""
	return _potrivire(adresa) is not None


def e_feed_extern_public(adresa):
	"""True pentru un dosar al feedului public (nu cel de proba)"""
	m = _potrivire(adresa)
	return m is not None and not m.group(1)


def e_feed_extern_vechi(adresa):
	"""True pentru un dosar al feedului extern al unei baze vechi (DOSARE_VECHI), prin http sau https"""
	try:
		parti = urlsplit(adresa or '')
		gazda = (parti.hostname or '').lower()
	except ValueError:
		return False
	if parti.scheme not in ('http', 'https') or gazda != GAZDA_MONEA:
		return False
	return _CALE_VECHE.match(parti.path or '') is not None


def inlocuirea_vechilor(radacina='/'):
	"""Scoate din fisierul surselor omului (HdsPachete.FISIER_SURSE_UTILIZATOR) sursele cu adresa feedului extern al
	unei baze vechi: pachetele de acolo nu merg pe imaginea aceasta, iar feedul ei il pune pune_feedul. Intoarce cate
	surse au fost scoase (0 daca nu era nimic de scos sau fisierul nu s-a putut scrie)."""
	surse = P.citeste_surse_utilizator(radacina)
	ramase = [(n, a) for n, a in surse if not e_feed_extern_vechi(a)]
	if len(ramase) == len(surse):
		return 0
	motiv = P.scrie_surse_utilizator(ramase, radacina)
	if motiv:
		_jurnal('sursele vechi nu s-au putut scoate')
		return 0
	return len(surse) - len(ramase)


def _sterge_lista(radacina, conf):
	"""Lista descarcata a sursei noastre (lists_dir/NUME_SURSA), ca opkg sa nu instaleze din lista adresei de dinainte
	pana la urmatorul opkg update"""
	try:
		os.remove(os.path.join(P._cale(radacina, conf.lists_dir), NUME_SURSA))
	except OSError:
		pass


def adresa_pentru(arhitectura):
	return '%s/%s' % (ADRESA, arhitectura)


def text_fisier(arhitectura):
	return '%s\nsrc/gz %s %s\n' % (ANTET, NUME_SURSA, adresa_pentru(arhitectura))


def _aceeasi_lista(adresa, arhitectura):
	"""True cand adresa e dosarul public al feedului pentru aceeasi arhitectura, pe oricare gazda (acelasi index):
	lista descarcata de la ea ramane buna sub adresa noua"""
	m = _potrivire(adresa)
	return m is not None and not m.group(1) and m.group(2) == arhitectura


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
	fisier; un FISIER al nostru ramas a fost sters), 'strain' (FISIER exista fara ANTET: neatins), 'fara-arhitectura',
	'fara-dosar' (procesorul nu are dosar in feed, ARHITECTURI_FEED; un FISIER al nostru ramas si lista lui au fost
	sterse) sau 'eroare'. Nu porneste nimic (lista se descarca la urmatorul opkg update: Extensii la deschidere,
	verificarea zilnica a actualizarilor)."""
	cale = P._cale(radacina, FISIER)
	try:
		with open(cale, 'r', encoding='utf-8', errors='replace') as fh:
			acum = fh.read()
	except (IOError, OSError):
		acum = None
	if acum is not None and not acum.startswith(ANTET):
		return 'strain', ''
	scoase = inlocuirea_vechilor(radacina)
	if scoase:
		_jurnal('surse cu adresa feedului unei baze vechi scoase: %d' % scoase)
	for nume, adresa, fisier in _surse_din_alte_fisiere(radacina):
		if e_feed_extern_vechi(adresa) and nume != NUME_SURSA:
			# intr-un fisier strain (pus cu o comanda): nu se atinge, dar nu tine locul feedului acestei baze
			_jurnal('o sursa straina are adresa feedului unei baze vechi: %s' % os.path.basename(fisier))
			continue
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
	if arh not in ARHITECTURI_FEED:
		if acum is not None:
			try:
				os.remove(cale)
			except OSError as e:
				return 'eroare', str(e)
			_sterge_lista(radacina, conf)
		return 'fara-dosar', arh
	text = text_fisier(arh)
	if acum == text:
		return 'la-zi', arh
	eroare = _scrie(cale, text)
	if eroare:
		return 'eroare', eroare
	if acum is not None and not _aceeasi_lista(_adresa_din_fisier(acum), arh):
		# alta arhitectura, dosarul de proba sau fisierul unei baze vechi: lista veche nu mai e buna. De pe adresa de
		# pana in 0.7.7, pentru aceeasi arhitectura, lista ramane (acelasi index), ca Extensii si modulele sa n-o piarda.
		_sterge_lista(radacina, conf)
	return 'scris', arh


def _adresa_din_fisier(text):
	"""adresa sursei noastre din textul fisierului (None daca nu e)"""
	for rand in (text or '').splitlines():
		parti = rand.split()
		if len(parti) >= 3 and parti[0] in ('src', 'src/gz') and parti[1] == NUME_SURSA:
			return parti[2]
	return None


def adrese_cazute(linii):
	"""adresele pe care opkg spune ca nu le-a putut descarca (randurile "Failed to download ...")"""
	rez = []
	for rand in linii or ():
		if 'ailed to download' not in rand:
			continue
		for a in _ADRESA_IN_RAND.findall(rand.split('ailed to download', 1)[1]):
			a = a.rstrip('.:;)')
			if a not in rez:
				rez.append(a)
	return rez


def dupa_update(linii, radacina='/'):
	"""Chemat dupa un `opkg update` cu cod de eroare (Components/HdsExtensiiLucru.treciPeRezerva, asistenta). Pana in
	0.7.7 muta aici sursa pe serverul nostru cand cadea gazduirea; acum sursa e chiar pe serverul nostru si nu are
	unde trece, deci intoarce mereu False (cine a chemat nu mai porneste inca un opkg update). Nu ridica exceptii."""
	return False


# /etc/opkg/all-feed.conf, pe care pluginurile scrise pentru imaginile OE-Alliance il gasesc acolo: primul rand
# "src/gz <imaginea>-all <adresa>"; unele pluginuri iau din el numele imaginii, cu al doilea cuvant al randului sau cu
# cut -d'-' -f1, si nu se mai incarca deloc cand lipseste. La noi sursele sunt in hdsatelit-feed.conf, deci randul sursei
# de aici e o nota (#src/gz ...), pe care opkg si uneltele imaginii nu o citesc: nicio sursa dublata. Il scrie imaginea
# inainte de prima citire a pluginurilor, ca sa vina si printr-o actualizare prin pachete; un all-feed.conf fara
# ANTET_COMPAT (pus de om sau de un pachet) nu se atinge. Niciun pachet nu trebuie sa puna acest fisier: opkg refuza sa
# instaleze peste un fisier care exista si nu e al niciunui pachet.
FISIER_ALL = '/etc/opkg/all-feed.conf'
NUME_ALL = 'hdsatelit-all'
ANTET_COMPAT = '# HD Satelit: nota pentru pluginurile scrise pentru alte imagini. O scrie imaginea la pornire.'


def text_all_feed(adresa=None):
	"""Continutul lui all-feed.conf: nota cu forma unei surse OE-Alliance (al doilea cuvant: NUME_ALL), apoi ANTET_COMPAT."""
	nota = '#src/gz %s %s' % (NUME_ALL, adresa) if adresa else '#src/gz %s' % NUME_ALL
	return '%s\n%s\n# Sursele de pachete sunt in hdsatelit-feed.conf; randul de sus e numai o nota, opkg nu-l citeste.\n' % (
		nota, ANTET_COMPAT)


# /etc/issue si /etc/issue.net: primul rand e "hdsatelit <versiune> \n \l" (in issue.net "... %h"), scris de pachetul base-files
# cu versiunea imaginii de pe stick. base-files nu se schimba printr-o actualizare prin pachete (oe-build/feed_actualizare.py,
# TIPARE_IMAGINE_NOUA), deci dupa actualizari ramanea versiunea bazei (0.7.0 sau 0.7.1 pe receptoarele cu 0.7.6), iar pluginurile
# care iau versiunea de acolo (al doilea cuvant al randului) si jurnalul de cadere (main/bsod.cpp, issue.net) o vedeau pe cea
# veche. Imaginea pune la pornire, in locul ei, versiunea care ruleaza (randul version= din /etc/image-version, ca ecranul
# Despre); restul fisierului ramane octet cu octet. Un fisier care nu incepe cu "hdsatelit <versiune>" (schimbat de om sau
# de alt pachet) nu se atinge, unul lipsa nu se face, iar unul deja la zi nu se rescrie (nicio scriere pe flash la pornire).
FISIERE_ISSUE = ('/etc/issue', '/etc/issue.net')
_RAND_ISSUE = re.compile(br'\Ahdsatelit[ \t]+([0-9]{1,3}(?:\.[0-9]{1,3}){1,3})(?=[ \t\r\n]|\Z)')
_ISSUE_MAX = 4096


def versiune_care_ruleaza(radacina='/'):
	"""Versiunea imaginii care ruleaza ("0.7.6", "0.3.10") din randul version= al /etc/image-version (16 sau 19 cifre,
	Components/HdsJurnalVersiuni.py); "" pentru un fisier lipsa sau stricat si pentru un build de incercare."""
	try:
		from Components import HdsJurnalVersiuni as J
	except ImportError:  # probe pe PC: modulul incarcat singur, din dosarul Components
		import HdsJurnalVersiuni as J
	return J.versiune_din_build(J.build_curent(P._cale(radacina, J.IMAGE_VERSION)))


def _scrie_octeti(cale, date):
	"""Inlocuieste fisierul dintr-o data (fisier.nou, apoi rename), cu drepturile celui vechi. None sau textul erorii."""
	nou = cale + '.nou'
	try:
		mod = os.stat(cale).st_mode & 0o7777
		with open(nou, 'wb') as fh:
			fh.write(date)
			fh.flush()
			os.fsync(fh.fileno())
		os.chmod(nou, mod)
		os.replace(nou, cale)
		return None
	except (IOError, OSError) as e:
		try:
			os.remove(nou)
		except OSError:
			pass
		return str(getattr(e, 'strerror', None) or e)


def pune_versiunea_issue(radacina='/'):
	"""Aduce la zi versiunea din /etc/issue si /etc/issue.net (vezi sus). Intoarce lista fisierelor scrise; nu ridica exceptii."""
	scrise = []
	try:
		versiune = versiune_care_ruleaza(radacina)
	except Exception as e:
		_jurnal('issue: versiunea imaginii: %s' % e)
		return scrise
	if not versiune:
		return scrise
	nou_v = versiune.encode('ascii')
	for fisier in FISIERE_ISSUE:
		cale = P._cale(radacina, fisier)
		try:
			if os.path.islink(cale) or not os.path.isfile(cale):
				continue
			with open(cale, 'rb') as fh:
				acum = fh.read(_ISSUE_MAX + 1)
			if len(acum) > _ISSUE_MAX:
				continue
			m = _RAND_ISSUE.match(acum)
			if not m or m.group(1) == nou_v:
				continue
			eroare = _scrie_octeti(cale, acum[:m.start(1)] + nou_v + acum[m.end(1):])
		except Exception as e:
			eroare = str(e)
		if eroare:
			_jurnal('%s: %s' % (fisier, eroare))
		else:
			scrise.append(fisier)
	return scrise


def pune_fisierele_compat(radacina='/'):
	"""Pune sau tine la zi all-feed.conf (vezi mai sus) si versiunea din /etc/issue si /etc/issue.net (pune_versiunea_issue),
	inainte de prima citire a pluginurilor (Components/PluginComponent.py). Fara /etc/opkg/opkg.conf (nu e un receptor, de pilda
	probele de pe PC) nu scrie nimic. Intoarce lista fisierelor scrise."""
	scrise = []
	if not os.path.isfile(P._cale(radacina, '/etc/opkg/opkg.conf')):
		return scrise
	# issue inaintea intoarcerilor de mai jos: un all-feed.conf strain sau deja la zi nu opreste versiunea
	scrise.extend(pune_versiunea_issue(radacina))
	cale = P._cale(radacina, FISIER_ALL)
	try:
		with open(cale, 'r', encoding='utf-8', errors='replace') as fh:
			acum = fh.read()
	except (IOError, OSError):
		acum = None
	if acum is not None and ANTET_COMPAT not in acum:
		return scrise
	adresa = None
	for nume, adr, _f in _surse_din_alte_fisiere(radacina):
		if nume == NUME_ALL:
			adresa = adr
			break
	text = text_all_feed(adresa)
	if acum == text:
		return scrise
	eroare = _scrie(cale, text)
	if eroare:
		_jurnal('all-feed.conf: %s' % eroare)
	else:
		scrise.append(FISIER_ALL)
	return scrise


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
