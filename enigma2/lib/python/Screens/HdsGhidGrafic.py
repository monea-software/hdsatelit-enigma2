# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsGhidGrafic: ghidul TV grafic (grila canale x ore), scris de la zero pentru imaginea HD Satelit (26.11.2026;
# nimic din pluginurile Dream sau din alte imagini, numai ideea obisnuita a unei grile). Designul: Stitch, proiectul
# 'HD Satelit - Ghid TV grafic (RW2)'.
#
# Ce se vede: canalele buchetului pe verticala (numarul, sigla mica daca exista, numele), timpul pe orizontala (doua
# ore, rigla din jumatate in jumatate de ora), emisiunile ca blocuri cu titlul, linia orei de acum, emisiunea aleasa
# cu ora si descrierea jos, tastele colorate.
# Taste: sageti = canal sus/jos, emisiune stanga/dreapta; CH+/CH- = pagina de canale; << >> (si |<< >>|) = o zi
# inapoi/inainte; OK = porneste canalul (a doua oara, pe canalul care merge deja, inchide ghidul); pe o emisiune care
# n-a inceput OK deschide detaliile; INFO = detaliile; ROSU = inregistreaza (sau sterge programarea); VERDE =
# aminteste-mi (comutare la ora emisiunii); GALBEN = cauta in ghid dupa titlu; ALBASTRU = alege buchetul; MENU = ziua
# si ora, inapoi la acum, ghidul in lista; 0 = inapoi la acum; EXIT = inchide.
#
# RAPID PE RECEPTOARELE SLABE (Eduard, 26.11.2026: grila altor imagini 'merge foarte greu'; tinta: deschiderea sub 1 s,
# o sageata sub 100 ms pe ZGEMMA H8.2H si Vu+ Solo SE):
#   - lista e un eListbox cu un rand pe canal; eListbox construieste si deseneaza numai randurile care se vad;
#   - ghidul se citeste cu un singur apel la cache pentru randurile paginii si o fereastra de 4 ore
#     (Components/HdsGhidGrila.Memorie); pagina urmatoare (canalele de dedesubt) se citeste dupa desenare, din ceas;
#   - stanga/dreapta in fereastra = un singur rand redesenat (invalidateEntry); sus/jos = numai randul vechi si cel nou
#     (eListbox.moveSelection); numai mutarea ferestrei (alta ora, alta zi, alta pagina) redeseneaza pagina;
#   - selectia listei e oprita (setSelectionEnable 0): blocul ales e desenat de noi, iar titlurile randului ales nu
#     mai deruleaza toate odata;
#   - siglele se decodeaza micsorate de ePicLoad, pe firul lui, una dupa alta, numai pentru randurile vazute; randul se
#     redeseneaza o data cand vin (niciodata LoadPixmap in desenarea randului);
#   - marcajele temporizatoarelor se fac o data pe fereastra, nu la fiecare bloc.
# Masurare: cu fisierul /tmp/hds-ghid-masura prezent, timpii (deschiderea, fiecare tasta, randurile construite,
# apelurile la cache) se scriu in /tmp/hds-ghid-masura.txt.

import os
import time
_T_MODUL = time.time()

from enigma import eListbox, eListboxPythonMultiContent, eTimer, gFont, eServiceReference, eEPGCache, getDesktop, \
	RT_HALIGN_LEFT, RT_HALIGN_RIGHT, RT_HALIGN_CENTER, RT_VALIGN_CENTER

from Screens.Screen import Screen
from Components.ActionMap import ActionMap
from Components.GUIComponent import GUIComponent
from Components.Label import Label
from Components.config import config
from Components import HdsGhidGrila as G
from ServiceReference import ServiceReference
from Tools.ScaledSkin import scaledSkin

try:
	from Components import HdsTraducereEpg as _E
except Exception:
	_E = None

FISIER_MASURA = "/tmp/hds-ghid-masura"
LATIME_SKIN = 1920

# culorile temei HD Satelit (HDSatelit/skin.xml), ca numere (alfa 00 = opac)
C_FOND = 0x0010162A
C_CANAL = 0x0010162A
C_CANAL_ALES = 0x001C2440
C_BARA_ALES = 0x009FB4FF
C_BLOC = 0x00282D3F
C_BLOC_ACUM = 0x00404555
C_BLOC_ALES = 0x00374EA1
C_CHENAR_ALES = 0x009FB4FF
C_TEXT = 0x00F2F4F8
C_TEXT2 = 0x00C9D2E3
C_TEXT_SLAB = 0x00AEB9CC
C_AMBRA = 0x00F5B83D
C_REC = 0x00E5484D
C_GOL = 0x001A2034
C_TRECUT = 0x00141A2E   # partea din fereastra care a trecut: cache-ul sterge emisiunile terminate, locul ramane marcat


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_): textele se traduc la folosire."""
	return text


T_TITLU = N_("Ghid grafic")
T_GOL = N_("Buchetul nu are canale.")
T_FARA_PROGRAM = N_("Fără program în ghid")
T_TASTE = N_("OK Pornește   INFO Detalii   CH+/CH- Pagină   << >> Zi")


def _font(nume):
	try:
		from skin import fontHds
		return fontHds(nume)
	except Exception:
		return nume


def _scara():
	try:
		return getDesktop(0).size().width() / float(LATIME_SKIN)
	except Exception:
		return 1.0


def _marimeFont(baza):
	"""Marimea in pixeli a unui font scris pentru 1920: scara ecranului si 'Mărimea textului' (config.osd.fontscale), cel
	mult 127 px (literele mai mari nu se deseneaza, SSV1)."""
	try:
		from skin import getFontScalePercent
		p = getFontScalePercent()
	except Exception:
		p = 100
	return max(8, min(127, int(baza * _scara() * p / 100.0)))


def _masoara():
	return os.path.exists(FISIER_MASURA)


def _scrieMasura(text):
	try:
		with open(FISIER_MASURA + ".txt", "a") as f:
			f.write("%s %s\n" % (time.strftime("%H:%M:%S"), text))
	except Exception:
		pass


class Sigle(object):
	"""Siglele mici ale canalelor: cautarea imaginii (Tools/PiconResolver.cauta_sigla), decodare micsorata cu un singur
	ePicLoad pe firul lui, cate una, numai cele cerute de randurile desenate; cand vine una, `gata(ref)`."""

	MAX = 120

	def __init__(self, latime, inaltime, gata):
		self.latime, self.inaltime = latime, inaltime
		self.gata = gata
		self.cai = {}
		self.pix = {}
		self.ordine = []
		self.rele = set()
		self.coada = []
		self.lucru = None
		self.oprit = False
		self.incarcator = None
		try:
			from Tools.PiconResolver import sigle_pornite, cauta_sigla
			from enigma import ePicLoad
			if not sigle_pornite():
				return
			self.cauta = cauta_sigla
			self.incarcator = ePicLoad()
			self.incarcator.setPara((latime, inaltime, 1, 1, False, 1, "#00000000"))
			try:
				self.incarcator.PictureData.get().append(self._venit)
			except AttributeError:
				self._legatura = self.incarcator.PictureData.connect(self._venit)
		except Exception as e:
			print("[HdsGhidGrafic] siglele: %s" % e)
			self.incarcator = None

	def sigla(self, ref, nume):
		"""Pixmap-ul siglei sau None (lipseste ori se decodeaza acum)."""
		if self.incarcator is None or not ref:
			return None
		cale = self.cai.get(ref)
		if cale is None:
			try:
				cale = self.cauta(ref, nume=nume or None) or ""
			except Exception:
				cale = ""
			self.cai[ref] = cale
		if not cale or cale in self.rele:
			return None
		ptr = self.pix.get(cale)
		if ptr is None and cale != self.lucru and all(c != cale for c, r in self.coada):
			self.coada.append((cale, ref))
			if self.lucru is None:
				self._urmatoarea()
		return ptr

	def _urmatoarea(self):
		while self.coada and not self.oprit:
			cale, ref = self.coada.pop()
			self.lucru = (cale, ref)
			try:
				if self.incarcator.startDecode(cale) == 0:
					return
			except Exception:
				pass
			self.rele.add(cale)
		self.lucru = None

	def _venit(self, info=""):
		if self.oprit or self.lucru is None:
			return
		(cale, ref), self.lucru = self.lucru, None
		try:
			ptr = self.incarcator.getData()
		except Exception:
			ptr = None
		if ptr is not None:
			if cale not in self.pix:
				self.ordine.append(cale)
			self.pix[cale] = ptr
			while len(self.ordine) > self.MAX:
				self.pix.pop(self.ordine.pop(0), None)
			self.gata(ref)
		else:
			self.rele.add(cale)
		del self.coada[:-24]
		self._urmatoarea()

	def opreste(self):
		self.oprit = True
		self.coada = []
		self.pix = {}


class HdsGrila(GUIComponent):
	"""Randurile grilei: un rand pe canal. Starea (fereastra, randul si emisiunea alese) o tine ecranul."""

	GUI_WIDGET = eListbox

	def __init__(self, ecran):
		GUIComponent.__init__(self)
		self.ecran = ecran
		self.l = eListboxPythonMultiContent()
		self.l.setBuildFunc(self.construieste)
		self.l.setFont(0, gFont(_font("Regular"), _marimeFont(28)))
		self.l.setFont(1, gFont(_font("Bold"), _marimeFont(28)))
		self.l.setFont(2, gFont(_font("Regular"), _marimeFont(22)))
		self.l.setFont(3, gFont(_font("Bold"), _marimeFont(28)))
		self.construite = 0
		self.ultim = 0

	def postWidgetCreate(self, instance):
		instance.setContent(self.l)
		instance.setSelectionEnable(0)
		instance.setWrapAround(False)

	def preWidgetRemove(self, instance):
		instance.setContent(None)

	def hdsTraducereEpg(self):
		"""Components/HdsTraducereEpg.py: a venit o traducere; randurile vazute se redeseneaza."""
		if self.instance is not None:
			self.l.invalidate()

	def construieste(self, index):
		self.construite += 1
		self.ultim = time.time()
		try:
			return self.ecran.randul(index)
		except Exception as e:
			import traceback
			print("[HdsGhidGrafic] randul %s: %s" % (index, traceback.format_exc()))
			if _masoara():
				_scrieMasura("EROARE randul %s: %s" % (index, traceback.format_exc().replace("\n", " | ")))
			return [None]


class HdsRigla(GUIComponent):
	"""Rigla orelor: un singur rand, redesenat numai cand se muta fereastra (si o data pe minut, pentru ora de acum)."""

	GUI_WIDGET = eListbox

	def __init__(self, ecran):
		GUIComponent.__init__(self)
		self.ecran = ecran
		self.l = eListboxPythonMultiContent()
		self.l.setBuildFunc(self.construieste)
		self.l.setFont(0, gFont(_font("Regular"), _marimeFont(24)))
		self.l.setFont(1, gFont(_font("Bold"), _marimeFont(20)))

	def postWidgetCreate(self, instance):
		instance.setContent(self.l)
		instance.setSelectionEnable(0)

	def preWidgetRemove(self, instance):
		instance.setContent(None)

	def construieste(self, index):
		try:
			return self.ecran.rigla()
		except Exception as e:
			print("[HdsGhidGrafic] rigla: %s" % e)
			return [None]


SKIN = """<screen name="HdsGhidGrafic" position="72,40" size="1776,1000" flags="wfNoBorder" backgroundColor="#0010162A">
	<eLabel position="32,30" size="150,44" backgroundColor="#002A3350" zPosition="1" />
	<widget name="eticheta" position="32,30" size="150,44" font="{fBold};24" foregroundColor="#00F5B83D" backgroundColor="#002A3350" halign="center" valign="center" noWrap="1" zPosition="2" />
	<widget name="buchet" position="200,24" size="900,56" font="{fBold};34" foregroundColor="#00F2F4F8" backgroundColor="#0010162A" valign="center" noWrap="1" zPosition="2" />
	<widget name="data" position="1110,24" size="420,56" font="{fRegular};30" foregroundColor="#00C9D2E3" backgroundColor="#0010162A" halign="right" valign="center" noWrap="1" zPosition="2" />
	<eLabel position="1544,26" size="200,52" backgroundColor="#002A3350" zPosition="1" />
	<widget name="ceas" position="1544,26" size="200,52" font="{fBold};36" foregroundColor="#00F5B83D" backgroundColor="#002A3350" halign="center" valign="center" noWrap="1" zPosition="2" />
	<eLabel position="32,92" size="1712,1" backgroundColor="#002A3350" zPosition="1" />
	<widget name="rigla" position="32,100" size="1712,40" itemHeight="40" backgroundColor="#0010162A" scrollbarMode="showNever" zPosition="2" />
	<widget name="grila" position="32,144" size="1712,576" itemHeight="64" backgroundColor="#0010162A" scrollbarMode="showNever" zPosition="2" />
	<widget name="gol" position="32,400" size="1712,64" font="{fRegular};32" foregroundColor="#00C9D2E3" backgroundColor="#0010162A" halign="center" valign="center" zPosition="3" />
	<eLabel position="32,736" size="1712,168" backgroundColor="#00172036" zPosition="1" />
	<widget name="emTitlu" position="56,746" size="1160,52" font="{fBold};32" foregroundColor="#00F2F4F8" backgroundColor="#00172036" valign="center" noWrap="1" zPosition="2" />
	<widget name="emOra" position="1230,746" size="490,52" font="{fBold};28" foregroundColor="#00F5B83D" backgroundColor="#00172036" halign="right" valign="center" noWrap="1" zPosition="2" />
	<widget name="emDescriere" position="56,800" size="1664,96" font="{fRegular};26" foregroundColor="#00C9D2E3" backgroundColor="#00172036" zPosition="2" />
	<eLabel position="32,938" size="22,22" backgroundColor="#00E5484D" zPosition="1" />
	<widget name="key_red" position="64,922" size="250,54" font="{fBold};26" foregroundColor="#00F2F4F8" backgroundColor="#0010162A" valign="center" noWrap="1" zPosition="2" />
	<eLabel position="324,938" size="22,22" backgroundColor="#0046B06A" zPosition="1" />
	<widget name="key_green" position="356,922" size="250,54" font="{fBold};26" foregroundColor="#00F2F4F8" backgroundColor="#0010162A" valign="center" noWrap="1" zPosition="2" />
	<eLabel position="616,938" size="22,22" backgroundColor="#00E8B93A" zPosition="1" />
	<widget name="key_yellow" position="648,922" size="200,54" font="{fBold};26" foregroundColor="#00F2F4F8" backgroundColor="#0010162A" valign="center" noWrap="1" zPosition="2" />
	<eLabel position="858,938" size="22,22" backgroundColor="#003D7BE0" zPosition="1" />
	<widget name="key_blue" position="890,922" size="200,54" font="{fBold};26" foregroundColor="#00F2F4F8" backgroundColor="#0010162A" valign="center" noWrap="1" zPosition="2" />
	<widget name="taste" position="1100,922" size="644,54" font="{fRegular};24" foregroundColor="#00AEB9CC" backgroundColor="#0010162A" halign="right" valign="center" noWrap="1" zPosition="2" />
</screen>"""


class HdsGhidGrafic(Screen):
	"""Ghidul TV grafic. Aceeasi semnatura ca ghidul in lista (EPGSelection) pentru buchet: (services, zapFunc, None,
	bouquetChangeCB); `buchete` = lista buchetelor [(nume, ref)] si `alegeBuchet(ref, ecran)` pentru tasta albastra."""

	def __init__(self, session, services, zapFunc=None, eventid=None, bouquetChangeCB=None, buchete=None, alegeBuchet=None,
			numeBuchet="", ghidLista=None):
		self.t_deschidere = time.time()
		self.ghidLista = ghidLista
		Screen.__init__(self, session)
		self.skinName = "HdsGhidGrafic"
		self.skin = scaledSkin(SKIN.format(fRegular=_font("Regular"), fBold=_font("Bold")), LATIME_SKIN)
		self.setTitle(_(T_TITLU))
		self.zapFunc = zapFunc
		self.bouquetChangeCB = bouquetChangeCB
		self.buchete = buchete
		self.alegeBuchet = alegeBuchet
		self.closeRecursive = False
		self.epg = eEPGCache.getInstance()
		self.memorie = G.Memorie(self.epg)
		self.vedere = G.VEDERE_IMPLICITA
		acum = int(time.time())
		self.minim = G.aliniaza(acum)
		self.t0 = self.minim
		self.t_cursor = acum                     # momentul dupa care se alege emisiunea la sus/jos
		self.ales = -1                           # indexul emisiunii alese in randul ales (in memorie)
		self.randuri = []                        # [(cheie, ServiceReference)]
		self.sel = 0                             # randul ales
		self.nume = {}
		self.marcaje = {}
		self.pe_pagina = 1
		self.sigle = None
		self.masoara = _masoara()
		self.tasta = None
		self.zile = (_("Mon"), _("Tue"), _("Wed"), _("Thu"), _("Fri"), _("Sat"), _("Sun"))

		self["eticheta"] = Label(_("Buchet"))
		self["buchet"] = Label(numeBuchet or "")
		self["data"] = Label("")
		self["ceas"] = Label("")
		self["grila"] = HdsGrila(self)
		self["rigla"] = HdsRigla(self)
		self["gol"] = Label("")
		self["emTitlu"] = Label("")
		self["emOra"] = Label("")
		self["emDescriere"] = Label("")
		self["key_red"] = Label(_("Înregistrează"))
		self["key_green"] = Label(_("Amintește-mi"))
		self["key_yellow"] = Label(_("Caută"))
		self["key_blue"] = Label(_("Buchetul"))
		self["taste"] = Label(_(T_TASTE))

		self["actions"] = ActionMap(["HdsGhidGraficActions"], {
			"ok": self.ok,
			"cancel": self.inchide,
			"up": self.sus,
			"down": self.jos,
			"left": self.stanga,
			"right": self.dreapta,
			"pageUp": self.paginaSus,
			"pageDown": self.paginaJos,
			"dayBack": self.ziInapoi,
			"dayForward": self.ziInainte,
			"info": self.detalii,
			"red": self.inregistreaza,
			"green": self.amintesteMi,
			"yellow": self.cauta,
			"blue": self.buchetul,
			"menu": self.meniu,
			"now": self.laAcum,
			"epg": self.inchide,
		}, -1)

		self.ceasPas = eTimer()
		self.ceasPas.callback.append(self.minut)
		self.ceasAvans = eTimer()
		self.ceasAvans.callback.append(self.citesteInAvans)
		self.ceasMasura = eTimer()
		self.ceasMasura.callback.append(self.dupaDesenare)
		self.ceasSigle = eTimer()
		self.ceasSigle.callback.append(self.sigleVenite)
		self.sigle_venite = set()
		self._seteazaRanduri(services)
		self.tasta = ("deschidere", self.t_deschidere, 0, 0) if self.masoara else None
		self.onLayoutFinish.append(self.laInceput)
		self.onClose.append(self.laInchidere)
		from Screens.TimerEntry import GhidTimer
		self.ghidTimer = GhidTimer(session, self.timereSchimbate)

	# ------------------------------------------------------------------ randurile
	def _seteazaRanduri(self, services):
		self.sel = 0
		self.randuri = []
		for s in services or []:
			sr = s if isinstance(s, ServiceReference) else ServiceReference(s)
			self.randuri.append((G.cheie(sr), sr))
		self.nume = {}

	def _nume(self, i):
		n = self.nume.get(i)
		if n is None:
			try:
				n = self.randuri[i][1].getServiceName() or ""
			except Exception:
				n = ""
			n = n.replace("\xc2\x86", "").replace("\xc2\x87", "").replace("\x86", "").replace("\x87", "")
			self.nume[i] = n
		return n

	def setServices(self, services, numeBuchet=None):
		"""Alt buchet (CH din ghid sau tasta albastra): aceeasi fereastra, primul canal."""
		self._seteazaRanduri(services)
		if numeBuchet is not None:
			self["buchet"].setText(numeBuchet)
		self.memorie.uita()
		self["grila"].l.setList([(i,) for i in range(len(self.randuri))])
		self._mutaLa(0)
		self._umple(True)

	def laInceput(self):
		g = self["grila"]
		inst = g.instance
		inaltime = g.l.getItemSize().height() or 64
		self.pe_pagina = max(1, inst.size().height() // inaltime)
		self.latime = g.l.getItemSize().width() or inst.size().width()
		self.inaltime = inaltime
		self.col = int(round(self.latime * 300.0 / 1712))
		self.x0 = self.col + 4
		self.lw = self.latime - self.x0
		sh = max(16, inaltime - 16)
		self.sigle = Sigle(int(round(sh * 5 / 3.0)), sh, self.siglaVenita)
		self["grila"].l.setList([(i,) for i in range(len(self.randuri))])
		self["rigla"].l.setList([(0,)])
		# randul canalului care merge, emisiunea de acum
		start = 0
		try:
			ref = self.session.nav.getCurrentlyPlayingServiceReference()
			c = G.cheie(ref) if ref is not None else ""
			for i, (k, s) in enumerate(self.randuri):
				if k == c:
					start = i
					break
		except Exception:
			pass
		self._mutaLa(start)
		self._umple(True)
		self.minut(prima=True)
		if self.masoara:
			self.functie_ms = (time.time() - self.t_deschidere) * 1000
			global _MODUL_MS
			if _MODUL_MS is not None:
				_scrieMasura("modulul ecranului (cu Components/HdsGhidGrila) incarcat in %.0f ms" % _MODUL_MS)
				_MODUL_MS = None
			self.ceasMasura.start(400, True)

	def laInchidere(self):
		for c in (self.ceasPas, self.ceasAvans, self.ceasMasura, self.ceasSigle):
			c.stop()
		if self.sigle is not None:
			self.sigle.opreste()

	def indexAles(self):
		"""Randul ales, tinut de ecran: in timpul desenarii eListbox muta cursorul continutului pe fiecare rand
		(getCurrentIndex ar da randul desenat, nu pe cel ales)."""
		return self.sel

	def _sus(self):
		return (self.indexAles() // self.pe_pagina) * self.pe_pagina

	def _refsPagina(self, inceput):
		return [k for k, s in self.randuri[inceput:inceput + self.pe_pagina]]

	def _fereastraCitire(self):
		"""(a, b, b_citire): ce trebuie sa fie in memorie (fereastra vazuta) si pana unde se citeste cand lipseste: de trei
		ori cat se vede, ca sagetile si mutarile ferestrei spre dreapta din urmatoarele ore sa nu mai ceara nimic."""
		return self.t0, self.t0 + self.vedere, self.t0 + 3 * self.vedere

	def _umple(self, tot=False):
		"""Citeste pagina vazuta (ce lipseste) si marcajele; redeseneaza pagina daca tot=True."""
		a, b, bc = self._fereastraCitire()
		sus = self._sus()
		self.memorie.cere(self._refsPagina(sus), a, b, bc)
		self.marcaje = G.marcajeTemporizatoare(self.session.nav.RecordTimer.timer_list)
		self._alegeLaTimp()
		if tot:
			self["grila"].l.invalidate()
			self["rigla"].l.invalidate()
			self._data()
		self._detalii()
		self.ceasAvans.start(150, True)

	def citesteInAvans(self):
		"""Dupa desenare: pagina de dedesubt (si cea de deasupra) in aceeasi fereastra, ca CH-/jos sa nu astepte."""
		a, b, bc = self._fereastraCitire()
		sus = self._sus()
		self.memorie.cere(self._refsPagina(sus + self.pe_pagina), a, b, bc)
		if sus > 0:
			self.memorie.cere(self._refsPagina(max(0, sus - self.pe_pagina)), a, b, bc)

	def _randCurent(self):
		i = self.indexAles()
		if 0 <= i < len(self.randuri):
			return i, self.randuri[i][0], self.randuri[i][1]
		return -1, "", None

	def _emisiuni(self, ref):
		return self.memorie.emisiuni(ref) or []

	def _alegeLaTimp(self):
		i, ref, s = self._randCurent()
		if i < 0:
			self.ales = -1
			return
		ev = self._emisiuni(ref)
		t = max(self.t_cursor, self.t0)
		if t >= self.t0 + self.vedere:
			t = self.t0
		self.ales = G.laTimp(ev, t)
		if self.ales >= 0:
			e = ev[self.ales]
			if not (e[1] < self.t0 + self.vedere and G.sfarsitul(e) > self.t0):
				self.ales = -1

	def emisiuneAleasa(self):
		i, ref, s = self._randCurent()
		ev = self._emisiuni(ref)
		if 0 <= self.ales < len(ev):
			return ev[self.ales]
		return None

	# ------------------------------------------------------------------ desenarea
	def randul(self, index):
		"""Intrarile unui rand (apelat de eListbox numai pentru randurile care se vad)."""
		if index >= len(self.randuri):
			return [None]
		ref, s = self.randuri[index]
		h = self.inaltime
		ales_rand = index == self.indexAles()
		rez = [None]
		T = eListboxPythonMultiContent.TYPE_TEXT
		# coloana canalului
		rez.append((T, 0, 1, self.col, h - 2, 0, RT_HALIGN_LEFT, "", None, None, C_CANAL_ALES if ales_rand else C_CANAL, None))
		if ales_rand:
			rez.append((T, 0, 1, 4, h - 2, 0, RT_HALIGN_LEFT, "", None, None, C_BARA_ALES, None))
		nume = self._nume(index)
		lnr = int(h * 0.9)
		rez.append((T, 8, 0, lnr, h, 2, RT_HALIGN_RIGHT | RT_VALIGN_CENTER, str(index + 1), C_TEXT_SLAB, None, None, None))
		x = 8 + lnr + 10
		pix = self.sigle.sigla(ref, nume) if self.sigle is not None else None
		if pix is not None:
			sw, sh = self.sigle.latime, self.sigle.inaltime
			rez.append((eListboxPythonMultiContent.TYPE_PIXMAP_ALPHABLEND, x, (h - sh) // 2, sw, sh, pix))
			x += sw + 10
		rez.append((T, x, 0, max(10, self.col - x - 8), h, 1, RT_HALIGN_LEFT | RT_VALIGN_CENTER, nume, C_TEXT, None, None, None))
		# blocurile emisiunilor
		t1 = self.t0 + self.vedere
		ev = self.memorie.emisiuni(ref)
		acum = int(time.time())
		if ev is None:
			# nu s-a citit inca (pagina de dedesubt inainte de citire): se cere acum, numai pagina lui
			a, b, bc = self._fereastraCitire()
			sus = (index // self.pe_pagina) * self.pe_pagina
			self.memorie.cere(self._refsPagina(sus), a, b, bc)
			ev = self.memorie.emisiuni(ref) or []
		bl = G.blocuri(ev, self.t0, t1, self.x0, self.lw)
		xa = G.xTimp(acum, self.t0, t1, self.x0, self.lw)
		if xa is not None and xa > self.x0 and bl:
			rez.append((T, self.x0, 1, xa - self.x0, h - 2, 0, RT_HALIGN_LEFT, "", None, None, C_TRECUT, None))
		if not bl:
			rez.append((T, self.x0, 1, self.lw, h - 2, 2, RT_HALIGN_LEFT | RT_VALIGN_CENTER, "  " + _(T_FARA_PROGRAM),
				C_TEXT_SLAB, None, C_GOL, None))
		ales_ev = self.emisiuneAleasa() if ales_rand else None
		pad = max(6, int(12 * _scara()))
		marca = max(8, h // 6)
		for x, w, e in bl:
			este_ales = ales_ev is not None and e[0] == ales_ev[0] and e[1] == ales_ev[1]
			este_acum = e[1] <= acum < G.sfarsitul(e)
			if este_ales:
				rez.append((T, x, 1, w, h - 2, 0, RT_HALIGN_LEFT, "", None, None, C_BLOC_ALES, None, 2, C_CHENAR_ALES))
			else:
				rez.append((T, x, 1, w, h - 2, 0, RT_HALIGN_LEFT, "", None, None, C_BLOC_ACUM if este_acum else C_BLOC, None))
			fel = G.felTemporizator(self.marcaje, ref, e)
			tw = w - 2 * pad
			if fel:
				tw -= marca + pad
				rez.append((T, x + w - pad - marca, (h - marca) // 2, marca, marca, 0, RT_HALIGN_LEFT, "", None, None,
					C_REC if fel == "inregistrare" else C_AMBRA, None))
			if tw > 8:
				titlu = e[3]
				if _E is not None and titlu:
					try:
						titlu = _E.text("titlu", titlu, self["grila"], False)
					except Exception:
						pass
				rez.append((T, x + pad, 1, tw, h - 2, 3 if este_ales else 0, RT_HALIGN_LEFT | RT_VALIGN_CENTER, titlu,
					C_TEXT, None, None, None))
		if xa is not None:
			rez.append((T, xa - 1, 0, 3, h, 0, RT_HALIGN_LEFT, "", None, None, C_AMBRA, None))
		return rez

	def rigla(self):
		T = eListboxPythonMultiContent.TYPE_TEXT
		h = self["rigla"].l.getItemSize().height() or 40
		t1 = self.t0 + self.vedere
		rez = [None]
		acum = int(time.time())
		xa = G.xTimp(acum, self.t0, t1, self.x0, self.lw)
		lw = int(90 * _scara())
		for t, text in G.ore(self.t0, t1):
			x = G.xTimp(t, self.t0, t1, self.x0, self.lw)
			if x is None:
				continue
			if xa is not None and xa - lw < x + 10 < xa + lw // 2 + 4:
				continue   # eticheta orei ar fi sub ora de acum
			rez.append((T, x, 4, 2, h - 8, 0, RT_HALIGN_LEFT, "", None, None, 0x002A3350, None))
			rez.append((T, x + 10, 0, 160, h, 0, RT_HALIGN_LEFT | RT_VALIGN_CENTER, text, C_TEXT2, None, None, None))
		if xa is not None:
			rez.append((T, max(self.x0, xa - lw // 2), 6, lw, h - 12, 1, RT_HALIGN_CENTER | RT_VALIGN_CENTER, G.hhmm(acum),
				0x0010162A, None, C_AMBRA, None))
		zi = G.ziua(self.t0, acum, self.zile, _("Today"), _("Mâine"))
		rez.append((T, 8, 0, self.col - 16, h, 1, RT_HALIGN_LEFT | RT_VALIGN_CENTER, zi, C_AMBRA, None, None, None))
		return rez

	def _data(self):
		self["data"].setText(G.ziua(self.t0, int(time.time()), self.zile, _("Today"), _("Mâine")))

	def minut(self, prima=False):
		acum = int(time.time())
		self["ceas"].setText(G.hhmm(acum))
		if not prima:
			# linia orei de acum se muta: pagina si rigla se redeseneaza o data pe minut
			nou_minim = G.aliniaza(acum)
			self.minim = nou_minim
			self["grila"].l.invalidate()
			self["rigla"].l.invalidate()
		self.ceasPas.start((60 - acum % 60) * 1000 + 50, True)

	def _detalii(self):
		e = self.emisiuneAleasa()
		i, ref, s = self._randCurent()
		if s is None:
			self["gol"].setText(_(T_GOL))
			self["gol"].show()
			for n in ("emTitlu", "emOra", "emDescriere"):
				self[n].setText("")
			return
		self["gol"].setText("")
		self["gol"].hide()          # altfel fondul lui acopera randul al cincilea
		if e is None:
			self["emTitlu"].setText(self._nume(i))
			self["emOra"].setText("")
			self["emDescriere"].setText(_(T_FARA_PROGRAM))
			return
		titlu = e[3]
		if _E is not None and titlu:
			try:
				titlu = _E.text("titlu", titlu, self["grila"], False)
			except Exception:
				pass
		self["emTitlu"].setText(titlu)
		self["emOra"].setText("%s - %s  (%d min)" % (G.hhmm(e[1]), G.hhmm(G.sfarsitul(e)), max(1, (e[2] + 30) // 60)))
		self["emDescriere"].setText(self._descriere(ref, e))

	def _eveniment(self, ref, e):
		try:
			return self.epg.lookupEventId(eServiceReference(ref), e[0])
		except Exception:
			return None

	def _descriere(self, ref, e):
		ev = self._eveniment(ref, e)
		if ev is None:
			return ""
		scurta = ev.getShortDescription() or ""
		lunga = ev.getExtendedDescription() or ""
		if scurta == e[3]:
			scurta = ""
		text = " ".join(x for x in (scurta, lunga) if x and x not in ("",))
		return text.replace("\n", " ")[:600]

	# ------------------------------------------------------------------ masurarea
	def _incepe(self, nume):
		if self.masoara:
			self.tasta = (nume, time.time(), self.memorie.apeluri, self["grila"].construite)

	def _gata(self):
		if self.masoara and self.tasta is not None:
			self.functie_ms = (time.time() - self.tasta[1]) * 1000
			self.ceasMasura.start(400, True)

	def dupaDesenare(self):
		if self.tasta is None:
			return
		nume, t, apeluri, construite = self.tasta
		# pana la ultimul rand construit de eListbox pentru tasta asta (randurile se construiesc cand se deseneaza);
		# ceasul pornit la 400 ms dupa tasta lasa desenarea sa se termine inainte
		functie = getattr(self, "functie_ms", 0)
		ultim = self["grila"].ultim
		total = max(functie, (ultim - t) * 1000) if ultim >= t else functie
		_scrieMasura("%s: %.0f ms pana la ultimul rand desenat, functia %.0f ms, randuri construite %d, apeluri cache %d, VmRSS %s" % (
			nume, total, functie, self["grila"].construite - construite,
			self.memorie.apeluri - apeluri, self._rss()))
		self.tasta = None

	def _rss(self):
		try:
			with open("/proc/self/status") as f:
				for linie in f:
					if linie.startswith("VmRSS:"):
						return linie.split(":", 1)[1].strip()
		except Exception:
			pass
		return "?"

	# ------------------------------------------------------------------ miscarea
	def _mutaLa(self, index):
		inst = self["grila"].instance
		if self.randuri:
			self.sel = max(0, min(index, len(self.randuri) - 1))
			if inst is not None:
				inst.moveSelectionTo(self.sel)

	def _redeseneazaRand(self, index):
		try:
			self["grila"].l.invalidateEntry(index)
		except Exception:
			self["grila"].l.invalidate()

	def _schimbaRand(self, nou):
		"""Sus/jos: randul nou; emisiunea dupa momentul cursorului. Pagina noua = citirea ei (daca lipseste)."""
		if not self.randuri:
			return
		n = len(self.randuri)
		nou = nou % n
		vechi_sus = self._sus()
		self._mutaLa(nou)
		if self._sus() != vechi_sus:
			a, b, bc = self._fereastraCitire()
			self.memorie.cere(self._refsPagina(self._sus()), a, b, bc)
			self.ceasAvans.start(150, True)
		self._alegeLaTimp()
		# eListbox a redesenat randul vechi si pe cel nou (sau pagina); randul nou se construieste cu emisiunea aleasa
		self._detalii()

	def sus(self):
		self._incepe("sus")
		self._schimbaRand(self.indexAles() - 1)
		self._gata()

	def jos(self):
		self._incepe("jos")
		self._schimbaRand(self.indexAles() + 1)
		self._gata()

	def paginaSus(self):
		self._incepe("pagina sus")
		i = self.indexAles()
		self._schimbaRand(i - self.pe_pagina if i >= self.pe_pagina else (len(self.randuri) - 1 if i == 0 else 0))
		self._gata()

	def paginaJos(self):
		self._incepe("pagina jos")
		i = self.indexAles()
		n = len(self.randuri)
		self._schimbaRand(i + self.pe_pagina if i + self.pe_pagina < n else (0 if i == n - 1 else n - 1))
		self._gata()

	def _mutaFereastra(self, t0):
		t0 = max(self.minim, min(t0, self.minim + G.ZILE * G.ZI))
		if t0 == self.t0:
			return False
		self.t0 = t0
		self._umple(True)
		return True

	def dreapta(self):
		self._incepe("dreapta")
		i, ref, s = self._randCurent()
		if s is None:
			return
		ev = self._emisiuni(ref)
		urm = self.ales + 1 if self.ales >= 0 else G.laTimp(ev, self.t0 + self.vedere)
		acop = self.memorie.acopera(ref)
		if (urm < 0 or urm >= len(ev)) and acop is not None:
			# dupa ultima emisiune citita: fereastra canalului dusa cu inca 6 ore
			self.memorie.extinde(ref, min(acop[1] + 6 * 3600, self.minim + G.ZILE * G.ZI + self.vedere))
			ev = self._emisiuni(ref)
		if 0 <= urm < len(ev) and (self.ales < 0 or ev[urm][1] >= ev[self.ales][1]):
			e = ev[urm]
			self.ales = urm
			self.t_cursor = max(e[1], self.t0)
			t0 = G.fereastraPentru(e, self.t0, self.vedere, self.minim)
			if t0 != self.t0:
				self.t0 = t0
				self.t_cursor = max(e[1], t0)
				self._umple(True)
				self.ales = G.indexDupaId(self._emisiuni(ref), e[0])
				self._detalii()
			else:
				self._redeseneazaRand(i)
				self._detalii()
		else:
			# randul n-are nimic mai departe: se muta ora
			self.t_cursor = self.t0 + self.vedere
			self._mutaFereastra(self.t0 + self.vedere // 2)
		self._gata()

	def stanga(self):
		self._incepe("stanga")
		i, ref, s = self._randCurent()
		if s is None:
			return
		ev = self._emisiuni(ref)
		ant = self.ales - 1 if self.ales >= 0 else -1
		if ant < 0 and self.t0 > self.minim:
			acop = self.memorie.acopera(ref)
			if acop is not None and acop[0] > self.minim - G.VEDERE_IMPLICITA:
				# emisiunea aleasa se tine minte inainte: extinderea pune emisiuni in fata, indexul se schimba
				ales_id = ev[self.ales][0] if 0 <= self.ales < len(ev) else -1
				self.memorie.extindeInapoi(ref, max(self.minim - 3600, acop[0] - 6 * 3600))
				ev = self._emisiuni(ref)
				if self.ales >= 0:
					self.ales = G.indexDupaId(ev, ales_id)
				ant = (self.ales - 1) if self.ales >= 0 else G.laTimp(ev, self.t0 - 1)
		if 0 <= ant < len(ev) and G.sfarsitul(ev[ant]) > self.minim:
			e = ev[ant]
			self.ales = ant
			t0 = G.fereastraPentru(e, self.t0, self.vedere, self.minim)
			self.t_cursor = max(e[1], t0)
			if t0 != self.t0:
				self.t0 = t0
				self._umple(True)
				self.ales = G.indexDupaId(self._emisiuni(ref), e[0])
				self._detalii()
			else:
				self._redeseneazaRand(i)
				self._detalii()
		elif self.t0 > self.minim:
			self.t_cursor = self.t0 - self.vedere // 2
			self._mutaFereastra(self.t0 - self.vedere // 2)
		self._gata()

	@property
	def emisiuneAleasaId(self):
		e = self.emisiuneAleasa()
		return e[0] if e is not None else -1

	def _zi(self, semn):
		self._incepe("zi %+d" % semn)
		self.t_cursor = max(self.t_cursor, self.t0) + semn * G.ZI
		if self._mutaFereastra(G.aliniaza(self.t0 + semn * G.ZI)):
			self._detalii()
		self._gata()

	def ziInapoi(self):
		self._zi(-1)

	def ziInainte(self):
		self._zi(1)

	def laAcum(self):
		self._incepe("acum")
		self.t_cursor = int(time.time())
		if not self._mutaFereastra(self.minim):
			self._alegeLaTimp()
			self._redeseneazaRand(self.indexAles())
			self._detalii()
		self._gata()

	# ------------------------------------------------------------------ fapte
	def _eveniment_si_serviciu(self):
		i, ref, s = self._randCurent()
		e = self.emisiuneAleasa()
		if s is None or e is None:
			return None, s
		return self._eveniment(ref, e), s

	def ok(self):
		i, ref, s = self._randCurent()
		if s is None:
			return
		e = self.emisiuneAleasa()
		acum = int(time.time())
		if e is not None and e[1] > acum:
			self.detalii()
			return
		if self.zapFunc is None:
			self.detalii()
			return
		try:
			cur = self.session.nav.getCurrentlyPlayingServiceReference()
			if cur is not None and G.cheie(cur) == ref:
				self.close(True)
				return
		except Exception:
			pass
		self.closeRecursive = True
		self.zapFunc(s.ref)

	def detalii(self):
		ev, s = self._eveniment_si_serviciu()
		if ev is None:
			return
		from Screens.EventView import EventViewSimple
		self.session.openWithCallback(lambda *a: self.timereSchimbate(), EventViewSimple, ev, s)

	def inregistreaza(self):
		ev, s = self._eveniment_si_serviciu()
		if ev is not None:
			self.ghidTimer.comuta(ev, s)

	def amintesteMi(self):
		ev, s = self._eveniment_si_serviciu()
		if ev is None:
			return
		from Components import HdsInregistrariProgramate as HIP
		if HIP.cautaEmisiune(self.session.nav.RecordTimer, s, ev) is not None:
			self.ghidTimer.editeaza(ev, s)
			return
		from RecordTimer import RecordTimerEntry, parseEvent
		self.ghidTimer._pune((True, RecordTimerEntry(s, checkOldTimers=True, justplay=True, *parseEvent(ev))), ev, s)

	def timereSchimbate(self):
		if self.instance is None:
			return
		self.marcaje = G.marcajeTemporizatoare(self.session.nav.RecordTimer.timer_list)
		self["grila"].l.invalidate()

	def cauta(self):
		from Screens.VirtualKeyBoard import VirtualKeyBoard
		e = self.emisiuneAleasa()
		self.session.openWithCallback(self._cautaText, VirtualKeyBoard, title=_("Caută în ghid după titlu"),
			text=(e[3] if e is not None else ""))

	def _cautaText(self, text):
		if not text:
			return
		try:
			rez = self.epg.search(("RIBDT", 200, eEPGCache.PARTIAL_TITLE_SEARCH, text, eEPGCache.NO_CASE_CHECK)) or []
		except Exception as e:
			print("[HdsGhidGrafic] cautarea: %s" % e)
			rez = []
		acum = int(time.time())
		rez = sorted((x for x in rez if x[2] is not None and x[2] + max(x[3] or 0, 60) > acum), key=lambda x: x[2])[:100]
		if not rez:
			from Screens.MessageBox import MessageBox
			self.session.open(MessageBox, _("Nicio emisiune găsită în ghid."), MessageBox.TYPE_INFO, timeout=5)
			return
		lista = []
		for r, eid, b, d, t in rez:
			try:
				nume = ServiceReference(r).getServiceName()
			except Exception:
				nume = ""
			lista.append(("%s %s   %s   %s" % (G.ziua(b, acum, self.zile, _("Today"), _("Mâine")), G.hhmm(b), nume, t),
				(r, eid, b, d, t)))
		from Screens.ChoiceBox import ChoiceBox
		self.session.openWithCallback(self._cautaAles, ChoiceBox, title=_("Rezultatele căutării"), list=lista)

	def _cautaAles(self, ales):
		if not ales:
			return
		r, eid, b, d, t = ales[1]
		c = G.cheie(r)
		cd = G.cheieDvb(r)
		for i, (k, s) in enumerate(self.randuri):
			if k == c or (cd and G.cheieDvb(k) == cd):
				self.t_cursor = b
				self._mutaLa(i)
				self.t0 = max(self.minim, G.aliniaza(b))
				self._umple(True)
				ev = self._emisiuni(k)
				j = G.indexDupaId(ev, eid)
				if j < 0:
					j = next((x for x, e in enumerate(ev) if e[1] == b), -1)
				if j >= 0:
					self.ales = j
					self._redeseneazaRand(i)
					self._detalii()
				return
		# canalul nu e in buchet: detaliile emisiunii
		try:
			ev = self.epg.lookupEventId(eServiceReference(r), eid)
		except Exception:
			ev = None
		if ev is not None:
			from Screens.EventView import EventViewSimple
			self.session.open(EventViewSimple, ev, ServiceReference(r))

	def buchetul(self):
		if not self.buchete:
			if self.bouquetChangeCB is not None:
				self.bouquetChangeCB(1, self)
			return
		from Screens.ChoiceBox import ChoiceBox
		lista = [(nume, ref) for nume, ref in self.buchete]
		self.session.openWithCallback(self._buchetAles, ChoiceBox, title=_("Alege buchetul"), list=lista)

	def _buchetAles(self, ales):
		if ales and self.alegeBuchet is not None:
			self.alegeBuchet(ales[1], self, ales[0])

	def meniu(self):
		from Screens.ChoiceBox import ChoiceBox
		lista = [(_("Alege ziua și ora"), self.alegeOra), (_("Înapoi la acum"), self.laAcum)]
		if self.ghidLista is not None:
			lista.append((_("Ghidul în listă"), self.inLista))
		self.session.openWithCallback(lambda r: r and r[1](), ChoiceBox, title=_(T_TITLU), list=lista)

	def inLista(self):
		"""Ghidul in lista pentru aceleasi canale: il deschide cine a deschis grila, dupa inchiderea ei (Session.close cere
		ca ecranul inchis sa fie cel de deasupra)."""
		self.close(False, [s for k, s in self.randuri])

	def alegeOra(self):
		from Components.config import ConfigClock
		from Screens.TimeDateInput import TimeDateInput
		# un ceas nou, fara salvare: porneste de la ora ferestrei de acum
		self.session.openWithCallback(self._oraAleasa, TimeDateInput, ConfigClock(default=max(self.t0, int(time.time()))))

	def _oraAleasa(self, ret):
		if ret and len(ret) > 1 and ret[0]:
			self.t_cursor = int(ret[1])
			self._mutaFereastra(G.aliniaza(int(ret[1])))
			self._detalii()

	# ------------------------------------------------------------------ siglele
	def siglaVenita(self, ref):
		self.sigle_venite.add(ref)
		if not self.ceasSigle.isActive():
			self.ceasSigle.start(60, True)

	def sigleVenite(self):
		venite, self.sigle_venite = self.sigle_venite, set()
		sus = self._sus()
		for i in range(sus, min(sus + self.pe_pagina, len(self.randuri))):
			if self.randuri[i][0] in venite:
				self._redeseneazaRand(i)

	def inchide(self):
		self.close(self.closeRecursive)


_MODUL_MS = (time.time() - _T_MODUL) * 1000   # cat a durat incarcarea modulului (masurare, prima deschidere)
