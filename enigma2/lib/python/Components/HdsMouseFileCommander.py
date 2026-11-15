# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Mouse-ul in File Commander (navigatorul cu doua panouri de pe televizor), fara sa schimbam pluginul.

DE CE (Eduard, 14.11.2026 18:56): cu mouse-ul pus in receptor, in File Commander mergeau deja clicul, dublu clicul,
rotita si butoanele colorate (Components/HdsMouseEcran.py), dar:
- clicul in celalalt panou muta numai selectia acolo; panoul activ al pluginului (SOURCELIST / TARGETLIST) ramanea cel
  vechi pana la tasta stanga / dreapta, deci tasta galbena copia tot din panoul vechi;
- tragerea dintre panouri nu copia (MouseEcran.tras stie numai bara de derulare).
Ca in pagina web /fisiere: tragerea simpla copiaza, Shift + tragere muta, iar intrebarea e cea a tastelor pluginului.

CUM: MouseEcran.gest da gestul intai ecranului care are hdsGestMouse; pentru ecranele pluginului (FileCommanderScreen
si FileCommanderScreenFileSelect) adaptorul de aici tine locul acelei metode. Foloseste numai ce are pluginul in
sursa lui publica (OE-Alliance, oe-alliance-plugins/FileCommander, src/FileCommander/ui.py): componentele
list_left / list_right, atributul SOURCELIST, metodele listLeft() / listRight() (schimba panoul activ, ca tastele
stanga / dreapta) si goYellow() / goGreen() (copiaza / muta elementul ales din panoul activ in celalalt, cu intrebarea
lor). Daca o versiune a pluginului n-are ceva din acestea, adaptorul intoarce None si gestul merge ca inainte.
- clic (un clic) pe un rand din panoul inactiv: panoul devine activ si randul se alege (nu se deschide); al doilea clic
  sau dublu clicul il deschid, prin MouseEcran, ca in orice lista;
- tras din randul unui panou si lasat in celalalt panou: panoul de unde a plecat devine activ, randul tras se alege si
  se apasa galbenul (copiaza) sau, cu Shift tinut, verdele (muta). Lasat in acelasi panou sau in afara: nimic;
- tras pornit pe bara de derulare: merge ca inainte (MouseEcran).
Shift: din pagina web vine cu gestul (mod); de la mouse-ul USB se citeste din nucleu de pe tastatura pusa in receptor
(acelasi cititor ca editorul de canale, Screens.HdsEditorCanale.TastaturiNucleu).
In ecranul de selectie multipla (FileCommanderScreenFileSelect) goYellow / goGreen ale pluginului lucreaza cu elementele
bifate (selectedFiles), nu cu randul tras: tragerea copiaza / muta ce e bifat, ca in pagina web.
"""

ECRANE = ("FileCommanderScreen", "FileCommanderScreenFileSelect")
LISTE = ("list_left", "list_right")
SHIFT = frozenset((42, 54))   # KEY_LEFTSHIFT, KEY_RIGHTSHIFT


def _jurnal(text):
	print("[HdsMouseFileCommander] %s" % text)


def _cititorShiftNucleu():
	"""Codurile tastelor Shift / Ctrl apasate acum pe tastaturile receptorului, sau None."""
	try:
		from Screens.HdsEditorCanale import TastaturiNucleu
	except Exception:
		return None
	return TastaturiNucleu()


class AdaptorFileCommander(object):
	"""Gesturile mouse-ului pe ecranele pluginului. Tine minte numai trasul inceput intr-un rand."""

	def __init__(self, citeste_taste=None):
		self._citeste = citeste_taste
		self._cititor_cautat = citeste_taste is not None
		self._tras = None

	@staticmethod
	def potrivit(ecran):
		if ecran is None or type(ecran).__name__ not in ECRANE:
			return False
		for nume in ("listLeft", "listRight", "goYellow", "goGreen"):
			if not callable(getattr(ecran, nume, None)):
				return False
		return all(_componenta(ecran, n) is not None for n in LISTE)

	def pentru(self, ecran):
		"""Functia de forma hdsGestMouse pentru ecran, sau None daca ecranul nu e al pluginului."""
		if not self.potrivit(ecran):
			return None

		def gest(fel, x=None, y=None, clicuri=1, pasi=0, x0=None, y0=None, nou=False, text="", mod=None):
			return self.gest(ecran, fel, x, y, clicuri, x0, y0, nou, mod)
		return gest

	# ------------------------------------------------------------------ gesturile
	def gest(self, ecran, fel, x, y, clicuri=1, x0=None, y0=None, nou=False, mod=None):
		if fel == "clic" and clicuri < 2:
			return self._clic(ecran, x, y)
		if fel in ("clic", "dublu"):
			# dublu clic direct in panoul inactiv: intai panoul activ, apoi OK prin MouseEcran (deschide in panoul bun)
			gasit = _listaSub(ecran, x, y)
			if gasit is not None and not gasit[1].peBara(x):
				_activeaza(ecran, gasit[0])
			return None
		if fel == "drag":
			return self._tragere(ecran, x0 if x0 is not None else x, y0 if y0 is not None else y, nou)
		if fel == "dragend":
			return self._lasare(ecran, x, y, mod)
		return None

	def _clic(self, ecran, x, y):
		gasit = _listaSub(ecran, x, y)
		if gasit is None:
			return None
		nume, lista = gasit
		if lista.peBara(x) or _componenta(ecran, nume) is getattr(ecran, "SOURCELIST", None):
			return None
		rand = lista.randSub(y)
		_activeaza(ecran, nume)
		if _componenta(ecran, nume) is not getattr(ecran, "SOURCELIST", None):
			return None   # pluginul n-a schimbat panoul (lucreaza inca): clicul merge ca inainte
		if rand < lista.total():
			lista.inst.moveSelectionTo(rand)
		return {"facut": "selectie", "ecran": type(ecran).__name__, "lista": nume, "rand": lista.inst.getCurrentIndex(),
			"panou": "activ"}

	def _tragere(self, ecran, x0, y0, nou):
		if nou or self._tras is None or self._tras[0] != id(ecran):
			self._tras = None
			gasit = _listaSub(ecran, x0, y0)
			if gasit is None or gasit[1].peBara(x0):
				return None   # tras pe bara sau in afara listelor: MouseEcran
			nume, lista = gasit
			rand = lista.randSub(y0)
			self._tras = (id(ecran), nume, rand if rand < lista.total() else None)
		return {"facut": "nimic", "ecran": type(ecran).__name__, "tras": True, "lista": self._tras[1]}

	def _lasare(self, ecran, x, y, mod):
		tras, self._tras = self._tras, None
		if tras is None or tras[0] != id(ecran):
			return None   # trasul nu era al nostru (bara de derulare): MouseEcran
		rez = {"facut": "nimic", "ecran": type(ecran).__name__}
		sursa, rand = tras[1], tras[2]
		gasit = _listaSub(ecran, x, y)
		if rand is None or gasit is None or gasit[0] == sursa:
			return rez
		_activeaza(ecran, sursa)
		comp = _componenta(ecran, sursa)
		if comp is not getattr(ecran, "SOURCELIST", None):
			return rez
		try:
			comp.instance.moveSelectionTo(rand)
		except Exception as e:
			_jurnal("randul tras nu se alege: %r" % (e,))
			return rez
		muta = self._shift(mod)
		(ecran.goGreen if muta else ecran.goYellow)()
		rez.update(facut="mutare" if muta else "copiere", lista=sursa, rand=rand, tinta=gasit[0])
		return rez

	def _shift(self, mod):
		if mod is not None:
			return "shift" in mod
		if not self._cititor_cautat:
			self._cititor_cautat = True
			self._citeste = _cititorShiftNucleu()
		if self._citeste is None:
			return False
		try:
			apasate = self._citeste()
		except Exception:
			return False
		finally:
			inchide = getattr(self._citeste, "inchide", None)
			if callable(inchide):
				inchide()   # dispozitivele se deschid din nou la urmatoarea lasare (nu tinem fd-uri cat merge enigma2)
		return bool(apasate and set(apasate) & SHIFT)


def _componenta(ecran, nume):
	try:
		comp = ecran[nume]
	except (KeyError, TypeError, IndexError):
		return None
	return comp if getattr(comp, "instance", None) is not None else None


def _listaSub(ecran, x, y):
	"""(numele listei, Lista din HdsMouseEcran) pentru list_left / list_right de sub (x, y), sau None."""
	if x is None or y is None:
		return None
	from Components.HdsMouseEcran import Lista, _dreptunghi
	for nume in LISTE:
		comp = _componenta(ecran, nume)
		if comp is None:
			continue
		try:
			if not comp.instance.isVisible():
				continue
			r = _dreptunghi(comp.instance)
		except Exception:
			continue
		if r[2] > 0 and r[3] > 0 and r[0] <= x < r[0] + r[2] and r[1] <= y < r[1] + r[3]:
			return nume, Lista(nume, comp, comp.instance, r)
	return None


def _activeaza(ecran, nume):
	"""Panoul `nume` devine activ, ca la tasta stanga / dreapta a pluginului."""
	if _componenta(ecran, nume) is getattr(ecran, "SOURCELIST", None):
		return
	try:
		(ecran.listLeft if nume == "list_left" else ecran.listRight)()
	except Exception as e:
		_jurnal("panoul nu se schimba: %r" % (e,))
