# Modificat de moneasoftware.com si hdsatelit.com, 2026
##
## Picon renderer by Gruffy .. some speedups by Ghost
##
# Siglele se cauta in dosarele fixe si pe toate discurile montate.
# Intai se incearca referinta si variantele ei, apoi numele normalizat,
# inclusiv fara terminatia de calitate. Lista, web-ul si afisajul color
# folosesc cauta_sigla() din Tools/PiconResolver.py. Fara sigla se arata picon_default.png
# (in skinul HDSatelit un dreptunghi transparent: caseta ramane
# goala, fara semn care sa para o eroare). Cu atributul de skin defaultPerType="1" lipsa se arata cu
# picon_default_tv.png sau picon_default_radio.png din skinul activ, cand exista.
#
# Sigla se potriveste in caseta din skin (ePixmap.setScale): un picon obisnuit de 220x132 intra intreg si in casetele de
# 110x66 sau 150x90 (fara potrivire se vedea numai coltul lui din stanga sus).
# Setarea "Siglele canalelor (piconuri)" (config.usage.hds_piconuri, din fabrica da): oprita, nicio sigla nu se cauta
# si caseta ramane goala (picon_default). Schimbarea setarii se vede pe loc in ecranele deschise (Components/HdsPiconBare).
# Atributul de skin vecini="x,y,l,i=x2,l2|..." (Components/HdsPiconBare): elementele ecranului cu position="x,y" si
# size="l,i" se muta la x2 cu latimea l2 numai cat se vede o sigla (setarea pornita si sigla gasita sau picon_default al omului); fara sigla
# raman la locul lor din skin, deci nu ramane loc gol in stanga.
# picon_default.png pus de om intr-un dosar de sigle (setarea pornita) e tot o imagine vazuta in caseta: numara ca sigla
# pentru vecini, altfel numele se scria peste ea (TODO 24.11 14:50). Cel din tema (caseta goala) nu numara.
from .Renderer import Renderer
from enigma import ePixmap, eEnv
from Tools.Directories import fileExists, SCOPE_SKIN_IMAGE, SCOPE_CURRENT_SKIN, resolveFilename
from Tools.PiconResolver import (CAI_SIGLE, RADACINI_MEDIA, DOSARE_SIGLE,
	searchPaths, TIPURI_FLUX, TIPURI_RADIO, sigle_pornite, nume_sigle,
	nume_dupa_canal, nume_cautate_canal, nume_canal, generatie_sigle,
	dosare_sigle, getPiconPath, resetPiconPath, cauta_sigla, getPiconName as _getPiconName)
from Tools import PiconResolver as _PiconResolver
try:
	from Tools.PiconResolver import revizie_index, sigla_din_index, cere_index, nume_memorat
except ImportError:
	revizie_index = sigla_din_index = cere_index = nume_memorat = None

# Numele de modul pe care le importa pluginurile scrise pentru imaginile OE-Alliance (11.11.2026; de pilda
# "from Components.Renderer.Picon import getPiconName"). Cautarea e tot a noastra (Tools/PiconResolver.py); mode
# ("infobar" / "channelselection") se primeste, dar imaginea are aceleasi sigle peste tot.
lastPiconPath = None
piconPathCache = {}


def getPiconName(serviceName, mode=None):
	return _getPiconName(serviceName)


def getChannelSelectionPiconName(serviceName):
	return _getPiconName(serviceName)


def findPicon(serviceName, mode=None):
	"""calea siglei cu numele de fisier dat (fara .png), din dosarele de sigle; sir gol cand nu e"""
	for path in dosare_sigle("picon"):
		pngname = path + serviceName + ".png"
		if fileExists(pngname):
			return pngname
	return ""


def setPiconPath(key, path):
	global lastPiconPath
	piconPathCache[key] = path
	if key in (None, "infobar"):
		lastPiconPath = path


def getDefaultPiconPath():
	for path in dosare_sigle("picon"):
		return path.rstrip("/")
	return None


def initPiconPaths():
	"""dosarele de sigle se afla singure (discurile montate); pentru pluginurile care o cheama"""
	resetPiconPath()


def _implicita_om_din_index(dosar):
	"""LCP1: calea lui picon_default.png din indexul din memorie al siglelor (Tools/PiconResolver, PCN6: numai dosarele
	locale, citite de firul de fundal), sau "". Fara disc si fara zavor; indexul altei generatii nu conteaza."""
	try:
		R = _PiconResolver
		e = R._index.get(dosar)
		if e is None or e[0] != R._generatie:
			return ""
		for tabela in e[2]:
			cale = tabela.get("picon_default")
			if cale:
				return cale
	except Exception as ex:
		print("[Picon] picon_default din index: %s" % ex)
	return ""


def _anunta(r):
	"""Sigla s-a aratat sau s-a ascuns: vecinii ei (Components/HdsPiconBare) la locul lor."""
	try:
		from Components.HdsPiconBare import schimbat
		schimbat(r)
	except Exception as e:
		print("[Picon] vecinii: %s" % e)

class Picon(Renderer):
	_dosar_sigle = "picon"
	searchPaths = CAI_SIGLE

	def __init__(self):
		Renderer.__init__(self)
		self.path = self._dosar_sigle
		self.nameCache = { }
		self.pngname = ""
		self.perType = False
		# vecini: textul atributului de skin (Components/HdsPiconBare); hdsAre: se vede acum o sigla in caseta (gasita
		# pentru canal sau picon_default al omului); hdsAdevarata: sigla gasita pentru canal (ticul indexului o cauta
		# cat timp e False); hdsImplicitaOm: imaginea data de implicita() vine din dosarele de sigle ale omului
		self.vecini = ""
		self.hdsAre = False
		self.hdsAdevarata = False
		self.hdsImplicitaOm = False
		self.hdsSigleGeneratie = -1
		self.hdsSigleCeas = None
		# PCN6: referinta afisata si revizia indexului de sigle (Tools/PiconResolver.py) vazuta la ultimul tic
		self.hdsSref = ""
		self.hdsIndexRevizie = -1
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
			elif attrib == "mode":
				# imaginile OE-Alliance: dosarul de sigle al barei sau al listei; la noi aceleasi sigle
				self.mode = value
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
			self.hdsSref = ""
			if what[0] != self.CHANGED_CLEAR:
				sref = self.source.text or ""
				self.hdsSref = sref
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
			self.hdsAdevarata = are
			if pngname == "": # no picon for service found
				pngname = self.implicita(sref)
				are = self.hdsImplicitaOm
			if self.pngname != pngname:
				if pngname.lower().endswith(".jpg"):
					from enigma import loadJPG
					pixmap = loadJPG(pngname)
					if pixmap:
						self.instance.setPixmap(pixmap)
					else:
						self.hdsAdevarata = False
						pngname = self.implicita(sref)
						are = self.hdsImplicitaOm
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
				return
		except Exception:
			pass
		self.hdsIndexTic()

	def hdsIndexTic(self):
		"""PCN6: cat timp caseta arata imaginea implicita, o sigla aparuta in indexul din memorie se arata fara schimbarea
		canalului. Numai memorie: fara cautare, fara fileExists, fara changed(); se incarca o singura data sigla gasita
		(indexul are numai dosare locale)."""
		try:
			if self.hdsAdevarata or not self.instance or not self.hdsSref or sigla_din_index is None or not sigle_pornite():
				return
			revizie = revizie_index()
			if revizie != self.hdsIndexRevizie:
				self.hdsIndexRevizie = revizie
				# numele canalului numai din memorie (aflat la cautarea de la changed), niciodata cerut aici
				png = sigla_din_index(self.hdsSref, self.path, nume_memorat(self.hdsSref, self.path))
				if png and png != self.pngname:
					self.instance.setPixmapFromFile(png)
					self.pngname = png
					self.hdsAdevarata = True
					if not self.hdsAre:
						self.hdsAre = True
						if self.vecini:
							_anunta(self)
					return
				# LCP1: nicio sigla pentru canal, dar picon_default.png al omului a aparut in index: se arata acum, fara
				# schimbarea canalului (implicita() ia aici numai din memorie: "default_om" e deja cautat)
				if not self.hdsImplicitaOm and self.nameCache.get("default_om") == "" and _implicita_om_din_index(self.path):
					png = self.implicita(self.hdsSref)
					if self.hdsImplicitaOm and png != self.pngname:
						self.instance.setPixmapFromFile(png)
						self.pngname = png
						if not self.hdsAre:
							self.hdsAre = True
							if self.vecini:
								_anunta(self)
						return
			cere_index(self.path)
		except Exception as e:
			print("[Picon] indexul siglelor: %s" % e)

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
		"""Imaginea pentru serviciul fara sigla: dupa tip (defaultPerType), altfel picon_default. hdsImplicitaOm spune daca
		vine din dosarele de sigle ale omului (atunci numara ca sigla); cu setarea oprita numai cea din tema, ca in
		imaginile OE-Alliance. Rezultatul se tine minte in nameCache (fara IO la schimbarile urmatoare de canal)."""
		self.hdsImplicitaOm = False
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
		if sigle_pornite():
			pngname = self.nameCache.get("default_om")
			if pngname is None:
				pngname = self.findPicon("picon_default")
				self.nameCache["default_om"] = pngname
			if not pngname:
				# LCP1: picon_default.png pus de om intr-un dosar de sigle deja cautat se vede la canalul urmator, din indexul
				# din memorie (numai memorie; indexul il reciteste firul lui de fundal), nu abia la generatia urmatoare
				pngname = _implicita_om_din_index(self.path)
				if pngname:
					self.nameCache["default_om"] = pngname
			if pngname:
				self.hdsImplicitaOm = True
				return pngname
		pngname = self.nameCache.get("default", "")
		if pngname == "": # no default yet in cache..
			tmp = resolveFilename(SCOPE_CURRENT_SKIN, "picon_default.png")
			if fileExists(tmp):
				# tema HDSatelit la 2K: picon_default desenat la 200x120 (HDSatelit/2k/), nu marit
				try:
					import skin
					tmp = skin.caleLaEcran(tmp)
				except Exception:
					pass
				pngname = tmp
			else:
				pngname = resolveFilename(SCOPE_SKIN_IMAGE, "skin_default/picon_default.png")
			self.nameCache["default"] = pngname
		return pngname

	def findPicon(self, serviceName):
		for path in dosare_sigle(self.path):
			pngname = path + serviceName + ".png"
			if fileExists(pngname):
				return pngname
		return ""
