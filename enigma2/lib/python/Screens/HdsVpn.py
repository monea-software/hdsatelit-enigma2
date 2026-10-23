# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsVpn.py: ecranul "VPN" (Setari > Retea & Internet > VPN): VPN-ul receptorului prin HMA (HideMyAss) sau alt
# furnizor OpenVPN, ori prin WireGuard.
#
# Sus: titlul si starea mare (Conectat, Oprit, Se conecteaza..., Fara legatura cu internetul oprit), cu culoarea ei;
# dedesubt serverul, ce trece prin VPN si adresa vazuta pe internet (sau motivul unei erori). Apoi randurile, toate cu
# sagetile si OK: pornirea/oprirea, furnizorul, serverul (STANGA/DREAPTA trec la serverul de alaturi, OK deschide
# lista), numele si parola (tastatura de pe ecran; dupa salvare nu se mai arata), importul de pe stick, ce trece prin
# VPN, oprirea totala la caderea VPN-ului, pornirea odata cu receptorul, adresa vazuta pe internet, instalarea
# programelor cand lipsesc, stergerile (cu "Nu" ales dinainte) si "Inchide". Sub lista, explicatia randului ales si
# rezultatul ultimei comenzi. VERDE porneste sau opreste VPN-ul, GALBEN afla adresa vazuta pe internet.
#
# Toata logica e in Components/HdsVpn.py (aceeasi in pagina web /vpn): ecranul citeste stare() la fiecare CITIRE_MS si
# porneste lucrarile (pornire, oprire, stick, adresa, instalare) pe firul lor; rezultatul il ia din stare() la citirea
# urmatoare. O lucrare pornita din web se vede si aici.
#
# Skinul: facut la deschidere dupa marimea ecranului si marimea literelor aleasa de om, ca la "Acces SSH"
# (Screens/HdsAccesSsh.py), cu aceleasi culori si fonturi; un bloc <screen name="HdsVpn"> din skin are intaietate.

from time import time

from enigma import eTimer, getDesktop

from .Screen import Screen
from .MessageBox import MessageBox
from .ChoiceBox import ChoiceBox
from .VirtualKeyBoard import VirtualKeyBoard
from Components.ActionMap import ActionMap
from Components.MenuList import MenuList
from Components.Sources.StaticText import StaticText
from Components import HdsVpn as V

CITIRE_MS = 1000
MESAJ_S = 15

# asezarea la 1920x1080 si litere 100 %: (nume, inaltime, font, spatiu dupa, creste), ca la Acces SSH
LATIME = 1400
MARGINE = 40
CONTINUT = 1320
SUS = 16
JOS = 12
BLOCURI = (
	("titlu", 56, 42, 4, False),
	("stare", 76, 52, 4, False),
	("detalii", 116, 28, 10, True),
	("list", None, 30, 12, True),
	("rand", 108, 26, 4, True),
	("mesaj", 72, 26, 8, True),
	("butoane", 40, 24, 0, True),
)
LISTA_RAND = 44
LISTA_MAX = 9
LISTA_MIN = 3
LISTA_TEXT = 16
INALTIME_MAX = 1046
BUTON_LATIME = 230
CULORI_STARE = {"bun": "#007ddc8a", "chihlimbar": "#00f5b83d", "rau": "#00ff8a7a", "slab": "#009aa6bb"}


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
	v = {"pl": a["fereastra"][0], "ph": a["fereastra"][1], "linie": max(1, a["detalii"][4] // 14)}
	for nume in ("titlu", "stare", "detalii", "list", "rand", "mesaj", "butoane"):
		x, y, l, h, font = a[nume]
		v[nume] = "%d,%d" % (x, y)
		v[nume + "_m"] = "%d,%d" % (l, h)
		v[nume + "_f"] = font
	v["li"] = a["rand_lista"]
	v["lo"] = max(1, LISTA_TEXT * a["detalii"][4] // 28)
	x, y, l, h, font = a["butoane"]
	bw = max(1, BUTON_LATIME * a["detalii"][4] // 28)
	v["verde"] = "%d,%d" % (x + l - 2 * bw - font, y)
	v["galben"] = "%d,%d" % (x + l - bw, y)
	v["buton_m"] = "%d,%d" % (bw, h)
	v["ajutor_m"] = "%d,%d" % (max(1, l - 2 * bw - 2 * font), h)
	for k, c in CULORI_STARE.items():
		v["c_" + k] = c
	return """
	<screen name="HdsVpn" position="center,center" size="%(pl)d,%(ph)d" flags="wfNoBorder" backgroundColor="#00101828" title="VPN">
		<eLabel position="0,0" size="%(pl)d,%(linie)d" backgroundColor="#00ffffff" zPosition="1" />
		<widget source="titlu" render="Label" position="%(titlu)s" size="%(titlu_m)s" font="Regular;%(titlu_f)d" valign="center" foregroundColor="#00f2f4f8" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget source="stare_bun" render="Label" position="%(stare)s" size="%(stare_m)s" font="Regular;%(stare_f)d" valign="center" foregroundColor="%(c_bun)s" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget source="stare_chihlimbar" render="Label" position="%(stare)s" size="%(stare_m)s" font="Regular;%(stare_f)d" valign="center" foregroundColor="%(c_chihlimbar)s" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget source="stare_rau" render="Label" position="%(stare)s" size="%(stare_m)s" font="Regular;%(stare_f)d" valign="center" foregroundColor="%(c_rau)s" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget source="stare_slab" render="Label" position="%(stare)s" size="%(stare_m)s" font="Regular;%(stare_f)d" valign="center" foregroundColor="%(c_slab)s" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget source="detalii" render="Label" position="%(detalii)s" size="%(detalii_m)s" font="Regular;%(detalii_f)d" valign="top" foregroundColor="#00c9d2e3" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget name="list" position="%(list)s" size="%(list_m)s" itemHeight="%(li)d" font="Regular;%(list_f)d" foregroundColor="#00f2f4f8" backgroundColor="#00101828" backgroundColorSelected="#00374ea1" foregroundColorSelected="#00ffffff" transparent="1" scrollbarMode="showOnDemand" textOffset="%(lo)d,0" zPosition="2" />
		<widget source="rand" render="Label" position="%(rand)s" size="%(rand_m)s" font="Regular;%(rand_f)d" valign="top" foregroundColor="#00f5b83d" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget source="mesaj" render="Label" position="%(mesaj)s" size="%(mesaj_m)s" font="Regular;%(mesaj_f)d" valign="top" foregroundColor="#00f2f4f8" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget source="ajutor" render="Label" position="%(butoane)s" size="%(ajutor_m)s" font="Regular;%(butoane_f)d" valign="center" foregroundColor="#009aa6bb" backgroundColor="#00101828" transparent="1" zPosition="6" />
		<widget source="key_green" render="Label" position="%(verde)s" size="%(buton_m)s" font="Regular;%(butoane_f)d" halign="center" valign="center" foregroundColor="#00ffffff" backgroundColor="#00218a3c" transparent="0" zPosition="6" />
		<widget source="key_yellow" render="Label" position="%(galben)s" size="%(buton_m)s" font="Regular;%(butoane_f)d" halign="center" valign="center" foregroundColor="#00101828" backgroundColor="#00e0b324" transparent="0" zPosition="6" />
	</screen>""" % v


# actiunile randurilor
COMUTA = "comuta"
INSTALEAZA = "instaleaza"
FURNIZOR = "furnizor"
SERVER = "server"
CONT = "cont"
STICK = "stick"
MOD = "mod"
OPRIRE = "oprire"
LA_PORNIRE = "la_pornire"
IP = "ip"
STERGE = "sterge"
STERGE_TOATE = "sterge_toate"
STERGE_CONT = "sterge_cont"
INCHIDE = "inchide"
# randurile care pornesc o lucrare (cat merge alta, OK spune intai sa astepti)
CU_LUCRARE = (COMUTA, INSTALEAZA, STICK, IP)
CU_SAGETI = (FURNIZOR, SERVER, MOD, OPRIRE, LA_PORNIRE)


def _da(v):
	return _("da") if v else _("nu")


def culoareStare(s):
	return {"conectat": "bun", "se_conecteaza": "chihlimbar", "blocat": "rau", "eroare": "rau"}.get(s["legatura"], "slab")


def randuri(s):
	"""Randurile listei dupa stare: (text, actiune, explicatie)."""
	r = []
	fel = s["fel"]
	if s["lipsesc"]:
		r.append((_("Instalează programele VPN"), INSTALEAZA, V.textProgrameLipsa(fel)))
	if s["pornit"] or s["legatura"] in ("conectat", "se_conecteaza", "blocat"):
		r.append((_("VPN: pornit"), COMUTA, _("OK oprește VPN-ul. Internetul merge apoi direct, prin rețeaua ta.")))
	else:
		r.append((_("VPN: oprit"), COMUTA, _("OK pornește VPN-ul cu serverul ales.")))
	r.append(("%s: %s" % (_("Furnizorul"), V.textFurnizor(s["furnizor"])), FURNIZOR, V.textCumIeiFisierele(s["furnizor"])))
	if s["profil"]:
		r.append(("%s: %s" % (_("Serverul"), s["profil"]["titlu"]), SERVER,
			_("STÂNGA/DREAPTA: serverul de alături. OK: lista serverelor (%d).") % s["nr_profiluri"]))
	else:
		r.append((_("Serverul: niciunul ales"), SERVER, _("OK: lista serverelor (%d). Fără servere, importă întâi fișierele.")
			% s["nr_profiluri"]))
	if fel == "openvpn":
		r.append(("%s (%s)" % (V.textCont(s["furnizor"]), _("salvate") if s["cont"] else _("lipsesc")), CONT,
			V.textExplicatieCont(s["furnizor"])))
	r.append((_("Importă fișierele de pe stick"), STICK,
		_("De pe stick: dosarul hdsatelit/vpn, cu fișierele .ovpn sau .conf ori cu arhiva .zip a furnizorului.")))
	r.append(("%s: %s" % (_("Ce trece prin VPN"), V.textMod(s["mod"])), MOD, textExplicatieMod(s)))
	# in modul navigator oprirea totala e mereu (navigatorul n-are alta iesire decat tunelul), deci randul lipseste
	if s["mod"] != "navigator":
		r.append(("%s: %s" % (_("Oprire totală la căderea VPN-ului"), _da(s["oprire_totala"])), OPRIRE,
			_("Dacă VPN-ul cade, receptorul nu mai iese în internet până revine. Rețeaua din casă merge.")))
	r.append(("%s: %s" % (_("Pornește odată cu receptorul"), _da(s["la_pornire"])), LA_PORNIRE,
		_("VPN-ul pornește singur după fiecare pornire a receptorului, dacă era pornit.")))
	r.append((_("Verifică adresa văzută pe internet"), IP, _("Află adresa IP și țara pe care le văd site-urile acum.")))
	if s["profil"]:
		r.append((_("Șterge serverul ales"), STERGE, _("Șterge de pe receptor fișierul serverului %s.") % s["profil"]["titlu"]))
	if s["nr_profiluri"]:
		r.append(("%s (%d)" % (_("Șterge toate serverele acestui furnizor"), s["nr_profiluri"]), STERGE_TOATE,
			_("Șterge de pe receptor toate fișierele importate pentru acest furnizor.")))
	if fel == "openvpn" and s["cont"]:
		r.append((_("Șterge numele și parola"), STERGE_CONT, _("Șterge de pe receptor numele și parola contului.")))
	r.append((_("Închide"), INCHIDE, ""))
	return r


def textExplicatieMod(s):
	return V.textExplicatieMod(s)


class HdsVpn(Screen):

	def __init__(self, session):
		marime = getDesktop(0).size()
		self.skin = skinRezerva(marime.width(), marime.height())
		Screen.__init__(self, session)
		titlu = _("VPN")
		self.setTitle(titlu)
		self["titlu"] = StaticText(titlu)
		for k in CULORI_STARE:
			self["stare_" + k] = StaticText("")
		self["detalii"] = StaticText("")
		self["list"] = MenuList([])
		self["rand"] = StaticText("")
		self["mesaj"] = StaticText("")
		self["ajutor"] = StaticText(_("OK: alege · STÂNGA/DREAPTA: schimbă"))
		self["key_green"] = StaticText(_("Pornește"))
		self["key_yellow"] = StaticText(_("Adresa IP"))
		self._randuri = []
		self._stare = None
		self._vazuta = None
		self._mesajPana = 0
		self["actiuni"] = ActionMap(["OkCancelActions", "DirectionActions", "ColorActions"], {
			"ok": self.ok,
			"cancel": self.close,
			"up": self.sus,
			"down": self.jos,
			"left": self.stanga,
			"right": self.dreapta,
			"green": self.verde,
			"yellow": self.galben,
		}, -1)
		self["list"].onSelectionChanged.append(self._randAles)
		self._ceas = eTimer()
		self._ceas.callback.append(self._citeste)
		self.onLayoutFinish.append(self._porneste)
		self.onClose.append(self._ceas.stop)

	def _porneste(self):
		ultima = V.LUCRARI.stare()["ultima"]
		self._vazuta = ultima["id"] if ultima else None
		self._citeste()

	# ------------------------------------------------------------------ citirea

	def _citeste(self):
		self._ceas.stop()
		try:
			s = V.stare()
		except Exception as eroare:
			print("[HdsVpn] starea: %r" % (eroare,))
			self._ceas.start(CITIRE_MS * 3, True)
			return
		self._stare = s
		culoare = culoareStare(s)
		text = V.textLegatura(s)
		for k in CULORI_STARE:
			self["stare_" + k].setText(text if k == culoare else "")
		self["detalii"].setText("\n".join(V.textDetalii(s)[:3]))
		pornit = s["pornit"] or s["legatura"] in ("conectat", "se_conecteaza", "blocat")
		self["key_green"].setText(_("Oprește") if pornit else _("Pornește"))
		self._puneRanduri(randuri(s))
		self._arataLucrarea(s["lucrare"])
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

	def _lucreaza(self):
		return self._stare["lucrare"]["lucreaza"] if self._stare else None

	def _randAles(self):
		r = self._randAlesAcum()
		lucreaza = self._lucreaza()
		self["rand"].setText(V.textLucrare(lucreaza) if lucreaza else (r[2] if r else ""))

	def _arataLucrarea(self, l):
		ultima = l["ultima"]
		if ultima and ultima["id"] != self._vazuta:
			self._vazuta = ultima["id"]
			self._mesaj(ultima["mesaj"])
		elif self._mesajPana and time() > self._mesajPana:
			self._mesajPana = 0
			self["mesaj"].setText("")
		self._randAles()

	def _mesaj(self, text):
		self["mesaj"].setText(text or "")
		self._mesajPana = time() + MESAJ_S

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
		s = self._stare
		if r is None or s is None or r[1] not in CU_SAGETI:
			self["list"].pageUp() if pas < 0 else self["list"].pageDown()
			return
		a = r[1]
		if a == FURNIZOR:
			i = V.FURNIZORI.index(s["furnizor"])
			self._schimba(furnizor=V.FURNIZORI[(i + pas) % len(V.FURNIZORI)])
		elif a == SERVER:
			lista = s["profiluri"]
			if not lista:
				self._mesaj(_("Nu sunt servere pentru acest furnizor. Importă întâi fișierele."))
				return
			ids = [p["id"] for p in lista]
			i = ids.index(s["profil"]["id"]) if (s["profil"] and s["profil"]["id"] in ids) else -1
			self._schimba(profil=ids[(i + pas) % len(ids)])
		elif a == MOD:
			i = V.MODURI.index(s["mod"]) if s["mod"] in V.MODURI else 0
			self._schimba(mod=V.MODURI[(i + pas) % len(V.MODURI)])
		elif a == OPRIRE:
			self._schimba(oprire_totala=not s["oprire_totala"])
		elif a == LA_PORNIRE:
			self._schimba(la_pornire=not s["la_pornire"])

	def _schimba(self, **schimbari):
		try:
			_reusit, mesaj, _numar = V.schimba(**schimbari)
		except Exception as eroare:
			mesaj = _("Eroare pe receptor: %s") % eroare
		self._mesaj(mesaj)
		self._citeste()

	def _intreaba(self, text, cand_da):
		self.session.openWithCallback(cand_da, MessageBox, text, MessageBox.TYPE_YESNO, default=False)

	def ok(self):
		r = self._randAlesAcum()
		s = self._stare
		if r is None or s is None:
			return
		a = r[1]
		if a in CU_LUCRARE and self._lucreaza():
			self._mesaj(_("Așteaptă să se termine ce ai pornit înainte."))
			return
		if a == INCHIDE:
			self.close()
		elif a == COMUTA:
			self.verde()
		elif a == INSTALEAZA:
			self._intreaba(_("Instalezi programele VPN din feedul de extensii HD Satelit? Durează câteva minute."),
				lambda da: da and self._lucrare(lambda: V.pornesteInstalarea(s["fel"])))
		elif a == FURNIZOR:
			lista = [(V.textFurnizor(f), f) for f in V.FURNIZORI]
			self.session.openWithCallback(self._furnizorAles, ChoiceBox, title=_("Furnizorul VPN"), list=lista,
				selection=V.FURNIZORI.index(s["furnizor"]))
		elif a == SERVER:
			if not s["profiluri"]:
				self._mesaj(_("Nu sunt servere pentru acest furnizor. Importă întâi fișierele."))
				return
			lista = [(p["titlu"], p["id"]) for p in s["profiluri"]]
			ids = [p["id"] for p in s["profiluri"]]
			ales = ids.index(s["profil"]["id"]) if (s["profil"] and s["profil"]["id"] in ids) else 0
			self.session.openWithCallback(self._serverAles, ChoiceBox, title=_("Serverul"), list=lista, selection=ales)
		elif a == CONT:
			self.session.openWithCallback(self._numeScris, VirtualKeyBoard, title=_("Numele contului VPN"), text="")
		elif a == STICK:
			self._lucrare(V.pornesteStick)
		elif a in (MOD, OPRIRE, LA_PORNIRE):
			self._sageata(1)
		elif a == IP:
			self.galben()
		elif a == STERGE:
			self._intreaba(_("Ștergi serverul %s?") % s["profil"]["titlu"], self._confirmaSterge)
		elif a == STERGE_TOATE:
			self._intreaba(_("Ștergi toate serverele acestui furnizor (%s)?") % s["nr_profiluri"], self._confirmaStergeToate)
		elif a == STERGE_CONT:
			self._intreaba(_("Ștergi numele și parola de pe receptor?"), self._confirmaStergeCont)

	def _lucrare(self, porneste):
		if porneste() is None:
			self._mesaj(_("Așteaptă să se termine ce ai pornit înainte."))
		self._citeste()

	def _furnizorAles(self, ales):
		if ales:
			self._schimba(furnizor=ales[1])

	def _serverAles(self, ales):
		if ales:
			self._schimba(profil=ales[1])

	def _numeScris(self, nume):
		if nume is None:
			return
		nume = nume.strip()
		if not nume:
			self._mesaj(_("Numele nu poate fi gol."))
			return
		self._nume = nume
		self.session.openWithCallback(self._parolaScrisa, VirtualKeyBoard,
			title=_("Parola contului VPN (după salvare nu se mai arată)"), text="")

	def _parolaScrisa(self, parola):
		nume = getattr(self, "_nume", "")
		self._nume = ""
		if parola is None or not nume:
			return
		_reusit, mesaj = V.salveazaCont(nume, parola)
		self._mesaj(mesaj)
		self._citeste()

	def _confirmaSterge(self, da):
		if da and self._stare and self._stare["profil"]:
			self._mesaj(V.stergeProfil(self._stare["profil"]["id"])[1])
			self._citeste()

	def _confirmaStergeToate(self, da):
		if da and self._stare:
			self._mesaj(V.stergeGrup(self._stare["furnizor"])[1])
			self._citeste()

	def _confirmaStergeCont(self, da):
		if da:
			self._mesaj(V.stergeCont()[1])
			self._citeste()

	def verde(self):
		s = self._stare
		if s is None:
			return
		if self._lucreaza():
			self._mesaj(_("Așteaptă să se termine ce ai pornit înainte."))
			return
		pornit = s["pornit"] or s["legatura"] in ("conectat", "se_conecteaza", "blocat")
		self._lucrare(V.opresteVpn if pornit else V.pornesteVpn)

	def galben(self):
		if self._lucreaza():
			self._mesaj(_("Așteaptă să se termine ce ai pornit înainte."))
			return
		self._lucrare(V.pornesteIp)
