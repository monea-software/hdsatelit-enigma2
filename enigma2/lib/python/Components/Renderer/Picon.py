# Modificat de moneasoftware.com si hdsatelit.com, 2026
##
## Picon renderer by Gruffy .. some speedups by Ghost
##
# Siglele se cauta in dosarele fixe si pe toate discurile montate.
# Intai se incearca referinta si variantele ei, apoi numele normalizat,
# inclusiv fara terminatia de calitate. Lista, web-ul si afisajul color
# folosesc aceeasi cautare:
# cauta_sigla(). Fara sigla se arata picon_default.png (in skinul HDSatelit un dreptunghi transparent: caseta ramane
# goala, fara semn care sa para o eroare). Cu atributul de skin defaultPerType="1" lipsa se arata cu
# picon_default_tv.png sau picon_default_radio.png din skinul activ, cand exista.
#
# Sigla se potriveste in caseta din skin (ePixmap.setScale): un picon obisnuit de 220x132 intra intreg si in casetele de
# 110x66 sau 150x90 (fara potrivire se vedea numai coltul lui din stanga sus).
# Setarea "Siglele canalelor (piconuri)" (config.usage.hds_piconuri, din fabrica da): oprita, nicio sigla nu se cauta
# si caseta ramane goala (picon_default). Schimbarea setarii se vede pe loc in ecranele deschise (Components/HdsPiconBare).
# Atributul de skin vecini="x,y,l,i=x2,l2|..." (Components/HdsPiconBare): elementele ecranului cu position="x,y" si
# size="l,i" se muta la x2 cu latimea l2 numai cat se vede o sigla adevarata (setarea pornita si sigla gasita); fara sigla
# raman la locul lor din skin, deci nu ramane loc gol in stanga.
from .Renderer import Renderer
from enigma import ePixmap, eEnv
from Tools.Directories import fileExists, SCOPE_SKIN_IMAGE, SCOPE_CURRENT_SKIN, resolveFilename
from collections import OrderedDict
from threading import RLock
import os
import time


def sigle_pornite():
	"""Setarea "Siglele canalelor (piconuri)"; fara setare (probele de pe PC, alt cod) sau la orice eroare: da."""
	try:
		import sys
		return bool(sys.modules["Components.config"].config.usage.hds_piconuri.value)
	except Exception:
		return True


def _anunta(r):
	"""Sigla s-a aratat sau s-a ascuns: vecinii ei (Components/HdsPiconBare) la locul lor."""
	try:
		from Components.HdsPiconBare import schimbat
		schimbat(r)
	except Exception as e:
		print("[Picon] vecinii: %s" % e)

# Dosarele de sigle in ordinea cautarii; %s este numele dosarului.
CAI_SIGLE = (eEnv.resolve('${datadir}/enigma2/%s/'),
	'/media/hdd/%s/',
	'/media/usb/%s/',
	'/media/mmc/%s/',
	'/media/cf/%s/',
	'/%s/')
# radacinile montarilor; in probe se pot inlocui cu dosare temporare
RADACINI_MEDIA = ("/media", "/run/media")
DOSARE_SIGLE = ("picon", "piconHD", "XPicon", "ZZPicon",
	"XPicons", "ZZPicons", "XPicons/picon", "ZZPicons/picon",
	"picon/piconHD", "picons/piconHD")

# Pluginurile primesc aici cai complete, fara sablonul folosit de clasa Picon.
searchPaths = tuple(cale % "picon" for cale in CAI_SIGLE)

# tipurile de referinta ale fluxurilor care poarta si partea DVB (SID, TSID, ONID, namespace)
TIPURI_FLUX = ("4097", "5001", "5002", "5003", "8193", "8739")
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


def dosare_sigle(dosar="picon"):
	"""Dosare comune; refacute la hotplug, deschiderea listei sau dupa un minut."""
	acum = time.time()
	with _zavor:
		e = _dosare.get(dosar)
		generatie = _generatie
	if e is not None and 0 <= acum - e[0] < 60:
		return e[1]
	nume = DOSARE_SIGLE if dosar == "picon" else (dosar,)
	montari = _montari_sigle()
	altele = [c % n for n in nume for c in CAI_SIGLE]
	altele.extend(os.path.join(m, n, "") for m in montari for n in nume)
	gasite, vazute = [], set()
	for cale in altele:
		cale = os.path.join(os.path.normpath(cale), "")
		if os.path.isdir(cale):
			cheie = os.path.normcase(os.path.realpath(cale))
			if cheie not in vazute:
				vazute.add(cheie)
				gasite.append(cale)
	with _zavor:
		if generatie == _generatie:
			_dosare[dosar] = (acum, gasite)
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


def _dosare_locuri():
	"""Dosarele de sigle ale locurilor adaugate de extensii (Components/HdsLocuriLista.py); acolo poate fi si JPEG."""
	try:
		from Components.HdsLocuriLista import dosareSigle
		return dosareSigle()
	except Exception:
		return []


def cauta_sigla(sref, dosar="picon", nume=None):
	"""Calea siglei unui serviciu, sau "" cand nu e niciuna. Dupa referinta, apoi dupa numele explicit sau aflat."""
	sref = str(sref or "")
	cheie = (sref, dosar, nume)
	acum = time.monotonic()
	with _zavor:
		mem = _cautari.get(cheie)
		if mem is not None:
			_cautari.move_to_end(cheie)
	if mem is not None and 0 <= acum - mem[0] < VIATA_CAUTARII:
		if not mem[1]:
			return _sigla_extensiei(sref, dosar)
		if fileExists(mem[1]):
			return mem[1]
	g = generatie_sigle()
	png = _cauta_locala(sref, dosar, nume)
	with _zavor:
		if g == _generatie:
			_cautari[cheie] = (acum, png)
			_cautari.move_to_end(cheie)
			while len(_cautari) > MAX_CAUTARI:
				_cautari.popitem(last=False)
	return png or _sigla_extensiei(sref, dosar)


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
	for candidat in nume_cautate_canal(nume_canal(sref) if nume is None else nume):
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


class Picon(Renderer):
	searchPaths = CAI_SIGLE

	def __init__(self):
		Renderer.__init__(self)
		self.path = "picon"
		self.nameCache = { }
		self.pngname = ""
		self.perType = False
		# vecini: textul atributului de skin (Components/HdsPiconBare); hdsAre: se vede acum o sigla adevarata
		self.vecini = ""
		self.hdsAre = False
		self.hdsSigleGeneratie = -1
		self.hdsSigleCeas = None
		try:
			from Components.HdsPiconBare import inregistreaza
			inregistreaza(self)
		except Exception as e:
			print("[Picon] setarea siglelor nu se urmareste: %s" % e)

	def applySkin(self, desktop, parent):
		attribs = [ ]
		for (attrib, value) in self.skinAttributes:
			if attrib == "path":
				self.path = value
			elif attrib == "defaultPerType":
				self.perType = value in ("1", "true", "yes")
			elif attrib == "vecini":
				self.vecini = value
			else:
				attribs.append((attrib,value))
		self.skinAttributes = attribs
		rez = Renderer.applySkin(self, desktop, parent)
		# sigla potrivita in caseta (blitScale), oricat de mare e fisierul
		try:
			self.instance.setScale(1)
		except Exception as e:
			print("[Picon] potrivirea in caseta: %s" % e)
		return rez

	GUI_WIDGET = ePixmap

	def changed(self, what):
		if self.instance:
			pngname = ""
			sref = ""
			if what[0] != self.CHANGED_CLEAR:
				sref = self.source.text or ""
				if sigle_pornite():
					try:
						from Components import HdsIptvSigle
						HdsIptvSigle.cereReferinte([sref])
						if self.hdsSigleCeas is None:
							from enigma import eTimer
							self.hdsSigleCeas = eTimer()
							self.hdsSigleCeas.callback.append(self.hdsSigleTic)
							self.hdsSigleCeas.start(1500, False)
					except Exception:
						pass
					pngname = cauta_sigla(sref, self.path)
			are = pngname != ""
			if pngname == "": # no picon for service found
				pngname = self.implicita(sref)
			if self.pngname != pngname:
				if pngname.lower().endswith(".jpg"):
					from enigma import loadJPG
					pixmap = loadJPG(pngname)
					if pixmap:
						self.instance.setPixmap(pixmap)
					else:
						are = False
						pngname = self.implicita(sref)
						self.instance.setPixmapFromFile(pngname)
				else:
					self.instance.setPixmapFromFile(pngname)
				self.pngname = pngname
			if are != self.hdsAre:
				self.hdsAre = are
				if self.vecini:
					_anunta(self)

	def hdsSigleTic(self):
		try:
			from Components import HdsIptvSigle
			generatie = (generatie_sigle(), HdsIptvSigle.generatie())
			if generatie != self.hdsSigleGeneratie:
				self.hdsSigleGeneratie = generatie
				self.nameCache.clear()
				self.pngname = ""
				self.changed((self.CHANGED_DEFAULT,))
		except Exception:
			pass

	def onShow(self):
		Renderer.onShow(self)
		if self.hdsSigleCeas is not None:
			self.hdsSigleCeas.start(1500, False)
		self.hdsSigleTic()

	def onHide(self):
		Renderer.onHide(self)
		if self.hdsSigleCeas is not None:
			self.hdsSigleCeas.stop()

	def preWidgetRemove(self, instance):
		if self.hdsSigleCeas is not None:
			self.hdsSigleCeas.stop()

	def implicita(self, sref):
		"""Imaginea pentru serviciul fara sigla: dupa tip (defaultPerType), altfel picon_default."""
		if self.perType and sref:
			campuri = sref.split(":")
			fel = "radio" if len(campuri) > 2 and campuri[2] in TIPURI_RADIO else "tv"
			cheie = "default_" + fel
			png = self.nameCache.get(cheie)
			if png is None:
				tmp = resolveFilename(SCOPE_CURRENT_SKIN, "picon_default_%s.png" % fel)
				png = tmp if fileExists(tmp) else ""
				self.nameCache[cheie] = png
			if png:
				return png
		pngname = self.nameCache.get("default", "")
		if pngname == "": # no default yet in cache..
			pngname = self.findPicon("picon_default")
			if pngname == "":
				tmp = resolveFilename(SCOPE_CURRENT_SKIN, "picon_default.png")
				if fileExists(tmp):
					pngname = tmp
				else:
					pngname = resolveFilename(SCOPE_SKIN_IMAGE, "skin_default/picon_default.png")
			self.nameCache["default"] = pngname
		return pngname

	def findPicon(self, serviceName):
		for path in self.searchPaths:
			pngname = (path % self.path) + serviceName + ".png"
			if fileExists(pngname):
				return pngname
		return ""

def getPiconName(serviceRef):
	"""Numele cerut de pluginuri: calea siglei unui serviciu (text), "" cand nu e niciuna."""
	if not isinstance(serviceRef, str):
		serviceRef = serviceRef.toString() if hasattr(serviceRef, "toString") else str(serviceRef)
	return cauta_sigla(serviceRef) or ""
