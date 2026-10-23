# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# retea_web.py: ecranele de retea de pe televizor in interfata web (HdsWebControl), paginile /retea si /dns.
#
# Orice ecran sau setare de pe receptor are pereche in interfata web. Pe televizor: Meniu > Setari > Retea & Internet >
# Network Connection Setup (Screens/NetworkSetup.py: lista placilor NetworkAdapterSelection, meniul placii
# AdapterSetupConfiguration, setarile placii AdapterSetup, proba NetworkAdapterTest; pentru o placa Wi-Fi si ecranele
# din Screens/WlanSetup.py) si DNS Server Settings (NameserverSetup). Aici, pe /retea, aceleasi lucruri:
# - placile (numele de pe televizor, pornita, legatura, adresa, placa implicita) si, cu doua placi configurate, tasta
#   galbena "Default" (placa implicita, apoi reteaua reporneste);
# - setarile placii, aceleasi randuri: Use Interface, Use DHCP, IP Address, Netmask, Use a gateway, Gateway (randurile
#   Wi-Fi ale extensiei WirelessLan nu sunt: extensia nu e in imagine), "Current settings" (adresa, masca, poarta, DNS
#   primar si secundar) si intrebarea despre a doua placa configurata;
# - proba retelei (placa, legatura, DHCP, adresa IP prin ping, serverele de nume prin nslookup);
# - Restart network;
# - pentru o placa Wi-Fi (driver gasit, ca in meniul placii): starea legaturii (WiFi status), cautarea retelelor,
#   conectarea cu parola (si la o retea ascunsa), cu setarile vechi puse inapoi la esec, ca pe televizor.
# Iar pe /dns lista serverelor DNS: adaugare, scoatere, salvare (/etc/resolv.conf), ca OK pe televizor.
#
# O SINGURA LOGICA: Components/HdsRetea.py (placile, placa implicita, aplicarea, DNS, repornirea) si Components/HdsWlan.py
# (textele si conectarea Wi-Fi), folosite si de ecranele de pe televizor; comenzile le dau iNetwork si WlanControl.
#
# Aplicarea setarilor unei placi, placa implicita, repornirea retelei si conectarea Wi-Fi pot rupe legatura browserului
# cu receptorul: se fac in doi pasi (meniu_comun_web: intrebarea cu avertismentele si adresa la care va fi pagina, apoi
# un cod de unica folosinta), numai din browserul conectat (nu cu ?token=). La fel lista serverelor DNS (ele hotarasc
# unde ajunge receptorul cand cauta un nume). "Renunta" nu schimba nimic.
#
# Rute (poarta comuna a HdsJsonResource; ce schimba ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF):
#   GET  /api/retea                          placile, DNS, lucrarea in curs, proba, Wi-Fi (starea, cautarea, conectarea)
#   POST /api/retea-placa?placa=&sus=0|1&dhcp=0|1&ip=&masca=&are_poarta=0|1&poarta=&alta=0|1   (+ pas / cod)
#   POST /api/retea-implicita?placa=         (+ pas / cod)
#   POST /api/retea-reporneste               (+ pas / cod)
#   POST /api/retea-proba?placa=             porneste proba retelei
#   POST /api/retea-wifi-cauta?placa=        cauta retelele Wi-Fi
#   POST /api/retea-wifi-conecteaza?placa=&ssid=<hex>|nume_ascuns=&securitate=&parola=&ascunsa=0|1   (+ pas / cod)
#   POST /api/retea-wifi-renunta             opreste conectarea in curs (setarile vechi inapoi)
#   GET  /api/dns                            serverele DNS
#   POST /api/dns-seteaza?servere=a.b.c.d,e.f.g.h   lista noua, scrisa ca OK pe televizor (+ pas / cod)
#   GET  /retea[?placa=], GET /dns           paginile
#
# FIRUL: totul pe firul enigma2. Comenzile (ip, ifup, ifdown, ethtool, ping, nslookup, wpa_cli) merg pe consola enigma2
# (iNetwork, WlanControl), fara sa astepte: sfarsitul lor schimba starea de aici, iar pagina o citeste din nou la cateva
# secunde. Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC pun in DEP reteaua lor, modulele si
# ceasul.

import os
import time

MAX_DNS = 10
PROBA_MAX_S = 90
WIFI_STARE_S = 2
CHEI_PLACA = ("placa", "sus", "dhcp", "ip", "masca", "are_poarta", "poarta", "alta", "pas", "cod")
CHEI_WIFI = ("placa", "ssid", "nume_ascuns", "securitate", "ascunsa", "pas", "cod")

# ce dau probele de pe PC in locul celor de pe receptor: "retea" (iNetwork), "HdsRetea", "HdsWlan", "WlanTools",
# "WlanControl", "ceas" (eTimer), "sysfs", "cale_implicita", "acum"
DEP = {}

_STARE = {"lucrare": None, "proba": None, "cautare": None, "conectare": None, "wifi": {}}
_OBIECTE = {"cautare": None, "conectare": None, "stare": {}, "nr": 0}


def _mc():
	from . import meniu_comun_web
	return meniu_comun_web


def _t(text):
	return _mc()._t(text)


def _dep(nume):
	if nume in DEP:
		return DEP[nume]
	if nume == "retea":
		from Components.Network import iNetwork
		return iNetwork
	if nume == "HdsRetea":
		from Components import HdsRetea
		return HdsRetea
	if nume == "HdsWlan":
		from Components import HdsWlan
		return HdsWlan
	if nume == "HdsIpv6":
		from Components import HdsIpv6
		return HdsIpv6
	if nume == "WlanTools":
		from Components import WlanTools
		return WlanTools
	if nume == "WlanControl":
		from Components.WlanControl import WlanControl
		return WlanControl
	if nume == "ceas":
		from enigma import eTimer
		return eTimer
	if nume == "sysfs":
		return "/sys/class/net"
	if nume == "cale_implicita":
		return _dep("HdsRetea").CALE_PLACA_IMPLICITA
	if nume == "acum":
		return time.time
	raise KeyError(nume)


def _acum():
	return _dep("acum")()


# ------------------------------------------------------------------ adresele

def ipDinText(text):
	"""[a, b, c, d] pentru "a.b.c.d" cu numere 0..255 (ca ConfigIP pe televizor), altfel None."""
	parti = (text or "").strip().split(".")
	if len(parti) != 4:
		return None
	rez = []
	for p in parti:
		if not p or len(p) > 3 or not all(c in "0123456789" for c in p):
			return None
		n = int(p)
		if n > 255:
			return None
		rez.append(n)
	return rez


def textIp(ip):
	try:
		if len(ip) == 4 and all(0 <= int(x) <= 255 for x in ip):
			return "%d.%d.%d.%d" % tuple(int(x) for x in ip)
	except (TypeError, ValueError):
		pass
	return ""


def _numar(ip):
	return (ip[0] << 24) | (ip[1] << 16) | (ip[2] << 8) | ip[3]


def prefixMasca(masca):
	"""Lungimea prefixului pentru o masca cu bitii 1 la rand (255.255.255.0 -> 24), altfel None."""
	n = _numar(masca)
	if n == 0:
		return None
	inversa = (~n) & 0xFFFFFFFF
	if inversa & (inversa + 1):
		return None
	return 32 - bin(inversa).count("1")


def adresaGazda(ip, prefix):
	"""True pentru o adresa pe care o poate avea placa in reteaua cu acest prefix."""
	if ip[0] == 0 or ip[0] == 127 or ip[0] >= 224:
		return False
	if prefix <= 30:
		gazda = _numar(ip) & ((1 << (32 - prefix)) - 1)
		if gazda == 0 or gazda == (1 << (32 - prefix)) - 1:
			return False
	return True


def aceeasiRetea(a, b, prefix):
	return (_numar(a) >> (32 - prefix)) == (_numar(b) >> (32 - prefix))


# ------------------------------------------------------------------ starea

def _legatura(placa):
	"""True / False din /sys/class/net/<placa>/carrier (aceeasi stire ca "Link detected" din ethtool), None cand placa
	e oprita."""
	try:
		with open(os.path.join(_dep("sysfs"), placa, "carrier"), "r", encoding="utf-8") as f:
			v = f.read().strip()
	except (IOError, OSError):
		return None
	if v in ("0", "1"):
		return v == "1"
	return None


def _areWifi(placa):
	try:
		return _dep("WlanTools").getWlanDriver(placa, _dep("sysfs")) is not None
	except Exception:
		return False


def _placa(R, H, nume, implicita, configurate, gazda):
	ip = R.getAdapterAttribute(nume, "ip")
	masca = R.getAdapterAttribute(nume, "netmask")
	poarta = R.getAdapterAttribute(nume, "gateway")
	try:
		descriere = R.getFriendlyAdapterDescription(nume)
	except Exception:
		descriere = ""
	alte = [x for x in configurate if x != nume]
	ip_text = textIp(ip) if ip else ""
	return {
		"nume": nume,
		"eticheta": R.getFriendlyAdapterName(nume) or nume,
		"descriere": descriere,
		"sus": R.getAdapterAttribute(nume, "up") is True,
		"dhcp": bool(R.getAdapterAttribute(nume, "dhcp")),
		"ip": "" if ip_text == "0.0.0.0" else ip_text,
		"masca": "" if textIp(masca or []) in ("", "0.0.0.0") else textIp(masca),
		"poarta": "" if textIp(poarta or []) in ("", "0.0.0.0") else textIp(poarta),
		# valorile din formularul de pe televizor (AdapterSetup.createConfig)
		"ip_formular": textIp(ip or [0, 0, 0, 0]),
		"masca_formular": textIp(masca or [255, 0, 0, 0]),
		"poarta_formular": textIp(poarta or [0, 0, 0, 0]),
		"are_poarta": bool(poarta),
		"mac": R.getAdapterAttribute(nume, "mac") or "",
		"legatura": _legatura(nume),
		"wifi": _areWifi(nume),
		"implicita": nume == implicita,
		"configurata": nume in configurate,
		"opreste_alta": H.trebuieOpritaAlta(nume, R),
		"alte": alte,
		"browser": bool(gazda) and ip_text == gazda,
	}


def _copie(x, fara=()):
	if x is None:
		return None
	return dict((k, v) for k, v in x.items() if k not in fara)


def _ipv6():
	"""Starea IPv6 de acum (Components/HdsIpv6.stare: semnul, disable_ipv6, randurile traduse), sau None."""
	try:
		s = _dep("HdsIpv6").stare()
		return {"pornit": bool(s["semn"]), "pornit_acum": s["pornit_acum"], "linii": list(s["linii"])}
	except Exception as eroare:
		print("[HdsWebControl] retea: starea IPv6: %s" % eroare)
		return None


def stare(gazda=None):
	"""Pentru GET /api/retea."""
	R = _dep("retea")
	H = _dep("HdsRetea")
	implicita = H.placaImplicita(R, _dep("cale_implicita"))
	configurate = list(R.getConfiguredAdapters())
	placi = [_placa(R, H, x, implicita, configurate, gazda) for x in H.adaptoare(R)]
	acum = _acum()
	lucrare = _copie(_STARE["lucrare"])
	if lucrare is not None:
		lucrare["secunde"] = int(acum - lucrare.pop("pornit", acum))
	proba = _copie(_STARE["proba"])
	if proba is not None:
		if not proba["gata"] and acum - proba["pornit"] > PROBA_MAX_S:
			_STARE["proba"]["gata"] = True
			proba["gata"] = True
			proba["expirat"] = True
		proba.pop("pornit", None)
		proba["pasi"] = dict(proba["pasi"])
	wifi = {}
	for p in placi:
		if p["wifi"] and p["sus"]:
			wifi[p["nume"]] = _wifiStare(p["nume"])
	W = _dep("HdsWlan")
	return {
		"result": True,
		"placi": placi,
		"implicita_se_poate": len(configurate) >= 2,
		"dns": [textIp(x) for x in _servereDns(R)],
		"lucrare": lucrare,
		"proba": proba,
		"wifi": wifi,
		"cautare": _copie(_STARE["cautare"], ("pornit", "gasite")),
		"conectare": _copie(_STARE["conectare"], ("pornit",)),
		"securitati_ascunse": [[s, W.securityText(s)] for s in W.HIDDEN_SECURITY],
		"ipv6": _ipv6(),
	}


def _servereDns(R):
	servere = getattr(R, "nameservers", None)
	if servere is None:
		servere = [x for x in R.getNameserverList() if x != [0, 0, 0, 0]]
	return list(servere)


# ------------------------------------------------------------------ cele doua trepte (intrebarea, codul)

def _doiPasi(request, argumente, actiune, tinta, intrebare, buton, detalii, fapta):
	mc = _mc()
	refuz = mc.numaiBrowser(request)
	if refuz:
		return {"result": False, "message": refuz}
	if argumente.get("pas") == "renunta":
		mc.uita(actiune, tinta)
		return {"result": True, "message": _t("Nu s-a schimbat nimic.")}
	cod = argumente.get("cod")
	if cod:
		if not mc.verifica(actiune, tinta, cod):
			return mc.codGresit()
		return fapta()
	return mc.raspunsIntrebare(actiune, tinta, intrebare, buton, detalii)


def _ocupat():
	"""Textul refuzului cand alta schimbare a retelei inca lucreaza, altfel None."""
	lucrare = _STARE["lucrare"]
	if lucrare is not None and not lucrare["gata"]:
		return _t("O altă schimbare a rețelei încă lucrează. Așteaptă să se termine.")
	conectare = _STARE["conectare"]
	if conectare is not None and conectare["lucreaza"]:
		return _t("O conectare Wi-Fi încă lucrează. Așteaptă să se termine sau oprește-o.")
	return None


def _lucrare(fel, placa, mesaj_gata):
	_OBIECTE["nr"] += 1
	x = {"nr": _OBIECTE["nr"], "fel": fel, "placa": placa, "gata": False, "pornit": _acum(), "mesaj": "", "eroare": False}
	_STARE["lucrare"] = x

	def gata(_data=True):
		x["gata"] = True
		x["mesaj"] = mesaj_gata
	return x, gata


def _esuat(x, eroare):
	_mc().jurnal("retea: %r" % eroare)
	x["gata"] = True
	x["eroare"] = True
	x["mesaj"] = _t("Schimbarea nu s-a putut face: %s") % eroare


def _url(gazda_port, ip_text, pagina="retea"):
	port = gazda_port[1] if gazda_port else None
	sufix = "" if port in (None, 80) else ":%d" % port
	return "http://%s%s/%s" % (ip_text, sufix, pagina)


def _gazda(request):
	"""(adresa receptorului la care a venit cererea, portul), sau (None, None)."""
	try:
		h = request.getHost()
		return str(h.host), int(h.port)
	except Exception:
		return None, None


# ------------------------------------------------------------------ setarile unei placi

def _citestePlaca(a, R, H):
	"""(valorile, None) sau (None, motivul). Campurile care lipsesc iau valorile de acum, ca formularul de pe
	televizor; un camp trimis trebuie sa fie bun."""
	placa = a.get("placa", "")
	if placa not in H.adaptoare(R):
		return None, _t("Placa de rețea %s nu există pe receptor.") % placa[:20]
	da_nu = {}
	for cheie in ("sus", "dhcp", "are_poarta", "alta"):
		v = a.get(cheie)
		if v is not None and v not in ("0", "1"):
			return None, _t("Valoarea %s nu e bună pentru %s (se alege 0 sau 1).") % (v[:12], cheie)
		da_nu[cheie] = None if v is None else v == "1"
	if da_nu["sus"] is None or da_nu["dhcp"] is None:
		return None, _t("Se trimit sus=0|1 și dhcp=0|1.")
	adrese = {}
	for cheie, atribut, implicit in (("ip", "ip", [0, 0, 0, 0]), ("masca", "netmask", [255, 0, 0, 0]),
			("poarta", "gateway", [0, 0, 0, 0])):
		text = a.get(cheie)
		if text is None:
			adrese[cheie] = R.getAdapterAttribute(placa, atribut) or implicit
			continue
		ip = ipDinText(text)
		if ip is None:
			return None, _t("Adresa %s nu e bună. Se scrie ca 192.168.1.10.") % text[:20]
		adrese[cheie] = ip
	are_poarta = da_nu["are_poarta"]
	if are_poarta is None:
		are_poarta = bool(R.getAdapterAttribute(placa, "gateway"))
	if da_nu["sus"] and not da_nu["dhcp"]:
		prefix = prefixMasca(adrese["masca"])
		if prefix is None:
			return None, _t("Masca %s nu e bună (exemplu: 255.255.255.0).") % textIp(adrese["masca"])
		if not adresaGazda(adrese["ip"], prefix):
			return None, _t("Adresa IP %s nu poate fi a receptorului în această rețea.") % textIp(adrese["ip"])
		if are_poarta:
			p = adrese["poarta"]
			if not adresaGazda(p, prefix) or p == adrese["ip"]:
				return None, _t("Poarta %s nu e bună.") % textIp(p)
			if not aceeasiRetea(p, adrese["ip"], prefix):
				return None, _t("Poarta %s nu e în aceeași rețea cu adresa %s și masca %s.") % (textIp(p),
					textIp(adrese["ip"]), textIp(adrese["masca"]))
	alta = True if da_nu["alta"] is None else da_nu["alta"]
	return {"placa": placa, "sus": da_nu["sus"], "dhcp": da_nu["dhcp"], "ip": adrese["ip"], "masca": adrese["masca"],
		"poarta": adrese["poarta"] if are_poarta else None, "alta": alta}, None


def _schimbata(v, R):
	"""Ca isChanged pe televizor: numai randurile care se vad pe ecran."""
	placa = v["placa"]
	if v["sus"] != (R.getAdapterAttribute(placa, "up") is True):
		return True
	if not v["sus"]:
		return False
	if v["dhcp"] != bool(R.getAdapterAttribute(placa, "dhcp")):
		return True
	if v["dhcp"]:
		return False
	if v["ip"] != (R.getAdapterAttribute(placa, "ip") or [0, 0, 0, 0]):
		return True
	if v["masca"] != (R.getAdapterAttribute(placa, "netmask") or [255, 0, 0, 0]):
		return True
	poarta = R.getAdapterAttribute(placa, "gateway")
	if (v["poarta"] is not None) != bool(poarta):
		return True
	return v["poarta"] is not None and v["poarta"] != poarta


def aplicaPlaca(request):
	"""POST /api/retea-placa: ca OK in "Adapter settings", cu intrebarea si codul."""
	R = _dep("retea")
	H = _dep("HdsRetea")
	a = _mc().argumente(request, CHEI_PLACA, 40)
	v, motiv = _citestePlaca(a, R, H)
	if v is None:
		return {"result": False, "message": motiv}
	if not _schimbata(v, R):
		return {"result": True, "message": _t("Nu s-a schimbat nimic.")}
	placa = v["placa"]
	gazda = _gazda(request)
	alta = v["alta"] and H.trebuieOpritaAlta(placa, R)
	tinta = "%s|%d|%d|%s|%s|%s|%d" % (placa, v["sus"], v["dhcp"], textIp(v["ip"]), textIp(v["masca"]),
		textIp(v["poarta"]) if v["poarta"] else "-", alta)
	ip_acum = textIp(R.getAdapterAttribute(placa, "ip") or [])
	prin_ea = bool(gazda[0]) and gazda[0] == ip_acum
	adresa_noua = textIp(v["ip"]) if v["sus"] and not v["dhcp"] else ""
	detalii = []
	if prin_ea:
		if not v["sus"]:
			detalii.append(_t("Browserul tău e legat la receptor prin această placă. Când placa se oprește, pagina nu "
				"mai răspunde până o pornești din nou de pe televizor."))
		elif v["dhcp"]:
			detalii.append(_t("Browserul tău e legat la receptor prin această placă. Adresa o va da routerul și poate fi "
				"alta decât acum: o vezi pe televizor, la informațiile despre rețea, sau în lista routerului."))
		elif adresa_noua != ip_acum:
			detalii.append(_t("Browserul tău e legat la receptor prin această placă. După aplicare, pagina va fi la "
				"%s.") % _url(gazda, adresa_noua))
	detalii.append(_t("Cât placa pornește din nou, legătura cu receptorul se întrerupe câteva secunde."))
	if alta:
		alte = [x for x in R.getConfiguredAdapters() if x != placa]
		detalii.append(_t("Se oprește și cealaltă placă configurată: %s.") % ", ".join(alte))
		ip_alte = [textIp(R.getAdapterAttribute(x, "ip") or []) for x in alte]
		if gazda[0] and gazda[0] in ip_alte:
			detalii.append(_t("Browserul tău e legat la receptor prin ea: pagina nu va mai răspunde de aici."))
	eticheta = R.getFriendlyAdapterName(placa) or placa

	def fapta():
		ocupat = _ocupat()
		if ocupat:
			return {"result": False, "message": ocupat}
		stare_veche = R.getAdapterAttribute(placa, "up")
		x, gata = _lucrare("placa", placa, _t("Your network configuration has been activated."))

		def aplica(_data=True):
			try:
				H.aplicaPlaca(placa, v["sus"], v["dhcp"], v["ip"], v["masca"], v["poarta"], stare_veche, gata, R)
			except Exception as eroare:
				_esuat(x, eroare)
		try:
			if alta:
				H.opresteCelelalte(placa, aplica, R)
			else:
				aplica()
		except Exception as eroare:
			_esuat(x, eroare)
		if x["eroare"]:
			return {"result": False, "message": x["mesaj"]}
		return {"result": True, "message": _t("Please wait for activation of your network configuration..."),
			"adresa_noua": adresa_noua, "url_nou": _url(gazda, adresa_noua) if adresa_noua else ""}

	return _doiPasi(request, a, "retea-placa", tinta, _t("Activezi aceste setări de rețea pentru %s?") % eticheta,
		_t("Da, aplică"), detalii, fapta)


def placaImplicita(request):
	"""POST /api/retea-implicita: tasta galbena din lista placilor, cu intrebarea si codul."""
	R = _dep("retea")
	H = _dep("HdsRetea")
	a = _mc().argumente(request, ("placa", "pas", "cod"), 40)
	placa = a.get("placa", "")
	if placa not in H.adaptoare(R):
		return {"result": False, "message": _t("Placa de rețea %s nu există pe receptor.") % placa[:20]}
	if len(R.getConfiguredAdapters()) < 2:
		return {"result": False, "message": _t("Placa implicită se alege numai când sunt două plăci configurate.")}
	if H.placaImplicita(R, _dep("cale_implicita")) == placa:
		return {"result": True, "message": _t("Placa aceasta e deja cea implicită.")}
	eticheta = R.getFriendlyAdapterName(placa) or placa

	def fapta():
		ocupat = _ocupat()
		if ocupat:
			return {"result": False, "message": ocupat}
		x, gata = _lucrare("implicita", placa, _t("Finished configuring your network"))
		try:
			if H.alegePlacaImplicita(placa, R, _dep("cale_implicita")):
				H.reporneste(gata, R)
			else:
				gata()
		except Exception as eroare:
			_esuat(x, eroare)
			return {"result": False, "message": x["mesaj"]}
		return {"result": True, "message": _t("Please wait while we configure your network...")}

	return _doiPasi(request, a, "retea-implicita", placa, _t("Faci din %s placa implicită? Rețeaua repornește.") % eticheta,
		_t("Da, fă-o implicită"), [_t("Cât rețeaua repornește, legătura cu receptorul se întrerupe câteva secunde.")],
		fapta)


def reporneste(request):
	"""POST /api/retea-reporneste: Restart network, cu intrebarea si codul."""
	R = _dep("retea")
	H = _dep("HdsRetea")
	a = _mc().argumente(request, ("pas", "cod"), 40)

	def fapta():
		ocupat = _ocupat()
		if ocupat:
			return {"result": False, "message": ocupat}
		x, gata = _lucrare("reporneste", "", _t("Finished restarting your network"))
		try:
			H.reporneste(gata, R)
		except Exception as eroare:
			_esuat(x, eroare)
			return {"result": False, "message": x["mesaj"]}
		return {"result": True, "message": _t("Please wait while your network is restarting...")}

	return _doiPasi(request, a, "retea-reporneste", "", _t("Repornești plăcile de rețea?"), _t("Da, repornește rețeaua"),
		[_t("Cât rețeaua repornește, legătura cu receptorul se întrerupe câteva secunde.")], fapta)


# ------------------------------------------------------------------ proba retelei

def proba(request):
	"""POST /api/retea-proba?placa=: aceiasi pasi ca "Network test" (fara pauzele de 3 s dintre ei)."""
	R = _dep("retea")
	H = _dep("HdsRetea")
	a = _mc().argumente(request, ("placa",), 40)
	placa = a.get("placa", "")
	if placa not in H.adaptoare(R):
		return {"result": False, "message": _t("Placa de rețea %s nu există pe receptor.") % placa[:20]}
	vechea = _STARE["proba"]
	if vechea is not None and not vechea["gata"] and _acum() - vechea["pornit"] <= PROBA_MAX_S:
		return {"result": False, "message": _t("Proba rețelei încă lucrează.")}
	wifi = _areWifi(placa)
	x = {"placa": placa, "eticheta": R.getFriendlyAdapterName(placa) or placa, "wifi": wifi, "gata": False,
		"pornit": _acum(), "pasi": {"legatura": None, "dhcp": R.getAdapterAttribute(placa, "dhcp") is True, "ip": None,
		"dns": None}}
	_STARE["proba"] = x

	def dns(esecuri):
		x["pasi"]["dns"] = H.confirmat(esecuri)
		x["gata"] = True

	def ip(esecuri):
		x["pasi"]["ip"] = H.confirmat(esecuri)
		R.checkDNSLookup(dns)

	def legatura(da):
		x["pasi"]["legatura"] = bool(da)
		R.checkNetworkState(ip)

	if wifi:
		_controlStare(placa).status(lambda st: legatura(st.get("wpa_state") == "COMPLETED"))
	else:
		R.getLinkState(placa, lambda iesire: legatura(H.legaturaEthtool(iesire)))
	return {"result": True, "message": _t("Proba a pornit.")}


# ------------------------------------------------------------------ Wi-Fi

def _controlStare(placa):
	c = _OBIECTE["stare"].get(placa)
	if c is None:
		c = _OBIECTE["stare"][placa] = _dep("WlanControl")(placa)
	return c


def _wifiStare(placa):
	"""Randurile ecranului "WiFi status" (citite din nou cel mult o data la WIFI_STARE_S secunde)."""
	W = _dep("HdsWlan")
	acum = _acum()
	s = _STARE["wifi"].setdefault(placa, {"linii": [], "t": 0, "cerut": 0, "lucreaza": False, "ssid": ""})
	if (not s["lucreaza"] or acum - s["cerut"] > 15) and acum - s["t"] >= WIFI_STARE_S:
		s["lucreaza"] = True
		s["cerut"] = acum
		c = _controlStare(placa)

		def cuSemnal(status, valori):
			# semnalul si din /proc/net/wireless, pentru driverele care nu raspund la signal_poll (ca pe televizor)
			s.update(linii=W.statusLines(status, valori, W.nivelProc(placa)), t=_acum(), lucreaza=False,
				ssid=_dep("WlanTools").ssidName(W.connectedSsid(status) or b""))

		def citita(status):
			if not status:
				s.update(linii=[_t("WiFi is not active on %s.") % placa], t=_acum(), lucreaza=False, ssid="")
				return
			c.signal(lambda valori: cuSemnal(status, valori))
		c.status(citita)
	return {"linii": list(s["linii"]), "conectata": s["ssid"]}


def _placaWifi(a):
	R = _dep("retea")
	placa = a.get("placa", "")
	if placa not in _dep("HdsRetea").adaptoare(R):
		return None, _t("Placa de rețea %s nu există pe receptor.") % placa[:20]
	if not _areWifi(placa):
		return None, _t("Placa %s nu e o placă Wi-Fi.") % placa
	return placa, None


def cautaWifi(request):
	"""POST /api/retea-wifi-cauta: ca "WiFi networks" (si Galben, cauta din nou)."""
	import binascii
	W = _dep("HdsWlan")
	T = _dep("WlanTools")
	placa, motiv = _placaWifi(_mc().argumente(request, ("placa",), 40))
	if placa is None:
		return {"result": False, "message": motiv}
	vechi = _OBIECTE["cautare"]
	if vechi is not None:
		vechi.stop()
	c = _OBIECTE["cautare"] = _dep("WlanControl")(placa)
	x = {"placa": placa, "lucreaza": True, "retele": [], "mesaj": _t("Searching for networks..."), "pornit": _acum()}
	_STARE["cautare"] = x

	def listata(status):
		conectata = W.connectedSsid(status)
		retele = []
		for n in x.pop("gasite", []):
			retele.append({"ssid": binascii.hexlify(n["ssid"]).decode("ascii"), "nume": n["name"],
				"securitate": n["security"], "securitate_text": W.securityText(n["security"]), "procent": n["percent"],
				"benzi": "/".join(n["bands"]), "conectata": n["ssid"] == conectata,
				"se_poate": n["security"] in T.SUPPORTED_SECURITY,
				"parola": n["security"] not in (T.SECURITY_OPEN, T.SECURITY_OWE)})
		x["retele"] = retele
		x["lucreaza"] = False
		x["mesaj"] = (_t("Networks found: %d") % len(retele)) if retele else _t("Nu s-a găsit nicio rețea. Caută din nou.")

	def gasite(retele):
		if retele is None:
			x["lucreaza"] = False
			x["mesaj"] = _t("Căutarea n-a reușit. Caută din nou.")
			return
		x["gasite"] = retele
		c.status(listata)

	def pornit(bun):
		if not bun:
			x["lucreaza"] = False
			x["mesaj"] = _t("The WiFi adapter could not be started.")
			return
		c.scan(gasite)

	c.ensureSupplicant(pornit)
	return {"result": True, "message": x["mesaj"]}


def _cheiDinAdresa(request):
	from .descarcare_subtitrari_web import _cheiDinAdresa as c
	return c(request)


def _parola(request):
	"""Parola exact cum a fost scrisa (fara taiere de spatii), cel mult 64 de caractere; "" daca lipseste. Numai din
	corpul cererii: scrisa in adresa (?parola=) ar ramane in istoricul browserului, deci se ignora (pagina o trimite
	in corp), ca PIN-urile la controlul parental."""
	if "parola" in _cheiDinAdresa(request):
		return ""
	for cheie, valori in list((getattr(request, "args", None) or {}).items())[:24]:
		if cheie in (b"parola", "parola"):
			v = (valori or [b""])[0]
			if isinstance(v, bytes):
				v = v.decode("utf-8", "replace")
			return str(v)[:64]
	return ""


def conecteazaWifi(request):
	"""POST /api/retea-wifi-conecteaza: ca alegerea unei retele (sau "Hidden network") si parola, cu intrebarea si
	codul; conectarea e a lui HdsWlan.ConectareWlan."""
	import binascii
	import hashlib
	W = _dep("HdsWlan")
	T = _dep("WlanTools")
	a = _mc().argumente(request, CHEI_WIFI, 80)
	placa, motiv = _placaWifi(a)
	if placa is None:
		return {"result": False, "message": motiv}
	ascunsa = a.get("ascunsa") == "1"
	securitate = a.get("securitate", "")
	if ascunsa:
		nume = a.get("nume_ascuns", "")
		ssid = nume.encode("utf-8")
		if not nume:
			return {"result": False, "message": _t("Scrie numele rețelei ascunse.")}
		if len(ssid) > 32:
			return {"result": False, "message": _t("A network name may have at most 32 bytes.")}
		if securitate not in W.HIDDEN_SECURITY:
			return {"result": False, "message": W.reasonText(_t("This kind of network security is not supported"))}
	else:
		try:
			ssid = binascii.unhexlify(a.get("ssid", ""))
		except (binascii.Error, TypeError, ValueError):
			ssid = b""
		if not ssid or len(ssid) > 32:
			return {"result": False, "message": _t("Alege o rețea din listă.")}
	if securitate not in T.SUPPORTED_SECURITY:
		return {"result": False, "message": W.reasonText(_t("This kind of network security is not supported"))}
	parola = "" if securitate in (T.SECURITY_OPEN, T.SECURITY_OWE) else _parola(request)
	motiv = T.checkPassword(securitate, parola)
	if motiv:
		return {"result": False, "message": W.reasonText(motiv)}
	nume = T.ssidName(ssid)
	tinta = "%s|%s|%s|%d|%s" % (placa, binascii.hexlify(ssid).decode("ascii"), securitate, ascunsa,
		hashlib.sha256(parola.encode("utf-8")).hexdigest()[:16])

	def fapta():
		ocupat = _ocupat()
		if ocupat:
			return {"result": False, "message": ocupat}
		vechi = _OBIECTE["cautare"]
		if vechi is not None:
			vechi.stop()
			_OBIECTE["cautare"] = None
		x = {"placa": placa, "nume": nume, "text": "", "lucreaza": True, "rezultat": None, "pornit": _acum()}
		_STARE["conectare"] = x

		def arata(text):
			x["text"] = text

		def sfarsit(rezultat):
			x["lucreaza"] = False
			x["rezultat"] = bool(rezultat)
			_STARE["wifi"].pop(placa, None)

		c = W.ConectareWlan(placa, ssid, securitate, parola, ascunsa, show=arata, finished=sfarsit,
			network=_dep("retea"), control=_dep("WlanControl"), timer=_dep("ceas"))
		_OBIECTE["conectare"] = c
		try:
			c.begin()
		except Exception as eroare:
			_mc().jurnal("retea: conectarea Wi-Fi: %r" % eroare)
			x["lucreaza"] = False
			x["rezultat"] = False
			x["text"] = _t("Conectarea nu s-a putut face: %s") % eroare
			return {"result": False, "message": x["text"]}
		return {"result": True, "message": x["text"]}

	return _doiPasi(request, a, "retea-wifi", tinta, _t("Te conectezi la rețeaua Wi-Fi %s?") % nume, _t("Da, conectează"),
		[_t("Placa %s se oprește și pornește din nou cu rețeaua aleasă. Dacă browserul e legat la receptor prin Wi-Fi, "
			"legătura se poate pierde.") % placa,
		_t("Dacă nu se poate conecta, receptorul pune înapoi setările de acum.")], fapta)


def renuntaWifi(request):
	"""POST /api/retea-wifi-renunta: Rosu cat se conecteaza (setarile vechi inapoi)."""
	c = _OBIECTE["conectare"]
	if c is None or not c.running:
		return {"result": False, "message": _t("Nu se face nicio conectare acum.")}
	c.cancel()
	return {"result": True, "message": _t("Cancelled.")}


# ------------------------------------------------------------------ DNS

def stareDns():
	"""Pentru GET /api/dns."""
	R = _dep("retea")
	return {"result": True, "servere": [textIp(x) for x in _servereDns(R)], "maxim": MAX_DNS}


def seteazaDns(request):
	"""POST /api/dns-seteaza?servere=a.b.c.d,...: OK in "Nameserver settings", in doi pasi (pas=intreaba -> intrebarea
	cu lista noua si codul legat de ea; cod= -> scrierea; pas=renunta), numai din browserul conectat: serverele de nume
	hotarasc unde ajunge receptorul cand cauta un nume (actualizari, liste, ceas). O adresa rea nu schimba nimic si nu
	cere confirmare."""
	R = _dep("retea")
	H = _dep("HdsRetea")
	a = _mc().argumente(request, ("servere", "pas", "cod"), 200)
	if "servere" not in a:
		rez = stareDns()
		rez.update(result=False, message=_t("Se trimite lista servere=a.b.c.d,e.f.g.h (poate fi goală)."))
		return rez
	servere = []
	for text in [x.strip() for x in a["servere"].split(",") if x.strip()]:
		ip = ipDinText(text)
		if ip is None or ip[0] == 0 or ip[0] >= 224:
			rez = stareDns()
			rez.update(result=False, message=_t("Adresa %s nu e a unui server DNS.") % text[:20])
			return rez
		if ip not in servere:
			servere.append(ip)
	if len(servere) > MAX_DNS:
		rez = stareDns()
		rez.update(result=False, message=_t("Cel mult %d servere DNS.") % MAX_DNS)
		return rez
	lista = ", ".join(textIp(x) for x in servere)

	def fapta():
		H.scrieDns(servere, R)
		rez = stareDns()
		rez.update(result=True, message=_t("Salvat."))
		return rez

	if servere:
		detalii = [_t("Servere DNS") + ": " + lista]
	else:
		detalii = [_t("Fără niciun server DNS, receptorul nu mai găsește adresele de pe internet după nume.")]
	return _doiPasi(request, a, "dns-seteaza", lista, _t("Salvezi serverele DNS?"), _t("Da, salvează"), detalii, fapta)


# ------------------------------------------------------------------ rutele si paginile

def rute(baza, resource):
	"""({nume: resursa de sub /api}, {nume: resursa paginii}). `baza` e HdsJsonResource din plugin.py."""

	def _eroare(self, request, eroare):
		_mc().jurnal("retea: %r" % eroare)
		return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	def _citire(functie):
		class Citire(baza):
			def render_GET(self, request):
				try:
					return self._raspunde(request, functie(request))
				except Exception as eroare:
					return _eroare(self, request, eroare)
		return Citire()

	def _scriere(functie):
		class Scriere(baza):
			schimbaCeva = True

			def render_POST(self, request):
				try:
					return self._raspunde(request, functie(request))
				except Exception as eroare:
					return _eroare(self, request, eroare)

			def render_GET(self, request):
				return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST
		return Scriere()

	def _pagina(text):
		class Pagina(resource.Resource):
			isLeaf = True

			def render_GET(self, request):
				return _mc().pagina(request, text)
		return Pagina()

	api = {
		b"retea": _citire(lambda r: stare(_gazda(r)[0])),
		b"retea-placa": _scriere(aplicaPlaca),
		b"retea-implicita": _scriere(placaImplicita),
		b"retea-reporneste": _scriere(reporneste),
		b"retea-proba": _scriere(proba),
		b"retea-wifi-cauta": _scriere(cautaWifi),
		b"retea-wifi-conecteaza": _scriere(conecteazaWifi),
		b"retea-wifi-renunta": _scriere(renuntaWifi),
		b"dns": _citire(lambda r: stareDns()),
		b"dns-seteaza": _scriere(seteazaDns),
	}
	return api, {b"retea": _pagina(pagina_retea), b"dns": _pagina(pagina_dns)}


def pagina_retea(stil, config_pagina):
	mc = _mc()
	return mc.sablon(_traducePagina(PAGINA_RETEA), stil, config_pagina,
		{"__DRUM_MENIU__": mc.drumHtml("network_setup")})


def pagina_dns(stil, config_pagina):
	mc = _mc()
	return mc.sablon(_traducePagina(PAGINA_DNS), stil, config_pagina, {"__DRUM_MENIU__": mc.drumHtml("dns_setup")})


PAGINA_RETEA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Rețea</title>
<style>__STIL_COMUN__
__STIL_PAGINI__
  .placa{display:grid;grid-template-columns:1fr auto;gap:10px;align-items:center;padding:10px 0;border-bottom:1px solid var(--bordura);}
  .placa:last-child{border-bottom:0;}
  .placa .nume{font-weight:600;}
  .placa .butoane{margin:0;justify-content:flex-end;}
  .placa.aleasa .nume{color:var(--accent);}
  .linii{white-space:pre-line;line-height:1.5;margin:0;}
  .retele th,.retele td{overflow-wrap:normal;word-break:normal;}
  .retele td:first-child{overflow-wrap:anywhere;}
  .retele td:last-child{text-align:right;white-space:nowrap;}
  #formWifi,#conectare{margin-top:14px;}
  .internet-stare{display:flex;align-items:center;gap:12px;padding:4px 0 10px;line-height:1.45;}
  .internet-stare svg{display:block;width:80px;height:60px;flex:none;}
  @media (max-width:560px){
    .placa{grid-template-columns:1fr;} .placa .butoane{justify-content:flex-start;}
    .retele thead{display:none;}
    .retele tr{display:grid;grid-template-columns:1fr auto;gap:2px 10px;padding:8px 0;border-bottom:1px solid var(--bordura);}
    main .card table.retele tr td{border:0;padding:2px 0;}
    .retele td:nth-child(1),.retele td:nth-child(2),.retele td:nth-child(3){grid-column:1;}
    .retele td:nth-child(2),.retele td:nth-child(3){color:var(--text-slab);font-size:.85rem;}
    .retele td:nth-child(4){grid-column:2;grid-row:1 / span 3;align-self:center;}
  }
</style>
</head>
<body>
<main>
<h1>Rețea</h1>
<p class="mesaj" id="incarcare">Se citește rețeaua...</p>
<div id="continut" class="ascuns">
  <section class="card" id="cardInternet">
    <h2>Internetul</h2>
    <div class="internet-stare"><span id="internetPictograma"><svg width="80" height="60" viewBox="0 0 40 30" aria-hidden="true" focusable="false"><use href="#hr-cablu_verific"/></svg></span><span id="internetText">Se verifică internetul...</span></div>
    <div class="rand">
      <label for="internetInterval">Cât de des se verifică internetul</label>
      <select id="internetInterval"><option value="30">30 de secunde</option><option value="60">un minut</option><option value="120">2 minute</option><option value="300">5 minute</option></select>
      <p class="ajutor nota">Receptorul verifică singur, în fundal, dacă are internet: trimite o întrebare DNS mică spre serverele publice 1.1.1.1, 9.9.9.9 și 8.8.8.8, fără date despre tine. La orice schimbare a rețelei (cablul, Wi-Fi, adresa) verifică pe loc. Aceeași setare pe televizor: Meniu &gt; Setări &gt; Rețea și Internet &gt; Verificarea internetului.</p>
    </div>
    <div class="rand">
      <label for="internetPictogramaBare">Arată pictograma internetului în bare</label>
      <select id="internetPictogramaBare"></select>
      <p class="ajutor nota">Da: pictograma se vede în barele de pe televizor, în capul ferestrelor din tema Pro și în antetul acestor pagini. Nu: se ascunde, iar ce era lângă ea revine la locul ei; verificarea internetului merge mai departe. Aceeași setare pe televizor, lângă cea de mai sus.</p>
    </div>
  </section>

  <section class="card" id="cardComutare">
    <h2>Trecerea singură pe altă rețea</h2>
    <p class="linii" id="comutareStare">Se citește...</p>
    <div class="rand">
      <label for="comutarePornita">Trecerea singură pe altă rețea</label>
      <select id="comutarePornita"></select>
      <p class="ajutor nota">Da: când internetul nu merge de câteva verificări la rând, receptorul trece singur pe cablu sau pe o rețea Wi-Fi salvată care are internet, și se întoarce când rețeaua lui își revine. Fără altă rețea nu face nimic. Nu trece în timpul unei actualizări sau al unei înregistrări din rețea.</p>
    </div>
    <div class="rand">
      <label for="comutareOrdine">Ordinea rețelelor</label>
      <select id="comutareOrdine"></select>
    </div>
    <p class="nota">După o trecere, receptorul poate avea altă adresă. Pe televizor apare adresa nouă; pagina se deschide mereu și cu <a href="http://hdsatelit.local/">http://hdsatelit.local/</a>. Aceeași setare pe televizor: Meniu &gt; Setări &gt; Rețea și Internet &gt; Trecerea singură pe altă rețea.</p>
    <div class="butoane"><button type="button" id="spreCanale">Cât de aglomerat e Wi-Fi-ul</button><button type="button" id="spreAparate">Ce aparate sunt în rețea</button></div>
  </section>

  <section class="card" id="cardIpv6">
    <h2>IPv6</h2>
    <p class="linii" id="ipv6Stare">Se citește...</p>
    <div class="rand">
      <label for="ipv6Pornit">IPv6</label>
      <select id="ipv6Pornit"></select>
      <p class="ajutor nota">Nu (din fabrică): plăcile de rețea nu au adrese IPv6, iar clientul IPv6 nu pornește; rețeaua merge pe IPv4, ca până acum. Da: receptorul primește și adrese IPv6, dacă rețeaua ta le dă. Se aplică pe loc. Aceeași setare pe televizor: Meniu &gt; Setări &gt; Rețea și Internet &gt; IPv6.</p>
    </div>
  </section>

  <section class="card">
    <h2>Plăcile de rețea</h2>
    <div id="placi"></div>
    <p class="nota" id="notaImplicita"></p>
  </section>

  <section class="card" id="cardSetari">
    <h2 id="titluSetari">Setările plăcii</h2>
    <div class="rand">
      <label for="sus">Folosește placa</label>
      <select id="sus"><option value="1">Da</option><option value="0">Nu</option></select>
    </div>
    <div class="rand" id="randDhcp">
      <label for="dhcp">Folosește DHCP</label>
      <select id="dhcp"><option value="1">Da</option><option value="0">Nu</option></select>
      <p class="ajutor nota">Cu DHCP, adresa, masca, poarta și serverele DNS le dă routerul.</p>
    </div>
    <div class="rand" id="randIp">
      <label for="ip">Adresa IP</label>
      <input id="ip" type="text" inputmode="decimal" autocomplete="off" spellcheck="false" placeholder="192.168.1.10">
    </div>
    <div class="rand" id="randMasca">
      <label for="masca">Masca de rețea</label>
      <input id="masca" type="text" inputmode="decimal" autocomplete="off" spellcheck="false" placeholder="255.255.255.0">
    </div>
    <div class="rand" id="randArePoarta">
      <label for="arePoarta">Folosește o poartă</label>
      <select id="arePoarta"><option value="1">Da</option><option value="0">Nu</option></select>
    </div>
    <div class="rand" id="randPoarta">
      <label for="poarta">Poarta</label>
      <input id="poarta" type="text" inputmode="decimal" autocomplete="off" spellcheck="false" placeholder="192.168.1.1">
      <p class="ajutor nota">De obicei, adresa routerului.</p>
    </div>
    <div class="rand ascuns" id="randAlta">
      <label for="alta">Oprește cealaltă placă configurată (<span id="altaNume"></span>)</label>
      <select id="alta"><option value="1">Da</option><option value="0">Nu</option></select>
      <p class="ajutor nota">O altă placă e deja configurată. Pe televizor, aceeași întrebare apare la OK.</p>
    </div>
    <div class="butoane">
      <button type="button" class="principal" id="aplica">Aplică setările</button>
      <button type="button" id="inapoi">Pune înapoi valorile de acum</button>
      <button type="button" id="spreDns">Serverele DNS</button>
    </div>
    <p class="nota" id="adresaNoua"></p>
  </section>

  <section class="card">
    <h2>Setările de acum</h2>
    <div id="acum"></div>
  </section>

  <section class="card">
    <h2>Proba rețelei</h2>
    <div id="proba"></div>
    <div class="butoane"><button type="button" id="pornesteProba">Pornește proba</button></div>
  </section>

  <section class="card ascuns" id="cardWifi">
    <h2>Wi-Fi</h2>
    <p class="linii" id="wifiStare"></p>
    <div class="butoane">
      <button type="button" id="cauta">Caută rețele</button>
      <button type="button" id="ascunsa">Rețea ascunsă</button>
    </div>
    <p class="nota" id="cautareMesaj"></p>
    <table class="retele ascuns" id="retele"><thead><tr><th>Rețeaua</th><th>Securitate</th><th>Semnal</th><th></th></tr></thead><tbody></tbody></table>
    <div class="ascuns" id="formWifi">
      <h2 id="formWifiTitlu"></h2>
      <div class="rand ascuns" id="randNumeAscuns">
        <label for="numeAscuns">Numele rețelei ascunse</label>
        <input id="numeAscuns" type="text" autocomplete="off" spellcheck="false" maxlength="32">
      </div>
      <div class="rand ascuns" id="randSecuritate">
        <label for="securitate">Securitatea rețelei ascunse</label>
        <select id="securitate"></select>
      </div>
      <div class="rand" id="randParola">
        <label for="parola">Parola rețelei</label>
        <input id="parola" type="password" autocomplete="off" spellcheck="false" maxlength="64">
      </div>
      <div class="butoane">
        <button type="button" class="principal" id="conecteaza">Conectează</button>
        <button type="button" id="inchideForm">Înapoi</button>
      </div>
    </div>
    <div class="ascuns" id="conectare">
      <p class="linii" id="conectareText"></p>
      <div class="butoane"><button type="button" class="rosu" id="opresteConectarea">Oprește conectarea</button></div>
    </div>
  </section>

  <section class="card">
    <h2>Repornirea rețelei</h2>
    <p class="nota">Oprește și pornește din nou toate plăcile de rețea, cu setările salvate.</p>
    <div class="butoane"><button type="button" class="rosu" id="reporneste">Repornește rețeaua</button></div>
  </section>

  <p class="mesaj" id="mesaj"></p>
  <div id="confirmare" class="card ascuns"></div>
  <p class="nota">Aceleași setări sunt pe televizor, în __DRUM_MENIU__. Serverele DNS au pagina lor: <a href="/dns" id="legaturaDns">Servere DNS</a>.</p>
</div>
</main>
<script>
__SCRIPT_COMUN__
var D = null, ALEASA = null, FORMULAR = null, RETEA = null, ASCUNSA = false;
var dinAdresa = new URLSearchParams(location.search).get("placa");
function scrie(el, t){ el.textContent = (t === null || t === undefined) ? "" : String(t); }
function placa(nume){ return ((D && D.placi) || []).filter(function(p){ return p.nume === nume; })[0] || null; }
function numeAfisat(p){ return p.eticheta + " (" + p.nume + ")"; }
function daNu(v, da, nu){ return v === null || v === undefined ? "nu se știe" : (v ? da : nu); }
function linie(cutie, eticheta, valoare){
  var r = document.createElement("div"); r.className = "status-linie";
  var a = document.createElement("span"); scrie(a, eticheta);
  var b = document.createElement("span"); scrie(b, valoare);
  r.appendChild(a); r.appendChild(b); cutie.appendChild(r);
}
function buton(text, clasa, fn){
  var b = document.createElement("button"); b.type = "button"; b.textContent = text;
  if(clasa){ b.className = clasa; }
  b.addEventListener("click", fn); return b;
}
function arataPlaci(){
  var c = $("placi"); c.textContent = "";
  D.placi.forEach(function(p){
    var r = document.createElement("div"); r.className = "placa" + (p.nume === ALEASA ? " aleasa" : "");
    var st = document.createElement("div");
    var n = document.createElement("div"); n.className = "nume"; scrie(n, numeAfisat(p)); st.appendChild(n);
    var parti = [p.sus ? "pornită" : "oprită"];
    parti.push("legătură: " + daNu(p.legatura, "da", "nu"));
    parti.push(p.ip ? p.ip : "fără adresă");
    if(p.implicita){ parti.push("implicită"); }
    if(p.browser){ parti.push("browserul tău e legat prin ea"); }
    var d = document.createElement("div"); d.className = "nota"; scrie(d, (p.descriere ? p.descriere + " · " : "") + parti.join(" · "));
    st.appendChild(d); r.appendChild(st);
    var bs = document.createElement("div"); bs.className = "butoane";
    bs.appendChild(buton(p.nume === ALEASA ? "Aleasă" : "Setări", p.nume === ALEASA ? "principal" : "", function(){ alege(p.nume); }));
    if(D.implicita_se_poate && !p.implicita){
      bs.appendChild(buton("Fă-o implicită", "", function(){
        var q = new URLSearchParams(); q.set("placa", p.nume);
        cuConfirmare("/api/retea-implicita", q, function(){ citeste(); });
      }));
    }
    r.appendChild(bs); c.appendChild(r);
  });
  scrie($("notaImplicita"), D.implicita_se_poate ? "Placa implicită e cea prin care receptorul iese spre internet când sunt pornite două plăci." : "");
}
function umpleFormular(p){
  FORMULAR = p.nume;
  scrie($("titluSetari"), "Setările plăcii " + numeAfisat(p));
  $("sus").value = p.sus ? "1" : "0";
  $("dhcp").value = p.dhcp ? "1" : "0";
  $("ip").value = p.ip_formular;
  $("masca").value = p.masca_formular;
  $("arePoarta").value = p.are_poarta ? "1" : "0";
  $("poarta").value = p.poarta_formular;
  $("alta").value = "1";
  scrie($("adresaNoua"), "");
  vizibile();
}
function vizibile(){
  var p = placa(ALEASA);
  var sus = $("sus").value === "1", dhcp = $("dhcp").value === "1", poarta = $("arePoarta").value === "1";
  $("randDhcp").classList.toggle("ascuns", !sus);
  ["randIp", "randMasca", "randArePoarta"].forEach(function(id){ $(id).classList.toggle("ascuns", !sus || dhcp); });
  $("randPoarta").classList.toggle("ascuns", !sus || dhcp || !poarta);
  $("randAlta").classList.toggle("ascuns", !(p && p.opreste_alta));
  if(p){ scrie($("altaNume"), p.alte.join(", ")); }
}
function arataAcum(){
  var c = $("acum"); c.textContent = "";
  var p = placa(ALEASA); if(!p){ return; }
  linie(c, "Placa", numeAfisat(p));
  linie(c, "Adresa IP", p.ip || "nu are");
  linie(c, "Masca de rețea", p.masca || "nu are");
  linie(c, "Poarta", p.poarta || "nu are");
  linie(c, "Server DNS principal", D.dns[0] || "nu are");
  linie(c, "Server DNS secundar", D.dns[1] || "nu are");
  linie(c, "Adresa fizică (MAC)", p.mac || "nu se știe");
  linie(c, "Legătura", daNu(p.legatura, "da", "nu"));
}
var AJUTOR_PROBA = {
  placa: "Proba găsește placa de rețea aleasă.",
  legatura: "Proba verifică dacă placa e legată la rețea. La deconectată: verifică dacă e pus cablul de rețea și dacă nu e rupt (la Wi-Fi: dacă placa e conectată la o rețea).",
  dhcp: "Pornit: adresa o dă routerul (verifică dacă routerul are DHCP pornit). Oprit: adresa e scrisă de mână (verifică setările de mai sus).",
  ip: "Proba verifică dacă receptorul ajunge la internet cu adresa lui. La neconfirmată: verifică DHCP, cablul și setările plăcii.",
  dns: "Proba verifică serverele de nume. La neconfirmat: verifică DHCP, cablul, setările plăcii și, dacă le-ai scris de mână, serverele DNS."
};
function arataProba(){
  var c = $("proba"); c.textContent = "";
  var x = D.proba;
  if(!x || x.placa !== ALEASA){
    var n = document.createElement("p"); n.className = "nota"; scrie(n, "Proba verifică pe rând placa, legătura, DHCP, adresa IP și serverele de nume."); c.appendChild(n);
    $("pornesteProba").disabled = false; return;
  }
  function v(cheie, da, nu){
    var val = x.pasi[cheie];
    if(val === null){ return x.gata ? "fără răspuns" : "se verifică..."; }
    return val ? da : nu;
  }
  [["placa", "Placa", x.eticheta],
   ["legatura", x.wifi ? "Rețeaua fără fir" : "Rețeaua locală", v("legatura", "conectată", "deconectată")],
   ["dhcp", "DHCP", x.pasi.dhcp ? "pornit" : "oprit"],
   ["ip", "Adresa IP", v("ip", "confirmată", "neconfirmată")],
   ["dns", "Serverele de nume", v("dns", "confirmate", "neconfirmate")]].forEach(function(r){
    var b = document.createElement("div"); b.className = "rand";
    var l = document.createElement("label"); scrie(l, r[1]); b.appendChild(l);
    var s = document.createElement("span"); scrie(s, r[2]); b.appendChild(s);
    var a = document.createElement("p"); a.className = "ajutor nota"; scrie(a, AJUTOR_PROBA[r[0]]); b.appendChild(a);
    c.appendChild(b);
  });
  $("pornesteProba").disabled = !x.gata;
  scrie($("pornesteProba"), x.gata ? "Pornește proba din nou" : "Proba lucrează...");
}
function arataWifi(){
  var p = placa(ALEASA);
  $("cardWifi").classList.toggle("ascuns", !(p && p.wifi));
  if(!p || !p.wifi){ return; }
  var w = D.wifi[p.nume];
  scrie($("wifiStare"), p.sus ? (w && w.linii.length ? w.linii.join("\\n") : "Se citește starea Wi-Fi...") : "Placa e oprită. Starea Wi-Fi se vede când placa e pornită.");
  var k = D.cautare;
  var tb = $("retele").querySelector("tbody"); tb.textContent = "";
  if(k && k.placa === p.nume){
    scrie($("cautareMesaj"), k.mesaj);
    $("cauta").disabled = k.lucreaza;
    (k.retele || []).forEach(function(n){
      var tr = document.createElement("tr");
      var a = document.createElement("td"); scrie(a, (n.conectata ? "Conectat: " : "") + n.nume); tr.appendChild(a);
      var b = document.createElement("td"); scrie(b, n.securitate_text); tr.appendChild(b);
      var s = document.createElement("td"); scrie(s, n.procent + "%" + (n.benzi ? " · " + n.benzi + " GHz" : "")); tr.appendChild(s);
      var d = document.createElement("td");
      var bt = buton("Conectează", "", function(){ deschideForm(n, false); }); bt.disabled = !n.se_poate;
      d.appendChild(bt); tr.appendChild(d); tb.appendChild(tr);
    });
    $("retele").classList.toggle("ascuns", !(k.retele && k.retele.length));
  } else {
    scrie($("cautareMesaj"), ""); $("cauta").disabled = false; $("retele").classList.add("ascuns");
  }
  var cn = D.conectare;
  var activ = !!(cn && cn.placa === p.nume && (cn.lucreaza || cn.rezultat !== null));
  $("conectare").classList.toggle("ascuns", !activ);
  if(activ){
    scrie($("conectareText"), cn.text);
    $("opresteConectarea").classList.toggle("ascuns", !cn.lucreaza);
  }
}
function deschideForm(n, ascunsa){
  RETEA = n; ASCUNSA = ascunsa;
  scrie($("formWifiTitlu"), ascunsa ? "Conectarea la o rețea ascunsă" : "Conectarea la " + n.nume);
  $("randNumeAscuns").classList.toggle("ascuns", !ascunsa);
  $("randSecuritate").classList.toggle("ascuns", !ascunsa);
  $("parola").value = "";
  parolaVizibila();
  $("formWifi").classList.remove("ascuns");
  (ascunsa ? $("numeAscuns") : $("parola")).focus();
}
function parolaVizibila(){
  var cere = ASCUNSA ? ["open", "owe"].indexOf($("securitate").value) === -1 : !!(RETEA && RETEA.parola);
  $("randParola").classList.toggle("ascuns", !cere);
}
function arata(){
  if(!ALEASA || !placa(ALEASA)){
    ALEASA = (dinAdresa && placa(dinAdresa)) ? dinAdresa : (D.placi[0] ? D.placi[0].nume : null);
  }
  arataPlaci();
  $("cardSetari").classList.toggle("ascuns", !ALEASA);
  var p = placa(ALEASA);
  if(p && FORMULAR !== p.nume){ umpleFormular(p); } else { vizibile(); }
  arataAcum(); arataProba(); arataWifi(); arataIpv6();
  if(D.lucrare && !D.lucrare.gata){ mesaj("Se lucrează la rețea (" + D.lucrare.secunde + " s)..."); }
}
var ULTIM_MESAJ = null;
function citeste(){
  return cerere("/api/retea").then(function(d){
    if(!d.result){ scrie($("incarcare"), d.message || "Receptorul nu a putut citi rețeaua."); return; }
    $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
    var gata = d.lucrare && d.lucrare.gata ? String(d.lucrare.nr) : "";
    var primul = D === null;
    D = d; arata();
    if(primul){ ULTIM_MESAJ = gata; }
    else if(gata && ULTIM_MESAJ !== gata && ULTIM_MESAJ !== null){
      ULTIM_MESAJ = gata; mesaj(d.lucrare.mesaj, d.lucrare.eroare);
      if(!d.lucrare.eroare){ FORMULAR = null; arata(); }
    }
  }).catch(function(){
    if(D && D.lucrare && !D.lucrare.gata){ mesaj("Legătura s-a întrerupt cât rețeaua pornește din nou. Pagina încearcă singură; dacă adresa s-a schimbat, deschide pagina la adresa nouă.", true); }
    else if(!D){ scrie($("incarcare"), "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."); }
    else { nimicNuRaspunde(); }
  });
}
function alege(nume){ ALEASA = nume; FORMULAR = null; arata(); }
$("sus").addEventListener("change", vizibile);
$("dhcp").addEventListener("change", vizibile);
$("arePoarta").addEventListener("change", vizibile);
$("inapoi").addEventListener("click", function(){ var p = placa(ALEASA); if(p){ umpleFormular(p); mesaj(""); } });
$("spreDns").addEventListener("click", function(){ location.href = adresa("/dns"); });
$("aplica").addEventListener("click", function(){
  var p = placa(ALEASA); if(!p){ return; }
  var q = new URLSearchParams(); q.set("placa", p.nume); q.set("sus", $("sus").value);
  q.set("dhcp", $("sus").value === "1" ? $("dhcp").value : (p.dhcp ? "1" : "0"));
  if($("sus").value === "1" && $("dhcp").value === "0"){
    q.set("ip", $("ip").value.trim()); q.set("masca", $("masca").value.trim()); q.set("are_poarta", $("arePoarta").value);
    if($("arePoarta").value === "1"){ q.set("poarta", $("poarta").value.trim()); }
  }
  if(p.opreste_alta){ q.set("alta", $("alta").value); }
  cuConfirmare("/api/retea-placa", q, function(d){
    if(d.result && d.url_nou && d.adresa_noua !== location.hostname){ scrie($("adresaNoua"), "Dacă browserul era legat prin această placă, pagina e acum la " + d.url_nou + "."); }
    citeste();
  });
});
$("pornesteProba").addEventListener("click", function(){
  var q = new URLSearchParams(); q.set("placa", ALEASA);
  cerere("/api/retea-proba", "POST", q).then(function(d){ mesaj(d.message, !d.result); citeste(); }).catch(nimicNuRaspunde);
});
$("reporneste").addEventListener("click", function(){ cuConfirmare("/api/retea-reporneste", new URLSearchParams(), function(){ citeste(); }); });
$("cauta").addEventListener("click", function(){
  var q = new URLSearchParams(); q.set("placa", ALEASA); $("cauta").disabled = true;
  cerere("/api/retea-wifi-cauta", "POST", q).then(function(d){ if(!d.result){ mesaj(d.message, true); } citeste(); }).catch(nimicNuRaspunde);
});
$("ascunsa").addEventListener("click", function(){
  var s = $("securitate"); s.textContent = "";
  (D.securitati_ascunse || []).forEach(function(x){ var o = document.createElement("option"); o.value = x[0]; o.textContent = x[1]; s.appendChild(o); });
  $("numeAscuns").value = "";
  deschideForm(null, true);
});
$("securitate").addEventListener("change", parolaVizibila);
$("inchideForm").addEventListener("click", function(){ $("formWifi").classList.add("ascuns"); $("parola").value = ""; });
$("conecteaza").addEventListener("click", function(){
  var q = new URLSearchParams(); q.set("placa", ALEASA);
  if(ASCUNSA){ q.set("ascunsa", "1"); q.set("nume_ascuns", $("numeAscuns").value); q.set("securitate", $("securitate").value); }
  else { q.set("ascunsa", "0"); q.set("ssid", RETEA.ssid); q.set("securitate", RETEA.securitate); }
  if(!$("randParola").classList.contains("ascuns")){ q.set("parola", $("parola").value); }
  cuConfirmare("/api/retea-wifi-conecteaza", q, function(d){
    if(d.result){ $("formWifi").classList.add("ascuns"); $("parola").value = ""; }
    citeste();
  });
});
$("opresteConectarea").addEventListener("click", function(){
  cerere("/api/retea-wifi-renunta", "POST", new URLSearchParams()).then(function(d){ mesaj(d.message, !d.result); citeste(); }).catch(nimicNuRaspunde);
});
$("legaturaDns").href = adresa("/dns");
// cardul Internetul: aceeasi stare ca pictograma din antet si din bara de pe televizor (/api/stare-retea; desenul e
// simbolul #hr-<cheie> pus de cadru in antet, aici la 80x60), setarea "Cat de des se verifica internetul" prin pagina
// generica a setarilor (setup.xml hds_internet, randul 0)
function citesteInternet(){
  cerere("/api/stare-retea").then(function(d){
    if(!d || !d.result){ return; }
    var u = document.querySelector("#internetPictograma use");
    if(u && d.pictograma && document.getElementById("hr-" + d.pictograma)){ u.setAttribute("href", "#hr-" + d.pictograma); }
    scrie($("internetText"), d.titlu || "");
  }).catch(function(){});
}
function citesteIntervalul(){
  cerere("/api/setari?id=hds_internet").then(function(d){
    if(d && d.result && d.randuri && d.randuri[0]){ $("internetInterval").value = d.randuri[0].valoare; }
    if(d && d.result && d.randuri && d.randuri[1]){ umpleAlegeri($("internetPictogramaBare"), d.randuri[1]); }
  }).catch(function(){});
}
// randul 1: pictograma in bare si in antet; dupa schimbare antetul se citeste pe loc (cadru_web.py, HDS_ANTET.retea)
$("internetPictogramaBare").addEventListener("change", function(){
  var q = new URLSearchParams(); q.set("id", "hds_internet"); q.set("r1", $("internetPictogramaBare").value);
  cerere("/api/setari-seteaza", "POST", q).then(function(d){
    mesaj(d.message, !d.result); citesteIntervalul();
    if(window.HDS_ANTET && window.HDS_ANTET.retea){ window.HDS_ANTET.retea(); }
  }).catch(nimicNuRaspunde);
});
$("internetInterval").addEventListener("change", function(){
  var q = new URLSearchParams(); q.set("id", "hds_internet"); q.set("r0", $("internetInterval").value);
  cerere("/api/setari-seteaza", "POST", q).then(function(d){ mesaj(d.message, !d.result); citesteIntervalul(); }).catch(nimicNuRaspunde);
});
citesteInternet(); citesteIntervalul();
setInterval(function(){ if(!document.hidden){ citesteInternet(); } }, 5000);
// cardul Trecerea singura pe alta retea (Components/HdsComutareRetea.py): starea din /api/comutare-retea, cele doua
// setari prin pagina generica a setarilor (setup.xml hds_retea_comutare: randul 0 pornita, randul 1 ordinea)
function umpleAlegeri(s, r){
  if(!r){ return; }
  if(!s.options.length){ (r.alegeri || []).forEach(function(a){ var o = document.createElement("option"); o.value = a[0]; o.textContent = a[1]; s.appendChild(o); }); }
  s.value = r.valoare;
}
function citesteComutarea(){
  cerere("/api/setari?id=hds_retea_comutare").then(function(d){
    if(d && d.result && d.randuri){ umpleAlegeri($("comutarePornita"), d.randuri[0]); umpleAlegeri($("comutareOrdine"), d.randuri[1]); }
  }).catch(function(){});
  cerere("/api/comutare-retea").then(function(d){
    if(!d || !d.result){ return; }
    var linii = [];
    if(!d.pornita){ linii.push("Oprită: receptorul rămâne pe rețeaua lui."); }
    else if(d.fara_alternative){ linii.push("Pornită, dar receptorul are o singură rețea: nu are pe ce trece."); }
    else if(d.mod === "comutat"){ linii.push("Acum pe " + d.activa + " (internetul nu mergea prin " + d.preferata + "). Se întoarce singur când acolo merge din nou."); }
    else { linii.push("Pornită. Acum receptorul e pe rețeaua lui obișnuită."); }
    if(d.cai && d.cai.length){ linii.push("Ordinea: " + d.cai.map(function(c, i){ return (i + 1) + ". " + c.nume; }).join(", ")); }
    if(d.adresa){ linii.push("Adresa receptorului: " + d.adresa + " (sau hdsatelit.local)"); }
    if(d.amanat){ linii.push("Amânat: " + d.amanat + "."); }
    if(d.ultimul){ linii.push("Ultima dată: " + d.ultimul); }
    scrie($("comutareStare"), linii.join("\\n"));
  }).catch(function(){});
}
function seteazaComutarea(rand, valoare){
  var q = new URLSearchParams(); q.set("id", "hds_retea_comutare"); q.set("r" + rand, valoare);
  cerere("/api/setari-seteaza", "POST", q).then(function(d){ mesaj(d.message, !d.result); citesteComutarea(); }).catch(nimicNuRaspunde);
}
$("comutarePornita").addEventListener("change", function(){ seteazaComutarea(0, $("comutarePornita").value); });
$("comutareOrdine").addEventListener("change", function(){ seteazaComutarea(1, $("comutareOrdine").value); });
$("spreCanale").addEventListener("click", function(){ location.href = adresa("/wifi-canale"); });
$("spreAparate").addEventListener("click", function(){ location.href = adresa("/aparate-retea"); });
citesteComutarea();
// cardul IPv6 (Components/HdsIpv6.py): starea de acum vine cu /api/retea (ipv6.linii, aceleasi randuri ca pe
// televizor), setarea prin pagina generica a setarilor (setup.xml hds_ipv6, randul 0); receptorul o aplica pe loc
function arataIpv6(){
  if(D && D.ipv6 && D.ipv6.linii){ scrie($("ipv6Stare"), D.ipv6.linii.join("\\n")); }
}
function citesteIpv6(){
  cerere("/api/setari?id=hds_ipv6").then(function(d){
    if(d && d.result && d.randuri){ umpleAlegeri($("ipv6Pornit"), d.randuri[0]); }
  }).catch(function(){});
}
$("ipv6Pornit").addEventListener("change", function(){
  var q = new URLSearchParams(); q.set("id", "hds_ipv6"); q.set("r0", $("ipv6Pornit").value);
  cerere("/api/setari-seteaza", "POST", q).then(function(d){ mesaj(d.message, !d.result); citesteIpv6(); citeste(); }).catch(nimicNuRaspunde);
});
citesteIpv6();
if(new URLSearchParams(location.search).get("f") === "ipv6" && $("cardIpv6").scrollIntoView){ $("cardIpv6").scrollIntoView(); }
setInterval(function(){ if(!document.hidden){ citesteComutarea(); } }, 10000);
citeste();
setInterval(function(){ if(!document.hidden){ citeste(); } }, 3000);
</script>
</body>
</html>
"""


PAGINA_DNS = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Servere DNS</title>
<style>__STIL_COMUN__
__STIL_PAGINI__
  .server{display:grid;grid-template-columns:1fr minmax(160px,260px) auto;gap:10px;align-items:center;padding:8px 0;border-bottom:1px solid var(--bordura);}
  .server:last-child{border-bottom:0;}
  @media (max-width:560px){ .server{grid-template-columns:1fr auto;} .server label{grid-column:1 / -1;} }
</style>
</head>
<body>
<main>
<h1>Servere DNS</h1>
<p class="mesaj" id="incarcare">Se citesc serverele...</p>
<div id="continut" class="ascuns">
  <section class="card">
    <h2>Serverele de nume</h2>
    <div id="servere"></div>
    <p class="nota" id="gol">Nu e niciun server DNS. Fără el, receptorul nu găsește adresele de pe internet după nume.</p>
    <div class="butoane">
      <button type="button" id="adauga">Adaugă un server</button>
    </div>
  </section>
  <div class="butoane">
    <button type="button" class="principal" id="salveaza">Salvează și aplică</button>
    <button type="button" id="renunta">Renunță</button>
    <button type="button" id="spreRetea">Setările plăcilor</button>
  </div>
  <p class="mesaj" id="mesaj"></p>
  <div id="confirmare" class="card ascuns"></div>
  <p class="nota">Serverul DNS transformă numele (de exemplu hdsatelit.com) în adrese. Cu DHCP, serverele le dă de obicei routerul. Exemple: 1.1.1.1, 8.8.8.8, 9.9.9.9. Aceleași setări sunt pe televizor, în __DRUM_MENIU__.</p>
</div>
</main>
<script>
__SCRIPT_COMUN__
var MAXIM = 10;
function rand(valoare){
  var c = $("servere"), n = c.children.length + 1;
  var r = document.createElement("div"); r.className = "server";
  var l = document.createElement("label"); l.textContent = "Server DNS " + n; l.htmlFor = "dns" + n;
  var i = document.createElement("input"); i.type = "text"; i.id = "dns" + n; i.inputMode = "decimal"; i.autocomplete = "off"; i.spellcheck = false; i.placeholder = "1.1.1.1"; i.value = valoare || "";
  var b = document.createElement("button"); b.type = "button"; b.textContent = "Scoate";
  b.addEventListener("click", function(){ r.remove(); numeroteaza(); });
  r.appendChild(l); r.appendChild(i); r.appendChild(b); c.appendChild(r);
  numeroteaza();
  return i;
}
function numeroteaza(){
  var randuri = $("servere").children;
  for(var k = 0; k < randuri.length; k++){
    var l = randuri[k].querySelector("label"), i = randuri[k].querySelector("input");
    l.textContent = "Server DNS " + (k + 1); i.id = "dns" + (k + 1); l.htmlFor = i.id;
  }
  $("gol").classList.toggle("ascuns", randuri.length > 0);
  $("adauga").disabled = randuri.length >= MAXIM;
}
function arata(d){
  MAXIM = d.maxim || 10;
  $("servere").textContent = "";
  (d.servere || []).forEach(function(s){ rand(s); });
  numeroteaza();
}
function citeste(){
  return cerere("/api/dns").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi serverele."; return; }
    $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
    arata(d);
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; });
}
$("adauga").addEventListener("click", function(){ rand("").focus(); });
$("renunta").addEventListener("click", function(){ mesaj("Nu s-a schimbat nimic."); citeste(); });
$("spreRetea").addEventListener("click", function(){ location.href = adresa("/retea"); });
$("salveaza").addEventListener("click", function(){
  var lista = [];
  Array.prototype.forEach.call($("servere").querySelectorAll("input"), function(i){ var v = i.value.trim(); if(v){ lista.push(v); } });
  var q = new URLSearchParams(); q.set("servere", lista.join(","));
  cuConfirmare("/api/dns-seteaza", q, function(d){ if(d.result && d.servere){ arata(d); } });
});
citeste();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- traducerea paginilor
# Textele sabloanelor de mai sus, traduse la cerere in limba receptorului (traducere_pagini.py). Un text
# nou sau schimbat in sablon se scrie si aici (proba textelor paginilor web il cere).
def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textele se traduc la folosire."""
	return text


TEXTE_PAGINA = {
	"html": (
		N_("Rețea"),
		N_("Se citește rețeaua..."),
		N_("Internetul"),
		N_("Se verifică internetul..."),
		N_("Cât de des se verifică internetul"),
		N_("30 de secunde"),
		N_("un minut"),
		N_("2 minute"),
		N_("5 minute"),
		N_("Receptorul verifică singur, în fundal, dacă are internet: trimite o întrebare DNS mică spre "
			"serverele publice 1.1.1.1, 9.9.9.9 și 8.8.8.8, fără date despre tine. La orice schimbare a "
			"rețelei (cablul, Wi-Fi, adresa) verifică pe loc. Aceeași setare pe televizor: Meniu &gt; Setări "
			"&gt; Rețea și Internet &gt; Verificarea internetului."),
		N_("Arată pictograma internetului în bare"),
		N_("Da: pictograma se vede în barele de pe televizor, în capul ferestrelor din tema Pro și în "
			"antetul acestor pagini. Nu: se ascunde, iar ce era lângă ea revine la locul ei; verificarea "
			"internetului merge mai departe. Aceeași setare pe televizor, lângă cea de mai sus."),
		N_("Trecerea singură pe altă rețea"),
		N_("Se citește..."),
		N_("Da: când internetul nu merge de câteva verificări la rând, receptorul trece singur pe cablu sau "
			"pe o rețea Wi-Fi salvată care are internet, și se întoarce când rețeaua lui își revine. Fără "
			"altă rețea nu face nimic. Nu trece în timpul unei actualizări sau al unei înregistrări din "
			"rețea."),
		N_("Ordinea rețelelor"),
		N_("După o trecere, receptorul poate avea altă adresă. Pe televizor apare adresa nouă; pagina se "
			"deschide mereu și cu <a href=\"http://hdsatelit.local/\">http://hdsatelit.local/</a>. Aceeași "
			"setare pe televizor: Meniu &gt; Setări &gt; Rețea și Internet &gt; Trecerea singură pe altă "
			"rețea."),
		N_("Cât de aglomerat e Wi-Fi-ul"),
		N_("Ce aparate sunt în rețea"),
		N_("Nu (din fabrică): plăcile de rețea nu au adrese IPv6, iar clientul IPv6 nu pornește; rețeaua merge pe "
			"IPv4, ca până acum. Da: receptorul primește și adrese IPv6, dacă rețeaua ta le dă. Se aplică pe loc. "
			"Aceeași setare pe televizor: Meniu &gt; Setări &gt; Rețea și Internet &gt; IPv6."),
		N_("Plăcile de rețea"),
		N_("Setările plăcii"),
		N_("Folosește placa"),
		N_("Da"),
		N_("Nu"),
		N_("Folosește DHCP"),
		N_("Cu DHCP, adresa, masca, poarta și serverele DNS le dă routerul."),
		N_("Adresa IP"),
		N_("Masca de rețea"),
		N_("Folosește o poartă"),
		N_("Poarta"),
		N_("De obicei, adresa routerului."),
		N_("Oprește cealaltă placă configurată (<span id=\"altaNume\"></span>)"),
		N_("O altă placă e deja configurată. Pe televizor, aceeași întrebare apare la OK."),
		N_("Aplică setările"),
		N_("Pune înapoi valorile de acum"),
		N_("Serverele DNS"),
		N_("Setările de acum"),
		N_("Proba rețelei"),
		N_("Pornește proba"),
		N_("Caută rețele"),
		N_("Rețea ascunsă"),
		N_("Rețeaua"),
		N_("Securitate"),
		N_("Semnal"),
		N_("Numele rețelei ascunse"),
		N_("Securitatea rețelei ascunse"),
		N_("Parola rețelei"),
		N_("Conectează"),
		N_("Înapoi"),
		N_("Oprește conectarea"),
		N_("Repornirea rețelei"),
		N_("Oprește și pornește din nou toate plăcile de rețea, cu setările salvate."),
		N_("Repornește rețeaua"),
		N_("Aceleași setări sunt pe televizor, în __DRUM_MENIU__. Serverele DNS au pagina lor: <a "
			"href=\"/dns\" id=\"legaturaDns\">Servere DNS</a>."),
		N_("Servere DNS"),
		N_("Se citesc serverele..."),
		N_("Serverele de nume"),
		N_("Nu e niciun server DNS. Fără el, receptorul nu găsește adresele de pe internet după nume."),
		N_("Adaugă un server"),
		N_("Salvează și aplică"),
		N_("Renunță"),
		N_("Setările plăcilor"),
		N_("Serverul DNS transformă numele (de exemplu hdsatelit.com) în adrese. Cu DHCP, serverele le dă "
			"de obicei routerul. Exemple: 1.1.1.1, 8.8.8.8, 9.9.9.9. Aceleași setări sunt pe televizor, în "
			"__DRUM_MENIU__."),
	),
	"js": (
		N_("nu se știe"),
		N_("pornită"),
		N_("oprită"),
		N_("legătură:"),
		N_("fără adresă"),
		N_("implicită"),
		N_("browserul tău e legat prin ea"),
		N_("Aleasă"),
		N_("Setări"),
		N_("Fă-o implicită"),
		N_("Placa implicită e cea prin care receptorul iese spre internet când sunt pornite două plăci."),
		N_("Setările plăcii"),
		N_("Placa"),
		N_("Adresa IP"),
		N_("nu are"),
		N_("Masca de rețea"),
		N_("Poarta"),
		N_("Server DNS principal"),
		N_("Server DNS secundar"),
		N_("Adresa fizică (MAC)"),
		N_("Legătura"),
		N_("Proba găsește placa de rețea aleasă."),
		N_("Proba verifică dacă placa e legată la rețea. La deconectată: verifică dacă e pus cablul de "
			"rețea și dacă nu e rupt (la Wi-Fi: dacă placa e conectată la o rețea)."),
		N_("Pornit: adresa o dă routerul (verifică dacă routerul are DHCP pornit). Oprit: adresa e scrisă "
			"de mână (verifică setările de mai sus)."),
		N_("Proba verifică dacă receptorul ajunge la internet cu adresa lui. La neconfirmată: verifică "
			"DHCP, cablul și setările plăcii."),
		N_("Proba verifică serverele de nume. La neconfirmat: verifică DHCP, cablul, setările plăcii și, "
			"dacă le-ai scris de mână, serverele DNS."),
		N_("Proba verifică pe rând placa, legătura, DHCP, adresa IP și serverele de nume."),
		N_("fără răspuns"),
		N_("se verifică..."),
		N_("Rețeaua fără fir"),
		N_("Rețeaua locală"),
		N_("conectată"),
		N_("deconectată"),
		N_("confirmată"),
		N_("neconfirmată"),
		N_("Serverele de nume"),
		N_("Pornește proba din nou"),
		N_("Proba lucrează..."),
		N_("Se citește starea Wi-Fi..."),
		N_("Placa e oprită. Starea Wi-Fi se vede când placa e pornită."),
		N_("Conectat:"),
		N_("Conectează"),
		N_("Conectarea la o rețea ascunsă"),
		N_("Conectarea la"),
		N_("Se lucrează la rețea ("),
		N_("Receptorul nu a putut citi rețeaua."),
		N_("Legătura s-a întrerupt cât rețeaua pornește din nou. Pagina încearcă singură; dacă adresa s-a "
			"schimbat, deschide pagina la adresa nouă."),
		N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
		N_("Dacă browserul era legat prin această placă, pagina e acum la"),
		N_("Oprită: receptorul rămâne pe rețeaua lui."),
		N_("Pornită, dar receptorul are o singură rețea: nu are pe ce trece."),
		N_("Acum pe"),
		N_("(internetul nu mergea prin"),
		N_("). Se întoarce singur când acolo merge din nou."),
		N_("Pornită. Acum receptorul e pe rețeaua lui obișnuită."),
		N_("Ordinea:"),
		N_("Adresa receptorului:"),
		N_("(sau hdsatelit.local)"),
		N_("Amânat:"),
		N_("Ultima dată:"),
		N_("Server DNS"),
		N_("Scoate"),
		N_("Receptorul nu a putut citi serverele."),
		N_("Nu s-a schimbat nimic."),
	),
}


def _traducePagina(sablon, fel="pagina"):
	"""Sablonul in limba receptorului; fara pachetul HdsWebControl (probele de pe PC), sablonul ca atare."""
	try:
		from .traducere_pagini import traduce
	except ImportError:
		return sablon
	return traduce(sablon, TEXTE_PAGINA, fel)
# ---------------------------------------------------------------- sfarsitul traducerii paginilor
