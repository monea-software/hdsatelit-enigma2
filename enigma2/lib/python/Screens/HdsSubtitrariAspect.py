# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsSubtitrariAspect (ecranul) - „Aspectul subtitrărilor": stilul literelor subtitrarilor TEXT (teletext, fisiere si,
# textul citit din subtitrarile DVB). Subtitrarile DVB ca poze raman cum le trimite postul.
# Randurile, grupate: un stil gata facut; literele (fontul, grosimea, marimea, culoarea); conturul (grosimea, culoarea);
# umbra (da/nu, culoarea, directia, distanta, moale sau tare); fundalul (niciunul, pe fiecare rand, o cutie; culoarea,
# opacitatea); asezarea (inaltimea fata de marginea de jos, distanta dintre randuri); subtitrarile DVB (marirea pozelor:
# clara sau OCR, numai cele care merg; textul de ajutor spune ce face cand cursorul e pe ea) si, cu OCR
# ales sau cerut de traducerea subtitrarilor (HdsOcrSubtitrari.esteOcrPornit), contorul „Recunoașterea textului": cate pagini s-au citit ca text si cate au ramas imagine; pe rand, ajutorul
# spune de ce (prea tarziu, text nesigur, fara model ...) si timpul mediu, iar OK pune contorul la zero. Tot atunci,
# randul „Limbile recunoașterii” („8 în imagine, 2 descărcate”): OK deschide lista limbilor (Screens/HdsOcrLimbi.py),
# de unde un model se descarca, se opreste sau se sterge. Contorul si numarul limbilor se improspateaza la CONTOR_MS
# cat e ecranul deschis. Randurile care nu au efect (culoarea umbrei cand umbra e oprita, culoarea fundalului fara
# fundal, culoarea conturului fara contur, contorul si limbile fara OCR) nu se arata.
#
# Previzualizarea: o fraza de proba desenata chiar de eSubtitleWidget (acelasi cod care deseneaza subtitrarile),
# pe tot ecranul, peste imaginea de acum, deci exact unde si cum vor aparea subtitrarile. Setarile se pun in
# eSubtitleWidget la fiecare schimbare (notificarile din Components/HdsSubtitrariAspect.py), iar eSubtitleWidget
# reface singur textul de pe ecran; la Anulare valorile se intorc si se pun inapoi o singura data.
# Galben: un fundal de proba deschis (jumatate alb, jumatate gri) in spatele frazei, pentru cand nu merge niciun
# canal sau imaginea e intunecata: pe el se vad umbra, conturul si fundalul randurilor.
#
# Skinul HDSatelit nu se atinge: ecranul isi poarta skinul aici, facut la deschidere dupa marimea ecranului
# (1920x1080 sau 1280x720), pentru ca fraza de proba trebuie sa acopere tot ecranul, ca subtitrarile.
# Aceleasi alegeri sunt in interfata web, pagina /subtitrari (Plugins/Extensions/HdsWebControl/subtitrari_web.py).

from __future__ import absolute_import

from enigma import getDesktop, eSubtitleWidget, eTimer

from Screens.Screen import Screen
from Components.ActionMap import ActionMap
from Components.ConfigList import ConfigListScreen
from Components.config import configfile, getConfigListEntry, ConfigNothing, ConfigSelection
from Components.GUIComponent import GUIComponent
from Components.Label import Label
from Components.Sources.StaticText import StaticText

from Components import HdsSubtitrariAspect as sa

# 8 randuri de lista, ca sub ea sa incapa doua randuri de ajutor (nota despre marirea DVB)
RANDURI_VIZIBILE = 8
# cat de des se improspateaza contorul OCR cat e ecranul deschis
CONTOR_MS = 2000


def _ocr():
	"""Components.HdsOcrSubtitrari, sau None (modulul lipseste sau nu se incarca: ecranul merge fara contor)"""
	try:
		from Components import HdsOcrSubtitrari
		return HdsOcrSubtitrari
	except Exception:
		return None


def _ocrLucreaza(ocr, setari):
	"""OCR-ul paginilor DVB lucreaza: ales la „Mărirea subtitrărilor DVB” sau cerut de traducerea subtitrarilor
	(Components/HdsOcrSubtitrari.esteOcrPornit); fara functie (modul vechi), numai alegerea maririi"""
	if setari.hds_marire_dvb.value == "ocr":
		return True
	f = getattr(ocr, "esteOcrPornit", None)
	try:
		return bool(f()) if f is not None else False
	except Exception:
		return False


def _modeleOcr():
	"""Components.HdsOcrModele, sau None (fara el randul limbilor nu se arata)"""
	try:
		from Components import HdsOcrModele
		return HdsOcrModele
	except Exception:
		return None


class ProbaSubtitrare(GUIComponent):
	"""eSubtitleWidget-ul adevarat, cu fraza de proba tinuta pe ecran."""
	GUI_WIDGET = eSubtitleWidget

	def __init__(self):
		GUIComponent.__init__(self)
		self.text = u""

	def arata(self, text=None):
		if text is not None:
			self.text = text
		if self.instance is not None and hasattr(self.instance, "showSample"):
			self.instance.showSample(self.text)


def _skin(latime, inaltime):
	def x(v):
		return int(round(v * latime / 1920.0))

	def y(v):
		return int(round(v * inaltime / 1080.0))

	def f(v):
		return max(12, int(round(v * inaltime / 1080.0)))

	panou = "#10141a22"
	butoane = []
	for i, (nume, culoare) in enumerate((("key_red", "#9f1313"), ("key_green", "#1f771f"), ("key_yellow", "#a08000"),
			("key_blue", "#18188b"))):
		butoane.append('<widget source="%s" render="Label" position="%d,%d" size="%d,%d" zPosition="5" font="Regular;%d" '
			'halign="center" valign="center" foregroundColor="#00ffffff" backgroundColor="%s" transparent="0" />'
			% (nume, x(390 + i * 288), y(590), x(276), y(46), f(22), culoare))
	return """
	<screen name="HdsSubtitrariAspect" position="0,0" size="%(l)d,%(h)d" flags="wfNoBorder" backgroundColor="#ff000000" title="Aspectul subtitrărilor">
		<widget name="fundal_deschis" position="0,%(fy)d" size="%(fl)d,%(fh)d" backgroundColor="#00e8e8e8" zPosition="1" />
		<widget name="fundal_mediu" position="%(fl)d,%(fy)d" size="%(fl2)d,%(fh)d" backgroundColor="#00708090" zPosition="1" />
		<widget name="proba" position="0,0" size="%(l)d,%(h)d" zPosition="2" transparent="1" />
		<eLabel position="%(px)d,%(py)d" size="%(pl)d,%(ph)d" backgroundColor="%(panou)s" zPosition="3" />
		<widget source="Title" render="Label" position="%(cx)d,%(ty)d" size="%(cl)d,%(th)d" font="Regular;%(tf)d" foregroundColor="#00ffffff" backgroundColor="%(panou)s" transparent="1" valign="center" zPosition="4" />
		<widget name="config" position="%(cx)d,%(ly)d" size="%(cl)d,%(lh)d" itemHeight="%(ih)d" font="Regular;%(lf)d" secondfont="Regular;%(vf)d" scrollbarMode="showOnDemand" backgroundColor="%(panou)s" zPosition="4" />
		<widget source="ajutor" render="Label" position="%(cx)d,%(ay)d" size="%(cl)d,%(ah)d" font="Regular;%(af)d" foregroundColor="#00d0d8e0" backgroundColor="%(panou)s" transparent="1" valign="center" zPosition="4" />
		%(butoane)s
	</screen>""" % {
		"l": latime, "h": inaltime,
		"fy": y(660), "fh": inaltime - y(660), "fl": latime // 2, "fl2": latime - latime // 2,
		"px": x(360), "py": y(36), "pl": x(1200), "ph": y(614), "panou": panou,
		"cx": x(390), "cl": x(1140),
		"ty": y(44), "th": y(52), "tf": f(34),
		"ly": y(100), "lh": y(RANDURI_VIZIBILE * 48), "ih": y(48), "lf": f(27), "vf": f(25),
		"ay": y(490), "ah": y(94), "af": f(21),
		"butoane": "\n\t\t".join(butoane),
	}


class HdsSubtitrariAspect(Screen, ConfigListScreen):
	def __init__(self, session):
		marime = getDesktop(0).size()
		self.skin = _skin(marime.width(), marime.height())
		Screen.__init__(self, session)
		self.setTitle(_("Aspectul subtitrărilor"))
		self.setari = sa.initConfig()
		sa.reimprospateazaFonturi()
		ConfigListScreen.__init__(self, [], session=session)
		self._toate = sa.elemente(self.setari)

		self["proba"] = ProbaSubtitrare()
		self["fundal_deschis"] = Label("")
		self["fundal_mediu"] = Label("")
		self._fundalProba = False
		self["ajutor"] = StaticText(self._textAjutor())
		self["key_red"] = StaticText(_("Cancel"))
		self["key_green"] = StaticText(_("Save"))
		self["key_yellow"] = StaticText(u"")
		self["key_blue"] = StaticText(_("Valori implicite"))

		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions"], {
			"ok": self.lista,
			"cancel": self.anuleaza,
			"red": self.anuleaza,
			"green": self.salveaza,
			"yellow": self.schimbaFundalProba,
			"blue": self.valoriImplicite,
		}, -2)

		# stilul gata facut: nu e o setare salvata, arata care stil se potriveste cu setarile de acum
		self.stil = ConfigSelection(choices=sa.textStiluri(), default=sa.PERSONALIZAT)
		self.stil.value = sa.stilCurent()
		self._inStil = False
		self.stil.addNotifier(self._stilAles, initial_call=False)
		# contorul OCR: un rand de citit (o singura alegere, textul contorului), improspatat de un ceas
		self.contorOcr = ConfigSelection(choices=[("contor", self._textContor())], default="contor")
		# limbile OCR: un rand de citit („8 în imagine, 2 descărcate”); OK deschide lista lor
		self.limbiOcr = ConfigSelection(choices=[("limbi", self._textLimbi())], default="limbi")
		self._ceasContor = eTimer()
		self._ceasContor.callback.append(self._improspateazaContor)
		# randurile care apar si dispar dupa umbra, fundal, contur si marirea DVB (contorul numai cu OCR)
		for cheie in ("umbra", "fundal", "contur", "marire_dvb"):
			sa.element(cheie, self.setari).addNotifier(self._randuriSchimbate, initial_call=False)
		for e in self._toate:
			e.addNotifier(self._setareSchimbata, initial_call=False)
		self._ultimul = 0
		self._facLista()
		self["config"].onSelectionChanged.append(self._sariPesteTitlu)
		self.onLayoutFinish.append(self._pornit)
		self.onClose.append(self._inchis)

	# ------------------------------------------------------------------ randurile
	def _randuri(self):
		s = self.setari
		titlu = lambda text: getConfigListEntry(text, ConfigNothing())
		lista = [getConfigListEntry(_("Stil gata făcut"), self.stil)]
		lista.append(titlu(_("LITERELE")))
		lista.append(getConfigListEntry(_("Fontul"), s.hds_stil_font))
		lista.append(getConfigListEntry(_("Grosimea literelor"), s.hds_grosime))
		lista.append(getConfigListEntry(_("Mărimea literelor"), s.hds_marime))
		lista.append(getConfigListEntry(_("Culoarea literelor"), s.hds_culoare))
		lista.append(titlu(_("CONTURUL")))
		lista.append(getConfigListEntry(_("Conturul literelor"), s.hds_contur))
		if s.hds_contur.value != "fara":
			lista.append(getConfigListEntry(_("Culoarea conturului"), s.hds_culoare_contur))
		lista.append(titlu(_("UMBRA")))
		lista.append(getConfigListEntry(_("Umbră sub litere"), s.hds_umbra))
		if s.hds_umbra.value:
			lista.append(getConfigListEntry(_("Culoarea umbrei"), s.hds_culoare_umbra))
			lista.append(getConfigListEntry(_("Direcția umbrei"), s.hds_directie_umbra))
			lista.append(getConfigListEntry(_("Distanța umbrei"), s.hds_distanta_umbra))
			lista.append(getConfigListEntry(_("Marginea umbrei"), s.hds_umbra_moale))
		lista.append(titlu(_("FUNDALUL")))
		lista.append(getConfigListEntry(_("Fundal în spatele rândurilor"), s.hds_fundal))
		if s.hds_fundal.value != "niciunul":
			lista.append(getConfigListEntry(_("Culoarea fundalului"), s.hds_culoare_fundal))
			lista.append(getConfigListEntry(_("Opacitatea fundalului"), s.hds_opacitate_fundal))
		lista.append(titlu(_("AȘEZAREA")))
		lista.append(getConfigListEntry(_("Înălțimea față de marginea de jos"), s.hds_jos))
		lista.append(getConfigListEntry(_("Distanța dintre rânduri"), s.hds_spatiere))
		# numai cand are ce alege: fara serviciul OCR ramane doar „clara” (Components/HdsSubtitrariAspect.seAlegeMarireaDvb)
		if sa.seAlegeMarireaDvb(s):
			lista.append(titlu(_("SUBTITRĂRILE DVB")))
			lista.append(getConfigListEntry(_("Mărirea subtitrărilor DVB"), s.hds_marire_dvb))
			# contorul si limbile: si cand OCR-ul e cerut numai de traducerea subtitrarilor (marirea = clara)
			ocr = _ocr()
			if ocr is not None and _ocrLucreaza(ocr, s):
				lista.append(getConfigListEntry(_("Recunoașterea textului"), self.contorOcr))
				if _modeleOcr() is not None:
					lista.append(getConfigListEntry(_("Limbile recunoașterii"), self.limbiOcr))
		return lista

	def _facLista(self):
		"""Lista din nou, cu cursorul pe aceeasi setare."""
		curent = self["config"].getCurrent()
		lista = self._randuri()
		self["config"].list = lista
		self["config"].l.setList(lista)
		if curent is not None and len(curent) > 1:
			for i, rand in enumerate(lista):
				if rand[1] is curent[1]:
					self["config"].setCurrentIndex(i)
					self._ultimul = i
					break

	@staticmethod
	def _esteTitlu(rand):
		return rand is not None and len(rand) > 1 and isinstance(rand[1], ConfigNothing)

	def _sariPesteTitlu(self):
		"""Sus/jos nu se opreste pe titlurile grupelor: merge mai departe in aceeasi directie."""
		lista = self["config"]
		i = lista.getCurrentIndex()
		if self._esteTitlu(lista.getCurrent()):
			pas = 1 if i >= self._ultimul else -1
			j = i + pas
			if 0 <= j < len(lista.list):
				self._ultimul = i
				lista.setCurrentIndex(j)
				return
		self._ultimul = i
		self["ajutor"].setText(self._textAjutor())

	def _textAjutor(self):
		"""Sub lista: pe randul maririi DVB, ce face ea acum; pe contorul OCR, amanuntele lui; altfel ajutorul obisnuit."""
		rand = self["config"].getCurrent() if "config" in self else None
		if rand is not None and len(rand) > 1 and rand[1] is self.setari.hds_marire_dvb:
			text = sa.textNotaMarireDvb()
			ocr = _ocr()
			if self.setari.hds_marire_dvb.value != "ocr" and ocr is not None and _ocrLucreaza(ocr, self.setari):
				text += u" " + _("Recunoașterea textului lucrează și acum: o cere traducerea subtitrărilor.")
			return text
		if rand is not None and len(rand) > 1 and rand[1] is getattr(self, "contorOcr", None):
			ocr = _ocr()
			return ocr.textContorDetalii() if ocr is not None else u""
		if rand is not None and len(rand) > 1 and rand[1] is getattr(self, "limbiOcr", None):
			return _("OK deschide lista limbilor: cele din imagine, cele descărcate și cele care se pot descărca, cu "
				"mărimea fiecăreia.")
		return _("Stânga și dreapta schimbă valoarea, OK deschide lista. Fraza de jos arată "
			"subtitrările text așa cum vor fi.")

	# ------------------------------------------------------------------ contorul OCR
	@staticmethod
	def _textContor():
		ocr = _ocr()
		return ocr.textContorScurt() if ocr is not None else u""

	@staticmethod
	def _textLimbi():
		om = _modeleOcr()
		if om is None:
			return u""
		try:
			return om.textScurt()
		except Exception:
			return u""

	def _puneValoare(self, element, cheie, text):
		"""valoarea unui rand de citit (o singura alegere), schimbata numai cand difera"""
		if element.getText() != text:
			# setChoices tine descrierea veche cand valoarea ramane aceeasi; value= o citeste din nou
			element.setChoices([(cheie, text)], default=cheie)
			element.value = cheie
			for rand in self["config"].list:
				if rand[1] is element:
					self["config"].invalidate(rand)

	def _improspateazaContor(self):
		"""Textul randurilor OCR si, cand cursorul e pe unul, ajutorul, dupa contorul de acum (se schimba numai ce
		difera). Numarul limbilor se citeste numai cand randul lui se vede."""
		self._puneValoare(self.contorOcr, "contor", self._textContor())
		if any(rand[1] is self.limbiOcr for rand in self["config"].list):
			self._puneValoare(self.limbiOcr, "limbi", self._textLimbi())
		ajutor = self._textAjutor()
		if self["ajutor"].getText() != ajutor:
			self["ajutor"].setText(ajutor)

	def _contorLaZero(self):
		ocr = _ocr()
		if ocr is not None:
			ocr.puneContorulLaZero()
		self._improspateazaContor()

	def _randuriSchimbate(self, element):
		self._facLista()

	# ------------------------------------------------------------------ stilul gata facut
	def _stilAles(self, element):
		if self._inStil or element.value == sa.PERSONALIZAT:
			return
		self._inStil = True
		try:
			sa.aplicaStil(element.value)
		finally:
			self._inStil = False
		self._facLista()

	def _setareSchimbata(self, element):
		"""Dupa o setare schimbata de mana, randul „Stil gata făcut" arata stilul care se potriveste (sau Personalizat)."""
		if self._inStil:
			return
		stil = sa.stilCurent()
		if stil != self.stil.value:
			self._inStil = True
			try:
				self.stil.value = stil
			finally:
				self._inStil = False
			for rand in self["config"].list:
				if rand[1] is self.stil:
					self["config"].invalidate(rand)

	def _inchis(self):
		self._ceasContor.stop()
		for cheie in ("umbra", "fundal", "contur", "marire_dvb"):
			e = sa.element(cheie, self.setari)
			if self._randuriSchimbate in e.notifiers:
				e.notifiers.remove(self._randuriSchimbate)
		for e in self._toate:
			if self._setareSchimbata in e.notifiers:
				e.notifiers.remove(self._setareSchimbata)

	def _pornit(self):
		sa.aplica()
		self._arataFundalProba()
		self["proba"].arata(sa.textProba())
		self._ceasContor.start(CONTOR_MS, False)

	# ------------------------------------------------------------------ taste
	def keyLeft(self):
		if not self._esteTitlu(self["config"].getCurrent()):
			ConfigListScreen.keyLeft(self)

	def keyRight(self):
		if not self._esteTitlu(self["config"].getCurrent()):
			ConfigListScreen.keyRight(self)

	# ------------------------------------------------------------------ fundalul de proba
	def _arataFundalProba(self):
		for nume in ("fundal_deschis", "fundal_mediu"):
			if self._fundalProba:
				self[nume].show()
			else:
				self[nume].hide()
		self["key_yellow"].setText(_("Fără fundal de probă") if self._fundalProba else _("Fundal de probă"))

	def schimbaFundalProba(self):
		self._fundalProba = not self._fundalProba
		self._arataFundalProba()

	# ------------------------------------------------------------------ lista
	def lista(self):
		"""OK: la Da/Nu schimba valoarea; la celelalte deschide lista tuturor valorilor."""
		rand = self["config"].getCurrent()
		if rand is None or len(rand) < 2 or self._esteTitlu(rand):
			return
		element = rand[1]
		if element is self.contorOcr:
			self._contorLaZero()
			return
		if element is self.limbiOcr:
			from Screens.HdsOcrLimbi import HdsOcrLimbi
			self.session.openWithCallback(lambda *a: self._improspateazaContor(), HdsOcrLimbi)
			return
		if element is self.setari.hds_umbra:
			element.value = not element.value
			self["config"].invalidateCurrent()
			return
		alegeri = [(descriere, valoare) for valoare, descriere in element.choices.choices]
		valori = [valoare for descriere, valoare in alegeri]
		curenta = valori.index(element.value) if element.value in valori else 0
		from Screens.ChoiceBox import ChoiceBox
		self._inLista = element
		self.session.openWithCallback(self._alesDinLista, ChoiceBox, title=rand[0], list=alegeri, selection=curenta)

	def _alesDinLista(self, ales):
		element = getattr(self, "_inLista", None)
		self._inLista = None
		if ales is None or element is None:
			return
		element.value = ales[1]
		self["config"].invalidateCurrent()

	def valoriImplicite(self):
		"""Albastru: toate valorile de la inceput (se vad pe loc; se pastreaza numai cu Salvează)."""
		sa.implicite()
		self._facLista()
		for rand in self["config"].list:
			self["config"].invalidate(rand)

	# ------------------------------------------------------------------ salvare / anulare
	def salveaza(self):
		for element in self._toate:
			element.save()
		configfile.save()
		sa.aplica()
		# fara True: meniul (Screens/Menu.py, menuClosed) ar inchide atunci toate meniurile, nu numai ecranul
		self.close()

	def anuleaza(self):
		with sa.oSinguraAplicare():
			for element in self._toate:
				element.cancel()
		self.close(False)
