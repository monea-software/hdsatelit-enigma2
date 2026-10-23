# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsEcranPornire.py: ecranul din meniu prin care se alege poza de pornire (galeria gata facuta si pozele proprii).
#
# Asezarea e aceeasi ca in pagina web (HdsWebControl/ecran_pornire_web.py): sus un rand de file cu grupele („Toate”,
# „Logo”, „Natură”, ... „Pozele mele” cand exista, la urma „Adaugă o poză”), dedesubt ecranele grupei alese in
# randuri si coloane, fiecare cu poza lui mica si numele, cel pus acum cu semnul „pus acum”. Pe fila „Adaugă o poză”
# locul grilei il ia explicatia (ce poza, de unde, cat de mare, cate) si „OK: alegi poza de pe stick”.
#
# Numai sagetile si OK: Stanga/Dreapta pe file schimba grupa, Jos intra in ecrane; in ecrane sagetile muta chenarul
# (Stanga/Dreapta trec si de la un rand la altul, Sus din primul rand urca la file). OK pe un ecran deschide o
# fereastra mica cu ce se poate face cu el: „Pune acest ecran” (primul, deci OK, OK il pune), „Șterge din galerie” sau
# „Șterge poza”, „Pune la loc ecranele șterse” cand omul a sters vreunul, „Înapoi”. OK pe fila „Adaugă o poză”
# deschide navigatorul de fisiere. Tastele colorate si MENU sunt numai scurtaturi pentru aceleasi lucruri.
#
# Ecranul nu stie nimic despre fisiere: unde stau ecranele, cum se cheama, care e pus acum, cum se pune sau se sterge
# unul, cum se face un ecran dintr-o poza stau in Components/HdsEcranePornire.py, acelasi modul ca pentru web.
# Punerea si conversia unei poze merg pe un fir separat; rezultatul il arata un eTimer pe firul enigma2.
#
# Pozele mici (mici/<id>.jpg, 480x270) se decodeaza cu un singur ePicLoad, una dupa alta (coada), pe masura ce se
# arata; ultimele citite raman in memorie (cel mult MAX_POZE_TINUTE), ca schimbarea grupei sa nu le citeasca din nou.
# Un .mvi e un cadru MPEG-2 pe care Pixmap nu il poate desena, deci poza mica e singura previzualizare.
#
# Skinul se socoteste din marimea ecranului (1920x1080, 1280x720), ca sa arate la fel pe skinul nostru si pe altele.
# Textele de pe file, din casute si de pe taste stau pe aceeasi linie de baza: eticheta cu valign="center" se
# centreaza dupa conturul literelor (grc.cpp), deci „g” sau „j” ar ridica textul, iar „Ă” sau „Î” l-ar cobori. Aici
# fundalul e o eticheta, iar textul alta, transparenta, cu valign="top", asezata dupa marimea fontului (_textCentrat).

from __future__ import absolute_import

import os
import re
import threading
import time

from enigma import eListboxPythonMultiContent, ePicLoad, eTimer, ePoint, eSize, getDesktop, gRGB, RT_HALIGN_LEFT, \
	RT_VALIGN_CENTER

from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Components.ActionMap import ActionMap
from Components.FileList import FileList
from Components.HdsNavigator import HdsPanouFisiere, isPictureFile
from Components.Label import Label
from Components.Language import language
from Components.MenuList import MenuList
from Components.MultiContent import MultiContentEntryText
from Components.Pixmap import Pixmap

from Components import HdsEcranePornire as ecrane
from Components import HdsMarireText as MT

TIPAR_POZE = r"(?i)^.*\.(jpeg|jpg|png)"       # doar ce stie sa verifice modulul: JPG si PNG

COLOANE = 4
RANDURI = 3
CASUTE = COLOANE * RANDURI
MAX_FILE = 12
MAX_POZE_TINUTE = 16
# cat asteapta ecranul dupa firul de punere sau de conversie; dupa atat se elibereaza (tastele, iesirea), iar un
# raspuns venit mai tarziu nu mai atinge ecranul
TERMEN_LUCRU_S = 240

# culorile din skinul HDSatelit si rezerva pentru alt skin (0xAARRGGBB, alfa 0 = plin)
CULORI = {
	"fila": ("hdsTrack", 0x002A3350),
	"fila_aleasa": ("hdsBrand", 0x00374EA1),
	"fila_cursor": ("hdsBrandLight", 0x009FB4FF),
	"text": ("hdsText", 0x00F2F4F8),
	"text_cursor": ("hdsPanelSolid", 0x0010162A),
	"chenar": ("hdsBrandLight", 0x009FB4FF),
	"pus": ("hdsGood", 0x004FD18B),
}

def _marimeText(octeti):
	if octeti >= 1024 * 1024:
		mb = octeti / (1024.0 * 1024.0)
		if mb == int(mb):
			return "%d MB" % mb
		text = "%.1f MB" % mb
		# virgula zecimala in toate limbile imaginii, in afara de engleza
		if not str(language.getLanguage() or "").startswith("en"):
			text = text.replace(".", ",")
		return text
	return "%d KB" % (octeti // 1024)


def _culoare(cheie):
	nume, implicit = CULORI[cheie]
	try:
		import skin
		c = skin.colorNames.get(nume)
		if c is not None:
			return c
	except Exception:
		pass
	return gRGB(implicit)


def _ecran():
	try:
		d = getDesktop(0).size()
		return d.width(), d.height()
	except Exception:
		return 1920, 1080


def _scaleaza(xml, f):
	"""Skinul facut pentru 1920x1080, adus la alt ecran: pozitiile, marimile si fonturile inmultite cu f."""
	def numere(m):
		return m.group(1) + ",".join(str(int(round(int(v) * f))) for v in m.group(2).split(",")) + '"'

	xml = re.sub(r'((?:position|size)=")(\d+(?:,\d+)*)"', numere, xml)
	return re.sub(r'(font="Regular;)(\d+)"', lambda m: '%s%d"' % (m.group(1), max(14, int(round(int(m.group(2)) * f)))), xml)


class HdsAlegePoza(Screen):
	"""Navigatorul de fisiere, oprit la poze. Intoarce calea aleasa sau None."""

	# la 1920x1080; pe alt ecran se scaleaza (_scaleaza). Textul de jos are loc pentru doua randuri.
	skin = """
	<screen name="HdsAlegePoza" position="center,center" size="1440,830" title="Alege o poză">
		<widget name="hds_cale" position="24,14" size="1392,40" font="Regular;26" foregroundColor="#00ffcc66" noWrap="1" />
		<widget name="lista" position="24,62" size="1392,560" scrollbarMode="showOnDemand" />
		<widget name="hds_stare" position="24,62" size="1392,560" font="Regular;28" halign="center" valign="center" transparent="1" zPosition="2" />
		<widget name="stare" position="24,634" size="1392,96" font="Regular;26" foregroundColor="#00F2F4F8" valign="center" transparent="1" />
		<widget name="buton_rosu" position="24,748" size="340,58" backgroundColor="#009f1313" foregroundColor="#00FFFFFF" font="Regular;26" halign="center" valign="center" transparent="0" />
		<widget name="buton_verde" position="388,748" size="340,58" backgroundColor="#001f771f" foregroundColor="#00FFFFFF" font="Regular;26" halign="center" valign="center" transparent="0" />
	</screen>"""

	def __init__(self, session):
		Screen.__init__(self, session)
		l, i = _ecran()
		if (l, i) != (1920, 1080):
			self.skin = _scaleaza(HdsAlegePoza.skin, min(l / 1920.0, i / 1080.0))
		self.setTitle(_("Alege o poză"))
		self.lista = FileList(None, matchingPattern=TIPAR_POZE)
		self["lista"] = self.lista
		# bara cu calea si mesajul pentru un dosar gol (Components/HdsNavigator.py)
		self.panou = HdsPanouFisiere(self, self.lista, details=False)
		self["stare"] = Label(_("Alege poza de pe stick, apoi apasă OK. Se aduce la 1920x1080, fără deformare."))
		self["buton_rosu"] = Label(_("Înapoi"))
		self["buton_verde"] = Label(_("Alege"))
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions"], {
			"ok": self.alege,
			"green": self.alege,
			"cancel": self.inapoi,
			"red": self.inapoi,
		}, -1)

	def inapoi(self):
		self.close(None)

	def alege(self):
		if self.lista.canDescent():
			self.lista.descent()
			return
		dosar = self.lista.getCurrentDirectory() or ""
		nume = self.lista.getFilename() or ""
		if not nume:
			return
		cale = nume if os.path.isabs(nume) else os.path.join(dosar, nume)
		if not isPictureFile(cale):
			self["stare"].setText(_("Fișierul acesta nu este o poză pe care receptorul să o poată citi."))
			return
		self.close(cale)


def _masuriMeniu():
	"""(latimea ferestrei, marginea, inaltimea randului, fontul) ferestrei mici de alegere, dupa marimea ecranului. Fontul
	e pus din cod (MT.fontCod il mareste cu Marimea textului); randul, deci si fereastra, creste odata cu el cand textul
	e marit (MT.inaltimeCod, la 100 % acelasi)."""
	l, i = _ecran()
	f = l / 1920.0
	return int(820 * f), int(20 * f), MT.inaltimeCod(int(64 * f)), max(14, int(30 * f))


def _skinMeniu(randuri):
	"""Fereastra mica de alegere: cat cere lista (cel mult 6 randuri), in mijlocul ecranului. Titlul il scrie skinul
	in bara de deasupra ferestrei (setTitle)."""
	L, p, hRand, _fRand = _masuriMeniu()
	H = 2 * p + hRand * max(1, min(6, randuri))
	return ('<screen name="HdsMeniuEcranPornire" position="center,center" size="%d,%d">'
		'<widget name="lista" position="%d,%d" size="%d,%d" itemHeight="%d" '
		'scrollbarMode="showOnDemand" transparent="1" /></screen>') % (L, H, p, p, L - 2 * p, H - 2 * p, hRand)


class HdsMeniuEcranPornire(Screen):
	"""Ce se poate face cu un ecran: o fereastra mica, cu titlul in bara ei, cat lista. Intoarce (text, cheie) sau
	None (EXIT), ca ChoiceBox."""

	def __init__(self, session, titlu, alegeri):
		Screen.__init__(self, session)
		self.skin = _skinMeniu(len(alegeri))
		self.alegeri = list(alegeri)
		# fiecare rand: textul cu o margine in stanga, centrat pe verticala; primul element e cheia (rand selectabil)
		L, p, hRand, fRand = _masuriMeniu()
		lat = L - 2 * p
		randuri = [[a[1], MultiContentEntryText(pos=(p, 0), size=(lat - 2 * p, hRand), font=0,
			flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER, text=a[0])] for a in self.alegeri]
		self["lista"] = MenuList(randuri, content=eListboxPythonMultiContent)
		# fontul HD Satelit si sub un skin strain (skin.fontHds; cu HDSatelit ales ramane "Regular"), cu Marimea textului
		self["lista"].l.setFont(0, MT.fontCod("Regular", fRand))
		self["lista"].l.setItemHeight(hRand)
		self.setTitle(titlu)
		self["actiuni"] = ActionMap(["OkCancelActions", "DirectionActions"], {
			"ok": self.alege,
			"cancel": self.inapoi,
			"up": self.sus,
			"down": self.jos,
			"upRepeated": self.sus,
			"downRepeated": self.jos,
		}, -1)

	def sus(self):
		self["lista"].up()

	def jos(self):
		self["lista"].down()

	def alege(self):
		try:
			k = self["lista"].getSelectionIndex()
		except Exception:
			k = 0
		self.close(self.alegeri[k] if 0 <= k < len(self.alegeri) else None)

	def inapoi(self):
		self.close(None)


def _skinEcranPornire():
	"""Skinul ecranului, socotit din marimea desktopului (1920x1080 sau 1280x720): file sus, grila 4x3 de ecrane (sau
	explicatia de la „Adaugă o poză”), randul de stare si tastele colorate jos."""

	def _textCentrat(y, h, marime):
		"""(y, inaltime) pentru o eticheta cu valign="top" care pune randul de litere mari la mijlocul cutiei y..y+h.
		Cu valign="top" linia de baza sta la y + ascendentul fontului, oricare ar fi literele, deci toate textele cu
		aceeasi marime stau la aceeasi inaltime. Fontul skinului (HdsRegular): ascendentul ~1,08 din marimea
		fontului, literele mari ~0,71 (masurat pe fisier)."""
		sus = y + h // 2 + int(round(0.71 * marime / 2.0)) - int(round(1.08 * marime))
		return sus, int(round(1.45 * marime))

	l, i = _ecran()
	f = l / 1920.0
	# sus loc pentru bara cu titlul, pe care skinul o deseneaza deasupra ferestrei
	x, y = int(60 * f), int(60 * f)
	W, H = l - 2 * x, i - y - int(24 * f)
	p = int(20 * f)
	hFila, fFila = int(52 * f), max(14, int(26 * f))
	lPoza, hPoza = int(360 * f), int(203 * f)
	gol_x, gol_y = int(28 * f), int(18 * f)
	hNume, fNume = int(42 * f), max(14, int(26 * f))
	hCasuta = hPoza + hNume
	lGrila = COLOANE * lPoza + (COLOANE - 1) * gol_x
	x0 = (W - lGrila) // 2
	yGrila = p + hFila + int(20 * f)
	hStare, fStare = int(40 * f), max(14, int(24 * f))
	hButon, fButon = int(50 * f), max(14, int(26 * f))
	yButon = H - p - hButon
	yStare = yButon - int(10 * f) - hStare
	b = max(3, int(6 * f))           # grosimea chenarului din jurul casutei alese
	hPus, fPus = int(40 * f), max(14, int(24 * f))
	r = ['<screen name="HdsEcranPornire" position="%d,%d" size="%d,%d" title="Ecran de pornire">' % (x, y, W, H)]
	yT, hT = _textCentrat(p, hFila, fFila)
	for k in range(MAX_FILE):
		# fundalul filei si textul ei (latimea si locul le pune _deseneazaFile, dupa nume)
		r.append('<widget name="fila%d" position="%d,%d" size="%d,%d" font="Regular;%d" backgroundColor="#002A3350" '
			'zPosition="2" />' % (k, p, p, 100, hFila, fFila))
		r.append('<widget name="text_fila%d" position="%d,%d" size="%d,%d" font="Regular;%d" halign="center" valign="top" '
			'foregroundColor="#00F2F4F8" noWrap="1" transparent="1" zPosition="3" />' % (k, p, yT, 100, hT, fFila))
	r.append('<widget name="chenar" position="%d,%d" size="%d,%d" backgroundColor="#009FB4FF" zPosition="1" />'
		% (x0 - b, yGrila - b, lPoza + 2 * b, hCasuta + 2 * b))
	for k in range(CASUTE):
		cx = x0 + (k % COLOANE) * (lPoza + gol_x)
		cy = yGrila + (k // COLOANE) * (hCasuta + gol_y)
		r.append('<widget name="fundal%d" position="%d,%d" size="%d,%d" backgroundColor="#000D1120" zPosition="2" />'
			% (k, cx, cy, lPoza, hCasuta))
		r.append('<widget name="poza%d" position="%d,%d" size="%d,%d" zPosition="3" alphatest="off" />'
			% (k, cx, cy, lPoza, hPoza))
		r.append('<widget name="fara%d" position="%d,%d" size="%d,%d" font="Regular;%d" halign="center" valign="center" '
			'foregroundColor="#00AEB9CC" backgroundColor="#000D1120" zPosition="3" />'
			% (k, cx, cy, lPoza, hPoza, fStare))
		yN, hN = _textCentrat(cy + hPoza, hNume, fNume)
		r.append('<widget name="nume%d" position="%d,%d" size="%d,%d" font="Regular;%d" halign="center" valign="top" '
			'foregroundColor="#00F2F4F8" noWrap="1" transparent="1" zPosition="3" />'
			% (k, cx + int(8 * f), yN, lPoza - int(16 * f), hN, fNume))
		# insigna „pus acum”: pe un rand (noWrap), destul de lata pentru cea mai lunga traducere; la deschidere se
		# strange dupa text (_potrivesteInsignele). valign="top": textul (litere mici, cu „p”) sta cu mijlocul literelor
		# la mijlocul insignei; centrat dupa contur urca din cauza cozii lui „p”
		r.append('<widget name="pus%d" position="%d,%d" size="%d,%d" font="Regular;%d" halign="center" valign="top" '
			'foregroundColor="#0010162A" backgroundColor="#004FD18B" noWrap="1" zPosition="4" />'
			% (k, cx + int(10 * f), cy + int(10 * f), int(200 * f), hPus, fPus))
	# fila „Adaugă o poză”: explicatia, mare, in locul grilei
	hGrila = RANDURI * hCasuta + (RANDURI - 1) * gol_y
	r.append('<widget name="explicatie" position="%d,%d" size="%d,%d" font="Regular;%d" halign="center" valign="center" '
		'foregroundColor="#00F2F4F8" backgroundColor="#000D1120" zPosition="5" />'
		% (x0, yGrila, lGrila, hGrila, max(14, int(30 * f))))
	r.append('<widget name="stare" position="%d,%d" size="%d,%d" font="Regular;%d" foregroundColor="#00F2F4F8" '
		'valign="center" noWrap="1" transparent="1" zPosition="2" />' % (p, yStare, W - 2 * p - int(300 * f), hStare, fStare))
	r.append('<widget name="pagina" position="%d,%d" size="%d,%d" font="Regular;%d" foregroundColor="#00AEB9CC" '
		'halign="right" valign="center" noWrap="1" transparent="1" zPosition="2" />'
		% (W - p - int(300 * f), yStare, int(300 * f), hStare, fStare))
	lButon = (W - 2 * p - 3 * int(16 * f)) // 4
	yBT, hBT = _textCentrat(yButon, hButon, fButon)
	for k, (nume, culoare) in enumerate((("rosu", "#009F1313"), ("verde", "#001F771F"),
			("galben", "#00A08020"), ("albastru", "#00203A7A"))):
		xB = p + k * (lButon + int(16 * f))
		r.append('<widget name="tasta_%s" position="%d,%d" size="%d,%d" backgroundColor="%s" zPosition="2" />'
			% (nume, xB, yButon, lButon, hButon, culoare))
		r.append('<widget name="buton_%s" position="%d,%d" size="%d,%d" foregroundColor="#00FFFFFF" font="Regular;%d" '
			'halign="center" valign="top" noWrap="1" transparent="1" zPosition="3" />'
			% (nume, xB + int(6 * f), yBT, lButon - int(12 * f), hBT, fButon))
	r.append("</screen>")
	return "\n".join(r)


class HdsEcranPornire(Screen):
	"""Ecranul de pornire: galeria gata făcută și pozele proprii, în rânduri și coloane."""

	FILA_TOATE = "toate"
	FILA_ADAUGA = "adauga"

	def __init__(self, session):
		Screen.__init__(self, session)
		self.skin = _skinEcranPornire()
		self.setTitle(_("Ecran de pornire"))
		self.file = []                  # [{"id", "nume"}], cu „Toate” la inceput si „Adaugă o poză” la urma
		self.ecrane = []                # toate ecranele, din galerie si proprii
		self.activ = None               # {"sursa", "id"} sau None
		self.proprii = 0                # cate poze proprii are omul
		self.sterse = 0                 # cate ecrane din galerie a sters omul
		self.fila = 0                   # fila aleasa
		self.cursor = 0                 # ecranul ales in grupa (index in self._inGrupa())
		self.sus = 0                    # primul rand aratat
		self.zona = "grila"             # „file” sau „grila”
		self._inchis = False
		self._lucreaza = False
		self._lucrare = 0               # numarul lucrarii in curs (punere sau conversie)
		self._pornitLa = 0.0
		self._rezultat = None           # (lucrare, raspuns)
		self._laPozaNoua = None
		self._coada = []                # [(generatie, casuta, cale)]
		self._decodeaza = None          # (generatie, casuta, cale) in lucru
		self._generatie = 0
		self._poze = {}                 # cale -> pixmap decodat
		self._ordine_poze = []

		for k in range(MAX_FILE):
			self["fila%d" % k] = Label("")
			self["text_fila%d" % k] = Label("")
		self["chenar"] = Label("")
		for k in range(CASUTE):
			self["fundal%d" % k] = Label("")
			self["poza%d" % k] = Pixmap()
			self["fara%d" % k] = Label("")
			self["nume%d" % k] = Label("")
			self["pus%d" % k] = Label(_("pus acum"))
		self["explicatie"] = Label("")
		self["stare"] = Label("")
		self["pagina"] = Label("")
		for nume in ("rosu", "verde", "galben", "albastru"):
			self["tasta_%s" % nume] = Label("")
		self["buton_rosu"] = Label(_("Închide"))
		self["buton_verde"] = Label(_("Pune ecranul"))
		self["buton_galben"] = Label(_("Adaugă o poză"))
		self["buton_albastru"] = Label(_("Ecranul din fabrică"))

		self["actiuni"] = ActionMap(
			["OkCancelActions", "ColorActions", "DirectionActions", "MenuActions"], {
				"ok": self.apasaOk,
				"cancel": self.inchide,
				"red": self.inchide,
				"green": self.pune,
				"yellow": self.pozaMea,
				"blue": self.dinFabrica,
				"menu": self.meniulEcranului,
				"up": self.sus_,
				"down": self.jos,
				"left": self.stanga,
				"right": self.dreapta,
				"upRepeated": self.sus_,
				"downRepeated": self.jos,
				"leftRepeated": self.stanga,
				"rightRepeated": self.dreapta,
			}, -1)

		self.incarcator = ePicLoad()
		try:
			self.incarcator.PictureData.get().append(self._pozaGata)
		except AttributeError:
			self._legatura_poza = self.incarcator.PictureData.connect(self._pozaGata)

		self._ceas = eTimer()
		try:
			self._ceas.callback.append(self._bate)
		except AttributeError:
			self._ceas_conn = self._ceas.timeout.connect(self._bate)

		self.onLayoutFinish.append(self._porneste)
		self.onClose.append(self._laInchidere)

	# ------------------------------------------------------------------ viata ecranului

	def _laInchidere(self):
		# firul de conversie sau o poza decodata pot veni dupa inchidere; steagul le face inofensive
		self._inchis = True
		self._ceas.stop()
		self._coada = []
		self._poze = {}

	def _porneste(self):
		self.c = dict((k, _culoare(k)) for k in CULORI)
		try:
			marime = self["poza0"].instance.size()
			# latime, inaltime, aspectul (doua numere), memorie, felul redimensionarii, fundal
			self.incarcator.setPara((marime.width(), marime.height(), 1, 1, False, 1, "#00000000"))
		except Exception as e:
			print("[HdsEcranPornire] nu pot pregati pozele mici: %s" % e)
		self._potrivesteInsignele()
		self._reciteste(primaData=True)

	def _potrivesteInsignele(self):
		"""Insigna „pus acum” cat textul ei, plus cate o margine (textul e acelasi pe toate casutele)."""
		try:
			w = self["pus0"].instance
			lat = w.calculateSize().width()
			f = self.instance.size().width() / 1800.0
			nou = min(int(340 * f), max(int(90 * f), lat + int(32 * f)))
			if nou >= w.size().width():
				return            # latimea din skin ajunge deja
			for k in range(CASUTE):
				i = self["pus%d" % k].instance
				i.resize(eSize(nou, i.size().height()))
		except Exception as e:
			print("[HdsEcranPornire] insigna: %s" % e)

	# ------------------------------------------------------------------ datele

	def _reciteste(self, primaData=False):
		"""Reia totul de la modul: galeria, pozele proprii si care ecran e pus acum."""
		try:
			d = ecrane.lista()
		except Exception as e:
			print("[HdsEcranPornire] nu pot citi lista: %s" % e)
			d = {"grupe": [], "ecrane": [], "proprii": [], "activ": None, "poate_converti": False}
		self.activ = d.get("activ")
		self.proprii = len(d.get("proprii") or [])
		self.sterse = int(d.get("sterse") or 0)
		self.ecrane = list(d.get("ecrane") or []) + list(d.get("proprii") or [])
		fila_de_dinainte = self.file[self.fila]["id"] if self.file and 0 <= self.fila < len(self.file) else None
		self.file = [{"id": self.FILA_TOATE, "nume": _("Toate")}]
		self.file += [g for g in (d.get("grupe") or []) if g.get("id") != self.FILA_TOATE][:MAX_FILE - 2]
		self.file.append({"id": self.FILA_ADAUGA, "nume": _("Adaugă o poză")})
		if primaData:
			self._laEcranulPus()
		else:
			ids = [f["id"] for f in self.file]
			self.fila = ids.index(fila_de_dinainte) if fila_de_dinainte in ids else 0
			self.cursor = min(self.cursor, max(0, len(self._inGrupa()) - 1))
			self.sus = min(self.sus, max(0, (len(self._inGrupa()) - 1) // COLOANE - RANDURI + 1))
		if not self.ecrane:
			self["stare"].setText(_("Galeria de ecrane nu este instalată pe acest receptor. Poți folosi o poză proprie."))
		self._deseneaza()

	def _laEcranulPus(self):
		"""La deschidere: fila grupei ecranului pus acum si chenarul pe el (altfel prima grupa, primul ecran)."""
		self.fila, self.cursor, self.zona = min(1, len(self.file) - 1), 0, "grila"
		if self.activ:
			for i, e in enumerate(self.ecrane):
				if self._estePus(e):
					grup = e.get("grup")
					for k, f in enumerate(self.file):
						if f["id"] == grup:
							self.fila = k
							self.cursor = self._inGrupa().index(e)
					break
		if not self._inGrupa():
			self.zona = "file"
		self.sus = max(0, self.cursor // COLOANE - RANDURI + 1)

	def _filaAleasa(self):
		return self.file[self.fila] if 0 <= self.fila < len(self.file) else None

	def _peFilaAdauga(self):
		fila = self._filaAleasa()
		return fila is not None and fila["id"] == self.FILA_ADAUGA

	def _inGrupa(self):
		f = self._filaAleasa()
		if f is None or f["id"] == self.FILA_ADAUGA:
			return []
		if f["id"] == self.FILA_TOATE:
			return list(self.ecrane)
		return [e for e in self.ecrane if e.get("grup") == f["id"]]

	def _ecranAles(self):
		lista = self._inGrupa()
		if self.zona != "grila" or not (0 <= self.cursor < len(lista)):
			return None
		return lista[self.cursor]

	def _estePus(self, e):
		return bool(self.activ) and self.activ.get("sursa") == e.get("sursa") and self.activ.get("id") == e.get("id")

	# ------------------------------------------------------------------ desenul

	def _deseneaza(self):
		if self._inchis:
			return
		self._deseneazaFile()
		self._deseneazaGrila()
		self._deseneazaStare()

	def _latimiFile(self, latime, f):
		"""Latimea fiecarei file: textul masurat (calculateSize pe eticheta lui) plus marginile; daca nu incap toate,
		marginile se strang intai, apoi filele se micsoreaza pe masura."""
		gol = max(6, int(12 * f))
		loc = latime - 2 * int(24 * f) - gol * (len(self.file) - 1)
		texte = []
		for k, fila in enumerate(self.file):
			w = self["text_fila%d" % k]
			w.setText(fila["nume"])
			try:
				texte.append(w.instance.calculateSize().width())
			except Exception:
				texte.append(int(len(fila["nume"]) * 14.5 * f))
		for margine in (int(44 * f), int(28 * f), int(16 * f)):
			latimi = [t + margine for t in texte]
			if sum(latimi) <= loc:
				return latimi, gol
		return [max(int(60 * f), w * loc // max(1, sum(latimi))) for w in latimi], gol

	def _deseneazaFile(self):
		"""Filele pe un rand, latimea fiecareia dupa nume; cea aleasa colorata, cea cu cursorul si mai deschisa."""
		try:
			latime = self.instance.size().width()
			f = latime / 1800.0
		except Exception:
			latime, f = 1800, 1.0
		latimi, gol = self._latimiFile(latime, f)
		x = int(24 * f)
		for k in range(MAX_FILE):
			fundal, text = self["fila%d" % k], self["text_fila%d" % k]
			if k >= len(self.file):
				fundal.hide()
				text.hide()
				continue
			try:
				for w in (fundal, text):
					w.instance.move(ePoint(x, w.instance.position().y()))
					w.instance.resize(eSize(latimi[k], w.instance.size().height()))
				if k == self.fila and self.zona == "file":
					culoare, scris = self.c["fila_cursor"], self.c["text_cursor"]
				elif k == self.fila:
					culoare, scris = self.c["fila_aleasa"], self.c["text"]
				else:
					culoare, scris = self.c["fila"], self.c["text"]
				fundal.instance.setBackgroundColor(culoare)
				fundal.instance.invalidate()
				text.instance.setForegroundColor(scris)
				text.instance.invalidate()
			except Exception as e:
				print("[HdsEcranPornire] fila %d: %s" % (k, e))
			fundal.show()
			text.show()
			x += latimi[k] + gol

	def _deseneazaGrila(self):
		lista = self._inGrupa()
		self._generatie += 1
		self._coada = []
		if self._peFilaAdauga():
			self["explicatie"].setText(self._textAdauga())
			self["explicatie"].show()
		else:
			self["explicatie"].hide()
		for k in range(CASUTE):
			i = self.sus * COLOANE + k
			if i >= len(lista):
				for nume in ("fundal", "poza", "fara", "nume", "pus"):
					self["%s%d" % (nume, k)].hide()
				continue
			e = lista[i]
			self["fundal%d" % k].show()
			self["nume%d" % k].setText(e.get("nume") or e.get("id"))
			self["nume%d" % k].show()
			if self._estePus(e):
				self["pus%d" % k].show()
			else:
				self["pus%d" % k].hide()
			cale = None
			if e.get("are_poza"):
				try:
					cale = ecrane.caleMic(e.get("sursa"), e.get("id"))
				except Exception:
					cale = None
			if cale and cale in self._poze:
				self._punePoza(k, self._poze[cale])
			elif cale:
				self["poza%d" % k].hide()
				self["fara%d" % k].setText("")
				self["fara%d" % k].show()
				self._coada.append((self._generatie, k, cale))
			else:
				self["poza%d" % k].hide()
				self["fara%d" % k].setText(_("fără previzualizare"))
				self["fara%d" % k].show()
		self._mutaChenarul()
		if self._decodeaza is None:
			self._urmatoareaPoza()

	def _mutaChenarul(self):
		lista = self._inGrupa()
		k = self.cursor - self.sus * COLOANE
		if self.zona != "grila" or not lista or not (0 <= k < CASUTE):
			self["chenar"].hide()
			return
		try:
			fundal = self["fundal%d" % k].instance
			b = max(3, int(6 * self.instance.size().width() / 1800.0))
			self["chenar"].instance.move(ePoint(fundal.position().x() - b, fundal.position().y() - b))
		except Exception as e:
			print("[HdsEcranPornire] chenarul: %s" % e)
		self["chenar"].show()

	def _deseneazaStare(self):
		lista = self._inGrupa()
		if self._peFilaAdauga():
			text = ""                   # explicatia mare de deasupra spune tot, cu „OK: alegi poza de pe stick.”
		elif self.zona == "file":
			text = _("Stânga și Dreapta schimbă grupa. Jos intri la ecrane.")
		else:
			e = self._ecranAles()
			if e is None:
				text = _("Nu este niciun ecran în această grupă.")
			elif self._estePus(e):
				text = _("„%s” este pus acum.") % e.get("nume")
			elif e.get("sursa") == "propriu":
				text = _("OK: pui sau ștergi poza ta „%s”.") % e.get("nume")
			elif e.get("se_sterge"):
				text = _("OK: pui ecranul „%s” sau îl ștergi din galerie.") % e.get("nume")
			else:
				text = _("OK pune ecranul „%s”. Se vede la următoarea pornire.") % e.get("nume")
		if not self._lucreaza:
			self["stare"].setText(text)
		if lista and len(lista) > CASUTE:
			ultim = min(len(lista), (self.sus + RANDURI) * COLOANE)
			self["pagina"].setText(_("%(de)d-%(pana)d din %(tot)d") % {
				"de": self.sus * COLOANE + 1, "pana": ultim, "tot": len(lista)})
		elif lista:
			self["pagina"].setText(_("Ecrane: %d") % len(lista))
		else:
			self["pagina"].setText("")

	def _textAdauga(self):
		"""Explicatia mare de pe fila „Adaugă o poză”, in locul grilei."""
		if not ecrane.pregatitDeConversie():
			return _("Deocamdată nu se poate: receptorul nu are unealta care face un ecran de pornire dintr-o poză.")
		randuri = [
			_("Pune o poză a ta ca ecran de pornire."),
			_("Poza stă pe stick: JPG sau PNG, de cel mult %s. Receptorul o aduce la 1920x1080, fără deformare.")
				% _marimeText(ecrane.MAX_POZA),
		]
		if self.proprii >= ecrane.MAX_PROPRII:
			randuri.append(_("Ai deja %d ecrane proprii. Șterge unul înainte de a pune altul.") % ecrane.MAX_PROPRII)
		else:
			randuri.append(_("Poți avea cel mult %(cate)d poze proprii; acum ai %(ai)d.") % {
				"cate": ecrane.MAX_PROPRII, "ai": self.proprii})
			randuri.append(_("OK: alegi poza de pe stick."))
		return "\n\n".join(randuri)

	# ------------------------------------------------------------------ pozele mici

	def _urmatoareaPoza(self):
		while self._coada:
			generatie, k, cale = self._coada.pop(0)
			if generatie != self._generatie:
				continue
			self._decodeaza = (generatie, k, cale)
			try:
				if self.incarcator.startDecode(cale) == 0:
					return
			except Exception as eroare:
				print("[HdsEcranPornire] poza mica %s: %s" % (cale, eroare))
			self._decodeaza = None
		self._decodeaza = None

	def _pozaGata(self, info=""):
		if self._inchis:
			return
		lucru, self._decodeaza = self._decodeaza, None
		try:
			ptr = self.incarcator.getData()
		except Exception:
			ptr = None
		if lucru is not None and ptr is not None:
			generatie, k, cale = lucru
			self._tine(cale, ptr)
			if generatie == self._generatie:
				self._punePoza(k, ptr)
		self._urmatoareaPoza()

	def _tine(self, cale, ptr):
		if cale not in self._poze:
			self._ordine_poze.append(cale)
		self._poze[cale] = ptr
		while len(self._ordine_poze) > MAX_POZE_TINUTE:
			self._poze.pop(self._ordine_poze.pop(0), None)

	def _punePoza(self, k, ptr):
		self["fara%d" % k].hide()
		self["poza%d" % k].instance.setPixmap(ptr.__deref__())
		self["poza%d" % k].show()

	# ------------------------------------------------------------------ taste

	def _dupaMutare(self, redeseneazaGrila=False):
		lista = self._inGrupa()
		if lista:
			self.cursor = max(0, min(self.cursor, len(lista) - 1))
			rand = self.cursor // COLOANE
			sus = self.sus
			if rand < self.sus:
				self.sus = rand
			elif rand >= self.sus + RANDURI:
				self.sus = rand - RANDURI + 1
			redeseneazaGrila = redeseneazaGrila or sus != self.sus
		if redeseneazaGrila:
			self._deseneazaGrila()
		else:
			self._mutaChenarul()
		self._deseneazaFile()
		self._deseneazaStare()

	def _schimbaFila(self, pas):
		if not self.file:
			return
		self.fila = (self.fila + pas) % len(self.file)
		self.cursor, self.sus = 0, 0
		self._dupaMutare(redeseneazaGrila=True)

	def sus_(self):
		if self.zona == "grila":
			if self.cursor >= COLOANE:
				self.cursor -= COLOANE
				self._dupaMutare()
			else:
				self.zona = "file"
				self._dupaMutare()

	def jos(self):
		lista = self._inGrupa()
		if self.zona == "file":
			if lista:
				self.zona = "grila"
				self.cursor = min(self.cursor, len(lista) - 1)
				self._dupaMutare()
		elif self.cursor + COLOANE < len(lista):
			self.cursor += COLOANE
			self._dupaMutare()
		elif self.cursor // COLOANE < (len(lista) - 1) // COLOANE:
			self.cursor = len(lista) - 1         # randul de jos e mai scurt: ultimul ecran
			self._dupaMutare()

	def stanga(self):
		if self.zona == "file":
			self._schimbaFila(-1)
		elif self.cursor > 0:
			self.cursor -= 1
			self._dupaMutare()

	def dreapta(self):
		if self.zona == "file":
			self._schimbaFila(1)
		elif self.cursor + 1 < len(self._inGrupa()):
			self.cursor += 1
			self._dupaMutare()

	def apasaOk(self):
		if self._peFilaAdauga():
			self.pozaMea()
		elif self.zona == "file":
			self.jos()
		else:
			self.meniulEcranului()

	def inchide(self):
		if self._lucreaza:
			return                      # cat timp se face ecranul din poza, nu se inchide pe la spate
		self.close()

	# ------------------------------------------------------------------ ce se poate face cu un ecran

	def _alegeriPentru(self, e):
		alegeri = []
		if not self._estePus(e):
			alegeri.append((_("Pune acest ecran"), "pune"))
		if e.get("se_sterge"):
			if e.get("sursa") == "propriu":
				alegeri.append((_("Șterge poza"), "sterge"))
			else:
				alegeri.append((_("Șterge din galerie"), "sterge"))
		if self.sterse and e.get("sursa") == "galerie":
			alegeri.append((_("Pune la loc ecranele șterse (%d)") % self.sterse, "laloc"))
		if alegeri:
			alegeri.append((_("Înapoi"), "inapoi"))
		return alegeri

	def meniulEcranului(self):
		"""OK (si MENU) pe un ecran: fereastra mica cu ce se poate face cu el. Cand nu e nimic de facut (ecranul din
		fabrica pus acum, fara ecrane sterse), randul de stare spune de ce."""
		if self._lucreaza:
			return
		e = self._ecranAles()
		if e is None:
			return
		alegeri = self._alegeriPentru(e)
		if not alegeri:
			self["stare"].setText(_("„%s” este pus acum.") % e.get("nume"))
			return
		if e.get("sursa") == "propriu":
			titlu = _("Poza ta „%s”") % e.get("nume")
		else:
			titlu = _("Ecranul „%s”") % e.get("nume")
		self.session.openWithCallback(lambda r: self._alegereFacuta(e, r), HdsMeniuEcranPornire, titlu, alegeri)

	def _alegereFacuta(self, e, rezultat):
		if self._inchis or not rezultat:
			return
		if rezultat[1] == "pune":
			self._puneInFir(e["sursa"], e["id"])
		elif rezultat[1] == "sterge":
			self._intreabaStergere(e)
		elif rezultat[1] == "laloc":
			self._spune(ecrane.laLoc())

	def _intreabaStergere(self, e):
		if e.get("sursa") == "propriu":
			intrebare = _("Ștergi ecranul „%s”?") % e["nume"]
		else:
			intrebare = _("Ștergi „%s” din galerie? Îl aduci înapoi cu „Pune la loc ecranele șterse”.") % e["nume"]
		self.session.openWithCallback(
			lambda da: self._stergeConfirmat(e, da), MessageBox, intrebare, MessageBox.TYPE_YESNO, default=False)

	def _stergeConfirmat(self, e, da):
		if not da or self._inchis:
			return
		self._spune(ecrane.sterge(e["id"], e.get("sursa")))

	def _spune(self, rezultat):
		"""Arata ce a iesit si reia listele, ca „pus acum” sa fie adevarat."""
		reusit, mesaj = rezultat
		self._reciteste()
		self["stare"].setText(mesaj)
		self.session.open(MessageBox, mesaj,
			MessageBox.TYPE_INFO if reusit else MessageBox.TYPE_ERROR, timeout=8)

	# ------------------------------------------------------------------ punerea ecranului

	def pune(self):
		if self._lucreaza:
			return
		e = self._ecranAles()
		if e is None:
			return
		self._puneInFir(e["sursa"], e["id"])

	def dinFabrica(self):
		if self._lucreaza:
			return
		try:
			implicit = ecrane.implicit()
		except Exception:
			implicit = ecrane.IMPLICIT
		self._puneInFir("galerie", implicit)

	def _incepeLucrul(self, text, pas_ms):
		self._lucreaza = True
		self._lucrare += 1
		self._pornitLa = time.time()
		self._rezultat = None
		self["stare"].setText(text)
		self._ceas.start(pas_ms, False)
		return self._lucrare

	def _puneInFir(self, sursa, id_ecran):
		"""Punerea (HdsEcranePornire.aplica: temporar, verificare, os.replace) pe un fir separat, ca web-ul: firul
		enigma2 nu asteapta dupa memoria flash. Numai scrie fisierul: nu reporneste interfata, nu atinge showiframe;
		ecranul se vede la urmatoarea pornire. Rezultatul il arata _bate, pe firul enigma2."""
		lucrare = self._incepeLucrul(_("Se pune ecranul..."), 100)
		fir = threading.Thread(target=self._firPunere, args=(lucrare, sursa, id_ecran))
		fir.daemon = True
		fir.start()

	def _firPunere(self, lucrare, sursa, id_ecran):
		"""Firul punerii. Nimic de aici nu atinge un widget."""
		try:
			bun, mesaj = ecrane.aplica(sursa, id_ecran)
			raspuns = {"result": bool(bun), "message": mesaj}
		except Exception as e:          # nimic nu are voie sa scape dintr-un fir
			raspuns = {"result": False, "message": _("Nu am putut pune ecranul: %s") % e}
		self._rezultat = (lucrare, raspuns)

	# ------------------------------------------------------------------ poza utilizatorului

	def pozaMea(self):
		if self._lucreaza:
			return
		if not ecrane.pregatitDeConversie():
			self.session.open(MessageBox, self._textAdauga(), MessageBox.TYPE_INFO, timeout=10)
			return
		if self.proprii >= ecrane.MAX_PROPRII:
			self.session.open(MessageBox, _("Ai deja %d ecrane proprii. Șterge unul înainte de a pune altul.")
				% ecrane.MAX_PROPRII, MessageBox.TYPE_INFO, timeout=10)
			return
		self.session.openWithCallback(self._pozaAleasa, HdsAlegePoza)

	def _pozaAleasa(self, cale=None):
		if not cale or self._inchis:
			return
		try:
			marime = os.path.getsize(cale)
		except OSError as e:
			self["stare"].setText(_("Poza nu a putut fi citită: %s") % e)
			return
		if marime > ecrane.MAX_POZA:
			self.session.open(MessageBox, _("Poza este prea mare (%(are)s). Receptorul primește cel "
				"mult %(cat)s.") % {"are": _marimeText(marime), "cat": _marimeText(ecrane.MAX_POZA)},
				MessageBox.TYPE_ERROR, timeout=10)
			return
		lucrare = self._incepeLucrul(_("Se face ecranul de pornire din poza aleasă. Durează puțin."), 300)
		fir = threading.Thread(target=self._firPoza, args=(lucrare, cale))
		fir.daemon = True
		fir.start()

	def _firPoza(self, lucrare, cale):
		"""Firul care face treaba grea. Nimic de aici nu atinge un widget."""
		try:
			with open(cale, "rb") as f:
				octeti = f.read(ecrane.MAX_POZA + 1)
			if len(octeti) > ecrane.MAX_POZA:
				raspuns = {"result": False, "message": _("Poza este prea mare.")}
			else:
				# acelasi drum ca poza urcata din interfata web: verificare dupa continut, scriere in dosarul
				# ecranelor proprii, conversie, abia apoi punerea ecranului
				raspuns = ecrane.primestePoza(octeti, os.path.basename(cale), aplica_acum=True)
		except Exception as e:          # nimic nu are voie sa scape dintr-un fir
			raspuns = {"result": False, "message": _("Ecranul nu a putut fi făcut: %s") % e}
		raspuns["poza_noua"] = bool(raspuns.get("result") and raspuns.get("id"))
		self._rezultat = (lucrare, raspuns)

	def _bate(self):
		"""Singurul loc care atinge widgeturile cat lucreaza firul: firul enigma2."""
		if self._inchis:
			return
		rezultat = self._rezultat
		if rezultat is None or rezultat[0] != self._lucrare:
			if time.time() - self._pornitLa > TERMEN_LUCRU_S:
				# firul nu s-a intors (un stick care nu mai raspunde, un codor agatat): ecranul se elibereaza, iar
				# raspunsul lui tarziu (alta lucrare) nu mai e luat in seama
				self._ceas.stop()
				self._lucreaza = False
				self._lucrare += 1
				self._reciteste()
				mesaj = _("Receptorul nu a terminat în %d de secunde. Poți închide ecranul; ce a reușit se vede "
					"când îl deschizi din nou.") % TERMEN_LUCRU_S
				self["stare"].setText(mesaj)
				self.session.open(MessageBox, mesaj, MessageBox.TYPE_ERROR, timeout=10)
			return
		self._ceas.stop()
		self._lucreaza = False
		self._rezultat = None
		_lucrare, raspuns = rezultat
		reusit = bool(raspuns.get("pus", raspuns.get("result")))
		if raspuns.get("poza_noua"):
			nou = raspuns.get("id")
			# dupa o poza noua: fila „Pozele mele”, chenarul pe ea
			self._reciteste()
			for k, f in enumerate(self.file):
				if f["id"] == "proprii":
					self.fila, self.zona, self.sus = k, "grila", 0
					lista = self._inGrupa()
					self.cursor = ([i for i, e in enumerate(lista) if e.get("id") == nou] or [0])[0]
					self._dupaMutare(redeseneazaGrila=True)
					break
			mesaj = raspuns.get("message") or ""
			self["stare"].setText(mesaj)
			self.session.open(MessageBox, mesaj, MessageBox.TYPE_INFO if reusit else MessageBox.TYPE_ERROR, timeout=8)
		else:
			self._spune((reusit, raspuns.get("message") or ""))     # _spune reia singur listele
