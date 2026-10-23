# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsIptvSurse: sursele IPTV (playlist M3U, portal Stalker, cont Xtream) si setarile config.hds_iptv.*, intr-un singur
# loc pentru ecranul de pe televizor (Screens/IptvSetup.py, Meniu > Setari > Surse Internet > IPTV, cu "Date de acces"
# pe Albastru) si pentru pagina web /iptv (HdsWebControl/internet_web.py): randurile, numele lor si verificarea unui
# text scris (valoareBuna).
#
# STAREA, cinstit (aceeasi ca in ghidul ecranului): sursele M3U se tin intr-o lista (/etc/enigma2/hds_iptv_surse.conf,
# un rand tip|nume|date pe sursa); pentru Stalker si Xtream se salveaza numai datele de acces, conectarea reala e faza
# urmatoare. Nicio alta parte a receptorului nu citeste inca lista sau setarile (intrarea e in lucru in meniu).
#
# Fisierul nu importa nimic din enigma2 la incarcare (config se ia in functii).

import os
import re

CALE_SURSE = "/etc/enigma2/hds_iptv_surse.conf"  # o linie per sursa: tip|nume|date (format simplu, editabil manual)
MAX_SURSE = 100
MAX_TEXT = 512

ETICHETE = {"m3u": "M3U", "stalker": "Stalker", "xtream": "Xtream"}
_MAC = re.compile(r"^[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}$")


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_), fara efect: numele campurilor se traduc la folosire."""
	return text


# setarile text config.hds_iptv.* (aceleasi randuri pe televizor, in "Date de acces", si in pagina web /iptv) si
# parola, care nu se arata nicaieri: se scrie numai cand se schimba
CAMPURI = ("m3u_cale", "stalker_portal", "stalker_mac", "xtream_server", "xtream_port", "xtream_user")
SECRETE = ("xtream_parola",)
NUME_CAMPURI = {
	"tip_sursa": N_("Tipul sursei"), "m3u_cale": N_("Playlist M3U/M3U8"), "stalker_portal": N_("Portal Stalker"),
	"stalker_mac": N_("Adresa MAC"), "xtream_server": N_("Server Xtream"), "xtream_port": N_("Port Xtream"),
	"xtream_user": N_("Utilizator Xtream"), "xtream_parola": N_("Parola Xtream"),
}


def initConfigIptv(config=None):
	"""config.hds_iptv.* (o singura data). hasattr(config, ...) nu e sigur: ConfigSubsection.__getattr__ arunca KeyError,
	nu AttributeError, pentru o cheie lipsa; se verifica in config.content.items."""
	from Components.config import ConfigSubsection, ConfigText, ConfigSelection
	if config is None:
		from Components.config import config
	if "hds_iptv" not in config.content.items:
		config.hds_iptv = ConfigSubsection()
		config.hds_iptv.tip_sursa = ConfigSelection(default="m3u", choices=[
			("m3u", _("Playlist M3U/M3U8 (fișier local sau URL)")),
			("stalker", _("Portal Stalker/Ministra")),
			("xtream", _("Cont Xtream Codes")),
		])
		config.hds_iptv.m3u_cale = ConfigText(default="", fixed_size=False)
		config.hds_iptv.stalker_portal = ConfigText(default="", fixed_size=False)
		config.hds_iptv.stalker_mac = ConfigText(default="00:1A:79:", fixed_size=False)
		config.hds_iptv.xtream_server = ConfigText(default="", fixed_size=False)
		config.hds_iptv.xtream_port = ConfigText(default="80", fixed_size=False)
		config.hds_iptv.xtream_user = ConfigText(default="", fixed_size=False)
		config.hds_iptv.xtream_parola = ConfigText(default="", fixed_size=False)
	return config.hds_iptv


def salveazaSurse(surse, cale=None):
	"""surse = lista de tupluri (tip, nume, date). Scrie fisierul, o linie per sursa (printr-un .nou si o redenumire).
	-> True daca s-a scris."""
	cale = cale or CALE_SURSE
	nou = cale + ".nou"
	try:
		with open(nou, "w", encoding="utf-8") as f:
			for tip, nume, date in surse:
				f.write("%s|%s|%s\n" % (tip, nume.replace("|", " ").replace("\n", " "), date.replace("\n", " ")))
		os.replace(nou, cale)
		return True
	except OSError:
		try:
			os.unlink(nou)
		except OSError:
			pass
		return False  # emulator/PC fara /etc/enigma2 scriabil: nu blocam ecranul de configurare


def incarcaSurse(cale=None):
	cale = cale or CALE_SURSE
	if not os.path.isfile(cale):
		return []
	rezultat = []
	try:
		with open(cale, encoding="utf-8") as f:
			for linie in f:
				parti = linie.rstrip("\n").split("|", 2)
				if len(parti) == 3:
					rezultat.append(tuple(parti))
	except OSError:
		pass
	return rezultat


def randSursa(sursa):
	"""Randul din lista de pe televizor: "[M3U] nume"."""
	tip, nume, date = sursa
	return "[%s] %s" % (ETICHETE.get(tip, tip), nume or date)


def textBun(text, maxim=MAX_TEXT):
	"""Un text de setare: fara caractere de control (fisierul de setari are un rand pe setare), cel mult `maxim`."""
	return len(text) <= maxim and not any(ord(c) < 32 or ord(c) == 127 for c in text)


def adaugaM3U(surse, cale):
	"""Galben pe televizor (Adauga sursa M3U): sursa din calea sau adresa scrisa in config.hds_iptv.m3u_cale.
	-> sursa adaugata sau None (cale goala, gresita sau lista plina)."""
	cale = (cale or "").strip()
	if not cale or not textBun(cale) or len(surse) >= MAX_SURSE:
		return None
	sursa = ("m3u", os.path.basename(cale) or cale, cale)
	surse.append(sursa)
	return sursa


def stergeSursa(surse, index):
	"""Verde pe televizor (Sterge selectia). -> sursa scoasa sau None."""
	if surse and 0 <= index < len(surse):
		return surse.pop(index)
	return None


def macBun(text):
	return bool(_MAC.match(text))


def portBun(text):
	return text.isdigit() and len(text) <= 5 and 0 < int(text) <= 65535


def valoareBuna(cheie, text):
	"""Textul bun pentru config.hds_iptv.<cheie>, sau None: aceeasi verificare pe televizor (Screens/IptvSetup.py) si in
	pagina web (internet_web.py). Fara caractere de control, cel mult MAX_TEXT; adresa MAC si portul in forma lor (gol
	se poate); adresele, utilizatorul si parola fara spatii."""
	if not textBun(text):
		return None
	if cheie == "stalker_mac" and text and not macBun(text):
		return None
	if cheie == "xtream_port" and text and not portBun(text):
		return None
	if cheie in ("stalker_portal", "xtream_server", "xtream_user", "xtream_parola") and any(x.isspace() for x in text):
		return None
	return text
