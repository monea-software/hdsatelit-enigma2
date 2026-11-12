# Modificat de moneasoftware.com si hdsatelit.com, 2026
"""Stratul de compatibilitate al modulului enigma pentru pluginurile scrise pentru interfata comuna enigma2.

Se cheama o singura data, din coada lui enigma.py (o pune acolo enigma_py_patcher.py la constructie):
aplica(globals() ale modulului enigma). Reguli:
- pune numai nume care LIPSESC; nimic din ce exporta deja C++-ul nu se inlocuieste;
- pune numai ce spune adevarul pe receptorul nostru. Numele pe care pluginurile le cauta ca sa afle daca imaginea
  stie ceva (loadSVG = desen SVG, setAnimation_* = animatiile ferestrelor) NU se pun: un plugin le-ar crede si s-ar
  strica (YouTube ar cere temele SVG);
- nu importa enigma (enigma.py e inca la jumatate cand se cheama); primeste globals() ale lui.
Ce pune (de ce, cine il cere):
- eAVControl (getInstance; getResolutionX/Y, getAspect, getFrameRate, getProgressive, getVideoMode din /proc, restul
  trimis lui eAVSwitch): pluginurile IPTV (XKlass, XStreamity) si altele il cer cand nu gasesc eAVSwitch;
- getE2Rev (versiunea), getPeerStreamingBoxes (lista goala: nu cautam alte receptoare in retea): interfata web straina, Partnerbox
  le importa la pornire si fara ele nu pornesc deloc;
- eListbox.goTop/goBottom/goLineUp/goLineDown/goPageUp/goPageDown/goLeft/goRight/goPageLeft/goPageRight/goFirst/goLast,
  numele noi ale directiilor (moveBottom, movePageUp...) si getCurrentPage: listele pluginurilor noi;
- pNavigation.isRealRecording... (felurile inregistrarilor, ca numere), evenimentele iPlayableService /
  iRecordableService pe care receptorul nostru nu le trimite (numere care nu se intalnesc niciodata: pluginul care le
  asculta nu mai cade la deschidere, iar evenimentul nu vine, ca pana acum);
- eDVBDB.setLoadUnlinkedUserbouquets si saveIptvServicelist (fara efect: listele noastre nu au aceste parti);
- RT_HALIGN_BIDI (= alinierea implicita).
"""

_PROC_VMPEG = "/proc/stb/vmpeg/0/"


def _citeste(cale):
	try:
		with open(cale) as f:
			return f.read().strip()
	except (IOError, OSError):
		return None


def _int(cale, baza, implicit):
	text = _citeste(cale)
	if not text:
		return implicit
	try:
		return int(text, baza)
	except ValueError:
		return implicit


def _faAVControl(g):
	eAVSwitch = g.get("eAVSwitch")

	class eAVControl(object):
		"""Ce citesc pluginurile despre imaginea de acum, din /proc ca decodorul; restul merge la eAVSwitch."""
		_instanta = None

		@classmethod
		def getInstance(cls):
			if cls._instanta is None:
				cls._instanta = cls()
			return cls._instanta

		def getResolutionX(self, defaultVal=0, flags=0):
			return _int(_PROC_VMPEG + "xres", 16, defaultVal)

		def getResolutionY(self, defaultVal=0, flags=0):
			return _int(_PROC_VMPEG + "yres", 16, defaultVal)

		def getAspect(self, defaultVal=0, flags=0):
			return _int(_PROC_VMPEG + "aspect", 16, defaultVal)

		def getFrameRate(self, defaultVal=50000, flags=0):
			return _int(_PROC_VMPEG + "framerate", 10, defaultVal)

		def getProgressive(self, flags=0):
			return bool(_int(_PROC_VMPEG + "progressive", 16, 0))

		def getVideoMode(self, defaultVal="", flags=0):
			return _citeste("/proc/stb/video/videomode") or defaultVal

		def __getattr__(self, nume):
			if nume.startswith("_") or eAVSwitch is None:
				raise AttributeError(nume)
			return getattr(eAVSwitch.getInstance(), nume)

	return eAVControl


def _listbox(eListbox):
	"""Numele noi ale directiilor, puse pe cele pe care le avem (lista noastra e verticala: stanga/dreapta = cate un rand)."""
	directii = {
		"moveBottom": "moveEnd", "moveFirst": "moveTop", "moveLast": "moveEnd",
		"movePageUp": "pageUp", "movePageDown": "pageDown",
		"moveLeft": "moveUp", "moveRight": "moveDown",
		"movePageLeft": "pageUp", "movePageRight": "pageDown",
		"refresh": "justCheck",
	}
	for nou, vechi in directii.items():
		if not hasattr(eListbox, nou) and hasattr(eListbox, vechi):
			setattr(eListbox, nou, getattr(eListbox, vechi))
	pasi = {
		"goTop": "moveTop", "goBottom": "moveBottom", "goLineUp": "moveUp", "goLineDown": "moveDown",
		"goPageUp": "movePageUp", "goPageDown": "movePageDown", "goLeft": "moveLeft", "goRight": "moveRight",
		"goPageLeft": "movePageLeft", "goPageRight": "movePageRight", "goFirst": "moveFirst", "goLast": "moveLast",
	}
	for metoda, directie in pasi.items():
		if not hasattr(eListbox, metoda) and hasattr(eListbox, directie):
			setattr(eListbox, metoda, (lambda d: lambda self: self.moveSelection(getattr(eListbox, d)))(directie))
	if not hasattr(eListbox, "getCurrentPage") and hasattr(eListbox, "getItemsPerPage"):
		def getCurrentPage(self):
			pe_pagina = self.getItemsPerPage()
			return self.getCurrentIndex() // pe_pagina + 1 if pe_pagina > 0 else 0
		eListbox.getCurrentPage = getCurrentPage


# felurile inregistrarilor, cu aceleasi numere ca in interfata comuna (biti)
_FELURI_INREGISTRARE = (
	("isRealRecording", 0x01), ("isStreaming", 0x02), ("isPseudoRecording", 0x04), ("isUnknownRecording", 0x08),
	("isFromTimer", 0x10), ("isFromInstantRecording", 0x20), ("isFromEPGrefresh", 0x40),
	("isFromSpecialJumpFastZap", 0x80), ("isAnyRecording", 0xFF),
)

# evenimentele pe care receptorul nostru nu le trimite; primesc numere negative, care nu vin niciodata
_EVENIMENTE = {
	"iPlayableService": ("evNewProgramInfo", "evGstreamerPlayStarted", "evFccFailed", "evUpdateTags", "evUpdateIDv3Cover",
		"evGstreamerStart", "evResumed", "evStreamError", "evTimeshiftError"),
	"iRecordableService": ("evTuneStart", "evPvrTuneStart", "evRecordAborted", "evGstRecordEnded", "evPvrEof",
		"errNoCiConnected", "errNoProgramInfo"),
}


def aplica(g):
	"""Pune in g (globals() ale lui enigma) numele care lipsesc. Intoarce lista numelor puse (pentru jurnal si probe)."""
	puse = []

	def pune(nume, valoare):
		if nume not in g:
			g[nume] = valoare
			puse.append(nume)

	pune("eAVControl", _faAVControl(g))
	versiune = g.get("getEnigmaVersionString")
	pune("getE2Rev", (lambda: versiune()) if versiune else (lambda: ""))
	pune("getPeerStreamingBoxes", lambda: [])
	if "RT_HALIGN_LEFT" in g:
		pune("RT_HALIGN_BIDI", g["RT_HALIGN_LEFT"])

	eListbox = g.get("eListbox")
	if eListbox is not None:
		inainte = set(dir(eListbox))
		_listbox(eListbox)
		puse.extend("eListbox." + x for x in sorted(set(dir(eListbox)) - inainte))

	pNavigation = g.get("pNavigation")
	if pNavigation is not None:
		for nume, valoare in _FELURI_INREGISTRARE:
			if not hasattr(pNavigation, nume):
				setattr(pNavigation, nume, valoare)
				puse.append("pNavigation." + nume)

	numar = -1000
	for clasa, nume_ev in _EVENIMENTE.items():
		c = g.get(clasa)
		if c is None:
			continue
		for nume in nume_ev:
			numar -= 1
			if not hasattr(c, nume):
				setattr(c, nume, numar)
				puse.append(clasa + "." + nume)

	eDVBDB = g.get("eDVBDB")
	if eDVBDB is not None:
		for nume in ("setLoadUnlinkedUserbouquets", "saveIptvServicelist"):
			if not hasattr(eDVBDB, nume):
				setattr(eDVBDB, nume, lambda self, *a: None)
				puse.append("eDVBDB." + nume)
	return puse
