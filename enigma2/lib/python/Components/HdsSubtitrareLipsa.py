# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsSubtitrareLipsa.py: semnul „canalul nu trimite acum subtitrari pe pagina aleasa”, pentru subtitrarile teletext.
#
# Un canal poate declara in PMT pagini de subtitrare teletext (de exemplu 777 si 778) fara sa le trimita: fluxul
# teletextului are atunci numai antete de umplere (pagina FF). Omul alege subtitrarea si nu se intampla nimic, fara
# nicio explicatie. Teletextul il culege nucleul pentru tot canalul (lib/dvb/hdsteletext.cpp, eHdsTeletext): orice
# antet al unei pagini o pune in memorie, deci versiune(pagina) > 0 inseamna ca pagina vine (si cand e goala, intre
# replici). Aici:
#  - hotarare(): vine / nu vine / nu se stie inca, din starea nucleului (fara enigma2, pentru probe);
#  - verifica(): aceeasi hotarare pentru o subtitrare (tuplul din subtitle().getSubtitleList()), cu nucleul de acum;
#  - Paza: dupa alegerea unei subtitrari teletext (Screens/InfoBarGenerics.py, InfoBarSubtitleSupport), la ~20 s,
#    un mesaj scurt care se inchide singur, o singura data pe canal si pagina cat ruleaza interfata. Subtitrarea
#    ramane aleasa: cand paginile incep sa vina, se vad singure.
# Pagina web „Sunet și subtitrări” (Plugins/Extensions/HdsWebControl/piste.py) arata acelasi text langa subtitrare.
# Subtitrarile DVB nu au un asemenea semn: intre replici fluxul lor poate tacea minute intregi, iar „nu vine” nu se
# poate deosebi de „nu se vorbeste”; pentru ele nu se spune nimic.
#
# Fisierul nu cere enigma2 la incarcare: probele de pe PC dau nucleul, ceasul si temporizatorul lor.
import time

ASTEPTARE_S = 20        # cat teletext trebuie sa fi venit pe canal inainte de „nu vine”
VERIFICARE_S = 5        # cat se asteapta intre doua verificari, cand inca nu se stie
RENUNTA_S = 90          # dupa atat, paza se opreste chiar daca tot nu se stie (canal fara teletext care vine)
ID_MESAJ = "HdsSubtitrareLipsa"
SECUNDE_MESAJ = 8


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_), fara efect: textul se traduce cand se arata."""
	return text


TEXT_NU_VINE = N_("Canalul nu trimite acum subtitrări pe pagina %s.")


def _t(text):
	try:
		return _(text)  # noqa: F821 (pus de enigma2 in builtins)
	except NameError:
		return text


def text_nu_vine(pagina):
	"""Mesajul pentru om, tradus: „Canalul nu trimite acum subtitrări pe pagina 777.”"""
	return _t(TEXT_NU_VINE) % pagina


def pagina_zecimala(pagina, magazin):
	"""Pagina din tuplul subtitrarii (pagina ca octet hexazecimal, magazinul 0..7; 0 = 8) -> 100..899, sau None
	(pagini cu cifre A-F nu au numar zecimal)."""
	try:
		p = int(pagina)
		m = int(magazin)
	except (TypeError, ValueError):
		return None
	if p < 0 or p > 0xFF or m < 0:
		return None
	text = "%d%02X" % ((m & 7) or 8, p)
	return int(text) if text.isdigit() else None


def hotarare(fel, pid, pagina, stare_nucleu, versiune, secunde, pachete_noi, asteptare=ASTEPTARE_S):
	"""True = pagina vine, False = nu vine (teletextul canalului vine de `asteptare` s, pagina nu), None = nu se stie.

	fel: 1 = teletext (altfel None); pid: PID-ul teletextului subtitrarii; pagina: 100..899 sau None;
	stare_nucleu: eHdsTeletext.stare() = (pid, pagini, subpagini, octeti, versiune, bune, rele) sau None;
	versiune: eHdsTeletext.versiune(pagina); secunde, pachete_noi: de cand si cate pachete bune au venit pe PID."""
	if fel != 1 or pagina is None or not stare_nucleu:
		return None
	try:
		pid_nucleu = int(stare_nucleu[0])
	except (TypeError, ValueError, IndexError):
		return None
	if pid_nucleu <= 0 or pid_nucleu != pid:
		return None
	if versiune and versiune > 0:
		return True
	if secunde < asteptare or pachete_noi <= 0:
		return None
	return False


class Observator(object):
	"""De cand vine teletextul PID-ului de acum, pe canalul de acum, si cate pachete bune au venit de atunci (contorul
	nucleului creste cat merge canalul si o ia de la zero la alt serviciu). Canalul conteaza: mai multe canale ale
	aceluiasi furnizor au acelasi PID de teletext."""

	def __init__(self, ceas=None):
		self.ceas = ceas or time.monotonic
		self._pid = None
		self._cheie = None
		self._bune0 = 0
		self._t0 = 0.0

	def vede(self, pid, bune, cheie=""):
		"""-> (secunde, pachete_noi) de la prima vedere a acestui PID pe acest canal."""
		acum = self.ceas()
		if pid != self._pid or cheie != self._cheie or bune < self._bune0:
			self._pid = pid
			self._cheie = cheie
			self._bune0 = bune
			self._t0 = acum
		return acum - self._t0, bune - self._bune0


_OBSERVATOR = Observator()


def _nucleu():
	try:
		from Components import HdsTeletext
		return HdsTeletext.nucleu()
	except Exception:
		return None


def verifica(tuplu, nucleu_dat=None, observator=None, cheie=""):
	"""Pentru o subtitrare (fel, pid, pagina, magazin, ...) a canalului `cheie` (referinta serviciului):
	(True/False/None, pagina 100..899 sau None)."""
	try:
		fel, pid, pag, mag = int(tuplu[0]), int(tuplu[1]), tuplu[2], tuplu[3]
	except (TypeError, ValueError, IndexError):
		return None, None
	pagina = pagina_zecimala(pag, mag)
	if fel != 1 or pagina is None:
		return None, pagina
	n = nucleu_dat if nucleu_dat is not None else _nucleu()
	if n is None:
		return None, pagina
	try:
		stare = n.stare()
		versiune = n.versiune(pagina)
	except Exception:
		return None, pagina
	obs = observator if observator is not None else _OBSERVATOR
	try:
		secunde, noi = obs.vede(int(stare[0]), int(stare[5]), cheie or "")
	except (TypeError, ValueError, IndexError):
		return None, pagina
	return hotarare(fel, pid, pagina, stare, versiune, secunde, noi), pagina


def text_pentru_web(tuplu, cheie="", nucleu_dat=None, observator=None):
	"""Textul de aratat langa subtitrare in pagina web, sau "" cand pagina vine sau nu se stie."""
	vine, pagina = verifica(tuplu, nucleu_dat, observator, cheie)
	return text_nu_vine(pagina) if vine is False else ""


def _arataMesaj(text):
	try:
		from Tools import Notifications
		from Screens.MessageBox import MessageBox
		Notifications.AddPopup(text, MessageBox.TYPE_INFO, SECUNDE_MESAJ, ID_MESAJ)
	except Exception as e:
		print("[HdsSubtitrareLipsa] mesajul nu s-a putut arata: %s" % e)


def _temporizator(functie):
	from enigma import eTimer
	t = eTimer()
	t.callback.append(functie)
	return t


class Paza(object):
	"""O subtitrare teletext aleasa: verificata la ASTEPTARE_S, apoi la VERIFICARE_S cat nu se stie, pana la
	RENUNTA_S. Mesajul o singura data pe (canal, pagina) cat ruleaza interfata."""

	def __init__(self, arata=None, temporizator=None, nucleu_dat=None, ceas=None):
		self.arata = arata or _arataMesaj
		self.nucleu_dat = nucleu_dat
		self.ceas = ceas or time.monotonic
		self.observator = Observator(self.ceas)
		self._timer = (temporizator or _temporizator)(self._verifica)
		self._tuplu = None
		self._cheie = ""
		self._pornit = 0.0
		self.aratate = set()

	def porneste(self, tuplu, cheie=""):
		self.opreste()
		try:
			if int(tuplu[0]) != 1:
				return False
		except (TypeError, ValueError, IndexError):
			return False
		self._tuplu = tuple(tuplu)
		self._cheie = cheie or ""
		self._pornit = self.ceas()
		verifica(self._tuplu, self.nucleu_dat, self.observator, self._cheie)  # incepe numaratoarea pe PID si canal
		self._timer.start(ASTEPTARE_S * 1000, True)
		return True

	def opreste(self):
		self._tuplu = None
		try:
			self._timer.stop()
		except Exception:
			pass

	def _verifica(self):
		if self._tuplu is None:
			return
		vine, pagina = verifica(self._tuplu, self.nucleu_dat, self.observator, self._cheie)
		if vine is None:
			if self.ceas() - self._pornit < RENUNTA_S:
				self._timer.start(VERIFICARE_S * 1000, True)
			else:
				self._tuplu = None
			return
		self._tuplu = None
		if vine is False:
			semn = (self._cheie, pagina)
			if semn in self.aratate:
				return
			self.aratate.add(semn)
			print("[HdsSubtitrareLipsa] pagina %s aleasa, dar canalul nu o trimite" % pagina)
			self.arata(text_nu_vine(pagina))


_PAZA = None


def pazeste(tuplu, cheie=""):
	"""Din InfoBarSubtitleSupport, la alegerea unei subtitrari (orice fel; numai teletextul e pazit)."""
	global _PAZA
	if _PAZA is None:
		_PAZA = Paza()
	return _PAZA.porneste(tuplu, cheie)


def opreste():
	"""Din InfoBarSubtitleSupport, la subtitrarea oprita sau la serviciul oprit."""
	if _PAZA is not None:
		_PAZA.opreste()
