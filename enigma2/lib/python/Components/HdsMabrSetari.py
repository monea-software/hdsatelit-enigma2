# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsMabrSetari: setarile DVB-MABR (IP multicast) si cautarea sesiunilor SAP, intr-un singur loc pentru ecranul de pe
# televizor (Screens/HdsDvbMABR.py, Meniu > Setari > Surse Internet > DVB-MABR) si pentru pagina web /mabr
# (HdsWebControl/internet_web.py).
#
# Setarile stau in /etc/enigma2/hdsmabr.conf: activ, autodiscover (descoperirea SAP/SD&S), interfata (fara rand pe
# ecran; se pastreaza) si cate un rand grup = adresa:port pentru fiecare grup multicast adaugat de mana.
# STAREA, cinstit: intrarea e marcata in lucru in meniu. Nicio parte a receptorului nu citeste inca hdsmabr.conf, iar
# modulul de ascultare SAP (Plugins.SystemPlugins.HdsComun.dvb_nit_ip) nu e in imagine: cautarea spune asta.
#
# Fisierul nu importa nimic din enigma2 la incarcare.

import os
import threading
import time

CALE_CONFIG = "/etc/enigma2/hdsmabr.conf"
MAX_GRUPURI = 64
SECUNDE_CAUTARE = 5.0

_CAUTARE = {"in_curs": False, "rezultat": None, "ora": 0}


def implicit():
	return {"activ": "da", "autodiscover": "da", "interfata": "", "grupuri": []}


def citeste(cale=None):
	config = implicit()
	cale = cale or CALE_CONFIG
	if not os.path.exists(cale):
		return config
	try:
		with open(cale, "r", encoding="utf-8", errors="replace") as f:
			for linie in f:
				linie = linie.strip()
				if not linie or linie.startswith("#") or "=" not in linie:
					continue
				cheie, val = linie.split("=", 1)
				cheie, val = cheie.strip().lower(), val.strip()
				if cheie in ("activ", "autodiscover"):
					config[cheie] = val.lower()
				elif cheie == "interfata":
					config["interfata"] = val
				elif cheie == "grup" and ":" in val:
					parti = val.split(":")
					if len(parti) == 2:
						try:
							config["grupuri"].append((parti[0].strip(), int(parti[1].strip())))
						except ValueError:
							pass
	except (IOError, OSError) as eroare:
		print("[HdsMabrSetari] citirea %s: %s" % (cale, eroare))
	return config


def scrie(config, cale=None):
	"""-> True daca s-a scris (printr-un fisier .nou si o redenumire)."""
	cale = cale or CALE_CONFIG
	linii = [
		"# Configurare HdsDvbMABR: DVB-MABR IP Multicast HDSatelit",
		"activ = %s" % config.get("activ", "da"),
		"autodiscover = %s" % config.get("autodiscover", "da"),
		"interfata = %s" % config.get("interfata", ""),
	]
	for adresa, port in config.get("grupuri", []):
		linii.append("grup = %s:%d" % (adresa, port))
	nou = cale + ".nou"
	try:
		with open(nou, "w", encoding="utf-8") as f:
			f.write("\n".join(linii) + "\n")
		os.replace(nou, cale)
		return True
	except (IOError, OSError) as eroare:
		print("[HdsMabrSetari] scrierea %s: %s" % (cale, eroare))
		try:
			os.unlink(nou)
		except OSError:
			pass
		return False


def pornit(config, cheie):
	"""activ / autodiscover ca adevarat sau fals (da, yes, 1)."""
	return str(config.get(cheie, "da")).lower() in ("da", "yes", "1", "true")


def textStare(config):
	"""Randul de sus al ecranului de pe televizor."""
	return _("DVB-MABR: %s | Autodiscover SAP: %s | Grupuri manuale: %d") % (
		_("ACTIV") if pornit(config, "activ") else _("INACTIV"),
		_("DA") if pornit(config, "autodiscover") else _("NU"),
		len(config.get("grupuri", [])))


def comuta(config, cheie):
	"""OK sau Galben pe randurile "DVB-MABR activ" si "Autodiscover SAP/SD&S". -> False pentru alta cheie."""
	if cheie not in ("activ", "autodiscover"):
		return False
	config[cheie] = "nu" if pornit(config, cheie) else "da"
	return True


def textGrup(adresa, port):
	return "udp://@%s:%d" % (adresa, port)


def adaugaGrup(config, text):
	"""Randul "+ Adauga grup manual": textul adresa:port, cu aceleasi verificari si mesaje ca pe televizor.
	-> (reusit, mesaj)."""
	text = (text or "").strip()
	if ":" not in text:
		return False, _("Format invalid: trebuie adresa:port (ex. 239.1.1.1:9000).")
	adresa, _sep, port_txt = text.rpartition(":")
	adresa = adresa.strip()
	try:
		port = int(port_txt.strip())
	except ValueError:
		return False, _("Port invalid: %s") % port_txt[:20]
	if not (0 < port <= 65535):
		return False, _("Port în afara intervalului 1-65535.")
	parti_ip = adresa.split(".")
	if len(parti_ip) != 4 or not all(p.isdigit() and len(p) <= 3 and 0 <= int(p) <= 255 for p in parti_ip):
		return False, _("Adresa IP invalidă: %s") % adresa[:40]
	adresa = ".".join(str(int(p)) for p in parti_ip)
	if not (224 <= int(parti_ip[0]) <= 239):
		return False, _("Adresa %s nu e multicast (224.0.0.0 - 239.255.255.255).") % adresa
	grupuri = config.setdefault("grupuri", [])
	if (adresa, port) in grupuri:
		return False, _("Grupul udp://@%s:%d e deja în listă.") % (adresa, port)
	if len(grupuri) >= MAX_GRUPURI:
		return False, _("Sunt prea multe grupuri. Șterge unul înainte.")
	grupuri.append((adresa, port))
	return True, _("Adăugat: udp://@%s:%d") % (adresa, port)


def stergeGrup(config, index):
	"""OK pe un grup: il scoate. -> (adresa, port) scos sau None."""
	grupuri = config.get("grupuri", [])
	if 0 <= index < len(grupuri):
		return grupuri.pop(index)
	return None


# ------------------------------------------------------------------ cautarea sesiunilor SAP
# Rezultatul unei cautari: {"sesiuni": [{"adresa", "port", "nume"}], "eroare": ""}; ecranul si pagina il scriu fiecare
# in felul lor (pe televizor primele 3 sesiuni, in web toate), cu acelasi mesaj cand nu e nicio sesiune sau e o eroare.
def cautaSesiuni(interfata, asculta=None):
	"""Cautarea propriu-zisa (dureaza SECUNDE_CAUTARE); merge pe un fir separat."""
	try:
		if asculta is None:
			from Plugins.SystemPlugins.HdsComun import dvb_nit_ip
			asculta = dvb_nit_ip.asculta_sap
		sesiuni = asculta(interfata=interfata, timeout=SECUNDE_CAUTARE) or []
		return {"sesiuni": [{"adresa": str(s.adresa_multicast), "port": int(s.port), "nume": str(s.nume or "")}
			for s in sesiuni], "eroare": ""}
	except ImportError:
		return {"sesiuni": [], "eroare": _("Modul dvb_nit_ip nedisponibil pe acest receptor.")}
	except Exception as eroare:
		return {"sesiuni": [], "eroare": _("Eroare căutare: %s") % eroare}


def mesajCautare(rezultat):
	"""Mesajul unei cautari fara sesiuni (eroarea sau "nicio sesiune"); "" cand sunt sesiuni."""
	if rezultat.get("eroare"):
		return rezultat["eroare"]
	if not rezultat.get("sesiuni"):
		return _("Nicio sesiune MABR descoperită în rețea.")
	return ""


def stareCautare():
	return dict(_CAUTARE)


def cauta(interfata, la_gata=None, asculta=None, pe_fir=True):
	"""Albastru (Cauta SAP): cautarea pe un fir separat; `la_gata(rezultat)` vine pe firul enigma2
	(reactor.callFromThread). -> False daca o cautare e deja in curs."""
	acum = time.time()
	# o cautare "in curs" de mai mult de 60 s nu mai raspunde (dureaza SECUNDE_CAUTARE): nu mai opreste
	if _CAUTARE["in_curs"] and acum - _CAUTARE["ora"] < 60:
		return False
	_CAUTARE.update(in_curs=True, rezultat=None, ora=acum)

	def _gata(rezultat):
		_CAUTARE.update(in_curs=False, rezultat=rezultat)
		if la_gata is not None:
			la_gata(rezultat)

	def _fir():
		rezultat = cautaSesiuni(interfata, asculta)
		try:
			from twisted.internet import reactor
			reactor.callFromThread(_gata, rezultat)
		except ImportError:
			_gata(rezultat)

	if pe_fir:
		threading.Thread(target=_fir, name="HdsMabr-sap", daemon=True).start()
	else:
		_fir()
	return True
