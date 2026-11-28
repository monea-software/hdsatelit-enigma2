# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
# Cautarea si memoria siglelor imaginii raman aici, separat de rendererele temelor.
# Pentru sablonul picon se cauta numai picon, pe discurile montate si in locurile fixe.
# Un alt set se cauta numai cand rendererul lui cere explicit dosarul respectiv.
from collections import OrderedDict
from threading import Lock, RLock
from Tools.Directories import fileExists, eEnv
import os
import time


def sigle_pornite():
	"""Setarea "Siglele canalelor (piconuri)"; fara setare (probele de pe PC, alt cod) sau la orice eroare: da."""
	try:
		import sys
		return bool(sys.modules["Components.config"].config.usage.hds_piconuri.value)
	except Exception:
		return True


# Dosarele de sigle in ordinea cautarii; %s este numele dosarului.
CAI_SIGLE = (eEnv.resolve('${datadir}/enigma2/%s/'),
	'/media/hdd/%s/',
	'/media/usb/%s/',
	'/media/mmc/%s/',
	'/media/cf/%s/',
	'/%s/')
# radacinile montarilor; in probe se pot inlocui cu dosare temporare
RADACINI_MEDIA = ("/media", "/run/media")
DOSARE_SIGLE = ("picon",)

# Pluginurile primesc aici cai complete, fara sablonul folosit de clasa Picon.
searchPaths = tuple(cale % "picon" for cale in CAI_SIGLE)

# tipurile de referinta ale fluxurilor care poarta si partea DVB (SID, TSID, ONID, namespace)
TIPURI_FLUX = ("4097", "5001", "5002", "5003", "8193", "8739")
# the players an IPTV source can use (Player si piconuri); the DVB part of the reference is the same for all three
TIPURI_PLAYER_IPTV = ("4097", "5001", "5002")
# tipurile de serviciu radio (ca lista de radio a imaginii)
TIPURI_RADIO = ("2", "a", "A")


def nume_sigle(sref):
	"""Numele de fisier (fara .png) incercate pentru o referinta, in ordine: exact, cu tipul serviciului 1, la fluxuri
	cu tipul referintei 1. Lista goala pentru o referinta fara campurile DVB."""
	campuri = str(sref or "").split(":")
	if len(campuri) < 10:
		return []
	baza = campuri[:10]
	nume = []

	def adauga(c):
		n = "_".join(c).rstrip("_")
		if n and n not in nume:
			nume.append(n)
	adauga(baza)
	if baza[2] not in ("1", "0"):
		c = list(baza)
		c[2] = "1"
		adauga(c)
	# Same IPTV channel under the other two players: logos saved for one player stay visible after a player switch.
	if baza[0] in TIPURI_PLAYER_IPTV:
		for tip in TIPURI_PLAYER_IPTV:
			if tip != baza[0]:
				c = list(baza)
				c[0] = tip
				adauga(c)
	if baza[0] in TIPURI_FLUX:
		c = list(baza)
		c[0] = "1"
		adauga(c)
		if c[2] not in ("1", "0"):
			c[2] = "1"
			adauga(c)
	# Unele liste au subreteaua in ultimele patru cifre ale namespace-ului.
	for c in list(nume):
		campuri = c.split("_")
		try:
			namespace = int(campuri[6], 16)
		except (ValueError, IndexError):
			continue
		if namespace & 0xffff:
			campuri[6] = "%X" % (namespace & 0xffff0000)
			adauga(campuri)
	return nume


def nume_dupa_canal(nume):
	"""Numele siglei dupa canal: ASCII fara diacritice, litere mici si cifre."""
	import unicodedata
	text = unicodedata.normalize("NFKD", str(nume or "")).encode("ascii", "ignore").decode("ascii")
	for semn, cuvant in (("&", "and"), ("+", "plus"), ("*", "star")):
		text = text.replace(semn, cuvant)
	return "".join(c for c in text.lower() if "a" <= c <= "z" or "0" <= c <= "9")


def nume_cautate_canal(nume):
	"""Numele complet, apoi fara terminatia de calitate, daca exista."""
	n = nume_dupa_canal(nume)
	rez = [n] if n else []
	for coada in ("fhd", "uhd", "hd", "sd", "4k"):
		if n.endswith(coada) and len(n) > len(coada):
			rez.append(n[:-len(coada)])
			break
	return rez


def nume_canal(sref):
	"""Numele din lista serviciilor; la fluxuri, si numele adaugat dupa adresa din referinta."""
	try:
		from enigma import eServiceCenter, eServiceReference
		ref = eServiceReference(sref)
		info = eServiceCenter.getInstance().info(ref)
		nume = info.getName(ref) if info else ""
		if nume:
			return nume
	except Exception:
		pass
	campuri = str(sref or "").split(":", 11)
	if campuri[0] in TIPURI_FLUX and len(campuri) > 11:
		from urllib.parse import unquote
		return unquote(campuri[11])
	return ""


_dosare = {}
_cautari = OrderedDict()
_zavor = RLock()
_generatie = 0
_manager_disc = None
MAX_CAUTARI = 2048
VIATA_CAUTARII = 60


def generatie_sigle():
	"""Numarul schimbarii discurilor sau siglelor; fara acces la disc."""
	return _generatie


def _disc_schimbat(fel, partitie):
	if fel in ("add", "remove", "change"):
		resetPiconPath()


def _leaga_discurile():
	global _manager_disc
	if _manager_disc is None:
		try:
			from Components.Harddisk import harddiskmanager
			if _disc_schimbat not in harddiskmanager.on_partition_list_change:
				harddiskmanager.on_partition_list_change.append(_disc_schimbat)
			_manager_disc = harddiskmanager
		except (ImportError, AttributeError):
			pass


def _montari_sigle():
	"""Montarile cunoscute si locurile obisnuite, fara parcurgerea discurilor."""
	_leaga_discurile()
	montari = set()
	if _manager_disc is not None:
		try:
			montari.update(p.mountpoint for p in
				_manager_disc.getMountedPartitions() if p.mountpoint)
		except (AttributeError, OSError):
			pass
	# Include si montarile facute manual, in afara managerului de discuri.
	try:
		with open("/proc/mounts", "r") as f:
			for linie in f:
				campuri = linie.split()
				if len(campuri) > 1:
					cale = campuri[1]
					for cod, semn in (("\\040", " "), ("\\011", "\t"),
						("\\134", "\\")):
						cale = cale.replace(cod, semn)
					montari.add(cale)
	except OSError:
		pass
	for radacina in RADACINI_MEDIA:
		try:
			intrari = os.listdir(radacina)
		except OSError:
			continue
		for intrare in intrari:
			cale = os.path.join(radacina, intrare)
			montari.add(cale)
			# Reteaua si montarile pe utilizator au inca un nivel.
			if intrare in ("net", "autofs") or radacina == "/run/media":
				try:
					montari.update(os.path.join(cale, n) for n in os.listdir(cale))
				except OSError:
					pass
	return sorted(montari)


# HDSatelit 0.7.6 (FRZ, raportul 2149, SF8008 0.7.5): firul interfetei a stat 12,2 s la pornire cu cadrul in isdir <- Screen.execBegin
# (prima sigla a barei). dosare_sigle facea isdir pe <montare>/picon pentru FIECARE montare din /proc/mounts, pe firul care cere
# sigla, si din nou la fiecare minut: o montare de retea moarta (cifs, nfs, autofs care incearca sa monteze) sau un disc adormit
# tin stat()-ul secunde intregi. Acum montarile de retea se verifica numai pe un fir de fundal, iar dupa prima lista (numai
# discurile locale) refacerea de la un minut merge tot pe firul de fundal: cine cere sigla primeste lista de pana atunci.
FS_RETEA = frozenset(("cifs", "smb3", "smbfs", "nfs", "nfs4", "autofs", "fuse.sshfs", "sshfs", "davfs", "fuse.davfs2",
	"fuse.rclone", "9p", "ncpfs", "afs", "ceph", "glusterfs", "fuse.glusterfs"))
DOSARE_RETEA = ("/media/net/", "/media/autofs/", "/autofs/", "/mnt/net/", "/mnt/autofs/")
_fire_sigle = {}        # dosar -> firul care reface lista lui


def _montari_retea():
	"""Caile montarilor de retea din /proc/mounts (dupa tipul sistemului de fisiere)."""
	rez = set()
	try:
		with open("/proc/mounts", "r") as f:
			for linie in f:
				campuri = linie.split()
				if len(campuri) > 2 and campuri[2] in FS_RETEA:
					cale = campuri[1]
					for cod, semn in (("\\040", " "), ("\\011", "\t"), ("\\134", "\\")):
						cale = cale.replace(cod, semn)
					rez.add(os.path.normpath(cale))
	except OSError:
		pass
	return rez


def _e_retea(cale, retea):
	"""True cand dosarul e pe o montare de retea (sau sub dosarele obisnuite ale retelei)."""
	c = os.path.normpath(cale)
	if any((c.replace(os.sep, "/") + "/").startswith(d) for d in DOSARE_RETEA):
		return True
	while c:
		if c in retea:
			return True
		sus = os.path.dirname(c)
		if sus == c:
			break
		c = sus
	return False


def _cai_sigle(dosar):
	"""(cai locale, cai de retea) in ordinea cautarii: dosarele imaginii, apoi montarile."""
	montari = _montari_sigle()
	retea = _montari_retea()
	altele = [c % dosar for c in CAI_SIGLE]
	altele.extend(os.path.join(m, dosar, "") for m in montari)
	locale, de_retea = [], []
	for cale in altele:
		(de_retea if _e_retea(cale, retea) else locale).append(cale)
	return locale, de_retea, altele


def _existente(cai):
	gasite, vazute = [], set()
	for cale in cai:
		cale = os.path.join(os.path.normpath(cale), "")
		if os.path.isdir(cale):
			cheie = os.path.normcase(os.path.realpath(cale))
			if cheie not in vazute:
				vazute.add(cheie)
				gasite.append(cale)
	return gasite


def _reface(dosar):
	"""Pe firul de fundal: lista intreaga (si montarile de retea), pusa in cache daca discurile nu s-au schimbat intre timp."""
	try:
		acum = time.time()
		with _zavor:
			generatie = _generatie
		_locale, _retea, toate = _cai_sigle(dosar)
		gasite = _existente(toate)
		with _zavor:
			if generatie == _generatie:
				_dosare[dosar] = (acum, gasite)
	except Exception as e:
		print("[PiconResolver] dosarele de sigle: %s" % e)


def _porneste_refacerea(dosar):
	import threading
	with _zavor:
		fir = _fire_sigle.get(dosar)
		if fir is not None and fir.is_alive():
			return False
		fir = threading.Thread(target=_reface, args=(dosar,), name="HdsDosareSigle")
		fir.daemon = True
		_fire_sigle[dosar] = fir
	fir.start()
	return True


def dosare_sigle(dosar="picon"):
	"""Dosare comune; refacute la hotplug, deschiderea listei sau dupa un minut (dupa prima lista: pe un fir de fundal)."""
	acum = time.time()
	with _zavor:
		e = _dosare.get(dosar)
		generatie = _generatie
	if e is not None and 0 <= acum - e[0] < 60:
		return e[1]
	if e is not None:
		_porneste_refacerea(dosar)
		return e[1]
	locale, de_retea, _toate = _cai_sigle(dosar)
	gasite = _existente(locale)
	with _zavor:
		if generatie == _generatie:
			# cu montari de retea, lista locala tine pana o completeaza firul (fara asteptarea minutului)
			_dosare[dosar] = (acum - (60 if de_retea else 0), gasite)
	if de_retea:
		_porneste_refacerea(dosar)
	return gasite


def getPiconPath(context=None):
	"""Primul dosar de sigle existent sau text gol; imaginea foloseste aceleasi dosare in toate ecranele."""
	dosare = dosare_sigle()
	return dosare[0] if dosare else ""


def resetPiconPath():
	"""Uita dosarele si rezultatele, inclusiv lipsurile, pentru toate ecranele."""
	global _generatie
	with _zavor:
		_generatie += 1
		_dosare.clear()
		_cautari.clear()
		# indexul se reciteste la prima lipsa de dupa (fara pauza): discurile s-au schimbat
		_index.clear()
		_index_cerut.clear()


# HDSatelit 0.7.8 (PCN6, raportul robiul, forum 1591 #3354): sigle numite dupa referinta, dar scrise altfel decat o cere
# cautarea exacta (litere mici in campurile hex, .PNG, zerouri in fata) nu se vedeau. Cautarea exacta de mai sus ramane
# neschimbata. In plus, un fir de fundal citeste dosarele de sigle locale (os.listdir; montarile de retea nu) si tine in
# memorie un index: numele normalizat -> calea fisierului. Firul interfetei NU face niciun acces la disc pentru index: il citeste numai cand cautarea
# exacta n-a gasit nimic, iar o potrivire din index nu intra in memoria rezultatelor (nicio verificare in plus la apelul
# urmator). Cat timp indexul nu e gata, rezultatul e exact cel vechi. Indexul nu goleste memoria si nu schimba generatia.
_index = {}             # dosar -> (generatie, ceas, [tabela nume normalizat -> cale, ...], toate dosarele aflate)
_fire_index = {}        # dosar -> firul care citeste indexul
_index_cerut = {}       # dosar -> ceasul ultimei porniri a firului
_zavor_index = Lock()   # numai acquire(False): firul interfetei nu asteapta niciodata
_revizie_index = [0]    # creste cand un index publicat difera de cel dinainte
VIATA_INDEXULUI = 60    # secunde; dupa atat indexul se reciteste in fundal, la urmatoarea cerere
PAUZA_INDEXULUI = 1.5   # secunde intre doua porniri ale firului pentru acelasi dosar


def _normalizat(baza):
	"""Cheia de index a unui nume de fisier fara extensie: campurile hex fara zerouri in fata, cu litere mari;
	orice alt nume cu litere mici. Aceeasi functie pentru fisiere si pentru numele cautate."""
	campuri = baza.split("_")
	if len(campuri) > 1:
		try:
			return "_".join("%X" % int(c, 16) for c in campuri)
		except ValueError:
			pass
	return baza.lower()


def revizie_index():
	"""Numarul schimbarilor indexului de sigle; numai memorie."""
	return _revizie_index[0]


def _citeste_index(dosar):
	"""Pe firul de fundal: listeaza dosarele de sigle LOCALE si publica indexul, daca discurile nu s-au schimbat intre timp.
	Dosarele de pe montari de retea nu intra in index: acolo ramane numai cautarea exacta de pe HEAD."""
	try:
		generatie = _generatie
		dosare = dosare_sigle(dosar)
		retea = _montari_retea()
		tabele = []
		for cale in dosare:
			# dosarul insusi poate fi o legatura spre o montare de retea: conteaza calea lui reala
			radacina = os.path.realpath(cale)
			if _e_retea(cale, retea) or _e_retea(radacina, retea):
				continue
			try:
				with os.scandir(cale) as it:
					# numai fisiere obisnuite din dosar: o legatura simbolica (de pilda spre o sigla de pe NAS) nu intra
					# in index, fiindca firul interfetei ar deschide-o la incarcare
					intrari = sorted(e.name for e in it if not e.is_symlink() and e.is_file(follow_symlinks=False))
			except OSError:
				continue
			tabela = {}
			for n in intrari:
				baza, extensie = os.path.splitext(n)
				if extensie.lower() == ".png" and baza:
					tabela.setdefault(_normalizat(baza), cale + n)
			tabele.append(tabela)
		if generatie != _generatie:
			return
		vechi = _index.get(dosar)
		_index[dosar] = (generatie, time.monotonic(), tabele, tuple(dosare))
		if vechi is None or vechi[2] != tabele:
			_revizie_index[0] += 1
	except Exception as e:
		print("[PiconResolver] indexul siglelor: %s" % e)
	finally:
		_fire_index.pop(dosar, None)


def cere_index(dosar="picon"):
	"""Porneste citirea indexului in fundal cand lipseste sau e vechi. Fara disc si fara asteptare: numai memorie si,
	cel mult o data la PAUZA_INDEXULUI secunde, pornirea unui fir."""
	acum = time.monotonic()
	e = _index.get(dosar)
	# dosarele aflate intre timp (de pilda o montare de retea gasita in fundal) cer recitirea indexului
	d = _dosare.get(dosar)
	if (e is not None and e[0] == _generatie and 0 <= acum - e[1] < VIATA_INDEXULUI
			and (d is None or tuple(d[1]) == e[3])):
		return False
	ultima = _index_cerut.get(dosar)
	if ultima is not None and 0 <= acum - ultima < PAUZA_INDEXULUI:
		return False
	if not _zavor_index.acquire(False):
		return False
	try:
		if dosar in _fire_index:
			return False
		import threading
		fir = threading.Thread(target=_citeste_index, args=(dosar,), name="HdsIndexSigle")
		fir.daemon = True
		_fire_index[dosar] = fir
		_index_cerut[dosar] = acum
	finally:
		_zavor_index.release()
	try:
		fir.start()
	except Exception as e:
		_fire_index.pop(dosar, None)
		print("[PiconResolver] firul indexului: %s" % e)
		return False
	return True


def sigla_din_index(sref, dosar="picon", nume=None):
	"""Calea siglei din indexul din memorie (numai dosare locale), sau "". Fara niciun acces la disc, fara zavor si fara
	servicii enigma: numele canalului se primeste deja aflat (nume), nu se cere aici; eServiceCenter.info() pe o
	inregistrare (/media/net/.../film.ts) citeste .meta de pe disc. Referintele cu cale de fisier nu folosesc indexul:
	pentru ele ramane numai ce gaseste cautarea HEAD."""
	e = _index.get(dosar)
	if e is None or e[0] != _generatie:
		return ""
	campuri = str(sref or "").split(":", 10)
	if len(campuri) > 10 and campuri[10].startswith("/"):
		return ""
	cautate = [_normalizat(n) for n in nume_sigle(sref)]
	cautate.extend(_normalizat(n) for n in nume_cautate_canal(nume or "") if n)
	for cheie in cautate:
		for tabela in e[2]:
			cale = tabela.get(cheie)
			if cale:
				return cale
	return ""


def nume_memorat(sref, dosar="picon"):
	"""Numele canalului aflat de ultima cautare a acestei referinte (memoria rezultatelor), sau None. Numai memorie."""
	mem = _cautari.get((sref, dosar, None))
	return mem[2] if mem is not None and len(mem) > 2 else None


def _dosare_locuri():
	"""Dosarele de sigle ale locurilor adaugate de extensii (Components/HdsLocuriLista.py); acolo poate fi si JPEG."""
	try:
		from Components.HdsLocuriLista import dosareSigle
		return dosareSigle()
	except Exception:
		return []


def cauta_sigla(sref, dosar="picon", nume=None):
	"""Calea siglei unui serviciu, sau "" cand nu e niciuna. Dupa referinta, apoi dupa numele explicit sau aflat."""
	if sref and not isinstance(sref, str) and hasattr(sref, "toString"):
		# eServiceReference primit direct: str() nu da referinta
		sref = sref.toString()
	sref = str(sref or "")
	cheie = (sref, dosar, nume)
	acum = time.monotonic()
	with _zavor:
		mem = _cautari.get(cheie)
		if mem is not None:
			_cautari.move_to_end(cheie)
	if mem is not None and 0 <= acum - mem[0] < VIATA_CAUTARII:
		if not mem[1]:
			return _din_index(sref, dosar, mem[2] if len(mem) > 2 else nume) or _sigla_extensiei(sref, dosar)
		if fileExists(mem[1]):
			return mem[1]
	g = generatie_sigle()
	png = _cauta_locala(sref, dosar, nume)
	# numele canalului aflat la o lipsa se tine langa ea: indexul nu-l mai cere o data
	canal = _canal_aflat.pop(sref, nume) if nume is None else nume
	with _zavor:
		if g == _generatie:
			_cautari[cheie] = (acum, png, canal)
			_cautari.move_to_end(cheie)
			while len(_cautari) > MAX_CAUTARI:
				_cautari.popitem(last=False)
	if png:
		return png
	return _din_index(sref, dosar, canal) or _sigla_extensiei(sref, dosar)


def _din_index(sref, dosar, nume):
	"""Dupa o lipsa a cautarii exacte: potrivirea din indexul din memorie (fara disc); cere recitirea lui in fundal
	cand e vechi (o sigla stearsa iese din index la urmatoarea citire)."""
	try:
		png = sigla_din_index(sref, dosar, nume)
		cere_index(dosar)
		return png
	except Exception as e:
		print("[PiconResolver] indexul siglelor: %s" % e)
		return ""


_canal_aflat = {}       # referinta -> numele canalului aflat de _cauta_locala, luat indata de cauta_sigla


def _cauta_locala(sref, dosar, nume):
	cai = dosare_sigle(dosar)
	locuri = _dosare_locuri() if dosar == "picon" else []
	def gaseste(nume):
		for cale in cai:
			png = cale + nume + ".png"
			if fileExists(png):
				return png
		for cale in locuri:
			for extensie in (".png", ".jpg"):
				if fileExists(cale + nume + extensie):
					return cale + nume + extensie
		return ""

	for candidat in nume_sigle(sref):
		png = gaseste(candidat)
		if png:
			return png
	if nume is None:
		nume = nume_canal(sref)
		_canal_aflat[sref] = nume
	for candidat in nume_cautate_canal(nume):
		if candidat:
			png = gaseste(candidat)
			if png:
				return png
	return ""


def _sigla_extensiei(sref, dosar):
	# Siglele aduse in fundal pot aparea intre doua cautari locale.
	if dosar == "picon":
		try:
			from Components import HdsIptvSigle
			return HdsIptvSigle.cauta(sref)
		except Exception:
			pass
	return ""


_leaga_discurile()


def getPiconName(serviceRef):
	"""Numele cerut de pluginuri: calea siglei unui serviciu (text), "" cand nu e niciuna."""
	if not isinstance(serviceRef, str):
		serviceRef = serviceRef.toString() if hasattr(serviceRef, "toString") else str(serviceRef)
	return cauta_sigla(serviceRef) or ""


class PiconResolver:
	@staticmethod
	def getPngName(sRef, nameCache, findPicon):
		cheie = sRef if isinstance(sRef, str) else sRef.toString() if hasattr(sRef, "toString") else str(sRef)
		png = nameCache.get(cheie, "")
		if png and fileExists(png):
			return png
		nameCache.pop(cheie, None)
		png = getPiconName(cheie)
		# Dosarul ales de plugin se verifica numai prin functia data de el.
		if not png and findPicon is not None:
			for nume in nume_sigle(cheie):
				png = findPicon(nume)
				if png:
					break
		if png:
			nameCache[cheie] = png
		# Lipsa nu se memoreaza: un disc sau o sigla poate aparea mai tarziu.
		return png or ""
