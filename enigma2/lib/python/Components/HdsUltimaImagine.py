# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsUltimaImagine.py: poza canalului la schimbare (PROBA DE CONCEPT, 11.11.2026, oprita din fabrica pana o vede Eduard).
#
# Dupa zap, decodorul asteapta cadrul-cheie si sincronizarea (pe canalele HD mari ~0,4 s + 0,5-1 s, masurat din flux cu
# unelte/stb/analiza_gop_ts.py). Cat asteapta, se arata pe loc ultima imagine vazuta pe canalul nou, peste video, iar cand
# vine imaginea vie poza se ascunde. Imaginea vie nu vine nici mai devreme, nici mai tarziu: ce castiga omul e ca vede pe
# loc canalul pe care a ajuns.
#
# Setarea: config.av.hds_zap_poza (Setari > Video, randul „Poza canalului la schimbare”, si pagina web /video), oprita din
# fabrica. Oprita: nu se face nicio poza si nu se arata nimic (modulul doar asculta evenimentele, fara lucru).
#
# Pozele:
# - se fac cu grab (numai imaginea canalului, -v, latimea LATIME, JPEG CALITATE) pe un fir, la DUPA_IMAGINE_S dupa ce
#   imaginea vie a venit si apoi o data la REFACERE_S cat omul ramane pe canal; niciodata la zap. Paza capturilor din
#   web (Plugins/Extensions/HdsWebControl/captura_sigura.py) hotaraste daca decodorul poate fi citit acum (nu dupa
#   pornire, nu in standby, nu la radio, cel mult o data la 1,5 s), aceeasi pentru web si pentru aceste poze;
# - stau NUMAI in memorie (DOSAR, /tmp e tmpfs): nimic pe memoria interna; la repornire se pierd; cel mult MAX_POZE si
#   MAX_OCTETI (cele mai vechi se sterg); o poza aproape goala (sub MIN_OCTETI: ecran negru, canal nedecriptat) nu se
#   pastreaza;
# - numele: cheia canalului (primele 10 campuri ale referintei), fara caractere de cale.
#
# Aratarea: la evStart (inaintea acordarii) se porneste numai decodarea JPEG-ului pe firul lui ePicLoad (fara lucru greu
# pe firul enigma2, unde orice milisecunda intarzie comanda catre tuner); cand decodarea e gata (dupa ce playService s-a
# terminat), poza se pune in fereastra nemodala de pe tot ecranul, sub bare (zPosition -3) si se arata. Se ascunde:
# - pe HiSilicon (exista /proc/msp/sync00): cand driverul spune ca a ARATAT primul cadru al zap-ului (VidFirstPlay si
#   VidFirstPlayTime de dupa evStart, cu o marja de PRAG_INAINTE_MS, in oricare instanta /proc/msp/syncNN: instantele se
#   fac la cerere si raman de la canalele de dinainte); citit pe un fir la SONDA_MS de la evStart, cel mult TIMP_MAX_S
#   (evenimentul video vine prea tarziu, iar citirea instantelor ia pe firul enigma2 pana la ~150 ms); inainte de el
#   ecranul ar arata cadrul vechi tinut (zapmode „hold”); fara campul in niciuna: pe loc. Daca imaginea vie e DEJA pe
#   ecran cand poza e gata (redarea fisierelor: primul cadru vine inaintea lui evStart), poza nu se mai arata;
# - pe celelalte: la primul eveniment video (evVideoSizeChanged, evVideoFramerateChanged, evVideoProgressiveChanged);
# - oricum: dupa TIMP_MAX_S, la evTuneFailed, la evEnd/evStopped si la zap-ul urmator.
# Fisierul /tmp/hds-poza-fisiere (numai pentru probe, nu-l pune nimic din imagine) lasa si redarea fisierelor .ts sa
# primeasca poza, ca pe .122 fara antena sa se poata masura cu o inregistrare.
# Timpii fiecarei aratari (evStart -> decodat -> aratat -> desenat -> imaginea vie -> ascuns) se scriu in JURNAL
# (/tmp, ultimele PASTRATE randuri), pentru masuratori.
#
# Fisierul nu importa nimic din enigma la incarcare (probele de pe PC folosesc functiile fara efecte).

import os
import threading
import time

DOSAR = "/tmp/hds-poze-canale"
JURNAL = "/tmp/hds-poza-canal.log"
PROBA_FISIERE = "/tmp/hds-poza-fisiere"
SYNC = "/proc/msp/sync00"
LATIME = 480
CALITATE = 60
MAX_POZE = 120
MAX_OCTETI = 4 * 1024 * 1024
MIN_OCTETI = 2500
DUPA_IMAGINE_S = 10
REFACERE_S = 600
TIMP_MAX_S = 4.0
SONDA_MS = 50     # citirea instantelor pe fir; o citire a luat pe .122 2-157 ms
PRAG_INAINTE_MS = 1500   # imaginea vie aratata cu atat inainte de evStart = a acestui zap (instantaVie)
TIMP_GRAB_S = 8
PASTRATE = 200
TIPURI_RADIO = ("2", "a", "A")
_T0 = time.monotonic


def _jurnal(text):
	print("[HdsUltimaImagine] %s" % text)


def N_(text):
	return text


def _t(text):
	try:
		from Components.Language import language   # noqa: F401 (limba activa)
		return _(text)  # noqa: F821 (pus de enigma in builtins)
	except Exception:
		return text


ETICHETA = N_("Poza canalului la schimbare")
DESCRIERE = N_("La schimbarea canalului apare pe loc ultima imagine văzută pe canalul nou, până vine imaginea vie. "
	"Pozele stau numai în memorie și se pierd la repornire.")


# ---------------------------------------------------------------- functii fara efecte (probele de pe PC)

def cheie(ref_text):
	"""Cheia unui canal din referinta (textul eServiceReference): primele 10 campuri, litere mari, ':' -> '_'; None pentru
	o referinta goala. Numele canalului (dupa al 10-lea camp) si calea unui fisier nu intra."""
	if not ref_text:
		return None
	campuri = ref_text.split(":")
	if len(campuri) < 10:
		return None
	k = "_".join(c.strip().upper() for c in campuri[:10])
	if not k.replace("_", "").isalnum():
		return None
	return k


def eFisier(ref_text):
	"""True pentru redarea unui fisier (calea dupa al 10-lea camp, ca la inregistrari)"""
	campuri = (ref_text or "").split(":")
	return len(campuri) > 10 and campuri[10].startswith("/")


def eRadio(ref_text):
	campuri = (ref_text or "").split(":")
	return len(campuri) > 2 and campuri[2] in TIPURI_RADIO


def cheieFisier(ref_text):
	"""Cheia unei redari de fisier (numai cu PROBA_FISIERE): numele fisierului, numai litere si cifre"""
	campuri = (ref_text or "").split(":")
	if len(campuri) <= 10:
		return None
	nume = campuri[10].rsplit("/", 1)[-1]
	k = "".join(ch for ch in nume if ch.isalnum())[:80]
	return ("F_" + k) if k else None


def calePoza(k, dosar=None):
	return os.path.join(dosar or DOSAR, k + ".jpg")


def deSters(intrari, max_poze=MAX_POZE, max_octeti=MAX_OCTETI):
	"""intrari = [(nume, marime, mtime)]; -> numele de sters (cele mai vechi intai) ca sa ramana cel mult max_poze si
	max_octeti"""
	ordonate = sorted(intrari, key=lambda e: e[2], reverse=True)   # cele mai noi intai
	pastrate = []
	total = 0
	sterse = []
	for nume, marime, _mtime in ordonate:
		if len(pastrate) < max_poze and total + marime <= max_octeti:
			pastrate.append(nume)
			total += marime
		else:
			sterse.append(nume)
	return sterse


def primulCadruAratat(text):
	"""Din textul /proc/msp/syncNN: True cand driverul a aratat primul cadru (VidFirstPlay: 1), False cand nu, None cand
	campul lipseste"""
	if not text:
		return None
	i = text.find("VidFirstPlay ")
	if i < 0:
		i = text.find("VidFirstPlay:")
		if i < 0:
			return None
	rest = text[i:i + 60].split(":", 1)
	if len(rest) < 2:
		return None
	val = rest[1].strip().split()
	if not val:
		return None
	try:
		return int(val[0].split("|")[0]) != 0
	except ValueError:
		return None


def campSync(text, nume):
	"""valoarea intreaga a campului `nume` din textul syncNN („Nume   :valoare|...”), sau None"""
	i = text.find(nume + " ") if text else -1
	while i >= 0:
		rest = text[i + len(nume):i + len(nume) + 40]
		if rest[:1] in (" ", ":"):
			p = rest.split(":", 1)
			if len(p) == 2 and p[0].strip() == "":
				v = p[1].strip().split("|")[0].split()
				try:
					return int(v[0]) if v else None
				except ValueError:
					return None
		i = text.find(nume + " ", i + 1)
	return None


def stareInstanta(text):
	"""(VidFirstPlay, VidFirstPlayTime, Systime) din textul unei instante syncNN (None unde lipseste)"""
	return campSync(text, "VidFirstPlay"), campSync(text, "VidFirstPlayTime"), campSync(text, "Systime")


def instantaVie(stari, ms_de_la_start, prag_ms=PRAG_INAINTE_MS):
	"""-> numele instantei syncNN care a ARATAT primul cadru al zap-ului de acum: VidFirstPlay 1 si VidFirstPlayTime cel
	mult prag_ms inainte de evStart (Systime din aceeasi citire minus ms_de_la_start; acelasi ceas, ms). Pragul: pe .122
	(11.11.2026) la redarea unui fisier primul cadru a venit cu 150-380 ms INAINTEA ascultatorilor Python ai lui evStart.
	O instanta ramasa de la un canal privit mai demult nu conteaza. "" cand niciuna; None cand nicio instanta nu are
	campul. stari = {nume: (VidFirstPlay, VidFirstPlayTime, Systime)}."""
	if not stari or all(st[0] is None for st in stari.values()):
		return None
	for nume in sorted(stari):
		a, cand, acum = stari[nume]
		if a and cand is not None and acum is not None and cand >= acum - ms_de_la_start - prag_ms:
			return nume
	return ""


def poateArata(pornit, ref_text, exista, proba_fisiere=False):
	"""-> (da, cheie) la evStart: setarea pornita, canal TV (nu radio), fisier numai cu proba, poza existenta"""
	if not pornit or not ref_text or eRadio(ref_text):
		return False, None
	if eFisier(ref_text):
		if not proba_fisiere:
			return False, None
		k = cheieFisier(ref_text)
	else:
		k = cheie(ref_text)
	if k is None:
		return False, k
	return bool(exista(k)), k


# ---------------------------------------------------------------- partea vie (pe receptor)

class _Stare(object):
	def __init__(self):
		self.sesiune = None
		self.nav = None
		self.ecran = None
		self.picload = None
		self.zap = 0              # numarul zap-ului (o decodare veche nu se mai arata)
		self.k = None             # cheia canalului de acum (pentru poze)
		self.decodare = None      # (zap, cheie) cat ePicLoad decodeaza
		self.aratat = False
		self.viu = False          # imaginea vie a venit (dupa driver, sau primul eveniment video)
		self.t = {}               # timpii aratarii de acum (ms de la evStart)
		self.tStart = 0.0
		self.ceasAscunde = None
		self.ceasSonda = None
		self.ceasDesen = None
		self.ceasPoza = None
		self.grabInCurs = False
		self.lacat = threading.Lock()
		# 12.11.2026: pe receptoarele cu libreader (SF8008 si celelalte) driverul nu suporta citiri din /proc/msp in timpul
		# zap-ului, deci acolo poza se ascunde la primul eveniment video, ca pe celelalte platforme (fara sonda)
		self.hisi = os.path.exists(SYNC) and not os.path.exists("/usr/bin/libreader")
		self.sondaRez = None    # (zap, nume/""/None) pus de firul sondei; firul enigma2 il vede pe ceasul lui


_S = _Stare()


def config():
	try:
		from Components.config import config as c
		return getattr(c.av, "hds_zap_poza", None)
	except Exception:
		return None


def initConfig():
	from Components.config import config as c, ConfigYesNo
	if getattr(c.av, "hds_zap_poza", None) is None:
		c.av.hds_zap_poza = ConfigYesNo(default=False)
	return c.av.hds_zap_poza


def pornit():
	e = config()
	return bool(e is not None and e.value)


def oferit():
	"""randul se arata numai cand exista grab (fara el nu se pot face poze)"""
	return os.path.exists("/usr/bin/grab")


def _ms():
	return int(round((_T0() - _S.tStart) * 1000.0))


def _ceas(fn):
	from enigma import eTimer
	t = eTimer()
	try:
		t.callback.append(fn)
	except AttributeError:
		t.timeout.get().append(fn)
	return t


def _opreste(t):
	if t is not None:
		try:
			t.stop()
		except Exception:
			pass


def _scrieJurnal(text):
	try:
		randuri = []
		if os.path.exists(JURNAL):
			with open(JURNAL) as f:
				randuri = f.read().splitlines()[-(PASTRATE - 1):]
		randuri.append(text)
		with open(JURNAL, "w") as f:
			f.write("\n".join(randuri) + "\n")
	except Exception as e:
		_jurnal("jurnalul: %s" % e)


# fereastra pozei: tot ecranul, fara chenar, sub bare si sub mesajul ecranului negru (zPosition -2); scrisa pentru 1920 si
# scalata la desktop. Skinurile pot avea <screen name="HdsUltimaImagineEcran"> cu un widget „poza”.
SKIN = """<screen name="HdsUltimaImagineEcran" position="0,0" size="1920,1080" flags="wfNoBorder" zPosition="-3" backgroundColor="#00000000">
	<widget name="poza" position="0,0" size="1920,1080" zPosition="1" scale="1" />
</screen>"""


def _clasaEcran():
	from Screens.Screen import Screen
	from Components.Pixmap import Pixmap
	from Tools.ScaledSkin import scaledSkin

	class HdsUltimaImagineEcran(Screen):
		def __init__(self, session):
			self.skin = scaledSkin(SKIN, 1920)
			Screen.__init__(self, session)
			self["poza"] = Pixmap()
	return HdsUltimaImagineEcran


def _ecran():
	if _S.ecran is None and _S.sesiune is not None:
		_S.ecran = _S.sesiune.instantiateDialog(_clasaEcran())
		try:
			_S.ecran.setAnimationMode(0)
		except Exception:
			pass
	return _S.ecran


def _picload():
	if _S.picload is None:
		from enigma import ePicLoad
		_S.picload = ePicLoad()
		_S.picload.PictureData.get().append(_decodat)
		# poza se decodeaza la marimea ei (LATIME x 16:9), fara redimensionare in program: pe .122 (11.11.2026) decodarea
		# cu redimensionare la 1920x1080 a luat 330-550 ms, mai mult decat prima imagine vie; intinderea pe tot ecranul o
		# face desenul elementului (scale="1" in skin)
		# latimea, inaltimea, aspectul, cache, redimensionarea (0 = simpla), fondul
		_S.picload.setPara((LATIME, LATIME * 9 // 16, 1, 1, False, 0, "#00000000"))
	return _S.picload


def _ascunde(motiv):
	"""ascunde poza (daca se vede) si scrie timpii; o decodare in curs ramane: _decodat n-o mai arata dupa imaginea vie
	(si o noteaza in jurnal), iar dupa un zap nou sau o oprire e uitata (_laStart, _eveniment)"""
	_opreste(_S.ceasAscunde)
	_opreste(_S.ceasSonda)
	if motiv in ("zap", "oprit"):
		_S.decodare = None
	if not _S.aratat:
		return
	_S.aratat = False
	if _S.ecran is not None:
		_S.ecran.hide()
	_S.t["ascuns"] = _ms()
	_S.t["motiv"] = motiv
	_scrieJurnal("zap %d %s | %s" % (_S.zap, _S.k or "-", " ".join("%s=%s" % kv for kv in sorted(_S.t.items()))))


def _decodat(*args):
	"""ePicLoad a terminat decodarea (pe firul enigma2): poza se pune si se arata, daca e tot zap-ul de acum"""
	d = _S.decodare
	_S.decodare = None
	if d is None or d[0] != _S.zap:
		return
	_S.t["decodat"] = _ms()
	if _S.viu:
		# imaginea vie a venit inaintea pozei: nu se mai arata
		_scrieJurnal("zap %d %s | nearatat (viu inainte) %s" % (_S.zap, _S.k or "-",
			" ".join("%s=%s" % kv for kv in sorted(_S.t.items()))))
		return
	try:
		ptr = _picload().getData()
	except Exception as e:
		_jurnal("getData: %s" % e)
		return
	if ptr is None:
		return
	rez = _S.sondaRez
	if _S.hisi and rez is not None and rez[0] == _S.zap and rez[1]:
		# sonda (pornita la evStart) a vazut deja primul cadru viu: poza nu se mai arata
		_S.viu = True
		_S.t["viu"] = _ms()
		_S.t["sync"] = rez[1]
		_scrieJurnal("zap %d %s | nearatat (viu inainte, driverul) %s" % (_S.zap, _S.k or "-",
			" ".join("%s=%s" % kv for kv in sorted(_S.t.items()))))
		_programeazaPoza(DUPA_IMAGINE_S)
		return
	e = _ecran()
	e["poza"].instance.setPixmap(ptr)
	e.show()
	_S.aratat = True
	_S.t["aratat"] = _ms()
	# eWidgetDesktop deseneaza pe un ceas de 0 ms pornit la show(); un ceas de 0 ms pornit acum vine dupa el
	if _S.ceasDesen is None:
		_S.ceasDesen = _ceas(_desenat)
	_S.ceasDesen.start(0, True)
	if _S.ceasAscunde is None:
		_S.ceasAscunde = _ceas(lambda: _ascunde("timp"))
	_S.ceasAscunde.start(int(TIMP_MAX_S * 1000), True)


def _desenat():
	if _S.aratat and "desenat" not in _S.t:
		_S.t["desenat"] = _ms()


def _fisiereSync():
	"""/proc/msp/sync00 si celelalte instante (11.11.2026: pe .122 redarea a mers pe sync03, iar sync00 a ramas neschimbat;
	la fel a vazut B pe .114); cautate din nou la fiecare citire (se fac si se desfac la cerere)"""
	baza = os.path.dirname(SYNC)
	try:
		return sorted(os.path.join(baza, n) for n in os.listdir(baza) if n.startswith("sync") and n[4:].isdigit()) or [SYNC]
	except Exception:
		return [SYNC]


def _citesteSync(cale=None):
	try:
		with open(cale or SYNC) as f:
			return f.read()
	except Exception:
		return ""


def _stari():
	"""{nume: (VidFirstPlay, VidFirstPlayTime, Systime)} pentru toate instantele syncNN de acum"""
	return dict((os.path.basename(c), stareInstanta(_citesteSync(c))) for c in _fisiereSync())


def _pornesteSonda():
	"""HiSilicon, la evStart, numai cand canalul are poza: un fir citeste instantele la SONDA_MS pana cand una a aratat
	primul cadru al acestui zap (instantaVie) sau pana la TIMP_MAX_S. Pe firul enigma2 nu se citeste nimic din /proc
	(pe .122 citirea instantelor a luat 2-157 ms la zap), numai rezultatul, pe ceasul _verificaSonda. Nu se asteapta
	evenimentul video: pe .122 el a venit la 1,0-1,2 s dupa evStart, dupa cadrul aratat de driver."""
	zap = _S.zap
	start = _S.tStart
	pana = start + TIMP_MAX_S
	_S.sondaRez = None

	def lucru():
		r = ""
		try:
			# pana la imaginea vie, la zap-ul urmator, la ascunderea pozei (oprire, timp) sau la TIMP_MAX_S
			while _S.zap == zap and not _S.viu and (_S.aratat or _S.decodare is not None) and _T0() < pana:
				# intai pauza: firul nu ia GIL-ul cat ruleaza inca ascultatorii lui evStart (pe .122, cu citirea pe loc,
				# ascultatorul meu a urcat la 23-28 ms)
				time.sleep(SONDA_MS / 1000.0)
				r = instantaVie(_stari(), int((_T0() - start) * 1000))
				if r is None or r:
					break
		except Exception as e:
			_jurnal("sonda: %s" % e)
		if _S.zap == zap:
			_S.sondaRez = (zap, r)
	threading.Thread(target=lucru, name="HdsUltimaImagineSonda", daemon=True).start()
	if _S.ceasSonda is None:
		_S.ceasSonda = _ceas(_verificaSonda)
	_S.ceasSonda.start(SONDA_MS, False)


def _verificaSonda():
	"""pe firul enigma2, la SONDA_MS: rezultatul firului sondei; poza (daca se vede) se ascunde cand driverul a aratat
	primul cadru viu; inainte de aratarea pozei rezultatul ramane pentru _decodat"""
	rez = _S.sondaRez
	if rez is None or rez[0] != _S.zap:
		return
	_opreste(_S.ceasSonda)
	if not _S.aratat:
		if rez[1] is not None and rez[1]:
			_S.viu = True
			_S.t["viu"] = _ms()
			_programeazaPoza(DUPA_IMAGINE_S)
		return
	r = rez[1]
	_S.t["viu"] = _ms()
	if r:
		_S.t["sync"] = r
	_S.viu = True
	_ascunde("viu" if r else ("fara-camp" if r is None else "sonda-timp"))
	_programeazaPoza(DUPA_IMAGINE_S)


def _imagineVie():
	"""primul eveniment video dupa evStart. Pe HiSilicon, cat se vede poza, o ascunde sonda (driverul spune cand a ARATAT
	cadrul; evenimentul video vine mai tarziu); altfel poza se ascunde acum. Fara poza: nimic de citit, numai poza
	canalului programata; o poza inca in decodare nu se mai arata (_decodat vede _S.viu)."""
	if _S.viu:
		return
	_S.t["video"] = _ms()
	if _S.hisi and _S.aratat:
		return
	_S.viu = True
	_S.t["viu"] = _S.t["video"]
	_ascunde("video")
	_programeazaPoza(DUPA_IMAGINE_S)


def _programeazaPoza(secunde):
	if not pornit():
		return
	if _S.ceasPoza is None:
		_S.ceasPoza = _ceas(_fotografiaza)
	_S.ceasPoza.start(int(secunde * 1000), True)


def _fotografiaza():
	"""pe firul enigma2: paza decodorului (aceeasi cu capturile din web), apoi grab pe un fir"""
	k = _S.k
	if not pornit() or k is None or _S.grabInCurs:
		return
	try:
		from Plugins.Extensions.HdsWebControl import captura_sigura as P
		ce, motiv = P.decide("video")
	except Exception as e:
		ce, motiv = "refuz", "paza: %s" % e
	if ce != "da":
		_jurnal("fara poza acum (%s %s)" % (ce, motiv))
		_programeazaPoza(30 if ce == "des" else REFACERE_S)
		return
	try:
		P.incepeVideo()
	except Exception:
		pass
	_S.grabInCurs = True
	threading.Thread(target=_grab, args=(k, _S.zap), name="HdsUltimaImagine").start()
	_programeazaPoza(REFACERE_S)


def _grab(k, zap):
	"""pe un fir: grab -v mic intr-un fisier temporar, pastrat numai daca nu e aproape gol si daca omul n-a schimbat
	canalul cat a mers grab-ul (altfel poza ar fi a altui canal); apoi curatenia dosarului"""
	import subprocess
	try:
		os.makedirs(DOSAR, exist_ok=True)
		tmp = os.path.join(DOSAR, ".nou-%s.jpg" % k)
		t0 = _T0()
		p = subprocess.Popen(["grab", "-v", "-q", "-j", str(CALITATE), "-r", str(LATIME), tmp],
			stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
		try:
			p.wait(timeout=TIMP_GRAB_S)
		except subprocess.TimeoutExpired:
			p.kill()
			_jurnal("grab nu a terminat in %d s" % TIMP_GRAB_S)
			return
		ms = int((_T0() - t0) * 1000)
		marime = os.path.getsize(tmp) if os.path.exists(tmp) else 0
		if zap != _S.zap:
			if os.path.exists(tmp):
				os.remove(tmp)
			_jurnal("poza %s aruncata: canalul s-a schimbat cat mergea grab" % k)
		elif p.returncode == 0 and marime >= MIN_OCTETI:
			os.replace(tmp, calePoza(k))
			_jurnal("poza %s: %d octeti in %d ms" % (k, marime, ms))
		else:
			if os.path.exists(tmp):
				os.remove(tmp)
			_jurnal("poza %s nepastrata (cod %s, %d octeti, %d ms)" % (k, p.returncode, marime, ms))
		curata()
	except Exception as e:
		_jurnal("grab: %s" % e)
	finally:
		_S.grabInCurs = False


def curata(dosar=None):
	dosar = dosar or DOSAR
	try:
		intrari = []
		for n in os.listdir(dosar):
			if n.endswith(".jpg") and not n.startswith("."):
				st = os.stat(os.path.join(dosar, n))
				intrari.append((n, st.st_size, st.st_mtime))
		for n in deSters(intrari):
			os.remove(os.path.join(dosar, n))
	except Exception as e:
		_jurnal("curatenia: %s" % e)


def stergeToate(dosar=None):
	"""setarea oprita: pozele se sterg (nimic tinut degeaba in memorie)"""
	dosar = dosar or DOSAR
	try:
		for n in os.listdir(dosar):
			os.remove(os.path.join(dosar, n))
	except Exception:
		pass


def _laStart():
	_opreste(_S.ceasPoza)
	_ascunde("zap")          # a zap-ului de dinainte, cu timpii lui
	_S.zap += 1
	_S.tStart = _T0()
	_S.t = {"t0": "%.3f" % _S.tStart}   # ceasul monoton = /proc/uptime (pentru probe)
	_S.viu = False
	_S.k = None
	if not pornit():
		return
	ref = None
	try:
		r = _S.nav.getCurrentlyPlayingServiceReference()
		ref = r.toString() if r is not None else None
	except Exception:
		pass
	da, k = poateArata(True, ref, lambda x: os.path.exists(calePoza(x)), os.path.exists(PROBA_FISIERE))
	_S.k = k
	if not da:
		return
	_S.decodare = (_S.zap, k)
	try:
		if _picload().startDecode(calePoza(k)):
			# ePicLoad inca decodeaza poza zap-ului de dinainte (zap-uri foarte dese): fara poza la acest zap
			_S.decodare = None
			_S.t["ocupat"] = 1
	except Exception as e:
		_S.decodare = None
		_jurnal("decodarea: %s" % e)
	if _S.hisi and _S.decodare is not None:
		_pornesteSonda()
	_S.t["start"] = _ms()


def _eveniment(ev):
	try:
		from enigma import iPlayableService as I
		if ev == I.evStart:
			_laStart()
		elif ev in (I.evVideoSizeChanged, getattr(I, "evVideoFramerateChanged", -100),
				getattr(I, "evVideoProgressiveChanged", -101)):
			if pornit():
				_imagineVie()
		elif ev in (I.evTuneFailed, I.evEnd, I.evStopped):
			_opreste(_S.ceasPoza)
			_ascunde("oprit")
	except Exception as e:
		_jurnal("evenimentul %s: %s" % (ev, e))


def _pregateste():
	"""fereastra si decodorul de poze facute dinainte (la pornirea setarii), nu la primul zap: altfel primul zap le-ar
	face pe firul enigma2, la evStart"""
	try:
		_ecran()
		_picload()
	except Exception as e:
		_jurnal("pregatirea: %s" % e)


def _schimbat(element):
	if not element.value:
		_ascunde("oprit")
		_opreste(_S.ceasPoza)
		stergeToate()
		return
	_pregateste()
	if _S.nav is not None and _S.k is None:
		# pornita acum: prima poza a canalului de acum peste DUPA_IMAGINE_S
		try:
			r = _S.nav.getCurrentlyPlayingServiceReference()
			ref = r.toString() if r is not None else None
			_S.k = cheie(ref) if ref and not eFisier(ref) and not eRadio(ref) else None
		except Exception:
			_S.k = None
		_programeazaPoza(DUPA_IMAGINE_S)


def porneste(session):
	"""din mytest.py, la pornirea interfetei: setarea si legatura la evenimentele serviciului"""
	e = initConfig()
	_S.sesiune = session
	_S.nav = getattr(session, "nav", None)
	try:
		from Components.SystemInfo import SystemInfo
		SystemInfo["HdsZapPoza"] = oferit()
	except Exception:
		pass
	if _S.nav is not None:
		_S.nav.event.append(_eveniment)
	e.addNotifier(_schimbat, initial_call=False)
	if e.value:
		_pregateste()
	return e
