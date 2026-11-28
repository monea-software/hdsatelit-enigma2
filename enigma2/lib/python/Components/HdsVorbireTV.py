# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com & hdsatelit.com
# SPDX-License-Identifier: GPL-2.0-only
# Service access and display live exclusively on the main loop.
import queue
import time
from Components import HdsVorbire as V
_t = V._t

_activ = None
_vechi = []
_proba = {"text": "", "lucreaza": False, "pana": 0}
_pagini = {}
LIPSA_S = 10		# seconds the missing-key message stays on the TV
LIPSA_DIN_NOU_S = 600.0	# and again after this long while the key is still missing (or after speech is turned on again)
# A reader that gets no sound right after a zap is tried again: some drivers give nothing to a PES filter opened while
# the decoder starts (ZGEMMA H8.2H Plus), and a slow internet stream may need more than the reader waits (measured:
# 8 s to PLAYING). Pauses before each new try; after the last one the channel is left alone until the next zap.
PAUZE_REINCERCARE = (2.0, 4.0, 8.0)


def textCurent(v):
	if v and getattr(v, "post_activ", False):
		return getattr(v, "text_post", "") if time.monotonic() < getattr(v, "expira_post", 0) else ""
	return v.text if v and time.monotonic() < v.expira else ""


def leagaPagina(generatie, v):
	if generatie:
		_pagini[generatie] = (v, v.canal_prioritate, getattr(v, "epoca_nativa", 0))
		while len(_pagini) > 256:
			_pagini.pop(next(iter(_pagini)))


def rezultatNativ(generatie, texte):
	leg = _pagini.pop(generatie, None)
	if leg:
		v, canal, epoch = leg
		if nativa() is v and canal == v.canal_prioritate and epoch == getattr(v, "epoca_nativa", 0):
			v.text_post = "\n".join(t for t in texte if t)
			v.expira_post = time.monotonic() + min(8, max(3.2, len(v.text_post) / 20.0))
			return True
		return False


def incearca():
	from Components import HdsPisteLimbi as P
	p = P.infobarActiv()
	v = getattr(p, "hdsVorbire", None)
	if v is None:
		return False
	_proba.update(text="", lucreaza=True, pana=time.monotonic() + 30)
	v.proba_pana = time.monotonic() + 15
	v.doar_proba = v.lucrator is None
	v.pasSigur()
	return True


def activ():
	return _activ


def alege(infobar):
	from Components import HdsPisteLimbi as P
	ref = infobar.session.nav.getCurrentlyPlayingServiceReference()
	if not V.salveaza({"pornit": True}, canal=cheie(ref, V._date.copie or {})):
		return False
	v = getattr(infobar, "hdsVorbire", None)
	if v:
		v.bifat = None
	return True


def stare():
	v = activ()
	if v is None:
		from Components import HdsPisteLimbi as P
		v = getattr(P.infobarActiv(), "hdsVorbire", None)
	s = V.initConfig()
	cfg = V._date.copie or {}
	return dict({"result": True, "pornit": s.pornit.value, "serviciu": s.serviciu.value, "limba": s.limba.value,
		"text": textCurent(v), "motiv": v.motiv if v else "oprit",
		"intarziere": round(v.intarziere, 1) if v else 0,
		"indiciu": bool(v and v.lucrator and time.monotonic() - v.pornit_la < 8),
		"proba": {"text": _proba["text"] if time.monotonic() < _proba["pana"] else "", "lucreaza": _proba["lucreaza"]}, "confidentialitate": V.confidentialitate(), "configurare": "/traducere-configurare",
		"sursa": "post" if v and getattr(v, "post_activ", False) else "vorbire",
		"chei": {c["serviciu"]: bool(c.get("cheie")) for c in cfg.get("recunoastere", [])}}, **V.stareSalvare())


def date(cale=""):
	cfg = V.configuratie()
	if cale.startswith("/"):
		cfg["film"] = cale
	return V._date.cere(cfg)


def cheie(ref, cfg):
	from Components import HdsPisteLimbi as P
	return cfg.get("cheie_film") if ref.getPath().startswith("/") else P.cheieCanal(ref)


def puneNativa(owner, pista):
	from Components import HdsPisteLimbi as P
	v = getattr(owner, "hdsVorbire", None)
	curenta = getattr(owner, "selected_subtitle", None)
	if v and (not curenta or not P.aceeasiSubtitrare(curenta, pista)):
		v.epoca_nativa = getattr(v, "epoca_nativa", 0) + 1
		v.text_post = ""
		v.expira_post = 0
	precedent = V._alegere_nativa
	V._alegere_nativa = True
	try:
		return P._pune(owner, pista)
	finally:
		V._alegere_nativa = precedent


def caleAudio(canal, cale, pid, demux):
	# Service type 1 includes local transport-stream playback, not playbin.
	if canal.split(":", 1)[0] == "1":
		return "dvb" if pid > 0 and demux is not None else None
	return "player" if "://" in cale or cale.startswith("/") else None


class Prioritate(object):
	TACERE = 20.0
	def __init__(self):
		self.inceput = None
		self.ultima = None

	def pagina(self, texte, acum):
		if any(isinstance(t, str) and t.strip() for t in texte):
			self.ultima = acum
			return True
		return False

	def prefera(self, acum, piste):
		if self.inceput is None:
			self.inceput = acum
		if self.ultima is not None and acum - self.ultima < self.TACERE:
			return False
		return not piste or acum - self.inceput >= self.TACERE


def nativa():
	from Components import HdsPisteLimbi as P
	v = getattr(P.infobarActiv(), "hdsVorbire", None)
	if v and getattr(v, "nativ_ok", False) and V.initConfig().pornit.value:
		if getattr(v, "versiune_cfg", V._date.versiune) != V._date.versiune:
			return None
		ref = v.owner.session.nav.getCurrentlyPlayingServiceReference()
		if ref and ref.toString() == v.canal_prioritate:
			v.actualizeazaSalt(v.owner.session.nav.getCurrentService())
			return v
	return None


def pagina(texte, legatura=None):
	v = nativa()
	if legatura is not None and (v is not legatura[0] or v.canal_prioritate != legatura[1] or (len(legatura) > 2 and getattr(v, "epoca_nativa", 0) != legatura[2])):
		return None
	if v and v.prioritate.pagina(texte, time.monotonic()):
		v.opreste()
		v.nativ_ok = v.post_activ = True
		v.motiv = "post"
	return v


def mesaj(motiv):
	return {"ascult": _t("Ascult sunetul canalului."), "cheie": _t("Pune întâi cheia: deschide configurarea de mai jos."),
		"post": _t("Subtitrarea postului are prioritate."),
		"sunet": _t("Sunetul nu este disponibil pentru această probă."),
		"nucleu": _t("Redarea acestui film are nevoie de actualizarea nucleului imaginii."),
		"serviciu": _t("Serviciile nu au răspuns la timp sau nu mai au cotă. Reîncerc singur."),
		"oprit": _t("Subtitrările din vorbire sunt oprite.")}.get(motiv, "")


class Legatura(object):
	def __init__(self, infobar):
		from enigma import eTimer
		self.owner = infobar
		self.lucrator = self.cititor = self.widget = self.tap_info = None
		self.semn = self.anulat = self.bifat = None
		self.text = ""
		self.motiv = "oprit"
		self.expira = self.intarziere = self.pornit_la = 0
		self.proba_pana = 0
		self.doar_proba = False
		self.prioritate = Prioritate()
		self.canal_prioritate = None
		self.nativ_ok = self.post_activ = False
		self.pista_la = 0
		self.index_pista = 0
		self.origine_nativa = None
		self.ultima_auto = None
		self.pcm = bytearray()
		self.cadre = None
		self.lipsa = None
		self.lipsa_dupa = 0
		self.timer = eTimer()
		self.timer.callback.append(self.pasSigur)
		from Components.config import config
		config.misc.standbyCounter.addNotifier(self.opreste, initial_call=False)
		infobar.onClose.append(self.inchide)
		infobar.session.nav.record_event.append(self.laInregistrare)
		V._traducere().puneLegatura()
		self.timer.start(100)

	def laInregistrare(self, *args):
		self.suspenda()

	def inchide(self):
		self.restauraNativa()
		self.suspenda()
		self.timer.stop()
		from Components.config import config
		config.misc.standbyCounter.removeNotifier(self.opreste)
		events = self.owner.session.nav.record_event
		if self.laInregistrare in events:
			events.remove(self.laInregistrare)
		self.widget = None
		self.timer.callback.remove(self.pasSigur)

	def opreste(self, *args):
		global _activ
		if self.lucrator:
			self.lucrator.opreste()
			_vechi.append((self.lucrator, self.cititor))
		if self.tap_info is not None:
			from enigma import iServiceInformation
			cod = getattr(iServiceInformation, "sHdsSpeechStop", None)
			if cod is not None:
				self.tap_info.getInfoObject(cod)
			self.tap_info = None
		self.lucrator = self.cititor = None
		self.nativ_ok = self.post_activ = False
		if self.proba_pana:
			_proba["lucreaza"] = False
		self.proba_pana = 0
		self.semn = None
		self.pcm.clear()
		self.cadre = None
		self.sterge()
		if _activ is self:
			_activ = None

	def sterge(self):
		self.text = ""
		if self.widget is not None:
			self.widget.clearPage()
			self.widget.hide()

	def mesajLipsa(self):
		# Speech on, no key for any service: a message on the TV says where to put it, instead of an empty screen.
		# Only while the person is watching (the bar is the dialog in front, not the screen with the code), not while
		# a key check started from the web page runs; once, then again after LIPSA_DIN_NOU_S or after Off and On.
		canal = getattr(self, "lipsa", None)
		acum = time.monotonic()
		if canal is None or acum < V._cheie_asteptata or acum < getattr(self, "lipsa_dupa", 0):
			return
		if getattr(self.owner.session, "current_dialog", self.owner) is not self.owner:
			return
		self.lipsa_dupa = acum + LIPSA_DIN_NOU_S
		from Tools import Notifications
		from Screens.MessageBox import MessageBox
		Notifications.AddPopup(V.textLipsaCheie(), MessageBox.TYPE_INFO, LIPSA_S, "HdsVorbireCheie")
		V._jurnal("missing key message shown on %s" % canal)

	def restauraNativa(self):
		origine = getattr(self, "origine_nativa", None)
		self.origine_nativa = None
		if origine and getattr(self, "ultima_auto", None):
			from Components import HdsPisteLimbi as P
			ref = self.owner.session.nav.getCurrentlyPlayingServiceReference()
			cur = getattr(self.owner, "selected_subtitle", None)
			if ref and ref.toString() == origine[0] and self.owner.subtitles_enabled and cur and P.aceeasiSubtitrare(cur, self.ultima_auto):
				puneNativa(self.owner, origine[2] if origine[1] else None)
		self.ultima_auto = None

	def pasSigur(self):
		self.lipsa = None
		try:
			self.pas()
		except Exception as e:
			self.suspenda()
			self.motiv = "sunet"
			try:
				import os
				import traceback
				f = traceback.extract_tb(e.__traceback__)[-1]
				self.jurnalSunet("step", "%s: %s at %s:%d" % (e.__class__.__name__, str(e)[:120], os.path.basename(f[0]), f[1]))
			except Exception:
				pass
		try:
			self.mesajLipsa()
		except Exception as e:
			self.jurnalSunet("message", "%s: %s" % (e.__class__.__name__, str(e)[:120]))

	def suspenda(self):
		if not getattr(self, "suspendat", False):
			self.invalideazaNativa()
		self.suspendat = True
		self.opreste()

	def pas(self):
		global _activ
		if _proba["pana"] and time.monotonic() > _proba["pana"]:
			_proba.update(text="", lucreaza=False, pana=0)
		from Components import HdsPisteLimbi as P, HdsRadioDate as RD
		from Screens.Standby import inStandby
		s = V.initConfig()
		nav = self.owner.session.nav
		proba = self.proba_pana > time.monotonic()
		if self.proba_pana and not proba:
			self.opreste()
			self.motiv = "sunet"
			return
		if (not s.pornit.value and not proba) or inStandby or getattr(self.owner.session, "pipshown", False) or nav.getRecordings() or P.infobarActiv(self.owner.session) is not self.owner:
			self.restauraNativa()
			self.suspenda()
			if not s.pornit.value:
				self.canal_prioritate = None
				self.lipsa_dupa = 0
				self.anulat = self.esec = None
			return
		viteza = getattr(self.owner, "seekstate", None)
		if isinstance(viteza, tuple) and viteza[:3] != (0, 0, 0):
			self.suspenda()
			return
		service = nav.getCurrentService()
		ref = nav.getCurrentlyPlayingServiceReference()
		if service is None or ref is None:
			self.suspenda()
			return
		self.actualizeazaSalt(service)
		if self.lucrator and self.lucrator.stop.is_set():
			self.opreste()
		cfg = date(ref.getPath())
		if cfg is None:
			proba_pana = self.proba_pana
			self.suspenda()
			if proba:
				self.proba_pana = proba_pana
				_proba["lucreaza"] = True
			return
		self.suspendat = False
		if getattr(self, "versiune_cfg", V._date.versiune) != V._date.versiune:
			self.invalideazaNativa()
		self.versiune_cfg = V._date.versiune
		cle = cheie(ref, cfg)
		mem = cfg.get("alegeri", {}).get(cle, {}).get("s")
		canal = ref.toString()
		if not proba and mem != P.VORBIRE and P.faraSubtitrariNiciodata():
			self.opreste()
			return
		if self.anulat and self.anulat != canal:
			self.anulat = None		# a channel left alone is tried again after a zap away and back
		if not proba and mem == P.OPRIT:
			self.opreste()
			return
		if not proba and self.anulat == canal:
			self.opreste()
			self.motiv = "sunet"
			return
		pid = RD.pid_audio(service)
		demux = RD.demux_serviciu(service)
		epoch = None
		if canal.startswith("1:") and ref.getPath().startswith("/"):
			from enigma import iServiceInformation
			cod = getattr(iServiceInformation, "sHdsSpeechDvb", None)
			d = service.info().getInfoObject(cod) if cod is not None else None
			if isinstance(d, dict):
				demux, epoch = d.get("demux"), d.get("salt")
			else:
				self.opreste()
				self.motiv = "nucleu"
				return
		if epoch != getattr(self, "native_epoch", epoch):
			self.invalideazaNativa()
			if self.lucrator:
				self.lucrator.goleste()
			self.sterge()
			self.epoch = epoch
		self.native_epoch = epoch
		tinta = V._traducere().limbaMeniului() if s.limba.value == "meniu" else s.limba.value
		if not proba:
			if getattr(self, "canal_prioritate", None) != canal:
				self.invalideazaNativa()
				self.canal_prioritate = canal
				self.esec = None		# the failures of another visit do not count here
				self.text_post = ""
				self.index_pista = self.pista_la = 0
				self.origine_nativa = (canal, self.owner.subtitles_enabled, getattr(self.owner, "selected_subtitle", None))
			self.nativ_ok = True
			self.cfg_nativa = cfg
			piste = P.subtitrari(service)
			acum = time.monotonic()
			vazute = self.piste_vazute
			curenta = getattr(self.owner, "selected_subtitle", None)
			if self.owner.subtitles_enabled and curenta:
				vazute.setdefault(tuple(curenta), acum)
			verificate = all(p.get("tuplu") and tuple(p["tuplu"]) in vazute and
				acum - vazute[tuple(p["tuplu"])] >= 10 for p in piste)
			vorbire = self.prioritate.prefera(acum, bool(piste) or self.owner.subtitles_enabled) and verificate
			if not vorbire:
				self.opreste()
				self.nativ_ok = self.post_activ = True
				self.motiv = "post"
			# Keep native reception enabled even during speech; rotate empty tracks only.
			if piste and (not self.owner.subtitles_enabled or (acum - self.pista_la >= 10 and
				(self.prioritate.ultima is None or acum - self.prioritate.ultima >= self.prioritate.TACERE))):
				pista = piste[self.index_pista % len(piste)].get("tuplu")
				if pista:
					puneNativa(self.owner, pista)
					self.ultima_auto = pista
					vazute.setdefault(tuple(pista), acum)
					self.index_pista += 1
				self.pista_la = acum
			if not vorbire:
				return
		online = caleAudio(canal, ref.getPath(), pid, demux)
		nou = (canal, pid, demux, s.serviciu.value, tinta, cfg["recunoastere"], cfg["traducere"])
		esec = getattr(self, "esec", None)
		if self.semn != nou and not proba and esec and esec[0] == canal and time.monotonic() < esec[2]:
			self.motiv = "sunet"
			return
		if self.semn != nou:
			proba_pana = self.proba_pana
			self.opreste()
			self.nativ_ok = not proba
			self.proba_pana = proba_pana
			if proba:
				_proba["lucreaza"] = True
			# Reap asynchronously, never join a network worker on the main thread.
			_vechi[:] = [(w, c) for w, c in _vechi if w.fir.is_alive() or (c and c.fir.is_alive())]
			if _vechi or (_activ is not None and _activ is not self):
				return
			if not any(c.get("cheie") for c in cfg["recunoastere"]):
				self.motiv = "cheie"
				if not proba:
					self.lipsa = canal
				return
			# For DVB use only the service demux, with a separately opened PES filter.
			# No guessing of demux0: it might belong to a recording or another channel.
			if online is None:
				self.motiv = "sunet"
				# right after a zap the PMT (pid, demux) is not there yet: logged only when it lasts
				fara = getattr(self, "fara_cale", None)
				if not fara or fara[0] != canal:
					self.fara_cale = (canal, time.monotonic())
				elif time.monotonic() - fara[1] > 5:
					self.jurnalSunet(canal, "no audio path: pid=%s demux=%s path=%s" % (pid, demux, ref.getPath()[:60]))
				return
			self.lucrator = V.Lucrator(cfg)
			self.lucrator.fir.start()
			if online == "dvb":
				from Components.HdsRadioAnaliza import SursaDemux, DEMUX
				self.cititor = V.Cititor(SursaDemux(pid, [DEMUX % (0, demux)]), self.lucrator)
				self.cititor.fir.start()
			else:
				self.cititor = V.CititorPlayer(self.lucrator)
				self.cititor.fir.start()
				self.tap_info = service.info()
				self.tap_stat = {"apeluri": 0, "goale": 0, "octeti": 0, "fel": ""}
				self.cadre = True
			self.semn = nou
			self.pornit_la = time.monotonic()
			if not proba:
				self.doar_proba = False
			self.bifat = None
			self.motiv = "ascult"
			_activ = self
			self.epoch = epoch
		if epoch != getattr(self, "epoch", epoch):
			self.lucrator.goleste()
			self.sterge()
			self.prioritate = Prioritate()
			self.epoch = epoch
		if not proba:
			self.nativ_ok = True
		if self.cititor and self.cititor.motiv:
			detaliu = getattr(self.cititor, "detaliu", "") or self.cititor.motiv
			if isinstance(self.cititor, V.CititorPlayer) and getattr(self, "tap_stat", None):
				detaliu += "; tap %(apeluri)d reads, %(goale)d empty, %(octeti)d bytes, codec %(fel)s" % self.tap_stat
			self.jurnalSunet(canal, detaliu)
			self.bifat = self.semn
			self.opreste()
			n = esec[1] + 1 if esec and esec[0] == canal else 1
			if not proba and n <= len(PAUZE_REINCERCARE):
				self.esec = (canal, n, time.monotonic() + PAUZE_REINCERCARE[n - 1])
			else:
				self.anulat = canal
			self.motiv = "sunet"
			return
		if self.cadre is not None:
			self.dinPlayer(service)
		while self.lucrator is not None:
			try:
				rez = self.lucrator.iesire.get_nowait()
				if len(rez) == 4 and rez[3] != self.lucrator.versiune:
					continue
				text, delay, serv = rez[:3]
			except queue.Empty:
				break
			self.esec = None		# sound reached the recogniser: later failures start counting again
			if text:
				if proba:
					_proba.update(text=text, lucreaza=False)
					self.proba_pana = 0
					if self.doar_proba:
						self.opreste()
						return
				self.afiseaza(text, delay)
			elif serv == "serviciu":
				self.motiv = "serviciu"
		if self.text and time.monotonic() >= self.expira:
			self.sterge()

	def jurnalSunet(self, canal, detaliu):
		# One log line per channel and reason: why speech subtitles have no sound (support and model ports).
		if getattr(self, "spus_sunet", None) != (canal, detaliu):
			self.spus_sunet = (canal, detaliu)
			V._jurnal("no sound on %s: %s" % (canal, detaliu))

	def invalideazaNativa(self):
		self.epoca_nativa = getattr(self, "epoca_nativa", 0) + 1
		self.text_post = ""
		self.expira_post = 0
		self.post_activ = False
		self.prioritate = Prioritate()
		self.piste_vazute = {}
		# Keep bounded old bindings: late translations must be refused by the widget too.

	def actualizeazaSalt(self, service):
		try:
			from enigma import iServiceInformation
			cod = getattr(iServiceInformation, "sHdsSpeechEpoch", None)
			epoch = service.info().getInfoObject(cod) if cod is not None else None
		except Exception:
			return
		if not isinstance(epoch, int):
			return
		if epoch != getattr(self, "urmarire_salt", epoch):
			self.invalideazaNativa()
			if self.lucrator:
				self.lucrator.goleste()
			self.sterge()
		self.urmarire_salt = epoch

	def dinPlayer(self, service):
		# getInfoObject copies a native mailbox; no Python thread touches GstBuffer.
		from enigma import iServiceInformation
		cod = getattr(iServiceInformation, "sHdsSpeechAudio", None)
		if cod is None:
			self.anulat = self.semn[0]
			self.opreste()
			self.motiv = "nucleu"
			return
		d = self.tap_info.getInfoObject(cod)
		st = getattr(self, "tap_stat", None)
		if st is not None:
			st["apeluri"] += 1
			if isinstance(d, dict) and d:
				st["octeti"] += len(d.get("date") or b"")
				st["fel"] = d.get("fel") or st["fel"]
			else:
				st["goale"] += 1
		if isinstance(d, dict):
			if d.get("salt"):
				self.invalideazaNativa()
				self.sterge()
				self.lucrator.goleste()
				self.prioritate = Prioritate()
				self.text_post = ""
				while not self.cititor.intrare.empty():
					try:
						self.cititor.intrare.get_nowait()
					except queue.Empty:
						break
			if d.get("date") or d.get("salt"):
				d["versiune"] = self.lucrator.versiune
				V.puneUltima(self.cititor.intrare, d)

	def arata(self, text):
		# The window and the widget visible first (above the service's own subtitle widget), then the text.
		from enigma import eSubtitleWidget, ePoint, eSize
		window = self.owner.subtitle_window
		if self.widget is None:
			self.widget = eSubtitleWidget(window.instance)
			self.widget.move(ePoint(0, 0))
			self.widget.resize(eSize(window.instance.size().width(), window.instance.size().height()))
			self.widget.setZPosition(1)
		window.show()
		# measured on ZGEMMA H8.2H Plus: the window may say shown while its instance is hidden (isVisible 0)
		if not window.instance.isVisible():
			window.instance.show()
		self.widget.show()
		self.widget.showSample(text)

	def afiseaza(self, text, delay):
		self.text, self.intarziere = text, delay
		self.expira = time.monotonic() + min(8, max(3.2, len(text) / 20.0))
		self.arata(text + ("\n~%.0f s" % delay if time.monotonic() - self.pornit_la < 8 else ""))
		self.motiv = "ascult"
