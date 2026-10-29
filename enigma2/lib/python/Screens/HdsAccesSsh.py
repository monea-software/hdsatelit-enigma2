# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsAccesSsh.py: ecranul "Parola receptorului" (Setari > Retea & Conexiuni): cum se intra pe receptor de pe calculator,
# prin FTP, SSH si SFTP, cu aceeasi parola.
#
# Sus, pe grupe: pentru ce merge parola (FTP, SSH, SFTP; FTP numai cand serverul FTP asculta), parola lui root, mare, de
# vazut oricand (altfel starea ei in cateva cuvinte, tot mare) si explicatia dedesubt; felul de conectare cu adresa
# receptorului; numarul cheilor SSH sau, in locul lui, cu alta culoare, starea periculoasa (root fara parola care se
# primeste, "Fără parolă în rețeaua locală" pornita, dropbear cu -B). Dedesubt, randurile cu ce se poate face, toate cu
# sagetile si OK: "Schimbă parola" (tastatura de pe ecran, cu parola de acum scrisa dinainte), "Fă o parolă nouă" (la
# intamplare), "Adaugă cheile de pe stick", cate un rand "Șterge cheia" pentru fiecare cheie, optiunea, "Text brut" si
# "Închide". Sub lista, explicatia randului ales si rezultatul ultimei comenzi. Parola la intamplare, stergerea unei chei
# si pornirea optiunii cer o confirmare cu "Nu" ales dinainte; parola scrisa de om nu (a scris-o chiar el, iar
# tastatura are EXIT); o parola care nu se primeste (prea scurta, cu spatii sau diacritice) da motivul si nu schimba
# nimic. Cat merge o comanda, OK spune intai sa astepti, fara intrebare.
# "Text brut" (randul lui sau tasta albastra) arata fisierele de setari ale serverelor SSH si FTP, cu litere de latime
# fixa (Stanga/Dreapta intre ele, Sus/Jos derulare, OK sau EXIT inapoi), fara /etc/shadow si fara fisierul parolei.
#
# Toata logica e in Components/HdsAccesSsh.py (aceeasi in pagina web /acces-ssh): ecranul citeste stare() la fiecare
# CITIRE_MS (cateva fisiere mici) si porneste lucrarile (parola, cheile, stickul, optiunea) pe firul lor; rezultatul il
# ia din stare() la citirea urmatoare. O lucrare pornita din web se vede si aici. Cat ecranul e deschis,
# Components.HdsAccesSsh.ecranDeschis() e adevarat (interfata web opreste atunci telecomanda si captura pentru
# browserele neconectate cu codul).
#
# Skinul: facut la deschidere dupa marimea ecranului si dupa marimea literelor aleasa de om (config.osd.fontscale:
# skin.parseFont mareste fontul, deci aici se maresc casutele de text, iar lista pastreaza cate randuri incap, cel putin
# 3), numai cu fonturile „Regular” si „Console” si culori scrise direct, deci merge cu orice skin; un bloc
# <screen name="HdsAccesSsh"> din skin are intaietate.

from time import time

from enigma import eTimer, getDesktop

from .Screen import Screen
from .MessageBox import MessageBox
from .VirtualKeyBoard import VirtualKeyBoard
from Components.ActionMap import ActionMap
from Components.MenuList import MenuList
from Components.ScrollLabel import ScrollLabel
from Components.Sources.StaticText import StaticText
from Components import HdsAccesSsh as A

# cat de des se citeste starea
CITIRE_MS = 1000
# cat ramane rezultatul unei comenzi sub lista
MESAJ_S = 12

# asezarea la 1920x1080 si litere 100 %: latimea ferestrei, marginea, latimea continutului; apoi, de sus in jos,
# (nume, inaltime, font, spatiu dupa, creste). Cu „creste” casuta se mareste odata cu literele alese de om; titlul si
# parola (litere de 72 de puncte, se citeste de la 3 m) sunt destul de mari si raman la fel (fontul scris aici e
# micsorat cu procentul, iar skin.parseFont il mareste la loc). Casutele de mai multe randuri au n x 1,36 x font
# (inaltimea randului in HdsRegular), ca si coada literelor de pe ultimul rand sa se vada: despre si chei 2 randuri,
# rand (explicatia si amprenta) si mesaj (rezultatul si motivul unui refuz) 3 randuri.
LATIME = 1400
MARGINE = 40
CONTINUT = 1320
SUS = 16
JOS = 12
BLOCURI = (
	("titlu", 56, 42, 6, False),
	("eticheta", 34, 26, 0, True),
	("parola", 96, 72, 4, False),
	("despre", 76, 28, 4, True),
	("cum", 40, 28, 2, True),
	("chei", 76, 28, 8, True),
	("list", None, 32, 14, True),
	("rand", 108, 26, 4, True),
	("mesaj", 108, 26, 10, True),
	("butoane", 40, 24, 0, True),
)
# lista: inaltimea unui rand, cate randuri cel mult si cel putin, departarea textului de margine
LISTA_RAND = 46
LISTA_MAX = 7
LISTA_MIN = 3
LISTA_TEXT = 16
# inaltimea cea mai mare a ferestrei la 1080 (restul ramane margine)
INALTIME_MAX = 1046
# butonul albastru, in dreapta randului de jos
BUTON_LATIME = 260
# textul brut: litere de latime fixa („Console”, din skin_default.xml, deci in orice skin)
BRUT_FONT = 22


def _procentLitere():
	"""Marimea literelor aleasa in Setari (skin.getFontScalePercent), 100 fara skin (probele de pe PC)."""
	try:
		import skin
		return int(skin.getFontScalePercent())
	except Exception:
		return 100


def asezare(latime, inaltime, procent=None):
	"""Pozitiile si marimile ecranului la rezolutia si marimea literelor date: {nume: (x, y, l, h, font)}, plus
	„fereastra” (l, h), „randuri” (cate randuri are lista) si „rand_lista” (inaltimea unui rand al ei)."""
	if procent is None:
		procent = _procentLitere()
	f = min(inaltime / 1080.0, (latime - 40) / float(LATIME))
	m = procent / 100.0

	def px(x):
		return max(1, int(round(x * f)))

	def text(x):
		return max(1, int(round(x * f * m)))

	def inaltime(h, creste):
		return text(h) if creste else px(h)

	def font(x, creste):
		return px(x) if creste else max(1, int(round(x * f / m)))

	rand_lista = text(LISTA_RAND)
	fix = px(SUS) + px(JOS)
	for nume, h, _font, dupa, creste in BLOCURI:
		fix += px(dupa) + (inaltime(h, creste) if h is not None else 0)
	loc = px(INALTIME_MAX) - fix
	randuri = max(LISTA_MIN, min(LISTA_MAX, loc // rand_lista))
	a = {"randuri": randuri, "rand_lista": rand_lista}
	x, l = px(MARGINE), px(CONTINUT)
	y = px(SUS)
	for nume, h, fnt, dupa, creste in BLOCURI:
		h = rand_lista * randuri if h is None else inaltime(h, creste)
		a[nume] = (x, y, l, h, font(fnt, creste))
		y += h + px(dupa)
	a["fereastra"] = (px(LATIME), y + px(JOS))
	return a


def skinRezerva(latime, inaltime, procent=None):
	"""Skinul ecranului dupa asezare(): aceeasi asezare la orice rezolutie si marime a literelor."""
	a = asezare(latime, inaltime, procent)
	v = {"pl": a["fereastra"][0], "ph": a["fereastra"][1], "linie": max(1, a["eticheta"][4] // 13)}
	for nume in ("titlu", "eticheta", "parola", "despre", "cum", "chei", "list", "rand", "mesaj", "butoane"):
		x, y, l, h, font = a[nume]
		v[nume] = "%d,%d" % (x, y)
		v[nume + "_m"] = "%d,%d" % (l, h)
		v[nume + "_f"] = font
	v["li"] = a["rand_lista"]
	v["lo"] = max(1, LISTA_TEXT * a["eticheta"][4] // 26)
	# textul brut: de la eticheta pana la sfarsitul mesajului
	x, y0 = a["eticheta"][0], a["eticheta"][1]
	y1 = a["mesaj"][1] + a["mesaj"][3]
	v["brut"] = "%d,%d" % (x, y0)
	v["brut_m"] = "%d,%d" % (a["eticheta"][2], y1 - y0)
	v["brut_f"] = max(1, BRUT_FONT * a["eticheta"][4] // 26)
	# randul de jos: indiciul textului brut in stanga, butonul albastru in dreapta
	x, y, l, h, font = a["butoane"]
	bw = max(1, BUTON_LATIME * a["eticheta"][4] // 26)
	v["albastru"] = "%d,%d" % (x + l - bw, y)
	v["albastru_m"] = "%d,%d" % (bw, h)
	v["ajutor_m"] = "%d,%d" % (max(1, l - bw - font), h)
	return """
	<screen name="HdsAccesSsh" position="center,center" size="%(pl)d,%(ph)d" flags="wfNoBorder" backgroundColor="#00101828" title="Parola receptorului">
		<eLabel position="0,0" size="%(pl)d,%(linie)d" backgroundColor="#00ffffff" zPosition="1" />
		<widget source="titlu" render="Label" position="%(titlu)s" size="%(titlu_m)s" font="Regular;%(titlu_f)d" valign="center" foregroundColor="#00f2f4f8" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget source="eticheta" render="Label" position="%(eticheta)s" size="%(eticheta_m)s" font="Regular;%(eticheta_f)d" valign="center" foregroundColor="#009aa6bb" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget source="parola" render="Label" position="%(parola)s" size="%(parola_m)s" font="Regular;%(parola_f)d" valign="center" foregroundColor="#00f5b83d" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget source="despre" render="Label" position="%(despre)s" size="%(despre_m)s" font="Regular;%(despre_f)d" valign="top" foregroundColor="#00f2f4f8" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget source="cum" render="Label" position="%(cum)s" size="%(cum_m)s" font="Regular;%(cum_f)d" valign="center" foregroundColor="#00c9d2e3" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget source="chei" render="Label" position="%(chei)s" size="%(chei_m)s" font="Regular;%(chei_f)d" valign="top" foregroundColor="#00c9d2e3" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget source="alarma" render="Label" position="%(chei)s" size="%(chei_m)s" font="Regular;%(chei_f)d" valign="top" foregroundColor="#00ff8a7a" backgroundColor="#00101828" transparent="1" zPosition="2" />
		<widget name="list" position="%(list)s" size="%(list_m)s" itemHeight="%(li)d" font="Regular;%(list_f)d" foregroundColor="#00f2f4f8" backgroundColor="#00101828" backgroundColorSelected="#00374ea1" foregroundColorSelected="#00ffffff" transparent="1" scrollbarMode="showOnDemand" textOffset="%(lo)d,0" zPosition="2" />
		<widget source="rand" render="Label" position="%(rand)s" size="%(rand_m)s" font="Regular;%(rand_f)d" valign="top" foregroundColor="#00f5b83d" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget source="mesaj" render="Label" position="%(mesaj)s" size="%(mesaj_m)s" font="Regular;%(mesaj_f)d" valign="top" foregroundColor="#00f2f4f8" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget name="brut" position="%(brut)s" size="%(brut_m)s" font="Console;%(brut_f)d" foregroundColor="#00f2f4f8" backgroundColor="#00101828" zPosition="5" />
		<widget source="ajutor" render="Label" position="%(butoane)s" size="%(ajutor_m)s" font="Regular;%(butoane_f)d" valign="center" foregroundColor="#009aa6bb" backgroundColor="#00101828" transparent="1" zPosition="6" />
		<widget source="key_blue" render="Label" position="%(albastru)s" size="%(albastru_m)s" font="Regular;%(butoane_f)d" halign="center" valign="center" foregroundColor="#00ffffff" backgroundColor="#003d7be0" transparent="0" zPosition="6" />
	</screen>""" % v


# actiunile randurilor
SCHIMBA = "schimba"
NOUA = "noua"
STICK = "stick"
STERGE = "sterge"
FARA_PAROLA = "fara-parola"
BRUT = "brut"
INCHIDE = "inchide"
# randurile care pornesc o lucrare (cat merge alta, OK spune intai sa astepti)
CU_LUCRARE = (SCHIMBA, NOUA, STICK, STERGE, FARA_PAROLA)


def randuri(s, parola):
	"""Randurile listei dupa stare: (text, actiune, argument, explicatie)."""
	lista = []
	if s["program"]:
		lista.append((_("Schimbă parola"), SCHIMBA, None,
			_("Scrii parola ta cu tastatura de pe ecran: 4-64 de semne, fără spații și fără diacritice. Cea veche nu mai merge.")))
		if s["fel_parola"] == "pusa":
			lista.append((_("Fă o parolă nouă"), NOUA, None,
				_("Receptorul face o parolă la întâmplare și o arată aici. Cea veche nu mai merge.")))
		else:
			lista.append((_("Fă o parolă"), NOUA, None, _("Receptorul face o parolă la întâmplare și o arată aici.")))
	lista.append((_("Adaugă cheile de pe stick"), STICK, None,
		_("Pune pe stick dosarul hdsatelit/ssh cu fișierul authorized_keys sau cu cheile tale .pub, apoi apasă OK.")))
	for c in s["chei"]:
		lista.append((_("Șterge cheia: %s") % A.textCheie(c), STERGE, c["amprenta"],
			_("OK șterge cheia. Calculatorul cu această cheie intră apoi numai cu parola.") + "\n" + c["amprenta"]))
	if s["fara_parola"]:
		lista.append((_("Fără parolă în rețeaua locală: pornit"), FARA_PAROLA, False,
			_("OK oprește. Oricine din rețeaua ta de acasă intră acum pe receptor fără parolă.")))
	else:
		lista.append((_("Fără parolă în rețeaua locală: oprit"), FARA_PAROLA, True,
			_("Rămâne oprit dacă nu ai un motiv anume. Pornit, oricine din rețeaua ta de acasă intră pe receptor fără parolă.")))
	lista.append((_("Text brut (fișierele serverelor SSH și FTP)"), BRUT, None,
		_("OK arată fișierele de setări ale serverelor SSH și FTP, așa cum sunt pe receptor.")))
	lista.append((_("Închide"), INCHIDE, None, ""))
	return lista


class HdsAccesSsh(Screen):

	def __init__(self, session):
		marime = getDesktop(0).size()
		self.skin = skinRezerva(marime.width(), marime.height())
		Screen.__init__(self, session)
		titlu = _("Parola receptorului")
		self.setTitle(titlu)
		self["titlu"] = StaticText(titlu)
		self["eticheta"] = StaticText(_("Parola lui root, aceeași pentru SSH și SFTP"))
		self["parola"] = StaticText("")
		self["despre"] = StaticText("")
		self["cum"] = StaticText("")
		self["chei"] = StaticText("")
		self["alarma"] = StaticText("")
		self["list"] = MenuList([])
		self["rand"] = StaticText("")
		self["mesaj"] = StaticText("")
		self["brut"] = ScrollLabel("")
		self["ajutor"] = StaticText("")
		self["key_blue"] = StaticText(_("Text brut"))
		self._randuri = []
		self._stare = None
		self._adresa = ""
		# parola aratata acum (o scrie dinainte tastatura de la "Schimbă parola")
		self._parola = ""
		# lucrarea pornita de aici (numarul ei) si ultima lucrare al carei rezultat s-a aratat
		self._vazuta = None
		self._mesajPana = 0
		self._brut = False
		self._paginaBruta = 0
		self._textBrut = None
		self._semnalat = False
		# amprenta cheii de sters, cat e deschisa intrebarea
		self._deSters = None
		self["actiuni"] = ActionMap(["OkCancelActions", "DirectionActions", "ColorActions"], {
			"ok": self.ok,
			"cancel": self.inchide,
			"up": self.sus,
			"down": self.jos,
			"left": self.stanga,
			"right": self.dreapta,
			"blue": self.albastru,
		}, -1)
		self["list"].onSelectionChanged.append(self._randAles)
		self._ceas = eTimer()
		self._ceas.callback.append(self._citeste)
		self.onLayoutFinish.append(self._porneste)
		self.onClose.append(self._laInchidere)

	def _porneste(self):
		A.semnalEcran(True)
		self._semnalat = True
		self["brut"].hide()
		self._adresa = A.adresaLocala()
		ultima = A.LUCRARI.stare()["ultima"]
		# rezultatul unei lucrari terminate inainte de deschidere nu se mai arata
		self._vazuta = ultima["id"] if ultima else None
		self._citeste()

	def _laInchidere(self):
		self._ceas.stop()
		if self._semnalat:
			self._semnalat = False
			A.semnalEcran(False)

	# ------------------------------------------------------------------ citirea

	def _citeste(self):
		self._ceas.stop()
		try:
			s = A.stare()
		except Exception as eroare:
			print("[HdsAccesSsh] starea: %r" % (eroare,))
			self._ceas.start(CITIRE_MS * 3, True)
			return
		self._stare = s
		parola = A.parolaDeAratat() if (s["parola_de_vazut"] and s["fel_parola"] == "pusa") else ""
		self._parola = parola
		self["eticheta"].setText(A.textEticheta(s))
		self["parola"].setText(parola or A.textParolaScurt(s))
		self["despre"].setText(A.textParola(s))
		self["cum"].setText(A.textCum(self._adresa, s.get("ftp")))
		alarme = A.textAlarme(s)
		# o stare periculoasa ia locul numarului de chei (cheile se vad oricum in lista)
		self["alarma"].setText(alarme[0] if alarme else "")
		self["chei"].setText("" if alarme else A.textChei(s))
		self._puneRanduri(randuri(s, parola))
		self._arataLucrarea(s["lucrare"])
		if self._brut:
			self._arataBrut(False)
		self._ceas.start(CITIRE_MS, True)

	def _puneRanduri(self, noi):
		if [r[:3] for r in noi] == [r[:3] for r in self._randuri]:
			return
		ales = self._randAlesAcum()
		self._randuri = noi
		self["list"].setList([r[0] for r in noi])
		index = 0
		if ales is not None:
			for i, r in enumerate(noi):
				if r[1] == ales[1] and (r[1] != STERGE or r[2] == ales[2]):
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
		if lucreaza:
			self["rand"].setText(A.textLucrare(lucreaza))
		else:
			self["rand"].setText(r[3] if r else "")

	def _arataLucrarea(self, l):
		ultima = l["ultima"]
		if ultima and ultima["id"] != self._vazuta:
			self._vazuta = ultima["id"]
			self["mesaj"].setText(ultima["mesaj"])
			self._mesajPana = time() + MESAJ_S
		elif self._mesajPana and time() > self._mesajPana:
			self._mesajPana = 0
			self["mesaj"].setText("")
		self._randAles()

	def _mesaj(self, text):
		self["mesaj"].setText(text)
		self._mesajPana = time() + MESAJ_S

	# ------------------------------------------------------------------ tastele

	def sus(self):
		if self._brut:
			self["brut"].pageUp()
			return
		self["list"].up()

	def jos(self):
		if self._brut:
			self["brut"].pageDown()
			return
		self["list"].down()

	def stanga(self):
		if self._brut:
			self._paginaBruta -= 1
			self._arataBrut(True)
		else:
			self["list"].pageUp()

	def dreapta(self):
		if self._brut:
			self._paginaBruta += 1
			self._arataBrut(True)
		else:
			self["list"].pageDown()

	def _intreaba(self, text, cand_da):
		self.session.openWithCallback(cand_da, MessageBox, text, MessageBox.TYPE_YESNO, default=False)

	def ok(self):
		if self._brut:
			self.albastru()
			return
		r = self._randAlesAcum()
		if r is None:
			return
		actiune, argument = r[1], r[2]
		if actiune in CU_LUCRARE and self._lucreaza():
			self._mesaj(_("Așteaptă să se termine ce ai pornit înainte."))
			return
		if actiune == INCHIDE:
			self.inchide()
		elif actiune == BRUT:
			self.albastru()
		elif actiune == SCHIMBA:
			self.session.openWithCallback(self._parolaScrisa, VirtualKeyBoard,
				title=_("Parola nouă: 4-64 de semne, fără spații și fără diacritice"), text=self._parola)
		elif actiune == STICK:
			self._porneste_lucrare(A.pornesteStick)
		elif actiune == NOUA:
			if self._stare and self._stare["fel_parola"] == "pusa":
				self._intreaba(_("Faci o parolă nouă? Cea de acum nu mai merge."), self._confirmaNoua)
			else:
				self._porneste_lucrare(A.pornesteParolaNoua)
		elif actiune == STERGE:
			self._deSters = argument
			cheie = [c for c in (self._stare["chei"] if self._stare else []) if c["amprenta"] == argument]
			nume = A.numeCheie(cheie[0]) if cheie else argument
			self._intreaba(_("Ștergi cheia %s?") % nume, self._confirmaSterge)
		elif actiune == FARA_PAROLA:
			if argument:
				self._intreaba(_("Pornești intrarea fără parolă? Oricine din rețeaua ta de acasă va intra pe receptor."),
					self._confirmaFaraParola)
			else:
				self._porneste_lucrare(lambda: A.pornesteFaraParola(False))

	def _parolaScrisa(self, text):
		"""Parola scrisa la tastatura (None cu EXIT): o parola care nu se primeste da motivul si nu schimba nimic."""
		if text is None:
			return
		motiv = A.motivParola(text)
		if motiv:
			self._mesaj(motiv)
			return
		if self._lucreaza():
			self._mesaj(_("Așteaptă să se termine ce ai pornit înainte."))
			return
		self._porneste_lucrare(lambda: A.pornestePuneParola(text))

	def _confirmaNoua(self, da):
		if da:
			self._porneste_lucrare(A.pornesteParolaNoua)

	def _confirmaSterge(self, da):
		if da:
			self._porneste_lucrare(lambda: A.pornesteSterge(self._deSters))

	def _confirmaFaraParola(self, da):
		if da:
			self._porneste_lucrare(lambda: A.pornesteFaraParola(True))

	def _porneste_lucrare(self, porneste):
		if porneste() is None:
			self._mesaj(_("Așteaptă să se termine ce ai pornit înainte."))
		self._citeste()

	# ------------------------------------------------------------------ textul brut

	def albastru(self):
		self._brut = not self._brut
		if self._brut:
			self["key_blue"].setText(_("Pe scurt"))
			self["ajutor"].setText(_("Stânga/Dreapta: alt fișier · Sus/Jos: derulare · OK sau EXIT: înapoi"))
			self["brut"].show()
			self._arataBrut(True)
		else:
			self["brut"].hide()
			self["ajutor"].setText("")
			self["key_blue"].setText(_("Text brut"))
			self.setTitle(_("Parola receptorului"))
			self["titlu"].setText(_("Parola receptorului"))

	def _arataBrut(self, sus):
		pagini = A.paginiBrute()
		self._paginaBruta %= len(pagini)
		titlu, cale, text = pagini[self._paginaBruta]
		self.setTitle("%s: %s (%d/%d)" % (_("Parola receptorului"), cale, self._paginaBruta + 1, len(pagini)))
		self["titlu"].setText("%s  %d/%d" % (titlu, self._paginaBruta + 1, len(pagini)))
		if sus or text != self._textBrut:
			self._textBrut = text
			self["brut"].setText("%s\n\n%s" % (cale, text))

	def inchide(self):
		if self._brut:
			self.albastru()
			return
		self.close()
