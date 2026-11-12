# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsVpnFurnizor.py: ecranul "Furnizorul VPN, fără fișiere", deschis din ecranul VPN (Screens/HdsVpn.py). Omul alege
# furnizorul (STANGA/DREAPTA sau OK pentru lista), scrie contul (tastatura de pe ecran; dupa salvare nu se mai arata)
# si alege tara; receptorul pune serverele tarii si porneste VPN-ul. Contul salvat nu se mai cere. Pentru furnizorii
# fara cale oficiala ecranul arata de unde iei fisierele (se importa apoi din ecranul VPN).
#
# Sus: titlul si starea VPN-ului; apoi randurile (furnizorul, contul, tara, stergerea contului, "Inchide"); sub lista
# explicatia randului ales si rezultatul ultimei lucrari. VERDE pune VPN-ul pentru tara aleasa.
#
# Toata logica e in Components/HdsVpnFurnizori.py (aceeasi in pagina web /vpn-furnizor): ecranul citeste stare() la
# fiecare CITIRE_MS si porneste lucrarile (lista tarilor, configurarea) pe firul lor; nicio cerere pe internet pe firul
# enigma2. Skinul se face la deschidere dupa marimea ecranului si marimea literelor, cu culorile ecranului VPN; un bloc
# <screen name="HdsVpnFurnizor"> din skin are intaietate.

from time import time

from enigma import eTimer, getDesktop

from .Screen import Screen
from .MessageBox import MessageBox
from .ChoiceBox import ChoiceBox
from .VirtualKeyBoard import VirtualKeyBoard
from Components.ActionMap import ActionMap
from Components.MenuList import MenuList
from Components.Sources.StaticText import StaticText
from Components import HdsVpnFurnizori as F

CITIRE_MS = 1000
MESAJ_S = 15

# asezarea la 1920x1080 si litere 100 %: (nume, inaltime, font, spatiu dupa, creste)
LATIME = 1400
MARGINE = 40
CONTINUT = 1320
SUS = 16
JOS = 12
BLOCURI = (
	("titlu", 56, 42, 4, False),
	("stare", 44, 30, 8, True),
	("list", None, 30, 12, True),
	("rand", 144, 26, 4, True),
	("mesaj", 72, 26, 8, True),
	("butoane", 40, 24, 0, True),
)
LISTA_RAND = 44
LISTA_MAX = 7
LISTA_MIN = 3
LISTA_TEXT = 16
INALTIME_MAX = 1046
BUTON_LATIME = 300


def _procentLitere():
	try:
		import skin
		return int(skin.getFontScalePercent())
	except Exception:
		return 100


def asezare(latime, inaltime, procent=None):
	"""Pozitiile si marimile ecranului: {nume: (x, y, l, h, font)}, "fereastra", "randuri", "rand_lista"."""
	if procent is None:
		procent = _procentLitere()
	f = min(inaltime / 1080.0, (latime - 40) / float(LATIME))
	m = procent / 100.0

	def px(x):
		return max(1, int(round(x * f)))

	def text(x):
		return max(1, int(round(x * f * m)))

	def inalt(h, creste):
		return text(h) if creste else px(h)

	def font(x, creste):
		return px(x) if creste else max(1, int(round(x * f / m)))

	rand_lista = text(LISTA_RAND)
	fix = px(SUS) + px(JOS)
	for _nume, h, _font, dupa, creste in BLOCURI:
		fix += px(dupa) + (inalt(h, creste) if h is not None else 0)
	loc = px(INALTIME_MAX) - fix
	randuri = max(LISTA_MIN, min(LISTA_MAX, loc // rand_lista))
	a = {"randuri": randuri, "rand_lista": rand_lista}
	x, l = px(MARGINE), px(CONTINUT)
	y = px(SUS)
	for nume, h, fnt, dupa, creste in BLOCURI:
		h = rand_lista * randuri if h is None else inalt(h, creste)
		a[nume] = (x, y, l, h, font(fnt, creste))
		y += h + px(dupa)
	a["fereastra"] = (px(LATIME), y + px(JOS))
	return a


def skinRezerva(latime, inaltime, procent=None):
	a = asezare(latime, inaltime, procent)
	v = {"pl": a["fereastra"][0], "ph": a["fereastra"][1], "linie": max(1, a["rand"][4] // 14)}
	for nume in ("titlu", "stare", "list", "rand", "mesaj", "butoane"):
		x, y, l, h, font = a[nume]
		v[nume] = "%d,%d" % (x, y)
		v[nume + "_m"] = "%d,%d" % (l, h)
		v[nume + "_f"] = font
	v["li"] = a["rand_lista"]
	v["lo"] = max(1, LISTA_TEXT * a["rand"][4] // 26)
	x, y, l, h, font = a["butoane"]
	bw = max(1, BUTON_LATIME * a["rand"][4] // 26)
	v["verde"] = "%d,%d" % (x + l - bw, y)
	v["buton_m"] = "%d,%d" % (bw, h)
	v["ajutor_m"] = "%d,%d" % (max(1, l - bw - font), h)
	return """
	<screen name="HdsVpnFurnizor" position="center,center" size="%(pl)d,%(ph)d" flags="wfNoBorder" backgroundColor="#00101828" title="VPN">
		<eLabel position="0,0" size="%(pl)d,%(linie)d" backgroundColor="#00ffffff" zPosition="1" />
		<widget source="titlu" render="Label" position="%(titlu)s" size="%(titlu_m)s" font="Regular;%(titlu_f)d" valign="center" foregroundColor="#00f2f4f8" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget source="stare" render="Label" position="%(stare)s" size="%(stare_m)s" font="Regular;%(stare_f)d" valign="center" foregroundColor="#00c9d2e3" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget name="list" position="%(list)s" size="%(list_m)s" itemHeight="%(li)d" font="Regular;%(list_f)d" foregroundColor="#00f2f4f8" backgroundColor="#00101828" backgroundColorSelected="#00374ea1" foregroundColorSelected="#00ffffff" transparent="1" scrollbarMode="showOnDemand" textOffset="%(lo)d,0" zPosition="2" />
		<widget source="rand" render="Label" position="%(rand)s" size="%(rand_m)s" font="Regular;%(rand_f)d" valign="top" foregroundColor="#00f5b83d" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget source="mesaj" render="Label" position="%(mesaj)s" size="%(mesaj_m)s" font="Regular;%(mesaj_f)d" valign="top" foregroundColor="#00f2f4f8" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget source="ajutor" render="Label" position="%(butoane)s" size="%(ajutor_m)s" font="Regular;%(butoane_f)d" valign="center" foregroundColor="#009aa6bb" backgroundColor="#00101828" transparent="1" zPosition="6" />
		<widget source="key_green" render="Label" position="%(verde)s" size="%(buton_m)s" font="Regular;%(butoane_f)d" halign="center" valign="center" foregroundColor="#00ffffff" backgroundColor="#00218a3c" transparent="0" zPosition="6" />
	</screen>""" % v


# actiunile randurilor
FURNIZOR = "furnizor"
CONT = "cont"
TARA = "tara"
STERGE = "sterge"
INCHIDE = "inchide"


def randuri(s, tara):
	"""Randurile listei dupa stare si tara aleasa: (text, actiune, explicatie)."""
	r = [("%s: %s" % (_("Furnizorul"), s.get("titlu", "")), FURNIZOR,
		s.get("ajutor", "") + " " + _("STÂNGA/DREAPTA: alt furnizor. OK: lista lor."))]
	if s.get("fel") == "fisiere":
		r.append((_("Închide"), INCHIDE, s.get("ajutor", "")))
		return r
	if s.get("indisponibil"):
		r.append((_("Închide"), INCHIDE, s["indisponibil"]))
		return r
	if s["fel_cont"] == "numar":
		cum = _("salvat") if s["cont"] else _("lipsește")
	else:
		cum = _("salvate") if s["cont"] else _("lipsesc")
	r.append(("%s (%s)" % (s["eticheta_cont"], cum), CONT, s["nota_cont"]))
	nume_tara = ""
	for t in s.get("tari") or []:
		if t["cod"] == tara:
			nume_tara = t["titlu"]
	if nume_tara:
		r.append(("%s: %s" % (_("Țara"), nume_tara), TARA, _("OK: altă țară. VERDE: pune VPN-ul pentru această țară.")))
	else:
		r.append((_("Alege țara"), TARA, _("OK: lista țărilor furnizorului. După alegere receptorul pune serverele și "
			"pornește VPN-ul.")))
	if s["cont"]:
		r.append((_("Șterge contul acestui furnizor"), STERGE, _("Șterge de pe receptor contul salvat pentru acest "
			"furnizor.")))
	r.append((_("Închide"), INCHIDE, ""))
	return r


class HdsVpnFurnizor(Screen):

	def __init__(self, session, furnizor=None):
		marime = getDesktop(0).size()
		self.skin = skinRezerva(marime.width(), marime.height())
		Screen.__init__(self, session)
		titlu = _("Furnizorul VPN, fără fișiere")
		self.setTitle(titlu)
		self["titlu"] = StaticText(titlu)
		self["stare"] = StaticText("")
		self["list"] = MenuList([])
		self["rand"] = StaticText("")
		self["mesaj"] = StaticText("")
		self["ajutor"] = StaticText(_("OK: alege · STÂNGA/DREAPTA: alt furnizor"))
		self["key_green"] = StaticText(_("Pune VPN-ul"))
		toti = [f for f in F.ORDINE] + [f for f in F.CU_FISIERE]
		self._toti = toti
		self._furnizor = furnizor if furnizor in toti else F.ORDINE[0]
		self._tara = {}
		self._randuri = []
		self._stare = None
		self._vazuta = None
		self._mesajPana = 0
		self._dupaTari = None
		self._cont = None
		self._aplicaVazut = ""
		self["actiuni"] = ActionMap(["OkCancelActions", "DirectionActions", "ColorActions"], {
			"ok": self.ok,
			"cancel": self.close,
			"up": self.sus,
			"down": self.jos,
			"left": self.stanga,
			"right": self.dreapta,
			"green": self.verde,
		}, -1)
		self["list"].onSelectionChanged.append(self._randAles)
		self._ceas = eTimer()
		self._ceas.callback.append(self._citeste)
		self.onLayoutFinish.append(self._porneste)
		self.onClose.append(self._ceas.stop)

	def _porneste(self):
		ultima = F._hv().LUCRARI.stare()["ultima"]
		self._vazuta = ultima["id"] if ultima else None
		self._citeste()
		self._ceraTarile()

	# ------------------------------------------------------------------ citirea

	def _citeste(self):
		self._ceas.stop()
		try:
			s = F.stare(self._furnizor)
			vpn = F._hv().textLegatura(F._hv().stare())
		except Exception as eroare:
			print("[HdsVpnFurnizor] starea: %r" % (eroare,))
			self._ceas.start(CITIRE_MS * 3, True)
			return
		self._stare = s
		self["stare"].setText("%s: %s" % (_("VPN"), vpn))
		self._puneRanduri(randuri(s, self._tara.get(self._furnizor, "")))
		self._arataLucrarea(s)
		self._ceas.start(CITIRE_MS, True)

	def _puneRanduri(self, noi):
		if [r[:2] for r in noi] == [r[:2] for r in self._randuri]:
			self._randuri = noi
			self._randAles()
			return
		ales = self._randAlesAcum()
		self._randuri = noi
		self["list"].setList([r[0] for r in noi])
		index = 0
		if ales is not None:
			for i, r in enumerate(noi):
				if r[1] == ales[1]:
					index = i
					break
		self["list"].moveToIndex(index)
		self._randAles()

	def _randAlesAcum(self):
		index = self["list"].getSelectionIndex()
		if 0 <= index < len(self._randuri):
			return self._randuri[index]
		return None

	def _randAles(self):
		r = self._randAlesAcum()
		s = self._stare
		self["rand"].setText(s["text_lucreaza"] if (s and s["lucreaza"]) else (r[2] if r else ""))

	def _arataLucrarea(self, s):
		ultima = s["ultima"]
		if ultima and ultima["id"] != self._vazuta:
			self._vazuta = ultima["id"]
			self._mesaj(ultima["mesaj"])
			if self._dupaTari is not None and ultima["id"] == self._dupaTari:
				self._dupaTari = None
				if ultima["reusit"]:
					self._alegeTara()
		elif s.get("aplica") and s["aplica"] != self._aplicaVazut:
			self._aplicaVazut = s["aplica"]
			self._mesaj(s["aplica"])
		elif self._mesajPana and time() > self._mesajPana:
			self._mesajPana = 0
			self["mesaj"].setText("")
		self._randAles()

	def _mesaj(self, text):
		self["mesaj"].setText(text or "")
		self._mesajPana = time() + MESAJ_S

	def _ocupat(self):
		return bool(self._stare and self._stare["lucreaza"])

	# ------------------------------------------------------------------ tastele

	def sus(self):
		self["list"].up()

	def jos(self):
		self["list"].down()

	def stanga(self):
		self._sageata(-1)

	def dreapta(self):
		self._sageata(1)

	def _sageata(self, pas):
		r = self._randAlesAcum()
		if r is None or r[1] != FURNIZOR:
			self["list"].pageUp() if pas < 0 else self["list"].pageDown()
			return
		i = self._toti.index(self._furnizor)
		self._schimbaFurnizor(self._toti[(i + pas) % len(self._toti)])

	def _schimbaFurnizor(self, fid):
		self._furnizor = fid
		self._cont = None
		self._citeste()
		self._ceraTarile()

	def _ceraTarile(self, din_nou=False):
		"""Lista tarilor se citeste singura cand alegi un furnizor cu cont (fara asteptare la "Alege tara")."""
		if self._furnizor not in F.ORDINE or F.indisponibil(self._furnizor):
			return None
		numar = F.pornesteTarile(self._furnizor, din_nou)
		if numar:
			self._citeste()
		return numar

	def ok(self):
		r = self._randAlesAcum()
		s = self._stare
		if r is None or s is None:
			return
		a = r[1]
		if a == INCHIDE:
			self.close()
		elif a == FURNIZOR:
			lista = [(F.titlu(f), f) for f in self._toti]
			self.session.openWithCallback(self._furnizorAles, ChoiceBox, title=_("Furnizorul VPN"), list=lista,
				selection=self._toti.index(self._furnizor))
		elif a == CONT:
			self._scrieContul(None)
		elif a == TARA:
			self._alegeTara()
		elif a == STERGE:
			self.session.openWithCallback(self._confirmaSterge, MessageBox,
				_("Ștergi de pe receptor contul acestui furnizor?"), MessageBox.TYPE_YESNO, default=False)

	def _furnizorAles(self, ales):
		if ales:
			self._schimbaFurnizor(ales[1])

	def _alegeTara(self):
		s = self._stare
		if not s.get("tari"):
			if self._ocupat():
				self._mesaj(_("Așteaptă să se termine ce ai pornit înainte."))
				return
			numar = self._ceraTarile(din_nou=bool(s.get("eroare")))
			if numar:
				self._dupaTari = numar
				self._mesaj(F.textLucrare(F.LUCRARE_TARI))
			elif numar is None:
				self._mesaj(_("Așteaptă să se termine ce ai pornit înainte."))
			return
		lista = [(t["titlu"], t["cod"]) for t in s["tari"]]
		coduri = [t["cod"] for t in s["tari"]]
		ales = self._tara.get(self._furnizor)
		self.session.openWithCallback(self._taraAleasa, ChoiceBox, title=_("Țara"), list=lista,
			selection=coduri.index(ales) if ales in coduri else 0)

	def _taraAleasa(self, ales):
		if not ales:
			return
		self._tara[self._furnizor] = ales[1]
		self._citeste()
		self.verde()

	def verde(self):
		"""Pune VPN-ul pentru tara aleasa: cere intai contul daca lipseste, apoi porneste configurarea."""
		s = self._stare
		if s is None or self._furnizor not in F.ORDINE or s.get("indisponibil"):
			return
		tara = self._tara.get(self._furnizor)
		if not tara:
			self._alegeTara()
			return
		if self._ocupat():
			self._mesaj(_("Așteaptă să se termine ce ai pornit înainte."))
			return
		bun, mesaj, cont = F.verificaCont(self._furnizor, **(self._cont or {}))
		if not bun:
			self._scrieContul(lambda: self.verde())
			return
		self._cont = None
		if F.configureaza(self._furnizor, tara, cont) is None:
			self._mesaj(_("Așteaptă să se termine ce ai pornit înainte."))
		else:
			self._mesaj(F.textLucrare(F.LUCRARE_CONFIGURARE))
		self._citeste()

	# ------------------------------------------------------------------ contul (tastatura de pe ecran)

	def _scrieContul(self, apoi):
		self._apoi = apoi
		s = self._stare
		if s["fel_cont"] == "numar":
			# hdsSecret: cu asistenta pornita, prima tasta cere oprirea ei
			self.session.openWithCallback(self._numarScris, VirtualKeyBoard, title=s["eticheta_cont"], text="",
				hdsSecret=True)
		else:
			self.session.openWithCallback(self._numeScris, VirtualKeyBoard, title=_("Numele de serviciu"), text="")

	def _numarScris(self, numar):
		if numar is None:
			return
		bun, mesaj, cont = F.verificaCont(self._furnizor, numar=numar)
		if not bun:
			self._mesaj(mesaj)
			return
		self._cont = {"numar": cont["numar"]} if cont else None
		self._mesaj(_("Numărul este scris. Alege țara."))
		self._dupaCont()

	def _numeScris(self, nume):
		if nume is None:
			return
		nume = nume.strip()
		if not nume:
			self._mesaj(_("Numele nu poate fi gol."))
			return
		self._nume = nume
		self.session.openWithCallback(self._parolaScrisa, VirtualKeyBoard,
			title=_("Parola de serviciu (după salvare nu se mai arată)"), text="", hdsSecret=True)

	def _parolaScrisa(self, parola):
		nume = getattr(self, "_nume", "")
		self._nume = ""
		if parola is None or not nume:
			return
		bun, mesaj, cont = F.verificaCont(self._furnizor, nume=nume, parola=parola)
		if not bun:
			self._mesaj(mesaj)
			return
		self._cont = cont
		self._mesaj(_("Contul este scris; se salvează când pui VPN-ul."))
		self._dupaCont()

	def _dupaCont(self):
		apoi = getattr(self, "_apoi", None)
		self._apoi = None
		if apoi is not None:
			apoi()
		elif self._tara.get(self._furnizor):
			self.verde()
		else:
			self._alegeTara()

	def _confirmaSterge(self, da):
		if da:
			self._mesaj(F.stergeDatele(self._furnizor)[1])
			self._citeste()
