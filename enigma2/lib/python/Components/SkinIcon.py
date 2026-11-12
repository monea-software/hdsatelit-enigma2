# Modificat de moneasoftware.com si hdsatelit.com, 2026
"""Pictogramele listelor desenate in Python, ca in OE-Alliance (aceeasi cale de import, Components.SkinIcon).

O tema care cere pictogramele din fontul ei (sau din enigma2icons al imaginii) scrie in <parameters>:
  <parameter name="FileListNativeIcons" value="1"/>                (ChoiceList: ChoiceListNative, tastatura: VirtualKeyboardNative)
  <parameter name="FileListIcon_movie" value="59765,accent,accent"/> (cod, culoare, culoare pe randul ales; culorile optionale)
si <alias name="FileListIcons" font="enigma2icons" size="31"/> pentru font. Fara acesti parametri (temele noastre si cele vechi)
listele deseneaza pozele de pana acum, neschimbate.
"""
from enigma import RT_HALIGN_CENTER, RT_VALIGN_CENTER

from Components.MultiContent import MultiContentEntryText
from Tools.Directories import SCOPE_CURRENT_SKIN, resolveFilename, fileExists

try:
	from enigma import RT_BLEND
except ImportError:
	RT_BLEND = 0


def _parametri():
	try:
		from skin import parameters
		return parameters
	except ImportError:
		return {}


def nativ(cheie):
	"""True cand tema cere desenul din font: `cheie` = ChoiceListNative, FileListNativeIcons, MovieListNativeIcons,
	VirtualKeyboardNative"""
	valoare = _parametri().get(cheie, 0)
	return isinstance(valoare, int) and valoare != 0


def culoare(valoare):
	"""o culoare din parametri: un numar (#.. sau 0x..) ramane; un nume se cauta in culorile temei; altfel None (culoarea
	listei). Alfa FF ar fi citit de lista drept „culoarea sablonului”, deci se scoate (ca _skinColor din FileList)."""
	if valoare is None:
		return None
	if isinstance(valoare, str):
		try:
			import skin
			c = skin.colorNames.get(valoare)
			valoare = c.argb() if c is not None else None
		except Exception:
			valoare = None
		if valoare is None:
			return None
	if not isinstance(valoare, int):
		return None
	return valoare & 0xFFFFFF if (valoare >> 24) & 0xFF == 0xFF else valoare


def codBun(cod):
	return isinstance(cod, int) and 0 < cod <= 0x10FFFF and not 0xD800 <= cod <= 0xDFFF


class SkinIcon:
	"""O pictograma de lista dintr-un font; temele care nu o cer primesc mai departe pozele."""

	def __init__(self, codepoint, color=None, selectedColor=None):
		self.text = chr(codepoint)
		self.color = culoare(color)
		self.selectedColor = culoare(selectedColor) if selectedColor is not None else self.color

	def entry(self, pos, size, font):
		return MultiContentEntryText(pos=pos, size=size, font=font, flags=RT_HALIGN_CENTER | RT_VALIGN_CENTER | RT_BLEND,
			text=self.text, color=self.color, color_sel=self.selectedColor)


def pictograma(componenta, nume, cheieNativ=None):
	"""SkinIcon pentru <componenta>Icon_<nume> cand tema cere desenul din font (<componenta>NativeIcons, sau `cheieNativ`);
	altfel None"""
	if not nativ(cheieNativ or componenta + "NativeIcons"):
		return None
	valoare = _parametri().get("%sIcon_%s" % (componenta, nume))
	valori = valoare if isinstance(valoare, (tuple, list)) else (valoare,)
	if 1 <= len(valori) <= 3 and codBun(valori[0]):
		return SkinIcon(*valori)
	return None


def loadSkinIcon(component, name, filename):
	"""ca in OE-Alliance: SkinIcon cand tema il cere, altfel poza `filename` (cale fata de dosarul temei, ca
	"icons/folder.png"; la noi si sub skin_default/); None cand nu e nici poza"""
	icon = pictograma(component, name)
	if icon is not None:
		return icon
	for cale in (filename, "skin_default/" + filename):
		fisier = resolveFilename(SCOPE_CURRENT_SKIN, cale)
		if fileExists(fisier):
			try:
				from Tools.LoadPixmap import LoadPixmap
				return LoadPixmap(fisier, cached=True)
			except Exception:
				return None
	return None


def fontPictograme(alias, marime, maxim=None):
	"""gFont pentru pictograme: <alias name=`alias`> al temei (fontul si marimea), altfel enigma2icons la `marime`; cel mult
	`maxim` (cutia in care se deseneaza). Marimea literei aleasa de om (FontSetup) se aplica la fel ca la textul listei."""
	from skin import getListFont
	try:
		from skin import fonts
		a = fonts.get(alias)
		familie, m = (a[0] or "enigma2icons", int(a[1]) or marime) if a else ("enigma2icons", marime)
	except Exception:
		familie, m = "enigma2icons", marime
	if maxim:
		m = min(m, maxim)
	return getListFont("", (familie, max(1, int(m))))[0]
