# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsPrimaImagine.py: „Prima imagine rapidă” pe receptoarele HiSilicon cu programul de platforma libreader (Octagon
# SF8008 si SF8008 MINI, Uclan Ustym 4K PRO, Amiko Viper 4K V10 si celelalte cu /usr/bin/libreader).
#
# Driverul de sincronizare (hi_sync.ko) are pe fiecare instanta /proc/msp/syncNN campul bQuickOutput: cu 1, primul cadru
# decodat se arata pe loc (si sta pe loc pana porneste miscarea); cu 0, cadrul gata decodat asteapta sa-l prinda ceasul
# canalului (PCR). Pe .114 (SF8008, 11.11.2026) libreader pune instanta canalului viu pe 0 la FIECARE pornire a
# decodorului, iar primul cadru decodat a stat 269-815 ms (mediana ~550) pana a fost aratat; scris inapoi pe 1 dupa ce
# decodorul a pornit, cadrul apare cum e decodat. Pe Viper 4K V20/V30/V40 (fara libreader) e deja 1. zapmode nu il
# schimba (probat cu toate cele patru valori). Masurat pe .114 (12.11.2026, ms de la comanda de zap, mediane): canale
# fara criptare 2105 -> 1711 si 2489 -> 1791, OSCam (SAT.1 HD) 2451 -> 2186, SoftCSA 2889 -> 2496, zap-uri repezi (~1 s
# intre ele) 1948 -> 1440; decodarea la fel, ErrFrame 0, tasta -> tuner fara schimbare constanta.
#
# Cum (numai SCRIERI, niciodata citiri din /proc/msp in timpul zap-ului: driverul SF8008 nu suporta citiri atunci):
# - instantele syncNN se afla din lista dosarului /proc/msp (nu din continutul lor) la pornire si din nou dupa
#   LINISTE_S fara zap; libreader le face la pornirea lui (pe .114 sync00-03 de la inceput);
# - de la evTunedIn (semnal prins; decodorul porneste dupa el, din PID-urile tinute minte sau dupa PMT) pana la primul
#   eveniment video (primul cadru decodat; si evStart, evEnd, evTuneFailed opresc), cel mult TIMP_MAX_S, un fir scrie
#   „bQuickOutput = true” in TOATE instantele la PAS_S: cea a canalului viu e singura pe 0, celelalte sunt deja 1, deci
#   nu e nevoie sa aflam care e (asta ar cere o citire); o scriere poate astepta dupa driver (pe .114 uneori ~200 ms),
#   de aceea putine scrieri, rare (la SoftCSA primul eveniment video vine abia cu imaginea, deci firul merge pana la
#   termen);
# - o instanta care nu (mai) exista e sarita la acest zap; alta eroare de scriere = zap cu eroare; dupa
#   MAX_ZAPURI_EROARE zap-uri la rand cu erori, scrierea se opreste pana la repornirea interfetei (inapoi la felul
#   platformei), cu rand in jurnal.
# Setarea: config.av.hds_prima_imagine (Setari > Video, randul „Prima imagine rapidă”, si pagina /video), pornita din
# fabrica numai pe SF8008 si SF8008 MINI (MODELE_PORNITE), aratata numai unde exista libreader. /tmp/hds-zap-vechi (ca la masurarea zap-ului: toate schimbarile
# zap-ului odata) sau /tmp/hds-prima-imagine-veche (numai aceasta) opreste scrierea, pentru masurari inainte/dupa pe
# aceeasi pornire.
#
# Fisierul nu importa nimic din enigma la incarcare (probele de pe PC folosesc functiile fara efecte).

import os
import threading
import time

MSP = "/proc/msp"
LIBREADER = "/usr/bin/libreader"
ZAP_VECHI = "/tmp/hds-zap-vechi"
PROBA_OPRITA = "/tmp/hds-prima-imagine-veche"    # numai pentru proba A/B a acestui modul
COMANDA = b"bQuickOutput = true\n"
PAS_S = 0.1          # .114, 12.11.2026: acelasi castig ca la 25 ms / 3 s, cu 24-56 de scrieri pe zap in loc de 80-380
TIMP_MAX_S = 1.5     # de la evTunedIn; decodorul porneste la 10-250 ms dupa blocare
LINISTE_S = 10.0
MAX_ZAPURI_EROARE = 3
_T0 = time.monotonic


def _jurnal(text):
	print("[HdsPrimaImagine] %s" % text)


def N_(text):
	return text


ETICHETA = N_("Prima imagine rapidă")
DESCRIERE = N_("La schimbarea canalului primul cadru apare imediat ce e decodat și stă pe loc până pornește mișcarea, "
	"cu până la o jumătate de secundă mai devreme. Oprește dacă imaginea apare greșit la schimbarea canalului.")


# ---------------------------------------------------------------- functii fara efecte (probele de pe PC)

def instante(nume):
	"""din numele intrarilor lui /proc/msp: caile instantelor syncNN, in ordine"""
	return [os.path.join(MSP, n) for n in sorted(nume) if n.startswith("sync") and n[4:].isdigit()]


def oferitPe(msp_exista, libreader_exista):
	"""numai pe HiSilicon (/proc/msp) cu programul de platforma libreader"""
	return bool(msp_exista and libreader_exista)


# ---------------------------------------------------------------- partea vie

class _Stare(object):
	def __init__(self):
		self.nav = None
		self.instante = []
		self.zap = 0
		self.activ = False          # firul scrie (intre evTunedIn si primul eveniment video)
		self.pana = 0.0
		self.fir = None
		self.firZap = -1           # zap-ul firului de acum (un singur fir pe zap)
		self.eroriLaRand = 0
		self.oprit = False          # oprit pana la repornire, dupa erori
		self.ceasLiniste = None
		self.scrieri = 0            # cate scrieri reusite (pentru probe si jurnal)


_S = _Stare()


def config():
	try:
		from Components.config import config as c
		return getattr(c.av, "hds_prima_imagine", None)
	except Exception:
		return None


# pornita din fabrica numai unde masurarea a aratat castigul (SF8008 pe .114; SF8008 MINI e aceeasi placa si acelasi
# driver); pe celelalte receptoare cu libreader randul exista, dar e oprit pana sunt masurate (coordonatorul, 12.11.2026)
MODELE_PORNITE = ("sf8008", "sf8008m")


def pornitaDinFabrica(model):
	return (model or "").strip().lower() in MODELE_PORNITE


def initConfig():
	from Components.config import config as c, ConfigYesNo
	if getattr(c.av, "hds_prima_imagine", None) is None:
		try:
			from Components.SystemInfo import BoxInfo
			model = BoxInfo.getItem("model") or ""
		except Exception:
			model = ""
		c.av.hds_prima_imagine = ConfigYesNo(default=pornitaDinFabrica(model))
	return c.av.hds_prima_imagine


def oferit():
	return oferitPe(os.path.isdir(MSP), os.path.exists(LIBREADER))


def pornit():
	e = config()
	return (bool(e is not None and e.value) and not _S.oprit and not os.path.exists(ZAP_VECHI)
		and not os.path.exists(PROBA_OPRITA))


def _listeaza():
	"""lista instantelor din dosarul /proc/msp (numai numele intrarilor, nu continutul lor)"""
	try:
		_S.instante = instante(os.listdir(MSP))
	except OSError:
		_S.instante = []


def _scrie(cale):
	"""-> True scris, None instanta lipsa, False alta eroare"""
	try:
		fd = os.open(cale, os.O_WRONLY | getattr(os, "O_BINARY", 0))
	except OSError as e:
		return None if e.errno == 2 else False
	try:
		os.write(fd, COMANDA)
		return True
	except OSError:
		return False
	finally:
		os.close(fd)


def _lucreaza(zap):
	"""firul: scrie in toate instantele la PAS_S cat timp zap-ul e acelasi si scrierea e activa"""
	erori = 0
	reusite = 0
	cai = list(_S.instante)
	while _S.zap == zap and _S.activ and _T0() < _S.pana and cai:
		for cale in list(cai):
			r = _scrie(cale)
			if r is None:
				cai.remove(cale)
			elif r:
				reusite += 1
			else:
				erori += 1
		time.sleep(PAS_S)
	_S.scrieri += reusite
	if erori and not reusite:
		_S.eroriLaRand += 1
		_jurnal("zap %d: scrierea in /proc/msp/syncNN a esuat (%d erori)" % (zap, erori))
		if _S.eroriLaRand >= MAX_ZAPURI_EROARE:
			_S.oprit = True
			_jurnal("oprita pana la repornirea interfetei, dupa %d zap-uri la rand cu erori: felul platformei"
				% _S.eroriLaRand)
	elif reusite:
		_S.eroriLaRand = 0


def _incepe():
	"""evTunedIn: scrierea porneste pe un fir"""
	if not pornit() or not _S.instante:
		return
	_S.activ = True
	_S.pana = _T0() + TIMP_MAX_S
	zap = _S.zap            # un fir ramas de la zap-ul de dinainte se opreste singur (alt numar de zap)
	if _S.fir is not None and _S.fir.is_alive() and _S.firZap == zap:
		return              # al doilea evTunedIn in acelasi zap: firul lui scrie deja (termenul e prelungit)
	_S.firZap = zap
	_S.fir = threading.Thread(target=_lucreaza, args=(zap,), name="HdsPrimaImagine")
	_S.fir.daemon = True
	_S.fir.start()


def _opreste():
	_S.activ = False


def _laLiniste():
	_listeaza()


def _ceas(fn):
	from enigma import eTimer
	t = eTimer()
	t.callback.append(fn)
	return t


def _eveniment(ev):
	try:
		from enigma import iPlayableService as I
		if ev == I.evStart:
			_opreste()
			_S.zap += 1
			if _S.ceasLiniste is not None:
				_S.ceasLiniste.start(int(LINISTE_S * 1000), True)
		elif ev == I.evTunedIn:
			_incepe()
		elif ev in (I.evVideoSizeChanged, getattr(I, "evVideoFramerateChanged", -100),
				getattr(I, "evVideoProgressiveChanged", -101), I.evEnd, I.evTuneFailed, I.evStopped):
			_opreste()
	except Exception as e:
		_jurnal("evenimentul %s: %s" % (ev, e))


def porneste(session):
	"""din mytest.py, la pornirea interfetei: setarea si, numai unde e oferita, legatura la evenimentele serviciului"""
	e = initConfig()
	of = oferit()
	try:
		from Components.SystemInfo import SystemInfo
		SystemInfo["HdsPrimaImagine"] = of
	except Exception:
		pass
	if not of:
		return e
	_listeaza()
	_S.nav = getattr(session, "nav", None)
	if _S.nav is not None:
		_S.nav.event.append(_eveniment)
	try:
		_S.ceasLiniste = _ceas(_laLiniste)
	except Exception:
		_S.ceasLiniste = None
	_jurnal("instantele: %s" % ", ".join(os.path.basename(c) for c in _S.instante))
	return e
