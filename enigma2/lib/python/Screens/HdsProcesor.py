# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsProcesor.py: ecranul „Procesor”. Meniu > Sistem & Dispozitive.
#
# Doua randuri (sus/jos intre ele):
# - „Modul de lucru” (config.hds_procesor.mod din Components/HdsProcesor.py): stanga/dreapta (si tastele < > ale
#   telecomenzii, home/end) schimba alegerea si descrierea ei, fara sa aplice nimic; OK sau Verde salveaza si aplica pe
#   loc (seteazaMod, aceeasi functie ca pagina web /procesor); EXIT sau Rosu renunta;
# - „Graficul”: stanga/dreapta sau OK alege ultima ora sau ultimele 30 de minute; graficul se schimba pe loc. Alegerea
#   sta numai in RAM cat merge enigma2 (nu e o setare, nu se scrie nimic). Verde salveaza modul si de pe randul acesta.
# Descrierea de sub randuri e a randului ales.
#
# Citirile vii (HdsProcesor.citire), in stanga: frecventa setata (plafonul; modul e pe primul rand) si cea de acum,
# temperatura (galbena de la 80 °C, rosie de la 95 °C), tensiunea, procentul folosit si timpul pe fiecare treapta de la
# pornire (procentul si durata), plus motivul pentru care plafonul e mai jos (caldura, racirea, pornirea sigura, alt
# program), cu galben, iar cateva minute dupa revenirea plafonului, cu verde, ca receptorul s-a racit (stare_bine).
# Cand nu e nimic de spus despre plafon, in acelasi loc, cu gri, nota: paza driverului si, fara semnul probei de
# caldura, cand apare modul Performanta (HdsProcesor.textNotaEcran).
# In dreapta, graficul temperaturii pe minute (HdsProcesor.istoricGrafic, desenat de HdsProcesor.desenGrafic pe un
# eCanvas): cea mai mare temperatura din minut, banda frecventei, liniile pragurilor pe bucata de timp a modului lor,
# cu valorile intr-o coloana in dreapta; sub el legenda si de cand exista istoricul. Istoricul il tine firul pazei si
# cand ecranul e inchis; ecranul numai il citeste. Panza se redeseneaza numai cand se schimba ce se vede (minut nou,
# temperatura sau frecventa minutului de acum, modul, alegerea, marimea: Istoric.semnatura), deci de 1-3 ori pe minut,
# nu la fiecare citire; desenul il face firul gRC, nu firul enigma2. O exceptie in desen nu iese din ecran: panza se
# umple cu fundalul (nu ramane imaginea veche).
#
# Ceasul de 1,5 s merge numai cat ecranul e aratat. Un OK refuzat pune randul la loc si tine mesajul pana la tasta
# urmatoare (cel mult EROARE_S secunde), peste improspatarea citirilor. Fara cpufreq (si daca dispare cat ecranul e
# deschis) randurile de setare, tasta Verde, graficul si linia despartitoare se ascund, iar ecranul spune ca frecventa
# nu se poate citi sau schimba.

import time

from .Screen import Screen
from Components.ActionMap import ActionMap
from Components.ConfigList import ConfigListScreen
from Components.Label import Label
from Components.ProgressBar import ProgressBar
from Components.Sources.CanvasSource import CanvasSource
from Components.Sources.StaticText import StaticText
from Components.config import config, getConfigListEntry, ConfigSelection
from Components import HdsProcesor as P

P.initConfig()

TREPTE_ARATATE = 5
CEAS_MS = 1500
EROARE_S = 8

# alegerea graficului (minute, ca text), tinuta cat merge enigma2; nu se salveaza
_grafic_ales = [str(P.GRAFIC_MINUTE[0])]


def _randTreapta(i):
	y = 366 + i * 28
	return ('<widget name="treapta%d" position="20,%d" size="110,26" font="Regular;18" halign="right" '
		'valign="center" /><widget name="bara%d" position="140,%d" size="300,14" borderWidth="1" '
		'borderColor="#00888888" /><widget name="procent%d" position="450,%d" size="250,26" font="Regular;18" '
		'halign="left" valign="center" />') % (i, y, i, y + 6, i, y)


def _randValoare(nume, y):
	return ('<widget source="e_%s" render="Label" position="20,%d" size="240,28" font="Regular;20" halign="left" '
		'valign="center" /><widget source="v_%s" render="Label" position="266,%d" size="434,28" font="Regular;20" '
		'halign="left" valign="center" />') % (nume, y, nume, y)


class HdsProcesor(Screen, ConfigListScreen):
	skin = """
	<screen name="HdsProcesor" position="center,center" size="1240,690" title="Procesor">
		<widget name="config" position="20,12" size="1200,76" scrollbarMode="showNever" font="Regular;22" secondfont="Regular;16" itemHeight="38" />
		<widget source="descriere" render="Label" position="20,92" size="1200,54" font="Regular;19" halign="left" valign="top" />
		<widget source="detaliu" render="Label" position="20,148" size="1200,24" font="Regular;16" halign="left" valign="top" foregroundColor="#00a8a8a8" />
		""" + _randValoare("setata", 180) + _randValoare("acum", 210) + """
		<widget source="e_temp" render="Label" position="20,240" size="240,28" font="Regular;20" halign="left" valign="center" />
		<widget name="temp_normal" position="266,240" size="434,28" font="Regular;20" halign="left" valign="center" />
		<widget name="temp_galben" position="266,240" size="434,28" font="Regular;20" halign="left" valign="center" foregroundColor="#00ffd24d" />
		<widget name="temp_rosu" position="266,240" size="434,28" font="Regular;20" halign="left" valign="center" foregroundColor="#00ff5a4a" />
		""" + _randValoare("tensiune", 270) + _randValoare("folosit", 300) + """
		<widget source="titlu_trepte" render="Label" position="20,336" size="680,26" font="Regular;18" halign="left" valign="center" />
		""" + "".join(_randTreapta(i) for i in range(TREPTE_ARATATE)) + """
		<widget source="nota" render="Label" position="20,512" size="680,84" font="Regular;17" halign="left" valign="top" foregroundColor="#00a8a8a8" transparent="1" />
		<widget source="stare" render="Label" position="20,512" size="680,84" font="Regular;18" halign="left" valign="top" foregroundColor="#00ffd24d" transparent="1" />
		<widget source="stare_bine" render="Label" position="20,512" size="680,84" font="Regular;18" halign="left" valign="top" foregroundColor="#0066d18b" transparent="1" />
		<widget name="despartitor" position="714,180" size="1,430" backgroundColor="#00444444" />
		<widget source="titlu_grafic" render="Label" position="730,180" size="490,28" font="Regular;20" halign="left" valign="center" />
		<widget source="grafic" render="Canvas" position="730,210" size="490,250" />
		<widget source="legenda" render="Label" position="730,464" size="490,120" font="Regular;15" halign="left" valign="top" foregroundColor="#00a8a8a8" />
		<widget source="istoric" render="Label" position="730,588" size="490,22" font="Regular;15" halign="left" valign="center" />
		<widget source="key_red" render="Label" position="20,640" size="220,32" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#9f1313" transparent="0" />
		<widget source="key_green" render="Label" position="260,640" size="220,32" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#1f771f" transparent="0" />
	</screen>
	"""

	def __init__(self, session):
		Screen.__init__(self, session)
		self.setTitle(_("Procesor"))
		self["key_red"] = StaticText(_("Cancel"))
		self["key_green"] = StaticText(_("Save"))
		self["descriere"] = StaticText("")
		self["detaliu"] = StaticText("")
		for nume, eticheta in (("setata", _("Frecvența setată")), ("acum", _("Frecvența de acum")),
				("tensiune", _("Tensiunea")), ("folosit", _("Procesor folosit"))):
			self["e_" + nume] = StaticText(eticheta)
			self["v_" + nume] = StaticText("")
		self["e_temp"] = StaticText(_("Temperatura"))
		for culoare in ("normal", "galben", "rosu"):
			self["temp_" + culoare] = Label("")
		self["titlu_trepte"] = StaticText("")
		for i in range(TREPTE_ARATATE):
			self["treapta%d" % i] = Label("")
			self["bara%d" % i] = ProgressBar()
			self["procent%d" % i] = Label("")
		self["stare"] = StaticText("")
		self["stare_bine"] = StaticText("")
		self["nota"] = StaticText("")
		self["despartitor"] = Label("")     # linia dintre citiri si grafic (in skinul HDSatelit)
		self["grafic"] = CanvasSource()
		self["titlu_grafic"] = StaticText("")
		self["legenda"] = StaticText("")
		self["istoric"] = StaticText("")
		self.eroare = None          # (text, ceasul monoton): mesajul unui OK refuzat, tinut peste improspatare
		self.desenat = None         # (semnatura istoricului, minute, marimea panzei, paza pornita, modul) desenate
		self.marime = None          # marimea panzei graficului, din skin (dupa asezare)
		self.culori = None
		self.grafic = ConfigSelection(default=_grafic_ales[0],
			choices=[(str(m), P.NUME_GRAFIC[m]) for m in P.GRAFIC_MINUTE])
		self.list = [getConfigListEntry(_("Modul de lucru"), config.hds_procesor.mod),
			getConfigListEntry(_("Graficul"), self.grafic)]
		ConfigListScreen.__init__(self, self.list, session=session)
		try:
			self["config"].onSelectionChanged.append(self.arataDescriere)
		except AttributeError:
			pass
		self["actions"] = ActionMap(["SetupActions", "ColorActions"], {
			"ok": self.keyOk,
			"green": self.keySave,
			"cancel": self.keyCancel,
			"red": self.keyCancel,
		}, -2)
		from enigma import eTimer
		self.ceas = eTimer()
		self.ceas.callback.append(self.actualizeaza)
		self.onShown.append(self._pornesteCeasul)
		self.onHide.append(self._opresteCeasul)
		self.onClose.append(self._opresteCeasul)
		self.onLayoutFinish.append(self._dupaAsezare)
		self.disponibil = None
		self._aplicaDisponibil(P.disponibil())
		self.arataDescriere()

	# ---- ceasul: numai cat ecranul e aratat ----

	def _pornesteCeasul(self):
		self.actualizeaza()
		self.ceas.start(CEAS_MS, False)

	def _opresteCeasul(self):
		self.ceas.stop()

	# ---- setarea ----

	def _aplicaDisponibil(self, disp):
		"""Fara cpufreq nu e nimic de ales: randurile de setare, tasta Verde, graficul si linia despartitoare dispar."""
		disp = bool(disp)
		if disp == self.disponibil:
			return
		self.disponibil = disp
		for nume in ("config", "despartitor"):
			try:
				if disp:
					self[nume].show()
				else:
					self[nume].hide()
			except (AttributeError, KeyError):
				pass
		self["key_green"].setText(_("Save") if disp else "")
		self._arataGraficul(disp)
		self.arataDescriere()

	def _randGrafic(self):
		"""Randul ales e „Graficul”."""
		try:
			rand = self["config"].getCurrent()
		except (AttributeError, KeyError):
			return False
		return rand is not None and rand[1] is self.grafic

	def arataDescriere(self):
		if not self.disponibil:
			self["descriere"].setText(P.textIndisponibil())
			self["detaliu"].setText("")
			return
		if self._randGrafic():
			self["descriere"].setText(P.textDescriereGrafic())
			self["detaliu"].setText("")
			return
		mod = config.hds_procesor.mod.value
		self["descriere"].setText(P.descriereMod(mod))
		self["detaliu"].setText(P.detaliuMod(mod))

	def _dupaTasta(self):
		self.eroare = None
		if self._randGrafic():
			_grafic_ales[0] = self.grafic.value
			self.deseneazaGrafic()
		self.arataDescriere()

	def keyLeft(self):
		ConfigListScreen.keyLeft(self)
		self._dupaTasta()

	def keyRight(self):
		ConfigListScreen.keyRight(self)
		self._dupaTasta()

	def keyHome(self):
		ConfigListScreen.keyHome(self)
		self._dupaTasta()

	def keyEnd(self):
		ConfigListScreen.keyEnd(self)
		self._dupaTasta()

	def keyOk(self):
		"""Pe randul „Graficul” OK trece la cealalta alegere (ca dreapta); pe primul rand salveaza modul, ca Verde."""
		if self.disponibil and self._randGrafic():
			self.keyRight()
			return
		self.keySave()

	def _eroareActiva(self):
		if self.eroare and time.monotonic() - self.eroare[1] < EROARE_S:
			return self.eroare[0]
		self.eroare = None
		return None

	def keySave(self):
		if not self.disponibil:
			return
		element = config.hds_procesor.mod
		reusit, mesaj = P.seteazaMod(element.value)
		if not reusit:
			element.cancel()
			try:
				self["config"].invalidateCurrent()      # randul arata iar valoarea care ramane
			except AttributeError:
				pass
			self._aplicaDisponibil(P.disponibil())
			self.arataDescriere()
			self.eroare = (mesaj, time.monotonic())
			self["stare"].setText(mesaj)
			self["stare_bine"].setText("")
			self["nota"].setText("")
			return
		self.close()

	def keyCancel(self):
		config.hds_procesor.mod.cancel()
		self.close()

	# ---- graficul ----

	def _rendererGrafic(self):
		"""Renderer-ul Canvas al graficului (marimea panzei vine din skin), sau None."""
		for r in getattr(self, "renderer", None) or ():
			if getattr(r, "source", None) is self["grafic"] and getattr(r, "instance", None) is not None:
				return r
		return None

	def _dupaAsezare(self):
		r = self._rendererGrafic()
		if r is not None:
			try:
				m = r.instance.size()
				self.marime = (m.width(), m.height())
			except Exception as e:
				print("[HdsProcesor] marimea graficului: %r" % (e,))
		try:
			from skin import colorNames
		except Exception:
			colorNames = None
		self.culori = P.culoriGrafic(colorNames)
		self._arataGraficul(self.disponibil)
		self.deseneazaGrafic()

	def _arataGraficul(self, vizibil):
		r = self._rendererGrafic()
		if r is not None:
			try:
				if vizibil:
					r.instance.show()
				else:
					r.instance.hide()
			except Exception:
				pass
		if not vizibil:
			for nume in ("titlu_grafic", "legenda", "istoric"):
				self[nume].setText("")
			self.desenat = None

	def _font(self, marime):
		"""(font pentru eCanvas.writeText, marimea folosita la asezare): „Regular” la marimea data, marita de
		Marimea textului ca textele skinului, cu functia comuna a fonturilor puse din cod (Components/HdsMarireText:
		fontul HD Satelit si sub un skin strain; cu HDSatelit ales ramane "Regular")."""
		from Components import HdsMarireText as MT
		return MT.fontCod("Regular", marime), MT.marimeCod(marime)

	def _text(self, nume, text):
		"""setText numai la schimbare (eticheta nu se redeseneaza degeaba la fiecare improspatare)."""
		if self[nume].getText() != text:
			self[nume].setText(text)

	def deseneazaGrafic(self):
		"""Redeseneaza panza numai cand se schimba ce se vede (Istoric.semnatura: minut nou, temperatura, frecventa,
		caldura sau modul minutului de acum; alegerea, marimea, modul, paza pornita). O exceptie nu iese din ecran: se
		scrie in jurnal, iar panza se umple cu fundalul (nu ramane desenul vechi, care ar minti)."""
		if not self.disponibil or not self.marime:
			return
		try:
			self._deseneazaGrafic()
		except Exception as e:
			print("[HdsProcesor] graficul: %r" % (e,))
			self.desenat = None
			try:
				latime, inaltime = self.marime
				panza = self["grafic"]
				panza.clear()
				panza.fill(0, 0, latime, inaltime, (self.culori or P.CULORI_GRAFIC)["fundal"])
				panza.flush()
			except Exception as e2:
				print("[HdsProcesor] panza: %r" % (e2,))

	def _deseneazaGrafic(self):
		minute = int(self.grafic.value)
		p = P.procesor()
		cheie = (p.istoric.semnatura(), minute, self.marime, p.pornit, p.mod)
		if cheie == self.desenat:
			return
		g = P.istoricGrafic(minute)
		self._text("titlu_grafic", P.titluGrafic(minute))
		self._text("legenda", P.textLegendaGrafic())
		self._text("istoric", P.textIstoric(g))
		latime, inaltime = self.marime
		font, marime = self._font(P.fontGrafic(inaltime))
		ops = P.desenGrafic(g, latime, inaltime, self.culori, marime)
		self._deseneaza(ops, font)
		self.desenat = cheie

	def _deseneaza(self, ops, font):
		from enigma import RT_HALIGN_CENTER, RT_HALIGN_LEFT, RT_HALIGN_RIGHT, RT_VALIGN_CENTER
		aliniere = {"stanga": RT_HALIGN_LEFT, "dreapta": RT_HALIGN_RIGHT, "centru": RT_HALIGN_CENTER}
		fundal = (self.culori or P.CULORI_GRAFIC)["fundal"]
		panza = self["grafic"]
		panza.clear()
		for op in ops:
			fel = op[0]
			if fel == "fill":
				panza.fill(op[1], op[2], op[3], op[4], op[5])
			elif fel == "linie":
				panza.drawLine(op[1], op[2], op[3], op[4], op[5], op[6])
			elif fel == "cerc":
				panza.fillCircle(op[1], op[2], op[3], op[4])
			elif fel == "text":
				panza.writeText(op[1], op[2], op[3], op[4], op[5], fundal, font, op[6],
					aliniere.get(op[7], RT_HALIGN_LEFT) | RT_VALIGN_CENTER)
		panza.flush()

	# ---- citirile vii ----

	def actualizeaza(self):
		try:
			self.arata(P.citire(1.0))
		except Exception as e:
			print("[HdsProcesor] citirea: %r" % (e,))
		self.deseneazaGrafic()

	def arata(self, d):
		disp = d.get("disponibil")
		self._aplicaDisponibil(disp)
		self["v_setata"].setText(P.textFrecventaSetataScurt(d) if disp else _("nu se poate citi"))
		self["v_acum"].setText(P.textFrecventa(d.get("frecventa_khz")))
		self["v_tensiune"].setText(P.textTensiune(d.get("tensiune_mv")))
		folosit = d.get("folosit_procent")
		self["v_folosit"].setText("%d%%" % folosit if folosit is not None else _("nu se poate citi"))
		t = d.get("temperatura")
		culoare = P.temperaturaCuloare(t)
		for c in ("normal", "galben", "rosu"):
			eticheta = self["temp_" + c]
			if c == culoare:
				eticheta.setText(P.textTemperatura(t))
				eticheta.show()
			else:
				eticheta.setText("")
				eticheta.hide()
		trepte = P.trepteProcent(d)
		self["titlu_trepte"].setText(_("Timp pe fiecare treaptă (de la pornire)") if trepte else "")
		for i in range(TREPTE_ARATATE):
			if i < len(trepte):
				khz, procent, secunde = trepte[i]
				self["treapta%d" % i].setText(P.textFrecventa(khz))
				self["bara%d" % i].setValue(procent)
				self["procent%d" % i].setText(P.textTreapta(procent, secunde))
				for w in ("treapta%d", "bara%d", "procent%d"):
					self[w % i].show()
			else:
				for w in ("treapta%d", "bara%d", "procent%d"):
					self[w % i].hide()
		eroare = self._eroareActiva()
		text = eroare if eroare else P.textMotivCitire(d)
		bine = not eroare and P.racitCitire(d)       # „s-a racit”: vestea buna, cu verde
		self["stare"].setText("" if bine else text)
		self["stare_bine"].setText(text if bine else "")
		# nota gri sta in acelasi loc: numai cand nu e nimic de spus despre plafon
		self._text("nota", "" if text else P.textNotaEcran(d.get("paza_driver"), bool(disp)))
