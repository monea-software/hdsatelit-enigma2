# Modificat de moneasoftware.com si hdsatelit.com, 2026
##
## Picon renderer by Gruffy .. some speedups by Ghost
##
# Siglele se cauta in dosarele folosite de toate imaginile (memoria interna, discul, stickul, cardul, /picon), dupa
# numele facut din referinta; daca lipseste, si cu tipul serviciului pus pe 1 (canalele HD 0x19 au adesea sigla sub
# 1_0_1_...) si, la fluxuri, cu partea DVB a referintei. Aceeasi cautare o folosesc si alte module (interfata web):
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

# dosarele de sigle, in ordinea cautarii; %s = numele dosarului (implicit „picon”)
CAI_SIGLE = (eEnv.resolve('${datadir}/enigma2/%s/'),
	'/media/hdd/%s/',
	'/media/usb/%s/',
	'/media/mmc/%s/',
	'/media/cf/%s/',
	'/%s/')

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
	return nume


_dosare = {}


def dosare_sigle(dosar="picon"):
	"""Dosarele de sigle care exista acum; lista se reface cel mult o data pe minut (un stick pus mai tarziu apare),
	ca o sigla lipsa sa nu intrebe la fiecare schimbare de canal un disc care doarme."""
	import os
	import time
	acum = time.time()
	e = _dosare.get(dosar)
	if e is not None and 0 <= acum - e[0] < 60:
		return e[1]
	gasite = [cale % dosar for cale in CAI_SIGLE if os.path.isdir(cale % dosar)]
	_dosare[dosar] = (acum, gasite)
	return gasite


def cauta_sigla(sref, dosar="picon"):
	"""Calea siglei unui serviciu, sau "" cand nu e niciuna. Numai verificari de existenta a fisierelor."""
	cai = dosare_sigle(dosar)
	if not cai:
		return ""
	for nume in nume_sigle(sref):
		for cale in cai:
			png = cale + nume + ".png"
			if fileExists(png):
				return png
	return ""


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
					pngname = self.nameCache.get(sref, "")
					# o sigla stearsa intre timp (dosarul scos, stickul luat) nu mai tine locul pe bare
					if pngname != "" and not fileExists(pngname):
						del self.nameCache[sref]
						pngname = ""
					if pngname == "":
						pngname = cauta_sigla(sref, self.path)
						if pngname != "":
							if len(self.nameCache) > 256:
								self.nameCache.clear()
							self.nameCache[sref] = pngname
			are = pngname != ""
			if pngname == "": # no picon for service found
				pngname = self.implicita(sref)
			if self.pngname != pngname:
				self.instance.setPixmapFromFile(pngname)
				self.pngname = pngname
			if are != self.hdsAre:
				self.hdsAre = are
				if self.vecini:
					_anunta(self)

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
