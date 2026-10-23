# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsTeletextCopie.py: copiile de teletext ale canalelor si setarile teletextului.
#
# Nucleul strange in fundal toate paginile si subpaginile canalului care merge (lib/dvb/hdsteletext.cpp). Aici:
#  - urmaritorul: cand caruselul e complet (cel putin 40 s pe canal si fiecare pagina primita de doua ori, adica
#    caruselul a trecut tot de doua ori; sau 75 s nicio pagina noua, pentru caruselele mari si paginile rare), copia
#    paginilor se scrie comprimata (zlib) pe disc, daca "Copie automata" e pornita si copia canalului lipseste sau are
#    peste 6 ore. Integrarea 0.3.0: regula veche (25 s nicio SUBPAGINA noua) nu se indeplinea pe caruselele mari (24 HORAS,
#    578 de subpagini, nicio copie in 5 minute; ARD nimic in 85 s; ZDF abia dupa ~4,5 minute);
#  - locul: pe discul sau stickul montat (/media/hdd, /media/usb), altfel in /etc/enigma2; marginit la spatiul ales,
#    copiile cele mai vechi pleaca primele. /media/hdd e de obicei o legatura spre /run/media/...: montarea se verifica
#    pe calea reala (ismount pe legatura da False, iar copiile ajungeau pe memoria interna);
#  - lista copiilor (canalul, data, paginile), incarcarea unei copii in nucleu (eHdsTeletext.copie: 0 televizorul,
#    1 pagina web), fara tuner;
#  - "Reimprospateaza": zap pe canal (motorul se roteste singur daca trebuie), caruselul complet (regula de sus), copia,
#    inapoi la canalul de dinainte; cel mult 10 minute, iar fara nicio pagina de teletext 90 s; la esec rezultatul spune
#    motivul si cate pagini s-au strans (text_rezultat, pentru televizor si web);
#  - lista canalelor care au teletext (din lamedb, c:02 = PID-ul teletextului).
#
# Fisierul nu cere enigma2 la incarcare: probele de pe PC dau nucleul, ceasul si dosarul lor.
import hashlib
import io
import json
import os
import time
import zlib

DOSARE_DISC = ("/media/hdd", "/media/usb")
DOSAR_FLASH = "/etc/enigma2"
SUBDOSAR = "hdsteletext"
INDEX = "index.json"
SPATII_MB = ("5", "10", "20", "50", "100")
SPATIU_IMPLICIT_MB = "20"
VARSTA_MAX_S = 6 * 3600         # copia automata se reface dupa 6 ore
PE_CANAL_MIN_S = 40             # caruselul complet: cel putin atat pe canal
TRECERI_COMPLETE = 2            # si fiecare pagina primita de cel putin atatea ori (caruselul trecut tot de doua ori)
FARA_PAGINI_NOI_S = 75          # sau atata timp nicio pagina noua (caruselele mari, paginile care nu se mai trimit)
REIMPROSPATARE_MAX_S = 600      # reimprospatarea se opreste dupa 10 minute
FARA_TELETEXT_S = 90            # reimprospatarea se opreste dupa atat timp pe canal fara nicio pagina de teletext
PAS_MS = 5000
MOTIV_INREGISTRARE = "inregistrare"
MOTIV_TIMP = "timp"
MOTIV_FARA_TELETEXT = "fara_teletext"
MOTIV_ZAP = "zap"


def N_(text):
	"""Semnul pentru xgettext (--keyword=N_): textul se traduce cand se arata (text_rezultat)."""
	return text


TEXT_TIMP = N_("Copia nu s-a reîmprospătat: în %(minute)d minute teletextul canalului nu s-a strâns tot. Pagini strânse: %(pagini)d.")
TEXT_FARA_TELETEXT = N_("Copia nu s-a reîmprospătat: în %(secunde)d de secunde canalul nu a trimis nicio pagină de teletext (fără semnal sau fără teletext).")
TEXT_ZAP = N_("Copia nu s-a reîmprospătat: receptorul nu a putut trece pe canal.")


def setari():
	"""config.plugins.hdsteletext (facute o data): hd (teletextul neted), contur, umbra, relief, copie_automata,
	spatiu (MB), peste (felul ales pe televizor)."""
	from Components.config import config, ConfigSubsection, ConfigYesNo, ConfigSelection
	import Plugins.Plugin  # noqa: F401  (config.plugins)
	try:
		return config.plugins.hdsteletext
	except (KeyError, AttributeError):     # ConfigSubsection da KeyError pentru un nume necunoscut
		pass
	s = ConfigSubsection()
	config.plugins.hdsteletext = s
	# Teletextul neted (numele intern a ramas hd, deci cine l-a ales si l-a salvat ca "Teletext HD" ramane pe el) oprit
	# din fabrica (integrarea 0.3.0): pe ARM o pagina HD ia 310-736 ms (ARD, ZDF) si 0,9-1,6 s (TVR), peste pragul de
	# 300 ms; clasicul 140-180 ms.
	s.hd = ConfigYesNo(default=False)
	# conturul (numai in jurul a ce e deschis la culoare), umbra literelor si formele in relief
	# (numai la neted) sunt optiuni, oprite din fabrica; inainte conturul si umbra se puneau singure, fara setare, deci
	# dupa actualizare sunt oprite pentru toti
	s.contur = ConfigYesNo(default=False)
	s.umbra = ConfigYesNo(default=False)
	s.relief = ConfigYesNo(default=False)
	s.copie_automata = ConfigYesNo(default=True)
	s.spatiu = ConfigSelection(default=SPATIU_IMPLICIT_MB, choices=[(m, "%s MB" % m) for m in SPATII_MB])
	s.peste = ConfigYesNo(default=False)
	return config.plugins.hdsteletext


def _nucleu(viu=True, loc=0):
	try:
		from enigma import eHdsTeletext
	except ImportError:
		return None
	return eHdsTeletext.getInstance() if viu else eHdsTeletext.copie(loc)


# ---------------------------------------------------------------- locul si indexul

def montat(cale):
	"""Cale montata, si cand e o legatura: /media/hdd e de obicei legatura spre /run/media/<eticheta>-sda1, iar
	os.path.ismount pe legatura da False."""
	return os.path.ismount(os.path.realpath(cale))


def dosar(baze=DOSARE_DISC, flash=DOSAR_FLASH, montat=None):
	"""Dosarul copiilor: pe primul disc sau stick montat si scriibil, altfel in /etc/enigma2."""
	montat = montat or globals()["montat"]
	for b in baze:
		try:
			if montat(b) and os.access(b, os.W_OK):
				return os.path.join(b, SUBDOSAR)
		except OSError:
			continue
	return os.path.join(flash, SUBDOSAR)


def nume_fisier(ref):
	return hashlib.md5(ref.encode("utf-8", "replace")).hexdigest()[:16] + ".ttx"


def citeste_index(d):
	try:
		with io.open(os.path.join(d, INDEX), encoding="utf-8") as f:
			date = json.load(f)
		if isinstance(date, dict) and isinstance(date.get("copii"), dict):
			return date
	except (IOError, OSError, ValueError):
		pass
	return {"copii": {}}


def _scrie_atomic(cale, octeti):
	nou = cale + ".nou"
	with open(nou, "wb") as f:
		f.write(octeti)
		f.flush()
		os.fsync(f.fileno())
	os.replace(nou, cale)


def scrie_index(d, index):
	_scrie_atomic(os.path.join(d, INDEX), json.dumps(index, ensure_ascii=False, indent=1, sort_keys=True).encode("utf-8"))


def copii(d=None):
	"""Lista copiilor, dupa numele canalului: [{"ref", "nume", "data", "pagini", "subpagini", "octeti", "fisier"}]."""
	d = d or dosar()
	index = citeste_index(d)
	lista = []
	for ref, c in index["copii"].items():
		if os.path.isfile(os.path.join(d, c.get("fisier", ""))):
			e = dict(c)
			e["ref"] = ref
			lista.append(e)
	lista.sort(key=lambda e: (e.get("nume", "").lower(), -e.get("data", 0)))
	return lista


def copia(ref, d=None):
	for c in copii(d):
		if c["ref"] == ref:
			return c
	return None


def margineste(d, index, max_octeti):
	"""Pleaca copiile cele mai vechi pana cand toate incap in spatiul ales. -> referintele sterse."""
	sterse = []
	copii_dupa_data = sorted(index["copii"].items(), key=lambda kv: kv[1].get("data", 0))
	total = sum(c.get("octeti", 0) for _, c in copii_dupa_data)
	while total > max_octeti and len(copii_dupa_data) > 1:
		ref, c = copii_dupa_data.pop(0)
		try:
			os.remove(os.path.join(d, c.get("fisier", "")))
		except OSError:
			pass
		total -= c.get("octeti", 0)
		del index["copii"][ref]
		sterse.append(ref)
	return sterse


def _max_octeti():
	try:
		return int(setari().spatiu.value) * 1024 * 1024
	except Exception:
		return int(SPATIU_IMPLICIT_MB) * 1024 * 1024


def salveaza(ref, nume, nucleu=None, d=None, acum=None, max_octeti=None):
	"""Copia paginilor de acum ale canalului (nucleul viu) -> {"ref", "nume", "data", ...} sau None (fara pagini)."""
	n = nucleu if nucleu is not None else _nucleu()
	if n is None or not ref:
		return None
	pid, pagini, subpagini = n.stare()[:3]
	if pid <= 0 or subpagini <= 0:
		return None
	date = zlib.compress(n.exporta(), 6)
	d = d or dosar()
	try:
		os.makedirs(d, exist_ok=True)
	except OSError:
		return None
	fisier = nume_fisier(ref)
	_scrie_atomic(os.path.join(d, fisier), date)
	index = citeste_index(d)
	info = {"nume": nume or "", "data": int(acum if acum is not None else time.time()), "pagini": pagini,
		"subpagini": subpagini, "octeti": len(date), "fisier": fisier, "pid": pid}
	index["copii"][ref] = info
	margineste(d, index, max_octeti if max_octeti is not None else _max_octeti())
	scrie_index(d, index)
	rez = dict(info)
	rez["ref"] = ref
	return rez


def sterge(ref, d=None):
	d = d or dosar()
	index = citeste_index(d)
	c = index["copii"].pop(ref, None)
	if c is None:
		return False
	try:
		os.remove(os.path.join(d, c.get("fisier", "")))
	except OSError:
		pass
	scrie_index(d, index)
	return True


def octeti_copie(ref, d=None):
	"""Copia necomprimata (formatul nucleului) sau None."""
	d = d or dosar()
	c = citeste_index(d)["copii"].get(ref)
	if not c:
		return None
	try:
		with open(os.path.join(d, c["fisier"]), "rb") as f:
			return zlib.decompress(f.read())
	except (IOError, OSError, KeyError, zlib.error):
		return None


def incarca(ref, loc=0, d=None, nucleu=None):
	"""Copia canalului in nucleu (locul 0 televizorul, 1 pagina web), fara tuner. -> informatiile copiei sau None."""
	date = octeti_copie(ref, d)
	n = nucleu if nucleu is not None else _nucleu(False, loc)
	if date is None or n is None:
		return None
	if n.incarca(date) < 0:
		return None
	return copia(ref, d)


def data_text(secunde):
	try:
		return time.strftime("%d.%m.%Y %H:%M", time.localtime(int(secunde)))
	except (TypeError, ValueError, OverflowError):
		return ""


# ---------------------------------------------------------------- canalele cu teletext

def canale_cu_teletext(lamedb="/etc/enigma2/lamedb"):
	"""Canalele TV din lamedb care au teletext (c:02): [(ref, nume)], dupa nume."""
	try:
		from Components import HdsIndexCanale
		with io.open(lamedb, encoding="utf-8", errors="replace") as f:
			canale = HdsIndexCanale.citeste_lamedb(f.read())
	except Exception:
		return []
	lista = [(c.ref, c.nume) for c in canale if getattr(c, "ttx_lamedb", False) and not getattr(c, "radio", False)]
	lista.sort(key=lambda x: (x[1] or "").lower())
	return lista


# ---------------------------------------------------------------- urmaritorul (fundalul)

def ref_salvabila(ref):
	"""Copii numai pentru canale (DVB sau flux http), nu pentru fisierele inregistrate."""
	if not ref or not ref.startswith("1:"):
		return False
	cale = ref.split(":", 10)[10] if ref.count(":") >= 10 else ""
	return not cale.startswith("/")


class Urmaritor(object):
	"""Urmareste caruselul canalului care merge; copia automata; reimprospatarea. Un singur obiect (porneste())."""

	def __init__(self, session=None, nucleu=None, ceas=time.time):
		self.session = session
		self.nucleu = nucleu
		self.ceas = ceas
		self.ref = None
		self.nume = ""
		self.inceput = 0
		self.ultima_crestere = 0        # cand a aparut ultima pagina noua
		self.subpagini = 0
		self.pagini = 0
		self.versiuni = {}              # pagina -> versiunea ei la pasul de dinainte (creste cand pagina vine din nou)
		self.treceri = {}               # pagina -> de cate ori s-a primit de cand suntem pe canal
		self.salvat = False
		self.complet = False
		self.reimprospatare = None      # {"ref", "inapoi", "inceput", "gata"}
		self.timer = None

	def _n(self):
		return self.nucleu if self.nucleu is not None else _nucleu()

	def _ref_acum(self):
		try:
			r = self.session.nav.getCurrentlyPlayingServiceReference()
			if r is None:
				return None, ""
			from ServiceReference import ServiceReference
			return r.toString(), ServiceReference(r).getServiceName() or ""
		except Exception:
			return None, ""

	def porneste_ceasul(self):
		from enigma import eTimer
		self.timer = eTimer()
		self.timer.callback.append(self.pas)
		self.timer.start(PAS_MS, False)

	def stare(self):
		return {"ref": self.ref, "nume": self.nume, "complet": self.complet, "subpagini": self.subpagini,
			"pagini": self.pagini,
			"secunde": int(self.ceas() - self.inceput) if self.ref else 0,
			"reimprospatare": dict((k, v) for k, v in self.reimprospatare.items() if k != "cb") if self.reimprospatare else None}

	def pas(self, ref=None, nume=None):
		"""Chemat la 5 s (sau din probe cu ref si nume date)."""
		if ref is None:
			ref, nume = self._ref_acum()
		acum = self.ceas()
		n = self._n()
		if ref != self.ref:
			self.ref, self.nume = ref, nume or ""
			self.inceput = self.ultima_crestere = acum
			self.subpagini = self.pagini = 0
			self.versiuni = {}
			self.treceri = {}
			self.salvat = False
			self.complet = False
		st = n.stare() if n is not None else (-1, 0, 0)
		pid, subpagini = st[0], st[2]
		if pid <= 0 or not ref_salvabila(ref):
			self.complet = False
			self.pagini = self.subpagini = 0
			return self._reimprospatare_pas(acum, None)
		self.subpagini = subpagini
		pagini = self._numara_treceri(n, acum)
		self.pagini = len(pagini)
		self.complet = subpagini > 0 and acum - self.inceput >= PE_CANAL_MIN_S and (
			self._toate_primite_de_doua_ori(pagini) or acum - self.ultima_crestere >= FARA_PAGINI_NOI_S)
		salvata = None
		if self.complet and not self.salvat:
			r = self.reimprospatare
			fortat = r is not None and r["ref"] == ref and not r.get("gata")
			if fortat or self._automat_trebuie(ref, acum):
				salvata = salveaza(ref, self.nume, n, acum=acum)
				self.salvat = salvata is not None
			else:
				self.salvat = True       # nimic de facut pe vizita asta (copia e proaspata sau copia automata e oprita)
		return self._reimprospatare_pas(acum, salvata)

	def _numara_treceri(self, n, acum):
		"""Paginile de acum; pentru fiecare, de cate ori a venit: versiunea ei (lib/dvb/hdsteletext.cpp, versiunePagina)
		creste la fiecare pachet primit, deci o versiune schimbata intre doi pasi (5 s) = pagina a venit din nou."""
		try:
			pagini = list(n.pagini())
		except Exception:
			return []
		for p in pagini:
			try:
				v = n.versiune(p)
			except Exception:
				v = 0
			vechi = self.versiuni.get(p)
			if vechi is None:
				self.treceri[p] = 1
				self.ultima_crestere = acum
			elif v != vechi:
				self.treceri[p] = self.treceri.get(p, 1) + 1
			self.versiuni[p] = v
		return pagini

	def _toate_primite_de_doua_ori(self, pagini):
		return bool(pagini) and all(self.treceri.get(p, 0) >= TRECERI_COMPLETE for p in pagini)

	def _automat_trebuie(self, ref, acum):
		try:
			if not setari().copie_automata.value:
				return False
		except Exception:
			pass
		c = citeste_index(dosar())["copii"].get(ref)
		return c is None or acum - c.get("data", 0) >= VARSTA_MAX_S

	# ------------------------------------------------------------ reimprospatarea

	def reimprospateaza(self, ref, gata=None):
		"""Zap pe canal, o trecere completa a caruselului, copia, apoi inapoi. gata(rezultat) la sfarsit:
		{"ok", "ref", "copie"} sau {"ok": False, "motiv"}."""
		# o inregistrare in curs: nu se schimba canalul (tunerul ei nu se ia, mai ales noaptea, pornit din web)
		try:
			inregistrari = self.session.nav.getRecordings()
		except Exception:
			inregistrari = None
		if inregistrari:
			self.reimprospatare = {"ref": ref, "inapoi": None, "inceput": self.ceas(), "gata": True,
				"rezultat": {"ok": False, "motiv": MOTIV_INREGISTRARE}}
			if gata is not None:
				gata({"ok": False, "ref": ref, "copie": None, "motiv": MOTIV_INREGISTRARE})
			return False
		inapoi, _ = self._ref_acum()
		self.reimprospatare = {"ref": ref, "inapoi": inapoi, "inceput": self.ceas(), "gata": False, "cb": gata}
		if ref != inapoi:
			try:
				from enigma import eServiceReference
				self.session.nav.playService(eServiceReference(ref))
			except Exception as e:
				print("[HdsTeletextCopie] reimprospatare, zap:", e)
				self._termina(False, MOTIV_ZAP)
				return False
		else:
			self.salvat = False        # acelasi canal: copia se face din nou la caruselul complet
		return True

	def _reimprospatare_pas(self, acum, salvata):
		r = self.reimprospatare
		if not r or r.get("gata"):
			return salvata
		if salvata is not None and salvata.get("ref") == r["ref"]:
			self._termina(True, "", salvata)
		elif self.ref == r["ref"] and self.pagini <= 0 and acum - r["inceput"] > FARA_TELETEXT_S:
			self._termina(False, MOTIV_FARA_TELETEXT)
		elif acum - r["inceput"] > REIMPROSPATARE_MAX_S:
			self._termina(False, MOTIV_TIMP)
		return salvata

	def _termina(self, ok, motiv, copie=None):
		r = self.reimprospatare
		r["gata"] = True
		pe_canal = self.ref == r["ref"]
		cifre = {"pagini": self.pagini if pe_canal else 0, "subpagini": self.subpagini if pe_canal else 0,
			"secunde": int(self.ceas() - r["inceput"])}
		if r.get("inapoi") and r["inapoi"] != r["ref"]:
			try:
				from enigma import eServiceReference
				self.session.nav.playService(eServiceReference(r["inapoi"]))
			except Exception:
				pass
		cb = r.pop("cb", None)
		rez = {"ok": ok, "ref": r["ref"], "copie": copie, "motiv": motiv}
		rez.update(cifre)
		r["rezultat"] = {"ok": ok, "motiv": motiv}
		r["rezultat"].update(cifre)
		if cb is not None:
			try:
				cb(rez)
			except Exception as e:
				print("[HdsTeletextCopie] reimprospatare:", e)


def text_rezultat(rez, tr=None):
	"""Textul pentru om al unei reimprospatari esuate (televizorul si pagina web), tradus cu tr (implicit _ din
	enigma2); "" cand motivul nu are un text al lui (atunci ecranul spune textul general)."""
	if tr is None:
		try:
			tr = _  # noqa: F821  (pus de enigma2 in builtins)
		except NameError:
			tr = N_
	motiv = (rez or {}).get("motiv")
	if motiv == MOTIV_TIMP:
		return tr(TEXT_TIMP) % {"minute": REIMPROSPATARE_MAX_S // 60, "pagini": int(rez.get("pagini") or 0)}
	if motiv == MOTIV_FARA_TELETEXT:
		return tr(TEXT_FARA_TELETEXT) % {"secunde": FARA_TELETEXT_S}
	if motiv == MOTIV_ZAP:
		return tr(TEXT_ZAP)
	return ""


_URMARITOR = []


def porneste(session):
	"""Pornit o data, din bara (Screens/InfoBar.py)."""
	if _URMARITOR:
		return _URMARITOR[0]
	u = Urmaritor(session)
	try:
		setari()
		u.porneste_ceasul()
	except Exception as e:
		print("[HdsTeletextCopie] urmaritorul nu porneste:", e)
	_URMARITOR.append(u)
	return u


def urmaritor():
	return _URMARITOR[0] if _URMARITOR else None
