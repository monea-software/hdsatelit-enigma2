# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com & hdsatelit.com
# SPDX-License-Identifier: GPL-2.0-only
# Passive audio copies, bounded queues, recognition and the shared translation engine.
import base64
import json
import queue
import shutil
import subprocess
import struct
import threading
import time
import weakref

BUCATA_S = 3.2
MAX_AUDIO = 2 * 1024 * 1024
MAX_VARSTA = 9.0
TERMEN = 3.0
SERVICII = ("groq", "gemini")
_lucratori = weakref.WeakSet()
_alegere_nativa = False
_cheie_asteptata = 0	# monotonic time until which a key check started from the web page may still save a key


def _t(text):
	try:
		return _(text)
	except NameError:
		return text


def confidentialitate():
	return _t("Subtitrarea postului are prioritate și se traduce în limba ta. Dacă rămâne fără text, trece singur la vorbire și revine când reapare subtitrarea. Sunetul canalului pleacă direct la serviciul ales, cu cheia ta. Nu trece prin serverele HD Satelit și nu se păstrează pe receptor. Serviciul îl prelucrează după regulile contului tău.")


def drumMeniu():
	"""Where the speech subtitle screen (with the QR code) is on the receiver, in the menu language."""
	return " > ".join(_t(p) for p in ("Menu", "Settings", "Audio & Sound Tracks", "Subtitrări din vorbire"))


def textLipsaCheie():
	return _t("Subtitrări din vorbire: lipsește cheia. Scanează codul din %s și lipește cheia.") % drumMeniu()


def cheiPuse():
	"""{serviciu: True/False} from the key store (never the key); {} when it cannot be read."""
	try:
		d = _traducere().chei().stare()
	except Exception:
		return {}
	return dict((x, bool(d.get(x))) for x in SERVICII)


def initConfig():
	from Components.config import config, ConfigSubsection, ConfigOnOff, ConfigSelection
	if not hasattr(config, "hds_vorbire"):
		config.hds_vorbire = ConfigSubsection()
		s = config.hds_vorbire
		s.pornit = ConfigOnOff(default=False)
		s.serviciu = ConfigSelection(default="groq", choices=[("gemini", "Gemini"), ("groq", "Groq")])
		s.limba = ConfigSelection(default="meniu", choices=[("meniu", _t("Limba meniului"))] +
			[(c, _t(n)) for c, n in _traducere().LIMBI_TINTA])
	return config.hds_vorbire


def _traducere():
	from Components import HdsTraducereSubtitrari
	return HdsTraducereSubtitrari


def configuratie():
	# Main loop: only ConfigElements, never the key store or channel files.
	T = _traducere()
	s = initConfig()
	ordine = [s.serviciu.value] + [x for x in SERVICII if x != s.serviciu.value]
	return {"tinta": T.limbaMeniului() if s.limba.value == "meniu" else s.limba.value,
		"recunoastere": [T.configuratia(serviciu=x, cheile={}, legaturi={}) for x in ordine],
		"traducere": T.lantul(cheile={}, legaturi={})}


class Date(object):
	# One disk reader; only immutable plain copies cross the thread boundary.
	def __init__(self):
		self._copie = None
		self.cerere = None
		self.versiune = 0
		self.fir = None
		self.la = 0
		self.citita = -1
		self.depozit = self.memorie = None

	@property
	def copie(self):
		c = self._copie
		return c[1] if c is not None and c[0] == self.versiune else None

	def invalideaza(self):
		self.versiune += 1
		self._copie = None

	def cere(self, cfg):
		if cfg != self.cerere:
			self.cerere = cfg
			self.invalideaza()
		if (self.fir is None or not self.fir.is_alive()) and (self.citita != self.versiune or time.monotonic() - self.la >= 1):
			self.fir = threading.Thread(target=self._lucru, name="HdsVorbireDisc", daemon=True)
			self.fir.start()
		return self.copie

	def _lucru(self):
		from Components import HdsPisteLimbi as P
		T = _traducere()
		v, cfg = self.versiune, self.cerere
		try:
			if self.depozit is None:
				self.depozit = T.Chei()
			if self.memorie is None:
				self.memorie = P.MemorieAlegeri()
			toate, legaturi = self.depozit._citesteTot()
			rez = dict(cfg)
			for grupa in ("recunoastere", "traducere"):
				rez[grupa] = []
				for c in cfg[grupa]:
					c = dict(c)
					serv = c["serviciu"]
					chei = []
					for k in toate.get(serv, []):
						cheie, oprita = T.cheiePentru(serv, c.get("adresa", ""), {serv: k}, legaturi)
						if cheie:
							chei.append(cheie)
					c.update(cheie=chei[0] if chei else "", chei=chei)
					rez[grupa].append(c)
			lant = [dict(c, tinta=rez["tinta"]) for c in rez["traducere"]]
			rez["servicii_pregatite"] = frozenset(c["serviciu"] for c in lant if not T.ceLipseste(c))
			rez["mesaj_traducere"] = T.mesajConfigurareLipsa(lant[0], T.textCeMaiPoate(lant=lant)) \
				if lant and not rez["servicii_pregatite"] else ""
			rez["alegeri"] = self.memorie.toate()
			rez["canale_oprite"] = frozenset(T._citesteCanaleOprite())
			if cfg.get("film"):
				rez["cheie_film"] = None
				try:
					with open(cfg["film"] + ".meta", "rb") as f:
						rez["cheie_film"] = P.cheieDinReferinta(f.readline(4096).decode("utf-8", "replace").strip())
				except OSError:
					pass
			if v == self.versiune:
				self._copie = (v, rez)
		except Exception:
			if v == self.versiune:
				self._copie = None
		finally:
			self.la = time.monotonic()
			self.citita = v


_date = Date()


def setariSchimbate():
	_date.invalideaza()
	# Safe from either thread: these are Python events and queues, not service objects.
	for lucrator in list(_lucratori):
		lucrator.opreste()


def ciorna():
	from Components.config import ConfigOnOff, ConfigSelection
	from types import SimpleNamespace
	s = initConfig()
	return SimpleNamespace(pornit=ConfigOnOff(default=s.pornit.value),
		serviciu=ConfigSelection(default=s.serviciu.value, choices=list(s.serviciu.choices.choices)),
		limba=ConfigSelection(default=s.limba.value, choices=list(s.limba.choices.choices)))


_salvare = None


def scrieSetari(cale, valori, tranzactie=None):
	from Components.config import TranzactieSetari
	proprie = tranzactie is None
	try:
		t = tranzactie or TranzactieSetari()
	except RuntimeError:
		return False
	try:
		return t.ruleaza(_scrieSetari, cale, valori)
	finally:
		if proprie:
			t.inchide()


def _scrieSetari(cale, valori):
	# Worker only. Merge just our fields, preserve every unrelated byte, verify disk.
	from Components.config import _scrieSigur
	import os
	import tempfile
	temporar = None
	try:
		cale = os.path.realpath(cale)
		try:
			with open(cale, "rb") as f:
				vechi = f.read(8 * 1024 * 1024 + 1)
			st = os.stat(cale)
		except FileNotFoundError:
			vechi = b""
			st = None
		if len(vechi) > 8 * 1024 * 1024:
			return False
		prefix = b"config.hds_vorbire."
		randuri = [r for r in vechi.splitlines(keepends=True) if not any(r.startswith(prefix + k.encode("ascii") + b"=") for k in valori)]
		text = b"".join(randuri)
		if text and not text.endswith(b"\n"):
			text += b"\n"
		for k, v in valori.items():
			text += prefix + k.encode("ascii") + b"=" + (str(v) if isinstance(v, bool) else v).encode("utf-8") + b"\n"
		fd, temporar = tempfile.mkstemp(prefix=".hds-vorbire-", dir=os.path.dirname(cale))
		os.close(fd)
		if not _scrieSigur(temporar, text):
			return False
		with open(temporar, "rb") as f:
			if f.read(len(text) + 1) != text:
				return False
		if st is not None:
			os.chmod(temporar, st.st_mode & 0o7777)
			if hasattr(os, "chown"):
				os.chown(temporar, st.st_uid, st.st_gid)
		try:
			with open(cale, "rb") as f:
				acum = f.read(len(vechi) + 1)
		except FileNotFoundError:
			acum = b""
		if acum != vechi:
			return False
		os.replace(temporar, cale)
		if os.name == "posix":
			try:
				fd = os.open(os.path.dirname(cale), os.O_RDONLY)
				try:
					os.fsync(fd)
				finally:
					os.close(fd)
			except OSError:
				pass
		with open(cale, "rb") as f:
			return f.read(len(text) + 1) == text
	except (OSError, ValueError, UnicodeError):
		return False
	finally:
		if temporar:
			try:
				os.unlink(temporar)
			except OSError:
				pass


def salveaza(valori, canal=None):
	global _salvare
	if _salvare is not None:
		return False
	from Components.config import configfile, TranzactieSetari
	from enigma import eTimer
	try:
		tranzactie = TranzactieSetari()
	except RuntimeError:
		return False
	configfile._scris = None
	cale = configfile.CONFIG_FILE
	q = queue.Queue(1)
	valori = dict(valori)
	op = {"gata": False, "ok": False, "valori": valori, "canal": canal}
	_salvare = op
	def lucru():
		try:
			ok = scrieSetari(cale, valori, tranzactie)
			mem_ok = True
			if ok and canal:
				from Components import HdsPisteLimbi as P
				mem_ok = P.MemorieAlegeri().noteazaSubtitrare(canal, P.VORBIRE)
			q.put((ok, mem_ok))
		except Exception:
			q.put((False, False))
	fase = [False, True, True]
	def restul(cereri):
		try:
			tranzactie.termina(cereri)
			q.put((True, True))
		except Exception:
			q.put((False, True))
	def gata():
		global _salvare
		try:
			ok, mem_ok = q.get_nowait()
		except queue.Empty:
			return
		if fase[0]:
			fase[1] = fase[1] and ok
			ok, mem_ok = fase[1:]
		else:
			fase[:] = [True, ok, mem_ok]
		if ok and not op.get("aplicat"):
			op["aplicat"] = True
			s = initConfig()
			for k, v in valori.items():
				e = getattr(s, k)
				e.value = v
				e.save()
			setariSchimbate()
			if canal and mem_ok:
				from Components import HdsPisteLimbi as P
				v = getattr(P.infobarActiv(), "hdsVorbire", None)
				if v:
					v.anulat = None
			_traducere().puneLegatura()
		# Ordinary saves queued during the reservation use a fresh main-loop snapshot.
		cereri = tranzactie.preia()
		if cereri:
			try:
				threading.Thread(target=restul, args=(cereri,), name="HdsVorbireSalvare", daemon=True).start()
				return
			except Exception:
				# The values remain in config; report failure and allow a later save to retry.
				fase[1] = ok = False
		if not tranzactie.inchide():
			return
		configfile._scris = None
		timer.stop()
		op.update(gata=True, ok=ok and mem_ok)
		_salvare = None
		_ultimaSalvare.update(gata=True, ok=ok and mem_ok, mem_esec=ok and not mem_ok)
		timer.callback.remove(gata)
	try:
		timer = eTimer()
		timer.callback.append(gata)
		op["timer"] = timer
		timer.start(100)
		threading.Thread(target=lucru, name="HdsVorbireSalvare", daemon=True).start()
	except Exception:
		if "timer" in op:
			timer.stop()
		tranzactie.inchide(fortat=True)
		_salvare = None
		_ultimaSalvare.update(gata=True, ok=False, mem_esec=False)
		return False
	return op


_ultimaSalvare = {"gata": True, "ok": True}


def stareSalvare():
	return {"salveaza": _salvare is not None, "salvat": _ultimaSalvare["ok"],
		"mesaj_salvare": _t("Se salvează setările.") if _salvare is not None else (
			"" if _ultimaSalvare["ok"] else (_t("Setarea s-a salvat, dar alegerea canalului nu s-a putut păstra.")
				if _ultimaSalvare.get("mem_esec") else _t("Setările nu s-au putut salva. Încearcă din nou.")))}


def puneUltima(coada, element):
	try:
		coada.put_nowait(element)
	except queue.Full:
		if isinstance(element, dict):
			element = dict(element, salt=True)
		try:
			coada.get_nowait()
		except queue.Empty:
			pass
		try:
			coada.put_nowait(element)
		except queue.Full:
			pass


def wavPcm(date, rata, canale):
	if not (8000 <= rata <= 96000 and 1 <= canale <= 8) or len(date) + 44 > MAX_AUDIO or len(date) % (canale * 2):
		raise ValueError("pcm")
	return struct.pack("<4sI4s4sIHHIIHH4sI", b"RIFF", 36 + len(date), b"WAVE", b"fmt ", 16,
		1, canale, rata, rata * canale * 2, canale * 2, 16, b"data", len(date)) + date


def converteste(date, fel, stop, executabil=None):
	# Only the short private copy is decoded, with one CPU thread. No temporary files.
	exe = executabil or shutil.which("ffmpeg")
	if not exe:
		raise ValueError("conversie")
	format_ = {"adts": "aac", "loas": "loas", "ac3": "ac3", "eac3": "eac3"}.get(fel)
	if not format_ or len(date) > MAX_AUDIO or stop.is_set():
		raise ValueError("format")
	p = subprocess.Popen([exe, "-nostdin", "-v", "error", "-threads", "1", "-f", format_, "-i", "pipe:0",
		"-t", "4", "-ac", "1", "-ar", "16000", "-threads", "1", "-f", "s16le", "pipe:1"],
		stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
	try:
		try:
			raw = p.communicate(date, timeout=1.5)[0]
		except subprocess.TimeoutExpired:
			p.kill()
			p.communicate()
			raise ValueError("conversie")
		if p.returncode or stop.is_set() or not raw or len(raw) > 128000:
			raise ValueError("conversie")
		return wavPcm(raw, 16000, 1)
	finally:
		if p.poll() is None:
			p.kill()
			p.wait()


class Cadre(object):
	# The existing radio header readers give frame boundaries without decoding audio.
	def __init__(self):
		from Components import HdsRadioAnaliza as A
		self.A = A
		self.tampon = bytearray()
		self.date = bytearray()
		self.durata = 0.0
		self.fel = None
		self.loas = None
		self.loas_cadru = b""


	def adauga(self, date):
		A = self.A
		self.tampon.extend(date[:65536])
		b = self.tampon
		i = 0
		rez = []
		while i + 12 <= len(b):
			a = None
			for fel, antet in (("mp2", A.antet_mp2), ("adts", A.antet_adts), ("ac3", A.antet_ac3), ("eac3", A.antet_eac3), ("loas", A.antet_loas), ("mp3", antetMp3)):
				a = antet(b, i)
				if a:
					break
			if not a:
				i += 1
				continue
			lungime = a[0]
			if i + lungime > len(b):
				break
			if self.fel != fel:
				self.date.clear()
				self.durata = 0.0
				self.fel = fel
			if fel == "loas":
				if a[1]:
					self.loas = a[1]
					self.loas_cadru = bytes(b[i:i + lungime])
					if a[1][0] in (5, 29):
						try:
							from Components.HdsVorbireAudio import latm
							rate = latm(self.loas_cadru)[2]
							self.loas = (a[1][0], rate, a[1][2])
						except ValueError:
							self.loas = None
				if not self.loas:
					i += lungime
					continue
				freq, n = self.loas[1], 1024
				if not self.date and not a[1]:
					self.date.extend(self.loas_cadru)
			else:
				freq = a[1] if fel == "adts" else a[2]
				n = a[3] if fel == "mp3" else 1024 * (1 + (b[i + 6] & 3)) if fel == "adts" else (256 * a[7] if fel == "eac3" else (1152 if fel == "mp2" else 1536))
			self.date.extend(b[i:i + lungime])
			self.durata += n / float(freq)
			i += lungime
			if len(self.date) > MAX_AUDIO:
				self.date.clear()
				self.durata = 0.0
			elif self.durata >= BUCATA_S:
				rez.append((bytes(self.date), fel))
				self.date.clear()
				self.durata = 0.0
		del b[:i]
		if len(b) > 65536:
			b.clear()
		return rez


def antetMp3(b, i):
	if i + 4 > len(b) or b[i] != 255 or b[i + 1] & 0xe0 != 0xe0:
		return None
	v, layer = (b[i + 1] >> 3) & 3, (b[i + 1] >> 1) & 3
	idx, fi = b[i + 2] >> 4, (b[i + 2] >> 2) & 3
	if v == 1 or layer != 1 or idx in (0, 15) or fi == 3:
		return None
	bitrates = (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320) if v == 3 else (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160)
	rate = (44100, 48000, 32000)[fi] >> (0 if v == 3 else (1 if v == 2 else 2))
	return ((144000 if v == 3 else 72000) * bitrates[idx] // rate + ((b[i + 2] >> 1) & 1), bitrates[idx], rate, 1152 if v == 3 else 576)


class Motor(object):
	def __init__(self, cfg, trimite=None, ceas=time.monotonic, conversie=converteste):
		self.cfg, self.ceas = cfg, ceas
		self.T = _traducere()
		self.trimite = trimite or self.T.trimite
		self.conversie = conversie
		self.blocat = {}
		self.rec = self.T.Traducator(acum=ceas, cu_trezire=False)
		self.tr = self.T.Traducator(acum=ceas, cu_trezire=False)

	def _cerere(self, cfg, date, fel, stop):
		serv = cfg["serviciu"]
		if fel not in ("mp2", "mp3", "wav") and not (fel == "adts" and serv == "gemini"):
			try:
				from Components.HdsVorbireAudio import impacheteaza
				date, fel = impacheteaza(date, fel), "m4a"
			except ValueError:
				date, fel = self.conversie(date, fel, stop), "wav"
		mime = {"mp2": "audio/mpeg", "mp3": "audio/mpeg", "adts": "audio/aac", "wav": "audio/wav", "m4a": "audio/m4a"}[fel]
		if serv == "groq":
			bord = "hds-audio-" + base64.b16encode(__import__("os").urandom(16)).decode("ascii")
			ext = "mpeg" if fel == "mp2" else ("mp3" if fel == "mp3" else ("m4a" if fel == "m4a" else "wav"))
			body = ("--%s\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\nwhisper-large-v3-turbo\r\n"
				"--%s\r\nContent-Disposition: form-data; name=\"response_format\"\r\n\r\nverbose_json\r\n"
				"--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"audio.%s\"\r\nContent-Type: %s\r\n\r\n" %
				(bord, bord, bord, ext, mime)).encode("ascii") + date + ("\r\n--%s--\r\n" % bord).encode("ascii")
			return "https://api.groq.com/openai/v1/audio/transcriptions", {
				"Authorization": "Bearer " + cfg["cheie"], "Content-Type": "multipart/form-data; boundary=" + bord}, body
		body = {"contents": [{"parts": [{"text": "Transcribe only spoken words. Silence or music: empty text. Return JSON with text and language (ISO 639-1). Do not translate."},
			{"inlineData": {"mimeType": mime, "data": base64.b64encode(date).decode("ascii")}}]}],
			"generationConfig": {"temperature": 0, "maxOutputTokens": 512, "responseMimeType": "application/json"}}
		model = cfg.get("model") or self.T.MODEL_GEMINI_IMPLICIT
		return self.T.GEMINI_ADRESA % model, {"x-goog-api-key": cfg["cheie"], "Content-Type": "application/json"}, json.dumps(body).encode("utf-8")

	def _lant(self, lant, stop, executa=None, text="", limba=""):
		T = self.T
		self.eroare = None
		lant = [dict(c, tinta=self.cfg["tinta"]) for c in lant if not T.ceLipseste(c)] if executa is None else [dict(c, tinta=self.cfg["tinta"]) for c in lant if c.get("cheie")]
		if not lant or stop.is_set():
			return None, None
		m = self.rec if executa else self.tr
		lot = T.Lot([T.Lucrare(lant[0], limba or "auto", [text], [], self.ceas(), lant=lant)])
		toate = {c["serviciu"]: list(c.get("chei") or ([c["cheie"]] if c.get("cheie") else [])) for c in lant}
		_, rez, err, ms, info = m._trimiteLot(lot, toate_cheile=toate, executa=executa, stop=stop, termen_s=TERMEN)
		self.eroare = err
		return rez, lot.cfg

	def recunoaste(self, date, fel, stop):
		if not date or len(date) > MAX_AUDIO or stop.is_set():
			return "", "", "oprit"
		def executa(cfg, termen):
			serv = cfg["serviciu"]
			try:
				url, headers, body = self._cerere(cfg, date, fel, stop)
			except ValueError:
				raise self.T.EroareTraducere(self.T.E_LIMBA, "format")
			if stop.is_set():
				raise self.T.EroareTraducere(self.T.E_TERMEN, "oprit")
			r = self.trimite(url, headers, body, termen)
			cod, raw = r
			if cod != 200:
				wait, zilnic = self.T.asteptareDinRaspuns(cod, getattr(r, "antete", {}), raw) if cod == 429 else (None, False)
				if zilnic:
					wait = max(wait or 0, self.T.panaLaMiezulNoptiiPacific() if serv == "gemini" else self.T.panaLaMiezulNoptiiUtc())
				raise self.T.EroareTraducere(self.T.felEroareHttp(serv, cod, raw), "serviciu", cod, wait, zilnic)
			j = json.loads(raw.decode("utf-8"))
			if serv == "gemini":
				j = json.loads("".join(p.get("text", "") for p in j["candidates"][0]["content"]["parts"]))
			text, lang = j.get("text", ""), j.get("language", "")
			if not isinstance(text, str) or not isinstance(lang, str):
				raise ValueError("raspuns")
			return text.strip()[:1200], self.T.cod2(lang), serv
		lant = [c for c in self.cfg["recunoastere"] if self.blocat.get(c["serviciu"], 0) <= self.ceas()]
		rez, c = self._lant(lant, stop, executa)
		for serv, b in self.rec.blocat.items():
			self.blocat[serv] = b[0] or self.ceas() + 3600
		if rez is not None:
			self.blocat[c["serviciu"]] = self.ceas() + (3.05 if c["serviciu"] == "groq" else 0)
		elif not stop.is_set():
			e = getattr(self, "eroare", None)
			semn = ([x["serviciu"] for x in lant], getattr(e, "fel", None), getattr(e, "cod", None),
				str(getattr(e, "text", e) or "")[:160])
			if semn != getattr(self, "spus", None):
				self.spus = semn
				_jurnal("recognition failed: services %s, %s HTTP %s %s" % semn)
		return rez or ("", "", "serviciu")

	def traduce(self, text, limba, stop):
		if not text or stop.is_set():
			return ""
		if limba == self.cfg["tinta"]:
			return text
		rez, c = self._lant(self.cfg["traducere"], stop, text=text, limba=limba)
		return rez[0] if rez else ""


class Anulare(object):
	# Per chunk: seek and age also cancel fallbacks between network calls.
	def __init__(self, lucrator, versiune, la):
		self.lucrator, self.versiune, self.la = lucrator, versiune, la

	def is_set(self):
		w = self.lucrator
		return w.stop.is_set() or w.versiune != self.versiune or w.ceas() - self.la > MAX_VARSTA


class Lucrator(object):
	# Exactly one recognition worker. Old channel jobs must exit before a new one starts.
	def __init__(self, cfg, motor=None, ceas=time.monotonic):
		self.stop = threading.Event()
		self.intrare = queue.Queue(2)
		self.iesire = queue.Queue(2)
		self.ceas = ceas
		self.motor = motor or Motor(cfg, ceas=ceas)
		self.versiune = 0
		self.fir = threading.Thread(target=self._lucru, name="HdsVorbire", daemon=True)
		_lucratori.add(self)

	def _lucru(self):
		while not self.stop.is_set():
			versiune = self.versiune
			try:
				bucata = self.intrare.get(timeout=0.1)
				la, date, fel = bucata[:3]
				if len(bucata) == 4 and bucata[3] != versiune:
					continue
			except queue.Empty:
				continue
			if self.stop.is_set() or self.ceas() - la > MAX_VARSTA or versiune != self.versiune:
				continue
			anulare = Anulare(self, versiune, la)
			try:
				text, limba, serv = self.motor.recunoaste(date, fel, anulare)
				if self.stop.is_set() or self.ceas() - la > MAX_VARSTA or versiune != self.versiune:
					continue
				tradus = self.motor.traduce(text, limba, anulare)
				if not self.stop.is_set() and self.ceas() - la <= MAX_VARSTA and versiune == self.versiune:
					puneUltima(self.iesire, (tradus, self.ceas() - la + BUCATA_S, serv, versiune))
			except Exception as e:
				if getattr(self, "spus", None) != e.__class__.__name__:
					self.spus = e.__class__.__name__
					_jurnal("speech step failed: %s: %s" % (e.__class__.__name__, str(e)[:160]))
				if not self.stop.is_set() and versiune == self.versiune:
					puneUltima(self.iesire, ("", 0, "serviciu", versiune))
		self.goleste()

	def goleste(self):
		self.versiune += 1
		for q in (self.intrare, self.iesire):
			while True:
				try:
					q.get_nowait()
				except queue.Empty:
					break

	def opreste(self):
		self.stop.set()
		self.goleste()


def _jurnal(text):
	print("[HdsVorbire] %s" % text)


TACERE_PES_S = 2.0	# a PES filter silent this long (from the start or after a few bytes) is replaced by a TS filter


class Cititor(object):
	# PES filter first (as the radio bars). Some drivers give a second PES filter on the audio PID nothing for ~20 s
	# after a zap (measured on ZGEMMA H8.2H Plus) while a TS filter on the same PID gets the packets at once: then the
	# packets are unwrapped with FiltruTs into the same PES bytes.
	def __init__(self, sursa, lucrator):
		self.sursa, self.lucrator = sursa, lucrator
		self.fir = threading.Thread(target=self._lucru, name="HdsVorbireAudio", daemon=True)
		self.motiv = ""
		self.detaliu = ""	# technical reason for the log, never shown as is

	def _lucru(self):
		from Components import HdsRadioAnaliza as A
		Pes = A.Pes
		pes, cadre = Pes(), Cadre()
		ts = None
		ultim = time.monotonic()
		ultim_audio = ultim
		versiune = self.lucrator.versiune
		try:
			if self.lucrator.stop.is_set():
				return
			eroare = self.sursa.deschide(self.sursa.cai[0])
			if eroare:
				self.detaliu = eroare
				self.motiv = "sunet"
				return
			octeti = 0
			while not self.lucrator.stop.is_set():
				if versiune != self.lucrator.versiune:
					versiune = self.lucrator.versiune
					pes, cadre = Pes(), Cadre()
					ts = A.FiltruTs(self.sursa.pid) if ts is not None else None
					self.sursa.inchide()
					eroare = self.sursa.deschide(self.sursa.cai[0])
					if eroare:
						self.detaliu = eroare
						self.motiv = "sunet"
						return
				date = self.sursa.citeste(100)
				if versiune != self.lucrator.versiune:
					continue
				if date:
					octeti += len(date)
					ultim = time.monotonic()
					if ts is not None:
						date = ts.adauga(date)
					for audio, fel in cadre.adauga(pes.adauga(date)):
						ultim_audio = time.monotonic()
						puneUltima(self.lucrator.intrare, (time.monotonic(), audio, fel, versiune))
				elif (ts is None and hasattr(self.sursa, "iesire") and
						time.monotonic() - ultim > TACERE_PES_S):
					self.sursa.inchide()
					self.sursa.iesire = A.DMX_OUT_TSDEMUX_TAP
					eroare = self.sursa.deschide(self.sursa.cai[0])
					if eroare:
						self.detaliu = "TS filter: " + eroare
						self.motiv = "sunet"
						return
					ts = A.FiltruTs(self.sursa.pid)
					pes, cadre = Pes(), Cadre()
					ultim = ultim_audio = time.monotonic()
					_jurnal("PES filter silent for %.0f s on %s, TS filter on PID %d" % (TACERE_PES_S, self.sursa.cai[0],
						self.sursa.pid))
				elif time.monotonic() - ultim > 4:
					self.detaliu = "%s: no %s data for 4 s (%d bytes before)" % (self.sursa.cai[0],
						"TS" if ts is not None else "PES", octeti)
					self.motiv = "sunet"
					break
				if time.monotonic() - ultim_audio > 10:
					self.detaliu = "%s: %d bytes, no audio frames for 10 s (%s)" % (self.sursa.cai[0], octeti,
						cadre.fel or "unknown")
					self.motiv = "format"
					break
		except Exception as e:
			self.detaliu = "reader: %s" % e.__class__.__name__
			self.motiv = "sunet"
		finally:
			self.sursa.inchide()


class CititorPlayer(object):
	# The main loop posts only private byte copies; framing and WAV work stay here.
	def __init__(self, lucrator):
		self.lucrator = lucrator
		self.intrare = queue.Queue(2)
		self.motiv = ""
		self.detaliu = ""
		self.primite = 0	# player copies received, for the log
		self.fir = threading.Thread(target=self._lucru, name="HdsVorbirePlayer", daemon=True)

	def _lucru(self):
		cadre, pcm, semn = Cadre(), bytearray(), None
		ultima = time.monotonic()
		ultim_audio = ultima
		try:
			while not self.lucrator.stop.is_set():
				try:
					d = self.intrare.get(timeout=0.1)
				except queue.Empty:
					if time.monotonic() - ultima > 5:
						self.detaliu = "player: no audio copy for 5 s (%d received)" % self.primite
						self.motiv = "sunet"
						return
					continue
				ultima = time.monotonic()
				self.primite += 1
				versiune = d.get("versiune", self.lucrator.versiune)
				if versiune != self.lucrator.versiune:
					continue
				fel, rate, ch = d.get("fel"), d.get("rata", 0), d.get("canale", 0)
				nou = (fel, rate, ch)
				if nou != semn or d.get("salt"):
					cadre, pcm, semn = Cadre(), bytearray(), nou
					if "versiune" not in d:
						self.lucrator.goleste()
						versiune = self.lucrator.versiune
				date = d.get("date", b"")[:65536]
				if fel == "pcm":
					if not (8000 <= rate <= 96000 and 1 <= ch <= 8):
						continue
					marime = (rate * 32 // 10) * ch * 2
					if marime + 44 > MAX_AUDIO:
						self.detaliu = "player: PCM %d Hz x %d too large" % (rate, ch)
						self.motiv = "format"
						return
					pcm.extend(date)
					if len(pcm) >= marime:
						puneUltima(self.lucrator.intrare, (time.monotonic(), wavPcm(bytes(pcm[:marime]), rate, ch), "wav", versiune))
						ultim_audio = time.monotonic()
						del pcm[:marime]
				else:
					for audio, tip in cadre.adauga(date):
						puneUltima(self.lucrator.intrare, (time.monotonic(), audio, tip, versiune))
						ultim_audio = time.monotonic()
				if time.monotonic() - ultim_audio > 10:
					self.detaliu = "player: no audio frames for 10 s (%s %s Hz)" % (semn[0] if semn else "?",
						semn[1] if semn else "?")
					self.motiv = "format"
					return
		except Exception as e:
			self.detaliu = "player: %s" % e.__class__.__name__
			self.motiv = "sunet"
		finally:
			pcm.clear()
			while not self.intrare.empty():
				try:
					self.intrare.get_nowait()
				except queue.Empty:
					break
