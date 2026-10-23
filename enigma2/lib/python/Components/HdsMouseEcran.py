# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsMouseEcran.py: mouse-ul pe ecranul receptorului. Unde a cazut clicul in ecranul deschis pe televizor si ce se face
# acolo. Folosit de interfata web (Plugins/Extensions/HdsWebControl/mouse_web.py, POST /api/mouse: clicul din caseta
# "Ecranul receptorului" a panoului, de pe captura, din imaginea live si de pe ecranul intreg). Scris pe baza mouse-ului
# emulatorului de pe PC (lib/gdi/sdl.cpp si pluginul lui de emulator), cu aceleasi gesturi:
# - clic stanga pe un rand al unei liste: primul clic muta selectia pe randul de sub mouse; clic pe randul deja ales sau
#   dublu clic = OK (lista de canale, EPG, filme ...). In meniuri (ECRANE_MENIU si cele facute din ele, plus listele cu
#   "menu" in nume) primul clic alege si deschide, ca pe PC. In setari (ECRANE_SETARI: Setup, ConfigListScreen si cele
#   facute din ele, plus listele ConfigList) tot doi pasi, ca in liste: un clic gresit nu schimba o setare. Sub ultimul rand: nimic;
# - clic pe un buton cu nume cunoscut (key_red ... key_blue, key_menu, key_info, key_help, key_text, key_epg, key_ok,
#   key_exit, la fel cu button_/btn_ in fata sau red/green/... in nume): tasta lui. Butoanele au intaietate fata de liste;
# - clic sau tras pe bara de derulare a unei liste (fasia din dreapta, lata cat o face eListbox: latimea/16, intre 18 si
#   22 de pixeli, plus spatiul de 5 pixeli dinaintea ei): selectia sare in acelasi loc din lista (sus = primul rand,
#   jos = ultimul). Bara exista numai cand lista are mai multe randuri decat incap;
# - rotita: pe o lista de sub mouse, selectia urca sau coboara cate un rand; o rotire mare (PAS_PAGINA pasi deodata sau
#   mai multi) = o pagina. Fara lista sub mouse, tastele SUS/JOS (cel mult TASTE_ROTITA odata);
# - clic dreapta = IESIRE, clic pe rotita (mijloc) = tasta MENIU, la fel in emulator (sdl.cpp) si in pagina web (pe
#   telefon: glisarea spre dreapta si tasta Inapoi a telefonului = clic dreapta, atingerea tinuta = clic pe rotita).
#   De ce IESIRE la dreapta: Inapoi se foloseste mult mai des decat MENIU, deci
#   sta pe butonul cel mai la indemana.
# - tastatura din pagina web, unde nu e o tasta a telecomenzii: "pagina" (Page Up/Down) =
#   o pagina in lista principala a ecranului (cea mai mare lista vizibila), iar fara lista (la privit) canalul +/-;
#   "capat" (Home/End) = primul sau ultimul rand al listei principale (fara lista: nimic);
#   "text" = semnele scrise la tastatura (litere, cifre, spatiu; "\b" = Backspace). Cand pe televizor e deschis un camp
#   de text sau o cautare, adica tastatura receptorului e in modul ASCII (eRCInput kmAscii, pus de ecranele cu text:
#   cautarea de canale, cautarea setarilor, lista de canale, InputBox, tastatura de pe ecran, campurile ConfigText),
#   semnele intra ca de la o tastatura USB: prin actiunea "gotAsciiCode" a ecranului (aceeasi functie pe care o cheama
#   eActionMap pentru KEY_ASCII), iar Backspace sterge (KEY_BACKSPACE unde ecranul are "deleteBackward", altfel
#   semnul 8, pe care cautarile il sterg ca litera, ca la tastatura emulatorului). Altfel semnele sunt taste ale telecomenzii:
#   cifrele, M = MENIU, I = INFO, E = EPG, T = TELETEXT, spatiul = PAUZA, Backspace = IESIRE; celelalte litere, nimic.
#   De ce asa: codul semnului (getPrevAsciiCode) il pune numai C++-ul, din evenimentul tastaturii; din Python nu se
#   poate pune, deci pe durata apelului functia getPrevAsciiCode din modulul ecranului (si din Components.config, pentru
#   ConfigText) intoarce semnul nostru, apoi se pune la loc.
#
# Coordonatele sunt pixelii ecranului enigma2 (getDesktop(0).size(), 1920x1080 cu skinul HDSatelit), aceiasi cu pozitiile
# widget-urilor (getAbsolutePosition). Interfata web trimite procente si le transforma aici (dinProcente).
#
# FIRUL: totul ruleaza pe firul principal enigma2 (cererea HTTP vine din reactorul care e chiar bucla enigma2; un mouse
# USB legat la receptor ar veni tot pe acolo, cu aceeasi clasa MouseEcran). Tastele pleaca prin functia primita
# (apasa(cod)); fara ea, prin eRCMapper, ca telecomanda. Modulul nu importa nimic din enigma2 la incarcare, deci se
# probeaza pe PC cu ecrane si widget-uri false (orice obiect cu aceleasi metode).
import time

KEY_OK, KEY_EXIT, KEY_MENU, KEY_INFO, KEY_HELP, KEY_TEXT, KEY_EPG = 352, 174, 139, 358, 138, 388, 365
KEY_RED, KEY_GREEN, KEY_YELLOW, KEY_BLUE = 398, 399, 400, 401
KEY_UP, KEY_DOWN = 103, 108
KEY_CHANNELUP, KEY_CHANNELDOWN = 402, 403
KEY_BACKSPACE, KEY_PAUSE = 14, 119
# semnele tastaturii cand pe televizor nu e un camp de text: tastele telecomenzii (cifrele KEY_1..KEY_0 = 2..11)
TASTE_SEMNE = dict([(str(c), c + 1) for c in range(1, 10)] + [("0", 11), ("m", KEY_MENU), ("i", KEY_INFO),
	("e", KEY_EPG), ("t", KEY_TEXT), (" ", KEY_PAUSE), ("\b", KEY_EXIT)])
TEXT_MAXIM = 64         # cate semne primeste o cerere
# butoanele din ecrane, dupa nume: key_red, button_red, btn_red, red, red_pix ...; key_menu, key_info ...
CULORI = {"red": KEY_RED, "green": KEY_GREEN, "yellow": KEY_YELLOW, "blue": KEY_BLUE}
ALTE = {"menu": KEY_MENU, "info": KEY_INFO, "help": KEY_HELP, "text": KEY_TEXT, "epg": KEY_EPG,
	"ok": KEY_OK, "exit": KEY_EXIT, "cancel": KEY_EXIT}
# meniurile: primul clic pe un rand alege si deschide (si ecranele facute din ele: se cauta in toata ierarhia clasei)
ECRANE_MENIU = ("Menu", "ChoiceBox", "MessageBox", "FixedMenu", "ChannelContextMenu", "MovieContextMenu",
	"HdsMeniuEcranPornire", "HelpMenu")
# setarile: doi pasi, ca in liste (clic = alege, clic pe randul ales = OK); au intaietate fata de meniuri si de numele
# "menu" al listei. Aici intra si listele ConfigList (Components/ConfigList.py) din orice ecran.
ECRANE_SETARI = ("ConfigListScreen", "Setup")
LISTE_SETARI = ("ConfigList",)
DUBLU_CLIC_S = 1.0     # al doilea clic al unui dublu clic, venit pe alt ecran in atat timp, nu mai apasa nimic
PAS_PAGINA = 3         # rotita: atatia pasi deodata (o rotire mare) = o pagina
PASI_MAXIM = 12        # cati pasi se primesc odata (restul se arunca: o rotita rapida nu trimite zeci de taste)
TASTE_ROTITA = 3       # fara lista sub mouse: cel mult atatea taste SUS/JOS la o cerere
LATIME_BARA = (18, 22)  # latimea barii de derulare a lui eListbox (elistbox.cpp, updateScrollBar): latimea/16 in aceste limite
SPATIU_BARA = 5         # spatiul dintre randuri si bara (acelasi loc in elistbox.cpp)
GESTURI = ("clic", "dublu", "drag", "dragend", "rotita", "dreapta", "mijloc", "pagina", "capat", "text")


def jurnal(text):
	print("[HdsMouseEcran] %s" % text)


def tastaButon(nume):
	"""Codul tastei unui buton dupa numele lui din ecran, sau None."""
	n = (nume or "").lower()
	for prefix in ("key_", "button_", "btn_"):
		if n.startswith(prefix):
			baza = n[len(prefix):].split("_")[0]
			return CULORI.get(baza) or ALTE.get(baza)
	return CULORI.get(n.split("_")[0])


def apasaTasta(cod):
	"""Tasta ca de pe telecomanda (eRCMapper.inject, cu numele dispozitivului nativ); fara eRCMapper, prin harta de
	actiuni. Interfata web da in loc functia ei (plugin.py, _trimiteTasta), care face acelasi lucru."""
	try:
		from enigma import eRCMapper
		m = eRCMapper.getInstance()
	except Exception:
		m = None
	if m is not None:
		m.inject(cod, 0)
		m.inject(cod, 1)
		return
	from enigma import eActionMap
	harta = eActionMap.getInstance()
	harta.keyPressed("SDL", cod, 0)
	harta.keyPressed("SDL", cod, 1)


def modAscii():
	"""True cand tastatura receptorului e in modul ASCII (un camp de text sau o cautare pe ecran), ca pentru o tastatura
	USB; False altfel sau fara enigma (pe PC)."""
	try:
		from enigma import eRCInput
		rc = eRCInput.getInstance()
		return rc is not None and rc.getKeyboardMode() != rc.kmNone
	except Exception:
		return False


def actiuneAscii(ecran, nume="gotAsciiCode"):
	"""Functia actiunii `nume` ("gotAsciiCode", "deleteBackward") dintr-o harta de actiuni pornita a ecranului
	(ActionMap, NumberActionMap ...), sau None. Cea cu prioritatea cea mai buna (numarul cel mai mic), ca in eActionMap."""
	gasite = []
	for comp in list(ecran.values()):
		actiuni = getattr(comp, "actions", None)
		if not isinstance(actiuni, dict) or nume not in actiuni:
			continue
		if not getattr(comp, "enabled", True):
			continue
		gasite.append((getattr(comp, "prio", 0) or 0, actiuni[nume]))
	if not gasite:
		return None
	gasite.sort(key=lambda g: g[0])
	return gasite[0][1]


def scrieAscii(functie, cod, module=()):
	"""Cheama functia actiunii "gotAsciiCode" cu semnul `cod`: pe durata apelului getPrevAsciiCode din modulul ei si din
	`module` (Components.config) intoarce `cod`."""
	f = getattr(functie, "__func__", functie)
	locuri = [getattr(f, "__globals__", None)] + [getattr(m, "__dict__", None) for m in module]
	vechi = []
	for g in locuri:
		if g is not None and "getPrevAsciiCode" in g and not any(g is v[0] for v in vechi):
			vechi.append((g, g["getPrevAsciiCode"]))
			g["getPrevAsciiCode"] = lambda: cod
	try:
		functie()
	finally:
		for g, v in vechi:
			g["getPrevAsciiCode"] = v


def marimeEcran():
	"""(latime, inaltime) ecranului enigma2 in pixeli; (1920, 1080) cand nu se poate afla (pe PC)."""
	try:
		from enigma import getDesktop
		s = getDesktop(0).size()
		if s.width() > 0 and s.height() > 0:
			return s.width(), s.height()
	except Exception:
		pass
	return 1920, 1080


def dinProcente(xp, yp, marime=None):
	"""Procentele din ecran (0-100, cu zecimale) -> pixelii ecranului enigma2."""
	w, h = marime or marimeEcran()
	x = int(round(min(max(float(xp), 0.0), 100.0) * w / 100.0))
	y = int(round(min(max(float(yp), 0.0), 100.0) * h / 100.0))
	return min(x, w - 1), min(y, h - 1)


def _dreptunghi(inst):
	p = inst.getAbsolutePosition()
	s = inst.size()
	return p.x(), p.y(), s.width(), s.height()


def _numeSursa(ecran, sursa):
	"""Un renderer (Label, Pixmap, Listbox) arata o sursa (StaticText, Boolean, List); numele ei in ecran."""
	for _i in range(4):
		if sursa is None:
			return ""
		for nume, comp in ecran.items():
			if comp is sursa:
				return nume
		sursa = getattr(sursa, "source", None)
	return ""


def _widgeturi(ecran):
	"""(nume, componenta, instanta) pentru fiecare widget al ecranului: componentele cu nume si rendererele surselor."""
	for nume, comp in list(ecran.items()):
		inst = getattr(comp, "instance", None)
		if inst is not None:
			yield nume, comp, inst
	for r in getattr(ecran, "renderer", None) or []:
		inst = getattr(r, "instance", None)
		if inst is not None:
			yield _numeSursa(ecran, getattr(r, "source", None)), r, inst


def _esteLista(inst):
	return hasattr(inst, "moveSelectionTo") and hasattr(inst, "getItemHeight") and hasattr(inst, "getTopIndex")


def _clase(ecran):
	return [c.__name__ for c in type(ecran).__mro__]


def _numeEcran(ecran):
	return ecran.__class__.__name__ if ecran is not None else ""


class Lista(object):
	"""O lista (eListbox) gasita sub mouse: dreptunghiul ei si socotelile de rand si de bara."""

	def __init__(self, nume, comp, inst, dreptunghi):
		self.nume, self.comp, self.inst = nume or "", comp, inst
		self.x, self.y, self.l, self.h = dreptunghi
		self._total = None

	def inaltimeRand(self):
		ih = 0
		try:
			ih = int(self.inst.getItemHeight())
		except Exception:
			pass
		return ih if ih > 0 else 48

	def randuriPePagina(self):
		try:
			n = int(self.inst.getItemsPerPage())
			if n > 0:
				return n
		except Exception:
			pass
		return max(1, self.h // self.inaltimeRand())

	def randSub(self, y):
		"""Indexul randului de sub y (poate fi dincolo de ultimul rand)."""
		return self.inst.getTopIndex() + max(0, y - self.y) // self.inaltimeRand()

	def total(self):
		"""Cate randuri are lista. Listele facute in Python isi spun lungimea (list, source.list, source.count());
		la cele din C++ (lista de canale) selectia se duce la capat si se aduce inapoi in acelasi pas al buclei, deci pe
		ecran nu se vede nimic (paginile listei raman aceleasi: eListbox le aliniaza la multipli de pagina)."""
		if self._total is not None:
			return self._total
		for obj in (self.comp, getattr(self.comp, "source", None)):
			if obj is None:
				continue
			val = getattr(obj, "list", None)
			if isinstance(val, (list, tuple)):
				self._total = len(val)
				return self._total
			numara = getattr(obj, "count", None)
			if callable(numara):
				try:
					self._total = int(numara())
					return self._total
				except Exception:
					pass
		inst = self.inst
		inainte = inst.getCurrentIndex()
		inst.moveSelection(getattr(inst, "moveEnd", 3))
		self._total = inst.getCurrentIndex() + 1
		if inst.getCurrentIndex() != inainte:
			inst.moveSelectionTo(inainte)
		return self._total

	def latimeBara(self):
		return min(max(self.l // 16, LATIME_BARA[0]), LATIME_BARA[1])

	def peBara(self, x):
		"""x cade pe bara de derulare (fasia din dreapta) si lista chiar are bara (mai multe randuri decat incap)."""
		if x is None or x < self.x + self.l - self.latimeBara() - SPATIU_BARA:
			return False
		return self.total() > self.randuriPePagina()

	def randDinBara(self, y):
		"""Randul din lista la locul y de pe bara: sus primul, jos ultimul, proportional intre ele."""
		total = self.total()
		if total <= 0:
			return 0
		parte = min(max(float(y - self.y) / max(self.h, 1), 0.0), 1.0)
		return min(int(parte * total), total - 1)


class MouseEcran(object):
	"""Gesturile mouse-ului pe ecranul de deasupra al televizorului. `ecran_curent()` da ecranul (session.current_dialog),
	`apasa(cod)` trimite o tasta. Tine minte numai cat trebuie: ultimul clic (pentru dublu clic) si trasul pe bara."""

	def __init__(self, ecran_curent, apasa=None, ceas=time.monotonic, mod_ascii=None, module_ascii=None):
		self._ecran_curent = ecran_curent
		self._apasa = apasa or apasaTasta
		self._ceas = ceas
		self._modAscii = mod_ascii or modAscii
		self._moduleAscii = module_ascii
		self._ultim = (-1000.0, None)
		self._tras = None

	# ---------------------------------------------------------------- intrarea comuna
	def gest(self, fel, x=None, y=None, clicuri=1, pasi=0, x0=None, y0=None, nou=False, text=""):
		"""Un gest; intoarce un dictionar cu ce s-a facut: {"facut": "selectie" | "ok" | "buton" | "bara" | "derulare" |
		"tasta" | "nimic", "ecran": numele clasei ecranului, plus "lista", "rand", "tasta", "nume" dupa caz}.
		nou: prima miscare a unui tras (uita un tras vechi ramas fara dragend, de pilda o fila inchisa in timpul lui)."""
		if fel == "clic":
			return self.clic(x, y, clicuri)
		if fel == "dublu":
			return self.clic(x, y, 2)
		if fel == "drag":
			if nou:
				self._tras = None
			return self.tras(x, y, x if x0 is None else x0, y if y0 is None else y0)
		if fel == "dragend":
			return self.trasGata(x, y)
		if fel == "rotita":
			return self.rotita(x, y, pasi)
		if fel == "dreapta":
			return self._tasta(KEY_EXIT)
		if fel == "mijloc":
			return self._tasta(KEY_MENU)
		if fel == "pagina":
			return self.pagina(pasi)
		if fel == "capat":
			return self.capat(pasi)
		if fel == "text":
			return self.text(text)
		raise ValueError("gest necunoscut: %r" % (fel,))

	def _ecran(self):
		ecran = self._ecran_curent()
		if ecran is None or getattr(ecran, "instance", None) is None:
			return None
		return ecran

	def _tasta(self, cod, ecran=None, nume=""):
		if ecran is None:
			ecran = self._ecran()
		self._apasa(cod)
		rez = {"facut": "tasta", "tasta": cod, "ecran": _numeEcran(ecran)}
		if nume:
			rez["facut"], rez["nume"] = "buton", nume
		return rez

	def _sub(self, ecran, x, y):
		"""Widget-urile vizibile de sub (x, y): [(nume, componenta, instanta, dreptunghi)]."""
		gasite = []
		if x is None or y is None:
			return gasite
		for nume, comp, inst in _widgeturi(ecran):
			try:
				if not inst.isVisible():
					continue
				wx, wy, ww, wh = _dreptunghi(inst)
			except Exception:
				continue
			if ww > 0 and wh > 0 and wx <= x < wx + ww and wy <= y < wy + wh:
				gasite.append((nume or "", comp, inst, (wx, wy, ww, wh)))
		return gasite

	def _lista(self, gasite):
		"""Cea mai mica lista dintre widget-urile gasite (o lista mica peste una mare castiga), sau None."""
		liste = [g for g in gasite if _esteLista(g[2])]
		if not liste:
			return None
		liste.sort(key=lambda g: g[3][2] * g[3][3])
		return Lista(*liste[0])

	# ---------------------------------------------------------------- clicul stanga
	def clic(self, x, y, clicuri=1):
		ecran = self._ecran()
		if ecran is None:
			return {"facut": "nimic", "ecran": ""}
		acum = self._ceas()
		ultim_timp, ultim_ecran = self._ultim
		self._ultim = (acum, id(ecran))
		if clicuri >= 2 and ultim_ecran != id(ecran) and acum - ultim_timp < DUBLU_CLIC_S:
			# primul clic din dublu clic a deschis deja alt ecran; al doilea nu mai apasa nimic acolo
			return {"facut": "nimic", "ecran": _numeEcran(ecran), "motiv": "ecran_nou"}
		gasite = self._sub(ecran, x, y)
		# 1. butoanele cu nume cunoscut
		for nume, comp, inst, _r in gasite:
			if _esteLista(inst):
				continue
			cod = tastaButon(nume)
			if cod:
				return self._tasta(cod, ecran, nume)
		# 2. lista de sub mouse: bara de derulare sau un rand
		lista = self._lista(gasite)
		if lista is None:
			return {"facut": "nimic", "ecran": _numeEcran(ecran)}
		if lista.peBara(x):
			return self._muta(ecran, lista, lista.randDinBara(y), "bara")
		return self._clicRand(ecran, lista, y, clicuri)

	def _unClic(self, ecran, lista):
		"""Un clic alege si deschide numai in meniuri; in setari si in celelalte liste, doi pasi."""
		clase = _clase(ecran)
		if any(c in ECRANE_SETARI for c in clase) or any(c in LISTE_SETARI for c in _clase(lista.comp)):
			return False
		return "menu" in lista.nume.lower() or any(c in ECRANE_MENIU for c in clase)

	def _clicRand(self, ecran, lista, y, clicuri):
		inst = lista.inst
		index = lista.randSub(y)
		inainte = inst.getCurrentIndex()
		rez = {"ecran": _numeEcran(ecran), "lista": lista.nume, "rand": index}
		if index > inainte and index >= lista.total():
			rez["facut"] = "nimic"
			rez["motiv"] = "sub_ultimul_rand"
			return rez
		if index == inainte or clicuri >= 2 or self._unClic(ecran, lista):
			if index != inainte:
				inst.moveSelectionTo(index)
			self._apasa(KEY_OK)
			rez["facut"] = "ok"
			return rez
		inst.moveSelectionTo(index)
		rez["facut"] = "selectie"
		rez["rand"] = inst.getCurrentIndex()
		return rez

	def _muta(self, ecran, lista, index, fel):
		if lista.inst.getCurrentIndex() != index:
			lista.inst.moveSelectionTo(index)
		return {"facut": fel, "ecran": _numeEcran(ecran), "lista": lista.nume, "rand": lista.inst.getCurrentIndex(),
			"total": lista.total()}

	# ---------------------------------------------------------------- trasul pe bara de derulare
	def tras(self, x, y, x0, y0):
		"""Mouse-ul tinut apasat si miscat. La prima miscare se afla din locul apasarii (x0, y0) daca trasul a inceput
		pe bara unei liste; daca nu, trasul nu face nimic pana la ridicare (trasGata)."""
		ecran = self._ecran()
		if ecran is None:
			self._tras = None
			return {"facut": "nimic", "ecran": "", "tras": False}
		if self._tras is None or self._tras[0] != id(ecran):
			lista = self._lista(self._sub(ecran, x0, y0))
			self._tras = (id(ecran), lista if lista is not None and lista.peBara(x0) else None)
		lista = self._tras[1]
		if lista is None:
			return {"facut": "nimic", "ecran": _numeEcran(ecran), "tras": False}
		rez = self._muta(ecran, lista, lista.randDinBara(y), "bara")
		rez["tras"] = True
		return rez

	def trasGata(self, x=None, y=None):
		tras, self._tras = self._tras, None
		ecran = self._ecran()
		if tras is None or tras[1] is None or ecran is None or tras[0] != id(ecran) or y is None:
			return {"facut": "nimic", "ecran": _numeEcran(ecran)}
		return self._muta(ecran, tras[1], tras[1].randDinBara(y), "bara")

	# ---------------------------------------------------------------- rotita
	def rotita(self, x, y, pasi):
		"""pasi > 0 = in jos (rotita trasa spre tine, degetul glisat in sus), pasi < 0 = in sus."""
		pasi = max(-PASI_MAXIM, min(PASI_MAXIM, int(pasi or 0)))
		ecran = self._ecran()
		if not pasi or ecran is None:
			return {"facut": "nimic", "ecran": _numeEcran(ecran)}
		lista = self._lista(self._sub(ecran, x, y))
		if lista is not None:
			inst = lista.inst
			if abs(pasi) >= PAS_PAGINA:
				inst.moveSelection(getattr(inst, "pageDown" if pasi > 0 else "pageUp", 5 if pasi > 0 else 4))
			else:
				for _i in range(abs(pasi)):
					inst.moveSelection(getattr(inst, "moveDown" if pasi > 0 else "moveUp", 1 if pasi > 0 else 0))
			return {"facut": "derulare", "ecran": _numeEcran(ecran), "lista": lista.nume, "rand": inst.getCurrentIndex(),
				"pagina": abs(pasi) >= PAS_PAGINA}
		cod = KEY_DOWN if pasi > 0 else KEY_UP
		for _i in range(min(abs(pasi), TASTE_ROTITA)):
			self._apasa(cod)
		return {"facut": "tasta", "tasta": cod, "ecran": _numeEcran(ecran)}

	# ---------------------------------------------------------------- tastatura: pagina si capetele
	def _listaPrincipala(self, ecran):
		"""Cea mai mare lista vizibila a ecranului (lista de canale, meniul, setarile), sau None."""
		liste = []
		for nume, comp, inst in _widgeturi(ecran):
			try:
				if not _esteLista(inst) or not inst.isVisible():
					continue
				r = _dreptunghi(inst)
			except Exception:
				continue
			if r[2] > 0 and r[3] > 0:
				liste.append((nume or "", comp, inst, r))
		if not liste:
			return None
		liste.sort(key=lambda g: -g[3][2] * g[3][3])
		return Lista(*liste[0])

	def pagina(self, pasi):
		"""Page Up/Down: pasi > 0 = o pagina in jos (sau canalul -), pasi < 0 = o pagina in sus (sau canalul +)."""
		ecran = self._ecran()
		if not pasi or ecran is None:
			return {"facut": "nimic", "ecran": _numeEcran(ecran)}
		lista = self._listaPrincipala(ecran)
		if lista is None:
			return self._tasta(KEY_CHANNELDOWN if pasi > 0 else KEY_CHANNELUP, ecran)
		inst = lista.inst
		inst.moveSelection(getattr(inst, "pageDown" if pasi > 0 else "pageUp", 5 if pasi > 0 else 4))
		return {"facut": "derulare", "ecran": _numeEcran(ecran), "lista": lista.nume, "rand": inst.getCurrentIndex(),
			"pagina": True}

	def capat(self, pasi):
		"""Home (pasi < 0) = primul rand, End (pasi > 0) = ultimul rand al listei principale; fara lista, nimic."""
		ecran = self._ecran()
		lista = self._listaPrincipala(ecran) if ecran is not None and pasi else None
		if lista is None:
			return {"facut": "nimic", "ecran": _numeEcran(ecran)}
		inst = lista.inst
		inst.moveSelection(getattr(inst, "moveEnd" if pasi > 0 else "moveTop", 3 if pasi > 0 else 2))
		return {"facut": "derulare", "ecran": _numeEcran(ecran), "lista": lista.nume, "rand": inst.getCurrentIndex()}

	# ---------------------------------------------------------------- tastatura: semnele scrise
	def text(self, text):
		"""Semnele scrise la tastatura paginii: in campul de text deschis pe televizor (modul ASCII), altfel tastele
		telecomenzii (TASTE_SEMNE). Intoarce "facut": "text" (cu "semne" = cate au intrat) sau "tasta" sau "nimic"."""
		ecran = self._ecran()
		text = (text or "")[:TEXT_MAXIM]
		if ecran is None or not text:
			return {"facut": "nimic", "ecran": _numeEcran(ecran)}
		functie = actiuneAscii(ecran) if self._modAscii() else None
		if functie is not None:
			module = self._moduleAscii
			if module is None:
				try:
					from Components import config as C
					module = (C,)
				except Exception:
					module = ()
			# Backspace: unde ecranul are "deleteBackward" (KeyboardInputActions: setarile, InputBox), tasta
			# KEY_BACKSPACE; altfel semnul 8, ca tastatura emulatorului (cautarile il sterg ca litera)
			sterge = actiuneAscii(ecran, "deleteBackward") is not None
			semne = 0
			for ch in text:
				if ch == "\b":
					if sterge:
						self._apasa(KEY_BACKSPACE)
					else:
						scrieAscii(functie, 8, module)
				elif ord(ch) >= 0x20:
					scrieAscii(functie, ord(ch), module)
				else:
					continue
				semne += 1
			return {"facut": "text", "ecran": _numeEcran(ecran), "semne": semne}
		ultima = None
		for ch in text.lower():
			cod = TASTE_SEMNE.get(ch)
			if cod:
				self._apasa(cod)
				ultima = cod
		if ultima is None:
			return {"facut": "nimic", "ecran": _numeEcran(ecran)}
		return {"facut": "tasta", "tasta": ultima, "ecran": _numeEcran(ecran)}
