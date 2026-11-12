# -*- coding: utf-8 -*-
# Luat din sursele GPL enigma2 (OE-Alliance), commitul 29d951a6ec2e (12.11.2026), fisierul lib/python/Components/Addons/GUIAddon.py.
# Licenta GPL-2.0 (ca enigma2); notele autorilor raman neschimbate. Adus in imaginea HD Satelit (lotul TOT, 12.11.2026):
# addon-urile de tema (atributul addon= din skin), folosite de temele scrise pentru imaginile OE-Alliance.
# Schimbat de HD Satelit: paza addon-urilor (o eroare nu strica ecranul) si ignoreWidgets creat cand ecranul nu-l are.
from skin import getSkinFactor
from Components.GUIComponent import GUIComponent


# HD Satelit: un addon al unei teme straine care nu se potriveste cu listele imaginii nu strica ecranul (si nici tema):
# eroarea se scrie in jurnal, iar elementul addon-ului lipseste. Se aplica singur fiecarei clase derivate.
_METODE_PAZITE = ("GUIcreate", "GUIdelete", "applySkin", "postWidgetCreate", "preWidgetRemove", "onContainerShown",
	"onSourceVisibleChanged", "selChange", "updateAddon", "changed", "connectRelatedElement")


def _pazit(functie, clasa, nume):
	def pazita(self, *argumente, **chei):
		try:
			return functie(self, *argumente, **chei)
		except Exception as e:
			print("[GUIAddon] %s.%s: %s: %s (elementul addon-ului lipseste)" % (clasa, nume, type(e).__name__, e))
			return False if nume == "applySkin" else None
	pazita.__name__ = nume
	pazita.__doc__ = functie.__doc__
	return pazita


class GUIAddon(GUIComponent):

	def __init_subclass__(cls, **chei):
		super().__init_subclass__(**chei)
		for nume in _METODE_PAZITE:
			if nume in cls.__dict__:
				setattr(cls, nume, _pazit(cls.__dict__[nume], cls.__name__, nume))
	def __init__(self):
		GUIComponent.__init__(self)
		self.source = None
		self.sources = {}
		self.relatedScreen = None

	def parseScale(self, value):
		# Replaces "f" with skin factor in non-coordinte fields and evaluates the formula
		try:
			val = int(value)
		except ValueError:
			f = getSkinFactor()  # noqa: F841
			try:
				val = int(eval(value))
			except Exception as err:
				print("[Skin] parseScale: %s '%s': formula '%s' cannot be evaluated!" % (type(err).__name__, err, value))
				val = 0
		return val

	def connectRelatedElement(self, relatedElementName, container):
		relatedElementNames = relatedElementName.split(",")
		if len(relatedElementNames) == 1:
			if relatedElementName == "session":
				self.source = container.session
			else:
				self.source = container[relatedElementName]
				if self.source and hasattr(self.source, "onVisibilityChange"):
					self.source.onVisibilityChange.append(self.onSourceVisibleChanged)
		elif len(relatedElementNames) > 1:
			for x in relatedElementNames:
				if x in container:
					component = container[x]
					self.sources[x] = component
					ignorate = container.__dict__.setdefault("ignoreWidgets", [])
					if isinstance(component, GUIComponent) and x not in ignorate:
						ignorate.append(x)
		container.onShow.append(self.onContainerShown)
		self.relatedScreen = container

	def onContainerShown(self):  # This will be overwritten by subclass
		pass

	def onSourceVisibleChanged(self):  # This will be overwritten by subclass
		pass
