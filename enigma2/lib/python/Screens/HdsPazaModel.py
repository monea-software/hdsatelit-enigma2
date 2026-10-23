# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsPazaModel.py (ecranul): mesajul aratat in locul interfetei cand imaginea ruleaza pe alt receptor decat cel pentru
# care e construita (Components/HdsPazaModel.py). Garda din enigma2.sh a oprit deja carligul trusei; showiframe (el
# da imaginea pe HDMI si drumul tastelor telecomenzii) l-a pornit numai daca stie ca nu scrie nimic pe receptor (cu
# UPD_PATH-ul etichetei pus in /proc/stb/info/upd_path, vezi garda). Cand showiframe nu a pornit, pe un receptor
# adevarat e posibil ca mesajul sa nu se vada si tastele sa nu ajunga aici; mesajul ramane atunci in interfata web.
#
# Continutul, de sus in jos: titlul („Software pentru alt receptor”, sau „Receptorul nu poate fi recunoscut” cand
# amprenta nu s-a putut citi), frazele simple (pentru ce receptor e software-ul, ce receptor e acesta, ca nu s-a scris
# nimic, ce se poate face), apoi, mai mic, cate un rand tehnic pentru fiecare nepotrivire si randul cu adresa paginii
# web. Toate textele vin din Components/HdsPazaModel.mesajPornire, aceleasi ca in pagina web (paza_model_web.py).
# Adresa se afla fara sa se trimita nimic in retea; cat timp reteaua nu are inca adresa, se incearca din nou la 5 s.
#
# Fereastra nu se inchide: OK si EXIT nu fac nimic (interfata nu porneste mai departe pe alt receptor). Tasta de
# pornire trece prin actiunile globale din mytest.py (PowerKey), care cer ALLOW_SUSPEND: apasarea scurta duce in
# standby (sau opreste, dupa setare), iar cea lunga face ce spune setarea ei, pe acelasi drum ca pe InfoBar.
#
# Skinul: facut la deschidere dupa marimea ecranului (asezarea e gandita pe 1920x1080), numai cu fontul „Regular” si
# culori scrise direct, ca sa arate la fel in orice skin (niciun skin nu are un bloc cu aceste nume). Inaltimile sunt
# socotite pentru cele 13 limbi: pana la sapte randuri tehnice, fraza cea mai lunga pe trei randuri.
#
# HdsPazaModelRefuz: fereastra refuzului unui pachet in actualizarea din meniu (Screens/HdsSoftwareUpdate.py); textul
# simplu sus, randurile tehnice mai mic, dedesubt, si OK sau EXIT o inchide. HdsPazaModelIntrebare: intrebarile aceluiasi
# ecran (verificarea pachetului, ultima confirmare), cu „Da” / „Nu” alese cu sagetile si OK. Fereastra de mesaj a
# skinului HDSatelit are loc numai pentru trei randuri, iar aceste texte au mai multe.

from enigma import eTimer, getDesktop

from .Screen import Screen
from Components.ActionMap import ActionMap
from Components.MenuList import MenuList
from Components.Sources.StaticText import StaticText

PAGINA_WEB = "/paza-model"
PORT_WEB_IMPLICIT = 80
# portul pe care asculta interfata web, scris de HdsWebControl la pornire (8080 cand 80 era ocupat)
CALE_PORT_ACUM = "/var/run/hdswebcontrol.port"
INTERVAL_ADRESA_MS = 5000
INCERCARI_ADRESA = 36


def _scara(latime, inaltime):
	def x(v):
		return int(round(v * latime / 1920.0))

	def y(v):
		return int(round(v * inaltime / 1080.0))
	return x, y


def skinEcran(latime, inaltime):
	"""Skinul pe tot ecranul, socotit pentru `latime` x `inaltime` (asezarea e gandita pe 1920x1080)."""
	x, y = _scara(latime, inaltime)
	return """
	<screen name="HdsPazaModel" position="0,0" size="%(l)d,%(h)d" flags="wfNoBorder" backgroundColor="#00101828" title="Software pentru alt receptor">
		<eLabel position="%(mx)d,%(ly)d" size="%(cl)d,%(linie)d" backgroundColor="#00f5b83d" zPosition="1" />
		<widget source="titlu" render="Label" position="%(mx)d,%(ty)d" size="%(cl)d,%(th)d" font="Regular;%(tf)d" halign="left" valign="center" foregroundColor="#00ffffff" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget source="mesaj" render="Label" position="%(mx)d,%(my)d" size="%(cl)d,%(mh)d" font="Regular;%(mf)d" halign="left" valign="top" foregroundColor="#00f2f4f8" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget source="tehnic" render="Label" position="%(mx)d,%(ey)d" size="%(cl)d,%(eh)d" font="Regular;%(ef)d" halign="left" valign="top" foregroundColor="#00aab4c4" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget source="nota" render="Label" position="%(mx)d,%(ny)d" size="%(cl)d,%(nh)d" font="Regular;%(ef)d" halign="left" valign="center" foregroundColor="#00aab4c4" backgroundColor="#00101828" transparent="1" zPosition="1" />
	</screen>""" % {
		"l": latime, "h": inaltime, "mx": x(160), "cl": latime - 2 * x(160), "linie": max(2, y(4)),
		"ty": y(60), "th": y(80), "tf": y(56), "ly": y(150),
		"my": y(175), "mh": y(520), "mf": y(34),
		"ey": y(705), "eh": y(290), "ef": y(26),
		"ny": y(1000), "nh": y(45),
	}


def portWeb():
	"""Portul pe care asculta interfata web (CALE_PORT_ACUM), apoi setarea pluginului HdsWebControl, apoi cel implicit"""
	try:
		with open(CALE_PORT_ACUM, encoding="ascii") as f:
			port = int(f.read(16).strip())
		if 0 < port < 65536:
			return port
	except (IOError, OSError, ValueError):
		pass
	try:
		from Components.config import config
		return int(config.plugins.hdswebcontrol.port.value)
	except Exception:
		return PORT_WEB_IMPLICIT


def adresaIp():
	"""Adresa IPv4 a receptorului in reteaua locala, sau "". Intai interfata rutei implicite (un connect UDP numai
	alege ruta, nu trimite nimic), apoi eth0 si wlan0 citite din nucleu (SIOCGIFADDR)."""
	import socket
	ip = ""
	try:
		s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		try:
			s.connect(("192.0.2.1", 9))
			ip = s.getsockname()[0]
		finally:
			s.close()
	except (OSError, socket.error, ValueError):
		ip = ""
	if not ip or ip.startswith("0.") or ip.startswith("127."):
		ip = ""
		try:
			import fcntl
			import struct
			s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
			try:
				for nume in ("eth0", "wlan0"):
					try:
						date = fcntl.ioctl(s.fileno(), 0x8915, struct.pack("256s", nume.encode("ascii")))
						ip = socket.inet_ntoa(date[20:24])
						break
					except (OSError, IOError):
						continue
			finally:
				s.close()
		except (ImportError, OSError, socket.error):
			ip = ""
	return ip if ip and not ip.startswith("0.") and not ip.startswith("127.") else ""


def adresaWeb(ip=None, port=None):
	"""http://<ip>[:port]/paza-model, sau "" cat timp receptorul nu are adresa in retea"""
	ip = adresaIp() if ip is None else ip
	if not ip:
		return ""
	port = portWeb() if port is None else port
	return "http://%s%s%s" % (ip, "" if port == 80 else ":%d" % port, PAGINA_WEB)


def textNota(adresa):
	if adresa:
		return _("Același mesaj apare și în interfața web a receptorului: %s") % adresa
	return _("Același mesaj apare și în interfața web a receptorului, la pagina /paza-model.")


def texte(verdict, adresa=""):
	"""(titlu, mesaj, tehnic, nota) din verdictul lui Components.HdsPazaModel.verdict()"""
	from Components import HdsPazaModel
	titlu, fraze, tehnice = HdsPazaModel.mesajPornire(verdict)
	return titlu, "\n\n".join(fraze), "\n".join(tehnice), textNota(adresa)


def skinRefuz(latime, inaltime):
	"""Fereastra refuzului, in mijlocul ecranului, socotita pentru `latime` x `inaltime` (asezarea pe 1920x1080)."""
	x, y = _scara(latime, inaltime)
	fl, fh = x(1400), y(800)
	return """
	<screen name="HdsPazaModelRefuz" position="center,center" size="%(fl)d,%(fh)d" flags="wfNoBorder" backgroundColor="#00101828" title="Pachetul nu se scrie">
		<eLabel position="0,0" size="%(fl)d,%(linie)d" backgroundColor="#00f5b83d" zPosition="1" />
		<widget source="titlu" render="Label" position="%(mx)d,%(ty)d" size="%(cl)d,%(th)d" font="Regular;%(tf)d" halign="left" valign="center" foregroundColor="#00ffffff" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget source="mesaj" render="Label" position="%(mx)d,%(my)d" size="%(cl)d,%(mh)d" font="Regular;%(mf)d" halign="left" valign="top" foregroundColor="#00f2f4f8" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget source="tehnic" render="Label" position="%(mx)d,%(ey)d" size="%(cl)d,%(eh)d" font="Regular;%(ef)d" halign="left" valign="top" foregroundColor="#00aab4c4" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget source="nota" render="Label" position="%(mx)d,%(ny)d" size="%(cl)d,%(nh)d" font="Regular;%(ef)d" halign="left" valign="center" foregroundColor="#00aab4c4" backgroundColor="#00101828" transparent="1" zPosition="1" />
	</screen>""" % {
		"fl": fl, "fh": fh, "linie": max(2, y(4)), "mx": x(50), "cl": fl - 2 * x(50),
		"ty": y(25), "th": y(65), "tf": y(44),
		"my": y(105), "mh": y(330), "mf": y(30),
		"ey": y(445), "eh": y(275), "ef": y(24),
		"ny": y(735), "nh": y(45),
	}


def texteRefuz(text):
	"""(mesaj, tehnic) din textul lui Components.HdsPazaModel.textRefuz: randurile tehnice vin dupa un rand gol"""
	parti = (text or "").split("\n\n", 1)
	return parti[0], (parti[1] if len(parti) > 1 else "")


def skinIntrebare(latime, inaltime, randuri_mesaj=9, randuri_tehnic=6):
	"""Fereastra unei intrebari cu „Da” / „Nu”, in mijlocul ecranului: titlul, textul (cel mult `randuri_mesaj`
	randuri), randurile tehnice mai mici (cel mult `randuri_tehnic`), cele doua alegeri si nota tastelor. Inaltimea
	ferestrei urmeaza numarul de randuri (asezarea pe 1920x1080)."""
	x, y = _scara(latime, inaltime)
	fl = x(1400)
	ty, th = 25, 65
	my = ty + th + 15
	mh = randuri_mesaj * 41
	ey = my + mh + 10
	eh = max(1, randuri_tehnic) * 33 if randuri_tehnic else 1
	ly = ey + eh + 15
	lh = 2 * 56
	ny = ly + lh + 15
	nh = 45
	fh = ny + nh + 20
	return """
	<screen name="HdsPazaModelIntrebare" position="center,center" size="%(fl)d,%(fh)d" flags="wfNoBorder" backgroundColor="#00101828" title="Întrebare">
		<eLabel position="0,0" size="%(fl)d,%(linie)d" backgroundColor="#00f5b83d" zPosition="1" />
		<widget source="titlu" render="Label" position="%(mx)d,%(ty)d" size="%(cl)d,%(th)d" font="Regular;%(tf)d" halign="left" valign="center" foregroundColor="#00ffffff" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget source="mesaj" render="Label" position="%(mx)d,%(my)d" size="%(cl)d,%(mh)d" font="Regular;%(mf)d" halign="left" valign="top" foregroundColor="#00f2f4f8" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget source="tehnic" render="Label" position="%(mx)d,%(ey)d" size="%(cl)d,%(eh)d" font="Regular;%(ef)d" halign="left" valign="top" foregroundColor="#00aab4c4" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget name="alegeri" position="%(mx)d,%(ly)d" size="%(ll)d,%(lh)d" font="Regular;%(lf)d" itemHeight="%(ih)d" foregroundColor="#00f2f4f8" backgroundColor="#00101828" foregroundColorSelected="#00101828" backgroundColorSelected="#00f5b83d" transparent="0" zPosition="1" />
		<widget source="nota" render="Label" position="%(mx)d,%(ny)d" size="%(cl)d,%(nh)d" font="Regular;%(ef)d" halign="left" valign="center" foregroundColor="#00aab4c4" backgroundColor="#00101828" transparent="1" zPosition="1" />
	</screen>""" % {
		"fl": fl, "fh": y(fh), "linie": max(2, y(4)), "mx": x(50), "cl": fl - 2 * x(50),
		"ty": y(ty), "th": y(th), "tf": y(44),
		"my": y(my), "mh": y(mh), "mf": y(30),
		"ey": y(ey), "eh": max(1, y(eh)), "ef": y(24),
		"ly": y(ly), "lh": y(lh), "ll": x(600), "lf": y(32), "ih": y(56),
		"ny": y(ny), "nh": y(nh),
	}


class HdsPazaModelRefuz(Screen):
	"""text: refuzul pazei pentru un pachet (Components.HdsPazaModel.textRefuz); OK sau EXIT inchide."""

	def __init__(self, session, text, titlu=None):
		marime = getDesktop(0).size()
		self.skin = skinRefuz(marime.width(), marime.height())
		Screen.__init__(self, session)
		titlu = titlu or _("Pachetul nu se scrie")
		mesaj, tehnic = texteRefuz(text)
		self.setTitle(titlu)
		self["titlu"] = StaticText(titlu)
		self["mesaj"] = StaticText(mesaj)
		self["tehnic"] = StaticText(tehnic)
		self["nota"] = StaticText(_("OK sau EXIT închide fereastra."))
		self["actiuni"] = ActionMap(["OkCancelActions"], {
			"ok": self.close,
			"cancel": self.close,
		}, -1)


class HdsPazaModelIntrebare(Screen):
	"""O intrebare cu doua alegeri; close(True) pentru prima („Da ...”), close(False) pentru „Nu” sau EXIT.
	text: textul simplu, apoi, dupa un rand gol, randurile tehnice (ca la texteRefuz). implicit_da: alegerea de la
	deschidere."""

	def __init__(self, session, text, titlu, da=None, nu=None, implicit_da=False, randuri_mesaj=9, randuri_tehnic=6):
		marime = getDesktop(0).size()
		self.skin = skinIntrebare(marime.width(), marime.height(), randuri_mesaj, randuri_tehnic)
		Screen.__init__(self, session)
		mesaj, tehnic = texteRefuz(text)
		self.setTitle(titlu)
		self._implicit = 0 if implicit_da else 1
		self["titlu"] = StaticText(titlu)
		self["mesaj"] = StaticText(mesaj)
		self["tehnic"] = StaticText(tehnic)
		self["alegeri"] = MenuList([da or _("Da"), nu or _("Nu")])
		self["nota"] = StaticText(_("Săgețile sus și jos aleg, OK confirmă, EXIT înseamnă „Nu”."))
		self["actiuni"] = ActionMap(["OkCancelActions", "DirectionActions"], {
			"ok": self._ok,
			"cancel": self._nu,
			"up": self._sus,
			"down": self._jos,
		}, -1)
		self.onLayoutFinish.append(self._laInceput)

	def _laInceput(self):
		self["alegeri"].moveToIndex(self._implicit)

	def _sus(self):
		self["alegeri"].up()

	def _jos(self):
		self["alegeri"].down()

	def _ok(self):
		self.close(self["alegeri"].getSelectionIndex() == 0)

	def _nu(self):
		self.close(False)


class HdsPazaModel(Screen):
	"""verdict: dict-ul lui Components.HdsPazaModel.verdict(); fara el se citeste acum."""

	# standby opreste canalul (nu ruleaza niciunul aici); mytest.py PowerKey cere atributul pentru standby si oprire
	ALLOW_SUSPEND = Screen.SUSPEND_STOPS

	def __init__(self, session, verdict=None):
		marime = getDesktop(0).size()
		self.skin = skinEcran(marime.width(), marime.height())
		Screen.__init__(self, session)
		if verdict is None:
			from Components import HdsPazaModel
			verdict = HdsPazaModel.verdict()
		titlu, mesaj, tehnic, nota = texte(verdict, adresaWeb())
		self.setTitle(titlu)
		self["titlu"] = StaticText(titlu)
		self["mesaj"] = StaticText(mesaj)
		self["tehnic"] = StaticText(tehnic)
		self["nota"] = StaticText(nota)
		# OK si EXIT sunt prinse aici ca sa nu inchida fereastra
		self["actiuni"] = ActionMap(["OkCancelActions"], {
			"ok": self.nimic,
			"cancel": self.nimic,
		}, -1)
		self._incercari = 0
		self._ceas = None
		if "http://" not in nota:
			self._ceas = eTimer()
			try:
				self._legatura = self._ceas.timeout.connect(self._cautaAdresa)
			except AttributeError:
				self._ceas.callback.append(self._cautaAdresa)
			self._ceas.start(INTERVAL_ADRESA_MS, False)
		self.onClose.append(self._laInchidere)
		print("[HdsPazaModel] receptor nepotrivit: %s" % " | ".join(tehnic.split("\n")))

	def _cautaAdresa(self):
		self._incercari += 1
		adresa = adresaWeb()
		if adresa:
			self["nota"].setText(textNota(adresa))
		if adresa or self._incercari >= INCERCARI_ADRESA:
			self._ceas.stop()

	def _laInchidere(self):
		if self._ceas is not None:
			self._ceas.stop()

	def nimic(self):
		pass
