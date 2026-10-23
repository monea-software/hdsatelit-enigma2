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
from .Renderer import Renderer
from enigma import ePixmap, eEnv
from Tools.Directories import fileExists, SCOPE_SKIN_IMAGE, SCOPE_CURRENT_SKIN, resolveFilename

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

	def applySkin(self, desktop, parent):
		attribs = [ ]
		for (attrib, value) in self.skinAttributes:
			if attrib == "path":
				self.path = value
			elif attrib == "defaultPerType":
				self.perType = value in ("1", "true", "yes")
			else:
				attribs.append((attrib,value))
		self.skinAttributes = attribs
		return Renderer.applySkin(self, desktop, parent)

	GUI_WIDGET = ePixmap

	def changed(self, what):
		if self.instance:
			pngname = ""
			sref = ""
			if what[0] != self.CHANGED_CLEAR:
				sref = self.source.text or ""
				pngname = self.nameCache.get(sref, "")
				if pngname == "":
					pngname = cauta_sigla(sref, self.path)
					if pngname != "":
						if len(self.nameCache) > 256:
							self.nameCache.clear()
						self.nameCache[sref] = pngname
			if pngname == "": # no picon for service found
				pngname = self.implicita(sref)
			if self.pngname != pngname:
				self.instance.setPixmapFromFile(pngname)
				self.pngname = pngname

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
