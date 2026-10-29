# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsBetaTester.py: ecranele programului de beta testeri. Meniu > Setari > Beta tester (ultima intrare din Setari).
# Logica e in Components/HdsBetaTester.py; aceleasi ecrane in interfata web: /beta-tester
# (HdsWebControl/betatester_web.py).
#
# - HdsBetaTester: intrarea din meniu. Cine nu e inscris vede invitatia (titlul, avantajele, cati testeri are modelul),
#   doua randuri: "Devino beta tester" (ecranul acordului) si "Forumul receptorului" (citit de oricine,
#   Screens/HdsForumReceptor.py), si in dreapta ultimele mesaje de pe forum; cine are acordul pe o nota mai veche vede
#   intai ecranul acordului. Dupa "Sunt de acord" ramane aici, in meniul testerului: randuri cu pictograma si un rand
#   scurt despre ce face fiecare (forumul primul, mesajul, "Ce am trimis", raspunsurile echipei, datele, "Ce trimit
#   acum", asistenta de la distanta, aparitia publica, nota, iesirea cu stergerea), iar in dreapta panoul testerului
#   (din ce data, numele de pe forum, ultima trimitere, cati testeri are modelul, identificatorul).
# - HdsBetaAcord: felurile de date, toate pornite din fabrica, cu comutatoare (OK, Stanga sau Dreapta le schimba);
#   randul scurt al randului ales sub lista; numele si e-mailul optionale (OK: tastatura de pe ecran); bifa notei,
#   singura nebifata, separata jos; Verde "Sunt de acord" merge numai cu ea; Rosu "Renunt"; Galben deschide nota.
#   Nimic nu pleaca inainte de "Sunt de acord".
# - HdsBetaDate: comutatoarele, numele si e-mailul, schimbate oricand.
# - HdsBetaText: un text lung (Ce trimit acum, raspunsurile, nota cu codul QR si adresa).
# - HdsBetaTrimise: "Ce am trimis".
# - HdsBetaMesaj: mesajul (Greseala / Idee / Intrebare), cu jurnalul ultimei erori si captura meniurilor numai daca
#   omul le bifeaza. Captura: dupa Verde ecranele se inchid, omul are CAPTURA_ASTEPTARE_S secunde sa deschida ecranul
#   despre care scrie, apoi captura (numai meniurile) se face singura si mesajul intra in coada.
# - HdsBetaPublic, HdsBetaLegareQr: numele public, e-mailul pentru cont, legarea unui cont de pe forum prin codul QR
#   sau prin codul de 6 cifre aratat de site, dezlegarea. Fara parole pe receptor.
#
# Skinul: ecranele sunt in skinul HDSatelit (HDSatelit/skin.xml, cadrul HdsCadru1776: titlul, ceasul, legenda
# tastelor). Skinul de aici e numai rezerva pentru alt skin ales: aceeasi geometrie (SABLON_*, acelasi corp ca in
# skin.xml), culorile skinului scrise ca valori, legenda tastelor ca in cadru (liniuta colorata + text). Randurile
# listelor (pictograma, titlul, randul scurt, insigna, comutatorul) le deseneaza codul (setBuildFunc), cu marimea
# randului si latimea luate din widget; pictogramele sunt cele ale meniului (HDSatelit/meniu), micsorate la deschidere.

import os
import re

from .Screen import Screen
from Components.ActionMap import ActionMap
from Components.Button import Button
from Components.ConfigList import ConfigListScreen
from Components.Label import Label
from Components.MenuList import MenuList
from Components.Pixmap import Pixmap
from Components.ScrollLabel import ScrollLabel
from Components.Sources.CanvasSource import CanvasSource
from Components.Sources.StaticText import StaticText
from Components.config import ConfigYesNo, ConfigText, ConfigSelection, getConfigListEntry
from Components import HdsBetaTester as B
from Screens.MessageBox import MessageBox

B.initConfig()

N_ = B.N_

TOATE_TASTELE = ("key_red", "key_green", "key_yellow", "key_blue")
CULORI_TASTE = {"key_red": "#E5484D", "key_green": "#46B06A", "key_yellow": "#E8B93A", "key_blue": "#3D7BE0"}

# culorile skinului HDSatelit (rolurile din skin.xml), scrise ca valori pentru skinul de rezerva
CULORI_SKIN = {
	"hdsPanelDialog": "#10162A",
	"hdsPanelSolid": "#10162A",
	"hdsCell": "#282D3F",
	"hdsTrack": "#2A3350",
	"hdsDivider": "#3A4255",
	"hdsText": "#F2F4F8",
	"white": "#FFFFFF",
	"hdsText2": "#C9D2E3",
	"hdsLabel": "#AEB9CC",
	"hdsBrand": "#374EA1",
	"hdsAmber": "#F5B83D",
	"hdsGood": "#4FD18B",
	"hdsBad": "#FF6B5E",
	"hdsMarkedText": "#10162A",
}

# culorile randurilor desenate din cod: rolul din skinul HDSatelit si rezerva pentru alt skin (0xRRGGBB)
CULORI = {
	"card": ("hdsCell", 0x282D3F),
	"ales": ("hdsBrand", 0x374EA1),
	"text": ("hdsText", 0xF2F4F8),
	"text2": ("hdsText2", 0xC9D2E3),
	"eticheta": ("hdsLabel", 0xAEB9CC),
	"alb": ("white", 0xFFFFFF),
	"chihlimbar": ("hdsAmber", 0xF5B83D),
	"pe_chihlimbar": ("hdsMarkedText", 0x10162A),
	"rosu": ("hdsBad", 0xFF6B5E),
	"bine": ("hdsGood", 0x4FD18B),
	"sina": ("hdsTrack", 0x2A3350),
	"fond": ("hdsPanelSolid", 0x10162A),
}

# pictogramele meniului folosite aici (HDSatelit/meniu/<culoare>/<glif>.png, 72x72)
GLIFE = {
	"forum": "traducere",
	"mesaj": "manual",
	"trimite_acum": "actualizare",
	"trimise": "jurnal",
	"raspunsuri": "informatii",
	"date": "dns",
	"acum": "editor-canale",
	"probe": "verificare-disc",
	"asistenta": "conexiune",
	"canal_testeri": "reincarca",
	"public": "licente",
	"nota": "mod-sigur",
	"iesire": "intrare",
	"acord": "noutati",
	"nota_noua": "noutati",
}
GLIF_TESTER = "noutati"
GLIF_FORUM = "traducere"

AVANTAJE_PE_ECRAN = B.AVANTAJE_ARATATE
MESAJE_FORUM = 3
TEXT_CARD = 170

_PICTOGRAME = {}


def _jurnal(text):
	print("[HdsBetaTester] %s" % text)


def _nimic(*_a):
	pass


def _taste(y=936, chei=TOATE_TASTELE, latime=1712, x=32):
	"""Legenda tastelor pentru skinul de rezerva (alt skin decat HDSatelit, care are cadrul lui): pe locul fiecarei
	culori o liniuta colorata si textul tastei; cele nefolosite nu apar deloc (nici in skin, nici in ecran)."""
	lat = latime // 4
	rez = []
	for i, nume in enumerate(TOATE_TASTELE):
		if nume not in chei:
			continue
		rez.append('<eLabel position="%d,%d" size="6,32" backgroundColor="%s" zPosition="1" />' % (x + i * lat, y + 8,
			CULORI_TASTE[nume]))
		rez.append('<widget name="%s" position="%d,%d" size="%d,48" font="Regular;28" foregroundColor="#F2F4F8" '
			'transparent="1" valign="center" noWrap="1" zPosition="1" />' % (nume, x + i * lat + 16, y, lat - 24))
	return "\n\t\t".join(rez)


def _rezerva(nume, titlu, corp, chei=()):
	"""Skinul de rezerva al unui ecran din corpul lui din skin.xml: aceeasi geometrie, culorile ca valori, fonturile
	Regular/Bold, liniile cadrului (titlul il scrie fereastra skinului ales), legenda tastelor `chei`."""
	corp = re.sub(r'font="Hds(Bold|Regular|Cond);', lambda m: 'font="%s;' % ("Bold" if m.group(1) == "Bold" else
		"Regular"), corp)
	# numai valorile culorilor (source="key_red" ramane numele sursei)
	corp = re.sub(r'((?:background|foreground)Color(?:Selected)?)="([A-Za-z_0-9]+)"', lambda m: '%s="%s"' % (
		m.group(1), CULORI_SKIN.get(m.group(2), m.group(2))), corp)
	return """
	<screen name="%s" resolution="1920,1080" position="center,center" size="1776,1000" backgroundColor="#10162A" title="%s">
		<eLabel position="32,88" size="1712,1" backgroundColor="#3A4255" zPosition="1" />
		<eLabel position="32,924" size="1712,1" backgroundColor="#3A4255" zPosition="1" />%s
		%s
	</screen>""" % (nume, titlu, corp, _taste(936, chei))


def _culoare(cheie):
	"""Culoarea rolului din skinul HDSatelit (0xRRGGBB), altfel rezerva."""
	nume, rezerva = CULORI[cheie]
	try:
		import skin
		c = skin.colorNames.get(nume)
		if c is not None:
			v = c.argb()
			return v & 0xFFFFFF if (v >> 24) in (0, 0xFF) else v
	except Exception:
		pass
	return rezerva


def _font(nume, marime):
	"""Fontul skinului (HdsBold, HdsRegular, HdsCond) la marimea data, prin skin.parseFont (si marirea textului)."""
	try:
		import skin
		return skin.parseFont("%s;%d" % (nume, max(8, int(marime))), ((1, 1), (1, 1)))
	except Exception:
		from enigma import gFont
		return gFont(nume, max(8, int(marime)))


def _dosarSkin():
	try:
		import skin
		return skin.DOSAR_HDS
	except Exception:
		return "/usr/share/enigma2/HDSatelit"


def _pictograma(glif, latura=72, culoare="deschis"):
	"""Pictograma meniului la latura data (micsorata o data, tinuta minte), sau None fara ea."""
	cheie = (glif, latura, culoare)
	if cheie not in _PICTOGRAME:
		ptr = None
		cale = os.path.join(_dosarSkin(), "meniu", culoare, glif + ".png")
		if os.path.isfile(cale):
			try:
				import skin
				from enigma import getDesktop
				ptr = skin.incarcaPixmapScalat(cale, latura, latura, getDesktop(0))
			except Exception as e:
				_jurnal("pictograma %s: %s" % (glif, e))
		_PICTOGRAME[cheie] = ptr
	return _PICTOGRAME[cheie]


def _punePictograma(widget, glif, culoare="alb"):
	"""Pictograma pe un widget Pixmap, la marimea lui."""
	try:
		i = widget.instance
		if i is None:
			return
		ptr = _pictograma(glif, min(i.size().width(), i.size().height()), culoare)
		if ptr is not None:
			i.setPixmap(ptr)
	except Exception as e:
		_jurnal("pictograma %s: %s" % (glif, e))


def _listaDesenata():
	"""O lista ale carei randuri le deseneaza codul (eListboxPythonMultiContent); fara enigma2 (probele de pe PC), lista
	simpla."""
	try:
		from enigma import eListboxPythonMultiContent
	except ImportError:
		return MenuList([])
	return MenuList([], content=eListboxPythonMultiContent)


def _pozitie(w):
	try:
		i = w.instance
		p, m = i.position(), i.size()
		return p.x(), p.y(), m.width(), m.height()
	except Exception:
		return None


def _aseaza(w, x, y, latime, inaltime):
	try:
		from enigma import ePoint, eSize
		if w.instance is not None:
			w.instance.move(ePoint(x, y))
			w.instance.resize(eSize(latime, inaltime))
	except Exception as e:
		_jurnal("locul: %s" % e)


def _arata(w, vizibil):
	try:
		if vizibil:
			w.show()
		else:
			w.hide()
	except Exception:
		pass


def _cuDirectii(actiuni, sus=None, jos=None, stanga=None, dreapta=None):
	"""Toate actiunile hartii DirectionActions (si cele Repeated si Up), ca jurnalul sa nu scrie "unknown action"."""
	for d, f in (("up", sus), ("down", jos), ("left", stanga), ("right", dreapta)):
		actiuni[d] = f or _nimic
		actiuni[d + "Repeated"] = f or _nimic
		actiuni[d + "Up"] = _nimic
	return actiuni


def _cuCulori(actiuni):
	"""Tastele colorate nefolosite nu fac nimic (fara "unknown action" in jurnal)."""
	for c in ("red", "green", "yellow", "blue"):
		actiuni.setdefault(c, _nimic)
	return actiuni


def _cuSetup(ecran, actiuni):
	"""Toate actiunile hartii SetupActions din data/keymap.xml pentru un ecran cu ConfigListScreen: harta ecranului
	(prioritatea -2) le primeste inaintea lui config_actions, deci fara ele jurnalul scrie "unknown action" la VERDE
	(save), stanga, dreapta, cifre si stergere. VERDE = actiunea "green" a ecranului; restul = ce face ConfigListScreen."""
	actiuni.setdefault("save", actiuni.get("green", _nimic))
	actiuni.setdefault("left", ecran.keyLeft)
	actiuni.setdefault("right", ecran.keyRight)
	actiuni.setdefault("deleteForward", ecran.keyDelete)
	actiuni.setdefault("deleteBackward", ecran.keyBackspace)
	for n in range(10):
		actiuni.setdefault(str(n), lambda n=n: ecran.keyNumberGlobal(n))
	return actiuni


def _dataScurta(text):
	""""AAAA-LL-ZZ HH:MM" (B.oraLocala) -> "ZZ.LL.AAAA"; altfel textul ca atare."""
	m = re.match(r"\A(\d{4})-(\d{2})-(\d{2})", text or "")
	return "%s.%s.%s" % (m.group(3), m.group(2), m.group(1)) if m else (text or "")


def _scurt(text, maxim):
	text = " ".join((text or "").split())
	if len(text) <= maxim:
		return text
	return text[:maxim].rsplit(" ", 1)[0] + "..."


def ecranAsistenta():
	"""Ecranul Cere ajutor de la distanta (modulul asistentei: Screens.HdsAsistenta.HdsAsistenta, numai cu
	SystemInfo["HdsAsistenta"] adevarat, pus de mytest.py), sau None: randul nu apare."""
	try:
		from Components.SystemInfo import SystemInfo
		if not SystemInfo.get("HdsAsistenta"):
			return None
		from Screens.HdsAsistenta import HdsAsistenta
		return HdsAsistenta
	except Exception:
		return None


def randCanalTesteri(A):
	"""Randul Primeste intai versiunile pentru testeri: Da/Nu (modulul canalului testerilor) si starea."""
	pornit = B.canalTesteriPornit(A)
	return "%s: %s" % (_(A.TEXT_BIFA_TESTERI), _("Da") if pornit else _("Nu")), pornit


def ecranForum():
	"""Forumul receptorului (Screens.HdsForumReceptor.HdsForum), sau None daca lipseste: randul nu apare."""
	try:
		from Screens.HdsForumReceptor import HdsForum
		return HdsForum
	except Exception as e:
		print("[HdsBetaTester] forumul receptorului: %s" % e)
		return None


def _modulForum():
	try:
		from Components import HdsForumReceptor
		return HdsForumReceptor
	except Exception:
		return None


def uitaJetonulForumului():
	"""Dupa o schimbare a profilului public: forumul primeste numele nou la cererea urmatoare."""
	F = _modulForum()
	if F is None:
		return
	try:
		F.uitaJetonul()
	except Exception as e:
		print("[HdsBetaTester] jetonul forumului: %s" % e)


def ecranProbe():
	"""Ecranul "Probele receptorului" (alt modul al imaginii), sau None daca lipseste: randul nu apare."""
	try:
		from Screens.HdsProbe import HdsProbe
		return HdsProbe
	except Exception:
		return None


def avantaje():
	"""Avantajele aratate celui care nu e inscris, numai cele adevarate pe acest receptor: [(glif, titlu, rand)]."""
	exista = {
		"canal_testeri": B.modulCanalTesteri() is not None,
		"forum": ecranForum() is not None,
		"asistenta": ecranAsistenta() is not None,
	}
	return [(glif, titlu, rand) for _cheie, glif, titlu, rand in B.avantaje(exista)]


def _deseneazaQr(ecran, sursa, text):
	"""Codul QR al textului pe CanvasSource-ul `sursa` (marimea din widget). -> True daca s-a desenat."""
	c = ecran[sursa]
	latime = inaltime = 0
	for r in getattr(ecran, "renderer", []) or []:
		if getattr(r, "source", None) is c and r.instance is not None:
			latime, inaltime = r.instance.size().width(), r.instance.size().height()
	if not latime:
		return False
	try:
		from Components.HdsQr import deseneaza
		deseneaza(c, text, latime, inaltime)
		c.flush()
		return True
	except Exception as e:
		print("[HdsBetaTester] codul QR: %s" % e)
		return False


# ------------------------------------------------------------------ randurile desenate

class _Desen(object):
	"""Randurile unei liste desenate de cod. Marimea randului si latimea listei se iau din widget la asezare (dupa
	skin), fonturile si culorile odata cu ele; pana atunci randurile sunt goale.

	fel "meniu": randurile (titlu, cheie, rand scurt, insigna, valoare, glif, culoare) - un card cu pictograma, titlul,
	randul scurt dedesubt si, in dreapta, insigna chihlimbar sau valoarea; "rosu" coloreaza titlul (iesirea).
	fel "bife": randurile (titlu, element, cheie) - titlul si, in dreapta, comutatorul (ConfigYesNo), textul scris
	(ConfigText) sau, la cheia "nota", caseta de bifat si chenarul chihlimbar al randului separat."""

	def __init__(self, lista, fel):
		self.lista = lista
		self.fel = fel
		self.W = self.H = 0
		self.c = {}
		self.latura = 0
		l = getattr(lista, "l", None)
		if l is not None and hasattr(l, "setBuildFunc"):
			l.setBuildFunc(self.rand)

	def aseaza(self):
		try:
			i = self.lista.instance
			self.W = i.size().width()
			self.H = i.getItemHeight()
		except Exception as e:
			_jurnal("lista: %s" % e)
			return
		if self.H <= 0 or self.W <= 0:
			self.W = self.H = 0
			return
		# marimile de mai jos sunt pentru randul de 72 px (meniul) si de 66 px (comutatoarele)
		f = self.H / (72.0 if self.fel == "meniu" else 66.0)
		self.f = f
		self.c = dict((k, _culoare(k)) for k in CULORI)
		self.latura = max(16, int(self.H * 0.64))
		l = self.lista.l
		l.setFont(0, _font("HdsBold", 30 * f))
		l.setFont(1, _font("HdsCond", 23 * f))
		l.setFont(2, _font("HdsBold", 21 * f))
		l.setFont(3, _font("HdsRegular", 26 * f))
		l.setFont(4, _font("HdsRegular", 24 * f))
		self.lista.setList(list(self.lista.list))

	def rand(self, *r):
		if not self.H:
			return [None]
		try:
			return self._meniu(*r) if self.fel == "meniu" else self._bifa(*r)
		except Exception as e:
			_jurnal("randul: %s" % e)
			return [None]

	def _card(self, rez, chenar=None):
		from Components.MultiContent import MultiContentEntryText
		c = self.c
		g = max(2, int(3 * self.f))
		latime = self.W - int(26 * self.f)          # loc pentru bara de derulare
		if chenar:
			rez.append(MultiContentEntryText(pos=(0, g), size=(latime, self.H - 2 * g), font=0, text="",
				backcolor=c["card"], backcolor_sel=c["ales"], border_width=max(2, int(3 * self.f)), border_color=chenar))
		else:
			rez.append(MultiContentEntryText(pos=(0, g), size=(latime, self.H - 2 * g), font=0, text="",
				backcolor=c["card"], backcolor_sel=c["ales"]))
		return latime

	def _meniu(self, titlu, cheie, rand="", insigna="", valoare="", glif="", culoare=""):
		from enigma import RT_HALIGN_LEFT, RT_HALIGN_RIGHT, RT_HALIGN_CENTER, RT_VALIGN_CENTER
		from Components.MultiContent import MultiContentEntryText, MultiContentEntryPixmapAlphaBlend
		c, f, H = self.c, self.f, self.H
		rez = [None]
		latime = self._card(rez)
		x = int(18 * f)
		png = _pictograma(glif, self.latura) if glif else None
		if png is not None:
			rez.append(MultiContentEntryPixmapAlphaBlend(pos=(x, (H - self.latura) // 2), size=(self.latura,
				self.latura), png=png))
		xT = x + self.latura + int(18 * f)
		dreapta = latime - int(18 * f)
		latI = 0
		if insigna:
			latI = int(len(insigna) * 11 * f) + int(28 * f)
			hI = int(H * 0.42)
			rez.append(MultiContentEntryText(pos=(dreapta - latI, (H - hI) // 2), size=(latI, hI), font=2,
				flags=RT_HALIGN_CENTER | RT_VALIGN_CENTER, text=insigna, color=c["pe_chihlimbar"],
				color_sel=c["pe_chihlimbar"], backcolor=c["chihlimbar"], backcolor_sel=c["chihlimbar"]))
			latI += int(14 * f)
		elif valoare:
			latI = int(260 * f)
			rez.append(MultiContentEntryText(pos=(dreapta - latI, 0), size=(latI, H), font=3,
				flags=RT_HALIGN_RIGHT | RT_VALIGN_CENTER, text=valoare, color=c["chihlimbar"], color_sel=c["alb"]))
			latI += int(14 * f)
		latT = max(40, dreapta - latI - xT)
		culoare_titlu = c["rosu"] if culoare == "rosu" else c["text"]
		if rand:
			rez.append(MultiContentEntryText(pos=(xT, int(H * 0.06)), size=(latT, int(H * 0.50)), font=0,
				flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER, text=titlu, color=culoare_titlu, color_sel=c["alb"]))
			rez.append(MultiContentEntryText(pos=(xT, int(H * 0.54)), size=(latT, int(H * 0.38)), font=1,
				flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER, text=rand, color=c["eticheta"], color_sel=c["text2"]))
		else:
			rez.append(MultiContentEntryText(pos=(xT, 0), size=(latT, H), font=0,
				flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER, text=titlu, color=culoare_titlu, color_sel=c["alb"]))
		return rez

	def _bifa(self, titlu, element, cheie):
		from enigma import RT_HALIGN_LEFT, RT_HALIGN_RIGHT, RT_HALIGN_CENTER, RT_VALIGN_CENTER, RT_WRAP
		from Components.MultiContent import MultiContentEntryText
		c, f, H = self.c, self.f, self.H
		rez = [None]
		nota = cheie == "nota"
		latime = self._card(rez, c["chihlimbar"] if nota else None)
		x = int(20 * f)
		dreapta = latime - int(20 * f)
		valoare = getattr(element, "value", "")
		if nota:
			l = int(H * 0.46)
			y = (H - l) // 2
			b = max(2, int(3 * f))
			rez.append(MultiContentEntryText(pos=(x, y), size=(l, l), font=0, text="", backcolor=c["alb"],
				backcolor_sel=c["alb"]))
			rez.append(MultiContentEntryText(pos=(x + b, y + b), size=(l - 2 * b, l - 2 * b), font=0, text="",
				backcolor=c["chihlimbar"] if valoare else c["fond"], backcolor_sel=c["chihlimbar"] if valoare else c["fond"]))
			xT = x + l + int(20 * f)
			rez.append(MultiContentEntryText(pos=(xT, 0), size=(dreapta - xT, H), font=4,
				flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER | RT_WRAP, text=titlu, color=c["text"], color_sel=c["alb"]))
			return rez
		if isinstance(valoare, bool):
			lS, hS = int(66 * f), int(34 * f)
			xS = dreapta - lS
			yS = (H - hS) // 2
			sina = c["bine"] if valoare else c["sina"]
			rez.append(MultiContentEntryText(pos=(xS, yS), size=(lS, hS), font=0, text="", backcolor=sina,
				backcolor_sel=sina))
			m = max(3, int(4 * f))
			lB = hS - 2 * m
			xB = xS + lS - m - lB if valoare else xS + m
			rez.append(MultiContentEntryText(pos=(xB, yS + m), size=(lB, lB), font=0, text="", backcolor=c["alb"],
				backcolor_sel=c["alb"]))
			lV = int(90 * f)
			rez.append(MultiContentEntryText(pos=(xS - lV - int(12 * f), 0), size=(lV, H), font=2,
				flags=RT_HALIGN_RIGHT | RT_VALIGN_CENTER, text=_("Da") if valoare else _("Nu"),
				color=c["bine"] if valoare else c["eticheta"], color_sel=c["alb"]))
			latT = xS - lV - int(24 * f) - x
		else:
			lV = int(latime * 0.42)
			rez.append(MultiContentEntryText(pos=(dreapta - lV, 0), size=(lV, H), font=3,
				flags=RT_HALIGN_RIGHT | RT_VALIGN_CENTER, text=str(valoare or ""), color=c["text2"], color_sel=c["alb"]))
			latT = dreapta - lV - int(16 * f) - x
		rez.append(MultiContentEntryText(pos=(x, 0), size=(max(40, latT), H), font=0,
			flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER, text=titlu, color=c["text"], color_sel=c["alb"]))
		return rez


# ------------------------------------------------------------------ meniul testerului si invitatia

# corpul ecranului, acelasi in skin.xml (in cadrul HdsCadru1776) si in skinul de rezerva; "loc_lista_vizitator" e
# locul listei cand omul nu e inscris (codul muta lista acolo)
CORP_TESTER = """
		<widget name="lista" position="32,108" size="1072,792" itemHeight="72" foregroundColor="hdsText" backgroundColor="hdsPanelDialog" backgroundColorSelected="hdsPanelDialog" foregroundColorSelected="hdsText" transparent="1" scrollbarMode="showOnDemand" enableWrapAround="1" zPosition="3" />
		<widget name="loc_lista_vizitator" position="32,756" size="1072,144" transparent="1" zPosition="0" />
		<widget name="panou" position="1136,108" size="608,792" backgroundColor="hdsCell" zPosition="1" />
		<widget name="semn" position="1156,124" size="72,72" alphatest="blend" zPosition="2" />
		<widget name="semn_forum" position="1156,124" size="72,72" alphatest="blend" zPosition="2" />
		<widget name="titlu_panou" position="1244,124" size="484,44" font="HdsBold;34" foregroundColor="hdsText" backgroundColor="hdsCell" transparent="1" valign="center" noWrap="1" zPosition="2" />
		<widget name="din" position="1244,166" size="484,32" font="HdsCond;24" foregroundColor="hdsLabel" backgroundColor="hdsCell" transparent="1" valign="center" noWrap="1" zPosition="2" />
		<widget name="linie_panou" position="1160,212" size="560,1" backgroundColor="hdsDivider" zPosition="2" />
		<widget name="eticheta_nume" position="1160,228" size="560,32" font="HdsCond;24" foregroundColor="hdsLabel" backgroundColor="hdsCell" transparent="1" valign="center" noWrap="1" zPosition="2" />
		<widget name="nume" position="1160,262" size="560,44" font="HdsBold;32" foregroundColor="hdsAmber" backgroundColor="hdsCell" transparent="1" valign="center" noWrap="1" zPosition="2" />
		<widget name="ultima" position="1160,326" size="560,40" font="HdsRegular;28" foregroundColor="hdsText" backgroundColor="hdsCell" transparent="1" valign="center" noWrap="1" zPosition="2" />
		<widget name="automat" position="1160,366" size="560,32" font="HdsCond;24" foregroundColor="hdsLabel" backgroundColor="hdsCell" transparent="1" valign="center" noWrap="1" zPosition="2" />
		<widget name="numar_fundal" position="1160,420" size="560,100" backgroundColor="hdsTrack" zPosition="2" />
		<widget name="numar_bara" position="1160,420" size="6,100" backgroundColor="hdsAmber" zPosition="3" />
		<widget name="numar" position="1182,424" size="526,92" font="HdsRegular;26" foregroundColor="hdsAmber" backgroundColor="hdsTrack" transparent="1" valign="center" zPosition="4" />
		<widget name="identificator" position="1160,736" size="560,152" font="HdsCond;22" foregroundColor="hdsLabel" backgroundColor="hdsCell" transparent="1" valign="bottom" zPosition="2" />
		<widget name="invitatie" position="32,108" size="1072,112" font="HdsBold;40" foregroundColor="hdsText" backgroundColor="hdsPanelDialog" transparent="1" valign="top" zPosition="2" />
		<widget name="invitatie_text" position="32,222" size="1072,76" font="HdsRegular;28" foregroundColor="hdsText2" backgroundColor="hdsPanelDialog" transparent="1" valign="top" zPosition="2" />
		<widget name="fundal_avantaj0" position="32,306" size="1072,108" backgroundColor="hdsCell" zPosition="1" />
		<widget name="semn_avantaj0" position="48,324" size="72,72" alphatest="blend" zPosition="2" />
		<widget name="titlu_avantaj0" position="140,312" size="948,42" font="HdsBold;30" foregroundColor="hdsText" backgroundColor="hdsCell" transparent="1" valign="center" noWrap="1" zPosition="2" />
		<widget name="text_avantaj0" position="140,354" size="948,56" font="HdsCond;24" foregroundColor="hdsLabel" backgroundColor="hdsCell" transparent="1" valign="top" zPosition="2" />
		<widget name="fundal_avantaj1" position="32,422" size="1072,108" backgroundColor="hdsCell" zPosition="1" />
		<widget name="semn_avantaj1" position="48,440" size="72,72" alphatest="blend" zPosition="2" />
		<widget name="titlu_avantaj1" position="140,428" size="948,42" font="HdsBold;30" foregroundColor="hdsText" backgroundColor="hdsCell" transparent="1" valign="center" noWrap="1" zPosition="2" />
		<widget name="text_avantaj1" position="140,470" size="948,56" font="HdsCond;24" foregroundColor="hdsLabel" backgroundColor="hdsCell" transparent="1" valign="top" zPosition="2" />
		<widget name="fundal_avantaj2" position="32,538" size="1072,108" backgroundColor="hdsCell" zPosition="1" />
		<widget name="semn_avantaj2" position="48,556" size="72,72" alphatest="blend" zPosition="2" />
		<widget name="titlu_avantaj2" position="140,544" size="948,42" font="HdsBold;30" foregroundColor="hdsText" backgroundColor="hdsCell" transparent="1" valign="center" noWrap="1" zPosition="2" />
		<widget name="text_avantaj2" position="140,586" size="948,56" font="HdsCond;24" foregroundColor="hdsLabel" backgroundColor="hdsCell" transparent="1" valign="top" zPosition="2" />
		<widget name="banda_fundal" position="32,656" size="1072,84" backgroundColor="hdsTrack" zPosition="1" />
		<widget name="banda_bara" position="32,656" size="6,84" backgroundColor="hdsAmber" zPosition="2" />
		<widget name="banda" position="56,656" size="1032,84" font="HdsRegular;28" foregroundColor="hdsAmber" backgroundColor="hdsTrack" transparent="1" valign="center" zPosition="3" />
		<widget name="fcard0" position="1160,232" size="560,184" backgroundColor="hdsPanelSolid" zPosition="2" />
		<widget name="fautor0" position="1176,240" size="210,36" font="HdsBold;26" foregroundColor="hdsAmber" backgroundColor="hdsPanelSolid" transparent="1" valign="center" noWrap="1" zPosition="3" />
		<widget name="finsigna0" position="1396,244" size="130,28" font="HdsCond;22" foregroundColor="hdsText2" backgroundColor="hdsTrack" halign="center" valign="center" noWrap="1" zPosition="4" />
		<widget name="fechipa0" position="1396,244" size="130,28" font="HdsCond;22" foregroundColor="hdsPanelSolid" backgroundColor="hdsGood" halign="center" valign="center" noWrap="1" zPosition="4" />
		<widget name="fora0" position="1532,240" size="172,36" font="HdsCond;22" foregroundColor="hdsLabel" backgroundColor="hdsPanelSolid" transparent="1" halign="right" valign="center" noWrap="1" zPosition="3" />
		<widget name="ftext0" position="1176,282" size="528,126" font="HdsRegular;24" foregroundColor="hdsText" backgroundColor="hdsPanelSolid" transparent="1" valign="top" zPosition="3" />
		<widget name="fcard1" position="1160,428" size="560,184" backgroundColor="hdsPanelSolid" zPosition="2" />
		<widget name="fautor1" position="1176,436" size="210,36" font="HdsBold;26" foregroundColor="hdsAmber" backgroundColor="hdsPanelSolid" transparent="1" valign="center" noWrap="1" zPosition="3" />
		<widget name="finsigna1" position="1396,440" size="130,28" font="HdsCond;22" foregroundColor="hdsText2" backgroundColor="hdsTrack" halign="center" valign="center" noWrap="1" zPosition="4" />
		<widget name="fechipa1" position="1396,440" size="130,28" font="HdsCond;22" foregroundColor="hdsPanelSolid" backgroundColor="hdsGood" halign="center" valign="center" noWrap="1" zPosition="4" />
		<widget name="fora1" position="1532,436" size="172,36" font="HdsCond;22" foregroundColor="hdsLabel" backgroundColor="hdsPanelSolid" transparent="1" halign="right" valign="center" noWrap="1" zPosition="3" />
		<widget name="ftext1" position="1176,478" size="528,126" font="HdsRegular;24" foregroundColor="hdsText" backgroundColor="hdsPanelSolid" transparent="1" valign="top" zPosition="3" />
		<widget name="fcard2" position="1160,624" size="560,184" backgroundColor="hdsPanelSolid" zPosition="2" />
		<widget name="fautor2" position="1176,632" size="210,36" font="HdsBold;26" foregroundColor="hdsAmber" backgroundColor="hdsPanelSolid" transparent="1" valign="center" noWrap="1" zPosition="3" />
		<widget name="finsigna2" position="1396,636" size="130,28" font="HdsCond;22" foregroundColor="hdsText2" backgroundColor="hdsTrack" halign="center" valign="center" noWrap="1" zPosition="4" />
		<widget name="fechipa2" position="1396,636" size="130,28" font="HdsCond;22" foregroundColor="hdsPanelSolid" backgroundColor="hdsGood" halign="center" valign="center" noWrap="1" zPosition="4" />
		<widget name="fora2" position="1532,632" size="172,36" font="HdsCond;22" foregroundColor="hdsLabel" backgroundColor="hdsPanelSolid" transparent="1" halign="right" valign="center" noWrap="1" zPosition="3" />
		<widget name="ftext2" position="1176,674" size="528,126" font="HdsRegular;24" foregroundColor="hdsText" backgroundColor="hdsPanelSolid" transparent="1" valign="top" zPosition="3" />
		<widget name="forum_stare" position="1160,232" size="560,576" font="HdsRegular;28" foregroundColor="hdsText2" backgroundColor="hdsCell" transparent="1" halign="center" valign="center" zPosition="3" />
		<widget name="forum_jos" position="1160,840" size="560,44" font="HdsCond;24" foregroundColor="hdsLabel" backgroundColor="hdsCell" transparent="1" valign="center" noWrap="1" zPosition="2" />"""

PARTI_TESTER = ("semn", "din", "eticheta_nume", "nume", "ultima", "automat", "numar_fundal", "numar_bara", "numar",
	"identificator")
PARTI_VIZITATOR = ("semn_forum", "invitatie", "invitatie_text", "banda_fundal", "banda_bara", "banda", "forum_stare",
	"forum_jos") + tuple("%s%d" % (p, k) for k in range(AVANTAJE_PE_ECRAN) for p in ("fundal_avantaj", "semn_avantaj",
	"titlu_avantaj", "text_avantaj"))
PARTI_CARD = ("fcard", "fautor", "finsigna", "fechipa", "fora", "ftext")


class HdsBetaTester(Screen):
	skin = _rezerva("HdsBetaTester", "Beta tester", CORP_TESTER, ("key_red", "key_green"))

	RANDURI = (
		("forum", B.N_("Forumul receptorului")),
		("mesaj", B.N_("Trimite un mesaj")),
		("trimite_acum", B.N_("Trimite acum")),
		("trimise", B.N_("Ce am trimis")),
		("raspunsuri", B.N_("Răspunsurile echipei")),
		("date", B.N_("Datele pe care le trimit")),
		("acum", B.N_("Ce trimit acum")),
		("probe", B.N_("Probele receptorului")),
		("asistenta", B.N_("Cere ajutor de la distanță")),
		("canal_testeri", ""),          # eticheta si starea vin din Components.HdsActualizari (canalul testerilor)
		("public", B.N_("Apariția publică")),
		("nota", B.N_("Nota de confidențialitate")),
		("iesire", B.N_("Ieși din program și șterge datele")),
	)
	# cine nu e inscris: acordul si forumul (citit de oricine)
	RANDURI_VIZITATOR = (
		("acord", B.N_("Devino beta tester")),
		("forum", B.N_("Forumul receptorului")),
	)
	# inscris cu o nota mai veche: acceptarea notei noi intai, forumul, nota si iesirea
	RANDURI_NOTA_VECHE = (
		("nota_noua", B.N_("Acceptă nota nouă")),
		("forum", B.N_("Forumul receptorului")),
		("nota", B.N_("Nota de confidențialitate")),
		("iesire", B.N_("Ieși din program și șterge datele")),
	)

	def __init__(self, session):
		Screen.__init__(self, session)
		self.setTitle(_("Beta tester"))
		self.ecran_dedesubt = B.ultimulEcranTitlu(session)
		self["lista"] = _listaDesenata()
		self.desen = _Desen(self["lista"], "meniu")
		self["loc_lista_vizitator"] = Label("")
		for nume in ("panou", "titlu_panou", "linie_panou") + PARTI_TESTER + PARTI_VIZITATOR:
			self[nume] = Pixmap() if nume.startswith("semn") else Label("")
		for k in range(MESAJE_FORUM):
			for p in PARTI_CARD:
				self["%s%d" % (p, k)] = Label("")
			self["finsigna%d" % k].setText(_("Beta tester").upper())
			self["fechipa%d" % k].setText(_("Echipa").upper())
		self["eticheta_nume"].setText(_("Numele tău pe forum"))
		self["invitatie"].setText(_(B.INTREBARE))
		self["invitatie_text"].setText(_("Ca beta tester trimiți date anonime care ajută imaginea și poți scrie pe "
			"forumul receptorului."))
		self["key_red"] = Button(_("Înapoi"))
		self["key_green"] = Button(_("Deschide"))
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions"], _cuCulori({
			"cancel": self.close,
			"red": self.close,
			"ok": self.deschide,
			"green": self.deschide,
		}), -2)
		self.randuri = []
		self._cerere = None
		self._numar = ""
		self._ultima = None
		self._inscris = None
		self._locuri = None
		self._lucrareForum = None
		self._forumNoi = 0       # mesajele noi de pe forum de la ultima vizita (insigna randului, testerul)
		from enigma import eTimer
		self.ceas = eTimer()
		self.ceas.callback.append(self._asteapta)
		self.onClose.append(self.ceas.stop)
		self.ceasNumar = eTimer()
		self.ceasNumar.callback.append(self._numarul)
		self.onClose.append(self.ceasNumar.stop)
		# "Ultima trimitere" se schimba singura cand o trimitere (Trimite acum, cea zilnica) se termina
		self.ceasUltima = eTimer()
		self.ceasUltima.callback.append(self._ultimaTrimitere)
		self.onClose.append(self.ceasUltima.stop)
		self.ceasForum = eTimer()
		self.ceasForum.callback.append(self._forumGata)
		self.onClose.append(self.ceasForum.stop)
		self.onFirstExecBegin.append(self._laInceput)
		self.onLayoutFinish.append(self._asezare)
		B.ceNumar()
		self.ceasNumar.start(1000, False)
		self.ceasUltima.start(3000, False)
		self.reface()

	# ------------------------------------------------------------ asezarea (dupa skin)

	def _asezare(self):
		self._locuri = (_pozitie(self["lista"]), _pozitie(self["loc_lista_vizitator"]))
		self["loc_lista_vizitator"].hide()
		_punePictograma(self["semn"], GLIF_TESTER)
		_punePictograma(self["semn_forum"], GLIF_FORUM)
		self.desen.aseaza()
		self._inscris = None
		self.reface()
		# vizitatorul: ultimele mesaje in panou; testerul: cate mesaje au venit de la ultima vizita (insigna)
		self._citesteForumul()

	def _locLista(self, inscris):
		if not self._locuri or None in self._locuri:
			return
		x, y, w, h = self._locuri[0] if inscris else self._locuri[1]
		_aseaza(self["lista"], x, y, w, h)

	def _schimbaFelul(self, inscris):
		"""Testerul sau invitatia: partile celuilalt fel se ascund, lista se muta la locul ei."""
		if inscris == self._inscris:
			return
		self._inscris = inscris
		for nume in PARTI_TESTER:
			_arata(self[nume], inscris)
		for nume in PARTI_VIZITATOR:
			_arata(self[nume], not inscris)
		for k in range(MESAJE_FORUM):
			for p in PARTI_CARD:
				_arata(self["%s%d" % (p, k)], False)
		self["titlu_panou"].setText(_("Ești beta tester") if inscris else _("Ultimele mesaje de pe forum"))
		self._locLista(inscris)

	# ------------------------------------------------------------ ceasurile

	def _numarul(self):
		"""Randul cu numarul de testeri ai modelului, cand vine raspunsul (ecranul nu il asteapta)."""
		B._culegeNumar()
		rand = B.randNumar()
		if rand != self._numar:
			self._numar = rand
			self.reface()
		if B._starea.get("cerere_numar") is None:
			self.ceasNumar.stop()

	def _ultimaTrimitere(self):
		if self._inscris and B.randUltimaTrimitere() != self._ultima:
			self.reface()

	def _laInceput(self):
		if B.notaVeche():
			self.session.openWithCallback(self._dupaAcord, HdsBetaNotaNoua)
			return
		self._cereRaspunsuri()

	def _dupaAcord(self, *_r):
		self.reface()
		self._cereRaspunsuri()

	def _dupaForum(self, *_r):
		"""Inapoi din forum: ce era acolo e vazut (HdsForumReceptor.tineVazut), insigna arata ce a ramas."""
		F = _modulForum()
		self._forumNoi = F.mesajeNoiCunoscute() if F is not None else 0
		self._dupaAcord()

	def _cereRaspunsuri(self):
		b = B.initConfig()
		if B.inscris(b) and self._cerere is None:
			self._cerere = B.Cerere(B.adresaServer(b), "raspunsuri", {"v": B.PROTOCOL, "id": b.id.value})
			self._cerere.start()
			self.ceas.start(500, False)

	def _asteapta(self):
		c = self._cerere
		if c is None or not c.gata:
			return
		self.ceas.stop()
		self._cerere = None
		if 200 <= c.cod < 300:
			B.tineRaspunsuri(c.raspuns)
		self.reface()

	# ------------------------------------------------------------ ultimele mesaje de pe forum (vizitatorul)

	def _citesteForumul(self):
		F = _modulForum()
		if F is None or ecranForum() is None:
			self["forum_stare"].setText("")
			return
		self["forum_stare"].setText(_("Se citește forumul..."))
		try:
			self._lucrareForum = F.citeste()
		except Exception as e:
			_jurnal("forumul: %s" % e)
			self._lucrareForum = None
			self["forum_stare"].setText("")
			return
		self.ceasForum.start(500, False)

	def _forumGata(self):
		l = self._lucrareForum
		if l is None or not getattr(l, "gata", False):
			return
		self.ceasForum.stop()
		self._lucrareForum = None
		if self._inscris:
			F = _modulForum()
			noi = F.mesajeNoi(l.rezultat) if (F is not None and l.reusit) else 0
			if noi != self._forumNoi:
				self._forumNoi = noi
				self.reface()
			return
		if not l.reusit:
			self["forum_stare"].setText(l.mesaj or "")
			return
		r = l.rezultat or {}
		mesaje = [m for m in (r.get("mesaje") or []) if isinstance(m, dict)][-MESAJE_FORUM:]
		mesaje.reverse()
		subiect = r.get("subiect") or {}
		n = subiect.get("mesaje") if isinstance(subiect, dict) else None
		self["forum_jos"].setText(_("Mesaje: %d") % n if isinstance(n, int) else "")
		self["forum_stare"].setText("" if mesaje else _("Încă nu e niciun mesaj aici."))
		F = _modulForum()
		for k in range(MESAJE_FORUM):
			m = mesaje[k] if k < len(mesaje) else None
			for p in PARTI_CARD:
				_arata(self["%s%d" % (p, k)], m is not None and p not in ("finsigna", "fechipa"))
			if m is None:
				continue
			self["fautor%d" % k].setText(m.get("autor") or "")
			ora = ""
			try:
				ora = F.oraLocala(m.get("cand") or "") if F is not None else ""
			except Exception:
				ora = ""
			self["fora%d" % k].setText(ora)
			self["ftext%d" % k].setText(_scurt(m.get("text") or "", TEXT_CARD))
			insigna = m.get("insigna") or ""
			for nume, fel in (("finsigna", "tester"), ("fechipa", "echipa")):
				w = self["%s%d" % (nume, k)]
				_arata(w, insigna == fel)
				if insigna == fel:
					self._dupaNume(w, self["fautor%d" % k])

	def _dupaNume(self, insigna, autor):
		"""Insigna imediat dupa numele autorului (latimea numelui masurata)."""
		pa, pi = _pozitie(autor), _pozitie(insigna)
		if pa is None or pi is None:
			return
		try:
			lat = autor.instance.calculateSize().width()
		except Exception:
			return
		x = min(pa[0] + lat + int(12 * pa[3] / 36.0), pa[0] + pa[2])
		_aseaza(insigna, x, pi[1], pi[2], pi[3])

	# ------------------------------------------------------------ randurile si panoul

	def reface(self):
		b = B.initConfig()
		noi = B.raspunsuriNoi()
		veche = B.notaVeche(b)
		# cu nota veche: meniul testerului, cu starea si acceptarea notei noi primele (nimic nu pleaca pana atunci)
		inscris = B.inscris(b) or veche
		randuri = []
		felul = self.RANDURI_NOTA_VECHE if veche else (self.RANDURI if inscris else self.RANDURI_VIZITATOR)
		for cheie, text in felul:
			if cheie == "forum" and ecranForum() is None:
				continue
			if (cheie == "probe" and ecranProbe() is None) or (cheie == "asistenta" and ecranAsistenta() is None):
				continue
			scurt = B.RANDURI_MENIU.get(cheie, "") if inscris else B.RANDURI_VIZITATOR.get(cheie, "")
			glif = GLIFE.get(cheie, "")
			if cheie == "canal_testeri":
				A = B.modulCanalTesteri()
				if A is None:
					continue
				randuri.append((randCanalTesteri(A)[0], cheie, _(scurt), "", "", glif, ""))
				continue
			insigna = valoare = ""
			if cheie == "raspunsuri" and noi:
				insigna = _("un răspuns nou") if noi == 1 else _("%d răspunsuri noi") % noi
			elif cheie == "forum" and inscris and self._forumNoi and _modulForum() is not None:
				insigna = _modulForum().textMesajeNoi(self._forumNoi)
			elif cheie == "public" and b.public.value:
				valoare = b.public.value
			elif cheie == "nota_noua":
				insigna = _("Trimiterea e oprită")
			randuri.append((_(text), cheie, _(scurt), insigna, valoare, glif, "rosu" if cheie == "iesire" else ""))
		self.randuri = randuri
		self["lista"].setList(randuri)
		self._schimbaFelul(inscris)
		if inscris:
			self._panouTester(b)
		else:
			self._invitatie()

	def _panouTester(self, b):
		self["din"].setText(_("Înscris din %s") % _dataScurta(B.oraLocala(b.acord.value)))
		nume = ""
		F = _modulForum()
		if F is not None:
			try:
				nume = F.numePublic()
			except Exception:
				nume = ""
		nume = nume or b.public.value
		self["nume"].setText(nume or _("Apari cu numele dat de forum."))
		self._ultima = B.randUltimaTrimitere()
		self["ultima"].setText(self._ultima)
		self["automat"].setText(_("(automat în fiecare zi)") if b.automat.value else "")
		numar = B.randNumar()
		if B.notaVeche(b):
			# starea spusa limpede, in caseta chihlimbar (in locul numarului de testeri)
			self["automat"].setText("")
			numar = _(B.NOTA_OPRITA)
		self["numar"].setText(numar)
		for nume_w in ("numar_fundal", "numar_bara", "numar"):
			_arata(self[nume_w], bool(numar))
		self["identificator"].setText(_("Identificatorul tău: %s\nAcordul din %s, nota de confidențialitate "
			"versiunea %d.\nPentru ștergerea datelor fără receptor, scrie la contact@hdsatelit.com cu identificatorul.")
			% (b.id.value, B.oraLocala(b.acord.value), int(b.nota.value)))

	def _invitatie(self):
		numar = B.randNumar()
		self["banda"].setText(numar)
		for nume in ("banda_fundal", "banda_bara", "banda"):
			_arata(self[nume], bool(numar))
		lista = avantaje()
		for k in range(AVANTAJE_PE_ECRAN):
			a = lista[k] if k < len(lista) else None
			for p in ("fundal_avantaj", "semn_avantaj", "titlu_avantaj", "text_avantaj"):
				_arata(self["%s%d" % (p, k)], a is not None)
			if a is None:
				continue
			glif, titlu, rand = a
			self["titlu_avantaj%d" % k].setText(titlu)
			self["text_avantaj%d" % k].setText(rand)
			_punePictograma(self["semn_avantaj%d" % k], glif)

	# ------------------------------------------------------------ OK

	def deschide(self):
		ales = self["lista"].getCurrent()
		if not ales:
			return
		cheie = ales[1]
		if cheie == "forum":
			e = ecranForum()
			if e is not None:
				self.session.openWithCallback(self._dupaForum, e)
			return
		if cheie == "acord":
			self.session.openWithCallback(self._dupaAcord, HdsBetaAcord)
			return
		if cheie == "nota_noua":
			self.session.openWithCallback(self._dupaAcord, HdsBetaNotaNoua)
			return
		if not B.inscris() and not (B.notaVeche() and cheie in ("nota", "iesire")):
			return
		if cheie == "mesaj":
			self.session.open(HdsBetaMesaj, self.ecran_dedesubt)
		elif cheie == "trimite_acum":
			_ok, text = B.trimiteAcum()
			self.session.open(MessageBox, text, MessageBox.TYPE_INFO, timeout=5)
		elif cheie == "probe":
			e = ecranProbe()
			if e is not None:
				self.session.open(e)
		elif cheie == "asistenta":
			e = ecranAsistenta()
			if e is not None:
				self.session.open(e)
		elif cheie == "canal_testeri":
			self.schimbaCanalTesteri()
		elif cheie == "trimise":
			self.session.open(HdsBetaTrimise)
		elif cheie == "raspunsuri":
			B.marcheazaVazute()
			self.session.openWithCallback(lambda *r: self.reface(), HdsBetaText, _("Răspunsurile echipei"),
				B.textRaspunsuri())
		elif cheie == "date":
			self.session.openWithCallback(lambda *r: self.reface(), HdsBetaDate)
		elif cheie == "acum":
			self.session.open(HdsBetaText, _("Ce trimit acum"), B.ultimulPachet() or _("Încă nu a plecat niciun pachet."))
		elif cheie == "public":
			self.session.openWithCallback(lambda *r: self.reface(), HdsBetaPublic)
		elif cheie == "nota":
			self.session.open(HdsBetaText, _("Nota de confidențialitate"), _(B.NOTA_SCURTA), B.ADRESA_NOTA)
		elif cheie == "iesire":
			self.session.openWithCallback(self._dupaIesire, MessageBox, _("Ieși din programul de beta testeri? Serverul "
				"șterge toate datele trimise de acest receptor, iar pe receptor nu mai rămâne nimic."),
				MessageBox.TYPE_YESNO, default=False)

	def schimbaCanalTesteri(self):
		"""OK pe "Primeste intai versiunile pentru testeri": bifa se schimba prin Components.HdsActualizari (scrie sau
		sterge sursa canalului, apoi cauta singur); pornita = nota canalului, nereusita = mesajul lui."""
		A = B.modulCanalTesteri()
		if A is None:
			return
		pornit = randCanalTesteri(A)[1]
		try:
			ok = A.actualizari.testeri(not pornit)
			mesaj = getattr(A.actualizari, "mesaj", "") or ""
		except Exception as e:
			print("[HdsBetaTester] canalul testerilor: %s" % e)
			ok, mesaj = False, ""
		self.reface()
		if ok and not pornit:
			text = _(A.TEXT_NOTA_TESTERI) if hasattr(A, "TEXT_NOTA_TESTERI") else ""
		elif ok:
			text = ""
		else:
			text = mesaj or _("Nu s-a putut.") + " " + _("Încearcă din nou.")
		if text:
			self.session.open(MessageBox, text, MessageBox.TYPE_INFO, timeout=10)

	def _dupaIesire(self, raspuns):
		if not raspuns:
			return
		_ok, text = B.iesire()
		self.session.open(MessageBox, text, MessageBox.TYPE_INFO, timeout=8)
		self.close()


# ------------------------------------------------------------------ acordul si datele (comutatoarele)

TEXT_NUME = N_("Numai ca să te putem întreba ceva despre o problemă găsită pe receptorul tău. Nu apare public.")
TEXT_EMAIL = N_("Numai pentru răspunsurile echipei. Nu apare public și se șterge la cerere.")


class _Comutatoare(object):
	"""Lista "config" cu comutatoarele felurilor de date, trimiterea automata, numele si e-mailul (si, la acord, bifa
	notei): OK, Stanga sau Dreapta schimba un comutator; OK pe nume sau e-mail deschide tastatura de pe ecran."""

	def _facLista(self):
		self["config"] = _listaDesenata()
		self.desen = _Desen(self["config"], "bife")
		self.onLayoutFinish.append(self.desen.aseaza)
		try:
			self["config"].onSelectionChanged.append(self._descriere)
		except Exception:
			pass

	def _randuri(self, cu_nota=False):
		rez = [(B.eticheta(fel), self.bife[fel], fel) for fel in B.FELURI]
		rez.append((_(B.AUTOMAT[0]), self.automat, "automat"))
		rez.append((_("Numele (opțional)"), self.nume, "nume"))
		rez.append((_("E-mailul (opțional)"), self.email, "email"))
		if cu_nota:
			rez.append((_(B.BIFA_NOTA), self.nota, "nota"))
		return rez

	def _actuala(self):
		cur = self["config"].getCurrent()
		return cur if cur and len(cur) > 2 else None

	def _redeseneaza(self):
		self["config"].setList(list(self.randuri_lista))
		self._descriere()

	def _schimba(self):
		cur = self._actuala()
		if cur is None:
			return
		el, cheie = cur[1], cur[2]
		if cheie in ("nume", "email"):
			from Components.ConfigList import deschideTastatura
			deschideTastatura(self.session, el, cur[0], lambda t: self._redeseneaza())
			return
		el.value = not el.value
		self._redeseneaza()

	def _comuta(self):
		cur = self._actuala()
		if cur is not None and cur[2] not in ("nume", "email"):
			self._schimba()

	def _sus(self):
		try:
			self["config"].up()
		except AttributeError:
			pass

	def _jos(self):
		try:
			self["config"].down()
		except AttributeError:
			pass

	def _textDescriere(self, cheie):
		if cheie in B.FELURI:
			return B.randScurt(cheie)
		if cheie == "automat":
			return _(B.AUTOMAT[1])
		if cheie == "nume":
			return _(TEXT_NUME)
		if cheie == "email":
			return _(TEXT_EMAIL)
		if cheie == "nota":
			return _("Galben deschide nota. Fără această bifă nu pleacă nimic.")
		return ""

	def _descriere(self):
		cur = self._actuala()
		self["descriere"].setText(self._textDescriere(cur[2]) if cur else "")


CORP_ACORD = """
		<widget name="antet_fundal" position="32,104" size="1712,84" backgroundColor="hdsCell" zPosition="1" />
		<widget name="antet_bara" position="32,104" size="6,84" backgroundColor="hdsGood" zPosition="2" />
		<widget name="antet" position="56,104" size="1672,84" font="HdsRegular;24" foregroundColor="hdsText" backgroundColor="hdsCell" transparent="1" valign="center" zPosition="3" />
		<widget name="config" position="32,200" size="1072,660" itemHeight="66" foregroundColor="hdsText" backgroundColor="hdsPanelDialog" backgroundColorSelected="hdsPanelDialog" foregroundColorSelected="hdsText" transparent="1" scrollbarMode="showOnDemand" enableWrapAround="1" zPosition="3" />
		<widget name="descriere" position="32,862" size="1072,58" font="HdsCond;22" foregroundColor="hdsLabel" backgroundColor="hdsPanelDialog" transparent="1" valign="top" zPosition="2" />
		<widget name="panou" position="1136,200" size="608,712" backgroundColor="hdsCell" zPosition="1" />
		<widget name="titlu_panou" position="1160,212" size="560,48" font="HdsBold;30" foregroundColor="hdsText" backgroundColor="hdsCell" transparent="1" valign="center" noWrap="1" zPosition="2" />
		<widget name="semn_avantaj0" position="1160,276" size="56,56" alphatest="blend" zPosition="2" />
		<widget name="titlu_avantaj0" position="1228,268" size="500,72" font="HdsBold;24" foregroundColor="hdsText" backgroundColor="hdsCell" transparent="1" valign="top" zPosition="2" />
		<widget name="text_avantaj0" position="1228,340" size="500,64" font="HdsCond;22" foregroundColor="hdsLabel" backgroundColor="hdsCell" transparent="1" valign="top" zPosition="2" />
		<widget name="semn_avantaj1" position="1160,416" size="56,56" alphatest="blend" zPosition="2" />
		<widget name="titlu_avantaj1" position="1228,408" size="500,72" font="HdsBold;24" foregroundColor="hdsText" backgroundColor="hdsCell" transparent="1" valign="top" zPosition="2" />
		<widget name="text_avantaj1" position="1228,480" size="500,64" font="HdsCond;22" foregroundColor="hdsLabel" backgroundColor="hdsCell" transparent="1" valign="top" zPosition="2" />
		<widget name="semn_avantaj2" position="1160,556" size="56,56" alphatest="blend" zPosition="2" />
		<widget name="titlu_avantaj2" position="1228,548" size="500,72" font="HdsBold;24" foregroundColor="hdsText" backgroundColor="hdsCell" transparent="1" valign="top" zPosition="2" />
		<widget name="text_avantaj2" position="1228,620" size="500,64" font="HdsCond;22" foregroundColor="hdsLabel" backgroundColor="hdsCell" transparent="1" valign="top" zPosition="2" />
		<widget name="numar" position="1160,700" size="560,72" font="HdsRegular;24" foregroundColor="hdsAmber" backgroundColor="hdsCell" transparent="1" valign="center" zPosition="2" />
		<widget name="stare" position="1160,784" size="560,120" font="HdsRegular;24" foregroundColor="hdsText" backgroundColor="hdsCell" transparent="1" valign="top" zPosition="2" />"""


class HdsBetaAcord(Screen, _Comutatoare):
	skin = _rezerva("HdsBetaAcord", "Beta tester", CORP_ACORD, ("key_red", "key_green", "key_yellow"))

	def __init__(self, session):
		Screen.__init__(self, session)
		self.setTitle(_("Devino beta tester"))
		b = B.initConfig()
		inapoi = B.notaVeche(b)
		self.bife = dict((fel, ConfigYesNo(default=bool(getattr(b, fel).value) if inapoi else True)) for fel in B.FELURI)
		self.automat = ConfigYesNo(default=bool(b.automat.value) if inapoi else True)
		self.nume = ConfigText(default=b.nume.value, fixed_size=False)
		self.email = ConfigText(default=b.email.value, fixed_size=False)
		self.nota = ConfigYesNo(default=False)
		for nume in ("antet_fundal", "antet_bara", "panou", "titlu_panou", "numar"):
			self[nume] = Label("")
		self["antet"] = Label(_(B.ANTET_ACORD))
		self["titlu_panou"].setText(_("Ce primești ca beta tester"))
		for k in range(AVANTAJE_PE_ECRAN):
			self["semn_avantaj%d" % k] = Pixmap()
			self["titlu_avantaj%d" % k] = Label("")
			self["text_avantaj%d" % k] = Label("")
		self._numar = ""
		from enigma import eTimer
		self.ceasNumar = eTimer()
		self.ceasNumar.callback.append(self._numarul)
		self.onClose.append(self.ceasNumar.stop)
		B.ceNumar()
		self.ceasNumar.start(1000, False)
		self["descriere"] = Label("")
		self["stare"] = Label(_("Nota de confidențialitate s-a schimbat: citește-o și dă din nou acordul.")
			if inapoi else "")
		self["key_red"] = Button(_("Renunț"))
		self["key_green"] = Button(_("Sunt de acord"))
		self["key_yellow"] = Button(_("Nota de confidențialitate"))
		self._facLista()
		self.randuri_lista = self._randuri(cu_nota=True)
		self["config"].setList(list(self.randuri_lista))
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], _cuCulori(_cuDirectii({
			"ok": self._schimba,
			"green": self.deAcord,
			"yellow": self.arataNota,
			"cancel": self.renunta,
			"red": self.renunta,
		}, self._sus, self._jos, self._comuta, self._comuta)), -2)
		self.onLayoutFinish.append(self._avantaje)
		self._descriere()
		self._numarul()

	def _avantaje(self):
		lista = avantaje()
		for k in range(AVANTAJE_PE_ECRAN):
			a = lista[k] if k < len(lista) else None
			for p in ("semn_avantaj", "titlu_avantaj", "text_avantaj"):
				_arata(self["%s%d" % (p, k)], a is not None)
			if a is not None:
				self["titlu_avantaj%d" % k].setText(a[1])
				self["text_avantaj%d" % k].setText(a[2])
				_punePictograma(self["semn_avantaj%d" % k], a[0])

	def _numarul(self):
		B._culegeNumar()
		rand = B.randNumar()
		if rand != self._numar:
			self._numar = rand
			self["numar"].setText(rand)
		if B._starea.get("cerere_numar") is None:
			self.ceasNumar.stop()

	def arataNota(self):
		self.session.open(HdsBetaText, _("Nota de confidențialitate"), _(B.NOTA_SCURTA), B.ADRESA_NOTA)

	def deAcord(self):
		if not self.nota.value:
			self["stare"].setText(_("Bifează întâi „%s”") % _(B.BIFA_NOTA))
			return
		if not any(c.value for c in self.bife.values()):
			self["stare"].setText(_("Bifează cel puțin un fel de date sau alege Renunț."))
			return
		ok, text = B.acceptaAcord(dict((fel, c.value) for fel, c in self.bife.items()), self.nume.value,
			self.email.value, automat=self.automat.value)
		if not ok:
			self["stare"].setText(text)
			return
		self.session.openWithCallback(lambda *r: self.close(True), MessageBox, text, MessageBox.TYPE_INFO, timeout=6)

	def renunta(self):
		self.close(False)


# ------------------------------------------------------------------ nota noua: anuntul si nota intreaga

CORP_NOTA_NOUA = """
		<widget name="antet_fundal" position="32,104" size="1712,124" backgroundColor="hdsCell" zPosition="1" />
		<widget name="antet_bara" position="32,104" size="6,124" backgroundColor="hdsAmber" zPosition="2" />
		<widget name="antet" position="60,104" size="1664,124" font="HdsRegular;32" foregroundColor="hdsText" backgroundColor="hdsCell" transparent="1" valign="center" zPosition="3" />
		<widget name="titlu_nou" position="32,248" size="1712,44" font="HdsBold;30" foregroundColor="hdsAmber" backgroundColor="hdsPanelDialog" transparent="1" valign="center" noWrap="1" zPosition="2" />
		<widget name="noutati" position="32,296" size="1712,272" font="HdsRegular;28" foregroundColor="hdsText2" backgroundColor="hdsPanelDialog" transparent="1" valign="top" zPosition="2" />
		<eLabel position="32,580" size="1712,1" backgroundColor="hdsDivider" zPosition="1" />
		<widget name="lista" position="32,596" size="1072,228" itemHeight="76" foregroundColor="hdsText" backgroundColor="hdsPanelDialog" backgroundColorSelected="hdsPanelDialog" foregroundColorSelected="hdsText" transparent="1" scrollbarMode="showNever" enableWrapAround="1" zPosition="3" />
		<widget name="rand_accept" position="32,832" size="1072,84" font="HdsCond;24" foregroundColor="hdsLabel" backgroundColor="hdsPanelDialog" transparent="1" valign="top" zPosition="2" />
		<widget source="qr" render="Canvas" position="1544,604" size="200,200" zPosition="3" />
		<widget name="adresa" position="1136,812" size="608,104" font="HdsCond;22" foregroundColor="hdsLabel" backgroundColor="hdsPanelDialog" transparent="1" halign="right" valign="top" zPosition="2" />"""


class HdsBetaNotaNoua(Screen):
	"""Anuntul notei noi: ce s-a schimbat, „Citeste nota intreaga” (pe receptor), „Accept” (acordul nou cu alegerile de
	dinainte), „Mai tarziu” (revine maine). Codul QR, mic, in colt, pentru cine vrea sa citeasca pe telefon. Iesirea
	din program ramane in meniul Beta tester. Se inchide cu True dupa Accept."""
	skin = _rezerva("HdsBetaNotaNoua", "Beta tester", CORP_NOTA_NOUA, ("key_red", "key_green", "key_yellow"))

	ORDINE = ("citeste", "accept", "mai_tarziu")
	GLIFE_BUTOANE = {"citeste": "informatii", "accept": "noutati", "mai_tarziu": "ceas"}

	def __init__(self, session):
		Screen.__init__(self, session)
		self.setTitle(_(B.NOTA_ANUNT_TITLU))
		for nume in ("antet_fundal", "antet_bara"):
			self[nume] = Label("")
		self["antet"] = Label(_(B.NOTA_ANUNT))
		self["titlu_nou"] = Label(_("Ce e nou"))
		self["noutati"] = Label("\n".join("•  " + t for t in B.noutatiNota()))
		self["rand_accept"] = Label(_(B.NOTA_ACCEPT_RAND))
		self["qr"] = CanvasSource()
		self["adresa"] = Label(_("Sau citește pe telefon:") + "\n" + B.adresaNotei().replace("https://", "").rstrip("/"))
		self["lista"] = _listaDesenata()
		self.desen = _Desen(self["lista"], "meniu")
		randuri = []
		for cheie in self.ORDINE:
			titlu, rand = B.NOTA_BUTOANE[cheie]
			randuri.append((_(titlu), cheie, _(rand), "", "", self.GLIFE_BUTOANE[cheie], ""))
		self.randuri = randuri
		self["lista"].setList(randuri)
		self["key_red"] = Button(_(B.NOTA_BUTOANE["mai_tarziu"][0]))
		self["key_green"] = Button(_(B.NOTA_BUTOANE["accept"][0]))
		self["key_yellow"] = Button(_(B.NOTA_BUTOANE["citeste"][0]))
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions"], _cuCulori({
			"ok": self.deschide,
			"green": self.accept,
			"yellow": self.citeste,
			"red": self.maiTarziu,
			"cancel": self.maiTarziu,
		}), -2)
		self.onLayoutFinish.append(self._asezare)

	def _asezare(self):
		self.desen.aseaza()
		_deseneazaQr(self, "qr", B.adresaNotei())

	def _alege(self, cheie):
		try:
			self["lista"].moveToIndex(self.ORDINE.index(cheie))
		except Exception:
			pass

	def deschide(self):
		ales = self["lista"].getCurrent()
		cheie = ales[1] if ales else "citeste"
		if cheie == "accept":
			self.accept()
		elif cheie == "mai_tarziu":
			self.maiTarziu()
		else:
			self.citeste()

	def citeste(self):
		"""Nota intreaga pe receptor, din copia din imagine; fara ea, pagina notei in navigatorul receptorului."""
		nota = B.textNota()
		if nota is not None:
			self.session.openWithCallback(self._dupaCitire, HdsBetaNotaText, nota[0], nota[1])
			return
		try:
			from Plugins.Extensions.HdsNavigator.plugin import deschideNavigator
			deschideNavigator(self.session, B.adresaNotei())
			self._alege("accept")
		except Exception as e:
			_jurnal("navigatorul pentru nota: %r" % (e,))
			self.session.open(MessageBox, _("Nota întreagă e la adresa:") + "\n" + B.adresaNotei(), MessageBox.TYPE_INFO,
				timeout=15)

	def _dupaCitire(self, *_r):
		# dupa citire, alegerea sta pe Accept
		self._alege("accept")

	def accept(self):
		ok, text = B.acceptaNotaNoua()
		if not ok:
			self.session.open(MessageBox, text, MessageBox.TYPE_INFO, timeout=6)
			return
		self.session.openWithCallback(lambda *r: self.close(True), MessageBox, text, MessageBox.TYPE_INFO, timeout=5)

	def maiTarziu(self):
		B.amanaAnuntNota()
		self.close(False)


CORP_NOTA_TEXT = """
		<widget name="text" position="32,104" size="1712,808" font="HdsRegular;30" foregroundColor="hdsText" backgroundColor="hdsPanelDialog" transparent="1" zPosition="2" />"""


class HdsBetaNotaText(Screen):
	"""Nota intreaga pe receptor, pe toata latimea, cu literele mari: Sus/Jos si Stanga/Dreapta dau pagina, EXIT, OK
	sau Rosu intorc la anunt."""
	skin = _rezerva("HdsBetaNotaText", "Beta tester", CORP_NOTA_TEXT, ("key_red",))

	def __init__(self, session, titlu, text):
		Screen.__init__(self, session)
		self.setTitle(titlu)
		self["text"] = ScrollLabel(text)
		self["key_red"] = Button(_("Înapoi"))
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], _cuCulori(_cuDirectii({
			"cancel": self.close,
			"ok": self.close,
			"red": self.close,
		}, self._sus, self._jos, self._sus, self._jos)), -2)

	def _sus(self):
		self["text"].pageUp()

	def _jos(self):
		self["text"].pageDown()


CORP_DATE = """
		<widget name="config" position="32,104" size="1712,594" itemHeight="66" foregroundColor="hdsText" backgroundColor="hdsPanelDialog" backgroundColorSelected="hdsPanelDialog" foregroundColorSelected="hdsText" transparent="1" scrollbarMode="showOnDemand" enableWrapAround="1" zPosition="3" />
		<eLabel position="32,712" size="1712,1" backgroundColor="hdsDivider" zPosition="1" />
		<widget name="descriere" position="32,724" size="1712,84" font="HdsRegular;26" foregroundColor="hdsText2" backgroundColor="hdsPanelDialog" transparent="1" valign="top" zPosition="2" />
		<widget name="stare" position="32,816" size="1712,96" font="HdsRegular;26" foregroundColor="hdsAmber" backgroundColor="hdsPanelDialog" transparent="1" valign="top" zPosition="2" />"""


class HdsBetaDate(Screen, _Comutatoare):
	skin = _rezerva("HdsBetaDate", "Datele pe care le trimit", CORP_DATE, ("key_red", "key_green"))

	def __init__(self, session):
		Screen.__init__(self, session)
		self.setTitle(_("Datele pe care le trimit"))
		b = B.initConfig()
		self.bife = dict((fel, ConfigYesNo(default=bool(getattr(b, fel).value))) for fel in B.FELURI)
		self.automat = ConfigYesNo(default=bool(b.automat.value))
		self.nume = ConfigText(default=b.nume.value, fixed_size=False)
		self.email = ConfigText(default=b.email.value, fixed_size=False)
		self["descriere"] = Label("")
		self["stare"] = Label(_("Un fel debifat nu mai pleacă de acum; serverul îl refuză și el."))
		self["key_red"] = Button(_("Cancel"))
		self["key_green"] = Button(_("Save"))
		self._facLista()
		self.randuri_lista = self._randuri()
		self["config"].setList(list(self.randuri_lista))
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], _cuCulori(_cuDirectii({
			"ok": self._schimba,
			"green": self.salveaza,
			"cancel": self.close,
			"red": self.close,
		}, self._sus, self._jos, self._comuta, self._comuta)), -2)
		self._descriere()

	def salveaza(self):
		ok, text = B.schimbaBife(dict((fel, c.value) for fel, c in self.bife.items()), self.nume.value,
			self.email.value, automat=self.automat.value)
		if ok:
			self.session.openWithCallback(lambda *r: self.close(), MessageBox, text, MessageBox.TYPE_INFO, timeout=5)
		else:
			self["stare"].setText(text)


# ------------------------------------------------------------------ textele lungi, "Ce am trimis", mesajul

CORP_TEXT = """
		<widget name="text" position="32,104" size="1200,808" font="HdsRegular;28" foregroundColor="hdsText" backgroundColor="hdsPanelDialog" transparent="1" zPosition="2" />
		<widget source="qr" render="Canvas" position="1284,120" size="420,420" zPosition="3" />
		<widget name="adresa" position="1256,556" size="476,150" font="HdsCond;24" foregroundColor="hdsLabel" backgroundColor="hdsPanelDialog" transparent="1" halign="center" valign="top" zPosition="2" />"""


class HdsBetaText(Screen):
	skin = _rezerva("HdsBetaText", "Beta tester", CORP_TEXT, ("key_red",))

	def __init__(self, session, titlu, text, adresa=""):
		Screen.__init__(self, session)
		self.setTitle(titlu)
		self.adresa = adresa
		self["text"] = ScrollLabel(text)
		self["qr"] = CanvasSource()
		self["adresa"] = Label((_("Scanează cu telefonul sau deschide:") + "\n" + B.ADRESA_NOTA_SCURTA) if adresa
			else "")
		self["key_red"] = Button(_("Înapoi"))
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], _cuCulori(_cuDirectii({
			"cancel": self.close,
			"ok": self.close,
			"red": self.close,
		}, self._sus, self._jos, self._sus, self._jos)), -2)
		self.onLayoutFinish.append(self._qr)

	def _sus(self):
		self["text"].pageUp()

	def _jos(self):
		self["text"].pageDown()

	def _qr(self):
		if self.adresa:
			_deseneazaQr(self, "qr", self.adresa)
			return
		# fara adresa (Ce trimit acum, raspunsurile): locul codului ascuns, nu un patrat gol
		for r in getattr(self, "renderer", []) or []:
			if getattr(r, "source", None) is self["qr"] and getattr(r, "instance", None) is not None:
				r.instance.hide()


CORP_TRIMISE = """
		<widget name="lista" position="32,104" size="1712,756" itemHeight="54" font="HdsRegular;28" foregroundColor="hdsText" backgroundColor="hdsPanelDialog" backgroundColorSelected="hdsBrand" foregroundColorSelected="white" transparent="1" scrollbarMode="showOnDemand" zPosition="2" />
		<widget name="text" position="32,868" size="1712,48" font="HdsCond;24" foregroundColor="hdsLabel" backgroundColor="hdsPanelDialog" transparent="1" valign="center" noWrap="1" zPosition="2" />"""


class HdsBetaTrimise(Screen):
	skin = _rezerva("HdsBetaTrimise", "Ce am trimis", CORP_TRIMISE, ("key_red",))

	def __init__(self, session):
		Screen.__init__(self, session)
		self.setTitle(_("Ce am trimis"))
		randuri = ["%s   ·   %s   ·   %s   ·   %s" % r for r in B.randuriTrimise()]
		self["lista"] = MenuList(randuri or [_("Încă nu a plecat nimic.")])
		self["text"] = Label(_("Ultimele %d, cel mai nou sus. Fără internet, pachetele așteaptă în coadă.") %
			B.TRIMISE_MAX)
		self["key_red"] = Button(_("Înapoi"))
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions"], _cuCulori({
			"cancel": self.close,
			"ok": self.close,
			"red": self.close,
		}), -2)


# mesajul care asteapta captura (dupa CAPTURA_ASTEPTARE_S secunde, cu ecranele inchise)
_asteptare = {"timer": None, "mesaj": None}


def _capturaSiMesaj():
	m = _asteptare.get("mesaj")
	_asteptare["mesaj"] = None
	if not m:
		return
	captura = B.capturaOsd()
	ok, text = B.mesaj(m["fel"], m["text"], m["ecran"], m["jurnal"], captura, contor=B.contor())
	print("[HdsBetaTester] mesajul cu captura: %s (%s)" % (ok, "captura" if captura else "fara captura"))


def _programeazaCaptura(mesaj_):
	from enigma import eTimer
	t = _asteptare.get("timer")
	if t is None:
		t = eTimer()
		t.callback.append(_capturaSiMesaj)
		_asteptare["timer"] = t
	_asteptare["mesaj"] = mesaj_
	t.start(B.CAPTURA_ASTEPTARE_S * 1000, True)


CORP_MESAJ = """
		<widget name="config" position="32,104" size="1712,300" itemHeight="60" font="HdsRegular;30" secondfont="HdsBold;28" foregroundColor="hdsText" backgroundColor="hdsPanelDialog" backgroundColorSelected="hdsBrand" foregroundColorSelected="white" transparent="1" scrollbarMode="showOnDemand" zPosition="2" />
		<eLabel position="32,420" size="1712,236" backgroundColor="hdsCell" zPosition="1" />
		<widget name="text" position="52,432" size="1672,212" font="HdsRegular;28" foregroundColor="hdsText" backgroundColor="hdsCell" transparent="1" valign="top" zPosition="2" />
		<widget name="stare" position="32,672" size="1712,240" font="HdsRegular;26" foregroundColor="hdsText2" backgroundColor="hdsPanelDialog" transparent="1" valign="top" zPosition="2" />"""


class HdsBetaMesaj(Screen, ConfigListScreen):
	skin = _rezerva("HdsBetaMesaj", "Trimite un mesaj", CORP_MESAJ, ("key_red", "key_green", "key_yellow"))

	def __init__(self, session, ecran=""):
		Screen.__init__(self, session)
		self.setTitle(_("Trimite un mesaj"))
		self.fel = ConfigSelection(choices=[(f, _(B.FELURI_MESAJ_TEXT[f])) for f in B.FELURI_MESAJ], default="greseala")
		self.textul = ConfigText(default="", fixed_size=False)
		self.ecran = ConfigText(default=ecran or "", fixed_size=False)
		self.jurnal = ConfigYesNo(default=False)
		self.captura = ConfigYesNo(default=False)
		self["text"] = Label("")
		self["stare"] = Label(_("Mesajul pleacă cu identificatorul anonim al receptorului, ca toate datele. "
			"Răspunsul echipei apare în „Răspunsurile echipei”."))
		self["key_red"] = Button(_("Cancel"))
		self["key_green"] = Button(_("Trimite"))
		self["key_yellow"] = Button(_("Scrie mesajul"))
		self.list = [
			getConfigListEntry(_("Felul"), self.fel),
			getConfigListEntry(_("Mesajul"), self.textul),
			getConfigListEntry(_("Ecranul sau funcția (opțional)"), self.ecran),
			getConfigListEntry(_("Atașează jurnalul ultimei erori"), self.jurnal),
			getConfigListEntry(_("Atașează o captură a ecranului (numai meniurile)"), self.captura),
		]
		ConfigListScreen.__init__(self, self.list, session=session)
		self["actiuni"] = ActionMap(["SetupActions", "ColorActions"], _cuSetup(self, _cuCulori({
			"ok": self.keyOK,
			"green": self.trimite,
			"yellow": self.scrie,
			"cancel": self.close,
			"red": self.close,
		})), -2)
		self._arata()

	def _arata(self):
		self["text"].setText(self.textul.value or _("Galben: scrie mesajul cu tastatura de pe ecran."))

	def scrie(self):
		from Components.ConfigList import deschideTastatura
		deschideTastatura(self.session, self.textul, _("Mesajul"), lambda t: self._arata())

	def keyOK(self):
		ConfigListScreen.keyOK(self)
		self._arata()

	def trimite(self):
		text = (self.textul.value or "").strip()
		if not text:
			self["stare"].setText(_("Scrie întâi mesajul."))
			return
		if self.captura.value:
			_programeazaCaptura({"fel": self.fel.value, "text": text, "ecran": self.ecran.value,
				"jurnal": bool(self.jurnal.value)})
			self.session.open(MessageBox, _("Ai %d secunde: închide meniurile și deschide ecranul despre care scrii. "
				"Captura se face singură, numai cu meniurile, apoi mesajul pleacă.") % B.CAPTURA_ASTEPTARE_S,
				MessageBox.TYPE_INFO, timeout=5)
			self.close()
			return
		ok, mesaj = B.mesaj(self.fel.value, text, self.ecran.value, bool(self.jurnal.value), None, contor=B.contor())
		if ok:
			self.session.openWithCallback(lambda *r: self.close(), MessageBox, mesaj, MessageBox.TYPE_INFO, timeout=5)
		else:
			self["stare"].setText(mesaj)


# ------------------------------------------------------------------ aparitia publica si legarea unui cont

CORP_PUBLIC = """
		<widget name="text" position="32,104" size="1712,120" font="HdsRegular;28" foregroundColor="hdsText2" backgroundColor="hdsPanelDialog" transparent="1" valign="top" zPosition="2" />
		<widget name="config" position="32,236" size="1712,180" itemHeight="60" font="HdsRegular;30" secondfont="HdsBold;28" foregroundColor="hdsText" backgroundColor="hdsPanelDialog" backgroundColorSelected="hdsBrand" foregroundColorSelected="white" transparent="1" scrollbarMode="showOnDemand" zPosition="2" />
		<eLabel position="32,432" size="1712,1" backgroundColor="hdsDivider" zPosition="1" />
		<widget name="stare" position="32,448" size="1712,464" font="HdsRegular;28" foregroundColor="hdsText" backgroundColor="hdsPanelDialog" transparent="1" valign="top" zPosition="2" />"""


class HdsBetaPublic(Screen, ConfigListScreen):
	skin_fara_forum = _rezerva("HdsBetaPublic", "Apariția publică", CORP_PUBLIC, ("key_red", "key_green", "key_blue"))
	skin = _rezerva("HdsBetaPublic", "Apariția publică", CORP_PUBLIC, TOATE_TASTELE)

	def __init__(self, session):
		self.forum = B.legareForum()
		if not self.forum:
			self.skin = HdsBetaPublic.skin_fara_forum
		Screen.__init__(self, session)
		self.setTitle(_("Apariția publică"))
		b = B.initConfig()
		self.nume = ConfigText(default=b.public.value, fixed_size=False)
		self.email = ConfigText(default="", fixed_size=False)
		self.cod = ConfigText(default="", fixed_size=False)
		self["text"] = Label(_("Opțional: apari cu un nume ales de tine pe pagina testerilor de pe site și la "
			"modelul tău. Fără parole pe receptor.") + ((" " + _("E-mailul (opțional) îți face un cont pe forum: "
			"primești o legătură și îți pui parola acolo, de pe orice aparat.")) if self.forum else ""))
		self["stare"] = Label(_("Se citește starea..."))
		self["key_red"] = Button(_("Înapoi"))
		self["key_green"] = Button(_("Salvează"))
		if self.forum:
			self["key_yellow"] = Button(_("Cod QR pentru telefon"))
		self["key_blue"] = Button(_("Nu mai apar public"))
		self.list = [getConfigListEntry(_("Numele public"), self.nume)]
		if self.forum:
			self.list.append(getConfigListEntry(_("E-mailul pentru cont (opțional)"), self.email))
			self.list.append(getConfigListEntry(_("Codul de 6 cifre de pe site (OK după ce îl scrii)"), self.cod))
		ConfigListScreen.__init__(self, self.list, session=session)
		self["actiuni"] = ActionMap(["SetupActions", "ColorActions"], _cuSetup(self, _cuCulori({
			"ok": self.keyOK,
			"green": self.salveaza,
			"yellow": self.qr,
			"blue": self.dezleaga,
			"cancel": self.close,
			"red": self.close,
		})), -2)
		self._cerere = None
		self._dupa = None
		from enigma import eTimer
		self.ceas = eTimer()
		self.ceas.callback.append(self._asteapta)
		self.onClose.append(self.ceas.stop)
		# metoda legata, nu lambda: GUISkin.applySkin da lui exec() tot ce nu e metoda legata (codul din skin)
		self.onLayoutFinish.append(self._citesteProfilul)

	def _citesteProfilul(self):
		self._porneste("profil-stare", self._arataProfil)

	def _porneste(self, ruta, dupa, **campuri):
		if self._cerere is not None:
			return
		self._cerere = B.cerereProfil(ruta, **campuri)
		if self._cerere is None:
			self["stare"].setText(_("Nu ești înscris în programul de beta testeri."))
			return
		self._dupa = dupa
		self["stare"].setText(_("Se trimite..."))
		self.ceas.start(500, False)

	def _asteapta(self):
		c = self._cerere
		if c is None or not c.gata:
			return
		self.ceas.stop()
		self._cerere = None
		ok, text = B.mesajRaspunsProfil(c)
		if not ok:
			self["stare"].setText(text)
			return
		self._dupa(c.raspuns)

	def _arataProfil(self, raspuns):
		profil = raspuns.get("profil")
		b = B.initConfig()
		vechi = b.public.value
		b.public.value = (profil or {}).get("nume_public") or ""
		B.salveaza(b)
		# numele de pe server (schimbat poate din forum sau din pagina web) intra si in camp, daca omul nu l-a
		# schimbat inca aici
		if self.nume.value == vechi and self.nume.value != b.public.value:
			self.nume.value = b.public.value
			self["config"].setList(self.list)
		self["stare"].setText(B.textProfil(profil))

	def _dupaSalvare(self, raspuns):
		self._arataProfil(raspuns)
		uitaJetonulForumului()

	def keyOK(self):
		cur = self["config"].getCurrent()
		if cur and cur[1] is self.cod and self.cod.value:
			self.leaga()
			return
		ConfigListScreen.keyOK(self)

	def salveaza(self):
		nume = B.textNume(self.nume.value, B.NUME_PUBLIC_MAX)
		email = B.textNume(self.email.value, B.EMAIL_MAX)
		if nume and not B.numePublicValid(nume):
			self["stare"].setText(_("Numele public are 2-40 de semne: litere, cifre, spațiu, punct, liniuță."))
			return
		if not B.emailValid(email):
			self["stare"].setText(_("Adresa de e-mail nu pare bună."))
			return
		campuri = {"nume_public": nume or None}
		if self.forum:
			campuri["email"] = email or None
		self._porneste("profil", self._dupaSalvare, **campuri)

	def leaga(self):
		cod = (self.cod.value or "").strip()
		if not B._COD6.match(cod):
			self["stare"].setText(_("Codul are 6 cifre. Îl vezi pe site, pe pagina de legare, când ești conectat."))
			return
		self._porneste("leaga", self._dupaSalvare, cod=cod)

	def dezleaga(self):
		self._porneste("dezleaga", self._dupaSalvare)

	def qr(self):
		if not self.forum:
			return
		self.session.openWithCallback(lambda *r: self._porneste("profil-stare", self._arataProfil), HdsBetaLegareQr)


CORP_LEGARE = """
		<widget name="text" position="32,104" size="1160,808" font="HdsRegular;28" foregroundColor="hdsText" backgroundColor="hdsPanelDialog" transparent="1" valign="top" zPosition="2" />
		<widget source="qr" render="Canvas" position="1264,120" size="440,440" zPosition="3" />
		<widget name="adresa" position="1224,576" size="520,150" font="HdsCond;24" foregroundColor="hdsLabel" backgroundColor="hdsPanelDialog" transparent="1" halign="center" valign="top" zPosition="2" />"""


class HdsBetaLegareQr(Screen):
	skin = _rezerva("HdsBetaLegareQr", "Leagă cu contul de pe forum", CORP_LEGARE, ("key_red",))

	def __init__(self, session):
		Screen.__init__(self, session)
		self.setTitle(_("Leagă cu contul de pe forum"))
		self["text"] = Label(_("Se cere un cod de legare..."))
		self["qr"] = CanvasSource()
		self["adresa"] = Label("")
		self["key_red"] = Button(_("Înapoi"))
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions"], _cuCulori({
			"cancel": self.close,
			"ok": self.close,
			"red": self.close,
		}), -2)
		self._cerere = None
		self._adresa = ""
		self._incercari = 0
		from enigma import eTimer
		self.ceas = eTimer()
		self.ceas.callback.append(self._asteapta)
		self.stare = eTimer()
		self.stare.callback.append(self._cereStarea)
		self.onClose.append(self.ceas.stop)
		self.onClose.append(self.stare.stop)
		self.onLayoutFinish.append(self._cereCod)

	def _cereCod(self):
		self._cerere = B.cerereProfil("cod-legare")
		if self._cerere is not None:
			self.ceas.start(500, False)

	def _cereStarea(self):
		self._incercari += 1
		if self._incercari * B.STARE_LEGARE_S > B.LEGARE_MAX_S:
			self.stare.stop()
			self["text"].setText(_("Codul a expirat. Deschide din nou ecranul pentru un cod nou."))
			return
		if self._cerere is None:
			self._cerere = B.cerereProfil("profil-stare")
			if self._cerere is not None:
				self.ceas.start(500, False)

	def _asteapta(self):
		c = self._cerere
		if c is None or not c.gata:
			return
		self.ceas.stop()
		self._cerere = None
		ok, text = B.mesajRaspunsProfil(c)
		if not ok:
			self["text"].setText(text)
			self.stare.stop()
			return
		if "cod" in c.raspuns and "adresa" in c.raspuns:
			self._adresa = str(c.raspuns.get("adresa") or "")[:200]
			if not self._adresa.startswith("https://"):
				self["text"].setText(_("Serverul a dat o adresă greșită."))
				return
			_deseneazaQr(self, "qr", self._adresa)
			self["adresa"].setText(self._adresa.replace("https://", ""))
			self["text"].setText(_("Scanează codul cu telefonul pe care ești conectat pe forumul imaginii și apasă "
				"„Leagă și arată-mă ca tester”. Codul e valabil 10 minute și se folosește o singură dată."))
			self.stare.start(B.STARE_LEGARE_S * 1000, False)
			return
		profil = c.raspuns.get("profil")
		if profil and profil.get("cont"):
			self.stare.stop()
			b = B.initConfig()
			b.public.value = profil.get("nume_public") or ""
			B.salveaza(b)
			self["text"].setText(B.textProfil(profil))
