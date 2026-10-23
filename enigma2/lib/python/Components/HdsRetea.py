# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsRetea.py: logica ecranelor de retea (Screens/NetworkSetup.py), aceeasi pe televizor si in interfata web
# (Plugins/Extensions/HdsWebControl/retea_web.py, paginile /retea si /dns):
# - adaptoare(): placile din lista "Network Connection Setup" (cele citite de iNetwork, altfel cele configurate, altfel
#   cele din /sys/class/net);
# - placaImplicita() / alegePlacaImplicita(): placa implicita din /etc/default_gw (tasta galbena a listei, numai cu
#   doua placi configurate), dupa care reteaua se reporneste;
# - aplicaPlaca(): ce face OK in "Adapter settings" (atributele lui iNetwork, ifdown / ifup, /etc/network/interfaces);
# - trebuieOpritaAlta() / opresteCelelalte(): intrebarea despre a doua placa configurata si raspunsul Da;
# - scrieDns(): OK in "Nameserver settings" (/etc/resolv.conf);
# - reporneste(): "Restart network" (iNetwork.restartNetwork, apoi placile citite din nou);
# - legaturaEthtool(), confirmat(): citirea legaturii din ethtool si pragul probei retelei (cel mult 2 adrese care nu
#   raspund din 3);
# - stareAdaptor() / textStare() / pictogramaStare(): ce arata lista placilor pentru fiecare placa: pornita, cablu bagat
#   sau legata la Wi-Fi (si semnalul), adresa IPv4, daca internetul trece pe ea (ruta implicita castigatoare).
# Comenzile le dau functiile lui iNetwork (Components/Network.py: liste de argumente, fara shell, pe consola enigma2);
# sfarsitul vine prin functia `gata`, pe firul enigma2, o singura data.
#
# Modulul nu importa nimic din enigma2 la incarcare: probele de pe PC dau o retea falsa (parametrul R).

import os

CALE_PLACA_IMPLICITA = "/etc/default_gw"
SYS_NET = "/sys/class/net/"
CALE_RUTE = "/proc/net/route"
CALE_WIRELESS = "/proc/net/wireless"


def retea(R=None):
	"""iNetwork (Components/Network.py), sau reteaua falsa a probelor."""
	if R is not None:
		return R
	from Components.Network import iNetwork
	return iNetwork


def adaptoare(R=None):
	"""Numele placilor, in ordinea listei de pe televizor."""
	R = retea(R)
	placi = list(R.getAdapterList())
	if not placi:
		placi = list(R.getConfiguredAdapters())
	if not placi:
		placi = list(R.getInstalledAdapters())
	return placi


def _citeste(cale):
	try:
		with open(cale, "r", encoding="utf-8", errors="replace") as f:
			return f.read()
	except (IOError, OSError):
		return None


def _sterge(cale):
	try:
		os.unlink(cale)
	except OSError:
		pass


def placaImplicita(R=None, cale=CALE_PLACA_IMPLICITA):
	"""Numele placii implicite, sau None. Cu mai putin de doua placi configurate fisierul nu mai are rost si se sterge,
	ca la fiecare citire a listei de pe televizor."""
	R = retea(R)
	if len(R.getConfiguredAdapters()) < 2 and os.path.exists(cale):
		_sterge(cale)
	if os.path.exists(cale):
		return _citeste(cale)
	return None


def alegePlacaImplicita(placa, R=None, cale=CALE_PLACA_IMPLICITA):
	"""Tasta galbena din lista placilor: True cand s-a schimbat ceva si reteaua trebuie repornita."""
	R = retea(R)
	configurate = len(R.getConfiguredAdapters())
	veche = _citeste(cale) if os.path.exists(cale) else None
	if configurate > 1 and (not veche or veche != placa):
		with open(cale, "w", encoding="utf-8") as f:
			f.write(placa)
		return True
	if veche and configurate < 2:
		_sterge(cale)
		return True
	return False


def _oData(gata):
	"""gata(True) chemata o singura data (getInterfaces cheama la fiecare placa citita)."""
	stare = [False]

	def f(data=True):
		if data is True and not stare[0]:
			stare[0] = True
			if gata is not None:
				gata(True)
	return f


def reporneste(gata=None, R=None):
	"""Restart network: restartNetwork, apoi placile citite din nou; gata(True) la sfarsit."""
	R = retea(R)
	citite = _oData(gata)

	def repornita(data):
		if data is True:
			R.getInterfaces(citite)
	R.restartNetwork(repornita)


def _comutarePornita():
	"""Setarea trecerii singure (config.usage.hds_retea_comutare); fara setarile enigma2 incarcate (probele de pe PC):
	False."""
	import sys
	if sys.modules.get("Components.config") is None:
		return False
	try:
		from Components import HdsComutareRetea
		return HdsComutareRetea.pornita()
	except Exception:
		return False


def trebuieOpritaAlta(placa, R=None, comutare=None):
	"""True cand alta placa e configurata, iar aceasta nu: televizorul intreaba daca o opreste pe cealalta. Cu trecerea
	singura pe alta retea pornita (Components/HdsComutareRetea.py) nu se intreaba: trecerea are nevoie de amandoua
	placile pornite (cablul si Wi-Fi-ul), iar rutele le tine ea in ordine."""
	R = retea(R)
	if (_comutarePornita() if comutare is None else comutare):
		return False
	configurate = R.getConfiguredAdapters()
	return len(configurate) >= 1 and placa not in configurate


def opresteCelelalte(placa, gata, R=None):
	"""Da la intrebarea despre a doua placa: celelalte placi configurate se opresc, apoi gata(True)."""
	R = retea(R)
	configurate = R.getConfiguredAdapters()
	for x in configurate:
		if x != placa:
			R.setAdapterAttribute(x, "up", False)

	def oprite(data):
		if data is True and gata is not None:
			gata(True)
	R.deactivateInterface(configurate, oprite)


def aplicaPlaca(placa, sus, dhcp, ip, masca, poarta, stare_veche, gata, R=None, extra=None):
	"""OK in "Adapter settings": atributele placii, ifdown / ifup si /etc/network/interfaces, apoi placile citite din
	nou si gata(True). `ip`, `masca`, `poarta` sunt liste de 4 numere; poarta None = fara poarta. `stare_veche` e
	atributul "up" de dinaintea schimbarii (False: placa doar porneste; altfel se opreste si porneste din nou).
	`extra()` scrie randurile Wi-Fi ale extensiei WirelessLan, cand ecranul le are."""
	R = retea(R)
	R.setAdapterAttribute(placa, "up", sus)
	R.setAdapterAttribute(placa, "dhcp", dhcp)
	R.setAdapterAttribute(placa, "ip", ip)
	R.setAdapterAttribute(placa, "netmask", masca)
	if poarta is not None:
		R.setAdapterAttribute(placa, "gateway", poarta)
	else:
		R.removeAdapterAttribute(placa, "gateway")
	if extra is not None:
		extra()
	citite = _oData(gata)

	def aplicata(data):
		if data is True:
			R.getInterfaces(citite)

	def oprita(data):
		if data is True:
			R.activateInterface(placa, aplicata)
	if sus is False:
		R.deactivateInterface(placa, aplicata)
	elif stare_veche is False:
		R.activateInterface(placa, aplicata)
	else:
		R.deactivateInterface(placa, oprita)
	R.writeNetworkConfig()


def scrieDns(servere, R=None):
	"""OK in "Nameserver settings": lista noua (fara dubluri, ca addNameserver) scrisa in /etc/resolv.conf."""
	R = retea(R)
	R.clearNameservers()
	for server in servere:
		R.addNameserver(server)
	R.writeNameserverConfig()


def legaturaEthtool(text):
	"""True / False dupa randul "Link detected:" din iesirea lui ethtool, None fara el."""
	if isinstance(text, bytes):
		text = text.decode("utf-8", "replace")
	stare = None
	for rand in (text or "").splitlines():
		rand = rand.strip()
		if "Link detected:" in rand:
			stare = "yes" in rand
	return stare


def confirmat(esecuri):
	"""Proba retelei: adresa IP si serverele de nume sunt confirmate cand au raspuns cel putin una din cele 3 probe."""
	return esecuri <= 2


# ---------------------------------------------------------------- starea fiecarei placi (lista placilor)

def _fisier(radacina, cale):
	t = _citeste(radacina + cale)
	return (t or "").strip()


def _ruta_castigatoare(radacina=""):
	"""Placa rutei implicite pe care o foloseste nucleul: metrica cea mai mica, fara rutele unei placi fara legatura
	(cablul scos; nucleul le sare cand ignore_routes_with_linkdown e pornit, Components/HdsComutareRetea.py)."""
	rute = []
	for rand in (_citeste(radacina + CALE_RUTE) or "").splitlines()[1:]:
		p = rand.split()
		if len(p) < 8 or p[1] != "00000000" or p[7] != "00000000":
			continue
		try:
			if not int(p[3], 16) & 1:
				continue
			rute.append((int(p[6]), len(rute), p[0]))
		except ValueError:
			continue
	cu_legatura = [r for r in rute if _fisier(radacina, SYS_NET + r[2] + "/carrier") != "0"]
	alese = cu_legatura or rute
	return min(alese)[2] if alese else None


def _nivel_wifi(radacina, placa):
	"""Calitatea legaturii Wi-Fi in procente, din /proc/net/wireless (nivelul in dBm), sau None."""
	for rand in (_citeste(radacina + CALE_WIRELESS) or "").splitlines()[2:]:
		p = rand.replace(":", " ", 1).split()
		if len(p) >= 4 and p[0] == placa:
			try:
				nivel = int(float(p[3].rstrip(".")))
			except ValueError:
				return None
			if nivel > 0:
				nivel -= 256
			if nivel in (0, -256) or nivel < -110:
				return None
			return max(0, min(100, 2 * (nivel + 100)))
	return None


def adresaPlacii(placa):
	"""Adresa IPv4 de acum a placii, din nucleu (SIOCGIFADDR, fara alt proces): "a.b.c.d", "" fara adresa, None cand nu
	se poate afla (alt sistem decat Linux)."""
	try:
		import fcntl
		import socket
		import struct
	except ImportError:
		return None
	s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	try:
		r = fcntl.ioctl(s.fileno(), 0x8915, struct.pack("256s", placa[:15].encode("ascii", "replace")))
		return socket.inet_ntoa(r[20:24])
	except (IOError, OSError, ValueError):
		return ""
	finally:
		s.close()


def stareAdaptor(placa, ip=None, radacina="", wifi=None):
	"""Starea de acum a placii, din fisierele nucleului (nimic trimis in retea):
	{"pornita": bool, "legatura": True/False/None (cablul bagat sau Wi-Fi legat), "wifi": bool, "ip": "a.b.c.d" sau "",
	"semnal": procent sau None, "internet": bool (ruta implicita castigatoare e pe ea), "activa": bool}.
	`ip` = lista de 4 numere sau textul adresei (din iNetwork); None = nestiuta."""
	flags = _fisier(radacina, SYS_NET + placa + "/flags")
	try:
		pornita = bool(int(flags, 16) & 1)
	except ValueError:
		pornita = False
	if wifi is None:
		wifi = os.path.exists(radacina + SYS_NET + placa + "/wireless") or \
			os.path.exists(radacina + SYS_NET + placa + "/phy80211")
	c = _fisier(radacina, SYS_NET + placa + "/carrier") if pornita else ""
	legatura = True if c == "1" else (False if c == "0" else None)
	if wifi and legatura and _fisier(radacina, SYS_NET + placa + "/operstate") not in ("up", "unknown", ""):
		legatura = False
	acum = adresaPlacii(placa) if not radacina else None
	if acum is not None:
		ip = acum
	if isinstance(ip, (list, tuple)):
		ip = ".".join(str(int(x)) for x in ip) if len(ip) == 4 and any(ip) else ""
	ip = ip or ""
	semnal = _nivel_wifi(radacina, placa) if wifi and legatura else None
	internet = pornita and legatura is not False and _ruta_castigatoare(radacina) == placa
	return {"pornita": pornita, "legatura": legatura, "wifi": bool(wifi), "ip": ip, "semnal": semnal,
		"internet": bool(internet), "activa": bool(pornita and legatura and ip)}


def textStare(st):
	"""Randul de sub numele placii in lista: ce face placa acum, scurt (incape pe un rand al listei)."""
	if not st["pornita"]:
		return _t("Oprită")
	parti = []
	if st["wifi"]:
		if st["legatura"]:
			parti.append(_t("Activă") if st["ip"] else _t("Legată la Wi-Fi, fără adresă IP"))
			if st["semnal"] is not None:
				parti.append(_t("semnal %d%%") % st["semnal"])
		else:
			parti.append(_t("Pornită, dar nelegată la nicio rețea Wi-Fi"))
	else:
		if st["legatura"]:
			parti.append(_t("Activă, cablul e bagat") if st["ip"] else _t("Cablul e bagat, fără adresă IP"))
		elif st["legatura"] is False:
			parti.append(_t("Pornită, dar fără cablu"))
		else:
			parti.append(_t("Pornită"))
	if st["ip"] and st["legatura"]:
		parti.append(st["ip"])
	if st["internet"]:
		parti.append(_t("internetul trece pe aici"))
	return " · ".join(parti)


def pictogramaStare(st):
	"""Pictograma placii: "activa" (bifa verde: pornita, legata, cu adresa), "oprita" (X rosu) sau "fara" (fara semn:
	pornita, dar fara cablu / nelegata / fara adresa)."""
	if st["activa"]:
		return "activa"
	if not st["pornita"]:
		return "oprita"
	return "fara"


def _t(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text
