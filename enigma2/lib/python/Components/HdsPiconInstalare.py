# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsPiconInstalare.py: siglele canalelor (piconurile) puse pe receptor din telecomanda sau din web, fara FTP si fara SSH
# (cererea dorinelu, forumul 795 #2463 si #2474; 0.7.5). Ecranul: Screens/HdsPiconuri.py; pagina web: /piconuri
# (Plugins/Extensions/HdsWebControl/piconuri_web.py).
#
# SURSA o alege omul: o adresa scrisa de el (arhiva zip, tar, tar.gz, tar.bz2, tar.xz sau pachet ipk), o arhiva sau un
# dosar de pe un stick sau disc, ori (in web) o arhiva trimisa din calculator. Imaginea nu are si nu propune nicio sursa.
#
# LOCUL: dosarul picon din memoria receptorului sau de pe un disc montat (Tools/PiconResolver.py cauta pe toate). Locul
# ales singur: cel care are deja sigle puse de noi, altfel discul cu cel mai mult loc liber, altfel memoria.
#
# NUMAI CANALELE DIN LISTA (din fabrica da): din arhiva se scriu numai siglele canalelor din buchetele receptorului
# (fara buchete: toate serviciile din lamedb), dupa referinta (PiconResolver.nume_sigle, ca toString: tipul si steagurile
# in zecimal, restul in hex mare) si dupa numele canalului (nume_cautate_canal). Numele se potrivesc fara litere mari sau
# mici; fisierul se scrie cu numele cautat de imagine. Arhiva intreaga se descarca (nu se poate altfel), dar pe disc
# raman numai siglele alese.
#
# SIGURANTA: din arhiva se iau numai fisiere .png (numele de baza, deci nicio cale nu iese din dosarul ales), cel mult
# MAX_PNG fiecare, cu semnatura PNG verificata; picon_default*.png nu se atinge (e sigla lipsei din tema). Legaturile din
# arhiva (seturile leaga multe referinte de un singur desen) se rezolva in arhiva si se scriu ca fisiere adevarate (un
# stick FAT nu tine legaturi); acelasi desen scris de mai multe ori se leaga tare cand discul poate, altfel se copiaza.
# Fiecare fisier: <nume>.nou, apoi os.replace (o sigla pe jumatate nu se vede). O sigla a omului peste care scriem se muta
# intai in DOSAR_VECHI si se pune la loc la dezinstalare.
#
# JURNALUL (<loc>/.hds-piconuri.json): sursa, felul ei, optiunea, data, fisierele scrise de noi si cele inlocuite.
# Actualizarea foloseste aceeasi sursa si acelasi loc; fisierele noastre care nu mai sunt in arhiva se sterg. Dezinstalarea
# sterge numai fisierele din jurnal si pune la loc siglele omului.
#
# DESCARCAREA: numai http si https, fara proxy, cel mult 5 redirectari, MAX_ARHIVA; fisierul temporar pe discul cu cel mai
# mult loc liber sau langa locul ales (nu in /tmp, care e in memoria RAM), sters la sfarsit. Spatiul se verifica inainte
# (Content-Length) si in timpul descarcarii. .ipk = arhiva ar citita aici (fara opkg, care ar scrie numai in memorie).
#
# Fara enigma la incarcare: probele de pe PC (teste/test_pic_*.py) folosesc functiile cu dosare temporare.

import io
import json
import os
import shutil
import stat
import tarfile
import threading
import time
import zipfile

JURNAL = ".hds-piconuri.json"
DOSAR_VECHI = ".hds-piconuri-vechi"
TEMP = ".hds-piconuri-descarcare"
MAX_ARHIVA = 2 * 1024 * 1024 * 1024
MAX_PNG = 1024 * 1024
MAX_FISIERE = 200000
REZERVA = 20 * 1024 * 1024          # loc lasat liber pe discul ales (si in memorie)
TIMP_RETEA = 30
SEMNATURA_PNG = b"\x89PNG\r\n\x1a\n"

# locurile; in probe se inlocuiesc cu dosare temporare
DOSAR_MEMORIE = "/usr/share/enigma2/picon"
DOSAR_SETARI = "/etc/enigma2"
RADACINI_MEDIA = ("/media",)
MONTARI_SARITE = ("net", "autofs", "upnp")


def _t(text):
	try:
		return _(text)
	except NameError:
		return text


class Eroare(Exception):
	"""O oprire cu un mesaj pentru om (deja tradus)."""


# ------------------------------------------------------------------------------------------------ locurile

def _liber(cale):
	"""Octetii liberi pe sistemul de fisiere al caii (sau al primului parinte care exista)."""
	while cale and not os.path.exists(cale):
		parinte = os.path.dirname(cale.rstrip("/"))
		if parinte == cale:
			break
		cale = parinte
	try:
		s = os.statvfs(cale or "/")
		return s.f_bavail * s.f_frsize
	except (OSError, AttributeError):
		try:
			return shutil.disk_usage(cale or "/").free
		except OSError:
			return 0


def _numara_sigle(dosar):
	n = 0
	try:
		with os.scandir(dosar) as it:
			for e in it:
				if e.name.lower().endswith(".png") and not e.name.startswith("picon_default"):
					n += 1
	except OSError:
		pass
	return n


def _montari():
	"""Discurile montate sub /media (fara retea), in care se poate scrie."""
	gasite = []
	for radacina in RADACINI_MEDIA:
		try:
			intrari = sorted(os.listdir(radacina))
		except OSError:
			continue
		for intrare in intrari:
			if intrare in MONTARI_SARITE:
				continue
			cale = os.path.join(radacina, intrare)
			if not os.path.isdir(cale) or not os.access(cale, os.W_OK):
				continue
			if radacina == "/media" and not os.path.ismount(cale):
				continue
			gasite.append(cale)
	return gasite


def citeste_jurnal(dosar):
	try:
		with open(os.path.join(dosar, JURNAL), "r", encoding="utf-8") as f:
			j = json.load(f)
		return j if isinstance(j, dict) else None
	except (OSError, ValueError):
		return None


class _Locuri(object):
	cand = 0
	rez = None


def locuri(proaspete=False):
	"""Locurile posibile: [{cale, nume, liber, sigle, ale_noastre}]; intai memoria, apoi discurile. Tinute minte 5 s
	(numararea siglelor parcurge dosarele); dupa o instalare sau dezinstalare se citesc din nou."""
	acum = time.time()
	if not proaspete and _Locuri.rez is not None and 0 <= acum - _Locuri.cand < 5:
		return [dict(l) for l in _Locuri.rez]
	rez = []
	for cale, nume in [(DOSAR_MEMORIE, _t("Memoria receptorului"))] + [
			(os.path.join(m, "picon"), _t("Disc sau stick: %s") % m) for m in _montari()]:
		j = citeste_jurnal(cale)
		rez.append({"cale": cale, "nume": nume, "liber": _liber(cale), "sigle": _numara_sigle(cale),
			"ale_noastre": len(j.get("fisiere", [])) if j else 0, "sursa": (j or {}).get("sursa", "")})
	_Locuri.rez, _Locuri.cand = rez, acum
	return [dict(l) for l in rez]


def loc_implicit(lista=None):
	"""Locul cu sigle puse de noi; altfel discul cu cel mai mult loc liber; altfel memoria."""
	lista = locuri() if lista is None else lista
	for l in lista:
		if l["ale_noastre"]:
			return l["cale"]
	discuri = [l for l in lista if l["cale"] != DOSAR_MEMORIE]
	if discuri:
		return max(discuri, key=lambda l: l["liber"])["cale"]
	return DOSAR_MEMORIE


def marime_text(octeti):
	if octeti >= 1024 * 1024 * 1024:
		return "%.1f GB" % (octeti / 1073741824.0)
	if octeti >= 1024 * 1024:
		return "%d MB" % (octeti // 1048576)
	return "%d kB" % max(1, octeti // 1024)


# ------------------------------------------------------------------------------------------------ canalele din lista

def _hex(c):
	try:
		return "%X" % int(c, 16)
	except ValueError:
		return c.upper()


def normalizeaza_ref(sref):
	"""Referinta ca toString: tipul si steagurile in zecimal, campurile 2-9 in hex mare fara zerouri in fata."""
	c = str(sref or "").strip().split(":")
	if len(c) < 10:
		return ""
	try:
		c[0] = str(int(c[0]))
		c[1] = str(int(c[1]))
	except ValueError:
		return ""
	c[2:10] = [_hex(x) for x in c[2:10]]
	return ":".join(c[:10]) + ":"


def _citeste_lamedb(dosar):
	"""{referinta: nume} din lamedb (formatul 4), altfel din lamedb5."""
	rez = {}
	try:
		with open(os.path.join(dosar, "lamedb"), "r", encoding="utf-8", errors="replace") as f:
			linii = f.read().splitlines()
		i = linii.index("services") + 1
		while i + 1 < len(linii) and linii[i] != "end":
			c = linii[i].split(":")
			if len(c) >= 5:
				try:
					sref = "1:0:%X:%X:%X:%X:%X:0:0:0:" % (int(c[4]), int(c[0], 16), int(c[2], 16), int(c[3], 16),
						int(c[1], 16))
					rez[sref] = linii[i + 1]
				except ValueError:
					pass
			i += 3
		return rez
	except (OSError, ValueError):
		pass
	try:
		with open(os.path.join(dosar, "lamedb5"), "r", encoding="utf-8", errors="replace") as f:
			for linie in f:
				if not linie.startswith("s:"):
					continue
				parti = linie.rstrip("\n").split(",", 2)
				c = parti[0][2:].split(":")
				if len(c) >= 5 and len(parti) > 1:
					try:
						sref = "1:0:%X:%X:%X:%X:%X:0:0:0:" % (int(c[4]), int(c[0], 16), int(c[2], 16),
							int(c[3], 16), int(c[1], 16))
						rez[sref] = parti[1].strip('"')
					except ValueError:
						pass
	except OSError:
		pass
	return rez


def _servicii_buchet(dosar, fisier, vazute, rez):
	if fisier in vazute or len(vazute) > 500:
		return
	vazute.add(fisier)
	try:
		with open(os.path.join(dosar, fisier), "r", encoding="utf-8", errors="replace") as f:
			linii = f.read().splitlines()
	except OSError:
		return
	ultim = None
	for linie in linii:
		if linie.startswith("#SERVICE "):
			sref = linie[9:].strip()
			ultim = None
			if 'FROM BOUQUET "' in sref:
				_servicii_buchet(dosar, sref.split('FROM BOUQUET "', 1)[1].split('"', 1)[0], vazute, rez)
				continue
			c = sref.split(":")
			if len(c) < 10:
				continue
			try:
				if int(c[1]) & 0x40 or int(c[1]) & 0x02:   # marcaj sau dosar
					continue
			except ValueError:
				continue
			nume = ""
			if len(c) > 11:          # fluxurile au numele la coada
				try:
					from urllib.parse import unquote
				except ImportError:
					unquote = lambda s: s
				nume = unquote(":".join(c[11:]))
			ultim = [sref, nume]
			rez.append(ultim)
		elif linie.startswith("#DESCRIPTION ") and ultim is not None:
			ultim[1] = linie[13:].strip()


def servicii_receptor(dosar=None):
	"""[(referinta, nume)] ale canalelor din buchete; fara buchete, toate din lamedb."""
	dosar = dosar or DOSAR_SETARI
	lamedb = _citeste_lamedb(dosar)
	lista = []
	vazute = set()
	for b in ("bouquets.tv", "bouquets.radio"):
		_servicii_buchet(dosar, b, vazute, lista)
	if not lista:
		return list(lamedb.items())
	rez = []
	for sref, nume in lista:
		n = normalizeaza_ref(sref)
		rez.append((sref, nume or lamedb.get(n, "")))
	return rez


def _resolver():
	from Tools import PiconResolver
	return PiconResolver


def nume_dorite(servicii):
	"""{nume mic: nume de scris} pentru siglele cautate de imagine pentru aceste canale."""
	R = _resolver()
	dorite = {}
	for sref, nume in servicii:
		n = normalizeaza_ref(sref)
		for x in (R.nume_sigle(n) if n else []):
			dorite.setdefault(x.lower(), x)
		for x in (R.nume_cautate_canal(nume) if nume else []):
			dorite.setdefault(x.lower(), x)
	return dorite


# ------------------------------------------------------------------------------------------------ arhivele

class _Fereastra(io.RawIOBase):
	"""O bucata dintr-un fisier deschis, ca fisier (membrul data.tar.* din .ipk), fara copiere."""

	def __init__(self, f, start, marime):
		self._f, self._start, self._marime, self._poz = f, start, marime, 0

	def readable(self):
		return True

	def seekable(self):
		return True

	def tell(self):
		return self._poz

	def seek(self, poz, de_unde=0):
		baza = (0, self._poz, self._marime)[de_unde]
		self._poz = max(0, min(self._marime, baza + poz))
		return self._poz

	def readinto(self, b):
		n = min(len(b), self._marime - self._poz)
		if n <= 0:
			return 0
		self._f.seek(self._start + self._poz)
		date = self._f.read(n)
		b[:len(date)] = date
		self._poz += len(date)
		return len(date)


def _membru_ipk(f):
	"""(start, marime) al lui data.tar.* dintr-o arhiva ar (.ipk/.deb)."""
	f.seek(8)
	while True:
		antet = f.read(60)
		if len(antet) < 60:
			break
		nume = antet[:16].decode("ascii", "replace").strip().rstrip("/")
		try:
			marime = int(antet[48:58].decode("ascii").strip())
		except ValueError:
			break
		start = f.tell()
		if nume.startswith("data.tar"):
			return start, marime
		f.seek(start + marime + (marime & 1))
	raise Eroare(_t("Pachetul nu are siglele în el (lipsește data.tar)."))


def fel_arhiva(cale):
	try:
		with open(cale, "rb") as f:
			cap = f.read(512)
	except OSError:
		return ""
	if cap.startswith(b"PK\x03\x04") or cap.startswith(b"PK\x05\x06"):
		return "zip"
	if cap.startswith(b"!<arch>\n"):
		return "ipk"
	if cap[:2] == b"\x1f\x8b" or cap[:3] == b"BZh" or cap[:6] == b"\xfd7zXZ\x00" or cap[257:262] == b"ustar":
		return "tar"
	return ""


def _nume_bun(baza):
	l = baza.lower()
	return (l.endswith(".png") and not baza.startswith(".") and not l.startswith("picon_default")
		and "/" not in baza and "\\" not in baza and len(baza) < 200)


def _scor_dosar(cale):
	"""Intre doua desene cu acelasi nume, cel din dosarul numit picon castiga."""
	parinte = os.path.basename(os.path.dirname(cale)).lower()
	return 0 if parinte == "picon" else 1


class _Sursa(object):
	"""Membrii PNG ai unei surse: {nume_baza: cheie}, unde cheie spune ce desen se citeste (legaturile rezolvate)."""

	def __init__(self):
		self.pnguri = {}     # nume de baza -> (scor, cheie)
		self.marimi = {}     # cheie -> marime

	def adauga(self, cale, cheie, marime):
		baza = cale.replace("\\", "/").rsplit("/", 1)[-1]
		if not _nume_bun(baza) or marime > MAX_PNG:
			return
		if len(self.pnguri) >= MAX_FISIERE and baza not in self.pnguri:
			return
		s = _scor_dosar(cale.replace("\\", "/"))
		vechi = self.pnguri.get(baza)
		if vechi is None or s < vechi[0]:
			self.pnguri[baza] = (s, cheie)
			self.marimi[cheie] = marime

	def citeste(self, cheie):
		raise NotImplementedError

	def inchide(self):
		pass


class _SursaTar(_Sursa):
	def __init__(self, fileobj, fisier=None):
		_Sursa.__init__(self)
		self._fisier = fisier
		try:
			self.tf = tarfile.open(fileobj=fileobj, mode="r:*")
			membri = self.tf.getmembers()
		except (tarfile.TarError, EOFError, OSError, ValueError) as e:
			self.inchide()
			raise Eroare(_t("Arhiva nu poate fi citită: %s") % e)
		self._dupa_nume = {}
		for m in membri:
			self._dupa_nume[m.name.lstrip("./")] = m
		for m in membri:
			tinta = self._rezolva(m)
			if tinta is not None:
				self.adauga(m.name, tinta.name, tinta.size)

	def _rezolva(self, m, adancime=0):
		"""Membrul obisnuit spre care duce m (legatura simbolica sau tare), sau None."""
		if adancime > 10:
			return None
		if m.isfile():
			return m
		if m.islnk():
			t = self._dupa_nume.get(m.linkname.lstrip("./"))
		elif m.issym():
			if m.linkname.startswith("/"):
				return None
			cale = os.path.normpath(os.path.join(os.path.dirname(m.name.lstrip("./")), m.linkname)).replace("\\", "/")
			t = self._dupa_nume.get(cale)
		else:
			return None
		return self._rezolva(t, adancime + 1) if t is not None else None

	def ordine(self, chei):
		"""Cheile in ordinea din arhiva (o arhiva comprimata se citeste inainte, fara intoarceri)."""
		return sorted(chei, key=lambda c: self._dupa_nume[c.lstrip("./")].offset_data)

	def citeste(self, cheie):
		f = self.tf.extractfile(self._dupa_nume[cheie.lstrip("./")])
		return f.read(MAX_PNG + 1) if f else b""

	def inchide(self):
		for x in (getattr(self, "tf", None), self._fisier):
			try:
				if x is not None:
					x.close()
			except Exception:
				pass


class _SursaZip(_Sursa):
	def __init__(self, cale):
		_Sursa.__init__(self)
		try:
			self.zf = zipfile.ZipFile(cale)
			infos = self.zf.infolist()
		except (zipfile.BadZipFile, OSError, ValueError) as e:
			raise Eroare(_t("Arhiva nu poate fi citită: %s") % e)
		dupa = dict((i.filename, i) for i in infos)
		for i in infos:
			if i.is_dir():
				continue
			tinta = i
			for _n in range(10):
				if stat.S_ISLNK(tinta.external_attr >> 16) and tinta.file_size < 1024:
					leg = self.zf.read(tinta).decode("utf-8", "replace")
					cale_t = os.path.normpath(os.path.join(os.path.dirname(tinta.filename), leg)).replace("\\", "/")
					tinta = dupa.get(cale_t)
					if tinta is None:
						break
				else:
					break
			if tinta is not None and not stat.S_ISLNK(tinta.external_attr >> 16):
				self.adauga(i.filename, tinta.filename, tinta.file_size)

	def ordine(self, chei):
		return sorted(chei)

	def citeste(self, cheie):
		with self.zf.open(cheie) as f:
			return f.read(MAX_PNG + 1)

	def inchide(self):
		self.zf.close()


class _SursaDosar(_Sursa):
	def __init__(self, dosar):
		_Sursa.__init__(self)
		for radacina, dosare, fisiere in os.walk(dosar, followlinks=False):
			dosare[:] = [d for d in dosare if not d.startswith(".")]
			for n in fisiere:
				cale = os.path.join(radacina, n)
				try:
					reala = os.path.realpath(cale)
					marime = os.path.getsize(reala)
				except OSError:
					continue
				if os.path.isfile(reala):
					self.adauga(cale, reala, marime)

	def ordine(self, chei):
		return sorted(chei)

	def citeste(self, cheie):
		with open(cheie, "rb") as f:
			return f.read(MAX_PNG + 1)


def deschide_sursa(cale):
	"""Sursa de sigle dintr-un dosar sau o arhiva (zip, tar*, ipk)."""
	if os.path.isdir(cale):
		return _SursaDosar(cale)
	fel = fel_arhiva(cale)
	if fel == "zip":
		return _SursaZip(cale)
	if fel == "tar":
		f = open(cale, "rb")
		return _SursaTar(f, f)
	if fel == "ipk":
		f = open(cale, "rb")
		try:
			start, marime = _membru_ipk(f)
		except Exception:
			f.close()
			raise
		return _SursaTar(io.BufferedReader(_Fereastra(f, start, marime), 1024 * 1024), f)
	raise Eroare(_t("Fișierul nu e o arhivă cunoscută (zip, tar, tar.gz, tar.xz, ipk)."))


# ------------------------------------------------------------------------------------------------ instalarea

def _reimprospateaza():
	"""Ecranele vad pe loc siglele noi (memoria cautarilor din Tools/PiconResolver.py uitata)."""
	try:
		_resolver().resetPiconPath()
	except Exception:
		pass
	_Semn.cand = 0
	_Locuri.rez = None


def _scrie_atomic(cale, date):
	nou = cale + ".nou"
	with open(nou, "wb") as f:
		f.write(date)
		f.flush()
		try:
			os.fsync(f.fileno())
		except OSError:
			pass
	os.replace(nou, cale)


def _scrie_jurnal(dosar, j):
	_scrie_atomic(os.path.join(dosar, JURNAL), json.dumps(j, ensure_ascii=False, indent=1).encode("utf-8"))


def _anunta(progres, text):
	if progres:
		try:
			progres(text)
		except Exception:
			pass


def instaleaza_din_cale(cale, dosar, numai_lista=True, servicii=None, progres=None, oprire=None,
		sursa=None, fel="fisier"):
	"""Pune siglele dintr-un dosar sau o arhiva in dosarul ales. Intoarce {scrise, sarite, sterse, mesaj}."""
	if not cale or not os.path.exists(cale):
		raise Eroare(_t("Nu găsesc fișierul sau dosarul ales."))
	if os.path.isdir(cale) and os.path.realpath(cale) == os.path.realpath(dosar):
		raise Eroare(_t("Ai ales chiar dosarul siglelor. Alege alt dosar sau o arhivă."))
	_anunta(progres, _t("Se citește arhiva..."))
	src = deschide_sursa(cale)
	try:
		return _instaleaza(src, dosar, numai_lista, servicii, progres, oprire, sursa or cale, fel)
	finally:
		src.inchide()


def _instaleaza(src, dosar, numai_lista, servicii, progres, oprire, sursa, fel):
	if not src.pnguri:
		raise Eroare(_t("În arhivă nu e nicio siglă (fișiere .png)."))
	plan = {}                                   # nume de scris -> cheie
	if numai_lista:
		dorite = nume_dorite(servicii if servicii is not None else servicii_receptor())
		if not dorite:
			raise Eroare(_t("Lista ta de canale e goală. Caută întâi canalele sau scoate bifa Numai canalele din lista mea."))
		for baza, (_s, cheie) in src.pnguri.items():
			nume = dorite.get(baza[:-4].lower())
			if nume is not None:
				plan.setdefault(nume + ".png", cheie)
		if not plan:
			raise Eroare(_t("Arhiva are %d sigle, dar niciuna nu se potrivește cu canalele din lista ta.") % len(src.pnguri))
	else:
		plan = dict((baza, cheie) for baza, (_s, cheie) in src.pnguri.items())
	# locul: desenele diferite, o singura data (restul se leaga tare cand se poate)
	unice = set(plan.values())
	nevoie = sum(src.marimi.get(c, 0) for c in unice)
	try:
		os.makedirs(dosar, exist_ok=True)
	except OSError as e:
		raise Eroare(_t("Nu pot face dosarul siglelor: %s") % e)
	if _liber(dosar) - REZERVA < nevoie:
		raise Eroare(_t("Nu e destul loc: trebuie %s, sunt liberi %s. Alege un disc sau numai canalele din lista ta.")
			% (marime_text(nevoie), marime_text(max(0, _liber(dosar) - REZERVA))))
	vechi = citeste_jurnal(dosar) or {}
	ale_noastre = set(vechi.get("fisiere", []))
	inlocuite = list(vechi.get("inlocuite", []))
	scrise, sarite, primul = [], 0, {}
	pe_cheie = {}
	for nume, cheie in plan.items():
		pe_cheie.setdefault(cheie, []).append(nume)
	total, gata = len(plan), 0
	ultim = 0
	for cheie in src.ordine(list(pe_cheie)):
		if oprire is not None and oprire.is_set():
			break
		try:
			date = src.citeste(cheie)
		except Exception:
			date = b""
		if not date.startswith(SEMNATURA_PNG) or len(date) > MAX_PNG:
			sarite += len(pe_cheie[cheie])
			gata += len(pe_cheie[cheie])
			continue
		for nume in pe_cheie[cheie]:
			tinta = os.path.join(dosar, nume)
			if os.path.lexists(tinta) and nume not in ale_noastre and nume not in inlocuite:
				# sigla omului: o pastram pentru dezinstalare
				try:
					os.makedirs(os.path.join(dosar, DOSAR_VECHI), exist_ok=True)
					os.replace(tinta, os.path.join(dosar, DOSAR_VECHI, nume))
					inlocuite.append(nume)
				except OSError:
					sarite += 1
					continue
			try:
				legat = False
				if cheie in primul:
					try:
						if os.path.lexists(tinta):
							os.remove(tinta)
						os.link(primul[cheie], tinta)
						legat = True
					except OSError:
						legat = False
				if not legat:
					_scrie_atomic(tinta, date)
					primul.setdefault(cheie, tinta)
				scrise.append(nume)
			except OSError as e:
				if not scrise:
					raise Eroare(_t("Nu pot scrie în dosarul siglelor: %s") % e)
				sarite += 1
			gata += 1
		if time.time() - ultim > 0.5:
			ultim = time.time()
			_anunta(progres, _t("Se scriu siglele: %d din %d") % (gata, total))
	# siglele noastre de data trecuta care nu mai sunt in sursa
	sterse = 0
	noi = set(scrise)
	if oprire is None or not oprire.is_set():
		for nume in ale_noastre - noi:
			try:
				os.remove(os.path.join(dosar, nume))
				sterse += 1
			except OSError:
				pass
			ascunsa = os.path.join(dosar, DOSAR_VECHI, nume)
			if nume in inlocuite and os.path.lexists(ascunsa):
				try:
					os.replace(ascunsa, os.path.join(dosar, nume))
					inlocuite.remove(nume)
				except OSError:
					pass
		pastrate = noi
	else:
		pastrate = noi | ale_noastre
	_scrie_jurnal(dosar, {"versiune": 1, "sursa": sursa, "fel": fel, "numai_lista": bool(numai_lista),
		"data": int(time.time()), "fisiere": sorted(pastrate), "inlocuite": sorted(set(inlocuite))})
	_reimprospateaza()
	mesaj = _t("Gata: %d sigle puse.") % len(scrise)
	if sarite:
		mesaj += " " + _t("%d sărite (nu erau PNG bune sau nu s-au putut scrie).") % sarite
	if oprire is not None and oprire.is_set():
		mesaj = _t("Oprit. %d sigle puse până acum.") % len(scrise)
	return {"scrise": len(scrise), "sarite": sarite, "sterse": sterse, "mesaj": mesaj}


def _adresa_buna(adresa):
	adresa = (adresa or "").strip()
	if adresa and "://" not in adresa:
		adresa = "https://" + adresa
	if not (adresa.startswith("http://") or adresa.startswith("https://")) or " " in adresa:
		raise Eroare(_t("Adresa trebuie să înceapă cu http:// sau https://."))
	return adresa


def dosar_temporar(dosar):
	"""Unde se descarca arhiva: discul cu cel mai mult loc liber, altfel langa locul ales."""
	discuri = _montari()
	if discuri:
		return os.path.join(max(discuri, key=_liber), TEMP)
	return os.path.join(os.path.dirname(dosar.rstrip("/")) or dosar, TEMP)


def descarca(adresa, tinta, progres=None, oprire=None, deschide=None):
	"""Descarca adresa in fisierul tinta. deschide(adresa) -> raspuns (in probe)."""
	adresa = _adresa_buna(adresa)
	if deschide is None:
		import ssl
		from urllib.request import build_opener, ProxyHandler, HTTPSHandler, Request
		opener = build_opener(ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context()))

		def deschide(a):
			return opener.open(Request(a, headers={"User-Agent": "HDSatelit-Picon/1"}), timeout=TIMP_RETEA)
	try:
		r = deschide(adresa)
	except Exception as e:
		raise Eroare(_t("Nu am putut descărca de la adresa dată: %s") % e)
	try:
		final = getattr(r, "geturl", lambda: adresa)() or adresa
		if not (final.startswith("http://") or final.startswith("https://")):
			raise Eroare(_t("Adresa trebuie să înceapă cu http:// sau https://."))
		try:
			lungime = int(r.headers.get("Content-Length") or 0)
		except (ValueError, AttributeError):
			lungime = 0
		if lungime > MAX_ARHIVA:
			raise Eroare(_t("Arhiva e prea mare (%s).") % marime_text(lungime))
		dosar_t = os.path.dirname(tinta)
		os.makedirs(dosar_t, exist_ok=True)
		if lungime and _liber(dosar_t) - REZERVA < lungime:
			raise Eroare(_t("Nu e destul loc pentru descărcare: trebuie %s.") % marime_text(lungime))
		citit, ultim = 0, 0
		with open(tinta, "wb") as f:
			while True:
				if oprire is not None and oprire.is_set():
					raise Eroare(_t("Oprit."))
				bucata = r.read(256 * 1024)
				if not bucata:
					break
				citit += len(bucata)
				if citit > MAX_ARHIVA:
					raise Eroare(_t("Arhiva e prea mare (%s).") % marime_text(citit))
				f.write(bucata)
				if time.time() - ultim > 0.5:
					ultim = time.time()
					if _liber(dosar_t) < REZERVA:
						raise Eroare(_t("Nu e destul loc pentru descărcare."))
					_anunta(progres, (_t("Se descarcă: %s din %s") % (marime_text(citit), marime_text(lungime)))
						if lungime else _t("Se descarcă: %s") % marime_text(citit))
		if citit == 0:
			raise Eroare(_t("La adresa dată nu e niciun fișier."))
		return citit
	finally:
		try:
			r.close()
		except Exception:
			pass


def instaleaza_din_adresa(adresa, dosar, numai_lista=True, servicii=None, progres=None, oprire=None, deschide=None):
	adresa = _adresa_buna(adresa)
	temp = dosar_temporar(dosar)
	fisier = os.path.join(temp, "arhiva")
	try:
		descarca(adresa, fisier, progres, oprire, deschide)
		return instaleaza_din_cale(fisier, dosar, numai_lista, servicii, progres, oprire, sursa=adresa, fel="adresa")
	finally:
		shutil.rmtree(temp, ignore_errors=True)


# arhiva trimisa din calculator (pagina web /piconuri): pe bucati, scrisa in fisierul temporar al locului ales
MAX_BUCATA = 4 * 1024 * 1024


class Incarcare(object):
	"""O singura arhiva trimisa odata: {id, cale, primit, total, nume, dosar, numai_lista}."""
	curenta = None
	_zavor = threading.Lock()


def scrie_bucata(ident, pozitie, total, octeti, dosar, nume="", numai_lista=True):
	"""Scrie o bucata. Intoarce True cand arhiva e intreaga (si porneste instalarea), False cand mai vin bucati."""
	if not ident or len(ident) > 40 or not ident.replace("-", "").isalnum():
		raise Eroare(_t("Trimiterea nu are un nume bun. Încearcă din nou."))
	if total <= 0 or total > MAX_ARHIVA or len(octeti) > MAX_BUCATA or pozitie < 0 or pozitie + len(octeti) > total:
		raise Eroare(_t("Arhiva e prea mare (%s).") % marime_text(max(total, 0)))
	with Incarcare._zavor:
		c = Incarcare.curenta
		if pozitie == 0:
			if Lucru.ocupat:
				raise Eroare(_t("Se instalează deja. Așteaptă să se termine."))
			if c is not None:
				shutil.rmtree(os.path.dirname(c["cale"]), ignore_errors=True)
			temp = dosar_temporar(dosar)
			os.makedirs(temp, exist_ok=True)
			if _liber(temp) - REZERVA < total:
				Incarcare.curenta = None
				raise Eroare(_t("Nu e destul loc pentru descărcare: trebuie %s.") % marime_text(total))
			c = Incarcare.curenta = {"id": ident, "cale": os.path.join(temp, "arhiva"), "primit": 0, "total": total,
				"nume": os.path.basename(nume or "arhiva")[:120], "dosar": dosar, "numai_lista": bool(numai_lista)}
			open(c["cale"], "wb").close()
		if c is None or c["id"] != ident or c["primit"] != pozitie or c["total"] != total:
			raise Eroare(_t("Trimiterea s-a întrerupt. Încearcă din nou."))
		with open(c["cale"], "ab") as f:
			f.write(octeti)
		c["primit"] += len(octeti)
		if c["primit"] < total:
			return False
		Incarcare.curenta = None
	if not Lucru.porneste(instaleaza_incarcata, c["cale"], c["dosar"], c["numai_lista"], c["nume"]):
		shutil.rmtree(os.path.dirname(c["cale"]), ignore_errors=True)
		raise Eroare(_t("Se instalează deja. Așteaptă să se termine."))
	return True


def instaleaza_incarcata(cale, dosar, numai_lista=True, nume="", servicii=None, progres=None, oprire=None):
	try:
		return instaleaza_din_cale(cale, dosar, numai_lista, servicii, progres, oprire, sursa=nume or "arhiva",
			fel="incarcata")
	finally:
		shutil.rmtree(os.path.dirname(cale), ignore_errors=True)


def loc_permis(cale):
	"""Numai locurile din locuri() (pagina web nu poate alege alta cale)."""
	for l in locuri():
		if l["cale"] == cale:
			return cale
	raise Eroare(_t("Locul ales nu mai există. Reîncarcă pagina."))


def actualizeaza(dosar, servicii=None, progres=None, oprire=None, deschide=None):
	"""Aceeasi sursa, acelasi loc, aceeasi optiune ca data trecuta."""
	j = citeste_jurnal(dosar)
	if not j or not j.get("sursa"):
		raise Eroare(_t("Aici nu sunt sigle puse din acest ecran. Instalează întâi un set."))
	if j.get("fel") == "adresa":
		return instaleaza_din_adresa(j["sursa"], dosar, j.get("numai_lista", True), servicii, progres, oprire, deschide)
	if j.get("fel") == "incarcata":
		raise Eroare(_t("Setul a fost trimis din calculator. Trimite din nou arhiva ca să-l actualizezi."))
	return instaleaza_din_cale(j["sursa"], dosar, j.get("numai_lista", True), servicii, progres, oprire,
		sursa=j["sursa"], fel=j.get("fel", "fisier"))


def dezinstaleaza(dosar):
	"""Sterge numai siglele puse de noi si pune la loc siglele omului. Intoarce cate au fost sterse."""
	j = citeste_jurnal(dosar)
	if not j:
		raise Eroare(_t("Aici nu sunt sigle puse din acest ecran."))
	sterse = 0
	for nume in j.get("fisiere", []):
		if not _nume_bun(nume):
			continue
		try:
			os.remove(os.path.join(dosar, nume))
			sterse += 1
		except OSError:
			pass
	ascunse = os.path.join(dosar, DOSAR_VECHI)
	for nume in j.get("inlocuite", []):
		if _nume_bun(nume) and os.path.lexists(os.path.join(ascunse, nume)):
			try:
				os.replace(os.path.join(ascunse, nume), os.path.join(dosar, nume))
			except OSError:
				pass
	try:
		os.remove(os.path.join(dosar, JURNAL))
	except OSError:
		pass
	for d in (ascunse, dosar):
		try:
			os.rmdir(d)
		except OSError:
			pass
	_reimprospateaza()
	return sterse


# ------------------------------------------------------------------------------------------------ semnul "Nu ai inca sigle"

class _Semn(object):
	cand = 0
	are = True


def exista_sigle():
	"""Este macar o sigla in dosarele imaginii (memorie si orice disc)? Tinut minte 60 s."""
	acum = time.time()
	if 0 <= acum - _Semn.cand < 60:
		return _Semn.are
	are = False
	try:
		dosare = _resolver().dosare_sigle("picon")
	except Exception:
		dosare = [DOSAR_MEMORIE]
	for d in dosare:
		if _numara_sigle(d):
			are = True
			break
	_Semn.are, _Semn.cand = are, acum
	return are


def _fara_sigle():
	"""Setarea pornita (sau necunoscuta, pe PC) si nicio sigla pe receptor."""
	try:
		from Components.config import config
		if not config.usage.hds_piconuri.value:
			return False
	except Exception:
		pass
	return not exista_sigle()


def stare_setare():
	"""Randurile de stare ale setarii Siglele canalelor (Screens/Setup.py, hdsStare)."""
	if not _fara_sigle():
		return []
	return [_t("Nu ai încă sigle. Apasă OK ca să instalezi un set.")]


def deschide_ecranul(session):
	"""OK pe setarea Siglele canalelor, pornita si fara nicio sigla (Screens/Setup.py, hdsDeschide)."""
	if not _fara_sigle():
		return False
	from Screens.HdsPiconuri import HdsPiconuri
	session.open(HdsPiconuri)
	return True


def leaga_setarea(element):
	"""Din Components/UsageConfig.py, dupa config.usage.hds_piconuri."""
	element.hdsStare = stare_setare
	element.hdsDeschide = deschide_ecranul


# ------------------------------------------------------------------------------------------------ lucrul pe fir

class Lucru(object):
	"""O singura instalare odata (ecranul si pagina web o impart). stare(): {ocupat, text, rezultat, eroare}."""
	_zavor = threading.Lock()
	ocupat = False
	text = ""
	rezultat = None
	eroare = ""
	oprire = None

	@classmethod
	def porneste(cls, functie, *args, **kw):
		with cls._zavor:
			if cls.ocupat:
				return False
			cls.ocupat, cls.text, cls.rezultat, cls.eroare = True, _t("Se pornește..."), None, ""
			cls.oprire = threading.Event()

		def progres(text):
			cls.text = text

		def fir():
			try:
				cls.rezultat = functie(*args, progres=progres, oprire=cls.oprire, **kw)
				if isinstance(cls.rezultat, dict):
					cls.text = cls.rezultat.get("mesaj", "")
			except Eroare as e:
				cls.eroare = str(e)
				cls.text = cls.eroare
			except Exception as e:
				cls.eroare = _t("Nu am putut termina: %s") % e
				cls.text = cls.eroare
			finally:
				cls.ocupat = False
		t = threading.Thread(target=fir, name="HdsPiconInstalare")
		t.daemon = True
		t.start()
		return True

	@classmethod
	def opreste(cls):
		if cls.oprire is not None:
			cls.oprire.set()

	@classmethod
	def stare(cls):
		return {"ocupat": cls.ocupat, "text": cls.text, "eroare": cls.eroare,
			"rezultat": cls.rezultat if isinstance(cls.rezultat, dict) else None}
