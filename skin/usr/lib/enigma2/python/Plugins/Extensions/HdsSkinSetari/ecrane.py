# -*- coding: utf-8 -*-
# Copyright (C) 2026 Monea Software pentru HD Satelit (https://hdsatelit.com, contact@moneasoftware.com)
# Licenta: GNU GPL versiunea 2. HDS-MARCA: skin HDSatelit, Monea Software pentru HD Satelit, 2026
#
# Ecranele panoului de setari: panoul principal, alegerea paletei, lista rolurilor, editorul unei culori.
# Fiecare ecran are in dreapta aceeasi previzualizare: un panou peste imagine alba si unul peste imagine
# neagra, colorate din Python (setBackgroundColor / setForegroundColor), deci fara repornire.
# Culorile ecranelor insesi sunt scrise direct (nu hds*) si fonturile sunt Regular/Bold, ca panoul sa se
# deschida si cand skinul activ nu e HDSatelit. Merge pe Python 2.7 si 3.x.
import os
import re

from enigma import eListboxPythonMultiContent, gFont, gRGB, getDesktop, RT_HALIGN_LEFT, RT_HALIGN_RIGHT, RT_VALIGN_CENTER
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.MenuList import MenuList
from Components.MultiContent import MultiContentEntryText
from Screens.Screen import Screen

from . import paleta as P
from .texte import tr_str as _
from .texte import tr as _tr

C_FUND = 0x000C1220
C_TEXT = 0x00F2F4F8
C_TEXT2 = 0x00AEB9CC
C_SEL = 0x00374EA1
C_ALB = 0x00FFFFFF


def _scara():
	try:
		w = getDesktop(0).size().width()
		if w and w != 1920:
			return w / 1920.0
	except Exception:
		pass
	return 1.0


def _scaleaza(skin):
	"""Skinul e scris pentru 1920x1080; pe alt ecran (1280x720) numerele din pos/size/font/itemHeight se inmultesc."""
	f = _scara()
	if f == 1.0:
		return skin

	def n(x):
		return str(int(int(x) * f + 0.5))

	skin = re.sub(r'(position|size)="(\d+),(\d+)"', lambda m: '%s="%s,%s"' % (m.group(1), n(m.group(2)), n(m.group(3))), skin)
	skin = re.sub(r'font="(\w+);(\d+)"', lambda m: 'font="%s;%s"' % (m.group(1), n(m.group(2))), skin)
	skin = re.sub(r'itemHeight="(\d+)"', lambda m: 'itemHeight="%s"' % n(m.group(1)), skin)
	return skin


def _px(x):
	return int(x * _scara() + 0.5)


def _u(x):
	"""Orice (exceptie, bytes, text) ca text unicode, fara sa cada."""
	try:
		if isinstance(x, bytes):
			return x.decode("utf-8", "replace")
		if isinstance(x, type(u"")):
			return x
		s = str(x)
		return s.decode("utf-8", "replace") if isinstance(s, bytes) else s
	except Exception:
		return u"?"


def _hex6(v):
	return "#00%06X" % (v & 0xFFFFFF)


# ---------------------------------------------------------------- previzualizarea
X0 = 1110
Y0 = 120
# (nume, x, y, w, h, font sau None, text (cheie sau text fix), aliniere)
_PV = (
	("fundal", 0, 0, 700, 340, None, "", ""),
	("linie", 0, 0, 700, 3, None, "", ""),
	# numarul: 96 px (cu textul marit la 130 %, "101" in Bold 52 are ~93 px; in 90 px se rupea si disparea)
	("nr", 24, 20, 96, 56, "Bold;40", "101", "left"),
	("canal", 120, 20, 380, 56, "Bold;40", "pv_channel", "left"),
	("ora", 500, 20, 176, 56, "Bold;36", "20:15", "right"),
	("acum", 24, 80, 652, 40, "Regular;30", "pv_now", "left"),
	# eticheta barei de semnal: acelasi cuvant ca in bara de jos (CALITATE, tradus), nu „SNR”; 155 px (vi: 153 px)
	("eticheta", 24, 128, 155, 32, "Regular;24", "quality", "left"),
	("sina", 180, 138, 300, 14, None, "", ""),
	("bun", 180, 138, 160, 14, None, "", ""),
	("slab", 340, 138, 60, 14, None, "", ""),
	("rau", 400, 138, 30, 14, None, "", ""),
	("dezact", 490, 128, 186, 32, "Regular;24", "pv_disabled", "right"),
	("sel", 0, 176, 700, 52, "Regular;30", "pv_selected", "left"),
	("selbara", 0, 176, 6, 52, None, "", ""),
	("celula", 24, 240, 318, 44, "Regular;28", "pv_next", "left"),
	("celacum", 358, 240, 318, 44, "Regular;28", "pv_now", "left"),
	("k0", 24, 298, 10, 30, None, "", ""),
	("k1", 194, 298, 10, 30, None, "", ""),
	("k2", 364, 298, 10, 30, None, "", ""),
	("k3", 534, 298, 10, 30, None, "", ""),
	("kt0", 40, 298, 140, 30, "Regular;22", "OK", "left"),
	("kt1", 210, 298, 140, 30, "Regular;22", "OK", "left"),
	("kt2", 380, 298, 140, 30, "Regular;22", "OK", "left"),
	("kt3", 550, 298, 140, 30, "Regular;22", "OK", "left"),
)


def _majuscule(s):
	"""Textul cu majuscule (ca eticheta din bara de jos), str pe ambele Python-uri."""
	try:
		from Components.Converter import HdsCommon as C
		s = C.upper(s)
	except Exception:
		s = s.upper()
	if str is bytes and not isinstance(s, bytes):
		s = s.encode("utf-8")
	return s


def skin_previzualizare():
	r = []
	for k, video in ((0, "#00FFFFFF"), (1, "#00000000")):
		oy = Y0 + k * 370
		r.append('<widget name="pv%d_video" position="%d,%d" size="720,360" backgroundColor="%s" transparent="0" zPosition="1" />' % (k, X0 - 10, oy - 10, video))
		for nume, x, y, w, h, font, _t, al in _PV:
			atr = 'name="pv%d_%s" position="%d,%d" size="%d,%d" transparent="0" zPosition="2" backgroundColor="#0010162A"' % (k, nume, X0 + x, oy + y, w, h)
			if font:
				atr += ' font="%s" foregroundColor="#00F2F4F8" valign="center" halign="%s"' % (font, al)
				# toate pe un rand (noWrap): cu textul marit, un cuvant mai lat decat caseta trecea pe randul al doilea, in
				# afara casetei, si disparea; la 100 % incap toate, deci nu se schimba nimic
				atr += ' noWrap="1"'
			r.append("<widget %s />" % atr)
	r.append('<widget name="pv_contrast" position="%d,%d" size="700,110" font="Regular;26" foregroundColor="#00F2F4F8" backgroundColor="#000C1220" transparent="0" valign="top" halign="left" zPosition="2" />' % (X0, Y0 + 740))
	return "\n".join(r)


class Previzualizare(object):
	"""Amestec pentru ecrane: pune widget-urile previzualizarii si le coloreaza."""

	def pune_previzualizare(self):
		for k in (0, 1):
			self["pv%d_video" % k] = Label("")
			for nume, x, y, w, h, font, t, al in _PV:
				txt = ""
				if font:
					if t.startswith("pv_"):
						txt = _(t)
					elif t == "quality":
						txt = _majuscule(_tr(t))
					else:
						txt = t
					if nume == "sel":
						txt = "  " + txt
				self["pv%d_%s" % (k, nume)] = Label(txt)
		self["pv_contrast"] = Label("")

	def _culori(self, nume, fund=None, text=None):
		try:
			inst = self[nume].instance
			if inst is None:
				return
			if fund is not None:
				inst.setBackgroundColor(gRGB(fund & 0xFFFFFF))
			if text is not None:
				inst.setForegroundColor(gRGB(text & 0xFFFFFF))
			inst.invalidate()
		except Exception:
			pass

	def coloreaza(self, pal):
		for k, video in ((0, 0x00FFFFFF), (1, 0x00000000)):
			pan = P.peste(pal["hdsPanel"], video)
			c = lambda n, f=None, t=None, k=k: self._culori("pv%d_%s" % (k, n), f, t)
			c("fundal", pan)
			c("linie", P.peste(pal["hdsLine"], pan))
			c("nr", pan, pal["hdsBrandLight"])
			c("canal", pan, pal["hdsText"])
			c("ora", pan, pal["hdsAmber"])
			c("acum", pan, pal["hdsText2"])
			c("eticheta", pan, pal["hdsLabel"])
			c("sina", pal["hdsTrack"])
			c("bun", pal["hdsGood"])
			c("slab", pal["hdsWarn"])
			c("rau", pal["hdsBad"])
			c("dezact", pan, pal["hdsDisabled"])
			c("sel", pal["hdsBrand"], pal["hdsSelText"])
			c("selbara", pal["hdsBrandLight"])
			c("celula", pal["hdsCell"], pal["hdsText2"])
			c("celacum", pal["hdsCellNow"], pal["hdsText"])
			for i, rol in enumerate(("key_red", "key_green", "key_yellow", "key_blue")):
				c("k%d" % i, pal[rol])
				c("kt%d" % i, pal["key_back"], pal["key_text"])
		cad = P.cade(pal)
		try:
			if not cad:
				self["pv_contrast"].setText(_("set_contrast_ok"))
				self._culori("pv_contrast", None, pal["hdsGood"] if P.raport(pal["hdsGood"], C_FUND) >= 4.5 else C_TEXT)
			else:
				nume = []
				for text, _f, r, prag in cad:
					n = _("role_" + ("hdsSelText" if text == "white" else text))
					if n not in nume:
						nume.append(n)
				sep = ", " if str is not bytes else b", "
				self["pv_contrast"].setText(_("set_contrast_low", sep.join(nume) if str is not bytes else sep.join(nume).decode("utf-8")))
				self._culori("pv_contrast", None, 0x00FF8A7A)
		except Exception:
			pass


def skin_taste():
	r = []
	for i, (culoare, nume) in enumerate(((0x00E5484D, "rosu"), (0x0046B06A, "verde"), (0x00E8B93A, "galben"), (0x003D7BE0, "albastru"))):
		x = 96 + i * 340
		r.append('<widget name="bara_%s" position="%d,990" size="8,40" backgroundColor="%s" transparent="0" zPosition="1" />' % (nume, x, _hex6(culoare)))
		r.append('<widget name="tasta_%s" position="%d,990" size="310,40" font="Regular;26" foregroundColor="#00F2F4F8" backgroundColor="#000C1220" transparent="1" valign="center" halign="left" noWrap="1" zPosition="1" />' % (nume, x + 18))
	return "\n".join(r)


def _cap(titlu_lat=900):
	return ('<widget name="titlu" position="96,36" size="%d,64" font="Bold;44" foregroundColor="#00F2F4F8" backgroundColor="#000C1220" transparent="1" valign="center" />' % titlu_lat
		+ '<widget name="ajutor" position="96,930" size="980,44" font="Regular;26" foregroundColor="#00AEB9CC" backgroundColor="#000C1220" transparent="1" valign="center" />'
		+ '<widget name="lista" position="96,120" size="980,790" itemHeight="64" scrollbarMode="showOnDemand" backgroundColor="#000C1220" backgroundColorSelected="#00374EA1" foregroundColor="#00F2F4F8" foregroundColorSelected="#00FFFFFF" transparent="0" />')


def _skin_ecran(nume):
	return _scaleaza('<screen name="%s" position="0,0" size="1920,1080" flags="wfNoBorder" backgroundColor="#000C1220">%s%s%s</screen>' % (
		nume, _cap(), skin_taste(), skin_previzualizare()))


# MenuList difera intre imagini: unele au up/goLineUp si setCurrentIndex, altele doar moveUp/moveDown sau
# up/down; toate au moveToIndex si l.getCurrentSelectionIndex(). Se cheama metoda Python a imaginii,
# fara try: o metoda lipsa trebuie sa se vada in proba, nu sa fie inghitita.
_MUTARI = {"up": ("up", "moveUp", "goLineUp"), "down": ("down", "moveDown", "goLineDown"),
	"pageUp": ("goPageUp", "pageUp"), "pageDown": ("goPageDown", "pageDown")}



def _nimic():
	pass


def cu_ridicari(actiuni):
	"""Sagetile tinute apasat fac ce face apasarea; ridicarea tastei (upUp...) e legata la nimic, ca jurnalul sa nu
	scrie "unknown action" la fiecare sageata."""
	for s in ("up", "down", "left", "right"):
		if s in actiuni:
			actiuni.setdefault(s + "Repeated", actiuni[s])
		actiuni.setdefault(s + "Up", _nimic)
	return actiuni

def lista_muta(lista, cum):
	for nume in _MUTARI[cum]:
		f = getattr(lista, nume, None)
		if callable(f):
			f()
			return
	raise AttributeError("MenuList fara %s" % "/".join(_MUTARI[cum]))


def lista_la(lista, i):
	if lista.instance is not None:
		lista.moveToIndex(i)


class Lista(MenuList):
	def __init__(self):
		MenuList.__init__(self, [], True, eListboxPythonMultiContent)
		self.l.setFont(0, gFont("Regular", _px(32)))
		self.l.setFont(1, gFont("Regular", _px(26)))
		self.l.setItemHeight(_px(64))


def rand(stanga, dreapta="", culoare=None, sub=None, lung=False):
	"""Un rand de lista: text in stanga, valoare in dreapta, optional un patrat de culoare inainte de valoare.
	lung: valoare lunga (de ex. "Manual (doar cu stanga / dreapta)"), cu fontul mic, pe toata latimea randului,
	aliniata la dreapta dupa eticheta (eticheta 32 px + valoarea 26 px incap in 932 px; verifica_limbi.py le masoara).
	Primul element nu poate fi None: eListboxPythonMultiContent socoteste randul cu None separator si nu il poate selecta."""
	r = [True, MultiContentEntryText(pos=(_px(24), 0), size=(_px(600), _px(64)), font=0, flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER,
		text=stanga, color=C_TEXT, color_sel=C_ALB)]
	if dreapta and lung:
		r.append(MultiContentEntryText(pos=(_px(24), 0), size=(_px(932), _px(64)), font=1,
			flags=RT_HALIGN_RIGHT | RT_VALIGN_CENTER, text=dreapta, color=C_TEXT2, color_sel=C_ALB))
	elif dreapta:
		r.append(MultiContentEntryText(pos=(_px(600), 0), size=(_px(356), _px(64)), font=1 if sub else 0,
			flags=RT_HALIGN_RIGHT | RT_VALIGN_CENTER, text=dreapta, color=C_TEXT2, color_sel=C_ALB))
	if culoare is not None:
		r.append(MultiContentEntryText(pos=(_px(24), _px(14)), size=(_px(8), _px(36)), font=0, flags=RT_HALIGN_LEFT,
			text="", backcolor=culoare & 0xFFFFFF, backcolor_sel=culoare & 0xFFFFFF))
		r[1] = MultiContentEntryText(pos=(_px(48), 0), size=(_px(560), _px(64)), font=0, flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER,
			text=stanga, color=C_TEXT, color_sel=C_ALB)
	return r


def text_pagina(n):
	"""Valoarea randului cu timpul pe pagina tehnica: manual (0, doar cu stanga / dreapta) sau secundele de rotire."""
	return _("set_page_manual") if not n else _("set_seconds", "%d" % n)


def text_afisaj(v):
	"""Valoarea randului „Pagina tehnica”: pe tot ecranul (implicit) sau fereastra sus."""
	return _("set_infobar2_window") if v == "fereastra" else _("set_infobar2_full")


def _bara_timp():
	"""Setarea imaginii pentru cat sta bara de informatii pe ecran (config.usage.infobar_timeout), sau None."""
	try:
		from Components.config import config
		return getattr(config.usage, "infobar_timeout", None)
	except Exception:
		return None


def valori_bara(el):
	"""Valorile setarii, cum le are imaginea care ruleaza (fiecare imagine are alta lista)."""
	try:
		return [str(el.choices[i]) for i in range(len(el.choices))]
	except Exception:
		return []


def text_bara(v):
	"""„nu se închide” (0) sau secundele."""
	try:
		n = int(v)
	except (TypeError, ValueError):
		return str(v)
	return _("set_infobar_never") if n <= 0 else _("set_seconds", "%d" % n)


def rand_paleta(nume, pal):
	r = [True, MultiContentEntryText(pos=(_px(24), 0), size=(_px(520), _px(64)), font=0, flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER,
		text=nume, color=C_TEXT, color_sel=C_ALB)]
	x = 560
	for rol in ("hdsPanelSolid", "hdsText", "hdsBrand", "hdsBrandLight", "hdsAmber", "hdsGood", "hdsBad"):
		r.append(MultiContentEntryText(pos=(_px(x), _px(12)), size=(_px(50), _px(40)), font=0, flags=RT_HALIGN_LEFT,
			text="", backcolor=pal[rol] & 0xFFFFFF, backcolor_sel=pal[rol] & 0xFFFFFF))
		x += 56
	return r


class Baza(Screen, Previzualizare):
	def __init__(self, session, stare):
		Screen.__init__(self, session)
		self.stare = stare
		self["titlu"] = Label("")
		self["ajutor"] = Label("")
		self["lista"] = Lista()
		for n in ("rosu", "verde", "galben", "albastru"):
			self["tasta_" + n] = Label("")
			self["bara_" + n] = Label("")
		self.pune_previzualizare()
		self.onLayoutFinish.append(self._gata)

	def _gata(self):
		try:
			self.setTitle(_("set_title"))
		except Exception:
			pass
		self.reface()
		self.taste()

	def taste(self):
		"""Bara colorata a unei taste se vede doar cand tasta are text."""
		for n in ("rosu", "verde", "galben", "albastru"):
			try:
				if self["tasta_" + n].getText():
					self["bara_" + n].show()
				else:
					self["bara_" + n].hide()
			except Exception:
				pass

	def index(self):
		i = self["lista"].l.getCurrentSelectionIndex()
		return i if isinstance(i, int) else 0

	def muta(self, sus):
		lista_muta(self["lista"], "up" if sus else "down")
		self.selectie()

	def selectie(self):
		pass

	def reface(self):
		pass


def _nume_paleta(pid):
	if pid == P.ID_IMPLICIT:
		return "HD Satelit"
	try:
		fam, nr = pid.rsplit("-", 1)
		return "%s %s" % (_("fam_" + fam), nr)
	except Exception:
		return pid


class Stare(object):
	"""Alegerea in lucru: pleaca din .conf, se schimba in ecrane, se scrie doar la Salveaza."""

	def __init__(self):
		self.conf = P.citeste_conf()
		self._palete = None

	def palete(self):
		if self._palete is None:
			self._palete = P.citeste_palete()
		return self._palete

	def familii(self):
		f = []
		for pid, fam, _b in self.palete():
			if fam not in f:
				f.append(fam)
		return f

	def paleta_baza(self, pid=None):
		p = P.paleta_dupa_id(pid or self.conf["paleta"], self.palete(), self.conf["alfa"])
		return p if p is not None else P.implicita(self.conf["alfa"])

	def paleta(self):
		return P.paleta_din_conf(self.conf, self.palete())

	def nume(self):
		n = _nume_paleta(self.conf["paleta"])
		if self.conf["roluri"]:
			n = _("set_custom", n.decode("utf-8") if isinstance(n, bytes) else n)
		return n


# ---------------------------------------------------------------- panoul principal
class HdsSkinSetari(Baza):
	skin = _skin_ecran("HdsSkinSetari")

	def __init__(self, session):
		Baza.__init__(self, session, Stare())
		self.skinName = "HdsSkinSetari"
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], cu_ridicari({
			"ok": self.ok, "cancel": self.close, "red": self.close, "green": self.salveaza,
			"up": lambda: self.muta(True), "down": lambda: self.muta(False),
			"left": lambda: self.lateral(-1), "right": lambda: self.lateral(1),
		}), -1)

	def reface(self):
		c = self.stare.conf
		pct = dict(P.ALFA_PANOU).get(c["alfa"], 85)
		idx = self.index()
		el = _bara_timp()
		if "bara" not in c and el is not None:
			c["bara"] = str(el.value)
		# randul „Cât stă bara de informații pe ecran”: setarea imaginii, cu alegerile ei; fara ea randul arata „-”
		bara = "< %s >" % text_bara(c["bara"]) if el is not None and c.get("bara") is not None else "-"
		self["lista"].setList([
			rand(_("set_palette"), self.stare.nume()),
			rand(_("set_colors"), "%d" % len(c["roluri"]) if c["roluri"] else ""),
			rand(_("set_transparency"), "< %s >" % _("set_percent", "%d" % pct)),
			rand(_("set_page_time"), "< %s >" % text_pagina(c["pagina"]), lung=not c["pagina"]),
			rand(_("set_infobar2"), "< %s >" % text_afisaj(c.get("afisaj", P.AFISAJ_IMPLICIT))),
			rand(_("set_infobar_time"), bara, lung=True),
			rand(_("set_reset")),
			rand(_("set_apply")),
		])
		lista_la(self["lista"], idx)
		self["titlu"].setText(_("set_title"))
		self["tasta_rosu"].setText(_("set_exit"))
		self["tasta_verde"].setText(_("set_save"))
		self.coloreaza(self.stare.paleta())

	def lateral(self, d):
		i = self.index()
		c = self.stare.conf
		if i == 2:
			valori = [a for a, _p in P.ALFA_PANOU]
			j = valori.index(c["alfa"]) if c["alfa"] in valori else 1
			c["alfa"] = valori[max(0, min(len(valori) - 1, j + d))]
		elif i == 3:
			valori = list(P.PAGINA_SECUNDE)
			j = valori.index(c["pagina"]) if c["pagina"] in valori else 0
			c["pagina"] = valori[max(0, min(len(valori) - 1, j + d))]
		elif i == 4:
			# doua valori: stanga si dreapta trec de la una la cealalta
			c["afisaj"] = "fereastra" if c.get("afisaj", P.AFISAJ_IMPLICIT) == "tot" else "tot"
		elif i == 5:
			valori = valori_bara(_bara_timp())
			if not valori:
				return
			j = valori.index(c.get("bara")) if c.get("bara") in valori else 0
			c["bara"] = valori[max(0, min(len(valori) - 1, j + d))]
		else:
			return
		self.reface()

	def ok(self):
		i = self.index()
		if i == 0:
			self.session.openWithCallback(self.inapoi, HdsAlegePaleta, self.stare)
		elif i == 1:
			self.session.openWithCallback(self.inapoi, HdsRoluri, self.stare)
		elif i in (2, 3, 4, 5):
			self.lateral(1)
		elif i == 6:
			self.stare.conf["paleta"] = P.ID_IMPLICIT
			self.stare.conf["alfa"] = P.ALFA_IMPLICIT
			self.stare.conf["roluri"] = {}
			self.reface()
		elif i == 7:
			self.salveaza()

	def inapoi(self, *args):
		self.reface()

	def salveaza(self):
		from Screens.MessageBox import MessageBox
		c = self.stare.conf
		try:
			from Components.config import config
			config.plugins.HdsSkin.pagina.value = str(c["pagina"])
			config.plugins.HdsSkin.pagina.save()
		except Exception:
			pass
		# cat sta bara de informatii: setarea imaginii (aceeasi ca in Preferinte OSD), salvata pe loc
		el = _bara_timp()
		if el is not None and c.get("bara") is not None and str(el.value) != c["bara"]:
			try:
				from Components.config import configfile
				el.value = c["bara"]
				el.save()
				configfile.save()
			except Exception as e:
				print("[HdsSkinSetari] bara de informatii: %s" % e)
		schimbat = False
		try:
			P.scrie_conf(c)
			if os.path.isfile(P.SKIN_XML):
				schimbat = P.scrie_skin(self.stare.paleta(), c["paleta"])
				# pagina tehnica pe tot ecranul sau in fereastra: numele ecranelor din skin.xml (paleta.scrie_afisaj)
				schimbat = P.scrie_afisaj(c.get("afisaj", P.AFISAJ_IMPLICIT)) or schimbat
		except P.EroareScriere as e:
			self.session.open(MessageBox, _("set_err_write", _u(e)), MessageBox.TYPE_ERROR)
			return
		except Exception as e:
			self.session.open(MessageBox, _("set_err_write", _u(e)), MessageBox.TYPE_ERROR)
			return
		if not skin_activ():
			self.session.open(MessageBox, _("set_not_active"), MessageBox.TYPE_INFO)
			return
		if schimbat:
			self.session.openWithCallback(self.reporneste, MessageBox, _("set_restart_q"), MessageBox.TYPE_YESNO)
		else:
			self.close()

	def reporneste(self, da=False):
		if da:
			from Screens.Standby import TryQuitMainloop
			self.session.open(TryQuitMainloop, 3)
		else:
			from Screens.MessageBox import MessageBox
			self.session.openWithCallback(lambda *a: self.close(), MessageBox, _("set_saved_later"), MessageBox.TYPE_INFO, timeout=6)


def skin_activ():
	try:
		from Components.config import config
		return config.skin.primary_skin.value.startswith("HDSatelit/")
	except Exception:
		return False


# ---------------------------------------------------------------- alegerea paletei
class HdsAlegePaleta(Baza):
	skin = _skin_ecran("HdsAlegePaleta")

	def __init__(self, session, stare):
		Baza.__init__(self, session, stare)
		self.skinName = "HdsAlegePaleta"
		self.familii = stare.familii()
		pid = stare.conf["paleta"]
		self.fam = 0
		for pid2, fam, _b in stare.palete():
			if pid2 == pid and fam in self.familii:
				self.fam = self.familii.index(fam)
		self.randuri = []
		self.pozitie = pid
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], cu_ridicari({
			"ok": self.alege, "cancel": self.close, "red": self.close, "green": self.alege,
			"up": lambda: self.muta(True), "down": lambda: self.muta(False),
			"left": lambda: self.familie(-1), "right": lambda: self.familie(1),
		}), -1)

	def reface(self):
		fam = self.familii[self.fam]
		self.randuri = [(pid, b) for pid, f, b in self.stare.palete() if f == fam]
		lista = []
		sel = 0
		for i, (pid, b) in enumerate(self.randuri):
			pal = P.implicita(self.stare.conf["alfa"]) if b is None else P.deriva(b, self.stare.conf["alfa"])
			lista.append(rand_paleta(_nume_paleta(pid), pal))
			if pid == self.pozitie:
				sel = i
		self["lista"].setList(lista)
		lista_la(self["lista"], sel)
		self["titlu"].setText("<  %s  (%d/%d)  >" % (_("fam_" + fam), self.fam + 1, len(self.familii)))
		self["ajutor"].setText(_("set_help_list"))
		self["tasta_rosu"].setText(_("set_exit"))
		self["tasta_verde"].setText(_("set_choose"))
		self.selectie()

	def familie(self, d):
		self.fam = (self.fam + d) % len(self.familii)
		self.pozitie = None
		self.reface()

	def selectie(self):
		i = self.index()
		if 0 <= i < len(self.randuri):
			pid = self.randuri[i][0]
			c = dict(self.stare.conf)
			c["paleta"] = pid
			self.coloreaza(P.paleta_din_conf(c, self.stare.palete()))

	def alege(self):
		i = self.index()
		if 0 <= i < len(self.randuri):
			self.stare.conf["paleta"] = self.randuri[i][0]
		self.close()


# ---------------------------------------------------------------- culorile pe roluri
class HdsRoluri(Baza):
	skin = _skin_ecran("HdsRoluri")

	def __init__(self, session, stare):
		Baza.__init__(self, session, stare)
		self.skinName = "HdsRoluri"
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], cu_ridicari({
			"ok": self.editeaza, "cancel": self.close, "red": self.close, "green": self.editeaza,
			"yellow": self.din_paleta,
			"up": lambda: self.muta(True), "down": lambda: self.muta(False),
			"left": lambda: self.pagina(True), "right": lambda: self.pagina(False),
		}), -1)

	def pagina(self, sus):
		lista_muta(self["lista"], "pageUp" if sus else "pageDown")

	def reface(self):
		pal = self.stare.paleta()
		lista = []
		for rol in P.EDITABILE:
			v = pal[rol]
			marcaj = "* " if rol in self.stare.conf["roluri"] else ""
			lista.append(rand(_("role_" + rol), marcaj + P.hexa(v), culoare=P.peste(v, 0x00202020) if P.FEL[rol] != "culoare" else v, sub=True))
		idx = self.index()
		self["lista"].setList(lista)
		lista_la(self["lista"], idx)
		self["titlu"].setText(_("set_colors"))
		self["ajutor"].setText("")
		self["tasta_rosu"].setText(_("set_exit"))
		self["tasta_verde"].setText(_("set_edit"))
		self["tasta_galben"].setText(_("set_from_palette"))
		self.coloreaza(pal)

	def editeaza(self):
		# alegerea pe grila (ecrane_culoare.py); codul hex si R, V, B raman sub Albastru (Avansat) acolo
		i = self.index()
		if 0 <= i < len(P.EDITABILE):
			from .ecrane_culoare import HdsAlegeCuloare
			self.session.openWithCallback(lambda *a: self.reface(), HdsAlegeCuloare, self.stare, P.EDITABILE[i])

	def din_paleta(self):
		i = self.index()
		if 0 <= i < len(P.EDITABILE):
			self.stare.conf["roluri"].pop(P.EDITABILE[i], None)
			self.reface()


# ---------------------------------------------------------------- editorul unei culori
class HdsEditorCuloare(Baza):
	skin = _skin_ecran("HdsEditorCuloare")
	PAS = 5

	def __init__(self, session, stare, rol):
		Baza.__init__(self, session, stare)
		self.skinName = "HdsEditorCuloare"
		self.rol = rol
		self.inainte = stare.conf["roluri"].get(rol)
		self.valoare = stare.paleta()[rol]
		self.cu_alfa = P.FEL[rol] in ("panou", "strat")
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], cu_ridicari({
			"ok": self.ok, "cancel": self.renunta, "red": self.renunta, "green": self.gata,
			"yellow": self.din_paleta,
			"up": lambda: self.muta(True), "down": lambda: self.muta(False),
			"left": lambda: self.lateral(-1), "right": lambda: self.lateral(1),
		}), -1)

	def reface(self):
		a, r, g, b = P.parti(self.valoare)
		randuri = [rand(_("set_hex"), P.hexa(self.valoare), culoare=self.valoare & 0xFFFFFF),
			rand(_("set_red"), "< %d >" % r), rand(_("set_green"), "< %d >" % g), rand(_("set_blue"), "< %d >" % b)]
		if self.cu_alfa:
			randuri.append(rand(_("set_alpha"), "< %d%% >" % int(a * 100 / 255.0 + 0.5)))
		randuri.append(rand(_("set_role_back")))
		idx = self.index()
		self["lista"].setList(randuri)
		lista_la(self["lista"], idx)
		self["titlu"].setText(_("role_" + self.rol))
		self["tasta_rosu"].setText(_("set_exit"))
		self["tasta_verde"].setText(_("set_save"))
		self["tasta_galben"].setText(_("set_from_palette"))
		self.stare.conf["roluri"][self.rol] = self.valoare
		self.coloreaza(self.stare.paleta())

	def lateral(self, d):
		i = self.index()
		a, r, g, b = P.parti(self.valoare)
		pas = self.PAS * d
		if i == 1:
			r = max(0, min(255, r + pas))
		elif i == 2:
			g = max(0, min(255, g + pas))
		elif i == 3:
			b = max(0, min(255, b + pas))
		elif i == 4 and self.cu_alfa:
			a = max(0, min(255, a + pas))
		else:
			return
		self.valoare = P.argb(a, r, g, b)
		self.reface()

	def ok(self):
		i = self.index()
		if i == 0:
			from Screens.VirtualKeyBoard import VirtualKeyBoard
			try:
				self.session.openWithCallback(self.hex_introdus, VirtualKeyBoard, title=_("set_hex"), text=P.hexa(self.valoare))
			except Exception:
				pass
		elif i == (5 if self.cu_alfa else 4):
			self.din_paleta()
		else:
			self.lateral(1)

	def hex_introdus(self, text=None):
		if text:
			v = P.citeste_culoare(text)
			if v is not None:
				if not self.cu_alfa:
					v &= 0x00FFFFFF
				self.valoare = v
		self.reface()

	def din_paleta(self):
		self.stare.conf["roluri"].pop(self.rol, None)
		self.close()

	def gata(self):
		self.stare.conf["roluri"].pop(self.rol, None)
		if self.valoare != self.stare.paleta()[self.rol]:
			self.stare.conf["roluri"][self.rol] = self.valoare
		self.close()

	def renunta(self):
		if self.inainte is None:
			self.stare.conf["roluri"].pop(self.rol, None)
		else:
			self.stare.conf["roluri"][self.rol] = self.inainte
		self.close()
