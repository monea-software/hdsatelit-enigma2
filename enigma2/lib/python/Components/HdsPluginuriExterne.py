# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Feedul pluginurilor externe (0.6.6): pluginuri luate de la altii, construite de Monea
Software din sursa lor publica si tinute pe moneasoftware.com, cate un dosar pe arhitectura procesorului.
Fiecare baza a imaginii are dosarul ei, fiindca pachetele unei baze nu merg pe alta (aceeasi arhitectura opkg):
  0.7.x (OE-Alliance 6.0, Python 3.14, OpenSSL 4):  https://moneasoftware.com/apps/hdsatelit-enigma2/feed-070/<arhitectura>
                                                    (si feed-070-proba/<arhitectura>, numai pentru probe)
  0.6.x (Python 3.13, libssl.so.3), DOSARE_VECHI:   .../feed/<arhitectura> si feed-proba/<arhitectura>
Imaginea aceasta nu foloseste niciodata un dosar vechi: o sursa cu adresa lui, adaugata de om sau venita dintr-o copie
a setarilor facuta pe 0.6.x, se scoate din fisierul surselor omului (inlocuirea_vechilor), iar o lista descarcata de la
o adresa veche se sterge, ca opkg sa nu instaleze din ea inainte de urmatorul opkg update.
Feedul pluginurilor noastre ramane pe stb.hdsatelit.com (Components/HdsActualizari.py, reteta hdsatelit-feed).

Rezerva (0.7.4, 12.11.2026): aceleasi fisiere stau si pe serverul nostru,
  https://stb.hdsatelit.com/feed/externe/feed-070/<arhitectura> (si feed-070-proba/<arhitectura>),
puse la fiecare publicare (unelte/pluginuri-externe/feed_vps.py). Gazduirea moneasoftware.com are un filtru anti-robot
care pune uneori adresa unui om pe lista gri (Wlad, Ucraina, 11.11.2026: 403 si pe receptor, si in browser). Cand un
`opkg update` arata ca a cazut lista de pe moneasoftware.com (dupa_update, chemat de Components/HdsExtensiiLucru.py),
aceeasi sursa (acelasi nume, acelasi fisier) trece pe adresa de rezerva si lista veche se sterge; omul nu face nimic.
La urmatoarea pornire pune_feedul pune iar adresa principala: cand gazduirea il deblocheaza, totul revine singur.
Nu doua surse: opkg update ar da tot cod de eroare cand cade una (ModuleLipsa si DriverLipsa il iau drept esec), iar
lista veche a sursei cazute ar ramane si opkg ar descarca tot de pe gazda blocata.

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
DOSAR = '/apps/hdsatelit-enigma2/feed-070'
ADRESA = 'https://' + GAZDA + DOSAR
# dosarele bazelor vechi (0.6.x), pe care imaginea aceasta nu le foloseste
DOSARE_VECHI = ('/apps/hdsatelit-enigma2/feed', '/apps/hdsatelit-enigma2/feed-proba')
GAZDA_REZERVA = 'stb.hdsatelit.com'
DOSAR_REZERVA = '/feed/externe/feed-070'
ADRESA_REZERVA = 'https://' + GAZDA_REZERVA + DOSAR_REZERVA
ANTET = '# HD Satelit: feedul pluginurilor externe (Monea Software, moneasoftware.com). Il scrie imaginea la pornire.'
# pachetele de baza ale imaginii, construite pentru procesor (nu pentru masina sau pentru toate): Architecture lor e
# arhitectura procesorului; primul gasit hotaraste
PACHETE_PROCESOR = ('python3-core', 'libc6', 'busybox', 'opkg')
FARA_PROCESOR = ('all', 'any', 'noarch')
_ARH = re.compile(r'^[a-z0-9][a-z0-9_\-]{0,63}\Z')
# calea unui dosar al feedului: DOSAR/<arh> (public) sau DOSAR-proba/<arh>
_CALE = re.compile(r'^' + re.escape(DOSAR) + r'(-proba)?/([a-z0-9][a-z0-9_\-]{0,63})/?\Z')
_CALE_REZERVA = re.compile(r'^' + re.escape(DOSAR_REZERVA) + r'(-proba)?/([a-z0-9][a-z0-9_\-]{0,63})/?\Z')
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
	if gazda == GAZDA_REZERVA:
		return _CALE_REZERVA.match(parti.path or '')
	return None


def e_feed_extern(adresa):
	"""True pentru adresa unui dosar al feedului pluginurilor externe (public sau de proba, principal sau rezerva),
	numai prin https"""
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
	if parti.scheme not in ('http', 'https') or gazda != GAZDA:
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


def adresa_pentru(arhitectura, rezerva=False):
	return '%s/%s' % (ADRESA_REZERVA if rezerva else ADRESA, arhitectura)


def text_fisier(arhitectura, rezerva=False):
	return '%s\nsrc/gz %s %s\n' % (ANTET, NUME_SURSA, adresa_pentru(arhitectura, rezerva))


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
	text = text_fisier(arh)
	if acum == text:
		return 'la-zi', arh
	eroare = _scrie(cale, text)
	if eroare:
		return 'eroare', eroare
	if acum is not None:
		# adresa s-a schimbat (alta arhitectura sau fisierul unei baze vechi): lista veche nu mai e buna
		_sterge_lista(radacina, conf)
	return 'scris', arh


def _adresa_din_fisier(text):
	"""adresa sursei noastre din textul fisierului (None daca nu e)"""
	for rand in (text or '').splitlines():
		parti = rand.split()
		if len(parti) >= 3 and parti[0] in ('src', 'src/gz') and parti[1] == NUME_SURSA:
			return parti[2]
	return None


def pe_rezerva(radacina='/'):
	"""True cand fisierul nostru tine acum adresa de rezerva"""
	try:
		with open(P._cale(radacina, FISIER), 'r', encoding='utf-8', errors='replace') as fh:
			text = fh.read()
	except (IOError, OSError):
		return False
	adresa = _adresa_din_fisier(text) or ''
	return text.startswith(ANTET) and adresa.startswith(ADRESA_REZERVA + '/')


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


def principalul_a_cazut(linii):
	"""True cand printre adresele cazute e lista feedului public de pe moneasoftware.com"""
	for a in adrese_cazute(linii):
		try:
			parti = urlsplit(a)
		except ValueError:
			continue
		if (parti.hostname or '').lower() == GAZDA and (parti.path or '').startswith(DOSAR + '/'):
			return True
	return False


def treci_pe_rezerva(radacina='/'):
	"""Fisierul nostru trece de pe moneasoftware.com pe adresa de rezerva (aceeasi sursa, acelasi nume), iar lista
	descarcata de pe moneasoftware.com se sterge (altfel opkg ar instala din ea, de pe gazda blocata). Numai un fisier
	al nostru (cu ANTET) care tine adresa principala. Intoarce True cand a trecut."""
	cale = P._cale(radacina, FISIER)
	try:
		with open(cale, 'r', encoding='utf-8', errors='replace') as fh:
			acum = fh.read()
	except (IOError, OSError):
		return False
	adresa = _adresa_din_fisier(acum) or ''
	if not acum.startswith(ANTET) or not adresa.startswith(ADRESA + '/'):
		return False
	arh = adresa[len(ADRESA) + 1:].strip('/')
	if not _ARH.match(arh):
		return False
	if _scrie(cale, text_fisier(arh, rezerva=True)):
		return False
	_sterge_lista(radacina, P.citeste_configurarea(radacina))
	_jurnal('moneasoftware.com nu raspunde: feedul pluginurilor externe trece pe rezerva (%s)' % adresa_pentru(arh, True))
	return True


def dupa_update(linii, radacina='/'):
	"""Dupa un `opkg update` cu cod de eroare: daca a cazut lista de pe moneasoftware.com, sursa trece pe rezerva.
	Intoarce True cand a trecut (atunci cine a chemat porneste inca un opkg update). Nu ridica exceptii."""
	try:
		return principalul_a_cazut(linii) and treci_pe_rezerva(radacina)
	except Exception as e:
		_jurnal('trecerea pe rezerva: %s' % e)
		return False


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
