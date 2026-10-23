# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
# HDS-MARCA: skin HDSatelit, Monea Software pentru HD Satelit, 2026
#
# HdsAlegeCuloare: alegerea vizuala a culorii unui rol (din "Culori pe roluri"), numai cu sagetile si OK. In stanga
# grila de nuante (grila.py: nuanta pe orizontala, lumina pe verticala, griurile in prima coloana), randul treptelor de
# transparenta (numai la rolurile cu transparenta) si banda cu culoarea de acum, culorile puse de mana si culorile
# paletei; celula aleasa e marita si inramata. In dreapta aceeasi previzualizare ca in celelalte ecrane ale panoului,
# colorata pe loc. Verde (sau OK) pastreaza culoarea, Rosu renunta, Galben = din paleta, Albastru = Avansat (codul hex si
# R, V, B, transparenta: HdsEditorCuloare). Culorile ecranului sunt scrise direct si fonturile sunt Regular/Bold, ca
# panoul sa se deschida si cand skinul activ nu e HDSatelit. Merge pe Python 2.7 si 3.x.
from enigma import ePoint, eSize, gRGB
from Components.ActionMap import ActionMap
from Components.Label import Label
from Screens.Screen import Screen

from . import grila as G
from . import paleta as P
from .ecrane import Previzualizare, skin_previzualizare, skin_taste, _scaleaza, _px
from .texte import tr_str as _

# textele noi ale ecranului: cheile merg in limbi-staging/*.json; pana atunci, textul de aici
_IMPLICIT = {
	"set_grid_band": u"Recente și paleta",
	"set_grid_value": u"Culoarea aleasă: {0}",
	"set_grid_value_alpha": u"Culoarea aleasă: {0}, transparență {1}",
	"set_grid_help": u"Săgețile te mută pe grilă, pe rândul transparenței și pe banda de jos; culoarea se vede pe loc "
		u"în dreapta. OK sau Verde păstrează culoarea, Albastru deschide codul hex și R, V, B.",
	"set_advanced": u"Avansat",
}


def _t(cheie, *args):
	s = _(cheie, *args)
	if s == cheie or (str is bytes and s == cheie.encode("utf-8")):
		s = _IMPLICIT.get(cheie, cheie)
		for i, a in enumerate(args):
			s = s.replace(u"{%d}" % i, a if isinstance(a, type(u"")) else u"%s" % (a,))
		if str is bytes:
			s = s.encode("utf-8")
	return s


CELULA = 52
PAS_GRILA = 56
X_GRILA = 96
Y_GRILA = 168
Y_ALFA = Y_GRILA + G.RANDURI * PAS_GRILA + 16          # 628
Y_BANDA = Y_ALFA + 72                                  # 700
X_RAND = 356
PAS_ALFA = 72
PAS_BANDA = 48


def _skin():
	r = ['<screen name="HdsAlegeCuloare" position="0,0" size="1920,1080" flags="wfNoBorder" backgroundColor="#000C1220">',
		'<widget name="titlu" position="96,36" size="980,64" font="Bold;44" foregroundColor="#00F2F4F8" backgroundColor="#000C1220" transparent="1" valign="center" noWrap="1" />',
		'<widget name="eticheta" position="96,112" size="980,44" font="Regular;28" foregroundColor="#00AEB9CC" backgroundColor="#000C1220" transparent="1" valign="center" noWrap="1" />']
	for col in range(G.COLOANE):
		for rand in range(G.RANDURI):
			r.append('<widget name="c_%d_%d" position="%d,%d" size="%d,%d" backgroundColor="#00000000" transparent="0" zPosition="1" />' % (
				col, rand, X_GRILA + col * PAS_GRILA, Y_GRILA + rand * PAS_GRILA, CELULA, CELULA))
	r.append('<widget name="et_alfa" position="96,%d" size="250,52" font="Regular;26" foregroundColor="#00F2F4F8" backgroundColor="#000C1220" transparent="1" valign="center" noWrap="1" />' % Y_ALFA)
	for i in range(len(G.ALFE)):
		r.append('<widget name="a_%d" position="%d,%d" size="64,52" font="Regular;22" foregroundColor="#00F2F4F8" backgroundColor="#00000000" transparent="0" halign="center" valign="center" zPosition="1" />' % (
			i, X_RAND + i * PAS_ALFA, Y_ALFA))
	r.append('<widget name="et_banda" position="96,%d" size="250,52" font="Regular;26" foregroundColor="#00F2F4F8" backgroundColor="#000C1220" transparent="1" valign="center" noWrap="1" />' % Y_BANDA)
	for i in range(G.BANDA_MAXIM):
		r.append('<widget name="b_%d" position="%d,%d" size="44,52" backgroundColor="#00000000" transparent="0" zPosition="1" />' % (
			i, X_RAND + i * PAS_BANDA, Y_BANDA))
	r.append('<widget name="rama" position="0,0" size="72,72" backgroundColor="#00FFFFFF" transparent="0" zPosition="3" />')
	r.append('<widget name="ales" position="0,0" size="64,64" font="Regular;22" foregroundColor="#00F2F4F8" backgroundColor="#00000000" transparent="0" halign="center" valign="center" zPosition="4" />')
	r.append('<widget name="valoare" position="96,776" size="980,44" font="Regular;28" foregroundColor="#00F2F4F8" backgroundColor="#000C1220" transparent="1" valign="center" noWrap="1" />')
	r.append('<widget name="ajutor" position="96,830" size="980,140" font="Regular;26" foregroundColor="#00AEB9CC" backgroundColor="#000C1220" transparent="1" />')
	r.append(skin_taste())
	r.append(skin_previzualizare())
	r.append("</screen>")
	return _scaleaza("".join(r))


def _gol(*args):
	pass


class HdsAlegeCuloare(Screen, Previzualizare):
	"""Culoarea unui rol aleasa pe grila; `stare` e Stare din ecrane.py, `rol` cheia din paleta.EDITABILE."""

	def __init__(self, session, stare, rol):
		self.skin = _skin()
		Screen.__init__(self, session)
		self.skinName = "HdsAlegeCuloare"
		self.stare = stare
		self.rol = rol
		self.cu_alfa = G.are_alfa(rol)
		self.inainte = stare.conf["roluri"].get(rol)
		self.acum = stare.paleta()[rol]
		self.alfa = (self.acum >> 24) & 255 if self.cu_alfa else 0
		self.rgb = G.rgb(self.acum)
		self.banda = G.banda(rol, stare.conf, stare.paleta(), self.acum)
		self.zona = "banda"
		self.col, self.rand = G.cea_mai_apropiata(self.acum)
		self.i_alfa = G.treapta_alfa(self.alfa)
		self.i_banda = 0
		self["titlu"] = Label(_("role_" + rol))
		self["eticheta"] = Label(_("set_colors"))
		for col in range(G.COLOANE):
			for rand in range(G.RANDURI):
				self["c_%d_%d" % (col, rand)] = Label("")
		self["et_alfa"] = Label(_("set_alpha") if self.cu_alfa else "")
		for i, p in enumerate(G.ALFE):
			self["a_%d" % i] = Label("%d%%" % p if self.cu_alfa else "")
		self["et_banda"] = Label(_t("set_grid_band"))
		for i in range(G.BANDA_MAXIM):
			self["b_%d" % i] = Label("")
		self["rama"] = Label("")
		self["ales"] = Label("")
		self["valoare"] = Label("")
		self["ajutor"] = Label(_t("set_grid_help"))
		for n in ("rosu", "verde", "galben", "albastru"):
			self["tasta_" + n] = Label("")
			self["bara_" + n] = Label("")
		self["tasta_rosu"].setText(_("set_exit"))
		self["tasta_verde"].setText(_("set_choose"))
		self["tasta_galben"].setText(_("set_from_palette"))
		self["tasta_albastru"].setText(_t("set_advanced"))
		self.pune_previzualizare()
		directii = {}
		for s in ("up", "down", "left", "right"):
			directii[s] = (lambda s=s: self.sageata(s))
			directii[s + "Repeated"] = (lambda s=s: self.sageata(s))
			directii[s + "Up"] = _gol
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], dict(directii, **{
			"ok": self.pastreaza, "green": self.pastreaza, "cancel": self.renunta, "red": self.renunta,
			"yellow": self.din_paleta, "blue": self.avansat,
		}), -1)
		self.onLayoutFinish.append(self._gata)

	# ------------------------------------------------------------ desen
	def _fund(self, nume, c):
		try:
			inst = self[nume].instance
			if inst is not None:
				inst.setBackgroundColor(gRGB(G.rgb(c)))
				inst.invalidate()
		except Exception:
			pass

	def _gata(self):
		for col in range(G.COLOANE):
			for rand in range(G.RANDURI):
				self._fund("c_%d_%d" % (col, rand), G.culoare(col, rand))
		for i in range(G.BANDA_MAXIM):
			if i < len(self.banda):
				self._fund("b_%d" % i, self.banda[i])
				self["b_%d" % i].show()
			else:
				self["b_%d" % i].hide()
		for i in range(len(G.ALFE)):
			if not self.cu_alfa:
				self["a_%d" % i].hide()
		for n in ("rosu", "verde", "galben", "albastru"):
			self["bara_" + n].show()
		self.reface()

	def _alfe(self):
		"""Treptele de transparenta: culoarea aleasa peste un gri mijlociu, cat se vede prin ea."""
		if not self.cu_alfa:
			return
		for i, p in enumerate(G.ALFE):
			a = G.alfa_din_procent(p)
			self._fund("a_%d" % i, P.peste(G.compune(self.rgb, a), 0x00808080))

	def _celula(self):
		if self.zona == "grila":
			return (_px(X_GRILA + self.col * PAS_GRILA), _px(Y_GRILA + self.rand * PAS_GRILA), _px(CELULA), _px(CELULA))
		if self.zona == "alfa":
			return (_px(X_RAND + self.i_alfa * PAS_ALFA), _px(Y_ALFA), _px(64), _px(52))
		return (_px(X_RAND + self.i_banda * PAS_BANDA), _px(Y_BANDA), _px(44), _px(52))

	def reface(self):
		x, y, w, h = self._celula()
		m = _px(6)
		for nume, d in (("rama", m + _px(4)), ("ales", m)):
			try:
				inst = self[nume].instance
				inst.move(ePoint(x - d, y - d))
				inst.resize(eSize(w + 2 * d, h + 2 * d))
			except Exception:
				pass
		c = self.culoare()
		self._fund("ales", P.peste(c, 0x00808080) if self.zona == "alfa" else c)
		self["ales"].setText(G.text_procent(self.alfa) if self.zona == "alfa" else "")
		self._alfe()
		if self.cu_alfa:
			self["valoare"].setText(_t("set_grid_value_alpha", G.hex6(c), G.text_procent(self.alfa)))
		else:
			self["valoare"].setText(_t("set_grid_value", G.hex6(c)))
		self.stare.conf["roluri"][self.rol] = c
		self.coloreaza(self.stare.paleta())

	def culoare(self):
		return G.compune(self.rgb, self.alfa if self.cu_alfa else 0)

	# ------------------------------------------------------------ taste
	def sageata(self, s):
		zone = ["grila"] + (["alfa"] if self.cu_alfa else []) + ["banda"]
		if s in ("left", "right"):
			d = -1 if s == "left" else 1
			if self.zona == "grila":
				self.col = max(0, min(G.COLOANE - 1, self.col + d))
			elif self.zona == "alfa":
				self.i_alfa = max(0, min(len(G.ALFE) - 1, self.i_alfa + d))
			else:
				self.i_banda = max(0, min(len(self.banda) - 1, self.i_banda + d))
		else:
			d = -1 if s == "up" else 1
			if self.zona == "grila" and 0 <= self.rand + d < G.RANDURI:
				self.rand += d
			else:
				i = zone.index(self.zona) + d
				if i < 0 or i >= len(zone):
					return
				self.zona = zone[i]
				if self.zona == "grila":
					self.rand = G.RANDURI - 1 if d < 0 else 0
		if self.zona == "grila":
			self.rgb = G.rgb(G.culoare(self.col, self.rand))
		elif self.zona == "alfa":
			# trecerea prin randul transparentei (Sus / Jos) nu schimba transparenta; numai Stanga / Dreapta
			if s in ("left", "right"):
				self.alfa = G.alfa_din_procent(G.ALFE[self.i_alfa])
		elif self.banda:
			self.rgb = G.rgb(self.banda[self.i_banda])
		self.reface()

	def pastreaza(self):
		c = self.culoare()
		self.stare.conf["roluri"].pop(self.rol, None)
		if c != self.stare.paleta()[self.rol]:
			self.stare.conf["roluri"][self.rol] = c
		self.close(True)

	def renunta(self):
		if self.inainte is None:
			self.stare.conf["roluri"].pop(self.rol, None)
		else:
			self.stare.conf["roluri"][self.rol] = self.inainte
		self.close(False)

	def din_paleta(self):
		self.stare.conf["roluri"].pop(self.rol, None)
		self.close(True)

	def avansat(self):
		from .ecrane import HdsEditorCuloare
		self.stare.conf["roluri"][self.rol] = self.culoare()
		self.session.openWithCallback(self._dupaAvansat, HdsEditorCuloare, self.stare, self.rol)

	def _dupaAvansat(self, *args):
		c = self.stare.paleta()[self.rol]
		self.rgb = G.rgb(c)
		if self.cu_alfa:
			self.alfa = (c >> 24) & 255
			self.i_alfa = G.treapta_alfa(self.alfa)
		self.reface()
