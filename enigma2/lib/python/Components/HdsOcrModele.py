# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsOcrModele.py: modelele de limba ale recunoasterii textului din subtitrarile DVB (tessdata_fast, Apache-2.0):
# cele din imagine, cele descarcate si cele care se pot descarca la cerere. O singura logica pentru ecranul de pe
# televizor (Screens/HdsOcrLimbi.py, din „Aspectul subtitrărilor”), pagina web /ocr-limbi
# (Plugins/Extensions/HdsWebControl/ocr_limbi_web.py) si clientul OCR (Components/HdsOcrSubtitrari.py).
#
# LOCURILE
#   - /usr/share/hds-ocr/tessdata: modelele din imagine (reteta hds-ocr-modele, numai limbile cu cele mai multe
#     subtitrari DVB); nu se sterg de aici;
#   - /usr/share/hds-ocr/modele.json: lista modelelor care se pot descarca (marimea si sha256 al fiecaruia, commitul
#     fix al depozitului tessdata_fast, adresa), plus /usr/share/hds-ocr/LICENSE (textul Apache-2.0); pachetul
#     hds-ocr-modele-lista;
#   - un stick sau un disc montat (nu in RAM, nu pe memoria interna, cel putin MINIM_MEDIU): <montare>/hds-ocr/tessdata,
#     cu <montare>/hds-ocr/LICENSE langa el. Asa modelele raman si dupa actualizarea imaginii;
#   - fara stick sau disc cu loc: /usr/share/hds-ocr/descarcate, numai cu acordul omului si numai daca raman libere cel
#     putin REZERVA_INTERN dupa descarcare (se pierd la actualizarea imaginii);
#   - /etc/enigma2/hdsatelit/ocr-modele.json: indexul modelelor puse pe stick sau disc (calea, marimea, sha256). Se
#     scrie numai la o descarcare, o stergere sau cand se gaseste un model copiat de mana, niciodata des;
#   - /tmp/hds-ocr-modele (RAM): cate o legatura spre fiecare model de pe un stick sau disc. Serviciul hds-ocr primeste
#     mereu aceleasi doua dosare in plus (--tessdata-extra: cel intern si acesta), deci un model nou se foloseste fara
#     repornirea serviciului, iar un stick scos da „fara model”, nu o eroare.
#
# FIRUL ENIGMA2 face numai lucruri scurte: citeste dosarul imaginii si pe cel intern (memoria interna), indexul si
# /proc/mounts (modeleInstalate) si pune legaturile in RAM (puneLegaturi). Tot ce atinge un stick sau un disc (statvfs,
# cautarea modelelor copiate de mana, scrierea, stergerea) si descarcarea merg pe fire; ecranul si pagina web citesc
# starea tinuta aici (instantaneu, lucrari) si o cer din nou cand trebuie (cereStare).
#
# DESCARCAREA: de la adresa din lista (commitul fix), cate un model odata, in <dosar>/.<model>.traineddata.part;
# fisierul trebuie sa aiba exact marimea si sha256 din lista, altfel se sterge; abia apoi primeste numele adevarat
# (os.replace), deci serviciul nu vede niciodata un model pe jumatate. Dupa o descarcare sau o stergere, generatie()
# creste: clientul OCR vede modelul nou la pagina urmatoare.
#
# PROPUNEREA: cand pista DVB aleasa are o limba fara model, dar modelul se poate descarca, receptorul intreaba o data
# (propune): "Da" deschide lista limbilor cu descarcarea pornita, "Nu mai întreba" tine minte limba
# (config.subtitles.hds_ocr_fara_intrebare). Limbile tinute minte se vad in lista limbilor si in pagina web, de unde
# se sterg (intreabaDinNou). La o pista fara limba declarata, cu limba ghicita dupa canal
# (Components/HdsOcrLimbaGhicita.py), intrebarea incepe cu "Limba ghicită a subtitrării" (propune(model, ghicita=True)).
#
# Modulul nu importa nimic din enigma2 la incarcare: probele de pe PC dau caile lor (Depozit(...)).

from __future__ import absolute_import

import errno
import hashlib
import json
import os
import re
import shutil
import threading
import time
import unicodedata

try:
	from urllib.request import Request, urlopen
except ImportError:
	from urllib2 import Request, urlopen

LISTA = "/usr/share/hds-ocr/modele.json"
LICENTA = "/usr/share/hds-ocr/LICENSE"
DOSAR_IMAGINE = "/usr/share/hds-ocr/tessdata"
DOSAR_INTERN = "/usr/share/hds-ocr/descarcate"
INDEX = "/etc/enigma2/hdsatelit/ocr-modele.json"
# legaturile spre modelele de pe stickuri, in RAM (se refac dupa fiecare schimbare; serviciul le primeste ca dosar)
DOSAR_LEGATURI = "/tmp/hds-ocr-modele"
MONTARI = "/proc/mounts"
SYS_BLOCK = "/sys/block"
DOSAR_MEDIU = "hds-ocr/tessdata"
LICENTA_MEDIU = "hds-ocr/LICENSE"
EXT = ".traineddata"

MB = 1000 * 1000                  # unitati zecimale, ca in textele de pe ecran (marimeText)
# in memoria interna raman libere cel putin atatia octeti dupa descarcare (setarile, listele, ghidul, jurnalele)
REZERVA_INTERN = 250 * MB
# pe un stick sau disc
REZERVA_MEDIU = 16 * MB
# sub atat nu e un stick sau disc adevarat (tmpfs-ul de /media are 64 KB), ca in Components/HdsStocare.py
MINIM_MEDIU = 64 * MB
TIMP_RETEA_S = 30
BUCATA = 64 * 1024
VARSTA_STARE_S = 30.0
MAX_JSON = 512 * 1024
AGENT = "HDSatelit/1.0 (hds-ocr-modele)"

FS_IN_MEMORIE = ("tmpfs", "ramfs", "devtmpfs", "overlay", "squashfs", "rootfs")
FS_RETEA = ("nfs", "nfs4", "cifs", "smb3", "smbfs", "fuse.sshfs", "autofs", "9p")
# unde monteaza receptorul stickurile si discurile (/media/hdd, /media/usb, /run/media/<eticheta>-sda1)
PREFIXE_MEDII = ("/media/", "/run/media/", "/mnt/")

# limbile din imagine, cand lista lipseste (reteta hds-ocr-modele, HDS_OCR_IMAGINE)
IMAGINE_IMPLICIT = ("ron", "fra", "pol", "deu", "ces", "hun", "spa", "ita")

# starea unui model
S_IMAGINE = "imagine"
S_DESCARCAT = "descarcat"
S_LIPSESTE = "lipseste"          # in index, dar stickul sau discul lui nu e pus (sau fisierul a disparut)
S_DE_DESCARCAT = "de_descarcat"
S_ASTEAPTA = "asteapta"
S_MERGE = "se_descarca"
S_STERGE = "se_sterge"
S_EROARE = "eroare"

# felul locului unde merge o descarcare
L_MEDIU = "mediu"
L_INTERN = "intern"
L_FARA = "fara_loc"


def N_(text):
	"""marcaj pentru xgettext (--keyword=N_), fara efect; textul se traduce la folosire"""
	return text


def _t(text):
	try:
		return _(text)
	except NameError:
		return text


def _jurnal(text):
	print("[HdsOcrModele] %s" % text)


# numele limbilor (msgid-uri englezesti, ca in Components/Language.py si HdsPisteLimbi.LIMBI_MENIU). „Persian (Farsi)”
# si nu „Persian”: acela e o intrare veche (#~) in mai multe po, iar msgfmt refuza acelasi msgid de doua ori.
# Numai limbile ale caror litere le au fontul subtitrarilor (HdsRegular) sau fontul de rezerva al skinului: georgiana,
# armeana, siriaca, azera (ə) si tatara (ә ө ү җ ң һ) lipsesc (textul citit s-ar desena fara litere, mai rau decat
# poza postului).
NUME = {
	"ron": N_("Romanian"), "fra": N_("French"), "pol": N_("Polish"), "deu": N_("German"), "ces": N_("Czech"),
	"hun": N_("Hungarian"), "spa": N_("Spanish"), "ita": N_("Italian"), "eng": N_("English"), "rus": N_("Russian"),
	"tur": N_("Turkish"), "por": N_("Portuguese"), "nld": N_("Dutch"), "slk": N_("Slovakian"),
	"bul": N_("Bulgarian"), "nor": N_("Norwegian"), "ell": N_("Greek"), "srp": N_("Serbian (Cyrillic)"),
	"srp_latn": N_("Serbian (Latin)"), "fin": N_("Finnish"), "swe": N_("Swedish"), "hrv": N_("Croatian"),
	"est": N_("Estonian"), "lit": N_("Lithuanian"), "slv": N_("Slovenian"), "lav": N_("Latvian"),
	"mkd": N_("Macedonian"), "dan": N_("Danish"), "ukr": N_("Ukrainian"), "sqi": N_("Albanian"),
	"cat": N_("Catalan"), "bel": N_("Belarusian"), "bos": N_("Bosnian"), "bre": N_("Breton"),
	"cos": N_("Corsican"), "cym": N_("Welsh"), "eus": N_("Basque"), "fao": N_("Faroese"), "fry": N_("Frisian"),
	"gla": N_("Scottish Gaelic"), "gle": N_("Irish"), "glg": N_("Galician"), "isl": N_("Icelandic"),
	"ltz": N_("Luxembourgish"), "mlt": N_("Maltese"), "oci": N_("Occitan"), "ara": N_("Arabic"),
	"heb": N_("Hebrew"), "fas": N_("Persian (Farsi)"), "kmr": N_("Kurdish"),
}

_TEXT_STARE = {
	S_IMAGINE: N_("în imagine"),
	S_DESCARCAT: N_("descărcat"),
	S_LIPSESTE: N_("lipsește, stickul nu e pus"),
	S_DE_DESCARCAT: N_("de descărcat"),
	S_ASTEAPTA: N_("așteaptă la rând"),
	S_MERGE: N_("se descarcă"),
	S_STERGE: N_("se șterge"),
	S_EROARE: N_("nu s-a descărcat"),
}

# grupele listei (ecranul si pagina web): in imagine, descarcate, de descarcat. O limba care se descarca ramane in locul
# ei din „de descărcat” (acolo unde s-a apasat OK sau butonul) pana se termina descarcarea.
GRUPA = {S_IMAGINE: 0, S_DESCARCAT: 1, S_STERGE: 1, S_LIPSESTE: 1, S_MERGE: 2, S_ASTEAPTA: 2, S_EROARE: 2,
	S_DE_DESCARCAT: 2}


def numeModel(model):
	return _t(NUME[model]) if model in NUME else model


def _cheieSortare(text):
	t = unicodedata.normalize("NFKD", u"%s" % text)
	return u"".join(c for c in t if not unicodedata.combining(c)).lower()


def marimeText(octeti):
	"""octeti -> „4,4 MB”, „850 KB”, „3,1 GB” (unitati zecimale, ca in lista modelelor si pe stickuri; virgula)"""
	if octeti is None:
		return u""
	if octeti >= 1000 ** 3:
		return (u"%.1f GB" % (octeti / 1e9)).replace(".", ",")
	if octeti >= 100 * 1000 ** 2:
		return u"%d MB" % int(round(octeti / 1e6))
	if octeti >= 1000 ** 2:
		return (u"%.1f MB" % (octeti / 1e6)).replace(".", ",")
	return u"%d KB" % max(1, int(round(octeti / 1000.0)))


_OCTAL = re.compile(br"\\([0-7]{3})")


def _decodeazaMontare(cale):
	"""calea din /proc/mounts (octeti) cu secventele \\ooo (spatiu, tab, backslash, literele UTF-8 ale unei etichete
	cu diacritice) inlocuite pe octeti, apoi citita ca UTF-8"""
	return _OCTAL.sub(lambda m: bytes(bytearray((int(m.group(1), 8),))), cale).decode("utf-8", "replace")


def _citesteJson(cale, maxim=MAX_JSON):
	try:
		with open(cale, "rb") as f:
			date = f.read(maxim + 1)
	except (IOError, OSError):
		return None
	if len(date) > maxim:
		return None
	try:
		return json.loads(date.decode("utf-8"))
	except (ValueError, UnicodeDecodeError):
		return None


def _scrieJson(cale, obiect):
	"""scrierea prin .nou + os.replace (un fisier pe jumatate nu ramane niciodata)"""
	d = os.path.dirname(cale)
	if d and not os.path.isdir(d):
		os.makedirs(d)
	tmp = cale + ".nou"
	with open(tmp, "wb") as f:
		f.write(json.dumps(obiect, ensure_ascii=True, indent=1, sort_keys=True).encode("ascii"))
		f.flush()
		os.fsync(f.fileno())
	os.replace(tmp, cale)


def _semn(cale):
	try:
		st = os.stat(cale)
	except OSError:
		return None
	return (st.st_mtime, st.st_size)


def _modeleDinDosar(dosar):
	try:
		return [f[:-len(EXT)] for f in os.listdir(dosar) if f.endswith(EXT) and not f.startswith(".")]
	except OSError:
		return []


class Oprita(Exception):
	pass


class EroareDescarcare(Exception):
	pass


class _Lucrare(object):
	"""o descarcare sau o stergere (starea o citesc ecranul si pagina web; o scrie firul de lucru)"""

	def __init__(self, model, fel, intern=False):
		self.model = model
		self.fel = fel                  # "descarcare" sau "stergere"
		self.intern = intern            # omul a spus da memoriei interne
		self.stare = "asteapta"         # asteapta, merge, gata, eroare, oprita
		self.primiti = 0
		self.total = 0
		self.mesaj = u""
		self.loc = u""
		self.oprita = False
		self.cand = time.time()

	def dict(self):
		return {"model": self.model, "fel": self.fel, "stare": self.stare, "primiti": self.primiti,
			"total": self.total, "procent": int(self.primiti * 100 / self.total) if self.total else 0,
			"mesaj": self.mesaj, "loc": self.loc}


class Depozit(object):
	"""modelele de pe receptor; caile se pot schimba pentru probe"""

	def __init__(self, lista=LISTA, licenta=LICENTA, dosar_imagine=DOSAR_IMAGINE, dosar_intern=DOSAR_INTERN,
			index=INDEX, montari=MONTARI, sys_block=SYS_BLOCK, dosar_legaturi=DOSAR_LEGATURI, deschide=None,
			ceas=time.time):
		self.cale_lista, self.licenta = lista, licenta
		self.dosar_imagine, self.dosar_intern = dosar_imagine, dosar_intern
		self.dosar_legaturi = dosar_legaturi
		# locul liber si dispozitivul radacinii (probele de pe PC dau altele)
		self.statvfs = getattr(os, "statvfs", None)
		self.devRadacina = lambda: os.stat("/").st_dev
		self.prefixe = PREFIXE_MEDII
		self.cale_index, self.cale_montari, self.sys_block = index, montari, sys_block
		self.deschide = deschide or self._deschide
		self.acum = ceas
		self.lacat = threading.RLock()
		self._lista = (None, None)             # (semn, date)
		self._index = (None, None)
		self._generatie = 0
		self._inst = None                       # ultima stare citita pe fir
		self._fir_stare = None
		self._lucrari = {}                      # model -> _Lucrare (cea mai noua)
		self._coada = []
		self._fir_lucru = None

	# ---------------------------------------------------------------- lista si indexul (fisiere mici, memoria interna)
	def lista(self):
		"""modele.json din imagine (tinut cat nu se schimba), sau {} daca lipseste"""
		semn = _semn(self.cale_lista)
		with self.lacat:
			if self._lista[0] == semn and self._lista[1] is not None:
				return self._lista[1]
		d = _citesteJson(self.cale_lista) if semn else None
		if not isinstance(d, dict) or d.get("format") != 1 or not isinstance(d.get("modele"), dict):
			d = {}
		with self.lacat:
			self._lista = (semn, d)
		return d

	def descarcabile(self):
		"""{model: {"marime", "sha256"}} din lista, numai limbile cunoscute"""
		return dict((m, v) for m, v in (self.lista().get("modele") or {}).items()
			if m in NUME and isinstance(v, dict) and isinstance(v.get("marime"), int) and len(v.get("sha256") or "") == 64)

	def inImagineDupaLista(self):
		return tuple(self.lista().get("in_imagine") or IMAGINE_IMPLICIT)

	def adresa(self, model):
		a = self.lista().get("adresa") or ""
		return a.replace("{model}", model) if "{model}" in a else ""

	def index(self):
		semn = _semn(self.cale_index)
		with self.lacat:
			if self._index[0] == semn and self._index[1] is not None:
				return self._index[1]
		d = _citesteJson(self.cale_index) if semn else None
		if not isinstance(d, dict) or not isinstance(d.get("modele"), dict):
			d = {"format": 1, "modele": {}}
		with self.lacat:
			self._index = (semn, d)
		return d

	def _scrieIndex(self, modele):
		with self.lacat:
			d = {"format": 1, "modele": modele}
			_scrieJson(self.cale_index, d)
			self._index = (_semn(self.cale_index), d)

	def generatie(self):
		"""creste dupa fiecare schimbare a modelelor (descarcare, stergere, model gasit pe un stick)"""
		return self._generatie

	def _schimbat(self):
		with self.lacat:
			self._generatie += 1

	# ---------------------------------------------------------------- montarile (numai /proc/mounts)
	def montari(self):
		rez = []
		try:
			with open(self.cale_montari, "rb") as f:
				for linie in f.read(256 * 1024).splitlines():
					p = linie.split()
					if len(p) >= 3:
						rez.append((_decodeazaMontare(p[1]), p[2].decode("utf-8", "replace"),
							p[0].decode("utf-8", "replace")))
		except (IOError, OSError):
			pass
		return rez

	def candidate(self, montari=None):
		"""montarile care pot fi un stick sau un disc: un dispozitiv /dev/..., sub /media, /run/media sau /mnt, nu
		radacina, nu in RAM, nu in retea"""
		montari = self.montari() if montari is None else montari
		radacina = [d for p, f, d in montari if p == "/"]
		rez = []
		for punct, fel, disp in montari:
			if not disp.startswith("/dev/") or fel in FS_IN_MEMORIE or fel in FS_RETEA:
				continue
			if not punct.startswith(self.prefixe):
				continue
			if disp in radacina:
				continue
			if punct not in [c[0] for c in rez]:
				rez.append((punct, fel, disp))
		return rez

	# ---------------------------------------------------------------- pe firul enigma2: ce modele sunt, unde
	def modeleInstalate(self):
		"""{model: (dosar, loc)} cu loc „imagine”, „intern” sau „mediu”. Numai dosarul imaginii si cel intern se citesc;
		modelele de pe stick sau disc vin din index, cand montarea lor e pusa (fara niciun acces la stick)."""
		rez = {}
		for m in _modeleDinDosar(self.dosar_imagine):
			rez[m] = (self.dosar_imagine, S_IMAGINE)
		for m in _modeleDinDosar(self.dosar_intern):
			rez.setdefault(m, (self.dosar_intern, L_INTERN))
		puncte = set(p for p, f, d in self.candidate())
		for m, e in (self.index().get("modele") or {}).items():
			if isinstance(e, dict) and e.get("punct") in puncte and e.get("cale"):
				rez.setdefault(m, (os.path.dirname(e["cale"]), L_MEDIU))
		return rez

	def dosareServiciu(self):
		"""dosarele date serviciului cu --tessdata-extra, aceleasi mereu (serviciul nu trebuie pornit din nou cand apare
		un model): memoria interna si dosarul de legaturi din RAM spre modelele de pe stickuri (puneLegaturi)"""
		return [self.dosar_intern, self.dosar_legaturi]

	def puneLegaturi(self, instalate=None):
		"""In dosarul de legaturi (RAM, /tmp): cate o legatura spre fiecare model de pe un stick sau disc; legaturile
		vechi se scot. O legatura spre un stick scos nu duce nicaieri, iar serviciul raspunde „fara model”. Intoarce
		modelele legate."""
		instalate = self.modeleInstalate() if instalate is None else instalate
		dorite = dict((m + EXT, os.path.join(d, m + EXT)) for m, (d, loc) in instalate.items() if loc == L_MEDIU)
		d = self.dosar_legaturi
		try:
			if not os.path.isdir(d):
				os.makedirs(d)
			for nume in os.listdir(d):
				cale = os.path.join(d, nume)
				if nume not in dorite or not os.path.islink(cale) or os.readlink(cale) != dorite[nume]:
					try:
						os.remove(cale)
					except OSError:
						pass
			for nume, tinta in dorite.items():
				cale = os.path.join(d, nume)
				if not os.path.islink(cale):
					os.symlink(tinta, cale)
		except (OSError, NotImplementedError, AttributeError) as e:
			_jurnal("legaturile modelelor: %s" % e)
		return sorted(m[:-len(EXT)] for m in dorite)

	def textScurt(self):
		"""valoarea randului din „Aspectul subtitrărilor”: „8 în imagine, 2 descărcate”"""
		inst = self.modeleInstalate()
		imagine = len([m for m, (d, l) in inst.items() if l == S_IMAGINE])
		desc = len(inst) - imagine
		if not desc:
			return _t("%d în imagine") % imagine
		if desc == 1:
			return _t("%d în imagine, una descărcată") % imagine
		return _t("%d în imagine, %d descărcate") % (imagine, desc)

	# ---------------------------------------------------------------- starea (pe fir)
	def cereStare(self, din_nou=False):
		"""(instantaneu sau None, se_citeste): ultima stare a stickurilor si a modelelor; porneste citirea pe fir cand e
		veche, lipseste sau se cere din nou. Pe firul enigma2 nu se asteapta nimic."""
		with self.lacat:
			inst = self._inst
			proaspat = inst is not None and self.acum() - inst["cand"] < VARSTA_STARE_S
			if (din_nou or not proaspat) and self._fir_stare is None:
				self._fir_stare = threading.Thread(target=self._citesteStarea, name="HdsOcrModele-stare")
				self._fir_stare.daemon = True
				self._fir_stare.start()
			return inst, self._fir_stare is not None

	def instantaneu(self):
		with self.lacat:
			return self._inst

	def _citesteStarea(self):
		try:
			inst = self.scaneaza()
		except Exception as e:
			_jurnal("starea nu se poate citi: %s" % e)
			inst = None
		with self.lacat:
			if inst is not None:
				self._inst = inst
			self._fir_stare = None

	def _mediu(self, punct, fel, disp, dev_radacina):
		"""un stick sau disc: liber, total, se poate scrie, e scos din port (removable); None daca nu e unul adevarat"""
		try:
			if not os.path.isdir(punct) or os.stat(punct).st_dev == dev_radacina:
				return None
			s = self.statvfs(punct)
		except (OSError, AttributeError, TypeError):
			return None
		total = s.f_blocks * s.f_frsize
		if total < MINIM_MEDIU:
			return None
		baza = os.path.basename(disp)
		while baza and baza[-1].isdigit() and not os.path.isdir(os.path.join(self.sys_block, baza)):
			baza = baza[:-1]
		if baza.endswith("p") and not os.path.isdir(os.path.join(self.sys_block, baza)):
			baza = baza[:-1]
		stick = False
		try:
			with open(os.path.join(self.sys_block, baza, "removable"), encoding="ascii", errors="replace") as f:
				stick = f.read(4).strip() == "1"
		except (IOError, OSError):
			stick = disp.startswith("/dev/mmcblk")
		return {"punct": punct, "fel": fel, "dispozitiv": disp, "liber": s.f_bavail * s.f_frsize, "total": total,
			"scriere": os.access(punct, os.W_OK), "stick": stick,
			"dosar": os.path.join(punct, DOSAR_MEDIU), "are_modele": os.path.isdir(os.path.join(punct, DOSAR_MEDIU))}

	def scaneaza(self):
		"""Pe fir: stickurile si discurile, locul liber, modelele din index (daca mai sunt) si modelele copiate de mana
		pe un stick (marimea si sha256 din lista; puse in index). Intoarce instantaneul.
		Un model aflat deja in index pe un mediu pus (cu fisierul acolo) nu se mai verifica si nu se muta, chiar daca
		are o copie si pe alt mediu: indexul de pe memoria interna nu se rescrie la fiecare scanare. Cand scanarea
		schimba ceva, schimbarile ei se pun peste indexul citit din nou sub lacat, deci o descarcare terminata in
		timpul scanarii ramane in el."""
		try:
			dev_radacina = self.devRadacina()
		except OSError:
			dev_radacina = None
		medii = []
		for punct, fel, disp in self.candidate():
			m = self._mediu(punct, fel, disp, dev_radacina)
			if m is not None and m["punct"] not in [x["punct"] for x in medii]:
				medii.append(m)
		try:
			s = self.statvfs(self.dosar_intern if os.path.isdir(self.dosar_intern) else os.path.dirname(self.dosar_intern))
			intern_liber = s.f_bavail * s.f_frsize
		except (OSError, AttributeError, TypeError):
			intern_liber = 0
		desc = self.descarcabile()
		idx = dict((m, dict(e)) for m, e in (self.index().get("modele") or {}).items() if isinstance(e, dict))
		puncte = set(x["punct"] for x in medii)
		lipsa = []
		scoase = {}             # model -> intrarea din index al carei fisier nu mai e pe mediul pus
		gasite = {}             # model -> intrarea noua (copiat de mana, sau gasit pe alt mediu decat cel scos)
		for m, e in idx.items():
			if e.get("punct") not in puncte:
				lipsa.append(m)
			elif not os.path.isfile(e.get("cale") or ""):
				scoase[m] = e
		self._curataParti([x["dosar"] for x in medii if x["are_modele"]] + [self.dosar_intern])
		for x in medii:
			if not x["are_modele"]:
				continue
			for m in _modeleDinDosar(x["dosar"]):
				if m not in desc or m in gasite:
					continue
				e = idx.get(m)
				if e is not None and m not in scoase and e.get("punct") in puncte:
					continue
				cale = os.path.join(x["dosar"], m + EXT)
				try:
					if os.path.getsize(cale) != desc[m]["marime"] or _sha256(cale) != desc[m]["sha256"]:
						continue
				except (IOError, OSError):
					continue
				gasite[m] = {"cale": cale, "punct": x["punct"], "marime": desc[m]["marime"], "sha256": desc[m]["sha256"],
					"cand": int(self.acum())}
		if scoase or gasite:
			with self.lacat:
				nou = dict((m, dict(e)) for m, e in (self.index().get("modele") or {}).items() if isinstance(e, dict))
				for m, e in scoase.items():
					if nou.get(m) == e:
						del nou[m]
				for m, e in gasite.items():
					if nou.get(m) is None or nou.get(m) == idx.get(m):
						nou[m] = e
				try:
					self._scrieIndex(nou)
				except (IOError, OSError) as e:
					_jurnal("indexul nu se poate scrie: %s" % e)
			self._schimbat()
		lipsa = [m for m in lipsa if m not in gasite]
		return {"cand": self.acum(), "medii": medii, "intern_liber": intern_liber, "lipsa": sorted(lipsa)}

	def _curataParti(self, dosare):
		"""sterge .<model>.traineddata.part ramase de la o descarcare intrerupta (curent, stick scos), afara de cele ale
		descarcarii de acum"""
		with self.lacat:
			in_lucru = set("." + l.model + EXT + ".part" for l in self._lucrari.values() if l.stare in ("asteapta", "merge"))
		for d in dosare:
			try:
				nume = [f for f in os.listdir(d) if f.startswith(".") and f.endswith(EXT + ".part")]
			except OSError:
				continue
			for f in nume:
				if f not in in_lucru:
					try:
						os.remove(os.path.join(d, f))
					except OSError:
						pass

	# ---------------------------------------------------------------- unde merge o descarcare
	def plan(self, marime, inst=None):
		"""{"fel": mediu | intern | fara_loc, "dosar", "punct", "liber", "stick", "text"} pentru un model de `marime`.
		Intai stickul sau discul care are deja modele, apoi cel cu cel mai mult loc; memoria interna numai daca nu e
		niciunul potrivit (atunci descarcarea cere acordul omului)."""
		inst = inst if inst is not None else self.instantaneu()
		if inst is None:
			return None
		medii = sorted([x for x in inst["medii"] if x["scriere"]], key=lambda x: (not x["are_modele"], -x["liber"]))
		for x in medii:
			if x["liber"] >= marime + REZERVA_MEDIU:
				return {"fel": L_MEDIU, "dosar": x["dosar"], "punct": x["punct"], "liber": x["liber"], "stick": x["stick"],
					"text": textLoc(L_MEDIU, x["liber"], x["stick"])}
		if inst["intern_liber"] - marime >= REZERVA_INTERN:
			return {"fel": L_INTERN, "dosar": self.dosar_intern, "punct": "", "liber": inst["intern_liber"],
				"stick": False, "text": textLoc(L_INTERN, inst["intern_liber"]), "medii": len(inst["medii"])}
		return {"fel": L_FARA, "dosar": "", "punct": "", "liber": inst["intern_liber"], "stick": False,
			"text": _t("Nu e loc: niciun stick sau disc cu loc liber, iar în memoria internă ar rămâne sub %s.")
			% marimeText(REZERVA_INTERN), "medii": len(inst["medii"])}

	# ---------------------------------------------------------------- randurile (ecranul si pagina web)
	def _felMediu(self, model, idx, inst):
		"""„stick” sau „disc” pentru un model de pe un mediu (dupa /sys/block/<disc>/removable, citit la scanare); „”
		cand nu se stie inca"""
		punct = (idx.get(model) or {}).get("punct") if isinstance(idx.get(model), dict) else None
		for x in (inst or {}).get("medii") or []:
			if punct and x.get("punct") == punct:
				return "stick" if x.get("stick") else "disc"
		return ""

	def randuri(self, inst=None):
		"""Toate limbile: cele din imagine, cele descarcate, cele care se descarca, apoi celelalte, fiecare grupa dupa
		nume. Fiecare rand: model, nume, marime, marime_text, stare, stare_text, loc, mediu (stick, disc), procent,
		detaliu."""
		inst = inst if inst is not None else self.instantaneu()
		instalate = self.modeleInstalate()
		desc = self.descarcabile()
		idx = self.index().get("modele") or {}
		lucrari = self.lucrari()
		lipsa = set(inst["lipsa"]) if inst else set()
		rez = []
		for m in set(desc) | set(instalate):
			if m not in NUME:
				continue
			marime = (desc.get(m) or {}).get("marime")
			if marime is None and m in instalate:
				try:
					marime = os.path.getsize(os.path.join(instalate[m][0], m + EXT)) if instalate[m][1] != L_MEDIU else None
				except OSError:
					marime = None
			l = lucrari.get(m)
			loc = u""
			mediu = u""
			procent = None
			if m in instalate and instalate[m][1] == S_IMAGINE:
				stare = S_IMAGINE
			elif l is not None and l["stare"] in ("asteapta", "merge"):
				stare = {("descarcare", "asteapta"): S_ASTEAPTA, ("descarcare", "merge"): S_MERGE}.get(
					(l["fel"], l["stare"]), S_STERGE)
				procent = l["procent"] if l["fel"] == "descarcare" else None
			elif m in instalate:
				stare = S_DESCARCAT
				loc = L_INTERN if instalate[m][1] == L_INTERN else L_MEDIU
				if loc == L_MEDIU:
					mediu = self._felMediu(m, idx, inst)
			elif m in idx and m in lipsa:
				stare = S_LIPSESTE
			elif l is not None and l["stare"] == "eroare" and l["fel"] == "descarcare":
				stare = S_EROARE
			else:
				stare = S_DE_DESCARCAT
			rez.append({"model": m, "nume": numeModel(m), "marime": marime, "marime_text": marimeText(marime),
				"stare": stare, "stare_text": textStare(stare, loc, procent, mediu), "loc": loc, "mediu": mediu,
				"procent": procent, "descarcabil": m in desc, "mesaj": (l or {}).get("mesaj") or u"",
				"detaliu": self.detaliu(m, stare, marime, loc, l, inst, mediu)})
		rez.sort(key=lambda r: (GRUPA.get(r["stare"], 3), _cheieSortare(r["nume"])))
		return rez

	def detaliu(self, m, stare, marime, loc, lucrare, inst, mediu=u""):
		"""textul de sub lista pentru randul ales (acelasi in pagina web)"""
		nume = numeModel(m)
		if stare == S_IMAGINE:
			return _t("%s: modelul e în imagine și merge fără descărcare.") % nume
		if stare == S_DESCARCAT:
			if loc == L_MEDIU and mediu == "stick":
				return _t("%s: modelul (%s) e descărcat pe stick. OK îl șterge.") % (nume, marimeText(marime))
			if loc == L_MEDIU and mediu == "disc":
				return _t("%s: modelul (%s) e descărcat pe disc. OK îl șterge.") % (nume, marimeText(marime))
			if loc == L_MEDIU:
				return _t("%s: modelul (%s) e descărcat pe stick sau disc. OK îl șterge.") % (nume, marimeText(marime))
			return _t("%s: modelul (%s) e descărcat în memoria internă. OK îl șterge.") % (nume, marimeText(marime))
		if stare in (S_MERGE, S_ASTEAPTA):
			return _t("%s: se descarcă modelul (%s). OK oprește descărcarea.") % (nume, marimeText(marime))
		if stare == S_STERGE:
			return _t("%s: modelul se șterge.") % nume
		if stare == S_LIPSESTE:
			return _t("%s: modelul e pe un stick sau disc care nu e pus acum. Pune-l la loc, sau apasă OK: îl descarci "
				"din nou sau îl scoți din listă.") % nume
		p = self.plan(marime or 0, inst)
		inceput = u""
		if stare == S_EROARE and lucrare is not None and lucrare.get("mesaj"):
			inceput = lucrare["mesaj"] + u" "
		if p is None:
			return inceput + _t("%s: modelul are %s. Se caută locul pentru el.") % (nume, marimeText(marime))
		if p["fel"] == L_FARA:
			return inceput + p["text"]
		return inceput + _t("%s: modelul are %s. OK îl descarcă %s.") % (nume, marimeText(marime), p["text"])

	# ---------------------------------------------------------------- descarcarea si stergerea
	def lucrari(self):
		with self.lacat:
			return dict((m, l.dict()) for m, l in self._lucrari.items())

	def inLucru(self):
		with self.lacat:
			return any(l.stare in ("asteapta", "merge") for l in self._lucrari.values())

	def descarca(self, model, intern=False):
		"""Porneste descarcarea (pe fir). {"result", "message", "cere_intern", "intrebare"}: cand singurul loc e memoria
		interna si omul nu a spus inca da, nu porneste nimic si intoarce intrebarea (cu locul liber)."""
		desc = self.descarcabile()
		nume = numeModel(model)
		if model not in desc:
			return {"result": False, "message": _t("Limba aceasta nu se poate descărca.")}
		if model in self.modeleInstalate():
			return {"result": False, "message": _t("%s: modelul e deja pe receptor.") % nume}
		with self.lacat:
			l = self._lucrari.get(model)
			if l is not None and l.stare in ("asteapta", "merge"):
				return {"result": True, "message": _t("%s: modelul se descarcă deja.") % nume}
		inst, _se_citeste = self.cereStare()
		p = self.plan(desc[model]["marime"], inst)
		if p is None:
			return {"result": False, "asteapta": True, "message": _t("Se caută un stick sau un disc. Încearcă din nou "
				"peste o clipă.")}
		if p["fel"] == L_FARA:
			return {"result": False, "message": p["text"]}
		if p["fel"] == L_INTERN and not intern:
			return {"result": False, "cere_intern": True, "message": u"", "intrebare": textIntrebareIntern(model,
				desc[model]["marime"], p["liber"], p.get("medii", 0))}
		l = _Lucrare(model, "descarcare", intern=intern)
		l.total = desc[model]["marime"]
		l.loc = p["text"]
		self._pune(l)
		return {"result": True, "message": _t("%s: modelul se descarcă %s.") % (nume, p["text"])}

	def sterge(self, model):
		inst = self.modeleInstalate()
		nume = numeModel(model)
		if model not in inst:
			idx = self.index().get("modele") or {}
			if model in idx:
				m2 = dict(idx)
				del m2[model]
				try:
					self._scrieIndex(m2)
				except (IOError, OSError):
					pass
				self._schimbat()
				return {"result": True, "message": _t("%s: modelul a ieșit din listă.") % nume}
			return {"result": False, "message": _t("%s: modelul nu e descărcat.") % nume}
		if inst[model][1] == S_IMAGINE:
			return {"result": False, "message": _t("Modelele din imagine nu se șterg.")}
		with self.lacat:
			l = self._lucrari.get(model)
			if l is not None and l.stare in ("asteapta", "merge"):
				return {"result": False, "message": _t("%s: modelul e în lucru acum.") % nume}
		self._pune(_Lucrare(model, "stergere"))
		return {"result": True, "message": _t("%s: modelul se șterge.") % nume}

	def opreste(self, model):
		with self.lacat:
			l = self._lucrari.get(model)
			if l is not None and l.fel == "descarcare" and l.stare == "gata":
				# descarcarea s-a terminat cat era deschisa intrebarea
				return {"result": False, "message": _t("%s: modelul s-a descărcat deja.") % numeModel(model)}
			if l is None or l.fel != "descarcare" or l.stare not in ("asteapta", "merge"):
				return {"result": False, "message": _t("%s: nicio descărcare nu merge.") % numeModel(model)}
			l.oprita = True
			if l.stare == "asteapta":
				l.stare = "oprita"
				if l in self._coada:
					self._coada.remove(l)
		return {"result": True, "message": _t("Descărcarea se oprește.")}

	def _pune(self, lucrare):
		with self.lacat:
			self._lucrari[lucrare.model] = lucrare
			self._coada.append(lucrare)
			if self._fir_lucru is None:
				self._fir_lucru = threading.Thread(target=self._lucreaza, name="HdsOcrModele-lucru")
				self._fir_lucru.daemon = True
				self._fir_lucru.start()

	def _lucreaza(self):
		while True:
			with self.lacat:
				if not self._coada:
					self._fir_lucru = None
					return
				l = self._coada.pop(0)
				if l.oprita:
					continue
				l.stare = "merge"
			try:
				if l.fel == "descarcare":
					self._descarca(l)
				else:
					self._sterge(l)
				l.stare = "gata"
			except Oprita:
				l.stare = "oprita"
				l.mesaj = _t("Descărcarea a fost oprită.")
			except Exception as e:
				l.stare = "eroare"
				l.mesaj = e.args[0] if isinstance(e, EroareDescarcare) else _t("Eroare: %s.") % e
				_jurnal("%s %s: %s" % (l.fel, l.model, e))
			self._schimbat()
			try:
				inst = self.scaneaza()
				with self.lacat:
					self._inst = inst
			except Exception as e:
				_jurnal("starea dupa %s: %s" % (l.fel, e))

	def _deschide(self, adresa):
		cerere = Request(adresa)
		cerere.add_header("User-Agent", AGENT)
		return urlopen(cerere, timeout=TIMP_RETEA_S)

	def _descarca(self, l):
		desc = self.descarcabile()[l.model]
		inst = self.scaneaza()
		with self.lacat:
			self._inst = inst
		if l.model in self.modeleInstalate():
			# scanarea de mai sus l-a gasit pe un stick (copiat de mana, sau pe un stick mutat in alt port)
			l.mesaj = _t("%s: modelul e deja pe receptor.") % numeModel(l.model)
			return
		p = self.plan(desc["marime"], inst)
		if p["fel"] == L_FARA or (p["fel"] == L_INTERN and not l.intern):
			raise EroareDescarcare(p["text"] if p["fel"] == L_FARA else _t("Stickul sau discul nu mai e pus."))
		adresa = self.adresa(l.model)
		if not adresa:
			raise EroareDescarcare(_t("Lista modelelor nu are adresa de descărcare."))
		l.loc = p["text"]
		dosar = p["dosar"]
		try:
			if not os.path.isdir(dosar):
				os.makedirs(dosar)
		except OSError as e:
			raise EroareDescarcare(_t("Nu pot crea dosarul modelelor: %s.") % (e.strerror or e))
		final = os.path.join(dosar, l.model + EXT)
		parte = os.path.join(dosar, "." + l.model + EXT + ".part")
		h = hashlib.sha256()
		l.primiti = 0
		try:
			try:
				r = self.deschide(adresa)
			except Exception as e:
				_jurnal("descarcarea %s, cererea: %r" % (l.model, e))
				raise EroareDescarcare(_ceasScurt(e) or _t("Modelul nu se poate descărca: %s.") % _scurtEroare(e))
			try:
				with open(parte, "wb") as f:
					while True:
						if l.oprita:
							raise Oprita()
						try:
							bucata = r.read(BUCATA)
						except Exception as e:
							_jurnal("descarcarea %s, citirea: %r" % (l.model, e))
							raise EroareDescarcare(_t("Descărcarea s-a întrerupt: %s.") % _scurtEroare(e))
						if not bucata:
							break
						l.primiti += len(bucata)
						if l.primiti > desc["marime"]:
							raise EroareDescarcare(_t("Fișierul primit e mai mare decât cel din listă. Nu a fost păstrat."))
						h.update(bucata)
						try:
							f.write(bucata)
						except (IOError, OSError) as e:
							raise EroareDescarcare(_t("Nu pot scrie %s: %s.") % (p["text"], e.strerror or e))
					f.flush()
					os.fsync(f.fileno())
			finally:
				try:
					r.close()
				except Exception:
					pass
			if l.primiti != desc["marime"] or h.hexdigest() != desc["sha256"]:
				raise EroareDescarcare(_t("Fișierul primit nu e cel din listă (sha256). Nu a fost păstrat."))
			os.replace(parte, final)
		except BaseException:
			try:
				os.remove(parte)
			except OSError:
				pass
			raise
		if p["fel"] == L_MEDIU:
			lic = os.path.join(p["punct"], LICENTA_MEDIU)
			if not os.path.exists(lic) and os.path.isfile(self.licenta):
				try:
					shutil.copyfile(self.licenta, lic)
				except (IOError, OSError) as e:
					_jurnal("licenta nu se poate copia: %s" % e)
			with self.lacat:
				idx = dict(self.index().get("modele") or {})
				idx[l.model] = {"cale": final, "punct": p["punct"], "marime": desc["marime"], "sha256": desc["sha256"],
					"cand": int(self.acum())}
				try:
					self._scrieIndex(idx)
				except (IOError, OSError) as e:
					_jurnal("indexul nu se poate scrie: %s" % e)
		l.mesaj = _t("%s: modelul e descărcat.") % numeModel(l.model)
		_jurnal("%s descarcat in %s (%d octeti)" % (l.model, dosar, l.primiti))

	def _sterge(self, l):
		inst = self.modeleInstalate()
		if l.model not in inst or inst[l.model][1] == S_IMAGINE:
			return
		cale = os.path.join(inst[l.model][0], l.model + EXT)
		try:
			os.remove(cale)
		except OSError as e:
			if e.errno != errno.ENOENT:
				raise EroareDescarcare(_t("Modelul nu se poate șterge: %s.") % (e.strerror or e))
		with self.lacat:
			idx = dict(self.index().get("modele") or {})
			if l.model in idx:
				del idx[l.model]
				try:
					self._scrieIndex(idx)
				except (IOError, OSError) as e:
					_jurnal("indexul nu se poate scrie: %s" % e)
		l.mesaj = _t("%s: modelul e șters.") % numeModel(l.model)

	# ---------------------------------------------------------------- licentele
	def licenteDescarcate(self):
		"""Modelele descarcate dupa construirea imaginii, pentru ecranul „Licențe”: nume, fisier, licenta (Apache-2.0),
		sursa (commitul fix) si calea textului licentei."""
		lista = self.lista()
		rez = []
		for m, (d, loc) in sorted(self.modeleInstalate().items()):
			if loc == S_IMAGINE:
				continue
			rez.append({"model": m, "nume": numeModel(m), "fisier": os.path.join(d, m + EXT),
				"licenta": lista.get("licenta") or "Apache-2.0", "commit": lista.get("commit") or "",
				"sursa": self.adresa(m), "text": self.licenta})
		return rez


def _sha256(cale):
	h = hashlib.sha256()
	with open(cale, "rb") as f:
		for bucata in iter(lambda: f.read(1 << 20), b""):
			h.update(bucata)
	return h.hexdigest()


def _ceasScurt(e):
	"""Un rand „ceasul e în urmă” (Components/HdsCeasHttps.py) cand certificatul serverului cade din cauza ceasului
	receptorului, altfel None (si ramane mesajul obisnuit, _scurtEroare)."""
	try:
		from Components import HdsCeasHttps
		return HdsCeasHttps.scurt(e)
	except Exception:
		return None


def _scurtEroare(e):
	"""o fraza scurta pentru om dupa felul erorii de retea; textul brut al exceptiei merge numai in jurnal. Functia nu
	foloseste nume din modul (importurile sunt aici, iar _ vine din builtins, ca in tot enigma2; xgettext ia textele
	din _())."""
	import errno as er
	import socket as so
	try:
		import ssl as sl
	except ImportError:
		sl = None
	try:
		_
	except NameError:
		return u"eroare de rețea"
	cod = getattr(e, "code", None)
	if isinstance(cod, int) and hasattr(e, "headers"):
		return _("serverul a refuzat cererea (HTTP %d)") % cod
	c = getattr(e, "reason", None)
	c = c if isinstance(c, BaseException) else e
	if isinstance(c, so.timeout) or "timed out" in (u"%s" % (c,)):
		return _("serverul modelelor nu răspunde la timp")
	if isinstance(c, so.gaierror):
		return _("nu găsesc serverul modelelor; verifică legătura la internet")
	if sl is not None and ("CERTIFICATE_VERIFY_FAILED" in (u"%s" % (c,)) or isinstance(c, getattr(sl,
			"SSLCertVerificationError", ()))):
		return _("certificatul serverului nu se poate verifica; verifică ora receptorului")
	if sl is not None and isinstance(c, sl.SSLError):
		return _("legătura sigură cu serverul nu merge")
	n = getattr(c, "errno", None)
	if isinstance(c, ConnectionRefusedError) or n == er.ECONNREFUSED:
		return _("serverul modelelor nu răspunde (legătura e refuzată)")
	if n in (er.ENETUNREACH, er.EHOSTUNREACH, getattr(er, "ENETDOWN", -1)):
		return _("receptorul nu are legătură la internet")
	if isinstance(c, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)):
		return _("legătura s-a întrerupt")
	return _("eroare de rețea")


def textStare(stare, loc=u"", procent=None, mediu=u""):
	if stare == S_DESCARCAT:
		if loc != L_MEDIU:
			return _t("descărcat, în memoria internă")
		if mediu == "stick":
			return _t("descărcat, pe stick")
		if mediu == "disc":
			return _t("descărcat, pe disc")
		return _t("descărcat, pe stick sau disc")
	if stare == S_MERGE and procent is not None:
		return _t("se descarcă, %d%%") % procent
	return _t(_TEXT_STARE.get(stare, stare))


def textLoc(fel, liber, stick=False):
	if fel == L_MEDIU:
		return (_t("pe stick (liber: %s)") if stick else _t("pe disc (liber: %s)")) % marimeText(liber)
	return _t("în memoria internă (liber: %s)") % marimeText(liber)


def textIntrebareIntern(model, marime, liber, medii=0):
	inceput = _t("Nu am găsit un stick sau un disc cu loc liber.") if medii else _t("Nu e pus niciun stick sau disc.")
	return inceput + u" " + _t("%s: modelul are %s. Îl pun în memoria internă a receptorului? Spațiul liber acolo: %s. "
		"La o actualizare a imaginii modelul se pierde; îl descarci din nou din lista limbilor.") % (numeModel(model),
		marimeText(marime), marimeText(liber))


def textLocSus(p):
	"""a doua fraza din textul de sus al listei (ecranul si pagina web): unde merge un model nou si cat loc e acolo"""
	if p is None:
		return _t("Se caută stickurile și discurile...")
	if p["fel"] == L_FARA:
		return p["text"]
	if p["fel"] == L_INTERN:
		if p.get("medii"):
			return _t("Stickul sau discul nu are loc liber sau nu se poate scrie pe el: un model nou poate merge în "
				"memoria internă (liber: %s), numai dacă spui da.") % marimeText(p["liber"])
		return _t("Nu e pus niciun stick sau disc: un model nou poate merge în memoria internă (liber: %s), numai dacă "
			"spui da.") % marimeText(p["liber"])
	return _t("Modelele noi merg %s.") % p["text"]


# ------------------------------------------------------------------ depozitul receptorului

_DEPOZIT = [None]


def depozit():
	if _DEPOZIT[0] is None:
		_DEPOZIT[0] = Depozit()
	return _DEPOZIT[0]


def modeleInstalate():
	return depozit().modeleInstalate()


def dosareServiciu():
	return depozit().dosareServiciu()


def generatie():
	return depozit().generatie()


def textScurt():
	return depozit().textScurt()


def licenteDescarcate():
	"""Pentru Components/HdsLicente.py: modelele descarcate dupa construire (fiecare cu licenta si textul ei)."""
	try:
		return depozit().licenteDescarcate()
	except Exception as e:
		_jurnal("licentele modelelor: %s" % e)
		return []


# ------------------------------------------------------------------ propunerea de descarcare

_INTREBATE = set()          # limbile propuse de la pornire (o singura data fiecare)


def initConfig():
	"""config.subtitles.hds_ocr_fara_intrebare: modelele pentru care omul a spus "Nu mai întreba" (separate prin
	virgula)."""
	from Components.config import config, ConfigSubsection, ConfigText
	if "subtitles" not in config.content.items:
		config.subtitles = ConfigSubsection()
	s = config.subtitles
	if "hds_ocr_fara_intrebare" not in s.content.items:
		s.hds_ocr_fara_intrebare = ConfigText(default="", fixed_size=False)
	return s


def _faraIntrebare():
	try:
		return set(x for x in initConfig().hds_ocr_fara_intrebare.value.split(",") if x)
	except Exception:
		return set()


def _nuMaiIntreba(model):
	try:
		s = initConfig()
		v = _faraIntrebare() | set((model,))
		s.hds_ocr_fara_intrebare.value = ",".join(sorted(v))
		s.hds_ocr_fara_intrebare.save()
		from Components.config import configfile
		configfile.save()
	except Exception as e:
		_jurnal("alegerea nu se poate salva: %s" % e)


def faraIntrebare():
	"""modelele pentru care omul a spus „Nu mai întreba pentru limba asta”, dupa nume"""
	return sorted(_faraIntrebare(), key=lambda m: _cheieSortare(numeModel(m)))


def textRandFaraIntrebare(modele=None, cel_mult=2):
	"""randul din lista limbilor (ecranul): „Întreabă din nou pentru: Bulgară, Slovacă”, cu cel mult `cel_mult` nume
	(apoi „și încă 2”), ca sa incapa pe un rand; „” cand nu e niciuna"""
	modele = faraIntrebare() if modele is None else modele
	if not modele:
		return u""
	nume = u", ".join(numeModel(m) for m in modele[:cel_mult])
	if len(modele) > cel_mult:
		nume += u" " + _t("și încă %d") % (len(modele) - cel_mult)
	return _t("Întreabă din nou pentru: %s") % nume


def intreabaDinNou():
	"""sterge "Nu mai întreba" pentru toate limbile: la o subtitrare intr-o limba fara model, intrebarea vine din nou"""
	vechi = _faraIntrebare()
	try:
		s = initConfig()
		s.hds_ocr_fara_intrebare.value = ""
		s.hds_ocr_fara_intrebare.save()
		from Components.config import configfile
		configfile.save()
	except Exception as e:
		_jurnal("alegerea nu se poate salva: %s" % e)
		return {"result": False, "message": _t("Alegerea nu se poate salva.")}
	_INTREBATE.difference_update(vechi)
	return {"result": True, "message": _t("Te întreb din nou pentru toate limbile.")}


def sePropune(model, dep=None):
	"""True daca pentru modelul lipsa se poate pune intrebarea acum: se descarca, nu e pe receptor, nu s-a mai
	intrebat de la pornire, omul nu a spus "Nu mai întreba" si nu merge deja o descarcare a lui."""
	dep = dep or depozit()
	if not model or model in _INTREBATE or model in _faraIntrebare():
		return False
	if model not in dep.descarcabile() or model in dep.modeleInstalate():
		return False
	l = dep.lucrari().get(model)
	return not (l and l["stare"] in ("asteapta", "merge"))


def textPropunere(model, dep=None, ghicita=False):
	"""intrebarea de descarcare; ghicita = pista nu are limba declarata, iar limba e ghicita dupa canal
	(Components/HdsOcrLimbaGhicita.py)"""
	dep = dep or depozit()
	marime = (dep.descarcabile().get(model) or {}).get("marime")
	if ghicita:
		return _t("Limba ghicită a subtitrării: %s. Ca să citesc subtitrarea ca text am nevoie de modelul acestei "
			"limbi (%s), care se descarcă de pe internet. Îl descarc?") % (numeModel(model), marimeText(marime))
	return _t("Limba subtitrării: %s. Ca să citesc subtitrarea ca text am nevoie de modelul acestei limbi (%s), care "
		"se descarcă de pe internet. Îl descarc?") % (numeModel(model), marimeText(marime))


def propune(model, ghicita=False):
	"""Pe firul enigma2, cand pista DVB are o limba fara model: intrebarea vine peste ecran (Tools.Notifications).
	ghicita = limba e ghicita dupa canal (pista nu are limba declarata). Intoarce True daca s-a pus intrebarea."""
	if not sePropune(model):
		return False
	_INTREBATE.add(model)
	depozit().cereStare()                      # locul se afla pana raspunde omul
	try:
		from Tools import Notifications
		from Screens.HdsOcrLimbi import HdsOcrIntrebare, HdsOcrLimbi
	except Exception as e:
		_jurnal("intrebarea nu se poate pune: %s" % e)
		return False

	def raspuns(ales=None):
		# fara valoare (fereastra inchisa de altcineva, de exemplu la standby) = „Nu acum”
		if ales == "da":
			Notifications.AddNotification(HdsOcrLimbi, alege=model, descarca=True)
		elif ales == "niciodata":
			_nuMaiIntreba(model)

	Notifications.AddNotificationWithCallback(raspuns, HdsOcrIntrebare, textPropunere(model, ghicita=ghicita), [
		(_t("Da, descarcă modelul"), "da"),
		(_t("Nu acum"), "nu"),
		(_t("Nu mai întreba pentru limba asta"), "niciodata"),
	])
	return True
