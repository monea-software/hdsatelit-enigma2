# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsDabUsb.py: ce stie imaginea despre radioul DAB+ terestru printr-un stick USB. Partea mare (receptia, cautarea, lista de posturi) e
# pluginul DabTerestru din feed; aici ramane numai ce trebuie sa mearga si fara el:
# - inventarul stickurilor, numai citire din sysfs: stickul nu se deschide, deci nu se ia nimanui si nu cere procesor;
# - starea pentru om: stick lipsa, stick nesuportat, port USB prea lent, stick folosit de DVB-T, stick bun;
# - pregatirea: gaseste pachetul in feed si il instaleaza din acelasi ecran, prin aceeasi lucrare opkg ca Extensiile.
#
# Driverul nucleului: nu se pune niciun blacklist si nu se descarca niciun modul. Un alt stick poate fi chiar tunerul DVB-T al omului.
# Daca dvb_usb_rtl28xxu tine stickul ales, librtlsdr (construita cu DETACH_KERNEL_DRIVER) il desprinde numai pe acela, la deschidere,
# si il reataseaza la inchidere. Numai cand interfata chiar foloseste acum tunerul acelui stick se spune „folosit de DVB-T” si nu se atinge.
#
# Fara enigma2 la incarcare: probele de pe PC dau dosarele prin parametri.
import os
import threading

PLUGIN = "/usr/lib/enigma2/python/Plugins/Extensions/DabTerestru"
PACHET = "enigma2-plugin-extensions-dabterestru"
SYSFS_USB = "/sys/bus/usb/devices"
SYSFS_DVB = "/sys/class/dvb"
FD_PROCES = "/proc/self/fd"
VITEZA_MINIMA = 480          # Mbit/s: 2,048 MS/s pe doi octeti cer cam 33 Mbit/s, deci numai High Speed

LIPSA, NESUPORTAT, VITEZA, DVB, BUN = "lipsa", "nesuportat", "viteza", "dvb", "bun"


def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textul se traduce la folosire."""
	return text


def _t(text):
	"""Traducerea enigma2 (_ din builtins), sau textul insusi (pe PC, fara traduceri)."""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


# stickurile cu RTL2832U pe care le deschide librtlsdr (lista ei de identificatori USB)
STICKURI = {
	(0x0bda, 0x2832): "RTL2832U",
	(0x0bda, 0x2838): "RTL2832U",
	(0x0413, 0x6680): "DigitalNow Quad DVB-T",
	(0x0413, 0x6f0f): "Leadtek WinFast DTV Dongle mini D",
	(0x0458, 0x707f): "Genius TVGo DVB-T03",
	(0x0ccd, 0x00a9): "Terratec Cinergy T Stick Black",
	(0x0ccd, 0x00b3): "Terratec NOXON DAB/DAB+",
	(0x0ccd, 0x00b4): "Terratec Deutschlandradio DAB",
	(0x0ccd, 0x00b5): "Terratec NOXON DAB",
	(0x0ccd, 0x00b7): "Terratec Media Broadcast DAB",
	(0x0ccd, 0x00b8): "Terratec BR DAB",
	(0x0ccd, 0x00b9): "Terratec WDR DAB",
	(0x0ccd, 0x00c0): "Terratec MuellerVerlag DAB",
	(0x0ccd, 0x00c6): "Terratec Fraunhofer DAB",
	(0x0ccd, 0x00d3): "Terratec Cinergy T Stick RC",
	(0x0ccd, 0x00d7): "Terratec T Stick PLUS",
	(0x0ccd, 0x00e0): "Terratec NOXON DAB/DAB+",
	(0x1209, 0x2832): "RTL2832U",
	(0x1554, 0x5020): "PixelView PV-DT235U",
	(0x15f4, 0x0131): "Astrometa DVB-T/DVB-T2",
	(0x15f4, 0x0133): "HanfTek DAB+FM+DVB-T",
	(0x185b, 0x0620): "Compro Videomate U620F",
	(0x185b, 0x0650): "Compro Videomate U650F",
	(0x185b, 0x0680): "Compro Videomate U680F",
	(0x1b80, 0xd393): "GIGABYTE GT-U7300",
	(0x1b80, 0xd394): "DIKOM USB-DVBT HD",
	(0x1b80, 0xd395): "Peak 102569AGPK",
	(0x1b80, 0xd397): "KWorld KW-UB450-T",
	(0x1b80, 0xd398): "Zaapa ZT-MINDVBZP",
	(0x1b80, 0xd39d): "SVEON STV20",
	(0x1b80, 0xd3a4): "Twintech UT-40",
	(0x1b80, 0xd3a8): "ASUS U3100MINI_PLUS_V2",
	(0x1b80, 0xd3af): "SVEON STV27",
	(0x1b80, 0xd3b0): "SVEON STV21",
	(0x1d19, 0x1101): "Dexatek DK DVB-T",
	(0x1d19, 0x1102): "MSI DigiVox mini II",
	(0x1d19, 0x1103): "Dexatek DK 5217 DVB-T",
	(0x1d19, 0x1104): "MSI DigiVox Micro HD",
	(0x1f4d, 0xa803): "Sweex DVB-T USB",
	(0x1f4d, 0xb803): "GTek T803",
	(0x1f4d, 0xc803): "Lifeview LV5TDeluxe",
	(0x1f4d, 0xd286): "MyGica TD312",
	(0x1f4d, 0xd803): "PROlectrix DV107669",
}

# alte stickuri de radio sau de televiziune, cu alt cip: omul afla de ce nu merg, nu ramane cu „stickul nu este conectat”
ALTE_STICKURI = {
	(0x1d50, 0x60a1): "Airspy",
	(0x1d50, 0x6089): "HackRF One",
	(0x1d50, 0xcc15): "HackRF",
	(0x0572, 0xc688): "MyGica T230",
	(0x0572, 0xc689): "MyGica T230C",
	(0x0572, 0x0320): "DVBSky T330",
	(0x048d, 0x9135): "ITE IT9135",
	(0x187f, 0x0202): "Siano",
}
ALTE_FIRME = {0x1df7: "SDRplay", 0x2013: "PCTV", 0x2040: "Hauppauge", 0x734c: "TBS"}
# driverele de tuner care arata ca dispozitivul e un stick DVB, chiar cand nu e in tabelele de sus
PREFIXE_DRIVER = ("dvb", "smsusb", "em28xx", "cx231xx", "dib0700", "af9015", "af9035", "as102")


def _citeste(cale):
	try:
		with open(cale, "rb") as f:
			return f.read(256).decode("utf-8", "replace").strip()
	except (IOError, OSError):
		return ""


def _hex(text):
	try:
		return int(text, 16)
	except ValueError:
		return -1


def _driver(rad, dev):
	"""Numele driverului care tine prima interfata a dispozitivului, sau „”."""
	try:
		return os.path.basename(os.readlink(os.path.join(rad, dev, dev + ":1.0", "driver")))
	except OSError:
		return ""


def _frontend_folosit(rad, dev, rad_dvb=SYSFS_DVB, fd_proces=FD_PROCES):
	"""True cand interfata tine deschis acum tunerul DVB al acestui stick (un descriptor spre /dev/dvb/adapterN/frontendM)."""
	try:
		nume = os.listdir(rad_dvb)
	except OSError:
		return False
	cale_dev = os.path.realpath(os.path.join(rad, dev))
	tinte = []
	for n in nume:
		if ".frontend" not in n:
			continue
		if os.path.realpath(os.path.join(rad_dvb, n, "device")).startswith(cale_dev + os.sep):
			a, f = n.replace("dvb", "", 1).split(".frontend", 1)
			tinte.append("/dev/dvb/adapter%s/frontend%s" % (a, f))
	if not tinte:
		return False
	try:
		for fd in os.listdir(fd_proces):
			try:
				if os.readlink(os.path.join(fd_proces, fd)) in tinte:
					return True
			except OSError:
				continue
	except OSError:
		pass
	return False


def _nume_stick(vid, pid, rad, dev, tabel):
	"""Numele pe care il scrie stickul despre el („NESDR SMArt v5”), cu fabricantul; altfel cel din tabel."""
	produs = _citeste(os.path.join(rad, dev, "product"))
	firma = _citeste(os.path.join(rad, dev, "manufacturer"))
	if produs and not produs.upper().startswith("RTL28"):
		return produs if not firma or firma.lower() in produs.lower() or firma.upper() == "REALTEK" else "%s %s" % (firma, produs)
	return tabel.get((vid, pid)) or produs or "%04x:%04x" % (vid, pid)


def inventar(rad=SYSFS_USB, rad_dvb=SYSFS_DVB, fd_proces=FD_PROCES):
	"""[stick]: toate stickurile de radio sau TV de pe USB, cele bune primele, in ordine stabila. Citeste numai sysfs; nu deschide nimic.
	Un stick: cale (portul USB, de exemplu 1-1.2), vid, pid, nume, serial, viteza (Mbit/s), driver, compatibil, folosit."""
	try:
		nume = sorted(os.listdir(rad))
	except OSError:
		return []
	rez = []
	for dev in nume:
		if ":" in dev or dev.startswith("usb"):
			continue
		vid = _hex(_citeste(os.path.join(rad, dev, "idVendor")))
		pid = _hex(_citeste(os.path.join(rad, dev, "idProduct")))
		if vid < 0 or pid < 0:
			continue
		compatibil = (vid, pid) in STICKURI
		driver = _driver(rad, dev)
		alt = (vid, pid) in ALTE_STICKURI or vid in ALTE_FIRME or driver.startswith(PREFIXE_DRIVER)
		if not compatibil and not alt:
			continue
		try:
			viteza = int(float(_citeste(os.path.join(rad, dev, "speed")) or "0"))
		except ValueError:
			viteza = 0
		tabel = STICKURI if compatibil else ALTE_STICKURI
		numele = _nume_stick(vid, pid, rad, dev, tabel)
		if not compatibil and numele == "%04x:%04x" % (vid, pid) and vid in ALTE_FIRME:
			numele = ALTE_FIRME[vid]
		rez.append({"cale": dev, "vid": vid, "pid": pid, "nume": numele, "serial": _citeste(os.path.join(rad, dev, "serial")),
			"viteza": viteza, "driver": driver, "compatibil": compatibil,
			"folosit": bool(compatibil and driver.startswith("dvb") and _frontend_folosit(rad, dev, rad_dvb, fd_proces))})
	rez.sort(key=lambda s: (0 if s["compatibil"] else 1, s["cale"]))
	return rez


def alege(inv, cale_aleasa=""):
	"""Stickul cu care se lucreaza: cel ales de om, daca e conectat; altfel primul compatibil. None cand nu e niciunul."""
	bune = [s for s in inv if s["compatibil"]]
	for s in bune:
		if s["cale"] == cale_aleasa:
			return s
	return bune[0] if bune else None


def fel_stare(inv, cale_aleasa=""):
	"""(fel, stickul): LIPSA, NESUPORTAT, VITEZA, DVB sau BUN."""
	s = alege(inv, cale_aleasa)
	if s is None:
		return (NESUPORTAT, inv[0]) if inv else (LIPSA, None)
	if s["folosit"]:
		return DVB, s
	if s["viteza"] and s["viteza"] < VITEZA_MINIMA:
		return VITEZA, s
	return BUN, s


def text_stare(fel, stick):
	"""Ce vede omul, la fel pe televizor si in web: {fel, titlu, rand, eticheta, culoare, nume}. Culoare: bun, galben sau rau."""
	nume = stick["nume"] if stick else ""
	if fel == LIPSA:
		return {"fel": fel, "nume": "", "titlu": _t("Stickul nu este conectat"), "culoare": "rau", "eticheta": _t("Lipsește"),
			"rand": _t("Pune un stick RTL-SDR într-un port USB și leagă antena pentru banda III. Ecranul îl vede singur.")}
	if fel == NESUPORTAT:
		return {"fel": fel, "nume": nume, "titlu": _t("Stick nesuportat: %s") % nume, "culoare": "rau", "eticheta": _t("Nesuportat"),
			"rand": _t("Radioul DAB+ merge numai cu stickuri cu cipul RTL2832U, de exemplu NESDR sau RTL-SDR Blog.")}
	if fel == DVB:
		return {"fel": fel, "nume": nume, "titlu": _t("Stick folosit de DVB-T: %s") % nume, "culoare": "galben", "eticheta": _t("Ocupat"),
			"rand": _t("Receptorul îl folosește acum ca tuner DVB-T. Pune alt stick sau oprește canalul DVB-T.")}
	if fel == VITEZA:
		return {"fel": fel, "nume": nume, "titlu": _t("Port USB prea lent: %s") % nume, "culoare": "galben", "eticheta": _t("Port lent"),
			"rand": _t("Stickul cere USB 2.0. Mută-l într-un alt port USB sau scoate hubul.")}
	return {"fel": BUN, "nume": nume, "titlu": _t("Stick pregătit: %s") % nume, "culoare": "bun", "eticheta": _t("Pregătit"),
		"rand": _t("Apasă Caută posturi. Căutarea nu ocupă niciun tuner de satelit.")}


def plugin_instalat(cale=PLUGIN):
	return os.path.isfile(os.path.join(cale, "plugin.py")) or os.path.isfile(os.path.join(cale, "plugin.pyc"))


def _X():
	from Components import HdsExtensiiLucru
	return HdsExtensiiLucru


def _pe_fir(lucru, gata):
	"""lucru() pe un fir separat, gata(rezultat, eroare) pe firul interfetei."""
	from twisted.internet import reactor

	def alearga():
		rez, err = None, None
		try:
			rez = lucru()
		except Exception as e:
			err = e
		reactor.callFromThread(gata, rez, err)
	threading.Thread(target=alearga, name="HdsDabUsb", daemon=True).start()


class Pregatire(object):
	"""Instalarea pluginului din feed, una singura pe receptor: ce porneste pagina vede si televizorul, si invers. Numai pe firul interfetei.
	Faze: nimic, citesc, lista (opkg update), de_instalat, instalare, gata, lipsa (nu e in feed), eroare."""

	def __init__(self, X=None, pe_fir=_pe_fir, instalat=plugin_instalat):
		self._x = X
		self.pe_fir = pe_fir
		self.instalat = instalat
		self.faza = "nimic"
		self.text = ""
		self.marime = 0
		self.catalog = None
		self.pachet = None
		self.lucrare = None
		self.a_cerut_lista = False
		self.vrea_instalare = False

	def X(self):
		return self._x if self._x is not None else _X()

	def _pune(self, faza, text=""):
		self.faza = faza
		self.text = text

	def verifica(self, instaleaza=False):
		"""Afla din feed marimea. Cu instaleaza=True, porneste si instalarea, fara alta intrebare: omul a apasat „Pregateste”."""
		if instaleaza:
			self.vrea_instalare = True
		if self.instalat():
			self._pune("gata")
			return
		if self.faza in ("citesc", "lista", "instalare"):
			return
		self._pune("citesc", _t("Caut programul de recepție..."))
		self.pe_fir(self.X().incarcaCatalog, self._catalog_citit)

	def _catalog_citit(self, catalog, eroare):
		if eroare is not None or catalog is None:
			self._pune("eroare", _t("Nu am putut citi lista de programe. Încearcă din nou."))
			self.vrea_instalare = False
			return
		self.catalog = catalog
		self.pachet = catalog._toate.get(PACHET)
		if self.pachet is None:
			if not self.a_cerut_lista:
				self.a_cerut_lista = True
				self._cere_lista()
				return
			self.a_cerut_lista = False
			self.vrea_instalare = False
			self._pune("lipsa", _t("Programul de recepție nu e în lista de pe internet. Verifică legătura la internet și încearcă din nou."))
			return
		dep = catalog.dependente_de_instalat(self.pachet)
		self.marime = self.pachet.marime + sum(d.marime for d in dep)
		self._pune("de_instalat", _t("Programul de recepție nu e încă pe receptor."))
		if self.vrea_instalare:
			self.instaleaza()

	def _cere_lista(self):
		"""opkg update, pe drumul Extensiilor; urmat de stare()."""
		X = self.X()
		self._pune("lista", _t("Descarc lista de programe..."))
		if not X.descarcareInCurs():
			if X.motivOcupat() is not None:
				self.vrea_instalare = False
				self._pune("eroare", X.motivOcupat()[0])
				return
			X.pornesteDescarcarea()

	def instaleaza(self):
		X = self.X()
		self.vrea_instalare = False
		if self.pachet is None:
			self.verifica(True)
			return
		ocupat = X.motivOcupat()
		if ocupat is not None:
			self._pune("eroare", ocupat[0])
			return
		plan, eroare = X.planInstalare(self.catalog, self.pachet)
		if plan is None:
			self._pune("eroare", eroare[0])
			return
		self._pune("instalare", _t("Se instalează programul de recepție..."))
		from Components.PluginComponent import plugins
		self.lucrare = X.pornesteLucrarea(plan, plugins=plugins, din_web=False)
		self.lucrare.asculta(self._lucrare)

	def _lucrare(self, fel, *date):
		if fel != "gata":
			return
		l, self.lucrare = self.lucrare, None
		if self.instalat():
			self._pune("gata")
			return
		cod = date[0] if date else None
		motiv = (getattr(l, "rezultat", "") or "") if l is not None else ""
		text = _t("Instalarea nu a reușit. Verifică legătura la internet și încearcă din nou.")
		self._pune("eroare", "%s %s" % (text, motiv) if isinstance(motiv, str) and motiv else text)
		print("[HdsDabUsb] instalarea: codul %s" % cod)

	def stare(self):
		"""{faza, text, marime (octeti), pas}. Se poate chema oricand; urmareste descarcarea listei."""
		if self.faza == "lista" and not self.X().descarcareInCurs():
			self._pune("citesc", _t("Caut programul de recepție..."))
			self.pe_fir(self.X().incarcaCatalog, self._catalog_citit)
		if self.instalat() and self.faza != "instalare":
			self._pune("gata")
		pas = ""
		if self.lucrare is not None:
			pas = getattr(self.lucrare, "pas", "") or ""
		return {"faza": self.faza, "text": self.text, "marime": self.marime, "pas": pas}


_pregatire = []


def pregatire():
	if not _pregatire:
		_pregatire.append(Pregatire())
	return _pregatire[0]
