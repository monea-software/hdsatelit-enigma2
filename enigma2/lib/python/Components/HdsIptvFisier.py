# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsIptvFisier: adresele listelor M3U puse intr-un fisier text se iau singure in IPTV, fara nimic scris pe televizor.
#
# CUM: omul copiaza prin FTP (sau cu orice program de fisiere) un fisier /etc/enigma2/iptv.txt cu cate o adresa pe rand,
# http:// sau https://; pe acelasi rand poate sta si un nume (inainte sau dupa adresa). Randurile goale si cele care incep cu
# # nu conteaza. Receptorul se uita la fisier o data pe minut (numai marimea si ora lui, fara citire), iar cand s-a schimbat
# adauga sursele noi prin aceeasi cale ca ecranul si pagina web (HdsIptvClient.verificaDate, HdsIptvLucru.adaugaSiCere) si
# arata un mesaj scurt pe televizor. Pagina web /iptv trimite acelasi text (fisierul ales in browser) la preiaText.
#
# Fisierul ramane pe loc (al omului), dar cu drepturile 0600, fiindca adresele pot avea parola in ele. Randurile luate se tin
# minte (amprenta adresei, in /etc/enigma2/hds_iptv/fisier-preluat.json): o sursa stearsa de om din lista nu revine la minutul
# urmator; daca o vrea inapoi, o adauga din ecran sau schimba randul. Un fisier care e chiar o lista de canale (#EXTM3U,
# #EXTINF) nu e o lista de adrese: nu se ia nimic din el, iar mesajul spune ce sa faca.
#
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau caile si functiile lor.

import hashlib
import json
import os
import re

CALE = "/etc/enigma2/iptv.txt"
NUME_TINUTE = "fisier-preluat.json"
MAX_OCTETI = 256 * 1024
MAX_RANDURI = 500
MAX_TINUTE = 2000
PAS_S = 60
PRIMA_S = 20

_ADRESA = re.compile(r"https?://\S+", re.IGNORECASE)
# ce desparte numele de adresa pe acelasi rand
_SEPARATORI = " \t|,;=:-"


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_), fara efect: textele se traduc la afisare."""
	return text


T_ADAUGATE = N_("Liste IPTV luate din fișierul %(fisier)s: %(n)d. Canalele apar în lista de canale, la Sateliți, pe rândul IPTV.")
T_GRESITE = N_("Rânduri fără o adresă bună în %(fisier)s: %(n)d. Pune câte o adresă pe rând, care începe cu http:// sau https://.")
T_PLAYLIST = N_("Fișierul %s e chiar o listă de canale, nu o listă de adrese. Pune-l pe un stick și adaugă-l ca Playlist.")
T_NIMIC = N_("Fișierul nu are nicio adresă nouă.")
T_PREA_MARE = N_("Fișierul e prea mare pentru o listă de adrese.")


def _t(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def ePlaylist(text):
	"""Un fisier M3U adevarat (canalele insesi), nu o lista de adrese de liste."""
	inceput = text.lstrip("﻿ \t\r\n")[:16].upper()
	return inceput.startswith("#EXTM3U") or "#EXTINF" in text[:65536].upper()


def randuri(text):
	"""-> (lista [(adresa, nume)] in ordinea din fisier, fara dubluri; numarul randurilor fara adresa buna)."""
	rez, vazute, gresite = [], set(), 0
	for n, rand in enumerate(text.replace("\r", "\n").split("\n")):
		if n >= MAX_RANDURI:
			break
		rand = rand.strip().lstrip("﻿")
		if not rand or rand.startswith("#"):
			continue
		m = _ADRESA.search(rand)
		if m is None:
			gresite += 1
			continue
		adresa = m.group(0)
		nume = (rand[:m.start()] + " " + rand[m.end():]).strip(_SEPARATORI + " ")
		if adresa in vazute:
			continue
		vazute.add(adresa)
		rez.append((adresa, nume))
	return rez, gresite


def amprenta(adresa):
	return hashlib.sha256(adresa.encode("utf-8")).hexdigest()[:20]


def _caleTinute(dosar):
	return os.path.join(dosar, NUME_TINUTE)


def citesteTinute(dosar):
	try:
		with open(_caleTinute(dosar), "rb") as f:
			date = json.loads(f.read().decode("utf-8"))
		return [x for x in date if isinstance(x, str)] if isinstance(date, list) else []
	except (OSError, ValueError):
		return []


def scrieTinute(dosar, tinute):
	tinute = tinute[-MAX_TINUTE:]
	try:
		if not os.path.isdir(dosar):
			os.makedirs(dosar, 0o700)
		cale = _caleTinute(dosar)
		temp = cale + ".nou"
		fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
		with os.fdopen(fd, "wb") as f:
			f.write(json.dumps(tinute).encode("utf-8"))
		os.replace(temp, cale)
	except OSError as e:
		print("[HdsIptvFisier] nu am putut tine minte randurile: %s" % type(e).__name__)


def _uneltele():
	from Components import HdsIptvClient as C, HdsIptvLucru as L, HdsIptvSurse as I
	return C.verificaDate, L.adaugaSiCere, I.DOSAR, C.E_PREA_MULTE


def preiaText(text, fisier=CALE, verifica=None, adauga=None, dosar=None, e_plin=None, tine_minte=True):
	"""Sursele noi din text. -> {"adaugate": [nume], "gresite": n, "plin": bool, "playlist": bool, "mesaje": [text tradus]}.
	tine_minte=False (pagina web): randurile nu se noteaza, omul a ales fisierul acum."""
	if verifica is None:
		verifica, adauga, dosar, e_plin = _uneltele()
	rez = {"adaugate": [], "gresite": 0, "plin": False, "playlist": False, "mesaje": []}
	if ePlaylist(text):
		rez["playlist"] = True
		rez["mesaje"].append(_t(T_PLAYLIST) % fisier)
		return rez
	lista, rez["gresite"] = randuri(text)
	tinute = citesteTinute(dosar) if tine_minte else []
	vechi = set(tinute)
	schimbat = False
	for adresa, nume in lista:
		a = amprenta(adresa)
		if a in vechi:
			continue
		sursa, eroare = verifica("m3u", {"adresa": adresa, "nume": nume})
		if eroare:
			rez["gresite"] += 1
		else:
			if adauga(sursa) is None:
				rez["plin"] = True
				break
			rez["adaugate"].append(sursa.get("nume") or "")
		if tine_minte:
			tinute.append(a)
			vechi.add(a)
			schimbat = True
	if schimbat:
		scrieTinute(dosar, tinute)
	if rez["adaugate"]:
		rez["mesaje"].append(_t(T_ADAUGATE) % {"fisier": fisier, "n": len(rez["adaugate"])})
	if rez["gresite"]:
		rez["mesaje"].append(_t(T_GRESITE) % {"fisier": fisier, "n": rez["gresite"]})
	if rez["plin"]:
		rez["mesaje"].append(_t(e_plin))
	return rez


def citesteFisier(cale=CALE):
	"""-> textul fisierului (si drepturile puse pe 0600), sau None cand lipseste ori e prea mare."""
	try:
		st = os.stat(cale)
	except OSError:
		return None
	if st.st_size > MAX_OCTETI:
		print("[HdsIptvFisier] %s are %d octeti, prea mult pentru o lista de adrese" % (cale, st.st_size))
		return None
	try:
		if st.st_mode & 0o077:
			os.chmod(cale, 0o600)
	except OSError:
		pass
	try:
		with open(cale, "rb") as f:
			return f.read(MAX_OCTETI).decode("utf-8", "replace")
	except OSError:
		return None


class Paznic(object):
	"""Se uita la fisier (marimea si ora); il citeste numai cand s-a schimbat."""

	def __init__(self, cale=CALE, preia=None, anunta=None):
		self.cale = cale
		self.preia = preia or (lambda text: preiaText(text, cale))
		self.anunta = anunta
		self.semn = None

	def verifica(self):
		try:
			st = os.stat(self.cale)
			semn = (st.st_size, int(st.st_mtime))
		except OSError:
			self.semn = None
			return None
		if semn == self.semn:
			return None
		self.semn = semn
		text = citesteFisier(self.cale)
		if text is None:
			return None
		try:
			rez = self.preia(text)
		except Exception as e:
			print("[HdsIptvFisier] %s: %r" % (self.cale, e))
			return None
		if rez["mesaje"] and (rez["adaugate"] or rez["gresite"] or rez["plin"] or rez["playlist"]) and self.anunta:
			self.anunta(" ".join(rez["mesaje"]))
		return rez


_paznic = None
_ceas = None


def _anuntaPeTelevizor(text):
	try:
		from Tools import Notifications
		from Screens.MessageBox import MessageBox
		Notifications.AddPopup(text=text, type=MessageBox.TYPE_INFO, timeout=10, id="HdsIptvFisier")
	except Exception as e:
		print("[HdsIptvFisier] mesajul: %r" % (e,))


def _tic():
	global _ceas
	if _ceas is not None:
		_ceas.start(PAS_S * 1000, True)
	try:
		_paznic.verifica()
	except Exception as e:
		print("[HdsIptvFisier] verificarea: %r" % (e,))


def porneste():
	"""La pornirea receptorului (HdsIptvLucru.porneste), si fara surse: o privire pe minut la fisier."""
	global _paznic, _ceas
	if _ceas is not None:
		return
	try:
		from enigma import eTimer
	except ImportError:
		return
	_paznic = Paznic(anunta=_anuntaPeTelevizor)
	_ceas = eTimer()
	_ceas.callback.append(_tic)
	_ceas.start(PRIMA_S * 1000, True)
