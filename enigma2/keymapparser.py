# Modificat de moneasoftware.com si hdsatelit.com, 2026
import enigma
import xml.etree.ElementTree

from keyids import KEYIDS

# these are only informational (for help)...
from Tools.KeyBindings import addKeyBinding

class KeymapError(Exception):
    def __init__(self, message):
        self.msg = message

    def __str__(self):
        return self.msg

# Steagurile tastelor: m apasare, b eliberare, r repetare, l lunga; s (32) = sfarsitul apasarii lungi, scris de keymap-urile
# pluginurilor din alte imagini (aici se primeste; legarea cu el nu se potriveste la nicio tasta a noastra).
STEAGURI = {'m': 1, 'b': 2, 'r': 4, 'l': 8, 's': 32}


def parseKeys(context, filename, actionmap, device, keys, help=True):
	# help=False: numai legatura in eActionMap, fara randul din ajutor (DEVICE_ALIASES: aceleasi taste, alt dispozitiv)
	# HDSatelit: un rand pe care nu-l intelegem (tasta necunoscuta, steag necunoscut, fara mapto) se sare cu un mesaj in
	# jurnal, nu opreste citirea intregului fisier: keymap.xml-ul propriu al unui plugin scris pentru alte imagini (cu
	# taste sau steaguri pe care noi nu le avem) cadea altfel la incarcare. mapTo e aceeasi cu mapto.
	for x in keys.findall("key"):
		get_attr = x.attrib.get
		mapto = get_attr("mapto") or get_attr("mapTo")
		id = get_attr("id")
		flags = get_attr("flags") or ""

		if not mapto or not id:
			print("[keymapparser] %s: randul din %s fara mapto sau id (%r, %r), sarit" % (filename, context, id, mapto))
			continue
		necunoscute = [f for f in flags if f not in STEAGURI]
		if necunoscute or not flags:
			print("[keymapparser] %s: steag necunoscut sau lipsa %r la %s/%s, sarit" % (filename, flags, context, id))
			continue
		flags = sum(STEAGURI[f] for f in flags)

		try:
			if len(id) == 1:
				keyid = ord(id) | 0x8000
			elif id[0] == '\\':
				if id[1] == 'x':
					keyid = int(id[2:], 0x10) | 0x8000
				elif id[1] == 'd':
					keyid = int(id[2:]) | 0x8000
				else:
					raise KeymapError("key id '" + str(id) + "' is neither hex nor dec")
			else:
				try:
					keyid = KEYIDS[id]
				except KeyError:
					raise KeymapError("key id '" + str(id) + "' is illegal")
		except (KeymapError, ValueError) as e:
			print("[keymapparser] %s: %s (%s/%s), sarit" % (filename, e, context, mapto))
			continue
		actionmap.bindKey(filename, device, keyid, flags, context, mapto)
		if help:
			addKeyBinding(filename, keyid, context, mapto, flags)

# Telecomenzile Vu+ Duo 4K Lite: driverul placii numeste telecomanda in infrarosu "vuplus remote control", iar cea
# Bluetooth "VUPLUS-BLE-RCU"; amandoua primesc tastele telecomenzii Vu+ obisnuite ("dreambox advanced remote control
# (native)"). Pe celelalte receptoare nu exista dispozitive cu aceste nume, deci legaturile in plus nu se folosesc.
DEVICE_ALIASES = {
	"dreambox advanced remote control (native)": ("vuplus remote control", "VUPLUS-BLE-RCU"),
}


def readKeymap(filename):
	p = enigma.eActionMap.getInstance()
	assert p

	source = open(filename, 'rb')

	try:
		dom = xml.etree.ElementTree.parse(source)
	except:
		raise KeymapError("keymap %s not well-formed." % filename)

	keymap = dom.getroot()

	for cmap in keymap.findall("map"):
		context = cmap.attrib.get("context")
		assert context, "map must have context"

		for device in cmap.findall("device"):
			name = device.attrib.get("name")
			parseKeys(context, filename, p, name, device)
			for alias in DEVICE_ALIASES.get(name, ()):
				parseKeys(context, filename, p, alias, device, help=False)

		parseKeys(context, filename, p, "generic", cmap)

def removeKeymap(filename):
	p = enigma.eActionMap.getInstance()
	p.unbindKeyDomain(filename)
