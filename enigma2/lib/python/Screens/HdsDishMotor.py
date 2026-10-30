# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsDishMotor.py - ce se vede pe televizor cat timp se roteste antena.
#
# Inlocuieste chenarul mic din stanga sus (Screens/Dish.py, o singura poza care clipeste) cu un panou care
# arata: directia, de unde pleaca si unde merge (grade si numele satelitilor), pozitia curenta estimata,
# cat mai are de mers, o bara de progres si o antena desenata care se roteste odata cu motorul.
#
# Toate cifrele vin din starea adevarata a motorului (Components/HdsMotorStare.py, care le ia din
# eDVBSatelliteEquipmentControl). Pozitia din timpul mersului NU e raportata de niciun motor, deci e
# estimata intre plecare si sosire si scrie pe ecran „estimat". Nimic nu e o animatie oarba.
#
# Desenul e facut cu eCanvas (Components/Sources/CanvasSource.py + Renderer/Canvas.py) si formele netezite din nucleu
# (lib/gdi/desennetezit.cpp: linii, arce, inele, cercuri si poligoane cu margini netede, fara patratele): fara nicio
# poza noua in imagine. Skinul HDSatelit nu se atinge din acest fisier;
# ecranul isi poarta skinul propriu, inline, scalat cu Tools/ScaledSkin.py ca celelalte ecrane proprii.
#
# ecranul „Rotirea antenei" (HdsDishMotorEcran) primeste comenzile DiSEqC 1.2
# (Components/HdsMotorComenzi.py) intr-o banda sub panou; panoul de sus ramane cel de pana acum. Panoul automat sta
# ascuns cat e deschis ecranul (altfel acelasi desen ar aparea de doua ori), iar cand tinta unei miscari nu se stie
# (pas, miscare fara oprire) se deseneaza sageata directiei in loc de arcul vechi ramas pe panza.
#
# satelitii sunt puncte pe bolta, plecarea
# (violet) si tinta (aurie) mai mari si cu gradele scrise langa ele, antena lata in centru care se roteste, raza
# semnalului un con ascutit la satelit si lat la antena. Aceeasi forma are desenul SVG din pagina web /motor.

import math

import re

from .Screen import Screen
from .ChoiceBox import ChoiceBox
from .InputBox import InputBox
from .MessageBox import MessageBox
from Components.ActionMap import ActionMap
from Components.config import config
from Components.Input import Input
from Components.Sources.CanvasSource import CanvasSource
from Components.Sources.StaticText import StaticText
from Components.Label import Label
from Components.HdsMotorStare import gradeText, secundeText, stareMotor, panou_automat_oprit, panouAutomatAscuns, satelitiPeArc, istoricTinta
from Components import HdsGrade
from Components import HdsMarireText as MT
from Tools.ScaledSkin import LAYOUT_WIDTH, scaledSkin

from enigma import eTimer, getDesktop, RT_HALIGN_CENTER, RT_HALIGN_LEFT, RT_HALIGN_RIGHT, RT_VALIGN_CENTER

# cat de des se redeseneaza. Motorul merge cu ~0,5 grade pe secunda, deci 4 cadre pe secunda sunt deja line;
# mai des ar incarca receptorul degeaba (masurat in emulator).
MS_IN_MISCARE = 500
# cat de des ne uitam daca a inceput vreo miscare, cat timp ecranul e ascuns
MS_IN_ASTEPTARE = 1000
# dupa sosire bara si antena ajung lin la capat in ~1,2 s (Components/HdsMotorViteza.ALUNECARE_S): atunci mai des,
# ca trecerea sa se vada lina si nu in doi pasi
MS_IN_ALUNECARE = 200
# cat timp ramane in banda un mesaj al comenzilor (erorile raman pana la urmatoarea comanda)
MESAJ_S = 8

# panza (coordonate in interiorul ei, la latimea de asezare 1280). Forma:
# satelitii sunt puncte pe bolta, de alta culoare decat ea si putin mai groase; plecarea si tinta au fiecare culoarea
# lor si sunt putin mai mari, cu gradele scrise langa ele; antena lata sta in centru si se roteste; raza semnalului e un
# con ascutit la satelit si lat la antena. Centrul si raza boltii sunt alese ca talerul intors orizontal sa nu atinga
# bara de jos, iar etichetele de deasupra boltii sa incapa in panza. Aceleasi cifre are desenul SVG din pagina web
# /motor (Plugins/Extensions/HdsWebControl/antena_web.py, functia deseneaza), ca sa arate la fel.
PANZA_L, PANZA_I = 860, 250
CENTRU_X, CENTRU_Y = 430, 192
RAZA = 156
MARGINE_GRADE = 4.0          # cat spatiu lasam in stanga si in dreapta capetelor drumului
# antena: talerul e un arc gros din cercul cu raza TALER_RAZA, cu mijlocul la TALER_DEPARTE de butuc, deschis cu
# TALER_DESCHIDERE grade de o parte si de alta a axei; LNB-ul sta in focar, la jumatatea razei, in fata talerului
TALER_DEPARTE = 16
TALER_RAZA = 40
TALER_DESCHIDERE = 50.0
TALER_GROS = 8
# punctele de pe bolta (raze) si etichetele cu gradele plecarii si ale tintei
PUNCT_SATELIT = 4.5
PUNCT_PLECARE = 6.5
PUNCT_TINTA = 7.0
ETICHETA_L, ETICHETA_I = 86, 24
ETICHETA_FONT = 19
# bara de progres: o capsula sub antena
BARA_Y, BARA_GROS = 235, 12

FOND = 0x101820
ARC = 0x2d4356
ARC_FACUT = 0x38b6ff
SATELIT = 0x6f8ba3           # ceilalti sateliti de pe bolta
PLECARE = 0xb99cff
TINTA = 0xffc250
TINTA_INEL = 0x80ffc250      # octetul de sus e transparenta (0 = opac, ca in skin): inelul din jurul tintei
ANTENA = 0xf2f6fa
BRAT = 0xbfd4e6
BARA_FOND = 0x1b2836
BARA = 0x38b6ff
BARA_GATA = 0x4ad991
# raza semnalului, doua straturi cu varful in acelasi loc: cel lat, mai sters, pana la marginile talerului, si cel
# ingust, mai aprins, pana in mijlocul lui. Albastra cat merge antena, aurie cand a ajuns pe tinta.
CON_MERS = (0xc038b6ff, 0x9038b6ff)
CON_SOSIT = (0xb8ffc250, 0x80ffc250)


def _parte(jos, sus, grade):
	"""fractia din drum: 0 = capatul din stanga (vestul), 1 = cel din dreapta (estul)"""
	parte = 0.5 if sus <= jos else (grade - jos) / (sus - jos)
	return min(1.0, max(0.0, parte))


def _unghi(parte):
	"""unghiul pe ecran, in grade, ca la eCanvas si ca in SVG (0 = dreapta, pozitiv in sensul acelor de ceas cu y in
	jos): 180 = vest (stanga), 270 = sus, 360 = est (dreapta)"""
	return 180.0 + 180.0 * parte


def _pe(unghi, raza, x, y):
	a = math.radians(unghi)
	return (x + raza * math.cos(a), y + raza * math.sin(a))


def gradeScurt(grade):
	"""13.0 -> „13,0°E”, -5.0 -> „5,0°V” („5.0°W” in engleza): eticheta de langa punctul de pe bolta, in limba
	meniului (Components/HdsGrade.py); pagina web primeste aceeasi eticheta (HdsMotorStare.stareJson, la_scurt)"""
	return HdsGrade.pozitie(grade)


def cutieEticheta(unghi):
	"""(stanga, sus, aliniere) pentru eticheta punctului de la `unghi`, la latimea de asezare: lipita de bolta pe
	dinafara, intinsa spre stanga in partea de vest, spre dreapta in partea de est, centrata sus; nu iese din panza"""
	x, y = _pe(unghi, RAZA + 13, CENTRU_X, CENTRU_Y)
	a = math.radians(unghi)
	stanga = x + math.cos(a) * ETICHETA_L / 2.0 - ETICHETA_L / 2.0
	sus = y + math.sin(a) * ETICHETA_I / 2.0 - ETICHETA_I / 2.0
	stanga = min(max(0.0, stanga), float(PANZA_L - ETICHETA_L))
	sus = min(max(0.0, sus), float(PANZA_I - ETICHETA_I))
	aliniere = "dreapta" if math.cos(a) < -0.3 else ("stanga" if math.cos(a) > 0.3 else "centru")
	return stanga, sus, aliniere


def seSuprapun(a, b, spatiu=4):
	return not (a[0] + ETICHETA_L + spatiu <= b[0] or b[0] + ETICHETA_L + spatiu <= a[0] or
		a[1] + ETICHETA_I + spatiu <= b[1] or b[1] + ETICHETA_I + spatiu <= a[1])


def deseneazaRotirea(panza, factor, de_la, la, acum, procent, a_ajuns, secunde_trecute, sateliti=(), antena=True,
		plecare=True, sosit=False, eticheta=None):
	"""Panza unei miscari cu tinta stiuta, cu formele netezite din nucleu (CanvasSource.drawLine/drawArc/drawRing/
	fillCircle/fillPolygon, desenate in C++ de lib/gdi/desennetezit.cpp), dupa fondul pus de ecran. Ordinea: raza
	semnalului, bolta, drumul facut, ceilalti sateliti, plecarea si tinta, antena, etichetele, bara.
	`factor` trece de la latimea de asezare 1280 la pixelii panzei, fara rotunjire (formele primesc zecimale).
	`acum` = unde e indreptata antena (estimat); `antena` = False cand pozitia nu se stie: atunci nu se deseneaza nici
	antena, nici raza. `plecare` = False cand plecarea nu se stie (nu se pune niciun punct violet). `sosit` = antena a
	ajuns cu adevarat pe tinta (raza se face aurie). `sateliti` = gradele celorlalti sateliti din lista tunerului.
	`eticheta(x, y, latime, inaltime, culoare, text, aliniere)` scrie un text (None = fara etichete).
	Intoarce cate forme s-au pus in coada."""
	g = lambda v: v * factor
	cx, cy = g(CENTRU_X), g(CENTRU_Y)
	jos = min(de_la, la) - MARGINE_GRADE
	sus = max(de_la, la) + MARGINE_GRADE
	u_de_la, u_la, u_acum = _unghi(_parte(jos, sus, de_la)), _unghi(_parte(jos, sus, la)), _unghi(_parte(jos, sus, acum))
	n = 0

	# raza semnalului: varful pe bolta, acolo unde e indreptata antena; baza pe gura talerului. Inaintea boltii, ca bolta
	# si punctele sa ramana curate peste ea.
	if antena:
		centru_taler = _pe(u_acum, g(TALER_DEPARTE + TALER_RAZA), cx, cy)
		varf = _pe(u_acum, g(RAZA), cx, cy)
		for culoare, deschidere in zip(CON_SOSIT if sosit else CON_MERS, (TALER_DESCHIDERE, TALER_DESCHIDERE * 0.45)):
			panza.fillPolygon([varf, _pe(u_acum + 180.0 - deschidere, g(TALER_RAZA), *centru_taler),
				_pe(u_acum + 180.0 + deschidere, g(TALER_RAZA), *centru_taler)], culoare)
			n += 1

	# bolta: tot drumul subtire, apoi bucata facuta deja, mai groasa si aprinsa
	panza.drawArc(cx, cy, g(RAZA), g(4), 180.0, 180.0, ARC, 1)
	n += 1
	mic, mare = sorted((u_de_la, u_acum))
	if antena and plecare and mare - mic > 0.05:
		panza.drawArc(cx, cy, g(RAZA), g(6), mic, mare - mic, ARC_FACUT, 1)
		n += 1

	# ceilalti sateliti din lista tunerului: puncte de alta culoare decat bolta, putin mai groase decat ea
	for grade in sateliti:
		if jos <= grade <= sus:
			x, y = _pe(_unghi(_parte(jos, sus, grade)), g(RAZA), cx, cy)
			panza.fillCircle(x, y, g(PUNCT_SATELIT), SATELIT)
			n += 1
	# plecarea (violet) si tinta (aurie, cu un inel in jur): mai mari decat punctele obisnuite
	if plecare:
		x, y = _pe(u_de_la, g(RAZA), cx, cy)
		panza.fillCircle(x, y, g(PUNCT_PLECARE), PLECARE)
		n += 1
	x, y = _pe(u_la, g(RAZA), cx, cy)
	panza.drawRing(x, y, g(PUNCT_TINTA + 4), g(1.6), TINTA_INEL)
	panza.fillCircle(x, y, g(PUNCT_TINTA), TINTA)
	n += 2

	if antena:
		n += _deseneazaAntena(panza, factor, u_acum)

	# etichetele: gradele plecarii si ale tintei, pe dinafara boltii, in culoarea punctului. Cand plecarea e prea
	# aproape de tinta, ramane numai eticheta tintei.
	if eticheta is not None:
		cutie_la = cutieEticheta(u_la)
		cutii = [(cutie_la, TINTA, gradeScurt(la))]
		if plecare:
			cutie_de_la = cutieEticheta(u_de_la)
			if not seSuprapun(cutie_de_la, cutie_la):
				cutii.append((cutie_de_la, PLECARE, gradeScurt(de_la)))
		for (stanga, sus_e, aliniere), culoare, text in cutii:
			eticheta(g(stanga), g(sus_e), g(ETICHETA_L), g(ETICHETA_I), culoare, text, aliniere)
			n += 1

	n += deseneazaBara(panza, factor, procent, a_ajuns, secunde_trecute)
	return n


def _deseneazaAntena(panza, factor, unghi):
	"""antena rotita spre `unghi`: stalpul si talpa (fixe), bratul scurt, talerul lat (arc gros concav spre cer),
	bratul LNB-ului cu doua sarme din marginile talerului, LNB-ul si butucul"""
	g = lambda v: v * factor
	cx, cy = g(CENTRU_X), g(CENTRU_Y)
	a = math.radians(unghi)
	ux, uy = math.cos(a), math.sin(a)          # spre cer
	nx, ny = -uy, ux                            # perpendicular pe axa talerului
	# stalpul si talpa, sub butuc: nu se rotesc
	panza.drawLine(cx, cy, cx, cy + g(26), g(6), BRAT)
	panza.fillPolygon([(cx - g(20), cy + g(32)), (cx + g(20), cy + g(32)), (cx + g(9), cy + g(22)), (cx - g(9), cy + g(22))], BRAT)
	# bratul pana la mijlocul talerului, apoi talerul: arc din cercul cu centrul in fata lui, pe axa
	vx, vy = cx + g(TALER_DEPARTE) * ux, cy + g(TALER_DEPARTE) * uy
	panza.drawLine(cx, cy, vx, vy, g(6), BRAT)
	fx, fy = vx + g(TALER_RAZA) * ux, vy + g(TALER_RAZA) * uy
	panza.drawArc(fx, fy, g(TALER_RAZA), g(TALER_GROS), unghi + 180.0 - TALER_DESCHIDERE, 2 * TALER_DESCHIDERE, ANTENA, 1)
	# bratul LNB-ului pana in focar, plus doua sarme subtiri din marginile talerului
	focar_x, focar_y = vx + g(TALER_RAZA / 2.0) * ux, vy + g(TALER_RAZA / 2.0) * uy
	panza.drawLine(vx, vy, focar_x, focar_y, g(2.5), BRAT)
	for semn in (-1, 1):
		mx, my = _pe(unghi + 180.0 + semn * (TALER_DESCHIDERE - 5), g(TALER_RAZA), fx, fy)
		panza.drawLine(mx, my, focar_x, focar_y, g(1.4), BRAT)
	# LNB-ul: un dreptunghi mic cu colturile taiate, intors spre taler
	lnb = []
	for lung, lat in ((-4, -5), (3, -5), (5, -3), (5, 3), (3, 5), (-4, 5)):
		lnb.append((focar_x + g(lung) * ux + g(lat) * nx, focar_y + g(lung) * uy + g(lat) * ny))
	panza.fillPolygon(lnb, TINTA)
	# butucul si un inel subtire in jurul lui
	panza.fillCircle(cx, cy, g(8), ANTENA)
	panza.drawRing(cx, cy, g(11.5), g(2), ARC_FACUT)
	return 10


def deseneazaFaraTinta(panza, factor, directie, procent, a_ajuns, secunde_trecute):
	"""Tinta nu se stie (pas, miscare fara oprire, pozitie memorata fara satelit legat): bolta goala si, daca se stie, o
	sageata curbata pe directia miscarii (estul in dreapta, ca pe bolta). Nicio antena si niciun satelit inventat."""
	g = lambda v: v * factor
	cx, cy = g(CENTRU_X), g(CENTRU_Y)
	panza.drawArc(cx, cy, g(RAZA), g(4), 180.0, 180.0, ARC, 1)
	n = 1
	if directie in ("est", "vest"):
		semn = 1.0 if directie == "est" else -1.0
		r = g(RAZA * 0.62)
		inceput, capat = 270.0 - semn * 32.0, 270.0 + semn * 32.0
		panza.drawArc(cx, cy, r, g(7), inceput, capat - inceput, ARC_FACUT, 1)
		# varful sagetii, in capatul dinspre directie: un triunghi cu varful mai departe pe cerc
		panza.fillPolygon([_pe(capat + semn * 9.0, r, cx, cy), _pe(capat - semn * 1.0, r - g(12), cx, cy),
			_pe(capat - semn * 1.0, r + g(12), cx, cy)], ARC_FACUT)
		n += 2
	return n + deseneazaBara(panza, factor, procent, a_ajuns, secunde_trecute)


def deseneazaBara(panza, factor, procent, a_ajuns, secunde_trecute):
	"""bara de progres: o capsula (linie groasa cu capete rotunde), fondul plus bucata facuta"""
	g = lambda v: v * factor
	gros = g(BARA_GROS)
	y = g(BARA_Y)
	x0, x1 = gros / 2 + g(1), g(PANZA_L) - gros / 2 - g(1)
	panza.drawLine(x0, y, x1, y, gros, BARA_FOND)
	n = 1
	if procent < 0:
		# nu stim cat s-a facut: o bucata scurta care pluteste, nu un procent inventat
		pas = (secunde_trecute * 140) % (PANZA_L + 160) - 160
		inceput, sfarsit = max(x0, g(max(0.0, pas))), min(x1, g(min(float(PANZA_L), pas + 160)))
		if sfarsit - inceput > 0.5:
			panza.drawLine(inceput, y, sfarsit, y, gros, BARA)
			n += 1
	else:
		lung = (x1 - x0) * min(100.0, procent) / 100.0
		if lung > 0.5:
			panza.drawLine(x0, y, x0 + lung, y, gros, BARA_GATA if a_ajuns else BARA)
			n += 1
	return n


def _fontHds(nume):
	"""fontul HD Satelit cu rolul `nume` sub un skin strain (skin.fontHds); cu HDSatelit ales, `nume`
	"""
	try:
		import skin
		return skin.fontHds(nume)
	except Exception:
		return nume


class HdsDishMotor(Screen):
	skinName = ["HdsDishMotor"]

	SKIN = """
	<screen name="HdsDishMotor" flags="wfNoBorder" position="center,center" size="900,478" zPosition="100" backgroundColor="#101820" title="Antena se roteste">
		<eLabel position="0,0" size="900,478" backgroundColor="#0b1219" zPosition="-2" />
		<eLabel position="0,0" size="900,3" backgroundColor="#38b6ff" zPosition="-1" />
		<widget source="titlu" render="Label" position="20,14" size="860,40" font="Regular;30" foregroundColor="#ffffff" backgroundColor="#0b1219" transparent="1" halign="center" valign="center" noWrap="1" />
		<widget source="canvas" render="Canvas" position="20,60" size="860,250" />
		<widget source="plecare" render="Label" position="20,318" size="280,64" font="Regular;22" foregroundColor="#b99cff" backgroundColor="#0b1219" transparent="1" halign="left" valign="top" />
		<widget source="curent" render="Label" position="310,318" size="280,64" font="Regular;22" foregroundColor="#38b6ff" backgroundColor="#0b1219" transparent="1" halign="center" valign="top" />
		<widget source="tinta" render="Label" position="600,318" size="280,64" font="Regular;22" foregroundColor="#ffc250" backgroundColor="#0b1219" transparent="1" halign="right" valign="top" />
		<widget source="ramas" render="Label" position="20,388" size="860,30" font="Regular;24" foregroundColor="#d7e3ec" backgroundColor="#0b1219" transparent="1" halign="center" valign="center" noWrap="1" />
		<widget source="detaliu" render="Label" position="20,420" size="860,26" font="Regular;16" foregroundColor="#6f8ba3" backgroundColor="#0b1219" transparent="1" halign="center" valign="center" noWrap="1" />
		<widget source="viteza" render="Label" position="20,446" size="860,26" font="Regular;18" foregroundColor="#8fb3cc" backgroundColor="#0b1219" transparent="1" halign="center" valign="center" noWrap="1" />
	</screen>
	"""

	def __init__(self, session):
		self.skin = scaledSkin(self.SKIN)
		Screen.__init__(self, session)

		self["canvas"] = CanvasSource()
		self["titlu"] = StaticText("")
		self["plecare"] = StaticText("")
		self["curent"] = StaticText("")
		self["tinta"] = StaticText("")
		self["ramas"] = StaticText("")
		self["detaliu"] = StaticText("")
		self["viteza"] = StaticText("")
		# panoul nu are nicio ActionMap: nu prinde nicio tasta, deci zapul si telecomanda merg exact ca pana acum

		# panza primeste din skin marimea deja scalata, deci si desenul se scaleaza cu acelasi factor
		try:
			self._factor = float(getDesktop(0).size().width()) / LAYOUT_WIDTH
		except Exception:
			self._factor = 1.0
		if self._factor <= 0:
			self._factor = 1.0

		self._vazut = False
		self._pornit = False
		# `config.usage.showdish` hotaraste numai daca panoul se arata; ceasul bate oricum, ca mutarile
		# motorului sa se invete si cand panoul e oprit (Components/HdsMotorViteza.py)
		self._arata = True
		self._cheie = None
		self._texte = {}
		self._sateliti_cheie = None
		self._sateliti = []
		# etichetele cu gradele de langa plecare si tinta; fara font desenul merge si fara ele. Fontul e pus din cod,
		# deci urmeaza Marimea textului (Components/HdsMarireText), iar caseta lui creste in _eticheta
		try:
			self._font = MT.fontCod(_fontHds("Regular"), max(1, int(round(ETICHETA_FONT * self._factor))))
		except Exception:
			self._font = None

		self._ceas = eTimer()
		try:
			self._ceas.callback.append(self._bate)
		except AttributeError:
			self._ceas_conn = self._ceas.timeout.connect(self._bate)

		# pozitia antenei tinuta minte intre porniri se da inapoi nucleului o singura data, aici: panoul automat e
		# creat de InfoBar (InfoBarGenerics.py:52) inaintea primului zap (ChannelSelection.py:1241-1243)
		try:
			from Components.HdsMotorPozitie import restaureaza
			restaureaza()
		except Exception as e:
			print("[HdsMotor] pozitia motorului nu a putut fi redata: %r" % (e,))

		config.usage.showdish.addNotifier(self._setareSchimbata, initial_call=False)
		self.onClose.append(self._laInchidere)
		self._setareSchimbata(config.usage.showdish)

	# ------------------------------------------------------------------ pornire / oprire

	def _setareSchimbata(self, element):
		"""setarea veche `config.usage.showdish` ramane respectata: oprita = nu apare nimic. Ceasul bate insa si atunci,
		o data pe secunda, numai ca motorul sa-si invete viteza din fiecare mutare (altfel mutarile facute
		cu panoul oprit s-ar pierde); nimic nu se arata si nimic nu se deseneaza.
		Nu ne uitam si daca vreun tuner are motor: vechiul Dish.py se uita si el necontenit la `isRotorMoving`,
		iar o conditie citita o singura data la pornire ar lasa fara panou pe cine tocmai si-a configurat
		motorul si a schimbat canalul, pana la urmatoarea repornire. Costul in repaus e o intrebare pe secunda."""
		self._arata = bool(element.value)
		if not self._arata and self._vazut:
			self._vazut = False
			self.hide()
		self._porneste()

	def _porneste(self):
		if not self._pornit:
			self._pornit = True
			self._ceas.start(MS_IN_ASTEPTARE, True)

	def _laInchidere(self):
		self._ceas.stop()
		try:
			config.usage.showdish.notifiers.remove(self._setareSchimbata)
		except Exception:
			pass

	# ------------------------------------------------------------------ bataia ceasului

	def _bate(self):
		if not self._pornit:
			return
		if panouAutomatAscuns():
			# „Rotirea antenei" sau „Gasire semnal" e deschis si arata el miscarea (si citeste starea, deci si invata):
			# panoul automat sta ascuns
			if self._vazut:
				self._vazut = False
				self.hide()
			self._ceas.start(MS_IN_ASTEPTARE, True)
			return
		stare = stareMotor()
		if not self._arata:
			# `showdish` oprit: starea s-a citit numai ca sa se invete viteza; nimic pe ecran
			self._ceas.start(MS_IN_ASTEPTARE, True)
			return
		if stare["activ"]:
			if not self._vazut:
				self._vazut = True
				self._cheie = None
				self._texte = {}
				self.show()
			self._scrie(stare)
			self._deseneaza(stare)
			self._ceas.start(MS_IN_ALUNECARE if stare.get("alunecare") else MS_IN_MISCARE, True)
		else:
			if self._vazut:
				self._vazut = False
				self.hide()
			self._ceas.start(MS_IN_ASTEPTARE, True)

	# ------------------------------------------------------------------ textele

	def _pune(self, nume, text):
		"""scrie in eticheta numai daca s-a schimbat ceva: altfel enigma2 reaseaza degeaba textul"""
		if self._texte.get(nume) != text:
			self._texte[nume] = text
			self[nume].setText(text)

	def _scrie(self, stare):
		self._pune("titlu", stare["stare_text"])

		plecare = gradeText(stare["de_la_grade"])
		if stare["de_la_nume"]:
			plecare = "%s\n%s" % (plecare, stare["de_la_nume"])
		self._pune("plecare", "%s\n%s" % (_("De la"), plecare))

		tinta = gradeText(stare["la_grade"])
		if stare["la_nume"]:
			tinta = "%s\n%s" % (tinta, stare["la_nume"])
		self._pune("tinta", "%s\n%s" % (_("Pana la"), tinta))

		if stare.get("curent_text"):
			# dupa o miscare manuala nici plecarea, nici tinta nu mai spun unde e antena (revizia m2)
			self._pune("curent", stare["curent_text"])
		elif stare["pozitie_grade"] is None:
			self._pune("curent", _("Pozitia de plecare nu e cunoscuta"))
		else:
			self._pune("curent", "%s\n%s" % (_("Acum (estimat)"), gradeText(stare["pozitie_grade"])))

		if stare.get("ramas_text") and not stare.get("manual"):
			# plecarea nestiuta sau timpul maxim trecut fara semnal (Components/HdsMotorStare._faptele):
			# numai ce se stie, acelasi rand ca in pagina web
			self._pune("ramas", stare["ramas_text"])
		elif stare["a_ajuns"]:
			# `manual` = miscarea a terminat-o o comanda (pas, oprire, plafon), nu sosirea vazuta de nucleu: tinta nu e
			# locul unde a ramas antena
			if stare["la_grade"] is not None and not stare.get("manual"):
				self._pune("ramas", _("Drumul s-a terminat la %s") % gradeText(stare["la_grade"]))
			else:
				self._pune("ramas", _("Motorul s-a oprit"))
		elif stare.get("oprire_automata_s") is not None and stare.get("manual"):
			self._pune("ramas", _("Oprire singură în %s") % secundeText(stare["oprire_automata_s"]))
		elif stare["grade_ramase"] is None:
			self._pune("ramas", _("Motorul merge, timpul nu se poate estima"))
		elif stare.get("intarziat") or stare["secunde_ramase"] is None:
			# timpul prezis a trecut: antena e aproape, nucleul asteapta semnalul pe tinta; nici „0 s”, nici un timp inventat
			self._pune("ramas", _("Aproape gata, se așteaptă semnalul pe satelitul nou"))
		else:
			self._pune("ramas", _("Mai are de mers %s grade, aproximativ %s") % (
				HdsGrade.numar(stare["grade_ramase"], 1), secundeText(stare["secunde_ramase"])))

		bucati = []
		if stare["comanda_text"]:
			bucati.append(_("comanda %s") % stare["comanda_text"])
		if stare["unghi_motor"] is not None:
			bucati.append(_("unghi motor %s") % gradeText(stare["unghi_motor"]))
		if stare["grade_total"] is not None:
			if stare.get("unghi_real"):
				# gradele de motor (unghiul orar USALS), nu diferenta pozitiilor orbitale
				bucati.append(_("rotire %s grade") % HdsGrade.numar(stare["grade_total"], 1))
			else:
				bucati.append(_("drum total %s grade") % HdsGrade.numar(stare["grade_total"], 1))
		bucati.append(_("tuner %d") % (stare["slot"] + 1))
		self._pune("detaliu", "   |   ".join(bucati))
		# randul de jos: viteza si, cand incape, ultimul semnal prins pe pozitia tinta (Components/HdsIstoricSemnal.py)
		viteza = stare.get("viteza_text") or ""
		istoric = istoricTinta(stare)
		if istoric and len(viteza) + len(istoric) <= 90:
			viteza = "%s   |   %s" % (viteza, istoric) if viteza else istoric
		self._pune("viteza", viteza)

	# ------------------------------------------------------------------ desenul

	def _s(self, valoare):
		"""coordonata de asezare (latime 1280) -> coordonata reala pe panza scalata de skin"""
		return int(round(valoare * self._factor))

	def _deseneaza(self, stare):
		"""Panza se redeseneaza intreaga la fiecare cadru: `CanvasSource.clear()` porneste o secventa noua, iar
		randarea (Renderer/Canvas.py) reia lista de la capat. Formele sunt netezite (deseneazaRotirea de mai sus), vreo
		25 pe cadru, desenate in C++ pe firul gRC; timpii au fost masurati in emulator.
		O stergere partiala nu se poate: zona maturata de antena si de raza e un sector de cerc."""
		panza = self["canvas"]
		de_la, la = stare["de_la_grade"], stare["la_grade"]
		acum = stare["pozitie_grade"]
		if la is None:
			# tinta nu se stie (pas, miscare fara oprire, pozitie memorata fara satelit legat): pana acum panza ramanea
			# cu arcul miscarii de dinainte; acum arata numai directia, daca se stie
			self._deseneazaFaraTinta(panza, stare)
			return
		plecare = de_la is not None
		if de_la is None:
			de_la = la
		# pozitia nu se stie din cauza unei comenzi (miscare manuala, oprire pe drum; HdsMotorStare._pozitiaNestiuta) sau
		# pentru ca plecarea nu se stie (dupa pornirea receptorului): antena si raza nu se deseneaza nicaieri pe arc, altfel
		# ar parea ca a ajuns pe tinta. Ca in pagina web, care nu o deseneaza cand pozitia lipseste.
		fara_antena = acum is None
		if acum is None:
			acum = de_la

		panza.clear()
		panza.fill(0, 0, self._s(PANZA_L), self._s(PANZA_I), FOND)
		deseneazaRotirea(panza, self._factor, de_la, la, acum, stare["procent"], stare["a_ajuns"],
			stare["secunde_trecute"], sateliti=self._satelitiPeArc(stare), antena=not fara_antena, plecare=plecare,
			sosit=bool(stare["a_ajuns"]) and not stare.get("manual") and not stare.get("fara_semnal_la_sosire"),
			eticheta=self._eticheta if self._font is not None else None)
		panza.flush()

	def _deseneazaFaraTinta(self, panza, stare):
		panza.clear()
		panza.fill(0, 0, self._s(PANZA_L), self._s(PANZA_I), FOND)
		deseneazaFaraTinta(panza, self._factor, stare.get("directie"), stare["procent"], stare["a_ajuns"],
			stare["secunde_trecute"])
		panza.flush()

	def _eticheta(self, x, y, latime, inaltime, culoare, text, aliniere):
		"""gradele de langa un punct de pe bolta. Fondul dat textului e fondul panzei: textul se netezeste spre el si nu
		umple nimic in jur (eTextPara::blit scrie numai pixelii literelor). Cu textul marit caseta creste cat fontul: spre
		partea in care se intinde eticheta (dupa aliniere) si la fel in sus si in jos, fara sa iasa din panza."""
		orizontal = {"stanga": RT_HALIGN_LEFT, "dreapta": RT_HALIGN_RIGHT}.get(aliniere, RT_HALIGN_CENTER)
		l2, i2 = MT.inaltimeCod(int(round(latime))), MT.inaltimeCod(int(round(inaltime)))
		if (l2, i2) != (int(round(latime)), int(round(inaltime))):
			if aliniere == "dreapta":
				x -= l2 - latime
			elif aliniere != "stanga":
				x -= (l2 - latime) / 2.0
			y -= (i2 - inaltime) / 2.0
			x = min(max(0.0, x), float(max(0, self._s(PANZA_L) - l2)))
			y = min(max(0.0, y), float(max(0, self._s(PANZA_I) - i2)))
			latime, inaltime = l2, i2
		self["canvas"].writeText(int(round(x)), int(round(y)), int(round(latime)), int(round(inaltime)), culoare, FOND,
			self._font, text, orizontal | RT_VALIGN_CENTER)

	def _satelitiPeArc(self, stare):
		"""gradele celorlalti sateliti din lista tunerului (fara plecare si tinta). Lista se ia o data pe miscare, nu de
		doua ori pe secunda."""
		cheie = (stare["slot"], stare["de_la_orbital"], stare["la_orbital"])
		if self._sateliti_cheie != cheie:
			self._sateliti_cheie = cheie
			self._sateliti = [grade for orbital, grade in satelitiPeArc(stare["slot"])
				if orbital not in (stare["de_la_orbital"], stare["la_orbital"])]
		return self._sateliti


# eliberarea si tinerea sagetilor ajung si ele la hartile de taste (keymap.xml:616-624); dialogurile obisnuite nu le
# au, deci enigma2 scria „unknown action" in jurnal la fiecare Jos dintr-o lista. Ale noastre nu fac nimic cu ele.
TASTE_FARA_EFECT = ("leftUp", "rightUp", "upUp", "downUp", "leftRepeated", "rightRepeated", "upRepeated", "downRepeated")


def _fara_efect():
	pass


def _linisteste(ecran):
	harta = ecran.get("actions")
	if harta is not None:
		for nume in TASTE_FARA_EFECT:
			harta.actions.setdefault(nume, _fara_efect)


class HdsMotorAlegere(ChoiceBox):
	"""lista (sateliti, pozitii memorate, limite, tunere): ChoiceBox-ul imaginii, fara scurtaturi pe culori"""

	def __init__(self, session, **k):
		ChoiceBox.__init__(self, session, **k)
		self.skinName = ["ChoiceBox"]
		_linisteste(self)


class HdsMotorLimite(ChoiceBox):
	"""Fereastra „Limite”: comenzile, cu ce stie receptorul despre limite deasupra (ultima comanda trimisa) si
	dedesubt (cand s-a pus limita de est si cea de vest), in locul „description” al ChoiceBox-ului din skin."""

	def __init__(self, session, descriere="", **k):
		ChoiceBox.__init__(self, session, **k)
		self.skinName = ["ChoiceBox"]
		self["description"] = Label(descriere)
		self.setTitle(_("Limite"))
		self._titluLimite = k.get("title", "")
		self.onLayoutFinish.append(self._unRand)
		_linisteste(self)

	def _unRand(self):
		"""textul de sus pe un singur rand: cand nu incape, deruleaza (in caseta de doua randuri a skinului o stare lunga
		se rupea pe trei randuri si se taia, mai ales cu textul marit)"""
		try:
			self["text"].instance.setNoWrap(1)
			self["text"].setText("")
			self["text"].setText(self._titluLimite)
		except Exception as e:
			print("[HdsDishMotor] textul limitelor pe un rand: %r" % (e,))


class HdsMotorNumar(InputBox):
	"""numarul pozitiei memorate: InputBox-ul imaginii"""

	def __init__(self, session, **k):
		InputBox.__init__(self, session, **k)
		self.skinName = ["InputBox"]
		_linisteste(self)


class HdsMotorIntrebare(MessageBox):
	"""Intrebarea dinaintea comenzilor care suprascriu ceva in motor (memorare, limite). „Nu" e ales dinainte, iar
	tasta verde nu mai raspunde „Da": in orice MessageBox verde e alwaysOK (keymap.xml:579, MessageBox.py:120-121), iar
	in acest ecran verde e si „Mergi la satelit", deci din obisnuinta s-ar putea confirma oprirea limitelor dintr-o
	apasare (revizia m1). „Da" se alege cu Jos sau Dreapta, apoi OK."""

	def __init__(self, session, text):
		MessageBox.__init__(self, session, text, type=MessageBox.TYPE_YESNO, default=False)
		self.skinName = ["MessageBox"]
		_linisteste(self)

	def alwaysOK(self):
		pass


class HdsDishMotorEcran(HdsDishMotor):
	"""Acelasi panou, deschis de utilizator din meniu („Rotirea antenei"), plus comenzile motorului intr-o banda sub el.
	Ramane pe ecran si cand motorul sta. Toate comenzile trec prin Components/HdsMotorComenzi.py (acelasi loc ca pagina
	web); ecranul doar le cheama si arata ce spun. Tunerul se ia abia la prima comanda (cine deschide ecranul doar ca
	sa vada rotirea nu isi pierde programul) si se da inapoi la iesire, cu programul pus la loc."""
	skinName = ["HdsDishMotorEcran", "HdsDishMotor"]
	# POWER pe telecomanda: standby-ul e primit (mytest.py cere ALLOW_SUSPEND), iar standby-ul opreste
	# motorul, porneste limitele si da tunerul inapoi (revizia m3); fara asta POWER nu facea nimic cat e deschis ecranul
	ALLOW_SUSPEND = Screen.SUSPEND_STOPS

	SKIN = """
	<screen name="HdsDishMotorEcran" flags="wfNoBorder" position="center,center" size="900,662" zPosition="100" backgroundColor="#101820" title="Rotirea antenei">
		<eLabel position="0,0" size="900,662" backgroundColor="#0b1219" zPosition="-2" />
		<eLabel position="0,0" size="900,3" backgroundColor="#38b6ff" zPosition="-1" />
		<widget source="titlu" render="Label" position="20,14" size="860,40" font="Regular;30" foregroundColor="#ffffff" backgroundColor="#0b1219" transparent="1" halign="center" valign="center" noWrap="1" />
		<widget source="canvas" render="Canvas" position="20,60" size="860,250" />
		<widget source="plecare" render="Label" position="20,318" size="280,64" font="Regular;22" foregroundColor="#b99cff" backgroundColor="#0b1219" transparent="1" halign="left" valign="top" />
		<widget source="curent" render="Label" position="310,318" size="280,64" font="Regular;22" foregroundColor="#38b6ff" backgroundColor="#0b1219" transparent="1" halign="center" valign="top" />
		<widget source="tinta" render="Label" position="600,318" size="280,64" font="Regular;22" foregroundColor="#ffc250" backgroundColor="#0b1219" transparent="1" halign="right" valign="top" />
		<widget source="ramas" render="Label" position="20,388" size="860,30" font="Regular;24" foregroundColor="#d7e3ec" backgroundColor="#0b1219" transparent="1" halign="center" valign="center" noWrap="1" />
		<widget source="detaliu" render="Label" position="20,420" size="860,26" font="Regular;16" foregroundColor="#6f8ba3" backgroundColor="#0b1219" transparent="1" halign="center" valign="center" noWrap="1" />
		<widget source="viteza" render="Label" position="20,446" size="860,26" font="Regular;18" foregroundColor="#8fb3cc" backgroundColor="#0b1219" transparent="1" halign="center" valign="center" noWrap="1" />
		<eLabel position="20,476" size="860,2" backgroundColor="#1b2836" />
		<widget source="comenzi_stare" render="Label" position="20,486" size="420,28" font="Regular;21" foregroundColor="#d7e3ec" backgroundColor="#0b1219" transparent="1" halign="left" valign="center" noWrap="1" />
		<widget source="limite" render="Label" position="450,486" size="430,28" font="Regular;21" foregroundColor="#d7e3ec" backgroundColor="#0b1219" transparent="1" halign="right" valign="center" noWrap="1" />
		<widget source="limite_oprite" render="Label" position="20,486" size="860,28" font="Regular;21" foregroundColor="#ff6b6b" backgroundColor="#0b1219" transparent="1" halign="right" valign="center" noWrap="1" />
		<widget source="mesaj" render="Label" position="20,516" size="860,52" font="Regular;21" foregroundColor="#ffc250" backgroundColor="#0b1219" transparent="1" halign="left" valign="top" />
		<widget source="semnal" render="Label" position="20,570" size="860,28" font="Regular;21" foregroundColor="#4ad991" backgroundColor="#0b1219" transparent="1" halign="left" valign="center" noWrap="1" />
		<widget source="ajutor" render="Label" position="20,600" size="860,24" font="Regular;17" foregroundColor="#6f8ba3" backgroundColor="#0b1219" transparent="1" halign="left" valign="center" noWrap="1" />
		<widget name="bara_rosu" position="20,632" size="6,22" backgroundColor="#e53935" />
		<widget source="key_red" render="Label" position="32,629" size="200,28" font="Regular;19" foregroundColor="#d7e3ec" backgroundColor="#0b1219" transparent="1" halign="left" valign="center" noWrap="1" />
		<widget name="bara_verde" position="240,632" size="6,22" backgroundColor="#43a047" />
		<widget source="key_green" render="Label" position="252,629" size="200,28" font="Regular;19" foregroundColor="#d7e3ec" backgroundColor="#0b1219" transparent="1" halign="left" valign="center" noWrap="1" />
		<widget source="key_yellow" render="Label" position="472,629" size="200,28" font="Regular;19" foregroundColor="#d7e3ec" backgroundColor="#0b1219" transparent="1" halign="left" valign="center" noWrap="1" />
		<widget name="bara_galben" position="460,632" size="6,22" backgroundColor="#fdd835" />
		<widget name="bara_albastru" position="680,632" size="6,22" backgroundColor="#1e88e5" />
		<widget source="key_blue" render="Label" position="692,629" size="188,28" font="Regular;19" foregroundColor="#d7e3ec" backgroundColor="#0b1219" transparent="1" halign="left" valign="center" noWrap="1" />
	</screen>
	"""

	@staticmethod
	def skinMarit(skin, procent):
		"""Skinul ecranului la marimea textului `procent` (config.osd.fontscale; skin.py mareste fontul, nu si caseta):
		mesajul (refuzul unei comenzi, "nu are niciun tuner") are loc de doua randuri intregi, iar ce e sub el si
		fereastra coboara cu diferenta. Caseta de 52 px (la 1280) tinea un rand si o bucata: de la 105 % al doilea rand se
		taia. La 100 % (si sub) skinul ramane cel de dinainte."""
		k = max(100, int(procent))
		if k <= 100:
			return skin
		e = 52 * k * k // 10000 - 52 + 8

		def muta(m):
			x, y = int(m.group(1)), int(m.group(2))
			return 'position="%d,%d"' % (x, y + e if y >= 570 else y)
		skin = re.sub(r'position="(\d+),(\d+)"', muta, skin)
		skin = skin.replace('size="900,662"', 'size="900,%d"' % (662 + e))
		return skin.replace('position="20,516" size="860,52"', 'position="20,516" size="860,%d"' % (52 + e))

	def __init__(self, session):
		try:
			import skin
			self.SKIN = self.skinMarit(HdsDishMotorEcran.SKIN, skin.getFontScalePercent())
		except Exception:
			pass
		HdsDishMotor.__init__(self, session)
		for nume in ("comenzi_stare", "limite", "limite_oprite", "mesaj", "semnal", "ajutor", "key_red", "key_green",
				"key_yellow", "key_blue"):
			self[nume] = StaticText("")
		for nume in BARE:
			self[nume] = Label("")
		self._bare_vazute = None
		self.setTitle(_("Rotirea antenei"))
		self["actiuni"] = ActionMap(["OkCancelActions", "DirectionActions", "ColorActions", "NumberActions"], {
			"cancel": self.iesire,
			"ok": self.oprire,
			"red": self.oprire,
			"left": lambda: self._comanda(lambda c: c.pas(False, "ecran")),
			"right": lambda: self._comanda(lambda c: c.pas(True, "ecran")),
			"up": lambda: self._marime(+1),
			"down": lambda: self._marime(-1),
			"4": lambda: self._comanda(lambda c: c.continuu(False, "ecran")),
			"6": lambda: self._comanda(lambda c: c.continuu(True, "ecran")),
			"green": self.satelit,
			"yellow": self.pozitii,
			"blue": self.limite,
			# eliberarea si tinerea sagetilor ajung si ele la harta (keymap.xml:616-624): nu fac nimic, altfel jurnalul
			# ar scrie „unknown action" la fiecare apasare. Tinerea nu repeta pasul: fiecare pas e o apasare.
			"leftUp": self._nimic, "rightUp": self._nimic, "upUp": self._nimic, "downUp": self._nimic,
			"leftRepeated": self._nimic, "rightRepeated": self._nimic, "upRepeated": self._nimic, "downRepeated": self._nimic,
			# NumberActions trimite toate cifrele (keymap.xml:307-318); numai 4 si 6 au comanda, celelalte nu fac nimic, ca
			# jurnalul sa nu scrie „unknown action NumberActions/N" la fiecare apasare
			"0": self._nimic, "1": self._nimic, "2": self._nimic, "3": self._nimic, "5": self._nimic,
			"7": self._nimic, "8": self._nimic, "9": self._nimic,
		}, -1)
		panou_automat_oprit("ecran", True)
		# aici ceasul bate indiferent de `config.usage.showdish`: utilizatorul a cerut anume ecranul
		self._porneste()

	# ------------------------------------------------------------------ comenzile

	def _comenzi(self):
		from Components.HdsMotorComenzi import comenzi
		return comenzi()

	def _arata(self, rezultat):
		"""textul intors de comenzi (un refuz, o intrebare fara raspuns) ajunge in banda; ceasul il rescrie oricum"""
		try:
			_ok, text = rezultat
		except (TypeError, ValueError):
			text = ""
		if text:
			self._comenzi()._spune(text)
		self._banda()

	def _comanda(self, functie):
		self._cuSlot(lambda: self._arata(functie(self._comenzi())))

	def _marime(self, delta):
		self._arata(self._comenzi().marimePas(delta))

	def oprire(self):
		self._arata(self._comenzi().opreste("ecran"))

	def iesire(self):
		self.close()

	def _opresteInainteDeDialog(self):
		"""cat e deschis un dialog motorul sta: deschiderea lui trimite intai oprirea (proiectul B 2.2). Intoarce True
		daca a oprit ceva (atunci dialogul nu se mai deschide: tasta a fost oprirea)."""
		c = self._comenzi()
		if c.seMisca() or c.stare in ("trimite", "oprire", "eliberare"):
			self._arata(c.opreste("ecran"))
			return True
		return False

	def _poateComanda(self):
		c = self._comenzi()
		motiv = c.motivIndisponibil()
		if motiv:
			c._spune(motiv)
			self._banda()
			return False
		return True

	def _cuSlot(self, apoi):
		"""cand sunt mai multe tunere cu motor, primul lucru e alegerea lui (o data, cat tunerul nu e luat)"""
		from Components import HdsMotorTuner
		c = self._comenzi()
		tunere = HdsMotorTuner.tunereCuMotor()
		if len(tunere) < 2 or c.tuner is not None or getattr(self, "_slot_ales", False):
			apoi()
			return

		def ales(rezultat):
			if rezultat:
				c.alegeSlot(rezultat[1])
				self._slot_ales = True
				apoi()
		self.session.openWithCallback(ales, HdsMotorAlegere, title=_("Alege tunerul cu motor"),
			list=[(_("Tunerul %s") % nume, slot) for slot, nume in tunere], keys=[])

	def satelit(self):
		if self._opresteInainteDeDialog() or not self._poateComanda():
			return
		c = self._comenzi()
		refuz = c._refuzFaraLimite() or c._refuzLacat()
		if refuz:
			self._arata((False, refuz))
			return
		self._cuSlot(self._alegeSatelit)

	def _alegeLocul(self, mesaj, apoi):
		"""alegerea locului antenei (Screens/HdsLocul.py); `apoi()` numai daca locul s-a schimbat"""
		from Screens.HdsLocul import deschide
		deschide(self.session, lambda schimbat: apoi() if schimbat else None, mesaj=mesaj)

	def _alegeSatelit(self):
		from Components import HdsMotorTuner, HdsLocul
		c = self._comenzi()
		slot = c._slotAles()
		refuz = HdsMotorTuner.refuzFaraLoc(slot)
		if refuz:
			# fara locul antenei motorul USALS nu porneste: mesajul in banda si alegerea locului, apoi lista satelitilor
			self._arata((False, refuz))
			self._alegeLocul(refuz, self._alegeSatelit)
			return
		sateliti = HdsMotorTuner.sateliti(slot)
		if not sateliti:
			self._arata((False, _("Pentru satelitul ales nu există niciun transponder în lista de sateliți, deci receptorul nu are ce acorda.")))
			return
		curent = c.referinta["orbital_position"] if c.referinta else c.pozitie_stiuta
		lista, ales = [], 0
		for i, (orbital, nume) in enumerate(sateliti):
			lista.append(("%s   (%s)" % (nume, gradeText(_gradeDin(orbital))), orbital))
			if orbital == curent:
				ales = i
		titlu = _("Mergi la satelit")
		if HdsLocul.stabilit():
			# textul listei are loc pentru doua randuri in skin (ChoiceBox, 836 x 88)
			titlu = "%s\n%s" % (titlu, _("Locul antenei: %s") % HdsLocul.textLoc())
		# primul rand schimba locul antenei (acelasi pentru toate tunerele), restul sunt satelitii
		lista.insert(0, (_("Schimbă locul antenei"), "loc"))
		self.session.openWithCallback(self._satelitAles, HdsMotorAlegere, title=titlu, list=lista, keys=[], selection=ales + 1)

	def _satelitAles(self, rezultat):
		if rezultat and rezultat[1] == "loc":
			self._alegeLocul(None, self._alegeSatelit)
			return
		if rezultat:
			self._arata(self._comenzi().laSatelit(rezultat[1], "ecran"))

	def pozitii(self):
		if self._opresteInainteDeDialog() or not self._poateComanda():
			return
		lista = [(_("Mergi la poziția memorată..."), "la"), (_("Memorează aici poziția..."), "memoreaza"),
			(_("Mergi la poziția 0 (referința motorului)"), "zero")]
		self._cuSlot(lambda: self.session.openWithCallback(self._pozitieAleasa, HdsMotorAlegere, title=_("Poziții memorate"),
			list=lista, keys=[]))

	def _pozitieAleasa(self, rezultat):
		if not rezultat:
			return
		if rezultat[1] == "zero":
			self._arata(self._comenzi().laReferinta("ecran"))
			return
		self.session.openWithCallback(lambda text: self._numarPozitie(rezultat[1], text), HdsMotorNumar,
			title=_("Numărul poziției (1-255)"), windowTitle=_("Poziții memorate"), text="1", type=Input.NUMBER)

	def _numarPozitie(self, actiune, text):
		if text is None:
			return
		try:
			pozitie = int(text)
		except ValueError:
			pozitie = 0
		if not 1 <= pozitie <= 255:
			self._arata((False, _("Poziția trebuie să fie un număr între 1 și 255.")))
			return
		c = self._comenzi()
		if actiune == "la":
			self._arata(c.laPozitie(pozitie, "ecran"))
			return
		self._intreaba(c.confirmare("memoreaza", pozitie), lambda: c.memoreaza(pozitie, True, "ecran"))

	def limite(self):
		if self._opresteInainteDeDialog() or not self._poateComanda():
			return
		lista = [(_("Limita de est este aici"), "est"), (_("Limita de vest este aici"), "vest"),
			(_("Pornește limitele"), "pornite"), (_("Oprește limitele (periculos)"), "oprite")]
		# deasupra comenzilor, ce stie receptorul despre limite (motorul nu le raporteaza): ultima comanda trimisa si
		# cand s-a pus fiecare limita (Components/HdsMotorComenzi.limiteTexte, aceleasi texte ca in web)
		from Components import HdsMotorComenzi
		texte = HdsMotorComenzi.stareComenzi().get("limite_texte") or {}
		titlu = texte.get("stare") or _("Limite")
		descriere = "\n".join(t for t in (texte.get("est_scurt"), texte.get("vest_scurt")) if t)
		self._cuSlot(lambda: self.session.openWithCallback(self._limitaAleasa, HdsMotorLimite, title=titlu,
			list=lista, keys=[], descriere=descriere))

	def _limitaAleasa(self, rezultat):
		if not rezultat:
			return
		c = self._comenzi()
		actiune = rezultat[1]
		if actiune == "pornite":
			self._arata(c.limitePornite("ecran"))
		elif actiune == "est":
			self._intreaba(c.confirmare("limita_est"), lambda: c.limitaEst(True, "ecran"))
		elif actiune == "vest":
			self._intreaba(c.confirmare("limita_vest"), lambda: c.limitaVest(True, "ecran"))
		elif actiune == "oprite":
			self._intreaba(c.confirmare("limite_oprite"), lambda: c.limiteOprite(True, "ecran"))

	def _intreaba(self, text, daca_da):
		def raspuns(da):
			if da:
				self._arata(daca_da())
		self.session.openWithCallback(raspuns, HdsMotorIntrebare, text)

	# ------------------------------------------------------------------ banda de jos

	def _banda(self, stare=None):
		from Components import HdsMotorComenzi
		d = (stare or {}).get("comenzi") or HdsMotorComenzi.stareComenzi()
		c = self._comenzi()
		motiv = c.motivIndisponibil()
		bucati = []
		if motiv:
			# fara tuner cu motor banda spune motivul si atat; tastele de comanda nu fac nimic, EXIT inchide
			for nume in ("comenzi_stare", "limite", "limite_oprite", "semnal", "key_red", "key_green", "key_yellow", "key_blue"):
				self._pune(nume, "")
			self._arataBarele(False)
			self._pune("mesaj", motiv)
			self._pune("ajutor", _("EXIT: ieșire"))
			return
		self._arataBarele(True)
		# msgid propriu: „Oprire” e tradus peste tot ca oprirea receptorului („Shutdown”)
		self._pune("key_red", _("Oprește motorul"))
		self._pune("key_green", _("Mergi la satelit"))
		self._pune("key_yellow", _("Poziții memorate"))
		self._pune("key_blue", _("Limite"))
		if d.get("oprire_automata_s") is None:
			bucati.append(_("Tunerul %s are motor") % d["tuner"])
		bucati.append(_("Pas: %d") % d["pas"])
		if d.get("oprire_automata_s") is not None:
			# cat merge motorul, locul numelui tunerului il ia oprirea automata (altfel randul se taie la „6 min 8 s")
			bucati.append(_("Oprire singură în %s") % secundeText(d["oprire_automata_s"]))
		self._pune("comenzi_stare", "   |   ".join(bucati))
		# starea limitelor: din comenzile date acum sau, pana la prima, din ultima comanda tinuta minte de receptor
		texte = d.get("limite_texte") or {}
		if d.get("limite_stare", d["limite"]) == "oprite":
			self._pune("limite", "")
			self._pune("limite_oprite", texte.get("scurt") or _("Limitele sunt oprite. Pornesc singure la ieșire."))
		else:
			self._pune("limite_oprite", "")
			self._pune("limite", texte.get("scurt") or (_("Limite: pornite") if d["limite"] == "pornite" else _("Limite: nu se știe")))
		mesaj = d.get("motiv") or ""
		vechime = d.get("motiv_de_acum_s")
		if mesaj and not d.get("eroare") and vechime is not None and vechime > MESAJ_S and d["stare"] != "misca_nucleu":
			mesaj = ""
		if d.get("lacat_proba"):
			mesaj = _("Mod de probă: se pot trimite numai oprirea și pornirea limitelor.")
		self._pune("mesaj", mesaj)
		self._pune("semnal", self._textSemnal(d))
		self._pune("ajutor", _("Stânga/Dreapta: un pas   Sus/Jos: mărimea pasului   4/6: mișcare fără oprire   OK: oprire   EXIT: ieșire"))

	def _arataBarele(self, da):
		if self._bare_vazute is not da:
			self._bare_vazute = da
			for nume in BARE:
				if da:
					self[nume].show()
				else:
					self[nume].hide()

	def _nimic(self):
		pass

	def _textSemnal(self, d):
		if not d.get("tuner_luat"):
			return _("La prima comandă programul se oprește; revine când ieși.")
		semnal = d.get("semnal")
		loc = ("%s  %s" % (d.get("referinta_satelit", ""), d.get("referinta", ""))).strip()
		if semnal is None:
			return ""
		if not semnal.get("citit"):
			return _("Semnalul nu se poate citi pe acest tuner.")
		if semnal.get("prins"):
			if semnal.get("calitate") is not None:
				return _("Semnal pe %s: recepționat, calitate %d %%") % (loc, semnal["calitate"])
			return _("Semnal pe %s: recepționat") % loc
		return _("Semnal pe %s: fără semnal") % loc

	# ------------------------------------------------------------------ ceasul si inchiderea

	def _bate(self):
		if not self._pornit:
			return
		stare = stareMotor()
		if not self._vazut:
			self._vazut = True
			self._cheie = None
			self._texte = {}
			self.show()
		if stare["activ"]:
			self._scrie(stare)
			self._deseneaza(stare)
			self._ceas.start(MS_IN_ALUNECARE if stare.get("alunecare") else MS_IN_MISCARE, True)
		else:
			self._pune("titlu", _("Antena nu se roteste"))
			self._pune("plecare", "")
			self._pune("curent", "")
			self._pune("tinta", "")
			self._pune("ramas", _("Aici se vede drumul ei cat timp motorul o roteste"))
			self._pune("viteza", "")
			pozitie = (stare.get("comenzi") or {}).get("pozitie_stiuta", -1)
			self._pune("detaliu", _("Antena e pe %s") % gradeText(_gradeDin(pozitie)) if pozitie is not None and pozitie >= 0 else "")
			self._gol()
			self._ceas.start(MS_IN_ASTEPTARE, True)
		try:
			self._banda(stare)
		except Exception as e:
			print("[HdsMotor] banda ecranului: %r" % (e,))

	def _gol(self):
		"""panza goala cat timp nu e nimic de aratat"""
		if self._cheie != "gol":
			self._cheie = "gol"
			panza = self["canvas"]
			panza.clear()
			panza.fill(0, 0, self._s(PANZA_L), self._s(PANZA_I), FOND)
			panza.flush()

	def _setareSchimbata(self, element):
		"""ecranul cerut din meniu nu asculta de `config.usage.showdish`: aceea priveste aparitia automata"""
		pass

	def _laInchidere(self):
		"""oprirea, limitele, uitarea pozitiei, tunerul si programul: lantul ramane in modulul comenzilor si se termina
		si dupa ce ecranul s-a inchis (nu atinge nimic din ecran)"""
		HdsDishMotor._laInchidere(self)
		panou_automat_oprit("ecran", False)
		try:
			self._comenzi().elibereaza("ecran")
		except Exception as e:
			print("[HdsMotor] iesirea din ecran: %r" % (e,))


BARE = ("bara_rosu", "bara_verde", "bara_galben", "bara_albastru")


def _gradeDin(orbital):
	from Components.DishMath import orbitalToDegrees
	return orbitalToDegrees(orbital)
