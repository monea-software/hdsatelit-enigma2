# coding: utf-8
# Modificat de moneasoftware.com si hdsatelit.com, 2026
from .config import config, configfile, ConfigSlider, ConfigSubsection, ConfigYesNo, ConfigText

import struct, sys, time, errno
from fcntl import ioctl
from os import path as os_path, listdir, open as os_open, close as os_close, write as os_write, read as os_read, O_RDWR, O_NONBLOCK

# ioctl number layout: MIPS and PowerPC (the old Dreambox receivers) use 13 size bits and 3 direction bits,
# ARM, AArch64 and x86 use the generic 14 and 2 (asm-generic/ioctl.h)
from os import uname
IOC_NRBITS = 8
IOC_TYPEBITS = 8
if uname().machine.lower().startswith(("mips", "ppc", "powerpc")):
	IOC_SIZEBITS = 13
	IOC_DIRBITS = 3
else:
	IOC_SIZEBITS = 14
	IOC_DIRBITS = 2

IOC_NRSHIFT = 0
IOC_TYPESHIFT = IOC_NRSHIFT+IOC_NRBITS
IOC_SIZESHIFT = IOC_TYPESHIFT+IOC_TYPEBITS
IOC_DIRSHIFT = IOC_SIZESHIFT+IOC_SIZEBITS

IOC_READ = 2

def EVIOCGNAME(length):
	return (IOC_READ<<IOC_DIRSHIFT)|(length<<IOC_SIZESHIFT)|(0x45<<IOC_TYPESHIFT)|(0x06<<IOC_NRSHIFT)

def EVIOCGBIT(ev, length):
	return (IOC_READ<<IOC_DIRSHIFT)|(length<<IOC_SIZESHIFT)|(0x45<<IOC_TYPESHIFT)|((0x20 + ev)<<IOC_NRSHIFT)

EV_KEY, EV_REL = 1, 2
KEY_SPACE, KEY_A, KEY_Z, BTN_LEFT, REL_X, REL_Y = 57, 30, 44, 0x110, 0, 1

def felDupaTaste(fd):
	""""mouse" (REL_X, REL_Y si BTN_LEFT), "keyboard" (A, Z si Spatiu) sau None, dupa ce trimite dispozitivul,
	ca in lib/driver/rcinput.cpp (o tastatura cu touchpad e tastatura)."""
	def biti(ev):
		try:
			return ioctl(fd, EVIOCGBIT(ev, 96), bytes(96))
		except (IOError, OSError):
			return b""
	def are(b, cod):
		return len(b) > cod // 8 and (b[cod // 8] >> (cod % 8)) & 1
	taste, rel = biti(EV_KEY), biti(EV_REL)
	if are(taste, KEY_A) and are(taste, KEY_Z) and are(taste, KEY_SPACE):
		return "keyboard"
	if are(rel, REL_X) and are(rel, REL_Y) and are(taste, BTN_LEFT):
		return "mouse"
	return None


class inputDevices:

	def __init__(self):
		self.Devices = {}
		self.currentDevice = ""
		self.getInputDevices()
	
	def getInputDevices(self):
		# fara /dev/input (PC, container, receptor fara dispozitive) lista ramane goala
		try:
			devices = listdir("/dev/input/")
		except OSError:
			devices = []

		for evdev in devices:
			if not evdev.startswith("event"): # mice and other non evdev nodes have no name
				continue
			try:
				buffer = bytes(512)
				self.fd = os_open("/dev/input/" + evdev, O_RDWR | O_NONBLOCK)
				name = ioctl(self.fd, EVIOCGNAME(256), buffer)
				end = name.find(b"\0")
				self.name = (name if end < 0 else name[:end]).decode("utf-8", "replace")
				fel = felDupaTaste(self.fd)
				os_close(self.fd)
			except (IOError,OSError) as err:
				print('[iInputDevices] getInputDevices  <ERROR: ioctl(EVIOCGNAME): ' + str(err) + ' >')
				self.name = None
				fel = None
			
			if self.name:
				if self.name == 'dreambox front panel':
					continue
				if self.name == "dreambox advanced remote control (native)" and config.misc.rcused.value != 0:
					continue
				if self.name == "dreambox remote control (native)" and config.misc.rcused.value == 0:
					continue
				self.Devices[evdev] = {'name': self.name, 'type': self.getInputDeviceType(self.name, fel),'enabled': False, 'configuredName': None }
	

	def getInputDeviceType(self,name, fel=None):
		# intai numele, apoi ce trimite dispozitivul (felDupaTaste): "USB Receiver", "Optical Mouse" ...
		if name.find("remote control") != -1:
			return "remote"
		elif name.find("keyboard") != -1:
			return "keyboard"
		elif name.find("mouse") != -1:
			return "mouse"
		elif fel in ("keyboard", "mouse"):
			return fel
		else:
			print("Unknown device type:",name)
			return None
			
	def getDeviceName(self, x):
		if x in list(self.Devices.keys()):
			return self.Devices[x].get("name", x)
		else:
			return "Unknown device name"

	def getDeviceList(self):
		return sorted(self.Devices.keys())

	def getDefaultRCdeviceName(self):
		if config.misc.rcused.value == 0:
			for device in self.Devices.keys():
				if self.Devices[device]["name"] == "dreambox advanced remote control (native)":
					return device
		else:
			for device in self.Devices.keys():
				if self.Devices[device]["name"] == "dreambox remote control (native)":
					return device

	def setDeviceAttribute(self, device, attribute, value):
		#print "[iInputDevices] setting for device", device, "attribute", attribute, " to value", value
		if device in self.Devices:
			self.Devices[device][attribute] = value
			
	def getDeviceAttribute(self, device, attribute):
		if device in self.Devices:
			if attribute in self.Devices[device]:
				return self.Devices[device][attribute]
		return None
			
	def setEnabled(self, device, value):
		oldval = self.getDeviceAttribute(device, 'enabled')
		#print "[iInputDevices] setEnabled for device %s to %s from %s" % (device,value,oldval)
		self.setDeviceAttribute(device, 'enabled', value)
		if oldval is True and value is False:
			self.setDefaults(device)

	def setName(self, device, value):
		#print "[iInputDevices] setName for device %s to %s" % (device,value)
		self.setDeviceAttribute(device, 'configuredName', value)
		
	#struct input_event {
	#	struct timeval time;    -> ignored
	#	__u16 type;             -> EV_REP (0x14)
	#	__u16 code;             -> REP_DELAY (0x00) or REP_PERIOD (0x01)
	#	__s32 value;            -> DEFAULTS: 700(REP_DELAY) or 100(REP_PERIOD)
	#}; -> size = 16

	def setDefaults(self, device):
		print("[iInputDevices] setDefaults for device %s" % (device))
		self.setDeviceAttribute(device, 'configuredName', None)
		event_repeat = struct.pack('iihhi', 0, 0, 0x14, 0x01, 100)
		event_delay = struct.pack('iihhi', 0, 0, 0x14, 0x00, 700)
		fd = os_open("/dev/input/" + device, O_RDWR)
		os_write(fd, event_repeat)
		os_write(fd, event_delay)
		os_close(fd)

	def setRepeat(self, device, value): #REP_PERIOD
		if self.getDeviceAttribute(device, 'enabled') == True:
			print("[iInputDevices] setRepeat for device %s to %d ms" % (device,value))
			event = struct.pack('iihhi', 0, 0, 0x14, 0x01, int(value))
			fd = os_open("/dev/input/" + device, O_RDWR)
			os_write(fd, event)
			os_close(fd)

	def setDelay(self, device, value): #REP_DELAY
		if self.getDeviceAttribute(device, 'enabled') == True:
			print("[iInputDevices] setDelay for device %s to %d ms" % (device,value))
			event = struct.pack('iihhi', 0, 0, 0x14, 0x00, int(value))
			fd = os_open("/dev/input/" + device, O_RDWR)
			os_write(fd, event)
			os_close(fd)


class InitInputDevices:
	
	def __init__(self):
		self.currentDevice = ""
		self.createConfig()
	
	def createConfig(self, *args):
		config.inputDevices = ConfigSubsection()
		for device in sorted(iInputDevices.Devices.keys()):
			self.currentDevice = device
			#print "[InitInputDevices] -> creating config entry for device: %s -> %s  " % (self.currentDevice, iInputDevices.Devices[device]["name"])
			self.setupConfigEntries(self.currentDevice)
			self.currentDevice = ""

	def inputDevicesEnabledChanged(self,configElement):
		if self.currentDevice != "" and iInputDevices.currentDevice == "":
			iInputDevices.setEnabled(self.currentDevice, configElement.value)
		elif iInputDevices.currentDevice != "":
			iInputDevices.setEnabled(iInputDevices.currentDevice, configElement.value)

	def inputDevicesNameChanged(self,configElement):
		if self.currentDevice != "" and iInputDevices.currentDevice == "":
			iInputDevices.setName(self.currentDevice, configElement.value)
			if configElement.value != "":
				devname = iInputDevices.getDeviceAttribute(self.currentDevice, 'name')
				if devname != configElement.value:
					cmd = "config.inputDevices." + self.currentDevice + ".enabled.value = False"
					exec (cmd)
					cmd = "config.inputDevices." + self.currentDevice + ".enabled.save()"
					exec (cmd)
		elif iInputDevices.currentDevice != "":
			iInputDevices.setName(iInputDevices.currentDevice, configElement.value)

	def inputDevicesRepeatChanged(self,configElement):
		if self.currentDevice != "" and iInputDevices.currentDevice == "":
			iInputDevices.setRepeat(self.currentDevice, configElement.value)
		elif iInputDevices.currentDevice != "":
			iInputDevices.setRepeat(iInputDevices.currentDevice, configElement.value)
		
	def inputDevicesDelayChanged(self,configElement):
		if self.currentDevice != "" and iInputDevices.currentDevice == "":
			iInputDevices.setDelay(self.currentDevice, configElement.value)
		elif iInputDevices.currentDevice != "":
			iInputDevices.setDelay(iInputDevices.currentDevice, configElement.value)

	def setupConfigEntries(self,device):
		cmd = "config.inputDevices." + device + " = ConfigSubsection()"
		exec (cmd)
		cmd = "config.inputDevices." + device + ".enabled = ConfigYesNo(default = False)"
		exec (cmd)
		cmd = "config.inputDevices." + device + ".enabled.addNotifier(self.inputDevicesEnabledChanged,config.inputDevices." + device + ".enabled)"
		exec (cmd)
		cmd = "config.inputDevices." + device + '.name = ConfigText(default="")'
		exec (cmd)
		cmd = "config.inputDevices." + device + ".name.addNotifier(self.inputDevicesNameChanged,config.inputDevices." + device + ".name)"
		exec (cmd)
		cmd = "config.inputDevices." + device + ".repeat = ConfigSlider(default=100, increment = 10, limits=(0, 500))"
		exec (cmd)
		cmd = "config.inputDevices." + device + ".repeat.addNotifier(self.inputDevicesRepeatChanged,config.inputDevices." + device + ".repeat)"
		exec (cmd)
		cmd = "config.inputDevices." + device + ".delay = ConfigSlider(default=700, increment = 100, limits=(0, 5000))"
		exec (cmd)
		cmd = "config.inputDevices." + device + ".delay.addNotifier(self.inputDevicesDelayChanged,config.inputDevices." + device + ".delay)"
		exec (cmd)


iInputDevices = inputDevices()
