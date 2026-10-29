# Modificat de moneasoftware.com si hdsatelit.com, 2026
from os import listdir, statvfs, makedirs, stat, major, minor, path, access, environ, readlink, symlink, unlink, rmdir, replace, fsync
from Tools.Directories import SCOPE_HDD, resolveFilename
from Tools.CList import CList
from Tools.BoundFunction import boundFunction
from Tools.BlockDevices import isSpecialMmcArea, rootDeviceName
from .SystemInfo import SystemInfo
import re
import subprocess
import time
from Components.Console import Console

def MajorMinor(path):
	rdev = stat(path).st_rdev
	return (major(rdev),minor(rdev))

def readFile(filename):
	file = open(filename, encoding="utf-8", errors="replace")
	data = file.read().strip()
	file.close()
	return data

def runCommand(args, data = None):
	"""exit code of a program started with an argument list, without a shell (HDSatelit: mount points
	and device paths no longer go into os.system strings); 127 like /bin/sh when the program cannot start"""
	try:
		if data is None:
			return subprocess.call(args)
		return subprocess.run(args, input = data).returncode
	except OSError:
		return 127

MOUNTS_FILE = "/proc/mounts"
MEDIA_ROOT = "/media/"
DEVICE_NAME_RX = re.compile(r"^[a-z][a-z0-9]*$")
OCTAL_ESCAPE_RX = re.compile(r"\\([0-7]{3})")

def unescapeMountPath(p):
	# spaces and tabs in paths are written as octal escapes, like \040
	return OCTAL_ESCAPE_RX.sub(lambda m: chr(int(m.group(1), 8)), p)

def readMounts(mounts = None):
	"""(source, mountpoint) pairs of the mounted filesystems; HDS_PROBA_MOUNTS replaces /proc/mounts in tests"""
	name = mounts or environ.get("HDS_PROBA_MOUNTS") or MOUNTS_FILE
	result = []
	try:
		with open(name, encoding="utf-8", errors="surrogateescape") as f:
			for line in f:
				parts = line.split()
				if len(parts) >= 2:
					result.append((parts[0], unescapeMountPath(parts[1])))
	except (IOError, OSError):
		pass
	return result

def findMountpoints(device, mounts = None):
	"""every place where /dev/<device> is mounted now, in /proc/mounts order; the name must match exactly (sda is not
	sda1)"""
	wanted = "/dev/" + device
	return [mountpoint for source, mountpoint in readMounts(mounts)
		if source == wanted or (source.startswith("/dev/") and path.realpath(source) == wanted)]

def findMountpoint(device, mounts = None):
	"""where /dev/<device> is mounted now, or None"""
	found = findMountpoints(device, mounts)
	return found[0] if found else None

# Storage devices get stable names under /media, in this order: /media/hdd is where recordings and timeshift go
# (SCOPE_HDD is /hdd/movie/, /hdd -> media/hdd), the others are for more sticks and cards.
MEDIA_NAMES = ("hdd", "usb", "usb2", "usb3", "usb4", "usb5", "usb6", "usb7", "usb8")
SYSTEM_MOUNT_BASE = "/run/media/"
# The base system mounts USB partitions itself before enigma2 starts: the generic udev-extraconf mount.sh of
# openembedded-core, in /run/media/<LABEL>-<device> (/run is on the internal flash). That mount stays where it is
# (the flash procedure and the boot hook use that path); the stable name is a link in /media, a tmpfs that is empty
# after every start, so a link never outlives the mount and nothing is written to the internal flash.
# A partition nothing has mounted after a short wait is mounted by enigma2 directly on the stable name.
SYS_CLASS_BLOCK = "/sys/class/block/"
UUID_DIR = "/dev/disk/by-uuid/"
# written by udev (write-deviceinfo.rules, device-info.sh) for every partition with a filesystem
FSTYPE_DIR = "/dev/fstype/"
FILESYSTEMS_FILE = "/proc/filesystems"
# UUID of the partition that had /media/hdd last: with several devices present, it gets /media/hdd again after a
# restart. Written only when that partition changes.
HDD_UUID_FILE = "/etc/enigma2/hds-disc-hdd"
NOT_MOUNTED_FS = ("swap", "LVM2_member", "linux_raid_member", "crypto_LUKS", "zfs_member")
# vfat file names in UTF-8 (the kernel default here is iso8859-1: names from the EPG would be unreadable on a PC)
UTF8_FS = ("vfat",)
# udev runs mount.sh before device-info.sh: a known type means mount.sh is done; while it is not known yet (udev
# busy, the receiver loaded), look again every 2 s, up to this many times
FSTYPE_RETRIES = 5
GONE_CHECK_MS = 3000
UUID_RX = re.compile(r"^[0-9A-Za-z-]{1,64}$")

def isUnder(p, base):
	"""p is inside base (base ends with /), not base itself: /media/hdd is under /media/, /media is not"""
	p = (p or "").rstrip("/") + "/"
	return p.startswith(base) and p != base

def isMediaName(p):
	"""/media/hdd, /media/usb, ... (with or without the last /)"""
	p = (p or "").rstrip("/")
	return p.startswith(MEDIA_ROOT) and p[len(MEDIA_ROOT):] in MEDIA_NAMES

def isAliasOf(alias, mountpoint):
	"""alias is a link that leads to mountpoint"""
	if not alias or not mountpoint:
		return False
	alias = alias.rstrip("/")
	try:
		return path.islink(alias) and path.realpath(alias) == path.realpath(mountpoint)
	except (OSError, ValueError):
		return False

def linkAlive(place, mounts = None):
	"""a link in /media still leads somewhere; a link into /run/media or /media must also lead onto a mounted device,
	not onto a folder left behind on the internal flash or in the RAM of /media (udev leaves the empty folder when it
	cannot unmount)"""
	if not path.exists(place):
		return False
	target = path.realpath(place)
	if not (isUnder(target, SYSTEM_MOUNT_BASE) or isUnder(target, MEDIA_ROOT)):
		return True
	if mounts is None:
		mounts = readMounts()
	holder = "/"
	for source, mountpoint in mounts:
		mountpoint = mountpoint.rstrip("/") or "/"
		if (target == mountpoint or target.startswith(mountpoint.rstrip("/") + "/")) and len(mountpoint) > len(holder):
			holder = mountpoint
	return holder not in ("/", MEDIA_ROOT.rstrip("/"))

def deviceUuid(device):
	"""UUID of the filesystem on /dev/<device>, from the udev links in /dev/disk/by-uuid (no blkid process), or None"""
	try:
		names = listdir(UUID_DIR)
	except OSError:
		return None
	for name in names:
		try:
			if path.basename(readlink(UUID_DIR + name)) == device:
				return name
		except OSError:
			pass
	return None

def uuidPresent(uuid):
	return bool(uuid) and path.lexists(UUID_DIR + uuid)

def deviceFsType(device):
	"""filesystem type found by udev on /dev/<device>: the name; "" when udev writes these files but has none for the
	device (no filesystem, or udev not finished yet); None when there is no such information (mount -t auto decides)"""
	try:
		return readFile(FSTYPE_DIR + device)
	except (IOError, OSError):
		return "" if path.isdir(FSTYPE_DIR) else None

def kernelFilesystems():
	"""filesystem types the kernel can mount now (/proc/filesystems, without the nodev ones)"""
	result = set()
	try:
		with open(FILESYSTEMS_FILE) as f:
			for line in f:
				parts = line.split()
				if len(parts) == 1:
					result.add(parts[0])
	except (IOError, OSError):
		pass
	return result

def mountArguments(device, fstype, target):
	"""argument list for mount (program, argv0, arguments): -t <type> only for a type the kernel knows (ntfs goes
	through -t auto to the mount.ntfs-3g helper listed in /etc/filesystems), utf8 only for vfat (other filesystems
	refuse the option)"""
	fsarg = fstype if fstype and fstype in kernelFilesystems() else "auto"
	options = "noatime,utf8" if fstype in UTF8_FS else "noatime"
	return ("mount", "mount", "-t", fsarg, "-o", options, "/dev/" + device, target)

DEVTYPE_UDEV = 0
DEVTYPE_DEVFS = 1

class Harddisk:
	def __init__(self, device):
		self.device = device

		if access("/run/udev", 0) or access("/dev/.udev", 0):
			self.type = DEVTYPE_UDEV
		elif access("/dev/.devfsd", 0):
			self.type = DEVTYPE_DEVFS
		else:
			# fara udev si fara devfs, /dev e static; numele dispozitivelor sunt ca la udev
			self.type = DEVTYPE_UDEV

		self.max_idle_time = 0
		self.idle_running = False
		self.timer = None

		self.dev_path = ''
		self.disk_path = ''
		self.phys_path = path.realpath(self.sysfsPath('device'))

		if self.type == DEVTYPE_UDEV:
			self.dev_path = '/dev/' + self.device
			self.disk_path = self.dev_path

		elif self.type == DEVTYPE_DEVFS:
			tmp = readFile(self.sysfsPath('dev')).split(':')
			s_major = int(tmp[0])
			s_minor = int(tmp[1])
			for disc in listdir("/dev/discs"):
				dev_path = path.realpath('/dev/discs/' + disc)
				disk_path = dev_path + '/disc'
				try:
					rdev = stat(disk_path).st_rdev
				except OSError:
					continue
				if s_major == major(rdev) and s_minor == minor(rdev):
					self.dev_path = dev_path
					self.disk_path = disk_path
					break

		print("new Harddisk", self.device, '->', self.dev_path, '->', self.disk_path)
		self.startIdle()

	def __lt__(self, ob):
		return self.device < ob.device

	def partitionPath(self, n):
		if self.type == DEVTYPE_UDEV:
			return self.dev_path + n
		elif self.type == DEVTYPE_DEVFS:
			return self.dev_path + '/part' + n

	def sysfsPath(self, filename):
		return path.realpath('/sys/block/' + self.device + '/' + filename)

	def stop(self):
		if self.timer:
			self.timer.stop()
			self.timer.callback.remove(self.runIdle)

	def bus(self):
		# CF (7025 specific)
		if self.type == DEVTYPE_UDEV:
			ide_cf = False	# FIXME
		elif self.type == DEVTYPE_DEVFS:
			ide_cf = self.device[:2] == "hd" and "host0" not in self.dev_path

		internal = "pci" in self.phys_path

		if ide_cf:
			ret = "External (CF)"
		elif internal:
			ret = "Internal"
		else:
			ret = "External"
		return ret

	def diskSize(self):
		line = readFile(self.sysfsPath('size'))
		try:
			cap = int(line)
		except:
			return 0;
		return cap // 1000 * 512 // 1000

	def capacity(self):
		cap = self.diskSize()
		if cap == 0:
			return ""
		return "%d.%03d GB" % (cap//1000, cap%1000)

	def model(self):
		if self.device[:2] == "hd":
			return readFile('/proc/ide/' + self.device + '/model')
		elif self.device[:2] == "sd":
			vendor = readFile(self.sysfsPath('device/vendor'))
			model = readFile(self.sysfsPath('device/model'))
			return vendor + '(' + model + ')'
		else:
			assert False, "no hdX or sdX"

	def free(self):
		try:
			mounts = open("/proc/mounts", encoding="utf-8", errors="surrogateescape")
		except IOError:
			return -1

		lines = mounts.readlines()
		mounts.close()

		for line in lines:
			parts = line.strip().split(" ")
			real_path = path.realpath(parts[0])
			if not real_path[-1].isdigit():
				continue
			try:
				if MajorMinor(real_path) == MajorMinor(self.partitionPath(real_path[-1])):
					stat = statvfs(parts[1])
					return stat.f_bfree//1000 * stat.f_bsize//1000
			except OSError:
				pass
		return -1

	def numPartitions(self):
		numPart = -1
		if self.type == DEVTYPE_UDEV:
			try:
				devdir = listdir('/dev')
			except OSError:
				return -1
			for filename in devdir:
				if filename.startswith(self.device):
					numPart += 1

		elif self.type == DEVTYPE_DEVFS:
			try:
				idedir = listdir(self.dev_path)
			except OSError:
				return -1
			for filename in idedir:
				if filename.startswith("disc"):
					numPart += 1
				if filename.startswith("part"):
					numPart += 1
		return numPart

	def unmount(self):
		try:
			mounts = open("/proc/mounts", encoding="utf-8", errors="surrogateescape")
		except IOError:
			return -1

		lines = mounts.readlines()
		mounts.close()

		cmd = ["umount"]

		for line in lines:                                                                          
			parts = line.strip().split(" ")                                                     
			real_path = path.realpath(parts[0])                                                 
			if not real_path[-1].isdigit():                                                     
				continue                                                                    
			try:                                                                                
				if MajorMinor(real_path) == MajorMinor(self.partitionPath(real_path[-1])):
					cmd.append(unescapeMountPath(parts[1]))
					break
			except OSError:
				pass

		return runCommand(cmd)

	def createPartition(self):
		# the partition table goes to sfdisk on its standard input (was printf ... | sfdisk)
		return runCommand(["sfdisk", "-f", "-uS", self.disk_path], data = b"8,\n;0,0\n;0,0\n;0,0\ny\n")

	def mkfs(self):
		cmd = ["mkfs.ext3"]
		if self.diskSize() > 4 * 1024:
			cmd += ["-T", "largefile"]
		cmd += ["-m0", "-O", "dir_index", self.partitionPath("1")]
		return runCommand(cmd)

	def mount(self):
		try:
			fstab = open("/etc/fstab", encoding="utf-8", errors="surrogateescape")
		except IOError:
			return -1

		lines = fstab.readlines()
		fstab.close()

		res = -1
		for line in lines:
			parts = line.strip().split(" ")
			real_path = path.realpath(parts[0])                                                 
			if not real_path[-1].isdigit():                                                     
				continue                                                                    
			try:                                                                                
				if MajorMinor(real_path) == MajorMinor(self.partitionPath(real_path[-1])):
					res = runCommand(["mount", "-t", "ext3", parts[0]])
					break
			except OSError:
				pass

		return res

	def createMovieFolder(self):
		try:
			makedirs(resolveFilename(SCOPE_HDD))
		except OSError:
			return -1
		return 0

	def fsck(self):
		# We autocorrect any failures
		# TODO: we could check if the fs is actually ext3
		return runCommand(["fsck.ext3", "-f", "-p", self.partitionPath("1")])

	def killPartition(self, n):
		part = self.partitionPath(n)

		if access(part, 0):
			res = runCommand(["dd", "bs=512", "count=3", "if=/dev/zero", "of=" + part])
		else:
			res = 0

		return res

	errorList = [ _("Everything is fine"), _("Creating partition failed"), _("Mkfs failed"), _("Mount failed"), _("Create movie folder failed"), _("Fsck failed"), _("Please Reboot"), _("Filesystem contains uncorrectable errors"), _("Unmount failed")]

	def initialize(self):
		self.unmount()

		# Udev tries to mount the partition immediately if there is an
		# old filesystem on it when fdisk reloads the partition table.
		# To prevent that, we overwrite the first 3 sectors of the
		# partition, if the partition existed before. That's enough for
		# ext3 at least.
		self.killPartition("1")

		if self.createPartition() != 0:
			return -1

		if self.mkfs() != 0:
			return -2

		if self.mount() != 0:
			return -3

		if self.createMovieFolder() != 0:
			return -4

		return 0

	def check(self):
		self.unmount()

		res = self.fsck()
		if res & 2 == 2:
			return -6

		if res & 4 == 4:
			return -7

		if res != 0 and res != 1:
			# A sum containing 1 will also include a failure
			return -5

		if self.mount() != 0:
			return -3

		return 0

	def getDeviceDir(self):
		return self.dev_path

	def getDeviceName(self):
		return self.disk_path

	# the HDD idle poll daemon.
	# as some harddrives have a buggy standby timer, we are doing this by hand here.
	# first, we disable the hardware timer. then, we check every now and then if
	# any access has been made to the disc. If there has been no access over a specifed time,
	# we set the hdd into standby.
	def readStats(self):
		try:
			l = open("/sys/block/%s/stat" % self.device).read()
		except IOError:
			return -1,-1
		(nr_read, _, _, _, nr_write) = l.split()[:5]
		return int(nr_read), int(nr_write)

	def startIdle(self):
		self.last_access = time.time()
		self.last_stat = 0
		self.is_sleeping = False
		from enigma import eTimer

		# disable HDD standby timer
		Console().ePopen(("hdparm", "hdparm", "-S0", self.disk_path))
		self.timer = eTimer()
		self.timer.callback.append(self.runIdle)
		self.idle_running = True
		self.setIdleTime(self.max_idle_time) # kick the idle polling loop

	def runIdle(self):
		if not self.max_idle_time:
			return
		t = time.time()

		idle_time = t - self.last_access

		stats = self.readStats()
		print("nr_read", stats[0], "nr_write", stats[1])
		l = sum(stats)
		print("sum", l, "prev_sum", self.last_stat)

		if l != self.last_stat and l >= 0: # access
			print("hdd was accessed since previous check!")
			self.last_stat = l
			self.last_access = t
			idle_time = 0
			self.is_sleeping = False
		else:
			print("hdd IDLE!")

		print("[IDLE]", idle_time, self.max_idle_time, self.is_sleeping)
		if idle_time >= self.max_idle_time and not self.is_sleeping:
			self.setSleep()
			self.is_sleeping = True

	def setSleep(self):
		Console().ePopen(("hdparm", "hdparm", "-y", self.disk_path))

	def setIdleTime(self, idle):
		self.max_idle_time = idle
		if self.idle_running:
			if not idle:
				self.timer.stop()
			else:
				self.timer.start(idle * 100, False)  # poll 10 times per period.

	def isSleeping(self):
		return self.is_sleeping

class Partition:
	def __init__(self, mountpoint, device = None, description = "", force_mounted = False, is_hotplug = None):
		self.mountpoint = mountpoint
		self.description = description
		self.force_mounted = force_mounted
		self.is_hotplug = force_mounted if is_hotplug is None else is_hotplug
		self.device = device

	def stat(self):
		return statvfs(self.mountpoint)

	def free(self):
		try:
			s = self.stat()
			return s.f_bavail * s.f_bsize
		except (OSError, TypeError):
			return None

	def total(self):
		try:
			s = self.stat()
			return s.f_blocks * s.f_bsize
		except (OSError, TypeError):
			return None

	def mounted(self):
		if self.force_mounted:
			return True
		if self.device and self.is_hotplug:
			# hotplug partitions: the mountpoint is whatever /proc/mounts says now, unless the partition is shown under
			# its stable name (/media/hdd, a link to where the system mounted it)
			mountpoint = findMountpoint(self.device)
			if mountpoint is None:
				return False
			if self.mountpoint != mountpoint and not isAliasOf(self.mountpoint, mountpoint):
				self.mountpoint = mountpoint
			return True
		return self.mountpoint in [mountpoint for source, mountpoint in readMounts()]

DEVICEDB_SR = \
	{"dm8000":
		{
			"/devices/pci0000:01/0000:01:00.0/host0/target0:0:0/0:0:0:0": _("DVD Drive"),
			"/devices/pci0000:01/0000:01:00.0/host1/target1:0:0/1:0:0:0": _("DVD Drive"),
			"/devices/platform/brcm-ehci-1.1/usb2/2-1/2-1:1.0/host3/target3:0:0/3:0:0:0": _("DVD Drive"),
		},
	"dm800":
	{
	},
	"dm7025":
	{
	}
	}

DEVICEDB = \
	{"dm8000":
		{
			"/devices/platform/brcm-ehci.0/usb1/1-1/1-1.1/1-1.1:1.0": _("Front USB Slot"),
			"/devices/platform/brcm-ehci.0/usb1/1-1/1-1.2/1-1.2:1.0": _("Back, upper USB Slot"),
			"/devices/platform/brcm-ehci.0/usb1/1-1/1-1.3/1-1.3:1.0": _("Back, lower USB Slot"),
			"/devices/platform/brcm-ehci.0/usb1/1-1/1-1.1/1-1.1:1.0": _("Front USB Slot"),
			"/devices/platform/brcm-ehci-1.1/usb2/2-1/2-1:1.0/": _("Internal USB Slot"),
			"/devices/platform/brcm-ohci-1.1/usb4/4-1/4-1:1.0/": _("Internal USB Slot"),
		},
	"dm800":
	{
		"/devices/platform/brcm-ehci.0/usb1/1-2/1-2:1.0": "Upper USB Slot",
		"/devices/platform/brcm-ehci.0/usb1/1-1/1-1:1.0": "Lower USB Slot",
	},
	"dm7025":
	{
		"/devices/pci0000:00/0000:00:14.1/ide1/1.0": "CF Card Slot", #hdc
		"/devices/pci0000:00/0000:00:14.1/ide0/0.0": "Internal Harddisk"
	}
	}

class HarddiskManager:
	def __init__(self):
		self.hdd = [ ]
		self.cd = ""
		self.partitions = [ ]
		self.devices_scanned_on_init = [ ]
		# hotplug partitions not listed yet (not mounted, or waiting for their stable name): device -> Partition
		self.pending = {}
		# stable name given to a partition mounted elsewhere: device -> /media/<name> (a link)
		self.aliases = {}
		# mount commands running now: device -> target
		self.busy = {}
		# how many times the filesystem type was not known yet: device -> count
		self.fstype_tries = {}
		self.mount_timers = {}
		self.console = None
		self.stale_checked = False
		self.hdd_uuid = self.readHddUuid()

		self.on_partition_list_change = CList()

		# fixed mountpoints first, so a partition mounted on one of them is not listed twice
		p = [
					("/media/hdd", _("Harddisk")),
					("/media/card", _("Card")),
					("/media/cf", _("Compact Flash")),
					("/media/mmc1", _("MMC Card")),
					("/media/net", _("Network Mount")),
					("/media/ram", _("Ram Disk")),
					("/media/usb", _("USB Stick")),
					("/", _("Internal Flash"))
				]

		self.partitions.extend([ Partition(mountpoint = x[0], description = x[1]) for x in p ])

		try:
			cmdline = readFile("/proc/cmdline")
		except IOError:
			cmdline = ""
		self.system_disk = rootDeviceName(cmdline, readMounts())
		self.enumerateBlockDevices()
		# partitions the base system mounted before enigma2 started get their stable names now: before any screen (a
		# timer recording right after a wake-up needs /media/hdd) and before any listener, so a stick present at start
		# does not raise an "add" event (the media scanner would walk it and show a message over the first screen).
		# Links only: no command runs while the modules are still loading.
		for device in sorted(self.pending.keys(), key = self.pendingOrder):
			if device in self.pending:
				self.mountIfNeeded(device, True, True)

	def getPartitionInfo(self, part):
		"""a partition lives under its disk in sysfs (/sys/class/block/sda1 -> .../block/sda/sda1)"""
		diskpath = path.dirname(path.realpath("/sys/class/block/" + part))
		disk = path.basename(diskpath)
		error = False
		removable = False
		try:
			removable = bool(int(readFile(diskpath + "/removable")))
		except (IOError, ValueError):
			error = True
		blacklisted = isSpecialMmcArea(disk) or disk == getattr(self, "system_disk", None)
		medium_found = True
		try:
			open("/dev/" + part).close()
		except IOError as err:
			if err.errno == 159: # no medium present
				medium_found = False
		return error, blacklisted, removable, False, [], medium_found

	def getBlockDevInfo(self, blockdev):
		devpath = "/sys/block/" + blockdev
		if not path.exists(devpath) and path.exists("/sys/class/block/%s/partition" % blockdev):
			return self.getPartitionInfo(blockdev)
		error = False
		removable = False
		blacklisted = False
		is_cdrom = False
		partitions = []
		try:
			removable = bool(int(readFile(devpath + "/removable")))
			dev = int(readFile(devpath + "/dev").split(':')[0])
			if dev in (1, 7, 31, 43): # ram, loop, mtdblock, nbd
				blacklisted = True
			if isSpecialMmcArea(blockdev) or blockdev == getattr(self, "system_disk", None):
				blacklisted = True # eMMC boot areas and the disk holding the system
			if blockdev[0:2] == 'sr':
				is_cdrom = True
			if blockdev[0:2] == 'hd':
				try:
					media = readFile("/proc/ide/%s/media" % blockdev)
					if "cdrom" in media:
						is_cdrom = True
				except IOError:
					error = True
			# check for partitions
			if not is_cdrom:
				for partition in listdir(devpath):
					if partition[0:len(blockdev)] != blockdev:
						continue
					partitions.append(partition)
			else:
				self.cd = blockdev
		except IOError:
			error = True
		# check for medium
		medium_found = True
		try:
			open("/dev/" + blockdev).close()
		except IOError as err:
			if err.errno == 159: # no medium present
				medium_found = False

		return error, blacklisted, removable, is_cdrom, partitions, medium_found

	def enumerateBlockDevices(self):
		print("enumerating block devices...")
		for blockdev in listdir("/sys/block"):
			error, blacklisted, removable, is_cdrom, partitions, medium_found = self.addHotplugPartition(blockdev)
			if not error and not blacklisted:
				if medium_found:
					for part in partitions:
						self.addHotplugPartition(part)
				self.devices_scanned_on_init.append((blockdev, removable, is_cdrom, medium_found))

	def is_hard_mounted(self, device):
		"""mounted on one of the fixed mountpoints (/media/hdd, /media/usb, /, ...), so already listed"""
		mountpoint = findMountpoint(device)
		if mountpoint is None:
			return False
		fixed = [x.mountpoint.rstrip("/") or "/" for x in self.partitions if not x.is_hotplug and x.mountpoint]
		return (mountpoint.rstrip("/") or "/") in fixed

	def knownPartition(self, device):
		return device in self.pending or any(x.device == device for x in self.partitions)

	def addHotplugPartition(self, device, physdev = None):
		if not physdev:
			dev, part = self.splitDeviceName(device)
			try:
				physdev = path.realpath('/sys/block/' + dev + '/device')[4:]
			except OSError:
				physdev = dev
				print("couldn't determine blockdev physdev for device", device)

		error, blacklisted, removable, is_cdrom, partitions, medium_found = self.getBlockDevInfo(device)
		print("found block device '%s':" % device, end=' ')

		if blacklisted:
			print("blacklisted")
		else:
			if error:
				print("error querying properties")
			elif not medium_found:
				print("no medium")
			else:
				print("ok, removable=%s, cdrom=%s, partitions=%s" % (removable, is_cdrom, partitions))

			l = len(device)
			if l:
				# see if this is a harddrive
				if not device[l-1].isdigit() and not removable and not is_cdrom:
					self.hdd.append(Harddisk(device))
					self.hdd.sort()
					SystemInfo["Harddisk"] = len(self.hdd) > 0

				usb = "/usb" in (physdev or "") and not is_cdrom
				if (not removable or medium_found) and not self.knownPartition(device) and (usb or not self.is_hard_mounted(device)):
					# device is the device name, without /dev
					# physdev is the physical device path, which we (might) use to determine the userfriendly name
					description = self.getUserfriendlyDeviceName(device, physdev)
					mountpoints = findMountpoints(device)
					p = Partition(mountpoint = mountpoints[0] if mountpoints else None, description = description, device = device, is_hotplug = True)
					p.physdev = physdev or ""
					p.has_partitions = bool(partitions)
					p.is_cdrom = is_cdrom
					p.usb = usb
					p.removable = removable
					stable = self.stableMountpoint(device, mountpoints) if (usb or device.startswith("sd")) and mountpoints else None
					if mountpoints and (stable or not usb):
						# not USB (fstab, the system), or already on its stable name (enigma2 started again)
						self.announceMounted(device, stable or mountpoints[0], p)
					else:
						# listed after a short wait, on its stable name: a link to where the base system mounted it,
						# or mounted there by enigma2 when nothing else mounted it
						self.pending[device] = p

		return error, blacklisted, removable, is_cdrom, partitions, medium_found

	def run(self, args, callback = None, extra_args = None):
		"""mount/umount as an argument list, without a shell; HDS_PROBA_MOUNT only prints it (probes); False if not run"""
		if isinstance(args, str):
			raise TypeError("an argument list is needed, not a shell line")
		if environ.get("HDS_PROBA_MOUNT"):
			print("[Harddisk] test mode, would run: %s" % " ".join(args[1:]))
			return False
		if self.console is None:
			self.console = Console()
		self.console.ePopen(tuple(args), callback, extra_args or [])
		return True

	def lazyUnmount(self, mountpoint, callback = None, extra_args = None):
		return self.run(("umount", "umount", "-l", mountpoint), callback, extra_args)

	def readHddUuid(self):
		try:
			uuid = readFile(HDD_UUID_FILE)
		except (IOError, OSError):
			return ""
		return uuid if UUID_RX.match(uuid) else ""

	def rememberHdd(self, uuid):
		"""the partition now on /media/hdd; the file changes only when another partition takes /media/hdd"""
		if not uuid or not UUID_RX.match(uuid) or uuid == self.hdd_uuid:
			return
		self.hdd_uuid = uuid
		temp = HDD_UUID_FILE + ".nou"
		try:
			with open(temp, "w") as f:
				f.write(uuid + "\n")
				f.flush()
				fsync(f.fileno())
			replace(temp, HDD_UUID_FILE)
		except (IOError, OSError) as err:
			print("[Harddisk] could not write %s: %s" % (HDD_UUID_FILE, err))

	def hddOwnerWaits(self, uuid):
		"""/media/hdd is kept for the partition that had it before, while that one is present and known here"""
		owner = self.hdd_uuid
		if not owner or uuid == owner or not uuidPresent(owner):
			return False
		try:
			device = path.basename(readlink(UUID_DIR + owner))
		except OSError:
			return False
		return self.knownPartition(device) and device not in self.aliases and MEDIA_ROOT + "hdd" not in [x.mountpoint for x in self.partitions if x.device == device]

	def freeMediaName(self, uuid):
		"""first free stable name: not mounted, not given or being mounted, not a link that still leads somewhere
		(linkAlive), not a folder with files in it (an empty folder or a dead link is replaced)"""
		mounts = readMounts()
		mounted = set((mountpoint.rstrip("/") or "/") for source, mountpoint in mounts)
		reserved = set(self.busy.values()) | set(self.aliases.values())
		for name in MEDIA_NAMES:
			place = MEDIA_ROOT + name
			if place in mounted or place in reserved:
				continue
			if name == "hdd" and self.hddOwnerWaits(uuid):
				continue
			try:
				if path.islink(place):
					if linkAlive(place, mounts):
						continue
					return name
				if path.isdir(place):
					if listdir(place):
						continue
					return name
				if path.lexists(place):
					continue
			except OSError:
				continue
			return name
		return None

	def stableMountpoint(self, device, mountpoints):
		"""the stable name a partition already has: mounted on it, or a link to its mount (after enigma2 restarts)"""
		for mountpoint in mountpoints:
			if isMediaName(mountpoint):
				return mountpoint.rstrip("/")
		for name in MEDIA_NAMES:
			alias = MEDIA_ROOT + name
			if any(isAliasOf(alias, mountpoint) for mountpoint in mountpoints):
				self.aliases[device] = alias
				return alias
		return None

	def makeAlias(self, device, mountpoint):
		"""/media/<name> as a link to where the base system mounted the partition; None if no name is free"""
		name = self.freeMediaName(deviceUuid(device))
		if name is None:
			print("[Harddisk] no free name under %s for %s" % (MEDIA_ROOT, device))
			return None
		alias = MEDIA_ROOT + name
		try:
			if path.islink(alias):
				unlink(alias)
			elif path.isdir(alias):
				rmdir(alias)
			symlink(mountpoint, alias)
		except OSError as err:
			print("[Harddisk] could not make %s for %s: %s" % (alias, device, err))
			return None
		self.aliases[device] = alias
		print("[Harddisk] %s (mounted on %s) is %s" % (device, mountpoint, alias))
		return alias

	def removeEmptyDir(self, place):
		"""a stable name left as an empty folder in /media (not a link, not mounted)"""
		if not isMediaName(place):
			return
		place = place.rstrip("/")
		try:
			if not path.islink(place) and path.isdir(place) and place not in [m.rstrip("/") for s, m in readMounts()]:
				rmdir(place)
		except OSError:
			pass

	def scheduleMount(self, device = None, delay_ms = 2000, mountedOnly = False):
		"""after a short wait: list the partition on its stable name (a link if the system mounted it, else enigma2
		mounts it there); device None = every partition still waiting (devices present at start); mountedOnly = only
		those the system has mounted already"""
		from enigma import eTimer
		key = device or (mountedOnly and "*mounted" or "*")
		old = self.mount_timers.pop(key, None)
		if old is not None:
			old.stop()
		timer = eTimer()
		if device:
			timer.callback.append(boundFunction(self.mountIfNeeded, device))
		else:
			timer.callback.append(boundFunction(self.mountPending, mountedOnly))
		timer.start(delay_ms, True)
		self.mount_timers[key] = timer

	def pendingOrder(self, device):
		# the partition that had /media/hdd first, then fixed disks before sticks, then by name
		p = self.pending[device]
		return (deviceUuid(device) != self.hdd_uuid or not self.hdd_uuid, bool(getattr(p, "removable", True)), device)

	def mountPending(self, mountedOnly = False):
		self.mount_timers.pop(mountedOnly and "*mounted" or "*", None)
		if not self.stale_checked:
			self.stale_checked = True
			self.cleanStale()
		for device in sorted(self.pending.keys(), key = self.pendingOrder):
			if device in self.pending:
				self.mountIfNeeded(device, True, mountedOnly)

	def cleanStale(self):
		"""left from devices pulled out while enigma2 was not running: mounts whose device is gone (only under /media
		and /run/media) and stable names that no longer lead onto a mounted device"""
		for source, mountpoint in readMounts():
			if not source.startswith("/dev/") or not (isUnder(mountpoint, MEDIA_ROOT) or isUnder(mountpoint, SYSTEM_MOUNT_BASE)):
				continue
			name = source[len("/dev/"):]
			if DEVICE_NAME_RX.match(name) and not path.exists(SYS_CLASS_BLOCK + name):
				print("[Harddisk] %s is gone, unmounting %s" % (source, mountpoint))
				self.lazyUnmount(mountpoint, self.unmountFinished, [mountpoint])
		for name in MEDIA_NAMES:
			place = MEDIA_ROOT + name
			try:
				if path.islink(place) and not linkAlive(place):
					unlink(place)
			except OSError:
				pass

	def mountIfNeeded(self, device, quiet = False, mountedOnly = False):
		self.mount_timers.pop(device, None)
		p = self.pending.get(device)
		if p is None or device in self.busy:
			return
		mountpoints = findMountpoints(device)
		if mountpoints:
			stable = None
			if getattr(p, "usb", False) or device.startswith("sd"):
				stable = self.stableMountpoint(device, mountpoints) or self.makeAlias(device, mountpoints[0])
			self.announceMounted(device, stable or mountpoints[0])
			return
		if mountedOnly or p.has_partitions or p.is_cdrom:
			return
		if not getattr(p, "usb", False) and not device.startswith("sd"):
			# internal flash and eMMC partitions are never mounted from here
			if not quiet:
				print("[Harddisk] %s is not a USB or SATA storage device, not mounted" % device)
			return
		if not DEVICE_NAME_RX.match(device):
			print("[Harddisk] unexpected device name %r, not mounted" % device)
			return
		fstype = deviceFsType(device)
		if fstype == "":
			# udev has not written the type yet, or there is no filesystem: look again a few times
			tries = self.fstype_tries.get(device, 0)
			if tries < FSTYPE_RETRIES:
				self.fstype_tries[device] = tries + 1
				self.scheduleMount(device)
			return
		if fstype in NOT_MOUNTED_FS:
			return
		name = self.freeMediaName(deviceUuid(device))
		if name is None:
			print("[Harddisk] no free name under %s for %s" % (MEDIA_ROOT, device))
			return
		target = MEDIA_ROOT + name
		try:
			if path.islink(target):
				unlink(target)
			if not path.isdir(target):
				makedirs(target)
		except OSError as err:
			print("[Harddisk] could not prepare %s: %s" % (target, err))
			return
		print("[Harddisk] mounting %s on %s" % (device, target))
		self.busy[device] = target
		if not self.run(mountArguments(device, fstype, target), self.mountFinished, [device, target]):
			self.busy.pop(device, None)

	def mountFinished(self, data, retval, extra_args):
		device, target = extra_args
		self.busy.pop(device, None)
		mountpoints = findMountpoints(device)
		if device not in self.pending:
			# pulled out while mounting: nothing stays on the stable name
			if target in mountpoints and not path.exists(SYS_CLASS_BLOCK + device):
				self.lazyUnmount(target, self.unmountFinished, [target])
			return
		if target in mountpoints:
			if len(mountpoints) > 1:
				# the base system mounted it at the same moment: one mount only, the system's, with the link
				print("[Harddisk] %s is also mounted on %s, keeping that one" % (device, [m for m in mountpoints if m != target][0]))
				self.busy[device] = target
				if not self.lazyUnmount(target, self.dropFinished, [device, target]):
					self.busy.pop(device, None)
				return
			self.announceMounted(device, target)
		elif mountpoints:
			self.removeEmptyDir(target)
			self.mountIfNeeded(device, True)
		else:
			print("[Harddisk] mounting %s on %s failed (%s): %s" % (device, target, retval, (data or "").strip()))
			self.removeEmptyDir(target)

	def dropFinished(self, data, retval, extra_args):
		device, target = extra_args
		self.busy.pop(device, None)
		self.removeEmptyDir(target)
		if device in self.pending:
			self.mountIfNeeded(device, True)

	def unmountFinished(self, data, retval, extra_args):
		self.removeEmptyDir(extra_args[0])

	def announceMounted(self, device, mountpoint, p = None):
		if p is None:
			p = self.pending.pop(device)
		else:
			self.pending.pop(device, None)
		p.mountpoint = mountpoint
		self.partitions.append(p)
		self.fstype_tries.pop(device, None)
		print("[Harddisk] %s is mounted on %s" % (device, mountpoint))
		if mountpoint.rstrip("/") == MEDIA_ROOT + "hdd":
			self.rememberHdd(deviceUuid(device))
		self.on_partition_list_change("add", p)

	def goneCheck(self, device):
		"""after a removal: the system's own unmount fails while files are still open; the device is gone, so any mount
		of it left under /media or /run/media is unmounted lazily"""
		self.mount_timers.pop("gone:" + device, None)
		if path.exists(SYS_CLASS_BLOCK + device):
			return
		for mountpoint in findMountpoints(device):
			if isUnder(mountpoint, MEDIA_ROOT) or isUnder(mountpoint, SYSTEM_MOUNT_BASE):
				print("[Harddisk] %s is gone, unmounting %s" % (device, mountpoint))
				self.lazyUnmount(mountpoint, self.unmountFinished, [mountpoint])

	def removeHotplugPartition(self, device):
		timer = self.mount_timers.pop(device, None)
		if timer is not None:
			timer.stop()
		self.pending.pop(device, None)
		self.busy.pop(device, None)
		self.fstype_tries.pop(device, None)
		for x in self.partitions[:]:
			if x.is_hotplug and x.device == device:
				self.partitions.remove(x)
				self.on_partition_list_change("remove", x)
		alias = self.aliases.pop(device, None)
		if alias:
			try:
				if path.islink(alias):
					unlink(alias)
			except OSError as err:
				print("[Harddisk] could not remove %s: %s" % (alias, err))
		mountpoints = findMountpoints(device)
		for mountpoint in mountpoints:
			if isUnder(mountpoint, MEDIA_ROOT):
				# mounted by enigma2 on its stable name; the device is gone, a lazy unmount frees the place
				self.lazyUnmount(mountpoint, self.unmountFinished, [mountpoint])
		if [m for m in mountpoints if not isUnder(m, MEDIA_ROOT)]:
			# the system unmounts its own mounts (udev mount.sh); look again once it is done
			from enigma import eTimer
			timer = eTimer()
			timer.callback.append(boundFunction(self.goneCheck, device))
			timer.start(GONE_CHECK_MS, True)
			self.mount_timers["gone:" + device] = timer
		l = len(device)
		if l and not device[l-1].isdigit():
			for hdd in self.hdd:
				if hdd.device == device:
					hdd.stop()
					self.hdd.remove(hdd)
					break
			SystemInfo["Harddisk"] = len(self.hdd) > 0

	def HDDCount(self):
		return len(self.hdd)

	def HDDList(self):
		list = [ ]
		for hd in self.hdd:
			hdd = hd.model() + " - " + hd.bus()
			cap = hd.capacity()
			if cap != "":
				hdd += " (" + cap + ")"
			list.append((hdd, hd))
		return list

	def getCD(self):
		return self.cd

	def getAutofsMountpoint(self, device):
		"""where the device is mounted (the media player asks this for the CD drive)"""
		return findMountpoint(device) or MEDIA_ROOT + device

	def getMountedPartitions(self, onlyhotplug = False):
		parts = [x for x in self.partitions if (x.is_hotplug or not onlyhotplug) and x.mounted()]
		# a device on a fixed place (/media/hdd, /media/usb) is listed once, with its own name
		taken = set(x.mountpoint.rstrip("/") for x in parts if x.is_hotplug and x.mountpoint)
		parts = [x for x in parts if x.is_hotplug or not x.mountpoint or (x.mountpoint.rstrip("/") or "/") not in taken]
		devs = set([x.device for x in parts])
		for devname in devs.copy():
			if not devname:
				continue
			dev, part = self.splitDeviceName(devname)
			if part and dev in devs: # if this is a partition and we still have the wholedisk, remove wholedisk
				devs.remove(dev)

		# return all devices which are not removed due to being a wholedisk when a partition exists
		return [x for x in parts if not x.device or x.device in devs]

	def splitDeviceName(self, devname):
		# this works for: sdaX, hdaX, sr0 (which is in fact dev="sr0", part=""). It doesn't work for other names like mtdblock3, but they are blacklisted anyway.
		dev = devname[:3]
		part = devname[3:]
		for p in part:
			if not p.isdigit():
				return devname, 0
		return dev, part and int(part) or 0

	def getUserfriendlyDeviceName(self, dev, phys):
		dev, part = self.splitDeviceName(dev)
		description = "External Storage %s" % dev
		have_model_descr = False
		try:
			description = readFile("/sys" + phys + "/model")
			have_model_descr = True
		except IOError as s:
			print("couldn't read model: ", s)
		from Tools.HardwareInfo import HardwareInfo
		if dev.find('sr') == 0 and dev[2].isdigit():
			devicedb = DEVICEDB_SR
		else:
			devicedb = DEVICEDB
		for physdevprefix, pdescription in list(devicedb.get(HardwareInfo().device_name,{}).items()):
			if phys.startswith(physdevprefix):
				if have_model_descr:
					description = pdescription + ' - ' + description
				else:
					description = pdescription
		# not wholedisk and not partition 1
		if part and part != 1:
			description += " (Partition %d)" % part
		return description

	def addMountedPartition(self, device, desc):
		already_mounted = False
		for x in self.partitions[:]:
			if x.mountpoint == device:
				already_mounted = True
		if not already_mounted:
			self.partitions.append(Partition(mountpoint = device, description = desc))

	def removeMountedPartition(self, mountpoint):
		for x in self.partitions[:]:
			if x.mountpoint == mountpoint:
				self.partitions.remove(x)
				self.on_partition_list_change("remove", x)

harddiskmanager = HarddiskManager()
