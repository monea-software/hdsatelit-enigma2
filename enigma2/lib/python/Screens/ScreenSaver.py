# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# ScreenSaver.py: protectia ecranului (screensaverul). Dupa un timp fara nicio tasta, pe un ecran negru ramane numai o
# sigla care se muta din cand in cand, ca televizorul sa nu ramana zeci de minute cu aceeasi imagine.
#
# Acelasi mecanism si aceleasi nume ca in enigma2 OE-Alliance (din sursele GPL enigma2 (OE-Alliance), commitul
# 03eeb0ea5, Screens/ScreenSaver.py si InfoBarGenerics.InfoBarScreenSaver), ca pluginurile scrise pentru ele sa mearga:
# - clasa ScreenSaver (si numele vechi Screensaver), cu widgetul „picture” si numele de skin „ScreenSaver” / „Screensaver”;
# - mixinul InfoBarScreenSaver (il iau si playerele pluginurilor din Screens.InfoBarGenerics sau din Screens.ScreenSaver),
#   cu metoda pornirii ceasului in ambele forme: screenSaverTimerStart si ScreenSaverTimerStart;
# - setarile config.usage.screenSaverStartTimer (secundele; 0 = oprita), screenSaverMoveTimer (cat sta sigla pe loc) si
#   screenSaverMode (0 ecran negru, 1 sigla, 2 sigla canalului), puse de Components/HdsRadioSetari.initProtectie.
#
# Cand porneste ceasul (ScreenSaverTimerStart, la intoarcerea ecranului in fata, la pornirea unui serviciu, la pauza,
# la schimbarea verdictului „numai sunet” si la fiecare tasta):
# - pauza (seekstate[0]), ca in OE-Alliance;
# - un fisier de sunet sau un post de radio (tipul 2 / 0x0A) cand ecranul radio nu se vede (ecranul radio are odihna lui);
# - un canal TV numai cu sunet (Components/HdsEcranNegru.py, NUMAI_SUNET), cu setarea „La canalele numai cu sunet” pe
#   „Protecția ecranului” sau „amândouă” (Components/HdsRadioSetari.py).
# Fata de OE-Alliance: timpul se socoteste de la ultima tasta (ascultatorul de taste sta legat numai cat ceasul merge),
# iar prima tasta apasata cu protectia pe ecran numai o inchide (apasarea si eliberarea ei nu ajung la alte ecrane).
#
# Alte feluri de protectie (ceasuri, imagini) se adauga in FELURI, cu valoarea lor in HdsRadioSetari.PROTECTIE_FEL.

from os.path import isfile, splitext
from random import randrange

from enigma import ePoint, eSize, eTimer, eActionMap, getDesktop

from Components.config import config
from Components.Pixmap import Pixmap
from Screens.Screen import Screen
from Tools.ScaledSkin import scaledSkin

SIGLA = "hds-protectie-sigla.png"
MARGINE = 40                 # px pe 1920: overscan-ul televizorului
MUTARE_IMPLICIT_S = 10
STEAG_APASAT = 0
STEAG_ELIBERAT = 1
# prioritatea ascultatorului de taste: inaintea tuturor hartilor (OE-Alliance: -maxsize - 1; aici cel mai mic int pe 32
# de biti, ca pe orice receptor)
PRIO_TASTE = -0x7FFFFFFF - 1

# valorile config.usage.screenSaverMode (OE-Alliance)
FEL_NEGRU = 0
FEL_SIGLA = 1
FEL_SIGLA_CANAL = 2
FELURI = (FEL_NEGRU, FEL_SIGLA, FEL_SIGLA_CANAL)
# 0.7.5 (R075): screensaverul ales in meniul Screensaver (Components/HdsRadioSetari.PROTECTIE_FEL_ALES). Fereastra lui
# vine din Screens.HdsScreensaver.ecranAles(), socotita la FIECARE pornire („Automat” se schimba intre zi si noapte,
# „Pe rand” trece la urmatorul); ScreenSaver de aici ramane rezerva cand screensaverul ales nu se poate deschide.
FEL_ALES = 3

try:
	from Components.MovieList import AUDIO_EXTENSIONS
except ImportError:
	AUDIO_EXTENSIONS = frozenset((".mp3", ".mp2", ".m4a", ".flac", ".ogg", ".wav", ".wma", ".ac3", ".aac"))

SKIN = """
<screen name="ScreenSaver" position="0,0" size="1920,1080" backgroundColor="#00000000" flags="wfNoBorder" zPosition="20">
	<widget name="picture" position="0,0" size="440,80" alphatest="blend" transparent="1" zPosition="1" />
</screen>"""


def _jurnal(text):
	print("[ScreenSaver] %s" % text)


def _valoare(nume, implicit):
	try:
		return int(getattr(config.usage, nume).value)
	except Exception:
		return implicit


def secundePornire():
	"""config.usage.screenSaverStartTimer: dupa cate secunde fara taste porneste protectia; 0 = oprita."""
	try:
		from Components import HdsRadioSetari as S
		return S.secunde_protectie()
	except Exception:
		return _valoare("screenSaverStartTimer", 0)


def caleSigla():
	try:
		from Tools.Directories import resolveFilename, SCOPE_SKIN_IMAGE
		cale = resolveFilename(SCOPE_SKIN_IMAGE, SIGLA)
	except Exception:
		cale = "/usr/share/enigma2/" + SIGLA
	return cale if isfile(cale) else None


class ScreenSaver(Screen):
	"""Fereastra protectiei: ecran negru pe tot ecranul si widgetul „picture” (sigla), mutat la intamplare la fiecare
	screenSaverMoveTimer secunde, in ecran, cu MARGINE de jur imprejur."""

	def __init__(self, session):
		Screen.__init__(self, session)
		self.skinName = ["ScreenSaver", "Screensaver"]
		self.skin = scaledSkin(SKIN)
		self["picture"] = Pixmap()
		self.cale = None
		self.marime = None
		self.ecranW = self.ecranH = 0
		self.margine = MARGINE
		self.movePictureTimer = eTimer()
		self.movePictureTimer.callback.append(self.movePicture)
		self.onLayoutFinish.append(self.layoutFinished)
		self.onShow.append(self.showScreenSaver)
		self.onHide.append(self.hideScreenSaver)

	def layoutFinished(self):
		try:
			self.ecranW = self.instance.size().width()
			self.ecranH = self.instance.size().height()
			self.margine = max(8, MARGINE * self.ecranW // 1920)
			s = self["picture"].instance.size()
			self.marime_sigla = (s.width(), s.height())
			try:
				self["picture"].instance.setPixmapScale(4 | 8)   # sigla incape in widget, cu proportiile ei
			except Exception:
				pass
		except Exception as e:
			_jurnal("asezarea: %s" % e)
			self.marime_sigla = (0, 0)

	def _pune(self, cale, marime):
		inst = self["picture"].instance
		if cale != self.cale:
			inst.setPixmapFromFile(cale)
			self.cale = cale
		if marime != self.marime:
			inst.resize(eSize(*marime))
			self.marime = marime

	def _siglaCanal(self):
		"""Calea si marimea siglei canalului care merge (picon), sau None."""
		try:
			from Components.Renderer.Picon import getPiconName
			from Tools.LoadPixmap import LoadPixmap
			ref = self.session.nav.getCurrentlyPlayingServiceReference()
			cale = getPiconName(ref.toString()) if ref is not None else None
			if not cale or not isfile(cale):
				return None
			px = LoadPixmap(cale)
			if px is None:
				return None
			f = float(self.ecranW) / 1920 if self.ecranW else 1.0
			return cale, (max(1, int(px.size().width() * f * 1.5)), max(1, int(px.size().height() * f * 1.5)))
		except Exception as e:
			_jurnal("sigla canalului: %s" % e)
			return None

	def showScreenSaver(self):
		fel = _valoare("screenSaverMode", FEL_SIGLA)
		ales = None
		if fel == FEL_SIGLA_CANAL:
			ales = self._siglaCanal()
		if ales is None and fel != FEL_NEGRU:
			cale = caleSigla()
			if cale is not None:
				ales = (cale, self.marime_sigla)
		if ales is None:
			self["picture"].hide()
			return
		try:
			self._pune(*ales)
			self["picture"].show()
			self.movePicture()
		except Exception as e:
			_jurnal("sigla: %s" % e)
			self["picture"].hide()

	def hideScreenSaver(self):
		self.movePictureTimer.stop()

	def movePicture(self, timerActive=True):
		w, h = self.marime or (0, 0)
		maxX = max(1, self.ecranW - w - 2 * self.margine)
		maxY = max(1, self.ecranH - h - 2 * self.margine)
		try:
			self["picture"].instance.move(ePoint(self.margine + randrange(maxX), self.margine + randrange(maxY)))
		except Exception as e:
			_jurnal("mutarea: %s" % e)
		if timerActive:
			self.movePictureTimer.startLongTimer(max(1, _valoare("screenSaverMoveTimer", MUTARE_IMPLICIT_S)))


# numele vechi (pluginurile scrise pentru alte imagini OE-Alliance)
Screensaver = ScreenSaver


def _refAudio(ref):
	"""Un post de radio (tipul 2 sau 0x0A) sau un fisier de sunet, dupa referinta (ca in OE-Alliance)."""
	try:
		campuri = ref.toString().split(":")
	except Exception:
		return False
	if len(campuri) > 2 and campuri[2].upper() in ("2", "A"):
		return True
	return len(campuri) > 10 and splitext(campuri[10])[1].lower() in AUDIO_EXTENSIONS


class InfoBarScreenSaver:
	"""Mixinul protectiei pentru bara si pentru playere (si ale pluginurilor). Cere de la ecran: session, execing,
	hide / show, onExecBegin / onExecEnd; seekstate e folosit numai daca exista."""

	def __init__(self):
		self.screenSaverTimer = eTimer()
		self.screenSaverTimer.callback.append(self.screenSaverTimeout)
		self.screenSaver = None
		self.__rezerva = None       # fereastra ScreenSaver de aici (felurile 0, 1, 2)
		self.__ales = None          # fereastra screensaverului ales (felul FEL_ALES), facuta la nevoie
		self.__tastaLegata = False
		self.__inghite = None
		try:
			self.screenSaver = self.session.instantiateDialog(ScreenSaver)
			self.screenSaver.hide()
			self.__rezerva = self.screenSaver
		except Exception as e:
			_jurnal("fereastra nu se poate face: %s" % e)
		# numele din alte imagini (unele pluginuri il citesc)
		self.screensaver = self.screenSaver
		if hasattr(self, "onExecBegin"):
			self.onExecBegin.append(self.__onExecBegin)
			self.onExecEnd.append(self.__onExecEnd)
		if hasattr(self, "onClose"):
			self.onClose.append(self.__onClose)
		try:
			from Components.ServiceEventTracker import ServiceEventTracker
			from enigma import iPlayableService
			self.__urmarire_protectie = ServiceEventTracker(screen=self, eventmap={
				iPlayableService.evStart: self.__serviciuPornit,
			})
		except Exception as e:
			_jurnal("urmarirea serviciului: %s" % e)

	# ---- cand trebuie

	def screenSaverCerut(self):
		"""Ce merge acum cere protectia ecranului (vezi antetul Screens/ScreenSaver.py)."""
		session = self.session
		if getattr(session, "pipshown", False):
			return False
		stare = getattr(self, "seekstate", None)
		if stare and stare[0]:
			return True
		try:
			ref = session.nav.getCurrentlyPlayingServiceOrGroup()
		except Exception:
			ref = None
		try:
			from Components import HdsRadioSetari as S
		except ImportError:
			S = None
		if ref is not None and _refAudio(ref):
			return not (S is not None and S.ecran_radio_vizibil())
		if S is not None and S.numai_sunet_protectie():
			# canalul TV numai cu sunet: verdictul il tine legatura ecranului negru a barei (Screens/HdsEcranNegru.py)
			return bool(getattr(getattr(self, "hdsEcranNegru", None), "numai_sunet", False))
		return False

	def screenSaverTimerStart(self):
		if getattr(self, "screenSaverTimer", None) is None:
			return    # chemat (de pilda din InfoBarSeek.setSeekState) inainte de __init__-ul mixinului
		secunde = secundePornire()
		if secunde and self.screenSaverCerut():
			self.screenSaverTimer.startLongTimer(secunde)
			self.__legaTasta(True)
		else:
			self.screenSaverTimer.stop()
			if not (self.screenSaver is not None and self.screenSaver.shown):
				self.__legaTasta(False)

	# numele vechi (OE-Alliance mai vechi; il cheama si playerele pluginurilor)
	ScreenSaverTimerStart = screenSaverTimerStart

	def screenSaverTimeout(self):
		if self.screenSaver is None or not getattr(self, "execing", True):
			return
		try:
			from Screens import Standby
			if Standby.inStandby or getattr(Standby, "inTryQuitMainloop", False):
				return
		except ImportError:
			pass
		if not self.screenSaverCerut():
			return
		self.screenSaver = self.screensaver = self.__fereastraDeAratat()
		self.hide()
		pvr = getattr(self, "pvrStateDialog", None)
		if pvr is not None:
			try:
				pvr.hide()
			except Exception:
				pass
		self.screenSaver.show()
		self.__legaTasta(True)

	def __fereastraDeAratat(self):
		"""Fereastra pornirii de acum: cu felul FEL_ALES, screensaverul ales (clasa ceruta din nou de fiecare data, iar
		fereastra facuta din nou numai cand clasa s-a schimbat; ascunsa, isi opreste singura ceasurile); altfel, sau cand
		nu se poate deschide, ScreenSaver de aici."""
		if _valoare("screenSaverMode", FEL_SIGLA) != FEL_ALES:
			return self.__rezerva
		try:
			from Screens.HdsScreensaver import ecranAles
			clasa = ecranAles()
		except Exception as e:
			_jurnal("screensaverul ales: %s" % e)
			return self.__rezerva
		if self.__ales is not None and self.__ales.__class__ is not clasa:
			try:
				self.session.deleteDialog(self.__ales)
			except Exception:
				pass
			self.__ales = None
		if self.__ales is None:
			try:
				self.__ales = self.session.instantiateDialog(clasa)
				self.__ales.hide()
			except Exception as e:
				_jurnal("screensaverul ales nu se poate deschide: %s" % e)
				self.__ales = None
				return self.__rezerva
		return self.__ales

	# ---- tastele

	def __legaTasta(self, da):
		if da and not self.__tastaLegata:
			eActionMap.getInstance().bindAction("", PRIO_TASTE, self.screenSaverKeyPress)
			self.__tastaLegata = True
		elif not da and self.__tastaLegata:
			eActionMap.getInstance().unbindAction("", self.screenSaverKeyPress)
			self.__tastaLegata = False

	def screenSaverKeyPress(self, key, flag):
		"""Orice tasta socoteste timpul de la capat. Cu protectia pe ecran, prima tasta numai o inchide: apasarea si
		celelalte steaguri ale aceleiasi taste (repetare, tinere, eliberare) se opresc aici."""
		if self.__inghite is not None:
			if key == self.__inghite:
				if flag == STEAG_ELIBERAT:
					self.__inghite = None
					self.screenSaverTimerStart()
				return 1
			self.__inghite = None
		if self.screenSaver is not None and self.screenSaver.shown:
			self.screenSaver.hide()
			try:
				self.show()
			except Exception:
				pass
			if flag == STEAG_APASAT:
				self.__inghite = key
			else:
				self.screenSaverTimerStart()
			return 1
		if self.screenSaverTimer.isActive():
			self.screenSaverTimer.startLongTimer(secundePornire() or 1)
		return 0

	# ---- ecranul si serviciul

	def __serviciuPornit(self):
		if self.screenSaver is not None and self.screenSaver.shown:
			self.screenSaver.hide()
		self.screenSaverTimerStart()

	def __onExecBegin(self):
		self.screenSaverTimerStart()

	def __onExecEnd(self):
		if self.screenSaver is not None and self.screenSaver.shown:
			self.screenSaver.hide()
		self.__inghite = None
		self.screenSaverTimer.stop()
		self.__legaTasta(False)

	def __onClose(self):
		self.screenSaverTimer.stop()
		self.__legaTasta(False)
		for fereastra in (self.__rezerva, self.__ales):
			if fereastra is not None:
				try:
					self.session.deleteDialog(fereastra)
				except Exception:
					pass
		self.screenSaver = self.screensaver = self.__rezerva = self.__ales = None
