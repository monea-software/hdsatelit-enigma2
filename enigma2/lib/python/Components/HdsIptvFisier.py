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
# Listele de canale insesi (CRF, forum 1274, TODO 12.11 15:44): un fisier .m3u / .m3u8 copiat prin FTP direct in /etc/enigma2/, ori
# pus in radacina unui stick sau disc USB, apare singur in IPTV, fara nimic de apasat (PaznicListe). Receptorul se uita o
# data pe minut numai la ora dosarelor (stat pe radacina montarii, care sta oricum in memorie: discul care doarme nu porneste) si
# citeste dosarul numai cand ora lui s-a schimbat. Un fisier e luat numai daca are #EXTINF si macar o adresa de flux (o lista de muzica
# de pe stick, cu cai de fisiere, nu); fiecare fisier se incearca o singura data (numele, marimea si ora lui, tinute minte ca mai sus):
# o sursa stearsa de om nu revine, iar fisierul urcat din nou (alta marime sau ora) se ia din nou. /tmp nu se cerceteaza: acolo isi
# descarca listele furnizorului si pluginurile IPTV straine. iptv.txt care e chiar o lista de canale si fisierul ales in pagina web
# se copiaza in /etc/enigma2/hds_iptv/liste/. Locurile din retea (NFS, SMB) nu se cerceteaza: o partajare cazuta ar bloca firul.
#
# Preluarea automata se poate opri (space71, 19.11.2026): config.plugins.hds_iptv_fisiere.automat, Da din fabrica (purtarea
# de mai sus, neschimbata). Pe Nu, firul interfetei nu mai priveste dosarele: un fir de fundal (unul singur odata) le priveste,
# citeste inceputul listelor si lasa cererile in memorie; televizorul si pagina web intreaba omul. Raspunsul e numai memorie;
# fisierul se verifica din nou tot pe fir, iar sursa se adauga pe calea obisnuita (verificaDate, adaugaSiCere). Lista luata intra
# in fisier-preluat.json (scris numai de firul interfetei, ca la orice lista luata), deci nu revine. Lista refuzata intra in
# liste-refuzate.json, citit si scris numai de firul de fundal: pe Nu nu se mai cere; pe Da se ia, ca pe HEAD.
# iptv.txt ramane automat: e fisierul pus anume de om ca sa fie luat.
#
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau caile si functiile lor.

import hashlib
import json
import os
import re
import shutil
import threading
from collections import deque

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
# fisierul e o lista de canale, dar fara nicio adresa de flux (de pilda o lista de muzica de pe stick)
T_PLAYLIST = N_("Fișierul %s e o listă de canale fără nicio adresă de internet, deci nu am ce pune în IPTV.")
T_LISTE_ADAUGATE = N_("Liste de canale găsite și puse în IPTV: %(nume)s. Canalele apar în lista de canale, la Sateliți, pe rândul IPTV.")
T_PLAYLIST_PREA_MARE = N_("Lista de canale %s e prea mare pentru memoria receptorului. Pune-o pe un stick.")

# Listele de canale puse prin FTP sau pe stick (CRF, forum 1274)
LOC_FTP = "/etc/enigma2"
# /tmp nu e printre locuri: pluginurile IPTV straine isi descarca acolo listele furnizorului (ar aparea a doua oara in IPTV)
EXTENSII_PLAYLIST = (".m3u", ".m3u8")
# sistemele de fisiere ale stick-urilor si discurilor legate la receptor; partajarile din retea si memoria nu se cerceteaza
FS_LOCALE = ("vfat", "msdos", "exfat", "ntfs", "ntfs3", "fuseblk", "ext2", "ext3", "ext4", "hfsplus", "btrfs", "xfs", "f2fs")
MAX_PLAYLIST_COPIAT = 16 * 1024 * 1024
LOC_LIBER_DUPA = 32 * 1024 * 1024    # dupa copiere raman macar atatia octeti in memoria receptorului
CITIRE_PROBA = 64 * 1024
MAX_FISIERE_DOSAR = 50               # intr-un dosar, cele mai multe liste luate deodata
_FLUX = re.compile(r"^[ \t]*(https?|rtsp|rtmp|mms|udp)://\S", re.IGNORECASE | re.MULTILINE)
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
	return C.verificaDate, L.adaugaSiCere, I.DOSAR, lambda: I.textSursePline(_t)


def preiaText(text, fisier=CALE, verifica=None, adauga=None, dosar=None, e_plin=None, tine_minte=True):
	"""Sursele noi din text. -> {"adaugate": [nume], "gresite": n, "plin": bool, "playlist": bool, "mesaje": [text tradus]}.
	tine_minte=False (pagina web): randurile nu se noteaza, omul a ales fisierul acum."""
	if verifica is None:
		verifica, adauga, dosar, e_plin = _uneltele()
	rez = {"adaugate": [], "gresite": 0, "plin": False, "playlist": False, "mesaje": []}
	if ePlaylist(text):
		# chiar lista de canale (CRF, forum 1274): se pune in IPTV ca atare, din copia ei din dosarul listelor
		rez["playlist"] = True
		return preiaPlaylistText(text, fisier, verifica, adauga, dosar, e_plin, tine_minte, rez)
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
		rez["mesaje"].append(_t(e_plin() if callable(e_plin) else e_plin))
	return rez


# ------------------------------------------------------------------ listele de canale (CRF, forum 1274)

PROASPAT_S = 15     # un fisier mai nou de atat poate fi inca in urcare prin FTP: dosarul se priveste din nou la minutul urmator


def areFluxuri(text):
	"""O lista de canale (#EXTM3U / #EXTINF) cu macar o adresa de flux de internet; o lista de muzica cu cai de fisiere nu."""
	return ePlaylist(text) and _FLUX.search(text[:CITIRE_PROBA]) is not None


def numeFisierLista(nume):
	"""Numele copiei din dosarul listelor: numai litere, cifre, punct, minus si linie jos, cu .m3u / .m3u8 la sfarsit."""
	baza = os.path.basename(str(nume or "").replace("\\", "/"))
	baza = re.sub(r"[^A-Za-z0-9_.\-]", "_", baza).lstrip(".")[:60]
	if not baza.lower().endswith(EXTENSII_PLAYLIST):
		baza = (os.path.splitext(baza)[0][:55] or "lista") + ".m3u"
	return baza


def numeLista(cale):
	"""Numele aratat al sursei: numele fisierului, fara extensie."""
	baza = os.path.basename(str(cale or "").replace("\\", "/"))
	return os.path.splitext(baza)[0] or baza


def semnLista(cale, st):
	"""Semnul unui fisier incercat: numele, marimea si ora lui (acelasi pe orice loc de montare al stick-ului)."""
	return amprenta("lista:%s:%d:%d" % (os.path.basename(cale), st.st_size, int(st.st_mtime)))


def _scrieCopie(dosar, nume, octeti=None, sursa=None):
	"""Copia unei liste in <dosar>/liste/<nume> (0600, scriere atomica). -> calea, sau None (prea mare, fara loc, eroare)."""
	temp = None
	try:
		marime = len(octeti) if octeti is not None else os.path.getsize(sursa)
		if marime > MAX_PLAYLIST_COPIAT:
			return None
		tinta = os.path.join(dosar, "liste")
		if not os.path.isdir(tinta):
			os.makedirs(tinta, 0o700)
		if shutil.disk_usage(tinta).free - marime < LOC_LIBER_DUPA:
			print("[HdsIptvFisier] prea putin loc pentru copia listei %s" % nume)
			return None
		cale = os.path.join(tinta, nume)
		temp = cale + ".nou"
		fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0), 0o600)
		with os.fdopen(fd, "wb") as f:
			if octeti is not None:
				f.write(octeti)
			else:
				with open(sursa, "rb") as s:
					shutil.copyfileobj(s, f, 256 * 1024)
		os.replace(temp, cale)
		return cale
	except OSError as e:
		print("[HdsIptvFisier] copia listei %s: %s" % (nume, type(e).__name__))
		if temp is not None:
			try:
				os.unlink(temp)
			except OSError:
				pass
		return None


def _adaugaLista(cale, nume, verifica, adauga, rez):
	"""O lista de canale pusa in IPTV pe calea comuna (ca Adauga din ecran si din web). False cand lista surselor e plina."""
	sursa, eroare = verifica("m3u", {"adresa": cale, "nume": nume})
	if eroare:
		print("[HdsIptvFisier] %s: %s" % (cale, eroare))
		rez["gresite"] += 1
		return True
	if adauga(sursa) is None:
		rez["plin"] = True
		return False
	rez["adaugate"].append(sursa.get("nume") or nume)
	return True


def _mesajeLista(rez, e_plin):
	if rez["adaugate"]:
		nume = ", ".join(rez["adaugate"][:3]) + (", ..." if len(rez["adaugate"]) > 3 else "")
		rez["mesaje"].append(_t(T_LISTE_ADAUGATE) % {"nume": nume})
	if rez["plin"] and e_plin:
		rez["mesaje"].append(_t(e_plin() if callable(e_plin) else e_plin))


def preiaPlaylistText(text, fisier, verifica, adauga, dosar, e_plin, tine_minte=True, rez=None):
	"""Un text care e chiar o lista de canale (iptv.txt pus prin FTP sau fisierul ales in pagina web): copia lui in dosarul listelor,
	pusa in IPTV. Acelasi text nu se ia de doua ori (tine_minte=False in web: omul a ales fisierul acum)."""
	if rez is None:
		rez = {"adaugate": [], "gresite": 0, "plin": False, "playlist": True, "mesaje": []}
	nume_fisier = os.path.basename(str(fisier or "").replace("\\", "/")) or "iptv.txt"
	if not areFluxuri(text):
		rez["mesaje"].append(_t(T_PLAYLIST) % nume_fisier)
		return rez
	octeti = text.encode("utf-8", "replace")
	semn = amprenta("playlist:" + hashlib.sha256(octeti).hexdigest())
	tinute = citesteTinute(dosar) if tine_minte else []
	if semn in tinute:
		return rez
	cale = _scrieCopie(dosar, numeFisierLista(nume_fisier), octeti=octeti)
	if cale is None:
		rez["mesaje"].append(_t(T_PLAYLIST_PREA_MARE) % nume_fisier)
		return rez
	_adaugaLista(cale, numeLista(nume_fisier), verifica, adauga, rez)
	if tine_minte and not rez["plin"]:
		tinute.append(semn)
		scrieTinute(dosar, tinute)
	_mesajeLista(rez, e_plin)
	return rez


def preiaListe(fisiere, verifica=None, adauga=None, dosar=None, e_plin=None):
	"""Fisierele .m3u / .m3u8 gasite de PaznicListe: [(cale, copiaza, stat)]. Fiecare se incearca o singura data (semnLista); o
	lista fara adrese de internet se sare fara mesaj. -> {"adaugate", "gresite", "plin", "playlist", "mesaje"}."""
	if verifica is None:
		verifica, adauga, dosar, e_plin = _uneltele()
	rez = {"adaugate": [], "gresite": 0, "plin": False, "playlist": True, "mesaje": []}
	tinute = citesteTinute(dosar)
	vechi = set(tinute)
	schimbat = False
	for cale, copiaza, st in fisiere:
		semn = semnLista(cale, st)
		if semn in vechi:
			continue
		try:
			with open(cale, "rb") as f:
				inceput = f.read(CITIRE_PROBA)
		except OSError:
			continue
		tinute.append(semn)
		vechi.add(semn)
		schimbat = True
		if not areFluxuri(inceput.decode("utf-8", "replace")):
			print("[HdsIptvFisier] %s: nicio adresa de internet, sarit" % cale)
			continue
		tinta = cale
		if copiaza:
			tinta = _scrieCopie(dosar, numeFisierLista(cale), sursa=cale)
			if tinta is None:
				rez["mesaje"].append(_t(T_PLAYLIST_PREA_MARE) % os.path.basename(cale))
				continue
		if not _adaugaLista(tinta, numeLista(cale), verifica, adauga, rez):
			# lista surselor e plina: fisierul ramane neincercat, poate se elibereaza un loc pana la repornire
			tinute.remove(semn)
			break
	if schimbat:
		scrieTinute(dosar, tinute)
	_mesajeLista(rez, e_plin)
	return rez


def montariLocale(text):
	"""Radacinile stick-urilor si discurilor din /proc/mounts: numai sub /media/, numai sistemele de fisiere locale (FS_LOCALE)."""
	rez = []
	for rand in (text or "").splitlines():
		parti = rand.split()
		if len(parti) < 3 or parti[2] not in FS_LOCALE:
			continue
		punct = parti[1].replace("\\040", " ").replace("\\011", "\t").replace("\\012", "\n").replace("\\134", "\\")
		if punct.startswith("/media/") and punct not in rez:
			rez.append(punct)
	return rez


def _citesteMontari():
	try:
		with open("/proc/mounts", "rb") as f:
			return f.read(256 * 1024).decode("utf-8", "replace")
	except OSError:
		return ""


class PaznicListe(object):
	"""Se uita la ora dosarelor (LOC_FTP, radacinile stick-urilor) si le citeste numai cand s-a schimbat. copiaza=True (pentru un loc
	din memoria temporara) face copia in dosarul listelor."""

	def __init__(self, locuri=None, montari=None, preia=None, anunta=None, ceas=None):
		# locuri: [(dosar, copiaza)] fixe; montari(): radacinile stick-urilor de acum
		self.locuri = list(locuri) if locuri is not None else [(LOC_FTP, False)]
		self.montari = montari or (lambda: montariLocale(_citesteMontari()))
		self.preia = preia or preiaListe
		self.anunta = anunta
		self.ceas = ceas or __import__("time").time
		self.ore = {}

	def fisiereNoi(self):
		"""[(cale, copiaza, stat)] din dosarele a caror ora s-a schimbat de la privirea trecuta."""
		import stat as S
		acum = self.ceas()
		rez, ore, vazute = [], {}, set()
		for dosar, copiaza in self.locuri + [(m, False) for m in self.montari()]:
			if dosar in vazute:
				continue
			vazute.add(dosar)
			try:
				st = os.stat(dosar)
			except OSError:
				continue
			# alt stick pe acelasi loc de montare are alt dispozitiv: se priveste din nou
			ora = (st.st_mtime_ns, st.st_ino, st.st_dev)
			if self.ore.get(dosar) == ora:
				ore[dosar] = ora
				continue
			try:
				nume = sorted(os.listdir(dosar))
			except OSError:
				continue
			din_nou, luate = False, 0
			for n in nume:
				if n.startswith(".") or not n.lower().endswith(EXTENSII_PLAYLIST):
					continue
				cale = os.path.join(dosar, n)
				try:
					stf = os.stat(cale)
				except OSError:
					continue
				if not S.S_ISREG(stf.st_mode):
					continue
				# un fisier cu ora din viitor (ceasul receptorului inca nepus) nu e socotit in urcare
				if 0 <= acum - stf.st_mtime < PROASPAT_S:
					din_nou = True
					continue
				if stf.st_size == 0:
					continue
				rez.append((cale, copiaza, stf))
				luate += 1
				if luate >= MAX_FISIERE_DOSAR:
					break
			if not din_nou:
				ore[dosar] = ora
		# dosarele care lipsesc acum (stick scos) se uita: la intoarcere se privesc din nou
		self.ore = ore
		return rez

	def verifica(self):
		fisiere = self.fisiereNoi()
		if not fisiere:
			return None
		try:
			rez = self.preia(fisiere)
		except Exception as e:
			print("[HdsIptvFisier] listele de canale: %r" % (e,))
			return None
		if self.anunta and rez["mesaje"]:
			self.anunta(" ".join(rez["mesaje"]))
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


# ------------------------------------------------------------------ acordul omului pentru listele gasite (space71, 19.11.2026)
# Firul interfetei atinge aici numai memoria: _cereri, _inLucru, _refuzate, cozile _deFacut si _gata (deque, fara zavor). Discul
# (stat, listdir, inceputul listelor de pe stick, liste-refuzate.json) il atinge numai firul de fundal _lucreaza, cate unul odata,
# pornit fara asteptare. Singura scriere ramasa pe firul interfetei e fisier-preluat.json dupa adaugarea unei liste aprobate
# (in /etc/enigma2, nu pe stick), ca la fiecare lista luata pe HEAD; asa fisierul are un singur scriitor.

T_AUTOMAT = N_("Preia automat listele M3U găsite")
T_NOTA_AUTOMAT = N_("Pe Nu, o listă de canale nouă găsită în /etc/enigma2 sau pe un stick așteaptă acordul tău pe televizor sau în pagina IPTV.")
T_ACORD = N_("Am găsit lista de canale %s. O pun în IPTV?")
T_DA = N_("Da, pune-o în IPTV")
T_NU = N_("Nu, las-o pe disc")
T_TARZIU = N_("Mai târziu")
T_TRIMIS = N_("Lista %s se verifică și se pune în IPTV.")
T_REFUZAT = N_("Lista %s rămâne pe disc, fără IPTV.")
T_REZOLVAT = N_("Cererea a fost deja rezolvată.")
T_SCHIMBATA = N_("Lista %s s-a schimbat sau nu mai e acolo. Dacă e tot acolo, o vezi din nou aici în cel mult un minut.")
T_GRESITA = N_("Lista %s nu s-a putut pune în IPTV.")

MAX_CERERI = 50
NUME_REFUZATE = "liste-refuzate.json"
PAS_FIR_MS = 500          # cat lucreaza firul de fundal, rezultatele se culeg la atat
PAS_FIR_LUNG_MS = 5000    # dupa PRIVIRI_REPEDE culegeri (un stick care nu raspunde), mai rar
PRIVIRI_REPEDE = 20

_cereri = {}              # jeton -> cererea in asteptare (numai firul interfetei)
_inLucru = {}             # jeton -> cererea aprobata, verificata acum de fir
_intrebate = set()        # jetoanele intrebate deja pe televizor
_refuzate = set()         # semnele refuzate in aceasta sesiune (firul le scrie in liste-refuzate.json)
_luate = set()            # semnele listelor aprobate si incercate in aceasta sesiune (o cautare veche nu le mai cere)
_uita = [True]            # firul trebuie sa priveasca din nou toate dosarele (trecere pe Nu, cerere lasata deoparte)
_intrebareDeschisa = [False]
_deFacut = deque()        # sarcinile firului de fundal (puse numai de firul interfetei)
_gata = deque()           # rezultatele lui (puse de fir, luate numai de firul interfetei)
_fir = [None]
_ceasFir = [None]
_priviri = [0]
_cautaFir = [None]        # PaznicListe al firului de fundal; firul interfetei nu-l atinge


def optiuneAutomata():
	"""Setarea Da/Nu, ca orice config.*: salvata de mecanismul obisnuit al imaginii."""
	from Components.config import config, ConfigSubsection, ConfigYesNo
	if not hasattr(config, "plugins"):
		config.plugins = ConfigSubsection()
	if not hasattr(config.plugins, "hds_iptv_fisiere"):
		config.plugins.hds_iptv_fisiere = ConfigSubsection()
	if not hasattr(config.plugins.hds_iptv_fisiere, "automat"):
		config.plugins.hds_iptv_fisiere.automat = ConfigYesNo(default=True)
	return config.plugins.hds_iptv_fisiere.automat


def preluareAutomata():
	"""True = purtarea de pe HEAD (si cand setarea nu se poate citi)."""
	try:
		return bool(optiuneAutomata().value)
	except Exception:
		return True


def seteazaPreluare(da):
	"""TV si web: valoarea si save() ale elementului; fisierul setarilor il scrie mecanismul obisnuit."""
	el = optiuneAutomata()
	if el.value != bool(da):
		el.value = bool(da)
	el.save()
	if el.value:
		_cereri.clear()
		_uita[0] = True
	else:
		_cereCautare()


def _idFisier(st):
	return (st.st_size, getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9)), st.st_ino, st.st_dev)


def _dosar():
	return _uneltele()[2]


def _anunta(text):
	if text:
		_anuntaPeTelevizor(text)


# ---- firul de fundal: nu atinge eTimer, config, Notifications sau _()

def _citesteRefuzate(dosar):
	try:
		with open(os.path.join(dosar, NUME_REFUZATE), "rb") as f:
			date = json.loads(f.read().decode("utf-8"))
		return [x for x in date if isinstance(x, str)] if isinstance(date, list) else []
	except (OSError, ValueError):
		return []


def _noteazaRefuzat(dosar, semn):
	"""Numai pe firul de fundal (singurul care citeste si scrie liste-refuzate.json); scriere atomica, 0600."""
	refuzate = _citesteRefuzate(dosar)
	if semn in refuzate:
		return
	refuzate = (refuzate + [semn])[-MAX_TINUTE:]
	try:
		if not os.path.isdir(dosar):
			os.makedirs(dosar, 0o700)
		cale = os.path.join(dosar, NUME_REFUZATE)
		fd = os.open(cale + ".nou", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
		with os.fdopen(fd, "wb") as f:
			f.write(json.dumps(refuzate).encode("utf-8"))
		os.replace(cale + ".nou", cale)
	except OSError as e:
		print("[HdsIptvFisier] nu am putut tine minte refuzul: %s" % type(e).__name__)


def _cautaInFir(dosar):
	"""Listele noi din dosarele schimbate: [("gasit", cererea)]. Scrie numai liste-refuzate.json (nimic aici)."""
	p = _cautaFir[0]
	if p is None:
		p = _cautaFir[0] = PaznicListe()
	tinute = set(citesteTinute(dosar)) | set(_citesteRefuzate(dosar))
	rez = []
	for cale, _copiaza, st in p.fisiereNoi():
		semn = semnLista(cale, st)
		if semn in tinute:
			continue
		try:
			with open(cale, "rb") as f:
				inceput = f.read(CITIRE_PROBA)
		except OSError:
			continue
		if not areFluxuri(inceput.decode("utf-8", "replace")):
			continue
		rez.append(("gasit", {"cale": cale, "nume": numeLista(cale), "semn": semn, "id": _idFisier(st)}))
	return rez


def _verificaInFir(cerere):
	"""Fisierul aprobat e tot acela (marime, ora, inod)? -> stat sau None."""
	import stat as S
	try:
		st = os.stat(cerere["cale"])
	except OSError:
		return None
	if not S.S_ISREG(st.st_mode) or _idFisier(st) != cerere["id"]:
		return None
	return st


def _lucreaza():
	while True:
		try:
			sarcina = _deFacut.popleft()
		except IndexError:
			return
		try:
			if sarcina[0] == "cauta":
				_gata.extend(_cautaInFir(sarcina[1]))
			elif sarcina[0] == "verifica":
				_gata.append(("verificat", sarcina[1], _verificaInFir(sarcina[1])))
			elif sarcina[0] == "uita" and _cautaFir[0] is not None:
				_cautaFir[0].ore = {}
			elif sarcina[0] == "refuz":
				_noteazaRefuzat(sarcina[1], sarcina[2])
		except Exception as e:
			print("[HdsIptvFisier] firul listelor: %r" % (e,))
			if sarcina[0] == "verifica":
				_gata.append(("verificat", sarcina[1], None))


# ---- firul interfetei: numai memorie (si fisier-preluat.json, ca pe HEAD)

def _pornesteFir():
	"""Porneste firul de fundal daca nu e viu si ceasul care ii culege rezultatele. Nu asteapta niciodata firul."""
	f = _fir[0]
	if (f is None or not f.is_alive()) and _deFacut:
		f = threading.Thread(target=_lucreaza, name="HdsIptvListe")
		f.daemon = True
		try:
			f.start()
		except RuntimeError as e:
			print("[HdsIptvFisier] firul listelor nu porneste: %r" % (e,))
			return
		_fir[0] = f
	_priviri[0] = 0
	if _ceasFir[0] is not None:
		_ceasFir[0].start(PAS_FIR_MS, True)


def _culege():
	"""Ceasul firului interfetei: ia rezultatele; reporneste firul daca au ramas sarcini."""
	f = _fir[0]
	viu = f is not None and f.is_alive()
	_aplica()
	if not viu:
		if _deFacut:
			_pornesteFir()
		return
	_priviri[0] += 1
	if _ceasFir[0] is not None:
		_ceasFir[0].start(PAS_FIR_MS if _priviri[0] < PRIVIRI_REPEDE else PAS_FIR_LUNG_MS, True)


def _cereCautare():
	"""Pe Nu, la fiecare tic: o privire la dosare, pe fir. Cat timp firul inca lucreaza (stick lent), nu se cere alta."""
	f = _fir[0]
	if f is not None and f.is_alive():
		return
	if not _deFacut:
		try:
			dosar = _dosar()
		except Exception as e:
			print("[HdsIptvFisier] dosarul listelor: %r" % (e,))
			return
		if _uita[0]:
			# dupa Da sau dupa o cerere lasata deoparte, firul nu are voie sa sara dosarele "neschimbate"
			_uita[0] = False
			_deFacut.append(("uita",))
		_deFacut.append(("cauta", dosar))
	_pornesteFir()


def _aplica(unelte=None):
	# listele aprobate din acest apel se noteaza in fisier-preluat.json o singura data, la sfarsit (o citire, o scriere, ca HEAD)
	de_tinut = {}
	while True:
		try:
			r = _gata.popleft()
		except IndexError:
			break
		try:
			if r[0] == "gasit":
				_adaugaCerere(r[1])
			elif r[0] == "verificat":
				_dupaVerificare(r[1], r[2], unelte, de_tinut)
		except Exception as e:
			print("[HdsIptvFisier] cererea listei: %r" % (e,))
	for dosar, semne in de_tinut.items():
		_tine(dosar, semne)
	_intreaba()


def _adaugaCerere(c):
	if preluareAutomata():
		_uita[0] = True
		return
	if c["semn"] in _refuzate or c["semn"] in _luate:
		return
	for j, v in list(_cereri.items()) + list(_inLucru.items()):
		if v["semn"] == c["semn"] and v["cale"] != c["cale"]:
			# acelasi semn in alt loc (stick si /etc/enigma2): HEAD il ia o singura data, deci si cererea e una
			return
		if v["cale"] == c["cale"]:
			if v["id"] == c["id"]:
				return
			# fisierul schimbat e o cerere noua; cea veche nu mai poate fi aprobata
			_cereri.pop(j, None)
	if len(_cereri) >= MAX_CERERI:
		_uita[0] = True
		return
	c = dict(c, jeton=os.urandom(8).hex())
	_cereri[c["jeton"]] = c


def _tine(dosar, semne):
	"""Semnele listelor luate, adaugate in fisier-preluat.json dintr-o data: o citire si cel mult o scriere."""
	tinute = citesteTinute(dosar)
	noi = []
	for x in semne:
		# si repetitiile din acelasi lot (acelasi nume, marime si ora in /etc/enigma2 si pe stick): o data, in ordine
		if x not in tinute and x not in noi:
			noi.append(x)
	if noi:
		scrieTinute(dosar, tinute + noi)


def _dupaVerificare(c, st, unelte=None, de_tinut=None):
	if _inLucru.get(c["jeton"]) is c:
		del _inLucru[c["jeton"]]
	if st is None:
		_anunta(_t(T_SCHIMBATA) % c["nume"])
		_deFacut.append(("uita",))
		_pornesteFir()
		return
	verifica, adauga, dosar, e_plin = unelte or _uneltele()
	rez = {"adaugate": [], "gresite": 0, "plin": False, "playlist": True, "mesaje": []}
	if not _adaugaLista(c["cale"], c["nume"], verifica, adauga, rez):
		# lista surselor e plina: cererea ramane, ca pe HEAD fisierul ramane neincercat
		_cereri[c["jeton"]] = c
	else:
		_luate.add(c["semn"])
		if de_tinut is None:
			_tine(dosar, [c["semn"]])
		else:
			de_tinut.setdefault(dosar, []).append(c["semn"])
		if rez["gresite"]:
			rez["mesaje"].append(_t(T_GRESITA) % c["nume"])
	_mesajeLista(rez, e_plin)
	_anunta(" ".join(rez["mesaje"]))


def raspunde(jeton, da, unelte=None):
	"""TV si web, pe firul interfetei. Jetonul se consuma o singura data (pop); al doilea raspuns afla ca s-a rezolvat."""
	c = _cereri.pop(jeton, None) if isinstance(jeton, str) else None
	if c is None:
		return {"result": False, "message": _t(T_REZOLVAT)}
	if not da:
		# numai memorie aici; firul scrie refuzul in liste-refuzate.json
		_refuzate.add(c["semn"])
		_deFacut.append(("refuz", (unelte or _uneltele())[2], c["semn"]))
		_pornesteFir()
		return {"result": True, "message": _t(T_REFUZAT) % c["nume"]}
	_inLucru[c["jeton"]] = c
	_deFacut.append(("verifica", c))
	_pornesteFir()
	return {"result": True, "message": _t(T_TRIMIS) % c["nume"]}


def stareListe():
	"""Ce arata televizorul si pagina web: setarea si cererile, numai din memorie (numele listei, fara cale sau adresa)."""
	automat = preluareAutomata()
	cereri = [] if automat else [{"jeton": j, "nume": c["nume"], "text": _t(T_ACORD) % c["nume"]}
		for j, c in list(_cereri.items())]
	return {"automat": automat, "cereri": cereri, "in_lucru": len(_inLucru)}


def _intreaba():
	"""O singura intrebare deschisa pe televizor; fiecare cerere se intreaba o data (apoi ramane in ecranul IPTV si pe web)."""
	if _intrebareDeschisa[0] or not _cereri or preluareAutomata():
		return
	noi = [c for j, c in list(_cereri.items()) if j not in _intrebate]
	if not noi:
		return
	c = noi[0]
	_intrebate.add(c["jeton"])
	try:
		from Tools import Notifications
		from Screens.MessageBox import MessageBox
	except ImportError:
		return

	def raspuns(ales=None):
		_intrebareDeschisa[0] = False
		if ales in ("da", "nu"):
			_anunta(raspunde(c["jeton"], ales == "da")["message"])
		_intreaba()
	_intrebareDeschisa[0] = True
	try:
		Notifications.AddNotificationWithCallback(raspuns, MessageBox, _t(T_ACORD) % c["nume"], type=MessageBox.TYPE_YESNO,
			list=[(_t(T_DA), "da"), (_t(T_NU), "nu"), (_t(T_TARZIU), "tarziu")])
	except Exception as e:
		_intrebareDeschisa[0] = False
		print("[HdsIptvFisier] intrebarea: %r" % (e,))


_paznic = None
_paznicListe = None
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
	try:
		if _paznicListe is not None:
			if preluareAutomata():
				_cereri.clear()
				_uita[0] = True
				_paznicListe.verifica()
			else:
				# pe Nu firul interfetei nu priveste dosarele: le priveste firul de fundal
				_cereCautare()
	except Exception as e:
		print("[HdsIptvFisier] listele de canale: %r" % (e,))


def porneste():
	"""La pornirea receptorului (HdsIptvLucru.porneste), si fara surse: o privire pe minut la fisier si la dosarele listelor."""
	global _paznic, _paznicListe, _ceas
	if _ceas is not None:
		return
	try:
		from enigma import eTimer
	except ImportError:
		return
	try:
		optiuneAutomata()
	except Exception as e:
		print("[HdsIptvFisier] setarea: %r" % (e,))
	_paznic = Paznic(anunta=_anuntaPeTelevizor)
	_paznicListe = PaznicListe(anunta=_anuntaPeTelevizor)
	_ceasFir[0] = eTimer()
	_ceasFir[0].callback.append(_culege)
	_ceas = eTimer()
	_ceas.callback.append(_tic)
	_ceas.start(PRIMA_S * 1000, True)
