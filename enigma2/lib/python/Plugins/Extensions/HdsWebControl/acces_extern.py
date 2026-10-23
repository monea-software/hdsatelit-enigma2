# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# acces_extern.py: adresele de flux pentru playerele externe din reteaua de acasa (VLC, Kodi cu PVR IPTV Simple, mai
# tarziu Emby), folosite de playlisturile M3U descarcate din interfata web (tv_web.py: POST /api/tv-m3u, fluxul
# GET /tv-extern/<cheie>/<canal>.ts).
#
# DE CE O CHEIE IN ADRESA: un player extern nu trimite cookie-ul browserului si nici antetul CSRF, iar jetonul API
# general (care deschide tot API-ul) nu are voie sa ajunga intr-un fisier. Fiecare playlist primeste deci o cheie a
# lui, care deschide NUMAI fluxul canalelor din acel playlist, nimic altceva (nicio comanda, nicio setare).
#
# SECURITATEA:
# - cine: numai din reteaua locala (aceeasi poarta ca tot serverul), si numai cine are fisierul playlistului;
# - ce: fluxul canalelor din playlist; nimic altceva. Aceleasi limite ca transmisia spre browser (cate sesiuni odata,
#   paza memoriei driverului, televizorul si inregistrarile au prioritate), iar cu "Permite transmisia" oprit nu merge;
# - cat timp: playlistul unui canal DURATA_CANAL_S (7 zile), un playlist exportat DURATA_LISTA_S (30 de zile); cheile
#   "pe aparat" (pentru un server ca Emby, care are nevoie de adrese care nu expira) au durata 0 = pana la revocare;
# - pe disc numai amprenta cheii (sha256), nu cheia: fisierul de setari copiat nu da adrese care merg;
# - orice cheie se revoca din pagina TV in browser; cel mult MAX_CHEI chei (cea mai veche iese); o cheie gresita nu
#   spune daca exista sau nu.
#
# CHEILE DE APARAT (aparate_web.py): un aparat din casa care tine o lista de canale pe
# termen lung (un player cu lista IPTV, un server media, un televizor cu aplicatie IPTV) primeste o cheie "aparat", cu un
# nume dat de om. Cheia nu expira; adresele ei sunt /tv-extern/<cheie>/canale.m3u, /tv-extern/<cheie>/ghid.xml,
# /tv-extern/<cheie>/sigla/<nume>.png si fluxul oricarui canal TV (canale None). `sursa` spune de unde vine lista
# (toate canalele TV, un buchet, un satelit sau filtrul din /canale) si se citeste din nou la fiecare cerere. Cel mult
# MAX_APARATE aparate (al MAX_APARATE+1-lea se refuza cu motivul); cand se umple MAX_CHEI iese cea mai veche cheie care
# NU e de aparat (un aparat nu dispare niciodata pe tacute). Ultima folosire a unui aparat se scrie pe disc cel mult o
# data la FOLOSIT_SALVARE_S (lista aparatelor o arata si dupa repornire, fara scrieri la fiecare cerere). Secretul unei
# chei de aparat nu se pastreaza nici el: adresele se arata o singura data, la adaugare.
#
# FIRUL: totul pe firul enigma2, apeluri scurte; scrierea fisierului numai la creare si la revocare. Fisierul nu importa
# nimic din enigma2.

import binascii
import hashlib
import hmac
import io
import json
import os
import re
import time

FISIER = "/etc/enigma2/hds-acces-flux.json"
DURATA_CANAL_S = 7 * 86400
DURATA_LISTA_S = 30 * 86400
MAX_CHEI = 64
MAX_CANALE = 2000
MAX_APARATE = 16
MAX_NUME_APARAT = 40
FOLOSIT_SALVARE_S = 3600
FELURI = ("canal", "lista", "aparat")
_RE_CHEIE = re.compile(r"^([0-9a-f]{8})([A-Za-z0-9_-]{24,64})$")
_RE_NUME_FISIER = re.compile(r"[^A-Za-z0-9._-]+")


def _t(text):
	"""Traducerea enigma2 (builtins._) la folosire, ca in tv_web.py; pe PC, fara ea, textul asa cum e."""
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


def _amprenta(secret):
	return hashlib.sha256(secret.encode("ascii")).hexdigest()


class Cheie(object):
	__slots__ = ("id", "amprenta", "fel", "canale", "nume", "proprietar", "proprietar_nume", "creat", "expira", "folosit",
		"sursa", "folosit_salvat")

	def __init__(self, id_, amprenta, fel, canale, nume, proprietar, proprietar_nume, creat, expira, sursa=None,
			folosit=0):
		self.id = id_
		self.amprenta = amprenta
		self.fel = fel
		self.canale = canale            # lista de referinte, sau None = orice canal (cheie pe aparat)
		self.nume = nume
		self.proprietar = proprietar    # cheia browserului care a facut-o ("b:<id>" sau "l:<adresa>")
		self.proprietar_nume = proprietar_nume
		self.creat = creat
		self.expira = expira            # 0 = pana la revocare
		self.sursa = sursa              # numai la aparate: de unde vine lista lui (aparate_web.py), cu "eticheta"
		self.folosit = folosit          # ultima folosire (la aparate si pe disc, cel mult o data la FOLOSIT_SALVARE_S)
		self.folosit_salvat = folosit   # ce e pe disc

	def dict(self):
		d = {"id": self.id, "amprenta": self.amprenta, "fel": self.fel, "canale": self.canale, "nume": self.nume,
			"proprietar": self.proprietar, "proprietar_nume": self.proprietar_nume, "creat": int(self.creat),
			"expira": int(self.expira)}
		if self.fel == "aparat":
			d["sursa"] = self.sursa
			d["folosit"] = int(self.folosit)
		return d

	def descriere(self):
		"""Pentru pagina: fara amprenta si fara lista intreaga de canale."""
		d = {"id": self.id, "fel": self.fel, "nume": self.nume, "canale": len(self.canale) if self.canale is not None else None,
			"browser": self.proprietar_nume, "creat": int(self.creat), "expira": int(self.expira), "folosit": int(self.folosit)}
		if self.fel == "aparat":
			d["sursa"] = (self.sursa or {}).get("eticheta") or ""
		return d


class Magazin(object):
	def __init__(self, cale=FISIER, ceas=time.time, aleator=os.urandom):
		self._cale = cale
		self._ceas = ceas
		self._aleator = aleator
		self._chei = None

	# ------------------------------------------------------------ discul
	def _incarca(self):
		if self._chei is not None:
			return
		self._chei = {}
		try:
			with io.open(self._cale, encoding="utf-8") as f:
				date = json.load(f)
		except (IOError, OSError, ValueError):
			return
		for d in (date.get("chei") or [])[:MAX_CHEI] if isinstance(date, dict) else []:
			try:
				sursa = d.get("sursa")
				c = Cheie(str(d["id"]), str(d["amprenta"]), str(d["fel"]), d.get("canale"), str(d.get("nume") or ""),
					str(d.get("proprietar") or ""), str(d.get("proprietar_nume") or ""), float(d.get("creat") or 0),
					float(d.get("expira") or 0), sursa if isinstance(sursa, dict) else None, float(d.get("folosit") or 0))
			except (KeyError, TypeError, ValueError):
				continue
			if c.fel in FELURI and re.match(r"^[0-9a-f]{8}$", c.id) and (c.canale is None or isinstance(c.canale, list)):
				self._chei[c.id] = c

	def _salveaza(self):
		date = {"versiune": 1, "chei": [c.dict() for c in self._chei.values()]}
		nou = self._cale + ".nou"
		try:
			with io.open(nou, "w", encoding="utf-8") as f:
				json.dump(date, f, ensure_ascii=False)
			os.chmod(nou, 0o600)
			os.replace(nou, self._cale)
			for c in self._chei.values():
				c.folosit_salvat = c.folosit
			return True
		except (IOError, OSError) as e:
			print("[HdsWebControl] acces_extern: nu pot scrie %s: %s" % (self._cale, e))
			return False

	# ------------------------------------------------------------ cheile
	def curata(self):
		self._incarca()
		acum = self._ceas()
		vechi = [i for i, c in self._chei.items() if c.expira and c.expira <= acum]
		for i in vechi:
			del self._chei[i]
		return bool(vechi)

	def creeaza(self, fel, canale, proprietar, proprietar_nume, nume, durata_s=None, sursa=None):
		"""-> (textul cheii pentru adresa, Cheie). `canale` = lista de referinte (curatate de cel care cheama) sau None
		numai pentru fel "aparat" (`sursa` = de unde vine lista lui; creeazaAparat verifica numele si limita)."""
		if fel not in FELURI:
			raise ValueError("fel necunoscut")
		if fel != "aparat" and not canale:
			raise ValueError("fara canale")
		self._incarca()
		self.curata()
		while len(self._chei) >= MAX_CHEI:
			# cea mai veche cheie care nu e de aparat (aparatele au limita lor, MAX_APARATE < MAX_CHEI)
			altele = [c for c in self._chei.values() if c.fel != "aparat"] or list(self._chei.values())
			cea_veche = min(altele, key=lambda c: c.creat)
			del self._chei[cea_veche.id]
		id_ = binascii.hexlify(self._aleator(4)).decode("ascii")
		while id_ in self._chei:
			id_ = binascii.hexlify(self._aleator(4)).decode("ascii")
		secret = binascii.b2a_base64(self._aleator(18)).decode("ascii").strip().replace("+", "-").replace("/", "_")
		if durata_s is None:
			durata_s = DURATA_CANAL_S if fel == "canal" else (DURATA_LISTA_S if fel == "lista" else 0)
		acum = self._ceas()
		c = Cheie(id_, _amprenta(secret), fel, list(canale)[:MAX_CANALE] if canale is not None else None,
			(nume or "")[:80], proprietar or "", (proprietar_nume or "")[:60], acum, acum + durata_s if durata_s else 0,
			dict(sursa) if (fel == "aparat" and isinstance(sursa, dict)) else None)
		self._chei[id_] = c
		self._salveaza()
		return id_ + secret, c

	def verifica(self, text, ref, noteaza=True):
		"""-> (Cheie, None) daca `text` e o cheie valabila care deschide canalul `ref` (referinta curatata), altfel
		(None, motiv). Motivul nu spune daca cheia exista. noteaza=False (cererea HEAD a unui player): fara ora folosirii,
		pentru ca nu porneste nimic."""
		m = _RE_CHEIE.match(text or "")
		if not m:
			return None, _t("Adresa nu e bună.")
		self._incarca()
		c = self._chei.get(m.group(1))
		if c is None or not hmac.compare_digest(c.amprenta, _amprenta(m.group(2))):
			return None, _t("Adresa nu e bună sau a fost revocată.")
		if c.expira and c.expira <= self._ceas():
			return None, _t("Adresa a expirat. Descarcă din nou playlistul din interfața web a receptorului.")
		if c.canale is not None and ref not in c.canale:
			return None, _t("Canalul nu e în acest playlist.")
		if noteaza:
			self._noteaza(c)
		return c, None

	def _noteaza(self, c):
		"""Ultima folosire: in memorie mereu; pe disc numai la aparate, cel mult o data la FOLOSIT_SALVARE_S."""
		c.folosit = self._ceas()
		if c.fel == "aparat" and c.folosit - c.folosit_salvat >= FOLOSIT_SALVARE_S:
			self._salveaza()

	# ------------------------------------------------------------ aparatele
	def aparat(self, id_):
		self._incarca()
		c = self._chei.get(str(id_ or ""))
		return c if (c is not None and c.fel == "aparat") else None

	def _numeOcupat(self, nume, afara_de=None):
		cheie = nume.casefold()
		return any(c.fel == "aparat" and c.id != afara_de and c.nume.casefold() == cheie for c in self._chei.values())

	def creeazaAparat(self, nume, sursa, proprietar, proprietar_nume):
		"""Cheia unui aparat din casa. -> (textul cheii, Cheie, None) sau (None, None, motivul pentru om)."""
		nume = curataNume(nume)
		if not nume:
			return None, None, _t("Scrie un nume pentru aparat.")
		if not isinstance(sursa, dict) or not sursa.get("fel"):
			return None, None, _t("Alege canalele aparatului.")
		self._incarca()
		if sum(1 for c in self._chei.values() if c.fel == "aparat") >= MAX_APARATE:
			return None, None, _t("Sunt deja %d aparate. Revocă unul pe care nu-l mai folosești.") % MAX_APARATE
		if self._numeOcupat(nume):
			return None, None, _t("Un aparat cu acest nume există deja. Alege alt nume.")
		text, c = self.creeaza("aparat", None, proprietar, proprietar_nume, nume, durata_s=0, sursa=sursa)
		return text, c, None

	def redenumeste(self, id_, nume):
		"""Numai aparatele. -> (True, None) sau (False, motivul)."""
		c = self.aparat(id_)
		if c is None:
			return False, _t("Aparatul nu mai există.")
		nume = curataNume(nume)
		if not nume:
			return False, _t("Scrie un nume pentru aparat.")
		if self._numeOcupat(nume, afara_de=c.id):
			return False, _t("Un aparat cu acest nume există deja. Alege alt nume.")
		c.nume = nume
		self._salveaza()
		return True, None

	def verificaAparat(self, text, noteaza=True):
		"""-> (Cheie, None) daca `text` e cheia unui aparat, altfel (None, motiv); o cheie de canal sau de lista primeste
		acelasi motiv ca una gresita (nu se afla ce chei exista). noteaza=False (HEAD): fara ora folosirii."""
		m = _RE_CHEIE.match(text or "")
		if not m:
			return None, _t("Adresa nu e bună.")
		self._incarca()
		c = self._chei.get(m.group(1))
		if c is None or c.fel != "aparat" or not hmac.compare_digest(c.amprenta, _amprenta(m.group(2))):
			return None, _t("Adresa nu e bună sau a fost revocată.")
		if noteaza:
			self._noteaza(c)
		return c, None

	def aparate(self):
		self._incarca()
		return [c.descriere() for c in sorted((c for c in self._chei.values() if c.fel == "aparat"),
			key=lambda c: (c.nume.casefold(), c.creat))]

	def revoca(self, id_):
		self._incarca()
		if self._chei.pop(str(id_ or ""), None) is None:
			return False
		self._salveaza()
		return True

	def revocaAleProprietarului(self, proprietar):
		self._incarca()
		ale = [i for i, c in self._chei.items() if c.proprietar == proprietar]
		for i in ale:
			del self._chei[i]
		if ale:
			self._salveaza()
		return len(ale)

	def lista(self, cu_aparate=True):
		self._incarca()
		self.curata()
		return [c.descriere() for c in sorted(self._chei.values(), key=lambda c: -c.creat)
			if cu_aparate or c.fel != "aparat"]


def curataNume(text, maxim=MAX_NUME_APARAT):
	"""Numele unui aparat dat de om: fara caractere de control, spatiile stranse, cel mult `maxim` semne."""
	text = "".join(ch for ch in str(text or "") if ch >= " " and not ("\x7f" <= ch <= "\x9f"))
	return " ".join(text.split())[:maxim].strip()


# ---------------------------------------------------------------- adresele si fisierul M3U

def codCanal(ref):
	"""Referinta in adresa: ':' -> '_' (litere, cifre si '_'). Invers: refDinCod."""
	return ref.replace(":", "_")


def refDinCod(cod):
	if not cod or not re.match(r"^[0-9A-Fa-f_]{10,96}$", cod):
		return None
	return cod.replace("_", ":")


_RE_GAZDA = re.compile(r"^(\[[0-9A-Fa-f:.]+\]|[A-Za-z0-9.-]{1,253})(:[0-9]{1,5})?$")


def gazdaBuna(gazda):
	return bool(gazda) and bool(_RE_GAZDA.match(gazda))


def adresaFlux(gazda, cheie_text, ref):
	return "http://%s/tv-extern/%s/%s.ts" % (gazda, cheie_text, codCanal(ref))


_RE_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def _curataText(text, maxim=120):
	"""Nume si grupe pentru M3U: fara caractere de control, fara virgule (playerele taie randul la ultima) si ghilimele."""
	text = _RE_CONTROL.sub("", text or "")
	return text.replace(",", " ").replace('"', "'").strip()[:maxim]


def textM3u(gazda, cheie_text, canale, grup=""):
	"""`canale` = [(ref, nume)]. #EXTM3U, apoi pentru fiecare canal #EXTINF cu numele si grupul, si adresa."""
	grup = _curataText(grup, 80)
	randuri = ["#EXTM3U"]
	for ref, nume in canale:
		nume = _curataText(nume) or ref
		extra = (' group-title="%s"' % grup) if grup else ""
		randuri.append('#EXTINF:-1 tvg-id="%s" tvg-name="%s"%s,%s' % (codCanal(ref), nume, extra, nume))
		randuri.append(adresaFlux(gazda, cheie_text, ref))
	return "\n".join(randuri) + "\n"


_DIACRITICE = {"ă": "a", "â": "a", "î": "i", "ș": "s", "ş": "s", "ț": "t", "ţ": "t", "Ă": "A", "Â": "A", "Î": "I",
	"Ș": "S", "Ş": "S", "Ț": "T", "Ţ": "T", "ä": "a", "ö": "o", "ü": "u", "Ä": "A", "Ö": "O", "Ü": "U", "ß": "ss",
	"°": ""}


def numeFisier(parti, implicit="hdsatelit"):
	"""Numele fisierului din bucati (canalul, satelitul, filtrele): litere ASCII, cifre, '.', '-', '_', cu .m3u."""
	bucati = []
	for p in parti:
		text = "".join(_DIACRITICE.get(ch, ch) for ch in (p or ""))
		text = _RE_NUME_FISIER.sub("-", text).strip("-._")
		if text:
			bucati.append(text)
	nume = "-".join(bucati)[:100].strip("-._") or implicit
	return nume + ".m3u"


_MAGAZIN = []


def magazin():
	if not _MAGAZIN:
		_MAGAZIN.append(Magazin())
	return _MAGAZIN[0]
