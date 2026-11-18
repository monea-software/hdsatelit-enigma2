# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""/web/stream?StreamService=<referinta>: canalul pentru transtreamproxy (transcodarea spre telefon, Vu+ cu codor).

transtreamproxy (GPL-3, github.com/oe-mirrors/filestreamproxy, ramura transtreamproxy; pus in imagine de
vuplus-transtreamproxy.bbappend din stratul imaginii, pornit pe portul 8002 de serviciul hds-transcodare) primeste
cererea telefonului si cere canalul de la interfata web a receptorului: GET /web/stream?StreamService=<referinta> pe
127.0.0.1:80, HTTP/1.0, fara Host. Raspunsul pe care il citeste (Demuxer.cpp, parse_webif_response; protocolul vechi
de streaming al interfetelor web Enigma2): randuri "+<demux>:<pid hex>:<tip>,<pid hex>:<tip>,..." (pat, pmt, video,
audio, subtitle, pcr, text), ultimul rand care incepe cu "+" fiind cel bun; legatura ramane deschisa cat
transcodeaza, iar cand o inchide, acordul se opreste aici. "-SERVICE ERROR:-<motiv>" = canalul nu porneste
(transtreamproxy reincearca de cateva ori, apoi spune telefonului 503). transtreamproxy asteapta raspunsul cam 3 s
pe o legatura; cand acordul dureaza mai mult cere din nou pe o legatura noua si o lasa deschisa pe cea veche: cererea
noua pentru acelasi canal preia acordul sesiunii care n-a dat inca PID-uri (_Sesiune.preia).

Tunerul il ia o inregistrare enigma2 de flux: eServiceCenter.record + prepareStreaming + start tin acordul si tabelele
PMT, fara fisier si fara cititor de demux (eDVBServiceRecord::doRecord nu face recorder la streaming);
transtreamproxy deschide singur /dev/dvb/adapter0/demuxN si codorul /dev/bcm_enc0. Ca serverul 8001
(Hds/DabT2/server8001.py), inregistrarea nu apare in lista inregistrarilor.

PRIORITATEA: televizorul si inregistrarile castiga, ca la celelalte fluxuri spre retea (Components/HdsTransmisie.py,
lib/dvb/hdscedare.h): inregistrarea e marcata ca una care cedeaza la zap (setYieldsToZap, lista de canale nu face gri
canalele din cauza ei), iar cat exista sesiuni, Navigation.playServiceExtensions si recordServiceExtensions opresc pe
loc sesiunile de pe alt transponder inainte de zap sau de o inregistrare adevarata. Pe acelasi transponder (tunerul e
impartit) nu se opreste nimic. La un grup de alternative fara nicio alternativa libera, Navigation.grupFaraTuner (_laGrup)
opreste sesiunile care nu sunt pe transponderul vreunei alternative, numai cat trebuie.

POARTA: numai de la receptorul insusi (127.0.0.1, ::1; treceFaraParola, chemata din aplicatii_web._poarta): fara
parola cand omul n-a pus parola pentru interfata in casa; cu parola pusa, transtreamproxy trimite antetul
Authorization al telefonului, iar poarta obisnuita il verifica. Legaturile din afara casei le opreste inainte
hds-transcodare-poarta (portul 8002).

FIRUL: totul pe firul enigma2 (render_GET, eTimer, notifyFinish). Fisierul nu importa nimic din enigma2 la
incarcare: probele de pe PC dau FABRICA lor.
"""
import re

SONDAJ_MS = 500            # cat de des se citesc PID-urile (se trimit numai cand se schimba)
PORNIRE_MAX_MS = 20000     # fara PID-uri in atat timp de la pornire: canalul nu porneste (fara semnal, tuner ocupat)
SESIUNI_MAX = 2            # codoarele placilor Vu+ au una sau doua iesiri

REF_BUNA = re.compile(r"^1:0:[0-9A-Fa-f]{1,4}:[0-9A-Fa-f]{1,4}:[0-9A-Fa-f]{1,4}:[0-9A-Fa-f]{1,4}:"
	r"[0-9A-Fa-f]{1,8}:0:0:0:$")

_SESIUNI = []              # sesiunile vii (firul enigma2)
_EXTENSII = [False]


def _jurnal(text):
	print("[HdsWebControl] transcodare: %s" % text)


def esteCererea(request):
	"""Calea cererii (fara ?...) e /web/stream."""
	cale = getattr(request, "path", b"") or b""
	if not isinstance(cale, bytes):
		cale = str(cale).encode("latin-1", "replace")
	return cale.split(b"?", 1)[0].rstrip(b"/") == b"/web/stream"


def treceFaraParola(request, L, adresa, esteReceptorul):
	"""True pentru transtreamproxy de pe receptor (127.0.0.1 sau ::1), pe /web/stream, cand omul n-a pus parola pentru
	interfata in casa."""
	try:
		return bool(esteCererea(request) and esteReceptorul(adresa) and not L.codAcasa())
	except Exception as e:
		_jurnal("poarta: %r" % (e,))
		return False


def refCurata(text):
	"""Referinta de serviciu DVB din StreamService (cu %3A sau :), sau None."""
	ref = (text or "").strip().replace("%3A", ":").replace("%3a", ":")
	if len(ref.split(":")) == 10:
		ref += ":"                           # fara ultimele doua puncte, ca in unele aplicatii
	return ref if REF_BUNA.match(ref) else None


def randul(date):
	"""getStreamingData() (dict cu demux si pids = [(pid, tip), ...]) -> "+<demux>:<pid>:<tip>,...\\n", sau None cand
	acordul nu e gata (None, fara demux, fara PID-uri)."""
	if not isinstance(date, dict):
		return None
	demux = date.get("demux")
	pids = date.get("pids") or []
	try:
		demux = int(demux)
	except (TypeError, ValueError):
		return None
	if not 0 <= demux <= 9:      # transtreamproxy citeste o singura cifra
		return None
	parti = []
	for x in pids:
		try:
			pid, tip = int(x[0]), str(x[1])
		except (TypeError, ValueError, IndexError):
			continue
		if 0 <= pid <= 0x1fff and tip and "," not in tip and ":" not in tip:
			parti.append("%x:%s" % (pid, tip))
	if not parti:
		return None
	return "+%d:%s\n" % (demux, ",".join(parti))


def _transponder(ref):
	"""(tsid, onid, namespace) din referinta, pentru intrebarea "acelasi tuner?"."""
	parti = (ref or "").split(":")
	if len(parti) < 7:
		return None
	try:
		return tuple(int(x, 16) for x in parti[4:7])
	except ValueError:
		return None


def _refText(ref):
	try:
		return ref.toString()
	except Exception:
		return str(ref or "")


class _Fabrica(object):
	"""Ce ia modulul din enigma2 (pe receptor). Probele dau alta."""

	def record(self, ref):
		from enigma import eServiceCenter, eServiceReference
		return eServiceCenter.getInstance().record(eServiceReference(ref))

	def ceas(self, functie):
		from enigma import eTimer
		t = eTimer()
		t.callback.append(functie)
		return t

	def navigatie(self):
		try:
			from Navigation import Navigation
			return Navigation
		except Exception:
			return None


FABRICA = _Fabrica()


def _laZap(nav, playref, *rest):
	_cedeaza(_refText(playref), "zap")
	return playref


def _laInregistrare(nav, ref, *rest):
	simulare = False
	try:
		import sys
		simulare = bool(sys._getframe(1).f_locals.get("simulate", False))
	except Exception:
		simulare = False
	if not simulare:
		_cedeaza(_refText(ref), "inregistrare")
	return ref


def _cedeaza(ref, motiv):
	"""Opreste sesiunile de pe alt transponder decat ref (televizorul sau o inregistrare adevarata au nevoie de tuner)."""
	tinta = _transponder(ref)
	for ses in list(_SESIUNI):
		if tinta is None or _transponder(ses.ref) != tinta:
			_jurnal("cedez tunerul (%s): %s" % (motiv, ses.ref))
			ses.opreste()


def _laGrup(nav, grup, liber, inregistrare=False, *rest):
	"""Navigation.grupFaraTuner (0.7.7): niciuna dintre alternativele unui grup n-are tuner, deci zap-ul si inregistrarea
	nu ajung la _laZap / _laInregistrare. Ca acolo, pe alternativele DVB ale grupului: _cedeazaGrup. Fara sesiuni,
	alternativele nici nu se citesc. Nicio eroare nu opreste zap-ul sau inregistrarea."""
	if not _SESIUNI:
		return
	try:
		tv = None
		if inregistrare:
			try:
				tv = _refText(nav.getCurrentlyPlayingServiceReference())
			except Exception:
				tv = None
		_cedeazaGrup(nav.alternativeDvb(grup), liber, "inregistrare" if inregistrare else "zap", tv)
	except Exception as e:
		_jurnal("grupul de alternative: %r" % (e,))


def _cedeazaGrup(alternative, liber, motiv, tv=None):
	"""Sesiunile care nu sunt pe transponderul vreunei alternative se opresc, cea mai noua intai, pana cand liber() spune
	ca o alternativa are tuner; la o inregistrare raman si cele de pe transponderul televizorului `tv` (impart tunerul cu
	el). Fara alternative DVB nu se opreste nimic. -> cate s-au oprit."""
	tinte = set(t for t in (_transponder(a) for a in alternative or () if str(a).split(":")[0] == "1") if t is not None)
	if not tinte:
		return 0
	raman = set(tinte)
	tp_tv = _transponder(tv) if tv else None
	if tp_tv is not None:
		raman.add(tp_tv)
	n = 0
	for ses in reversed(list(_SESIUNI)):
		if _transponder(ses.ref) in raman:
			continue
		_jurnal("cedez tunerul (%s, grupul de alternative %s): %s" % (motiv, ", ".join(alternative), ses.ref))
		ses.opreste()
		n += 1
		if liber():
			break
	return n


def _listeNavigatie():
	nav = FABRICA.navigatie()
	if nav is None:
		return ()
	# (lista, functia, la inceput): la zap si la inregistrare la inceput; la grupurile de alternative la coada, dupa
	# releele DAB+ / DVB-T2 si fluxurile 8001 (ordinea din Navigation.grupFaraTuner)
	return ((getattr(nav, "playServiceExtensions", None), _laZap, True),
		(getattr(nav, "recordServiceExtensions", None), _laInregistrare, True),
		(getattr(nav, "grupFaraTuner", None), _laGrup, False))


def _puneExtensiile():
	if _EXTENSII[0]:
		return
	for lista, f, la_inceput in _listeNavigatie():
		if isinstance(lista, list) and f not in lista:
			if la_inceput:
				lista.insert(0, f)
			else:
				lista.append(f)
	_EXTENSII[0] = True


def _scoateExtensiile():
	if not _EXTENSII[0]:
		return
	_EXTENSII[0] = False
	for lista, f, _la_inceput in _listeNavigatie():
		while isinstance(lista, list) and f in lista:
			lista.remove(f)


class _Sesiune(object):
	def __init__(self, request, ref):
		self.r = request
		self.ref = ref
		self.rec = None
		self.ceas = None
		self.ultim = None
		self.asteptat = 0
		self.gata = False

	def _scrie(self, text):
		try:
			self.r.write(text.encode("ascii"))
			return True
		except Exception as e:
			_jurnal("scrierea spre transtreamproxy: %r" % (e,))
			self.opreste()
			return False

	def eroare(self, motiv):
		_jurnal("%s: %s" % (self.ref, motiv))
		if not self.gata:
			self._scrie("-SERVICE ERROR:-%s\n" % motiv)
		self.opreste()
		return False

	def porneste(self):
		try:
			rec = FABRICA.record(self.ref)
		except Exception as e:
			return self.eroare("inregistrarea nu se face (%r)" % (e,))
		if rec is None:
			return self.eroare("referinta necunoscuta")
		self.rec = rec
		cedeaza = getattr(rec, "setYieldsToZap", None)
		if cedeaza is not None:
			try:
				cedeaza(True)
			except Exception as e:
				_jurnal("cedarea la zap: %r" % (e,))
		try:
			rez = rec.prepareStreaming()
		except Exception as e:
			return self.eroare("acordul nu porneste (%r)" % (e,))
		if rez:
			return self.eroare("acordul nu porneste (%s)" % rez)
		try:
			rez = rec.start()
		except Exception as e:
			return self.eroare("inregistrarea nu porneste (%r)" % (e,))
		if rez:
			return self.eroare("inregistrarea nu porneste (%s)" % rez)
		self._ruleaza("sesiune pornita")
		return True

	def preia(self, vechi):
		"""Ia acordul unei sesiuni pentru acelasi canal care n-a dat inca PID-uri. transtreamproxy asteapta cam 3 s
		raspunsul pe o legatura; daca acordul dureaza mai mult, cere din nou pe o legatura noua si o lasa deschisa pe
		cea veche (nu o mai citeste). Acordul continua aici, fara o a doua inregistrare pe acelasi canal."""
		self.rec, vechi.rec = vechi.rec, None
		self.asteptat = vechi.asteptat
		self._ruleaza("sesiune preluata")    # intra in lista inainte ca cea veche sa iasa (extensiile raman)
		vechi.opreste()
		return True

	def _ruleaza(self, nota):
		_SESIUNI.append(self)
		_puneExtensiile()
		try:
			self.r.notifyFinish().addBoth(self._plecat)
		except Exception as e:
			_jurnal("notifyFinish: %r" % (e,))
		self.ceas = FABRICA.ceas(self._sondaj)
		self.ceas.start(SONDAJ_MS, False)
		_jurnal("%s %s" % (nota, self.ref))
		self._sondaj()

	def _eroareRec(self):
		f = getattr(self.rec, "getError", None)
		if f is None:
			return 0
		try:
			e = f()
			if isinstance(e, (tuple, list)):
				e = e[-1]
			return int(e or 0)
		except Exception:
			return 0

	def _sondaj(self):
		if self.gata or self.rec is None:
			return
		eroare = self._eroareRec()
		if eroare:
			self.eroare("tunerul nu se poate folosi (%d)" % eroare)
			return
		try:
			s = self.rec.stream()
			date = s.getStreamingData() if s is not None else None
		except Exception as e:
			date = None
			_jurnal("getStreamingData: %r" % (e,))
		rand = randul(date)
		if rand is not None:
			if rand != self.ultim:
				self.ultim = rand
				self._scrie(rand)
			return
		if self.ultim is None:
			self.asteptat += SONDAJ_MS
			if self.asteptat >= PORNIRE_MAX_MS:
				self.eroare("canalul nu porneste (fara semnal sau tuner ocupat)")

	def _plecat(self, *_):
		if not self.gata:
			_jurnal("transtreamproxy a inchis legatura %s" % self.ref)
		self.opreste(finish=False)

	def opreste(self, finish=True):
		if self.gata:
			return
		self.gata = True
		if self.ceas is not None:
			try:
				self.ceas.stop()
			except Exception:
				pass
			self.ceas = None
		rec, self.rec = self.rec, None
		if rec is not None:
			try:
				rec.stop()
			except Exception as e:
				_jurnal("oprirea inregistrarii: %r" % (e,))
		while self in _SESIUNI:
			_SESIUNI.remove(self)
		if not _SESIUNI:
			_scoateExtensiile()
		if finish:
			try:
				self.r.finish()
			except Exception:
				pass


def h_stream(c):
	"""Ruta /web/stream (RUTE_WEB din aplicatii_web)."""
	request = c.r
	ref = refCurata(c.arg("StreamService", "", 200))
	request.setResponseCode(200)
	request.setHeader(b"content-type", b"text/plain; charset=utf-8")
	request.setHeader(b"cache-control", b"no-store")
	if ref is None:
		return b"-SERVICE ERROR:-referinta gresita\n"
	if request.method == b"HEAD":
		return b""
	vechi = next((s for s in _SESIUNI if s.ref == ref and s.ultim is None and s.rec is not None), None)
	if vechi is not None:
		_Sesiune(request, ref).preia(vechi)
		return c.NOT_DONE_YET
	if len(_SESIUNI) >= SESIUNI_MAX:
		return b"-SERVICE ERROR:-prea multe transcodari deodata\n"
	_Sesiune(request, ref).porneste()     # o eroare la pornire e scrisa si cererea e inchisa
	return c.NOT_DONE_YET
