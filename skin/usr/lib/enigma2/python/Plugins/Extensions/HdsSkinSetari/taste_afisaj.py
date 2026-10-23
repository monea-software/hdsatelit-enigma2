# -*- coding: utf-8 -*-
# Copyright (C) 2026 Monea Software pentru HD Satelit (https://hdsatelit.com, contact@moneasoftware.com)
# Licenta: GNU GPL versiunea 2. HDS-MARCA: skin HDSatelit, Monea Software pentru HD Satelit, 2026
#
# Tastele afisajului detaliat (a doua bara, pagina tehnica cu pagini) pe celelalte imagini, cu skinul HDSatelit
# (24.09.2026). Pe imaginea HDSatelit ecranul SecondInfoBar le are chiar el (Screens/SecondInfoBar.py) si aici nu
# se face nimic. Pe celelalte, cat se vede a doua bara, o harta de taste proprie, cu prioritatea -3 (inaintea
# hartilor imaginii), pusa pe INSTANTA barei, nu pe clasa:
#   stanga / dreapta = pagina anterioara / urmatoare, dupa ordinea de aratare (ghidul canalului primul);
#   sus / jos        = pe ghid (pagina 5) muta cursorul prin emisiuni, pe pagina 3 muta cursorul pistelor, pe pagina 4
#                      deruleaza lista CAID-urilor; pe celelalte trec mai departe, la purtarea imaginii (de pilda
#                      derularea descrierii emisiunii);
#   OK               = pe pagina 3 alege randul (pista audio, subtitrarea, canalul audio, downmix-ul) si bara ramane
#                      deschisa; pe celelalte trece mai departe (imaginea o inchide).
# Cursorul, alegerea si redesenarea sunt in Components/Converter/HdsCommon.py (sel_move, sel_ok, page_refresh), aceleasi
# ca pe imaginea HDSatelit. Cifrele, AUDIO, SUBTITLE, TEXT nu se prind.
#
# Unde se leaga: imaginile care au WHERE_INFOBARLOADED il cheama cu bara creata (InfoBar si MoviePlayer); in rest un
# ceas pornit la WHERE_SESSIONSTART asteapta InfoBar.instance. Bara a doua poate fi facuta din nou de imagine (la
# schimbarea setarii), deci legarea se verifica la fiecare aratare / ascundere a primei bare.
# Pornit doar pe imaginile cu acest carlig, altele decat HDSatelit; in rest nimic nu se schimba.

_stare = {"ceas": None, "incercari": 0, "urmarite": []}


def _carligul_barei():
	"""True pe imaginile care cheama pluginurile cu bara creata (WHERE_INFOBARLOADED)."""
	try:
		from Plugins.Plugin import PluginDescriptor
		return getattr(PluginDescriptor, "WHERE_INFOBARLOADED", None) is not None
	except Exception:
		return False


def _imagine_hdsatelit():
	"""True pe imaginea HDSatelit (menu.xml are intrarea panoului): acolo SecondInfoBar are tastele lui."""
	try:
		from .plugin import _imagineaAreIntrarea
		return _imagineaAreIntrarea()
	except Exception:
		return True


def _skin_hdsatelit():
	try:
		from Components.config import config
		return str(config.skin.primary_skin.value).startswith("HDSatelit/")
	except Exception:
		return False


def _pornit():
	return _skin_hdsatelit() and _carligul_barei() and not _imagine_hdsatelit()


def _conv():
	try:
		from Components.Converter import HdsCommon as C
		return C if hasattr(C, "sel_move") else None
	except Exception:
		return None


class _Taste(object):
	"""Harta de taste a unei bare a doua. Tine o referinta la bara doar cat traieste bara."""

	def __init__(self, bara, proprietar):
		from Components.ActionMap import ActionMap
		self.bara = bara
		self.proprietar = proprietar
		self.harta = ActionMap(["DirectionActions", "OkCancelActions"], {
			"left": lambda: self.pagina(-1), "right": lambda: self.pagina(1),
			"leftRepeated": lambda: self.pagina(-1), "rightRepeated": lambda: self.pagina(1),
			"up": lambda: self.cursor(-1), "down": lambda: self.cursor(1),
			"upRepeated": lambda: self.cursor(-1), "downRepeated": lambda: self.cursor(1),
			"ok": self.ok,
		}, -3)
		bara.onShow.append(self.arata)
		bara.onHide.append(self.ascunde)
		if getattr(bara, "shown", False):
			self.arata()

	def arata(self):
		try:
			if not self.harta.bound:
				self.harta.doBind()
		except Exception as e:
			print("[HdsSkinSetari] taste afisaj: %s" % e)

	def ascunde(self):
		try:
			if self.harta.bound:
				self.harta.doUnbind()
		except Exception:
			pass

	def _cititor(self, pagini=None):
		C = _conv()
		if C is None or C.page_active() not in (pagini or (C.SEL_PAGE,)):
			return C, None
		try:
			nav = self.proprietar.session.nav
			sursa = type("Sursa", (object,), {})()
			sursa.service = nav.getCurrentService()
			return C, C.Reader(sursa, None)
		except Exception:
			return C, None

	def pagina(self, d):
		C = _conv()
		if C is None:
			return 0
		try:
			if hasattr(C, "page_step"):
				C.page_step(d)
				return
			cur = C.page_active()
			valid = C.page_valid()
			if d > 0:
				alte = [p for p in valid if p > cur]
				C.page_set(alte[0] if alte else valid[0])
			else:
				alte = [p for p in valid if p < cur]
				C.page_set(alte[-1] if alte else valid[-1])
		except Exception as e:
			print("[HdsSkinSetari] pagina: %s" % e)

	def cursor(self, d):
		C = _conv()
		ghid = getattr(C, "EPG_PAGE", 0) if C is not None and hasattr(C, "epg_move") else 0
		pagini = (C.SEL_PAGE,) if C is not None else ()
		if ghid:
			pagini += (ghid, 4)
		C, r = self._cititor(pagini)
		if r is None:
			return 0  # alta pagina: tasta merge la imagine
		try:
			pagina = C.page_active()
			if pagina == ghid:
				if not C._epg_sel.get("drawn"):
					return 0  # skinul activ nu deseneaza lista
				if C.epg_move(r, d):
					C.page_refresh(ghid)
			elif pagina == 4:
				if C.ca_scroll(r, d):
					C.page_touch()
					C.page_refresh(4)
			elif C.sel_move(r, d):
				C.page_refresh()
		except Exception as e:
			print("[HdsSkinSetari] cursor: %s" % e)

	def ok(self):
		C, r = self._cititor()
		if r is None:
			return 0
		try:
			if C.sel_ok(r, self.proprietar):
				C.page_refresh()
		except Exception as e:
			print("[HdsSkinSetari] alegere: %s" % e)


def leaga(proprietar):
	"""Pune tastele pe bara a doua a proprietarului, daca nu sunt deja si daca bara nu le are singura."""
	bara = getattr(proprietar, "secondInfoBarScreen", None)
	if not bara or getattr(bara, "hdsSus", None) is not None:
		return False  # fara bara a doua, sau imaginea HDSatelit (le are chiar ecranul)
	if getattr(bara, "_hdsTasteAfisaj", None) is not None:
		return False
	try:
		bara._hdsTasteAfisaj = _Taste(bara, proprietar)
		print("[HdsSkinSetari] tastele afisajului legate pe %s" % bara.__class__.__name__)
		return True
	except Exception as e:
		print("[HdsSkinSetari] taste afisaj: %s" % e)
		return False


def urmareste(proprietar):
	"""Leaga acum si la fiecare aratare / ascundere a primei bare (bara a doua poate fi facuta din nou)."""
	if proprietar is None or not _pornit():
		return
	if getattr(proprietar, "_hdsUrmarit", False):
		leaga(proprietar)
		return
	try:
		proprietar._hdsUrmarit = True
		proprietar.onShow.append(lambda: leaga(proprietar))
		proprietar.onHide.append(lambda: leaga(proprietar))
	except Exception:
		pass
	leaga(proprietar)


def _tic():
	st = _stare
	st["incercari"] += 1
	try:
		from Screens.InfoBar import InfoBar
		ib = InfoBar.instance
	except Exception:
		ib = None
	if ib is not None:
		urmareste(ib)
	if ib is not None or st["incercari"] >= 120:
		try:
			st["ceas"].stop()
		except Exception:
			pass
		st["ceas"] = None


def porneste(session):
	"""WHERE_SESSIONSTART: pe imaginile fara WHERE_INFOBARLOADED, asteapta InfoBar.instance (cel mult 2 minute)."""
	if not _pornit() or _stare["ceas"] is not None:
		return
	try:
		from enigma import eTimer
		t = eTimer()
		try:
			t.callback.append(_tic)
		except AttributeError:
			_stare["legatura"] = t.timeout.connect(_tic)
		_stare["ceas"] = t
		t.start(1000, False)
	except Exception as e:
		print("[HdsSkinSetari] taste afisaj: %s" % e)
