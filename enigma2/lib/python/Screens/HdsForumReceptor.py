# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsForumReceptor.py: forumul receptorului pe televizor (Meniu > Setari > Beta tester > Forumul receptorului) si
# capturile de ecran. Logica: Components/HdsForumReceptor.py (forumul) si Components/HdsCapturi.py (capturile); in
# interfata web aceleasi lucruri la /forum-receptor.
#
# - HdsForum: subiectul modelului, ultimele mesaje, cel mai nou jos; fiecare mesaj pe un card (autorul, insigna, ora,
#   textul in limba receptorului, "Tradus din …", pozele mici). OK deschide mesajul, Galben (sau Sus pe primul mesaj)
#   aduce mesaje mai vechi, Albastru "Capturile mele". Testerul: Verde scrie un mesaj, MENU schimba numele de pe forum.
#   Vizitatorul: banda de invitatie si Verde "Devino beta tester" (acordul; dupa el scrierea porneste singura).
# - HdsForumMesaj: un mesaj intreg, pozele mari (Stanga/Dreapta, OK mareste), Galben/Albastru mesajul anterior/urmator,
#   Verde raspunde.
# - HdsForumScrie: textul (tastatura de pe ecran), cel mult 4 poze (Galben deschide direct galeria capturilor), Verde
#   trimite. Numele cu care apare omul se vede jos; MENU il schimba. Profilul si jetonul se pregatesc singure.
# - HdsCapturiGalerie: grila capturilor (cele mai noi intai), stick sau memoria receptorului (Albastru), alegere
#   multipla cand e deschisa din scriere, Galben sterge. O captura noua apare singura in grila.
# - HdsForumPoza: o poza pe tot ecranul.
# - HdsCapturaSalvata: mesajul mic de dupa captura, sus in dreapta, fara taste (Components/HdsCapturi.py il arata).
#
# Tot ce vorbeste cu serverul sau citeste poze mari ruleaza pe fire (Lucrare) sau in ePicLoad; ecranele asteapta cu un
# eTimer. Pozele mici se decodeaza una dupa alta (_Miniaturi).
#
# Skinul: ecranele sunt in skinul HDSatelit (HDSatelit/skin.xml, cu cadrul HdsCadru1776: titlul, ceasul, legenda
# tastelor); skinul de aici e numai rezerva pentru alt skin ales, cu aceleasi nume de widgeturi. Codul nu tine minte
# coordonate: insigna si ora se muta dupa latimea numelui, chenarele sub widgetul ales, textul cardului se strange pana
# la randul pozelor, pozele mici iau marimea widgetului, culorile puse din cod sunt rolurile skinului (CULORI).

import os
import time

from .Screen import Screen
from Components.ActionMap import ActionMap
from Components.Button import Button
from Components.Label import Label
from Components.Pixmap import Pixmap
from Components.ScrollLabel import ScrollLabel
from Components import HdsBetaTester as B
from Components import HdsCapturi as CAP
from Components import HdsForumReceptor as F
from Screens.MessageBox import MessageBox

N_ = F.N_

CARDURI = 3
POZE_PE_CARD = 4
PAS_MS = 250
TEXT_CARD_SCURT = 210
TEXT_CARD_LUNG = 430

C_CARD = "#1B2436"
C_CHENAR = "#374EA1"
C_AUTOR = "#F5B83D"
C_GRI = "#8B96A8"
C_TEXT = "#E8EDF5"
C_CREM = "#F3E3C3"
C_INSIGNA = "#3A4658"
C_ECHIPA = "#1F7A1F"
C_LOC = "#10162A"
C_ALES = "#1F7A1F"

TASTE = (("key_red", "#9F1313"), ("key_green", "#1F771F"), ("key_yellow", "#A08000"), ("key_blue", "#185090"))


def _taste(y, latime=1440, x=30, chei=None):
	"""Legenda tastelor colorate pentru skinul de rezerva (alt skin decat HDSatelit, care are cadrul lui): pe locul
	fiecarei culori o liniuta colorata si textul tastei; cele nefolosite nu apar."""
	lat = latime // 4
	rez = []
	for i, (nume, culoare) in enumerate(TASTE):
		if chei is not None and nume not in chei:
			continue
		rez.append('<eLabel position="%d,%d" size="6,32" backgroundColor="%s" zPosition="1" />' % (x + i * lat, y + 8,
			culoare))
		rez.append('<widget name="%s" position="%d,%d" size="%d,48" font="Regular;24" foregroundColor="#F2F4F8" '
			'transparent="1" valign="center" noWrap="1" zPosition="1" />' % (nume, x + i * lat + 16, y, lat - 24))
	return "\n\t\t".join(rez)


# adresa pozei de pe forum -> calea descarcata (pentru toate ecranele forumului, cat traieste interfata)
_CAI = {}


def _jurnal(text):
	print("[HdsForumReceptor] %s" % text)


def _nimic():
	pass


def _cuDirectii(actiuni):
	"""Toate actiunile hartii DirectionActions din keymap (si cele Repeated si Up): cele pe care ecranul nu le
	foloseste nu fac nimic, ca jurnalul sa nu scrie unknown action."""
	for d in ("up", "down", "left", "right"):
		for nume in (d, d + "Repeated", d + "Up"):
			actiuni.setdefault(nume, _nimic)
	return actiuni


def textTradus(limba):
	from Components.HdsForumReceptor import textTradus as tradus
	return tradus(limba)


def scurt(text, maxim):
	text = " ".join((text or "").split())
	if len(text) <= maxim:
		return text
	return text[:maxim].rsplit(" ", 1)[0] + "..."


def oraCaptura(secunde):
	return F.oraLocala(time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime(secunde)))


def marime(octeti):
	if octeti >= 1024 * 1024:
		return "%.1f MB" % (octeti / 1048576.0)
	return "%d KB" % max(1, int(round(octeti / 1024.0)))


# culorile puse din cod: rolul din skinul HDSatelit si rezerva pentru alt skin
CULORI = {
	"card": ("hdsCell", 0x1B2436),
	"card_ales": ("hdsTrack", 0x1E2A5A),
	"fila": ("hdsCell", 0x1B2436),
	"fila_aleasa": ("hdsBrand", 0x374EA1),
}


def _culoare(cheie):
	nume, rezerva = CULORI[cheie]
	try:
		import skin
		c = skin.colorNames.get(nume)
		if c is not None:
			return c
	except Exception:
		pass
	try:
		from enigma import gRGB
		return gRGB(rezerva)
	except Exception:
		return None


def _pozitie(w):
	"""(x, y, latime, inaltime) ale widgetului dupa asezarea skinului, sau None."""
	try:
		i = w.instance
		p, m = i.position(), i.size()
		return p.x(), p.y(), m.width(), m.height()
	except Exception:
		return None


def _mutaX(w, x):
	p = _pozitie(w)
	if p is not None:
		_muta(w, x, p[1])


def _chenarPe(chenar, w, b=4):
	"""Chenarul (o eticheta plina, mai mare cu b pe fiecare parte) mutat sub widgetul w."""
	p = _pozitie(w)
	if p is not None:
		_muta(chenar, p[0] - b, p[1] - b)


def _ceas(functie):
	from enigma import eTimer
	t = eTimer()
	t.callback.append(functie)
	return t


def _marimeInstanta(w, latime=None, inaltime=None):
	try:
		from enigma import eSize
		i = w.instance
		if i is None:
			return
		i.resize(eSize(latime if latime is not None else i.size().width(),
			inaltime if inaltime is not None else i.size().height()))
	except Exception as e:
		_jurnal("marimea: %s" % e)


def _muta(w, x, y):
	try:
		from enigma import ePoint
		if w.instance is not None:
			w.instance.move(ePoint(x, y))
	except Exception as e:
		_jurnal("locul: %s" % e)


def _latimeText(w, implicit):
	try:
		return w.instance.calculateSize().width()
	except Exception:
		return implicit


def _fundal(w, cheie):
	c = _culoare(cheie)
	try:
		if c is not None and w.instance is not None:
			w.instance.setBackgroundColor(c)
			w.instance.invalidate()
	except Exception as e:
		_jurnal("culoarea: %s" % e)


class _Miniaturi(object):
	"""Un singur ePicLoad, pozele una dupa alta (coada), pixmap-urile tinute minte pe cale. pune(cheie, pixmap) le
	duce pe ecran; cheia spune ecranului daca mai e de actualitate."""

	def __init__(self, latime, inaltime, pune, maxim=40):
		from enigma import ePicLoad
		self.pl = ePicLoad()
		try:
			self.pl.PictureData.get().append(self._gata)
		except AttributeError:
			self._legatura = self.pl.PictureData.connect(self._gata)
		self.latime, self.inaltime = latime, inaltime
		self.pune = pune
		self.maxim = maxim
		self.coada = []
		self.lucru = None
		self.tinute = {}
		self.ordine = []
		self.oprit = False
		self.pregatit = False

	def pregateste(self, w=None):
		"""Marimea pozelor: a widgetului w (din skin), altfel cea data la facere."""
		p = _pozitie(w) if w is not None else None
		if p is not None and p[2] > 0 and p[3] > 0:
			self.latime, self.inaltime = p[2], p[3]
		try:
			# latime, inaltime, aspectul (doua numere), memorie, felul redimensionarii, fundal
			self.pl.setPara((self.latime, self.inaltime, 1, 1, False, 1, "#00101626"))
			self.pregatit = True
		except Exception as e:
			_jurnal("pozele mici: %s" % e)

	def cere(self, cheie, cale):
		if self.oprit or not cale:
			return
		if cale in self.tinute:
			self.pune(cheie, self.tinute[cale])
			return
		self.coada.append((cheie, cale))
		if self.lucru is None:
			self._urmatoarea()

	def goleste(self):
		self.coada = []

	def uita(self, cale):
		self.tinute.pop(cale, None)

	def opreste(self):
		self.oprit = True
		self.coada = []
		self.tinute = {}

	def _urmatoarea(self):
		while self.coada and self.pregatit:
			cheie, cale = self.coada.pop(0)
			if cale in self.tinute:
				self.pune(cheie, self.tinute[cale])
				continue
			self.lucru = (cheie, cale)
			try:
				if self.pl.startDecode(cale) == 0:
					return
			except Exception as e:
				_jurnal("poza %s: %s" % (cale, e))
			self.lucru = None
		self.lucru = None

	def _gata(self, info=""):
		if self.oprit:
			return
		lucru, self.lucru = self.lucru, None
		try:
			ptr = self.pl.getData()
		except Exception:
			ptr = None
		if lucru is not None and ptr is not None:
			cale = lucru[1]
			if cale not in self.tinute:
				self.ordine.append(cale)
			self.tinute[cale] = ptr
			while len(self.ordine) > self.maxim:
				self.tinute.pop(self.ordine.pop(0), None)
			self.pune(lucru[0], ptr)
		self._urmatoarea()


def _punePixmap(w, ptr, loc=None):
	try:
		w.instance.setPixmap(ptr.__deref__())
		w.show()
		if loc is not None:
			loc.hide()
	except Exception as e:
		_jurnal("poza: %s" % e)


def _descarcata(adresa):
	"""Poza e deja in dosarul pozelor descarcate (dosarul are limita: una veche poate fi stearsa intre timp)."""
	cale = _CAI.get(adresa)
	if cale and os.path.isfile(cale):
		return True
	_CAI.pop(adresa, None)
	return False


class _Descarcari(object):
	"""Pozele de pe forum, descarcate una dupa alta pe un fir (Components/HdsForumReceptor.descarcaPoza). gata(cheie,
	cale) se cheama de pe firul enigma2, din bate()."""

	def __init__(self, gata):
		self.gata = gata
		self.coada = []
		self.lucru = None

	def cere(self, cheie, adresa):
		if not adresa:
			return
		if _descarcata(adresa):
			self.gata(cheie, _CAI[adresa])
			return
		self.coada.append((cheie, adresa))

	def goleste(self):
		self.coada = []

	def bate(self):
		"""-> True cat mai are de lucru."""
		if self.lucru is not None:
			cheie, adresa, l = self.lucru
			if not l.gata:
				return True
			self.lucru = None
			if l.reusit:
				_CAI[adresa] = l.rezultat
				self.gata(cheie, l.rezultat)
		while self.coada and self.lucru is None:
			cheie, adresa = self.coada.pop(0)
			if _descarcata(adresa):
				self.gata(cheie, _CAI[adresa])
				continue
			self.lucru = (cheie, adresa, F.descarcaPoza(adresa))
		return self.lucru is not None


def _tastaturaNume(ecran, dupa):
	"""MENU: 'Numele tău pe forum', tastatura de pe ecran cu numele de acum; OK salveaza (schimbaNume pe un fir)."""
	from Screens.VirtualKeyBoard import VirtualKeyBoard

	def gata(text=None):
		if text is None:
			return
		text = " ".join(text.split())
		if text == F.numePublic():
			return
		dupa(F.schimbaNume(text))
	ecran.session.openWithCallback(gata, VirtualKeyBoard, title=_("Numele tău pe forum"), text=F.numePublic())


# ------------------------------------------------------------------ forumul

def _skinForum():
	W, H = 1500, 920
	r = ['<screen name="HdsForum" resolution="1920,1080" position="center,center" size="%d,%d" '
		'title="Forumul receptorului">' % (W, H)]
	r.append('<widget name="subiect" position="30,10" size="1060,40" font="Regular;28" foregroundColor="%s" noWrap="1" '
		'transparent="1" />' % C_CREM)
	r.append('<widget name="numar" position="1100,16" size="370,32" font="Regular;20" foregroundColor="%s" halign="right" '
		'noWrap="1" transparent="1" />' % C_GRI)
	r.append('<widget name="linie" position="30,56" size="1440,2" backgroundColor="%s" />' % C_AUTOR)
	# banda: invitatia pentru vizitator, numele de pe forum pentru tester
	r.append('<widget name="banda_fundal" position="30,72" size="1440,70" backgroundColor="%s" zPosition="1" />' % C_CARD)
	r.append('<widget name="banda_bara" position="30,72" size="6,70" backgroundColor="%s" zPosition="2" />' % C_AUTOR)
	r.append('<widget name="banda" position="52,76" size="1400,34" font="Regular;23" foregroundColor="%s" noWrap="1" '
		'transparent="1" zPosition="2" />' % C_CREM)
	r.append('<widget name="banda_jos" position="52,110" size="1400,30" font="Regular;19" foregroundColor="%s" '
		'noWrap="1" transparent="1" zPosition="2" />' % C_GRI)
	y0, ch, gol = 154, 210, 10
	r.append('<widget name="chenar" position="26,%d" size="1448,%d" backgroundColor="%s" zPosition="0" />'
		% (y0 - 4, ch + 8, C_CHENAR))
	for k in range(CARDURI):
		y = y0 + k * (ch + gol)
		r.append('<widget name="fundal%d" position="30,%d" size="1440,%d" backgroundColor="%s" zPosition="1" />'
			% (k, y, ch, C_CARD))
		r.append('<widget name="autor%d" position="50,%d" size="560,36" font="Regular;26" foregroundColor="%s" noWrap="1" '
			'transparent="1" zPosition="2" />' % (k, y + 10, C_AUTOR))
		r.append('<widget name="insigna%d" position="620,%d" size="150,28" font="Regular;17" halign="center" '
			'valign="center" foregroundColor="#DCE1FD" backgroundColor="%s" noWrap="1" zPosition="3" />'
			% (k, y + 14, C_INSIGNA))
		r.append('<widget name="echipa%d" position="620,%d" size="150,28" font="Regular;17" halign="center" '
			'valign="center" foregroundColor="#FFFFFF" backgroundColor="%s" noWrap="1" zPosition="3" />'
			% (k, y + 14, C_ECHIPA))
		r.append('<widget name="ora%d" position="790,%d" size="300,30" font="Regular;20" foregroundColor="%s" noWrap="1" '
			'transparent="1" zPosition="2" />' % (k, y + 14, C_GRI))
		r.append('<widget name="tradus%d" position="1100,%d" size="350,30" font="Regular;18" foregroundColor="%s" '
			'halign="right" noWrap="1" transparent="1" zPosition="2" />' % (k, y + 16, C_GRI))
		r.append('<widget name="asteapta%d" position="1210,%d" size="240,30" font="Regular;18" halign="center" '
			'valign="center" foregroundColor="#FABC41" backgroundColor="#5E4200" noWrap="1" zPosition="3" />'
			% (k, y + 12))
		r.append('<widget name="text%d" position="50,%d" size="1400,%d" font="Regular;24" foregroundColor="%s" '
			'valign="top" transparent="1" zPosition="2" />' % (k, y + 52, ch - 64, C_TEXT))
		for j in range(POZE_PE_CARD):
			x = 50 + j * (128 + 12)
			r.append('<widget name="loc%d_%d" position="%d,%d" size="128,72" backgroundColor="%s" zPosition="2" />'
				% (k, j, x, y + ch - 84, C_LOC))
			r.append('<widget name="poza%d_%d" position="%d,%d" size="128,72" zPosition="3" alphatest="off" />'
				% (k, j, x, y + ch - 84))
	r.append('<widget name="gol" position="30,%d" size="1440,%d" font="Regular;26" halign="center" valign="center" '
		'foregroundColor="%s" transparent="1" zPosition="4" />' % (y0, CARDURI * ch + (CARDURI - 1) * gol, C_TEXT))
	r.append('<widget name="stare" position="30,816" size="1000,36" font="Regular;20" foregroundColor="#DCE1FD" '
		'noWrap="1" transparent="1" />')
	r.append('<widget name="pagina" position="1040,816" size="430,36" font="Regular;20" foregroundColor="%s" '
		'halign="right" noWrap="1" transparent="1" />' % C_GRI)
	r.append(_taste(866, 1440))
	r.append("</screen>")
	return "\n\t".join(r)


class HdsForum(Screen):
	skin = _skinForum()

	def __init__(self, session):
		Screen.__init__(self, session)
		self.setTitle(_("Forumul receptorului"))
		self.tester = F.poateScrie()
		self.mesaje = []
		self.cursor = 0
		self.sus = 0
		self.subiect = {}
		self.mai_vechi = False
		self._citire = None
		self._fel_citire = ""
		self._nume = None
		self._generatie = 0
		self._inchis = False
		# textul de jos care ramane dupa citirea pornita odata cu el (mesajul trimis, numele schimbat)
		self._dupaCitireText = ""
		self._texte = {}
		for nume in ("subiect", "numar", "banda", "banda_jos", "gol", "stare", "pagina"):
			self[nume] = Label("")
		for nume in ("linie", "banda_fundal", "banda_bara", "chenar"):
			self[nume] = Label("")
		for k in range(CARDURI):
			for nume in ("fundal", "autor", "ora", "tradus", "text"):
				self["%s%d" % (nume, k)] = Label("")
			self["insigna%d" % k] = Label(_("Beta tester").upper())
			self["echipa%d" % k] = Label(_("Echipa").upper())
			self["asteapta%d" % k] = Label(_("Așteaptă aprobarea"))
			for j in range(POZE_PE_CARD):
				self["loc%d_%d" % (k, j)] = Label("")
				self["poza%d_%d" % (k, j)] = Pixmap()
		self["key_red"] = Button(_("Înapoi"))
		self["key_green"] = Button("")
		self["key_yellow"] = Button(_("Mai vechi"))
		self["key_blue"] = Button(_("Capturile mele"))
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions", "MenuActions"], _cuDirectii({
			"ok": self.deschide,
			"cancel": self.close,
			"red": self.close,
			"green": self.verde,
			"yellow": self.maiVechi,
			"blue": self.capturi,
			"menu": self.schimbaNumele,
			"up": self.sus_,
			"down": self.jos,
			"upRepeated": self.sus_,
			"downRepeated": self.jos,
		}), -1)
		self._ceas = _ceas(self._bate)
		self.miniaturi = _Miniaturi(128, 72, self._pozaMica)
		self.descarcari = _Descarcari(self._descarcata)
		self.onLayoutFinish.append(self._porneste)
		self.onClose.append(self._laInchidere)
		self._texteTester()
		self._ascundeCardurile()

	# ------------------------------------------------------------ viata ecranului

	def _porneste(self):
		self.miniaturi.pregateste(self["poza0_0"])
		# marimea textului fiecarui card din skin (fara poze); cu poze se strange pana la randul lor
		self._texte = dict((k, _pozitie(self["text%d" % k])) for k in range(CARDURI))
		self._citeste()

	def _laInchidere(self):
		self._inchis = True
		self._ceas.stop()
		self.miniaturi.opreste()
		self.descarcari.goleste()
		# pozele descarcate (in RAM) se sterg odata cu forumul
		_CAI.clear()
		F.golestePozele()

	def _texteTester(self):
		self["key_green"].setText(_("Scrie un mesaj") if self.tester else _("Devino beta tester"))
		self._banda()

	def _banda(self):
		if self.tester:
			nume = F.numePublic()
			self["banda"].setText(_("Apari pe forum ca „%s”.") % nume if nume else
				_("Aici scriu beta testerii acestui receptor."))
			self["banda_jos"].setText(_("MENU: schimbă numele tău de pe forum"))
		else:
			self["banda"].setText(_("Aici scriu beta testerii acestui receptor. Ca să scrii și tu, devino beta tester."))
			self["banda_jos"].setText(B.randNumar())

	def _citeste(self, inainte=None):
		if self._citire is not None:
			return
		self._fel_citire = "vechi" if inainte is not None else "nou"
		self._citire = F.citeste(inainte)
		self["stare"].setText(_("Se citește forumul..."))
		if not self.mesaje:
			self["gol"].setText(_("Se citește forumul..."))
		self._ceas.start(PAS_MS, False)

	def _bate(self):
		if self._inchis:
			return
		lucreaza = False
		c = self._citire
		if c is not None:
			if c.gata:
				self._citire = None
				self._dupaCitire(c)
			else:
				lucreaza = True
		n = self._nume
		if n is not None:
			if n.gata:
				self._nume = None
				self._dupaNume(n)
			else:
				lucreaza = True
		if self.descarcari.bate():
			lucreaza = True
		if not lucreaza and self._citire is None and self._nume is None:
			self._ceas.stop()

	def _dupaCitire(self, c):
		if not c.reusit:
			self["stare"].setText(c.mesaj)
			if not self.mesaje:
				self["gol"].setText(c.mesaj)
			return
		self._arata(c.rezultat, vechi=self._fel_citire == "vechi")

	def _arata(self, rezultat, vechi=False):
		rezultat = rezultat if isinstance(rezultat, dict) else {}
		noi = [m for m in (rezultat.get("mesaje") or []) if isinstance(m, dict)]
		self.subiect = rezultat.get("subiect") if isinstance(rezultat.get("subiect"), dict) else self.subiect
		if vechi:
			cunoscute = set(m.get("nr") for m in self.mesaje)
			noi = [m for m in noi if m.get("nr") not in cunoscute]
			self.mesaje = noi + self.mesaje
			self.cursor += len(noi)
			if noi:
				self.cursor -= 1
				self.sus = max(0, self.cursor - CARDURI + 1)
		else:
			self.mesaje = noi
			self.cursor = max(0, len(noi) - 1)
			self.sus = max(0, len(noi) - CARDURI)
			F.tineVazut(rezultat)      # ultimele mesaje sunt pe ecran: insigna din meniul testerului se sterge
		self.mai_vechi = bool(rezultat.get("mai_vechi"))
		self["subiect"].setText(self.subiect.get("titlu") or _("Forumul receptorului"))
		total = self.subiect.get("mesaje")
		self["numar"].setText((_("Mesaje: %d") % total) if isinstance(total, int) else "")
		self._banda()
		if vechi and not noi:
			self["stare"].setText(_("Nu sunt mesaje mai vechi."))
		else:
			self["stare"].setText(self._dupaCitireText)
		self._dupaCitireText = ""
		self["gol"].setText("" if self.mesaje else _("Încă nu e niciun mesaj aici."))
		self._deseneaza()

	# ------------------------------------------------------------ desenul

	def _ascundeCardurile(self):
		for k in range(CARDURI):
			self._ascundeCard(k)
		self["chenar"].hide()

	def _ascundeCard(self, k):
		for nume in ("fundal", "autor", "insigna", "echipa", "ora", "tradus", "asteapta", "text"):
			self["%s%d" % (nume, k)].hide()
		for j in range(POZE_PE_CARD):
			self["loc%d_%d" % (k, j)].hide()
			self["poza%d_%d" % (k, j)].hide()

	def _deseneaza(self):
		if self._inchis:
			return
		self._generatie += 1
		self.miniaturi.goleste()
		self.descarcari.goleste()
		self["chenar"].hide()
		for k in range(CARDURI):
			i = self.sus + k
			if i >= len(self.mesaje):
				self._ascundeCard(k)
				continue
			self._deseneazaCard(k, self.mesaje[i], i == self.cursor)
		if self.mesaje:
			total = self.subiect.get("mesaje") if isinstance(self.subiect.get("mesaje"), int) else len(self.mesaje)
			total = max(total, len(self.mesaje))
			baza = total - len(self.mesaje)
			ultim = min(len(self.mesaje), self.sus + CARDURI)
			self["pagina"].setText(_("%(de)d-%(pana)d din %(tot)d") % {"de": baza + self.sus + 1, "pana": baza + ultim,
				"tot": total})
		else:
			self["pagina"].setText("")
		if self.descarcari.coada:
			self._ceas.start(PAS_MS, False)

	def _deseneazaCard(self, k, m, ales):
		fundal = self["fundal%d" % k]
		fundal.show()
		_fundal(fundal, "card_ales" if ales else "card")
		if ales:
			_chenarPe(self["chenar"], fundal)
			self["chenar"].show()
		autor = self["autor%d" % k]
		autor.setText(m.get("autor") or "")
		autor.show()
		# insigna si ora imediat dupa nume (latimea numelui masurata)
		pa = _pozitie(autor)
		x = pa[0] + min(pa[2], _latimeText(autor, pa[2] // 2)) + 16 if pa else None
		insigna = m.get("insigna") or ""
		for nume, fel in (("insigna", "tester"), ("echipa", "echipa")):
			w = self["%s%d" % (nume, k)]
			if insigna == fel:
				if x is not None:
					_mutaX(w, x)
					pw = _pozitie(w)
					x += (pw[2] if pw else 150) + 14
				w.show()
			else:
				w.hide()
		ora = self["ora%d" % k]
		ora.setText(F.oraLocala(m.get("cand") or ""))
		if x is not None:
			_mutaX(ora, x)
		ora.show()
		tradus, asteapta = self["tradus%d" % k], self["asteapta%d" % k]
		if m.get("stare") == "asteapta":
			asteapta.show()
			tradus.hide()
		else:
			asteapta.hide()
			tradus.setText(textTradus(m.get("tradus_din")))
			tradus.show()
		poze = [p for p in (m.get("poze") or []) if isinstance(p, dict) and p.get("adresa")][:POZE_PE_CARD]
		text = self["text%d" % k]
		text.setText(F.textCuPozeAscunse(scurt(m.get("text"), TEXT_CARD_SCURT if poze else TEXT_CARD_LUNG), m))
		self._marimeText(k, bool(poze))
		text.show()
		for j in range(POZE_PE_CARD):
			loc, poza = self["loc%d_%d" % (k, j)], self["poza%d_%d" % (k, j)]
			poza.hide()
			if j < len(poze):
				loc.show()
				self.descarcari.cere((self._generatie, k, j), poze[j]["adresa"])
			else:
				loc.hide()

	def _marimeText(self, k, cu_poze):
		"""Textul cardului: cat il da skinul; cu poze, pana la randul lor (sub text) sau pana la ele (in dreapta)."""
		t = self._texte.get(k)
		if t is None:
			return
		latime, inaltime = t[2], t[3]
		if cu_poze:
			p = _pozitie(self["loc%d_0" % k])
			if p is not None and p[1] > t[1]:
				inaltime = max(20, p[1] - t[1] - 6)
			elif p is not None:
				latime = max(100, p[0] - t[0] - 16)
		_marimeInstanta(self["text%d" % k], latime, inaltime)

	def _descarcata(self, cheie, cale):
		if cheie[0] == self._generatie:
			self.miniaturi.cere(cheie, cale)

	def _pozaMica(self, cheie, ptr):
		generatie, k, j = cheie
		if generatie != self._generatie or self._inchis:
			return
		_punePixmap(self["poza%d_%d" % (k, j)], ptr, self["loc%d_%d" % (k, j)])

	# ------------------------------------------------------------ tastele

	def sus_(self):
		if not self.mesaje:
			return
		if self.cursor == 0:
			if self.mai_vechi:
				self.maiVechi()
			return
		self.cursor -= 1
		if self.cursor < self.sus:
			self.sus = self.cursor
		self._deseneaza()

	def jos(self):
		if not self.mesaje or self.cursor >= len(self.mesaje) - 1:
			return
		self.cursor += 1
		if self.cursor >= self.sus + CARDURI:
			self.sus = self.cursor - CARDURI + 1
		self._deseneaza()

	def maiVechi(self):
		if not self.mesaje:
			self._citeste()
			return
		if not self.mai_vechi:
			self["stare"].setText(_("Nu sunt mesaje mai vechi."))
			return
		self._citeste(inainte=self.mesaje[0].get("nr"))

	def deschide(self):
		if not self.mesaje:
			self._citeste()
			return
		self.session.openWithCallback(self._dupaMesaj, HdsForumMesaj, self.mesaje, self.cursor, self.tester)

	def _dupaMesaj(self, rezultat=None):
		if not isinstance(rezultat, dict):
			return
		i = rezultat.get("index")
		if isinstance(i, int) and 0 <= i < len(self.mesaje):
			self.cursor = i
			if self.cursor < self.sus:
				self.sus = self.cursor
			elif self.cursor >= self.sus + CARDURI:
				self.sus = self.cursor - CARDURI + 1
			self._deseneaza()
		if rezultat.get("fa") in ("scrie", "acord"):
			self.verde(rezultat.get("text") or "")

	def verde(self, text=""):
		if self.tester:
			self.session.openWithCallback(self._dupaScriere, HdsForumScrie, text if isinstance(text, str) else "",
				self.subiect.get("titlu") or "")
			return
		from Screens.HdsBetaTester import HdsBetaAcord
		self.session.openWithCallback(self._dupaAcord, HdsBetaAcord)

	def _dupaAcord(self, *_r):
		if not F.poateScrie():
			return
		self.tester = True
		F.uitaJetonul()
		self._texteTester()
		self._citeste()
		self.verde()

	def _dupaScriere(self, rezultat=None):
		if not isinstance(rezultat, dict):
			return
		if rezultat.get("stare") == "asteapta":
			text = _("Mesajul tău a plecat și așteaptă aprobarea: până atunci îl vezi numai tu.")
		else:
			text = _("Mesajul tău a plecat.")
		self._citeste()
		self._dupaCitireText = text
		self["stare"].setText(text)

	def capturi(self):
		self.session.open(HdsCapturiGalerie)

	def schimbaNumele(self):
		if not self.tester or self._nume is not None:
			return
		_tastaturaNume(self, self._numePornit)

	def _numePornit(self, lucrare):
		self._nume = lucrare
		self["stare"].setText(_("Se schimbă numele..."))
		self._ceas.start(PAS_MS, False)

	def _dupaNume(self, n):
		if not n.reusit:
			self["stare"].setText(n.mesaj)
			return
		self._banda()
		self._citeste()
		self._dupaCitireText = _("Numele tău pe forum e acum „%s”.") % (n.rezultat or {}).get("nume", "")
		self["stare"].setText(self._dupaCitireText)


# ------------------------------------------------------------------ un mesaj

class HdsForumMesaj(Screen):
	skin = """
	<screen name="HdsForumMesaj" resolution="1920,1080" position="center,center" size="1500,920" title="Forumul receptorului">
		<widget name="autor" position="30,12" size="600,40" font="Regular;28" foregroundColor="%(autor)s" noWrap="1" transparent="1" />
		<widget name="insigna" position="640,18" size="150,30" font="Regular;18" halign="center" valign="center" foregroundColor="#DCE1FD" backgroundColor="%(insigna)s" noWrap="1" zPosition="2" />
		<widget name="echipa" position="640,18" size="150,30" font="Regular;18" halign="center" valign="center" foregroundColor="#FFFFFF" backgroundColor="%(echipa)s" noWrap="1" zPosition="2" />
		<widget name="ora" position="810,18" size="300,30" font="Regular;21" foregroundColor="%(gri)s" noWrap="1" transparent="1" />
		<widget name="tradus" position="1090,18" size="380,30" font="Regular;20" foregroundColor="%(gri)s" halign="right" noWrap="1" transparent="1" />
		<widget name="asteapta" position="1220,16" size="250,32" font="Regular;19" halign="center" valign="center" foregroundColor="#FABC41" backgroundColor="#5E4200" noWrap="1" zPosition="2" />
		<widget name="linie" position="30,60" size="1440,2" backgroundColor="%(autor)s" />
		<widget name="text" position="30,74" size="1440,240" font="Regular;25" foregroundColor="%(text)s" />
		<widget name="loc_mare" position="30,330" size="768,432" backgroundColor="%(loc)s" zPosition="1" />
		<widget name="mare" position="30,330" size="768,432" zPosition="2" alphatest="off" />
		<widget name="chenar" position="826,326" size="184,107" backgroundColor="%(chenar)s" zPosition="1" />
		%(mici)s
		<widget name="stare" position="30,780" size="1000,36" font="Regular;20" foregroundColor="#DCE1FD" noWrap="1" transparent="1" />
		<widget name="pagina" position="1040,780" size="430,36" font="Regular;20" foregroundColor="%(gri)s" halign="right" noWrap="1" transparent="1" />
		%(taste)s
	</screen>
	""" % {"autor": C_AUTOR, "insigna": C_INSIGNA, "echipa": C_ECHIPA, "gri": C_GRI, "text": C_TEXT, "loc": C_LOC,
		"chenar": C_CHENAR, "taste": _taste(866, 1440), "mici": "\n\t\t".join(
			'<widget name="loc_mic%d" position="830,%d" size="176,99" backgroundColor="%s" zPosition="2" />'
			'<widget name="mic%d" position="830,%d" size="176,99" zPosition="3" alphatest="off" />'
			% (j, 330 + j * 111, C_LOC, j, 330 + j * 111) for j in range(POZE_PE_CARD))}

	def __init__(self, session, mesaje, index=0, tester=False):
		Screen.__init__(self, session)
		self.setTitle(_("Forumul receptorului"))
		self.mesaje = list(mesaje or [])
		self.index = max(0, min(index, len(self.mesaje) - 1))
		self.tester = tester
		self.poza = 0
		self.cai = {}
		self._inchis = False
		self._generatie = 0
		for nume in ("autor", "ora", "tradus", "linie", "loc_mare", "chenar", "stare", "pagina"):
			self[nume] = Label("")
		self["insigna"] = Label(_("Beta tester").upper())
		self["echipa"] = Label(_("Echipa").upper())
		self["asteapta"] = Label(_("Așteaptă aprobarea"))
		self["text"] = ScrollLabel("")
		self["mare"] = Pixmap()
		for j in range(POZE_PE_CARD):
			self["loc_mic%d" % j] = Label("")
			self["mic%d" % j] = Pixmap()
		self["key_red"] = Button(_("Înapoi"))
		self["key_green"] = Button(_("Răspunde") if tester else _("Devino beta tester"))
		self["key_yellow"] = Button(_("Mesajul anterior"))
		self["key_blue"] = Button(_("Mesajul următor"))
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], _cuDirectii({
			"ok": self.mareste,
			"cancel": self.inapoi,
			"red": self.inapoi,
			"green": self.verde,
			"yellow": self.anterior,
			"blue": self.urmator,
			"left": self.stanga,
			"right": self.dreapta,
			"up": self.textSus,
			"down": self.textJos,
		}), -1)
		self._ceas = _ceas(self._bate)
		self.mici = _Miniaturi(176, 99, self._pozaMica)
		self.mari = _Miniaturi(768, 432, self._pozaMare, maxim=6)
		self.descarcari = _Descarcari(self._descarcata)
		self.onLayoutFinish.append(self._porneste)
		self.onClose.append(self._laInchidere)
		self._arata()

	def _porneste(self):
		self.mici.pregateste(self["mic0"])
		self.mari.pregateste(self["mare"])
		self._arata()

	def _laInchidere(self):
		self._inchis = True
		self._ceas.stop()
		self.mici.opreste()
		self.mari.opreste()

	def _poze(self):
		if not self.mesaje:
			return []
		m = self.mesaje[self.index]
		return [p.get("adresa") for p in (m.get("poze") or []) if isinstance(p, dict) and p.get("adresa")][:POZE_PE_CARD]

	def _arata(self):
		self._generatie += 1
		self.descarcari.goleste()
		self.mici.goleste()
		self.mari.goleste()
		if not self.mesaje:
			return
		m = self.mesaje[self.index]
		self["autor"].setText(m.get("autor") or "")
		insigna = m.get("insigna") or ""
		pa = _pozitie(self["autor"])
		x = pa[0] + min(pa[2], _latimeText(self["autor"], pa[2] // 2)) + 16 if pa else None
		for nume, fel in (("insigna", "tester"), ("echipa", "echipa")):
			if insigna == fel:
				if x is not None:
					_mutaX(self[nume], x)
					pw = _pozitie(self[nume])
					x += (pw[2] if pw else 150) + 16
				self[nume].show()
			else:
				self[nume].hide()
		self["ora"].setText(F.oraLocala(m.get("cand") or ""))
		if x is not None:
			_mutaX(self["ora"], x)
		if m.get("stare") == "asteapta":
			self["asteapta"].show()
			self["tradus"].hide()
		else:
			self["asteapta"].hide()
			self["tradus"].setText(textTradus(m.get("tradus_din")))
			self["tradus"].show()
		self["text"].setText(F.textCuPozeAscunse(m.get("text") or "", m))
		poze = self._poze()
		self.poza = min(self.poza, max(0, len(poze) - 1))
		for j in range(POZE_PE_CARD):
			self["mic%d" % j].hide()
			if j < len(poze):
				self["loc_mic%d" % j].show()
				self.descarcari.cere((self._generatie, j), poze[j])
			else:
				self["loc_mic%d" % j].hide()
		self["mare"].hide()
		if poze:
			self["loc_mare"].show()
			self._chenar()
		else:
			self["loc_mare"].hide()
			self["chenar"].hide()
		self._pagina()
		if self.descarcari.coada:
			self._ceas.start(PAS_MS, False)

	def _pagina(self):
		poze = self._poze()
		parti = [_("Mesajul %(k)d din %(n)d") % {"k": self.index + 1, "n": len(self.mesaje)}]
		if poze:
			parti.append(_("Poza %(k)d din %(n)d") % {"k": self.poza + 1, "n": len(poze)})
		self["pagina"].setText(" · ".join(parti))
		self["stare"].setText(_("OK: mărește poza. Stânga și Dreapta: celelalte poze.") if len(poze) > 1 else
			(_("OK: mărește poza.") if poze else ""))

	def _chenar(self):
		_chenarPe(self["chenar"], self["loc_mic%d" % self.poza])
		self["chenar"].show()

	def _bate(self):
		if self._inchis or not self.descarcari.bate():
			self._ceas.stop()

	def _descarcata(self, cheie, cale):
		if cheie[0] != self._generatie:
			return
		self.cai[cheie[1]] = cale
		self.mici.cere(cheie, cale)
		if cheie[1] == self.poza:
			self.mari.cere((self._generatie, self.poza), cale)

	def _pozaMica(self, cheie, ptr):
		if cheie[0] == self._generatie and not self._inchis:
			_punePixmap(self["mic%d" % cheie[1]], ptr, self["loc_mic%d" % cheie[1]])

	def _pozaMare(self, cheie, ptr):
		if cheie[0] == self._generatie and cheie[1] == self.poza and not self._inchis:
			_punePixmap(self["mare"], ptr)

	def _alegePoza(self, pas):
		poze = self._poze()
		if len(poze) < 2:
			return
		self.poza = (self.poza + pas) % len(poze)
		self["mare"].hide()
		self._chenar()
		self._pagina()
		cale = self.cai.get(self.poza)
		if cale:
			self.mari.cere((self._generatie, self.poza), cale)

	def stanga(self):
		self._alegePoza(-1)

	def dreapta(self):
		self._alegePoza(1)

	def textSus(self):
		self["text"].pageUp()

	def textJos(self):
		self["text"].pageDown()

	def mareste(self):
		cai = [self.cai.get(j) for j in range(len(self._poze()))]
		if not cai or not cai[self.poza]:
			return
		gata = [c for c in cai if c]
		self.session.open(HdsForumPoza, gata, gata.index(cai[self.poza]))

	def anterior(self):
		if self.index > 0:
			self.index -= 1
			self.poza = 0
			self.cai = {}
			self._arata()

	def urmator(self):
		if self.index < len(self.mesaje) - 1:
			self.index += 1
			self.poza = 0
			self.cai = {}
			self._arata()

	def verde(self):
		if self.tester:
			autor = (self.mesaje[self.index].get("autor") or "") if self.mesaje else ""
			self.close({"index": self.index, "fa": "scrie", "text": ("@%s " % autor) if autor else ""})
		else:
			self.close({"index": self.index, "fa": "acord"})

	def inapoi(self):
		self.close({"index": self.index})


# ------------------------------------------------------------------ o poza pe tot ecranul

class HdsForumPoza(Screen):
	skin = """
	<screen name="HdsForumPoza" resolution="1920,1080" position="0,0" size="1920,1080" flags="wfNoBorder" backgroundColor="#000000">
		<widget name="poza" position="0,0" size="1920,1080" zPosition="1" alphatest="off" />
		<widget name="pagina" position="1500,1010" size="380,40" font="Regular;24" foregroundColor="#E8EDF5" backgroundColor="#10162A" halign="center" valign="center" zPosition="2" />
	</screen>"""

	def __init__(self, session, cai, index=0):
		Screen.__init__(self, session)
		self.cai = [c for c in (cai or []) if c]
		self.index = max(0, min(index, len(self.cai) - 1))
		self["poza"] = Pixmap()
		self["pagina"] = Label("")
		self["actiuni"] = ActionMap(["OkCancelActions", "DirectionActions"], _cuDirectii({
			"ok": self.close,
			"cancel": self.close,
			"left": self.stanga,
			"right": self.dreapta,
		}), -1)
		self.mari = _Miniaturi(1920, 1080, self._gata, maxim=2)
		self.onLayoutFinish.append(self._porneste)
		self.onClose.append(self.mari.opreste)

	def _porneste(self):
		self.mari.pregateste(self["poza"])
		self._arata()

	def _arata(self):
		if not self.cai:
			return
		self["pagina"].setText("%d / %d" % (self.index + 1, len(self.cai)))
		if len(self.cai) < 2:
			self["pagina"].hide()
		self.mari.cere(self.index, self.cai[self.index])

	def _gata(self, cheie, ptr):
		if cheie == self.index:
			_punePixmap(self["poza"], ptr)

	def stanga(self):
		if len(self.cai) > 1:
			self.index = (self.index - 1) % len(self.cai)
			self._arata()

	def dreapta(self):
		if len(self.cai) > 1:
			self.index = (self.index + 1) % len(self.cai)
			self._arata()


# ------------------------------------------------------------------ scrie un mesaj

class HdsForumScrie(Screen):
	skin = """
	<screen name="HdsForumScrie" resolution="1920,1080" position="center,center" size="1500,800" title="Scrie un mesaj">
		<widget name="subtitlu" position="30,10" size="1440,36" font="Regular;22" foregroundColor="%(gri)s" noWrap="1" transparent="1" />
		<widget name="linie" position="30,52" size="1440,2" backgroundColor="%(autor)s" />
		<widget name="eticheta_text" position="30,66" size="700,30" font="Regular;20" foregroundColor="%(autor)s" noWrap="1" transparent="1" />
		<widget name="chenar_text" position="27,99" size="1446,206" backgroundColor="%(chenar)s" zPosition="0" />
		<widget name="fundal_text" position="30,102" size="1440,200" backgroundColor="%(card)s" zPosition="1" />
		<widget name="text" position="46,112" size="1408,180" font="Regular;24" foregroundColor="%(text)s" transparent="1" zPosition="2" />
		<widget name="eticheta_poze" position="30,320" size="900,30" font="Regular;20" foregroundColor="%(autor)s" noWrap="1" transparent="1" />
		<widget name="chenar_poza" position="26,354" size="328,188" backgroundColor="%(chenar)s" zPosition="0" />
		%(sloturi)s
		<widget name="info" position="30,556" size="1440,32" font="Regular;21" foregroundColor="%(gri)s" noWrap="1" transparent="1" />
		<widget name="nume" position="30,594" size="1440,32" font="Regular;21" foregroundColor="%(crem)s" noWrap="1" transparent="1" />
		<widget name="stare" position="30,636" size="1440,80" font="Regular;22" foregroundColor="#DCE1FD" transparent="1" />
		%(taste)s
	</screen>
	""" % {"gri": C_GRI, "autor": C_AUTOR, "chenar": C_CHENAR, "card": C_CARD, "text": C_TEXT, "crem": C_CREM,
		"taste": _taste(744, 1440), "sloturi": "\n\t\t".join(
			'<widget name="loc%d" position="%d,358" size="320,180" font="Regular;22" halign="center" valign="center" '
			'foregroundColor="%s" backgroundColor="%s" zPosition="1" />'
			'<widget name="poza%d" position="%d,358" size="320,180" zPosition="2" alphatest="off" />'
			% (j, 30 + j * 340, C_CREM, C_CARD, j, 30 + j * 340) for j in range(F.POZE_MAX))}

	def __init__(self, session, text="", subiect=""):
		Screen.__init__(self, session)
		self.setTitle(_("Scrie un mesaj"))
		self.textul = text or ""
		self.poze = []
		self.zona = "text"
		self.slot = 0
		self._trimitere = None
		self._jeton = None
		self._nume = None
		self._inchis = False
		self._generatie = 0
		for nume in ("linie", "chenar_text", "fundal_text", "chenar_poza", "stare", "nume"):
			self[nume] = Label("")
		self["subtitlu"] = Label((_("în %s") % subiect) if subiect else "")
		self["eticheta_text"] = Label(_("Textul (OK: tastatura de pe ecran)"))
		self["text"] = Label("")
		self["eticheta_poze"] = Label("")
		self["info"] = Label(_("Scrie într-o singură limbă: forumul traduce singur mesajul pentru fiecare cititor."))
		for j in range(F.POZE_MAX):
			self["loc%d" % j] = Label("")
			self["poza%d" % j] = Pixmap()
		self["key_red"] = Button(_("Renunță"))
		self["key_green"] = Button(_("Trimite"))
		self["key_yellow"] = Button(_("Adaugă o captură"))
		self["key_blue"] = Button(_("Scoate poza"))
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions", "MenuActions"], _cuDirectii({
			"ok": self.ok,
			"cancel": self.renunta,
			"red": self.renunta,
			"green": self.trimite,
			"yellow": self.adaugaCaptura,
			"blue": self.scoatePoza,
			"menu": self.schimbaNumele,
			"up": self.sus_,
			"down": self.jos,
			"left": self.stanga,
			"right": self.dreapta,
		}), -1)
		self._ceas = _ceas(self._bate)
		self.miniaturi = _Miniaturi(320, 180, self._pozaMica)
		self.onLayoutFinish.append(self._porneste)
		self.onClose.append(self._laInchidere)
		self._arata()

	def _porneste(self):
		self.miniaturi.pregateste(self["poza0"])
		self._arata()
		if F.poateScrie():
			# jetonul si profilul se pregatesc cat omul scrie (si numele cu care apare)
			self._jeton = F.cereJetonul()
			self._ceas.start(PAS_MS, False)

	def _laInchidere(self):
		self._inchis = True
		self._ceas.stop()
		self.miniaturi.opreste()

	def _arata(self):
		self["text"].setText(self.textul or _("OK: scrie mesajul cu tastatura de pe ecran."))
		self["eticheta_poze"].setText(_("Pozele (%(n)d din %(max)d)") % {"n": len(self.poze), "max": F.POZE_MAX})
		nume = F.numePublic()
		self["nume"].setText((_("Apari ca: %s") % nume if nume else _("Apari cu numele dat de forum.")) + "   " +
			_("MENU: schimbă numele tău de pe forum"))
		self._generatie += 1
		self.miniaturi.goleste()
		for j in range(F.POZE_MAX):
			loc, poza = self["loc%d" % j], self["poza%d" % j]
			poza.hide()
			if j < len(self.poze):
				loc.setText("")
				loc.show()
				self.miniaturi.cere((self._generatie, j), self.poze[j])
			elif j == len(self.poze):
				loc.setText("+ " + _("Adaugă o captură"))
				loc.show()
			else:
				loc.hide()
		self._chenare()

	def _chenare(self):
		if self.zona == "text":
			self["chenar_text"].show()
			self["chenar_poza"].hide()
		else:
			self["chenar_text"].hide()
			self.slot = max(0, min(self.slot, min(len(self.poze), F.POZE_MAX - 1)))
			_chenarPe(self["chenar_poza"], self["loc%d" % self.slot])
			self["chenar_poza"].show()

	def _pozaMica(self, cheie, ptr):
		if cheie[0] == self._generatie and not self._inchis:
			_punePixmap(self["poza%d" % cheie[1]], ptr, self["loc%d" % cheie[1]])

	def _ocupat(self):
		return self._trimitere is not None

	# ------------------------------------------------------------ tastele

	def sus_(self):
		if not self._ocupat():
			self.zona = "text"
			self._chenare()

	def jos(self):
		if not self._ocupat():
			self.zona = "poze"
			self._chenare()

	def stanga(self):
		if not self._ocupat() and self.zona == "poze" and self.slot > 0:
			self.slot -= 1
			self._chenare()

	def dreapta(self):
		if not self._ocupat() and self.zona == "poze" and self.slot < min(len(self.poze), F.POZE_MAX - 1):
			self.slot += 1
			self._chenare()

	def ok(self):
		if self._ocupat():
			return
		if self.zona == "text":
			from Screens.VirtualKeyBoard import VirtualKeyBoard
			self.session.openWithCallback(self._dupaTastatura, VirtualKeyBoard, title=_("Mesajul"), text=self.textul)
		elif self.slot < len(self.poze):
			self.session.open(HdsForumPoza, list(self.poze), self.slot)
		else:
			self.adaugaCaptura()

	def _dupaTastatura(self, text=None):
		if text is not None:
			self.textul = text
			self["stare"].setText("")
			self._arata()

	def adaugaCaptura(self):
		if self._ocupat():
			return
		loc = F.POZE_MAX - len(self.poze)
		if loc <= 0:
			self["stare"].setText(F.textEroare("poze"))
			return
		self.session.openWithCallback(self._dupaGalerie, HdsCapturiGalerie, loc)

	def _dupaGalerie(self, cai=None):
		if not cai:
			return
		for c in cai:
			if c not in self.poze and len(self.poze) < F.POZE_MAX:
				self.poze.append(c)
		self.zona = "poze"
		self.slot = min(len(self.poze), F.POZE_MAX - 1)
		self["stare"].setText("")
		self._arata()

	def scoatePoza(self):
		if self._ocupat() or not self.poze:
			return
		i = self.slot if (self.zona == "poze" and self.slot < len(self.poze)) else len(self.poze) - 1
		self.miniaturi.uita(self.poze[i])
		del self.poze[i]
		self._arata()

	def trimite(self):
		if self._ocupat():
			return
		if len(F.curataText(self.textul)) < F.TEXT_MIN:
			self["stare"].setText(_("Scrie întâi mesajul."))
			self.zona = "text"
			self._chenare()
			return
		self._trimitere = F.trimite(self.textul, list(self.poze))
		self["stare"].setText(_("Se trimite..."))
		self._ceas.start(PAS_MS, False)

	def _bate(self):
		if self._inchis:
			return
		lucreaza = False
		for atribut, dupa in (("_trimitere", self._dupaTrimitere), ("_jeton", self._dupaJeton),
				("_nume", self._dupaNume)):
			l = getattr(self, atribut)
			if l is None:
				continue
			if l.gata:
				setattr(self, atribut, None)
				dupa(l)
			else:
				lucreaza = True
				if atribut == "_trimitere" and l.pas:
					self["stare"].setText(l.pas)
		if not lucreaza:
			self._ceas.stop()

	def _dupaTrimitere(self, l):
		if l.reusit:
			self.close(l.rezultat)
			return
		self["stare"].setText(l.mesaj)

	def _dupaJeton(self, l):
		# fara mesaj pe ecran: la trimitere jetonul se cere din nou
		if l.reusit:
			self._arata()

	def schimbaNumele(self):
		if self._ocupat() or self._nume is not None or not F.poateScrie():
			return
		_tastaturaNume(self, self._numePornit)

	def _numePornit(self, lucrare):
		self._nume = lucrare
		self["stare"].setText(_("Se schimbă numele..."))
		self._ceas.start(PAS_MS, False)

	def _dupaNume(self, n):
		if n.reusit:
			self["stare"].setText(_("Numele tău pe forum e acum „%s”.") % (n.rezultat or {}).get("nume", ""))
			self._arata()
		else:
			self["stare"].setText(n.mesaj)

	def renunta(self):
		if self._ocupat():
			return
		if F.curataText(self.textul) or self.poze:
			self.session.openWithCallback(self._dupaIntrebare, MessageBox, _("Renunți la mesajul scris?"),
				MessageBox.TYPE_YESNO, default=False)
			return
		self.close(None)

	def _dupaIntrebare(self, da):
		if da:
			self.close(None)


# ------------------------------------------------------------------ galeria capturilor

COLOANE = 4
RANDURI = 3
CASUTE = COLOANE * RANDURI
L_CAS, H_CAS = 232, 130
X_CAS, Y_CAS = 30, 72
PAS_X, PAS_Y = L_CAS + 16, H_CAS + 36 + 14


def _skinGalerie(cu_verde):
	r = ['<screen name="HdsCapturiGalerie" resolution="1920,1080" position="center,center" size="1500,730" '
		'title="Capturile tale">']
	r.append('<widget name="subtitlu" position="30,12" size="900,36" font="Regular;22" foregroundColor="%s" noWrap="1" '
		'transparent="1" />' % C_GRI)
	r.append('<widget name="fila_stick" position="1010,10" size="225,40" font="Regular;20" halign="center" '
		'valign="center" foregroundColor="#FFFFFF" backgroundColor="%s" noWrap="1" />' % C_CHENAR)
	r.append('<widget name="fila_memorie" position="1245,10" size="225,40" font="Regular;20" halign="center" '
		'valign="center" foregroundColor="%s" backgroundColor="%s" noWrap="1" />' % (C_GRI, C_CARD))
	r.append('<widget name="linie" position="30,58" size="1440,2" backgroundColor="%s" />' % C_AUTOR)
	r.append('<widget name="chenar" position="%d,%d" size="%d,%d" backgroundColor="%s" zPosition="1" />'
		% (X_CAS - 4, Y_CAS - 4, L_CAS + 8, H_CAS + 8, C_CHENAR))
	for k in range(CASUTE):
		x = X_CAS + (k % COLOANE) * PAS_X
		y = Y_CAS + (k // COLOANE) * PAS_Y
		r.append('<widget name="loc%d" position="%d,%d" size="%d,%d" backgroundColor="%s" zPosition="2" />'
			% (k, x, y, L_CAS, H_CAS, C_CARD))
		r.append('<widget name="poza%d" position="%d,%d" size="%d,%d" zPosition="3" alphatest="off" />'
			% (k, x, y, L_CAS, H_CAS))
		r.append('<widget name="ales%d" position="%d,%d" size="44,32" font="Regular;20" halign="center" valign="center" '
			'foregroundColor="#FFFFFF" backgroundColor="%s" zPosition="4" />' % (k, x + 6, y + 6, C_ALES))
		r.append('<widget name="data%d" position="%d,%d" size="%d,30" font="Regular;19" foregroundColor="%s" noWrap="1" '
			'transparent="1" />' % (k, x, y + H_CAS + 4, L_CAS, C_GRI))
	r.append('<widget name="gol" position="30,72" size="976,512" font="Regular;24" halign="center" valign="center" '
		'foregroundColor="%s" transparent="1" zPosition="5" />' % C_TEXT)
	r.append('<widget name="loc_mare" position="1030,72" size="440,248" backgroundColor="%s" zPosition="1" />' % C_LOC)
	r.append('<widget name="mare" position="1030,72" size="440,248" zPosition="2" alphatest="off" />')
	r.append('<widget name="detalii" position="1030,336" size="440,180" font="Regular;21" foregroundColor="%s" '
		'transparent="1" />' % C_CREM)
	r.append('<widget name="pagina" position="1030,540" size="440,32" font="Regular;20" foregroundColor="%s" '
		'halign="right" noWrap="1" transparent="1" />' % C_GRI)
	r.append('<widget name="stare" position="30,600" size="1440,60" font="Regular;21" foregroundColor="#DCE1FD" '
		'transparent="1" />')
	chei = ("key_red", "key_green", "key_yellow", "key_blue") if cu_verde else ("key_red", "key_yellow", "key_blue")
	r.append(_taste(676, 1440, chei=chei))
	r.append("</screen>")
	return "\n\t".join(r)


class HdsCapturiGalerie(Screen):
	"""alege = cate capturi se pot alege (din scrierea unui mesaj; Verde le da inapoi ca liste de cai); 0 = numai
	privite ('Capturile mele')."""

	skin = _skinGalerie(False)
	skin_alege = _skinGalerie(True)

	def __init__(self, session, alege=0):
		self.alege = max(0, int(alege or 0))
		if self.alege:
			self.skin = HdsCapturiGalerie.skin_alege
		Screen.__init__(self, session)
		self.setTitle(_("Capturile tale"))
		self.alese = []
		self.cursor = 0
		self.sus = 0
		self._inchis = False
		self._generatie = 0
		self.locuri = CAP.locuri()
		toate = CAP.lista()
		self.loc = toate[0]["loc"] if toate else CAP.locImplicit(self.locuri)["cheie"]
		self.capturi = []
		for nume in ("subtitlu", "fila_stick", "fila_memorie", "linie", "chenar", "gol", "loc_mare", "detalii", "pagina",
				"stare"):
			self[nume] = Label("")
		for k in range(CASUTE):
			self["loc%d" % k] = Label("")
			self["poza%d" % k] = Pixmap()
			self["ales%d" % k] = Label("")
			self["data%d" % k] = Label("")
		self["mare"] = Pixmap()
		self["key_red"] = Button(_("Înapoi"))
		if self.alege:
			self["key_green"] = Button("")
		self["key_yellow"] = Button(_("Șterge captura"))
		self["key_blue"] = Button(_("Stick / Memorie"))
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], _cuDirectii({
			"ok": self.ok,
			"cancel": self.inapoi,
			"red": self.inapoi,
			"green": self.gata,
			"yellow": self.sterge,
			"blue": self.schimbaLocul,
			"up": lambda: self._muta(-COLOANE),
			"down": lambda: self._muta(COLOANE),
			"left": lambda: self._muta(-1),
			"right": lambda: self._muta(1),
			"upRepeated": lambda: self._muta(-COLOANE),
			"downRepeated": lambda: self._muta(COLOANE),
		}), -1)
		self.mici = _Miniaturi(L_CAS, H_CAS, self._pozaMica, maxim=48)
		self.mari = _Miniaturi(440, 248, self._pozaMare, maxim=4)
		self.onLayoutFinish.append(self._porneste)
		self.onClose.append(self._laInchidere)
		CAP.asculta(self._capturaNoua)
		self._citeste()

	def _porneste(self):
		self.mici.pregateste(self["poza0"])
		self.mari.pregateste(self["mare"])
		self._deseneaza()

	def _laInchidere(self):
		self._inchis = True
		CAP.nuMaiAsculta(self._capturaNoua)
		self.mici.opreste()
		self.mari.opreste()

	def _capturaNoua(self, _cale=None):
		"""O captura facuta cat galeria e deschisa apare pe loc in grila."""
		if self._inchis:
			return
		self.locuri = CAP.locuri()
		toate = CAP.lista()
		if toate:
			self.loc = toate[0]["loc"]
		self._citeste()
		self.cursor = 0
		self.sus = 0
		self._deseneaza()

	def _locul(self, cheie):
		for l in self.locuri:
			if l["cheie"] == cheie:
				return l
		return None

	def _citeste(self):
		self.capturi = CAP.lista(self.loc)
		self.cursor = max(0, min(self.cursor, len(self.capturi) - 1))
		vechi = list(self.alese)
		cai = set(c["cale"] for c in CAP.lista())
		self.alese = [c for c in vechi if c in cai]

	def _deseneaza(self):
		if self._inchis:
			return
		self._generatie += 1
		self.mici.goleste()
		l = self._locul(self.loc) or {"nume": "", "dosar": ""}
		self["subtitlu"].setText("%s · %s" % (l["nume"], _("Capturi: %d") % len(self.capturi)))
		stick = self._locul(CAP.STICK)
		self["fila_stick"].setText((stick or {}).get("nume") or _("Stick USB"))
		self["fila_memorie"].setText(_("Memoria receptorului"))
		activ, inactiv = (("fila_stick", "fila_memorie") if self.loc == CAP.STICK else ("fila_memorie", "fila_stick"))
		_fundal(self[activ], "fila_aleasa")
		_fundal(self[inactiv], "fila")
		if not (stick and stick["disponibil"]):
			self["fila_stick"].hide()
		else:
			self["fila_stick"].show()
		for k in range(CASUTE):
			i = self.sus * COLOANE + k
			loc, poza, ales, data = self["loc%d" % k], self["poza%d" % k], self["ales%d" % k], self["data%d" % k]
			poza.hide()
			if i >= len(self.capturi):
				for w in (loc, ales, data):
					w.hide()
				continue
			c = self.capturi[i]
			loc.show()
			data.setText("%s   %s" % (oraCaptura(c["cand"]), marime(c["marime"])))
			data.show()
			if c["cale"] in self.alese:
				ales.setText("%d" % (self.alese.index(c["cale"]) + 1))
				ales.show()
			else:
				ales.hide()
			self.mici.cere((self._generatie, k), c["cale"])
		if self.capturi:
			self["gol"].setText("")
			_chenarPe(self["chenar"], self["loc%d" % (self.cursor - self.sus * COLOANE)])
			self["chenar"].show()
		else:
			self["gol"].setText(_("Nicio captură aici: apasă tasta de captură de pe telecomandă (a treia tastă cu desen "
				"de ecran) pe orice ecran."))
			self["chenar"].hide()
		if len(self.capturi) > CASUTE:
			self["pagina"].setText(_("%(de)d-%(pana)d din %(tot)d") % {"de": self.sus * COLOANE + 1,
				"pana": min(len(self.capturi), (self.sus + RANDURI) * COLOANE), "tot": len(self.capturi)})
		else:
			self["pagina"].setText("")
		if self.alege:
			self["key_green"].setText(_("Adaugă la mesaj (%d)") % len(self.alese) if self.alese else
				_("Adaugă la mesaj"))
		self._detalii()

	def _detalii(self):
		self.mari.goleste()
		self["mare"].hide()
		if not self.capturi:
			self["detalii"].setText("")
			self["loc_mare"].hide()
			return
		c = self.capturi[self.cursor]
		l = self._locul(c["loc"]) or {"nume": ""}
		self["detalii"].setText("%s\n%s\n%s" % (time.strftime("%d.%m.%Y, %H:%M", time.localtime(c["cand"])),
			marime(c["marime"]), l["nume"]))
		self["loc_mare"].show()
		self.mari.cere((self._generatie, self.cursor), c["cale"])
		if self.alege:
			self["stare"].setText(_("OK alege capturile, Verde le pune în mesaj."))

	def _pozaMica(self, cheie, ptr):
		if cheie[0] == self._generatie and not self._inchis:
			_punePixmap(self["poza%d" % cheie[1]], ptr, self["loc%d" % cheie[1]])

	def _pozaMare(self, cheie, ptr):
		if cheie[1] == self.cursor and not self._inchis:
			_punePixmap(self["mare"], ptr)

	def _muta(self, pas):
		if not self.capturi:
			return
		nou = self.cursor + pas
		if not 0 <= nou < len(self.capturi):
			return
		self.cursor = nou
		rand = self.cursor // COLOANE
		sus = self.sus
		if rand < self.sus:
			self.sus = rand
		elif rand >= self.sus + RANDURI:
			self.sus = rand - RANDURI + 1
		if sus != self.sus:
			self._deseneaza()
			return
		_chenarPe(self["chenar"], self["loc%d" % (self.cursor - self.sus * COLOANE)])
		self._detalii()

	def ok(self):
		if not self.capturi:
			return
		c = self.capturi[self.cursor]
		if not self.alege:
			self.session.open(HdsForumPoza, [x["cale"] for x in self.capturi], self.cursor)
			return
		if c["cale"] in self.alese:
			self.alese.remove(c["cale"])
		elif len(self.alese) >= self.alege:
			self["stare"].setText(_("Poți alege o singură captură.") if self.alege == 1 else
				_("Poți alege cel mult %d capturi.") % self.alege)
			return
		else:
			self.alese.append(c["cale"])
		self._deseneaza()

	def gata(self):
		if not self.alege:
			return
		if self.alese:
			self.close(list(self.alese))
		elif self.capturi:
			# Verde pe o captura nealeasa: chiar aceea (fara pasul OK)
			self.close([self.capturi[self.cursor]["cale"]])

	def sterge(self):
		if not self.capturi:
			return
		self.session.openWithCallback(self._dupaStergere, MessageBox, _("Ștergi captura?"), MessageBox.TYPE_YESNO,
			default=False)

	def _dupaStergere(self, da):
		if not da or not self.capturi:
			return
		c = self.capturi[self.cursor]
		ok, mesaj = CAP.sterge(c["nume"], c["loc"])
		if not ok:
			self["stare"].setText(mesaj)
		self.mici.uita(c["cale"])
		self.mari.uita(c["cale"])
		self._citeste()
		self.sus = min(self.sus, max(0, (len(self.capturi) - 1) // COLOANE - RANDURI + 1))
		self._deseneaza()

	def schimbaLocul(self):
		self.locuri = CAP.locuri()
		alt = CAP.MEMORIE if self.loc == CAP.STICK else CAP.STICK
		l = self._locul(alt)
		if not (l and l["disponibil"]):
			self["stare"].setText(_("Nu e niciun stick USB conectat."))
			return
		self.loc = alt
		self.cursor = 0
		self.sus = 0
		self._citeste()
		self["stare"].setText("")
		self._deseneaza()

	def inapoi(self):
		self.close(None)


# ------------------------------------------------------------------ mesajul de dupa captura

class HdsCapturaSalvata(Screen):
	"""Sus in dreapta, 3 secunde (Components/HdsCapturi.py il arata si il ascunde); fara harta de taste."""

	skin = """
	<screen name="HdsCapturaSalvata" resolution="1920,1080" position="984,54" size="880,112" flags="wfNoBorder" backgroundColor="#10162A" zPosition="99">
		<widget name="bara" position="0,0" size="6,112" backgroundColor="#374EA1" />
		<widget name="titlu" position="26,14" size="840,44" font="Regular;28" foregroundColor="#FFFFFF" noWrap="1" transparent="1" />
		<widget name="detaliu" position="26,62" size="840,34" font="Regular;20" foregroundColor="#8B96A8" noWrap="1" transparent="1" />
	</screen>"""

	def __init__(self, session):
		Screen.__init__(self, session)
		self["bara"] = Label("")
		self["titlu"] = Label("")
		self["detaliu"] = Label("")

	def arata(self, titlu, detaliu=""):
		self["titlu"].setText(titlu or "")
		self["detaliu"].setText(detaliu or "")
