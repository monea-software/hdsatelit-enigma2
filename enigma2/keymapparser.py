# Modificat de moneasoftware.com si hdsatelit.com, 2026
import enigma
import xml.etree.ElementTree
import os
import stat
import tempfile

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


def _readKeymap(filename, main=False):
	try:
		with open(filename, 'rb') as source:
			data = source.read()
		dom = xml.etree.ElementTree.ElementTree(xml.etree.ElementTree.fromstring(data))
	except (OSError, xml.etree.ElementTree.ParseError, LookupError, ValueError) as error:
		raise KeymapError("keymap %s: %s" % (filename, error)) from error
	root = dom.getroot()
	if main and (root.tag != "keymap" or not any(c.findall("key") or c.findall("device/key") for c in root.findall("map"))):
		raise KeymapError("keymap %s: missing keymap/maps" % filename)
	# Validate all contexts before adding any bindings.
	for cmap in root.findall("map"):
		if not cmap.get("context") or any(not d.get("name") for d in cmap.findall("device")):
			raise KeymapError("keymap %s: missing context/device name" % filename)
	dom.hds_source = data
	return dom


def _bindKeymap(dom, filename):
	p = enigma.eActionMap.getInstance()
	assert p
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


def readKeymap(filename):
	_bindKeymap(_readKeymap(filename), filename)


_recovery = ""


def recoveryMessage(translate):
	_ = translate
	if _recovery == "factory":
		return _("Harta de taste nu a putut fi citită. Am încărcat tastele din pachet. Receptorul poate fi folosit în continuare.")
	if _recovery == "emergency":
		return _("Hărțile de taste nu pot fi citite. Am pornit cu tastele de bază. Meniul și interfața web sunt disponibile.")
	return ""


def _stamp(filename):
	s = os.lstat(filename)
	if not stat.S_ISREG(s.st_mode):
		raise OSError("keymap is not a regular file")
	return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)


def _atomicKeymap(filename, data, expected):
	# Never truncate the old map. Keep its bytes before replacing it.
	directory = os.path.dirname(filename)
	fd, temporary = tempfile.mkstemp(prefix=".keymap-", suffix=".nou", dir=directory)
	backup = None
	installed = False
	try:
		with os.fdopen(fd, "wb") as target:
			target.write(data)
			target.flush()
			os.fsync(target.fileno())
		os.chmod(temporary, 0o644)
		try:
			current = _stamp(filename)
		except FileNotFoundError:
			current = None
		if current != expected:
			raise OSError("keymap changed during recovery")
		if current is not None:
			backupfd, backup = tempfile.mkstemp(prefix=os.path.basename(filename) + ".stricat-", dir=directory)
			with os.fdopen(backupfd, "wb") as target, open(filename, "rb") as source:
				while True:
					block = source.read(65536)
					if not block:
						break
					target.write(block)
				target.flush()
				os.fsync(target.fileno())
			if _stamp(filename) != expected:
				raise OSError("keymap changed during backup")
		os.replace(temporary, filename)
		installed = True
		try:
			d = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
			try:
				os.fsync(d)
			finally:
				os.close(d)
		except OSError:
			pass
	finally:
		if os.path.exists(temporary):
			os.unlink(temporary)
		if backup is not None and not installed:
			os.unlink(backup)


def _emergencyKeymap():
	# Independent basic controls if even the packaged reserve is unavailable.
	root = xml.etree.ElementTree.Element("keymap")
	groups = {
		"ListboxActions": (("UP", "moveUp"), ("DOWN", "moveDown"), ("LEFT", "pageUp"), ("RIGHT", "pageDown")),
		"DirectionActions": (("UP", "up"), ("DOWN", "down"), ("LEFT", "left"), ("RIGHT", "right")),
		"OkCancelActions": (("OK", "ok"), ("ENTER", "ok"), ("EXIT", "cancel"), ("ESC", "cancel")),
		"SetupActions": (("OK", "ok"), ("EXIT", "cancel"), ("LEFT", "left"), ("RIGHT", "right"), ("RED", "cancel"), ("GREEN", "save")),
		"InfobarMenuActions": (("MENU", "mainMenu"),),
		"MenuActions": (("MENU", "menu"),),
		"GlobalActions": (("VOLUMEUP", "volumeUp"), ("VOLUMEDOWN", "volumeDown"), ("MUTE", "volumeMute")),
	}
	for context, keys in groups.items():
		cmap = xml.etree.ElementTree.SubElement(root, "map", context=context)
		for key, action in keys:
			xml.etree.ElementTree.SubElement(cmap, "key", id="KEY_" + key, mapto=action, flags="m")
	for action, flags in (("power_down", "m"), ("power_up", "b"), ("power_long", "l")):
		xml.etree.ElementTree.SubElement(cmap, "key", id="KEY_POWER", mapto=action, flags=flags)
	return xml.etree.ElementTree.ElementTree(root)


def readMainKeymap(filename, default=None, reserve=None):
	global _recovery
	_recovery = ""
	if default is None:
		default = enigma.eEnv.resolve("${datadir}/enigma2/keymap.xml")
	if reserve is None:
		reserve = os.path.join(os.path.dirname(default), "keymap-original", "keymap.xml")
	try:
		expected = _stamp(default)
	except OSError:
		expected = None
	try:
		dom = _readKeymap(filename, main=True)
	except KeymapError as error:
		print("[keymapparser] %s" % error)
		_recovery = "factory"
		dom = None
		for fallback in ([default] if filename != default else []) + [reserve]:
			try:
				dom = _readKeymap(fallback, main=True)
				break
			except KeymapError as fallbackError:
				print("[keymapparser] %s" % fallbackError)
		if dom is None:
			dom = _emergencyKeymap()
			_recovery = "emergency"
		elif filename == default:
			try:
				_atomicKeymap(default, dom.hds_source, expected)
			except OSError as restoreError:
				print("[keymapparser] restore: %s" % restoreError)
	_bindKeymap(dom, filename)
	return _recovery

def removeKeymap(filename):
	p = enigma.eActionMap.getInstance()
	p.unbindKeyDomain(filename)
