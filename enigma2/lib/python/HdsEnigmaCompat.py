# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
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
- RT_HALIGN_BIDI (= alinierea implicita);
- eStreamServer (0.7.8: getInstance; getConnectedClients, stopStreamClient, stopStream): serverul de flux de pe portul
  8001 al imaginii e scris in Python (Hds/DabT2/server8001.py), nu in C++, deci numele lipsea. Il cer temele straine
  (convertorul ClientsStreaming, pictograma "stream" din addon-ul ServiceInfoBar), pluginurile si cateva module ale
  noastre. Lista are numai clientii din retea: releele receptorului (Stream Relay pentru televizor, DAB+, DVB-T2) sunt
  felul in care televizorul reda acele canale, nu clienti (OE-Alliance le numara si pe ele, de pe 127.0.0.1). La coada,
  telefoanele cu un canal transcodat pe 8002 (Vu+ cu codor), cu semnul 1 al codorului, ca la OE-Alliance.
"""

_PROC_VMPEG = "/proc/stb/vmpeg/0/"
_SERVER_FLUX = "Hds.DabT2.server8001"


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


def _serverFlux():
	"""Modulul serverului de flux, numai daca l-a incarcat deja imaginea (fara import: enigma.py e inca la jumatate cand
	se pune stratul, iar un plugin care cheama mai devreme primeste lista goala, ca la un server fara clienti)."""
	import sys
	return sys.modules.get(_SERVER_FLUX)


_PROC_TCP = ("/proc/net/tcp", "/proc/net/tcp6")
_PORT_TRANSCODARE = 8002
_TRANSCODARE = "Plugins.Extensions.HdsWebControl.flux_transcodare_web"


def _adresaHex(text):
	"""Adresa din /proc/net/tcp (cuvinte de 32 de biti in ordinea masinii, little-endian pe receptoare) ca text."""
	import socket
	b = bytes.fromhex(text)
	b = b"".join(b[i:i + 4][::-1] for i in range(0, len(b), 4))
	if len(b) == 16 and b[:12] == b"\0" * 10 + b"\xff\xff":
		b = b[12:]
	return socket.inet_ntop(socket.AF_INET if len(b) == 4 else socket.AF_INET6, b)


def _clientiTranscodare():
	"""[(adresa, referinta, 1)] pentru telefoanele care primesc un canal transcodat pe 8002 (transtreamproxy, Vu+ cu
	codor; legaturile stabilite din /proc/net/tcp si tcp6, fara cele de pe receptor). Referinta e a sesiunii de
	transcodare (HdsWebControl/flux_transcodare_web.py) cand e una singura, altfel goala. 1 = cu codorul, ca la OE-Alliance.
	Ca acestea sa se numere ca inainte in HdsCommon.stream_clients (care le citea din /proc cat lipsea eStreamServer)."""
	import sys
	rez = []
	for cale in _PROC_TCP:
		text = _citeste(cale)
		for rand in (text or "").splitlines()[1:]:
			parti = rand.split()
			if len(parti) < 4 or parti[3] != "01":
				continue
			try:
				adresa, port = parti[1].rsplit(":", 1)
				if int(port, 16) != _PORT_TRANSCODARE:
					continue
				client = _adresaHex(parti[2].rsplit(":", 1)[0])
			except (ValueError, OSError):
				continue
			if client.startswith("127.") or client == "::1":
				continue
			rez.append(client)
	m = sys.modules.get(_TRANSCODARE)
	sesiuni = list(getattr(m, "_SESIUNI", None) or []) if m is not None else []
	ref = str(getattr(sesiuni[0], "ref", "") or "") if len(sesiuni) == 1 else ""
	return [(client, ref, 1) for client in rez]


def _faStreamServer():
	class eStreamServer(object):
		"""Ca eStreamServer din OE-Alliance, peste serverul Python de pe 8001 (Hds/DabT2/server8001.py). Se cheama din
		firul enigma2, ca acolo."""
		_instanta = None

		@classmethod
		def getInstance(cls):
			if cls._instanta is None:
				cls._instanta = cls()
			return cls._instanta

		def getConnectedClients(self):
			"""[(adresa, referinta, 0)] pentru fiecare client din retea al serverului 8001 (0 = fara transcodare), apoi
			[(adresa, referinta, 1)] pentru telefoanele cu canal transcodat pe 8002."""
			m = _serverFlux()
			try:
				rez = list(m.clienti_din_retea()) if m is not None else []
			except Exception:
				rez = []
			try:
				rez.extend(_clientiTranscodare())
			except Exception:
				pass
			return rez

		def stopStreamClient(self, remotehost, serviceref):
			m = _serverFlux()
			try:
				return bool(m.opreste_clientul(remotehost, serviceref)) if m is not None else False
			except Exception:
				return False

		def stopStream(self):
			"""Opreste primul client (ca la OE-Alliance), nu pe toti."""
			m = _serverFlux()
			try:
				if m is not None:
					m.opreste_clientul()
			except Exception:
				pass

	return eStreamServer


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
	# evNewProgramInfo: din 0.7.5 in nucleu (lib/service/iservice.h); ramane aici pentru nucleele mai vechi
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
	pune("eStreamServer", _faStreamServer())
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
