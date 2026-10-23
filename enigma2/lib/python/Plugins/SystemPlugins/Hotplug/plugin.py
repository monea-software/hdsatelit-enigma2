# Modificat de moneasoftware.com si hdsatelit.com, 2026
# Hotplug for HDSatelit Image: follows kernel device events and keeps the partition list of
# harddiskmanager in step when USB sticks, disks and card readers are added or removed.
# Other plugins keep using hotplugNotifier from this module:
# every entry is called as fnc(device, media_state) with "1" = added and "0" = removed.
import socket
from traceback import print_exc

from enigma import eTimer
from Components.Harddisk import harddiskmanager
from Plugins.Plugin import PluginDescriptor

NETLINK_KOBJECT_UEVENT = 15
KERNEL_EVENTS_GROUP = 1
POLL_INTERVAL_MS = 1000
# the base system (udev mount.sh) mounts first, enigma2 gives the stable name (/media/hdd, /media/usb) after this
# wait, and mounts the partition itself on that name only when nothing mounted it
MOUNT_WAIT_MS = 2000
# at start: the partitions the system mounted before enigma2 got their names when Components.Harddisk was loaded;
# this first pass names those mounted since then, the others are mounted by enigma2 after the longer wait
BOOT_NAMES_WAIT_MS = 300
BOOT_MOUNT_WAIT_MS = 10000
IGNORED_PREFIXES = ("loop", "ram", "mtdblock", "zram", "dm-", "nbd")

hotplugNotifier = []


def notifyListeners(device, media_state):
	# one listener that fails must not stop the others
	for fnc in hotplugNotifier[:]:
		try:
			fnc(device, media_state)
		except Exception:
			print("[Hotplug] listener failed for %s:" % device)
			print_exc()


def parseUevent(data):
	"""kernel uevent: "ACTION@DEVPATH" then "KEY=VALUE" fields separated by zero bytes"""
	fields = data.split(b"\0")
	if not fields or b"@" not in fields[0]:
		return None
	event = {}
	for field in fields[1:]:
		key, sep, value = field.partition(b"=")
		if sep:
			event[key.decode("utf-8", "replace")] = value.decode("utf-8", "replace")
	return event


def handleEvent(event):
	if event.get("SUBSYSTEM") != "block":
		return
	device = event.get("DEVNAME", "")
	if device.startswith("/dev/"):
		device = device[5:]
	if not device or device.startswith(IGNORED_PREFIXES):
		return
	action = event.get("ACTION")
	if action == "add":
		print("[Hotplug] added %s" % device)
		harddiskmanager.addHotplugPartition(device, event.get("DEVPATH"))
		harddiskmanager.scheduleMount(device, MOUNT_WAIT_MS)
		notifyListeners(device, "1")
	elif action == "remove":
		print("[Hotplug] removed %s" % device)
		harddiskmanager.removeHotplugPartition(device)
		notifyListeners(device, "0")
	elif action == "change" and event.get("DISK_MEDIA_CHANGE") == "1":
		# card readers and optical drives: the medium changed, the device stays
		print("[Hotplug] medium changed on %s" % device)
		harddiskmanager.removeHotplugPartition(device)
		harddiskmanager.addHotplugPartition(device, event.get("DEVPATH"))
		harddiskmanager.scheduleMount(device, MOUNT_WAIT_MS)
		notifyListeners(device, "1")


def injectEvent(event):
	"""for tests and tools: handle an event given as a dict, as if it came from the kernel"""
	try:
		handleEvent(event)
	except Exception:
		print("[Hotplug] event failed: %s" % event)
		print_exc()


class UeventListener:
	def __init__(self):
		self.sock = None
		self.timer = None

	def start(self):
		if self.sock is not None:
			return True
		try:
			sock = socket.socket(socket.AF_NETLINK, socket.SOCK_DGRAM, NETLINK_KOBJECT_UEVENT)
			sock.bind((0, KERNEL_EVENTS_GROUP))
			sock.setblocking(False)
		except (OSError, AttributeError) as err:
			# containers without rights, other kernels: the devices found at start stay known
			print("[Hotplug] kernel device events not available (%s)" % err)
			return False
		# eSocketNotifier is not available to Python here: a timer reads the non-blocking socket
		# once a second (one system call; a second of delay does not matter when a stick is plugged in)
		timer = eTimer()
		timer.callback.append(self.dataAvailable)
		timer.start(POLL_INTERVAL_MS, False)
		self.timer = timer
		self.sock = sock
		print("[Hotplug] listening for kernel device events")
		return True

	def stop(self):
		if self.timer is not None:
			self.timer.stop()
			self.timer = None
		if self.sock is not None:
			self.sock.close()
			self.sock = None

	def dataAvailable(self):
		while self.sock is not None:
			try:
				data = self.sock.recv(16384)
			except BlockingIOError:
				return
			except OSError as err:
				print("[Hotplug] reading kernel events failed (%s)" % err)
				return
			if not data:
				return
			event = parseUevent(data)
			if event:
				injectEvent(event)


listener = UeventListener()


def autostart(reason, **kwargs):
	if reason == 0:
		listener.start()
		# devices already present at start
		harddiskmanager.scheduleMount(None, BOOT_NAMES_WAIT_MS, mountedOnly = True)
		harddiskmanager.scheduleMount(None, BOOT_MOUNT_WAIT_MS)
	else:
		listener.stop()


def Plugins(**kwargs):
	return [PluginDescriptor(name="Hotplug", description=_("Follows added and removed storage devices"), where=PluginDescriptor.WHERE_AUTOSTART, needsRestart=True, fnc=autostart)]
