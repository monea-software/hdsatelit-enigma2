# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Video output for HDSatelit Image: reads what the receiver driver offers under /proc/stb/video and
# applies the chosen values. Nothing is assumed: an option exists
# only when the driver file for it exists, and only values from the driver's own list are written.
#
# On HiSilicon receivers (u5x/u57) the platform daemon (showiframe) sets the HDMI format each time a
# video starts, from videomode_50hz / videomode_60hz / videomode_24hz, by the frame rate of the channel. Writing
# only videomode was lost at the next zap, so the chosen mode goes into the three rate files, in the order the
# driver expects: videomode_50hz; videomode_60hz only if the first write worked;
# videomode (the 50 Hz mode) only as a fallback, when one of the two failed; then videomode_24hz. The values are
# written without a newline. A driver without the rate files gets videomode only (the emulator has no driver
# files at all and only logs what would be written). The daemon uses the files only at the next video start, so
# the screens that change the mode start the playing channel again (applyNow), to show the new mode during the
# confirmation. "Refresh rate by channel" = No (default): the chosen mode in all three files, no HDMI format
# change at zap. Yes: the same resolution at the rate of the channel (1080p50 / 1080p / 1080p24). The choice is
# saved even when it equals the default and is applied again at every start. Setari > Video lists only the
# modes the TV accepts (videomode_preferred), plus the saved mode, grouped by resolution and rate
# (sortModes); the saved value stays the whole driver mode name (1080p50).
# Setari > Video shows the mode as two rows, "Resolution" and "Frecventa" (the rates of that resolution, plus
# "Automat dupa canal" = "Refresh rate by channel" Yes); they are derived from the two saved settings (splitMode,
# joinMode), which stay the only ones saved. The start wizard offers the HD and UHD resolutions at 50 and 60 Hz
# (wizardModes). The web page /video and Setari > Video try a new setting the same way (tryVideo, keepVideo,
# cancelVideo). What the screen shows while the receiver changes the channel is the driver file zapmode (or
# zapping_mode on other drivers): config.av.hds_zapmode, offered only when the file exists, written at every start
# and at every change.
# How 4:3 programmes fill a 16:9 picture is the driver file policy (config.av.hds_policy43, the "Emisiunile 4:3" row of
# Setari > Video and of the web page /video, "Imaginea 4:3"): offered only when policy and policy_choices exist, only values of that
# list (split on any space: the u57 list has two spaces in it). The HiSilicon driver has the names the other way
# round for 4:3 programmes: "panscan" shows them whole with black bars at the sides (pillarbox) and "letterbox" fills
# the screen and cuts them at the top and bottom, so the labels say what is seen (policyLabel). The A/V row "Aspect
# Ratio" (Components/AVSwitch.py, lib/driver/avswitch.cpp) writes policy too; until a choice is saved here nothing is
# written and the row shows what the driver has (16:9 always = panscan); a saved choice is written at every start, at
# every change and again after the "Aspect Ratio" row wrote its own value; with "Aspect Ratio" on a 4:3 TV the row is not
# offered and nothing is written (policy is then about 16:9 programmes). policy2 (pictures wider than 16:9) is not
# offered: whether the driver has its names the other way round there too is not known yet.
#
# HDMI colours (HdmiColors, config.av.hds_hdmi_colors): the u5x/u57 platform daemon starts the HDMI output as RGB
# with limited levels (16-235) and leaves the RGB range at "default" in the AVI InfoFrame (Q = 0), so the TV chooses
# the range. Many TVs take full levels (0-255) for the 60 Hz modes that share their timing with computer modes
# (1080p60, 2160p60, 720p60) and limited levels for the 50 Hz ones: the same picture looks washed out at 60 Hz only.
# YCbCr has limited levels by definition, so it looks the same at 50 and 60 Hz. The driver path to YCbCr is
# hdmi_colorimetry: the daemon applies a write at once (colorimetry BT.709, then YCbCr 4:4:4 when the TV declares
# it and 10 bits when the TV declares them; the HDMI driver adapts the format itself when the pixel clock would be
# too high). "bt709" is the only value written: with "auto" the daemon puts BT.2020 in the AVI InfoFrame of a
# BT.709 picture when the TV has BT.2020. Nothing takes the output back to RGB until the receiver starts again,
# so "rgb" is a choice for the next start. "ycbcr" (default) is written by the looks of HdmiColors, on a timer: one at
# start, then every COLOR_WAIT_MS while the daemon or the TV is not ready (COLOR_WAITS times) and every COLOR_IDLE_MS
# after that, also once YCbCr is on HDMI (the daemon puts RGB back when a TV without YCbCr 4:4:4 is connected and
# keeps it for the next TV). A look reads the choice, the EDID (hdmi0_sink) and the output (hdmi0, hdmi0_vo): small
# /proc files, about 2 ms on the u57 receiver. It writes only when the TV declares YCbCr 4:4:4, and at most
# COLOR_WRITES times between two changes (another EDID, another video mode, the standby, a choice made on a screen),
# since each write makes the TV synchronize again. Nothing is written in standby (its end is a change, and
# Components/HdsStandbyTv.py asks for a look a moment after the HDMI output is on again), nothing in the COLOR_HOLD_GROUPS
# modes unless YCbCr was chosen there on a screen (with the question), and no look runs while "rgb" is the choice.
import os
import re
import sys

from Components.config import config, ConfigSelection, ConfigYesNo
from Components.SystemInfo import SystemInfo

VIDEO = "/proc/stb/video/"
MODE_RX = re.compile(r"^(\d+)([ip])(\d*)$")
RESOLUTION_NAMES = {"2160": "4K UHD", "1080": "Full HD", "720": "HD", "576": "SD", "480": "SD"}
# a mode without a rate in its name: the driver outputs it at this rate (1080p = 1080p 60 Hz)
IMPLIED_RATES = {"2160": "60", "1080": "60", "720": "60", "576": "50", "480": "60"}
# rate -> driver file with the mode for content at that rate, in the order they are written (writeModeFiles)
RATE_FILES = ((50, "videomode_50hz"), (60, "videomode_60hz"), (24, "videomode_24hz"))
RATE_FILE = dict(RATE_FILES)
# Setari > Video lists only the modes the TV declares when it declares at least this many of the driver modes
TV_MIN_MODES = 2
# when nothing is saved: the first of these that the TV accepts (videomode_preferred) and the driver offers
DEFAULT_MODES =("1080p50", "1080i50", "720p50", "1080p", "1080i", "720p", "576p", "576i", "pal")
# used only when the driver files are missing (emulator on a PC)
SIMULATED_MODES = ["720p50", "720p", "1080i50", "1080i", "1080p50", "1080p", "1080p24", "1080p25", "1080p30", "2160p50",
	"2160p", "2160p24"]
# the order of the mode lists: by resolution from the top, and in each resolution 50 Hz, 60 Hz, then 24, 25, 30 Hz;
# 3D modes and unknown names come last, in the order of the driver list
GROUP_ORDER = ("2160p", "1080p", "1080i", "720p", "576p", "576i", "480p", "480i")
RATE_ORDER = ("50", "60", "24", "25", "30")
NAMED_MODES = {"pal": ("576i", "50"), "ntsc": ("480i", "60")}
# the start wizard: the HD and UHD resolutions at 50 and 60 Hz; 24/25/30 Hz and SD only in Setari > Video (a fixed
# 24/25/30 Hz mode makes the menus and the 50 Hz channels judder, so it is not a choice for the first start)
WIZARD_GROUPS = ("2160p", "1080p", "1080i", "720p")
WIZARD_RATES = ("50", "60")
# the wizard list when the video output is missing (tests on a PC), in the order of sortModes, and its default
WIZARD_FALLBACK = ("2160p50", "2160p", "1080p50", "1080p", "1080i50", "1080i", "720p50", "720p")
WIZARD_DEFAULT = DEFAULT_MODES[0]
# the value of the "Frecventa" row for "Automat dupa canal" (the mode then follows the rate of each channel)
AUTO_RATE = "auto"
# what the screen shows while the channel changes: the driver file (the first that exists), the values in the order
# offered, the default (the last picture stays until the new channel shows its own, instead of a black screen);
# the labels are in zapLabel
ZAP_FILES = ("zapmode", "zapping_mode")
ZAP_MODES = ("mute", "hold", "mutetilllock", "holdtilllock")
ZAP_DEFAULT = "hold"
ZAP_ATTR = "hds_zapmode"
# 4:3 programmes on a 16:9 picture (see the top of the file): the driver file, the setting, the known values in the order
# offered, the one the "Aspect Ratio" row writes by default (16:9 always), and the list used in the emulator
POLICY_FILE = "policy"
POLICY_ATTR = "hds_policy43"
POLICY_ORDER = ("panscan", "letterbox", "bestfit", "nonlinear", "auto")
POLICY_DEFAULT = "panscan"
SIMULATED_POLICY = ["auto", "bestfit", "letterbox", "panscan", "nonlinear"]
# the "Aspect Ratio" values (Components/AVSwitch.py) of a 4:3 TV
ASPECT_43 = ("4_3_letterbox", "4_3_panscan")
# HDMI colours (see the top of the file): the driver file and the only value written, the setting and its values,
# the HDMI driver state files (HiSilicon /proc/msp) and the pid file of the platform daemon
COLOR_FILE = "hdmi_colorimetry"
COLOR_WRITE = "bt709"
COLOR_ATTR = "hds_hdmi_colors"
COLOR_YCBCR = "ycbcr"
COLOR_RGB = "rgb"
COLOR_DEFAULT = COLOR_YCBCR
MSP = "/proc/msp/"
COLOR_SINK = "hdmi0_sink"
COLOR_STATES = ("hdmi0", "hdmi0_vo")
DAEMON_PID = "/dev/si.pid"
# the looks: one COLOR_CHECK_MS after each write, at most COLOR_WRITES writes between two changes (each one makes the TV
# synchronize again); while the daemon or the TV is not ready, one every COLOR_WAIT_MS, COLOR_WAITS times; then, and
# once YCbCr is on HDMI or cannot be, one every COLOR_IDLE_MS
COLOR_CHECK_MS = 2000
COLOR_WRITES = 3
COLOR_WAIT_MS = 15000
COLOR_WAITS = 40
COLOR_IDLE_MS = 60000
# resolutions where the looks do not write YCbCr by themselves, only after it was chosen there on a screen (with the
# question): YCbCr 4:4:4 at 10 bits needs 742.5 MHz at 2160p 50/60 Hz, above the 600 MHz that HDMI 2.0 TVs declare,
# and the HDMI driver lowering the depth by itself (DeepColorAdapt) is not proven on this receiver; () writes everywhere
COLOR_HOLD_GROUPS = ("2160p",)
# what HdmiColors.tryNow did when YCbCr was chosen on a screen
TRY_WRITTEN = "written"
TRY_ALREADY = "already"
TRY_TV = "tv"
TRY_LATER = "later"


def _procFundal(functie, *argumente):
	# fisierele driverului (/proc/msp, /proc/hisi), citite de pe firul principal: prin firul de fundal
	# (Components/HdsProcFundal.py); fara modul (probele de pe PC), direct
	try:
		from Components import HdsProcFundal
	except Exception:
		return functie(*argumente)
	return HdsProcFundal.citeste(functie, *argumente)


def readText_direct(path):
	try:
		with open(path) as f:
			return f.read().strip()
	except (IOError, OSError):
		return None


def readText(path):
	"""Ca readText_direct; fisierele driverului (/proc/msp, /proc/hisi) le citeste pe firul de fundal."""
	return _procFundal(readText_direct, path)


def writeText(path, value):
	try:
		with open(path, "w") as f:
			f.write(value)
		return True
	except (IOError, OSError) as err:
		print("[VideoOutput] writing %s to %s failed: %s" % (value, path, err))
		return False


def configElement(attr):
	"""the config.av element or None; ConfigSubsection raises KeyError, so getattr with a default does not work"""
	return config.av.content.items.get(attr)


def modeLabel(mode):
	match = MODE_RX.match(mode)
	if not match:
		return {"pal": "PAL 576i 50 Hz", "ntsc": "NTSC 480i 60 Hz"}.get(mode, mode)
	lines, scan, rate = match.groups()
	label = "%s%s %s" % (lines, scan, RESOLUTION_NAMES.get(lines, ""))
	rate = rate or IMPLIED_RATES.get(lines, "")
	if rate:
		label += " %s Hz" % rate
	return label.replace("  ", " ").strip()


def modeParts(mode):
	"""(resolution group, rate) of a driver mode name, the rate as modeLabel shows it: 1080p50 -> ("1080p", "50"),
	1080p -> ("1080p", "60"), pal -> ("576i", "50"); (None, None) for 3D modes and unknown names"""
	if mode in NAMED_MODES:
		return NAMED_MODES[mode]
	match = MODE_RX.match(mode)
	if not match:
		return (None, None)
	lines, scan, rate = match.groups()
	return (lines + scan, rate or IMPLIED_RATES.get(lines, ""))


def sortModes(modes):
	"""the modes grouped by resolution (GROUP_ORDER) and by rate inside each group (RATE_ORDER); modes with the same
	place (pal and 576i) and the modes outside the two orders keep the order they came in"""
	def key(item):
		index, mode = item
		group, rate = modeParts(mode)
		return (GROUP_ORDER.index(group) if group in GROUP_ORDER else len(GROUP_ORDER),
			RATE_ORDER.index(rate) if rate in RATE_ORDER else len(RATE_ORDER), index)
	return [mode for index, mode in sorted(enumerate(modes), key=key)]


def groupLabel(mode):
	"""the name of the resolution group of a mode, the same in every language like modeLabel: "1080p Full HD",
	"576i SD"; a 3D or unknown mode is a group of its own, under its own name"""
	group, rate = modeParts(mode)
	if group is None:
		return mode
	return ("%s %s" % (group, RESOLUTION_NAMES.get(group[:-1], ""))).strip()


def modeGroups(modes):
	"""[(group label, [(mode, modeLabel(mode)), ...]), ...] in the order of sortModes, one entry per resolution"""
	groups = []
	for mode in sortModes(modes):
		label = groupLabel(mode)
		if not groups or groups[-1][0] != label:
			groups.append((label, []))
		groups[-1][1].append((mode, modeLabel(mode)))
	return groups


def groupKey(mode):
	"""the resolution of a mode as the "Resolution" row keeps it: 1080p50 -> "1080p", pal -> "576i"; a 3D or unknown
	mode is a resolution of its own, under its own name"""
	group = modeParts(mode)[0]
	return group if group is not None else mode


def groupModes(modes, group):
	"""the modes of one resolution, in the order of sortModes"""
	return [mode for mode in sortModes(modes) if groupKey(mode) == group]


def resolutionChoices(modes):
	"""[(resolution, label)] for the "Resolution" row: one per resolution of `modes`, in the order of sortModes"""
	result = []
	for mode in sortModes(modes):
		key = groupKey(mode)
		if key not in [value for value, label in result]:
			result.append((key, groupLabel(mode)))
	return result


def rateChoices(modes, group, auto=False):
	"""[(value, label)] for the "Frecventa" row of one resolution: its modes as "50 Hz", "60 Hz", "24 Hz" (the whole
	modeLabel when the mode has no rate or when two modes of the resolution have the same one, pal and 576i), then
	"Automat dupa canal" (AUTO_RATE) when `auto`"""
	members = groupModes(modes, group)
	rates = [modeParts(mode)[1] for mode in members]
	result = []
	for mode, rate in zip(members, rates):
		if rate and rates.count(rate) == 1:
			result.append((mode, "%s Hz" % rate))
		else:
			result.append((mode, modeLabel(mode)))
	if auto:
		result.append((AUTO_RATE, _("Automat după canal")))
	return result


def wizardModes(modes, keep=()):
	"""the list of the start wizard: from `modes` (screenModes, what the TV accepts) the WIZARD_GROUPS at
	WIZARD_RATES, plus the modes in `keep` (the saved one), all in the order of sortModes"""
	chosen = []
	for mode in list(modes) + list(keep):
		group, rate = modeParts(mode)
		if mode not in chosen and (mode in keep or (group in WIZARD_GROUPS and rate in WIZARD_RATES)):
			chosen.append(mode)
	return sortModes(chosen)


def N_(text):
	"""xgettext marker: the text is translated where it is shown"""
	return text


def zapLabel(value):
	"""the untranslated text of a zapmode value; a value this image does not know keeps the driver name. The config
	element is made at start, before the language is active, so the label stays untranslated here and
	ConfigSelection (getText, getMulti) and the web page translate it when they show it. The labels are short, so
	the value does not reach the row label with bigger letters (Setup list, 1176 px); "lin" (the ...tilllock
	values) is explained in zapDescription"""
	return {
		"mute": N_("Ecran negru"),
		"hold": N_("Ultima imagine"),
		"mutetilllock": N_("Ecran negru, lin"),
		"holdtilllock": N_("Ultima imagine, lin"),
	}.get(value, value)


def policyLabel(value):
	"""the untranslated text of a policy value for 4:3 programmes, by what is seen on this driver (see the top of the
	file); translated where it is shown, like zapLabel. A value this image does not know keeps the driver name."""
	return {
		"panscan": N_("Întreagă, cu benzi negre în lateral"),
		"letterbox": N_("Mărită, tăiată sus și jos"),
		"bestfit": N_("Întinsă pe tot ecranul"),
		"nonlinear": N_("Întinsă mai mult spre margini"),
		"auto": N_("Automat"),
	}.get(value, value)


def policyRowText():
	"""the label of the row (4:3 programmes), translated now"""
	return _("Imaginea 4:3")


def policyDescription():
	"""the help line of the "Emisiunile 4:3" row, on the screen and in the web page"""
	return _("Cum se vede imaginea 4:3 a emisiunilor vechi pe ecranul lat. Întinsă: fără benzi, dar oamenii par mai lați.")


def wideTv():
	"""True unless the "Aspect Ratio" row says the TV is 4:3: there policy is about 16:9 programmes on a 4:3 screen, and
	the "Imaginea 4:3" row (whose labels are about a wide screen) is not offered and not written"""
	aspect = configElement("aspectratio")
	return aspect is None or aspect.value not in ASPECT_43


def policyElement():
	"""config.av.hds_policy43, or None when the driver has no policy file with its list, or with a 4:3 TV (wideTv)"""
	return configElement(POLICY_ATTR) if wideTv() else None


def zapDescription():
	"""the help line of the zapmode row, on the screen and in the web page"""
	return _("Ce se vede cât receptorul trece pe alt canal. Cu „lin”, canalul nou apare abia când imaginea lui e stabilă, cu o clipă mai târziu.")


def colorLabel(value):
	"""the untranslated text of an HDMI colours value (translated where it is shown, like zapLabel)"""
	return {
		COLOR_YCBCR: N_("Ca la televizor (YCbCr)"),
		COLOR_RGB: N_("Ca la calculator (RGB)"),
	}.get(value, value)


def colorDescription(tvAccepts=True):
	"""the help line of the HDMI colours row, on the screen and in the web page; tvAccepts = HdmiColors.tvAccepts().
	With a TV that does not take YCbCr its sentence takes the place of the one about the next start, so the text stays
	within the three lines of the Setup description of the skin"""
	text = _("Cu „Ca la televizor”, imaginea arată la fel pe 50 și pe 60 Hz.")
	if tvAccepts is False:
		return text + " " + _("Televizorul acesta nu primește „Ca la televizor”, deci primește „Ca la calculator”.")
	return text + " " + _("„Ca la calculator” se aplică la următoarea pornire; pe unele televizoare imaginea iese spălăcită pe 60 Hz.")


def colorElement():
	"""config.av.hds_hdmi_colors, or None when the receiver has no way to YCbCr (HdmiColors.offered)"""
	return configElement(COLOR_ATTR)


def mspField(text, key):
	"""the first value of `key` in a HiSilicon /proc/msp text ("Key   : value", one or more pairs on a line), or None"""
	if not text:
		return None
	match = re.search(r"(?:^|\s)%s\s*:\s*(\S+)" % re.escape(key), text, re.M)
	return match.group(1) if match else None


def sinkYcbcr(text):
	"""what the TV declares in hdmi0_sink (its EDID as the HDMI driver read it): True = YCbCr 4:4:4, False = a valid
	EDID without it, None = no valid EDID (TV off, cable out, file missing)"""
	valid = mspField(text, "CapIsValid")
	if valid is None or valid.upper() not in ("YES", "Y", "TRUE", "1"):
		return None
	match = re.search(r"^\s*ColorSpace\s*:\s*(.+)$", text, re.M)
	if match is None:
		return False
	return "YCBCR444" in match.group(1).upper().replace("_", "").replace(" ", "")


def ycbcrSpace(value):
	"""True for a YCbCr colour space name of the HDMI driver (YCbCr444, YCBCR422, YUV420)"""
	return bool(value) and value.upper().startswith(("YCBCR", "YUV"))


def edidKey(text):
	"""what tells one TV from another in hdmi0_sink: CapIsValid and the raw EDID bytes (the other fields of the file
	have counters that change by themselves); None without the file"""
	if not text:
		return None
	match = re.search(r"EDIDRawData[^\n]*\n(.*?)\n\s*-{5}", text, re.S)
	raw = "".join(re.findall(r"0x[0-9a-fA-F]{2}", match.group(1))) if match else ""
	return (mspField(text, "CapIsValid"), raw)


def inStandby():
	"""True while the Standby screen is open; Screens.Standby is looked up only once enigma2 has loaded it"""
	module = sys.modules.get("Screens.Standby")
	return getattr(module, "inStandby", None) is not None


def rateModes(mode, byChannel, rateChoices):
	"""{rate: mode} for each rate file that exists (rateChoices = {50: [...], 60: [...], 24: [...]}, the driver list
	of each file). No: the chosen mode for every rate. Yes: the same resolution at each rate
	(1080p50 / 1080p / 1080p24); 24 Hz without its own variant takes the 60 Hz one (1080i), a rate without
	a variant keeps the chosen mode (576i, pal, 3D). A rate whose file does not offer any of these is left out."""
	result = {}
	match = MODE_RX.match(mode)
	base = match.group(1) + match.group(2) if match else None
	for rate, choices in rateChoices.items():
		candidates = []
		if byChannel and base:
			if rate == 50:
				candidates = [base + "50"]
			elif rate == 60:
				candidates = [base, base + "60"]
			else:
				candidates = [base + "24", base, base + "60"]
		candidates.append(mode)
		for candidate in candidates:
			if candidate in choices:
				result[rate] = candidate
				break
	return result


def defaultMode(options, preferred):
	"""the mode used when nothing is saved: fixed (not "what the driver has now", which changes from one start to
	the next), 1080p50 when the TV accepts it"""
	tv = [mode for mode in preferred if mode in options]
	for mode in DEFAULT_MODES:
		if mode in (tv or options):
			return mode
	return (tv or options)[0]


class VideoOutput:
	# setting name -> (config attribute, driver file with the current value, driver file with the choices)
	SETTINGS = (
		("videomode", "hds_videomode", "videomode", "videomode_choices"),
		("colorspace", "hds_colorspace", "hdmi_colorspace", "hdmi_colorspace_choices"),
		("colordepth", "hds_colordepth", "hdmi_colordepth", "hdmi_colordepth_choices"),
		("hdrtype", "hds_hdrtype", "hdmi_hdrtype", "hdmi_hdrtype_choices"),
	)
	RATE_ATTR = "hds_videorate_by_channel"

	def __init__(self, root=None):
		self.root = root if root is not None else VIDEO
		self.choices = {}
		for name, attr, current, choices in self.SETTINGS:
			self.choices[name] = self.readChoices(choices)
		self.preferred = self.readChoices("videomode_preferred")
		self.lastModeReached = None
		self.colors = None         # HdmiColors, set by InitVideoOutput
		self.simulation = not self.choices["videomode"]
		if self.simulation:
			self.choices["videomode"] = SIMULATED_MODES[:]
		# rate -> modes the driver accepts in that rate file; only for the files that exist
		self.rateChoices = {}
		for rate, name in RATE_FILES:
			if self.simulation:
				self.rateChoices[rate] = SIMULATED_MODES[:]
			elif os.path.exists(self.root + name):
				self.rateChoices[rate] = self.readChoices(name + "_choices") or self.choices["videomode"]
		# policy (4:3 programmes): only with the file and its list, the known values first in the order of POLICY_ORDER
		self.policyChoices = []
		offered = SIMULATED_POLICY[:] if self.simulation else (self.readChoices(POLICY_FILE + "_choices")
			if os.path.exists(self.root + POLICY_FILE) else [])
		self.policyChoices = [value for value in POLICY_ORDER if value in offered] + 			[value for value in offered if value not in POLICY_ORDER]
		# zapmode: the first driver file that exists; its values from *_choices (ZAP_MODES when that list is
		# missing), the known ones first in the order of ZAP_MODES; nothing when the driver has no such file
		self.zapFile = None
		self.zapChoices = []
		for name in ZAP_FILES:
			if self.simulation or os.path.exists(self.root + name):
				self.zapFile = name
				offered = [] if self.simulation else self.readChoices(name + "_choices")
				offered = offered or list(ZAP_MODES)
				self.zapChoices = [value for value in ZAP_MODES if value in offered] + \
					[value for value in offered if value not in ZAP_MODES]
				break

	def readChoices(self, name):
		text = readText(self.root + name)
		return text.split() if text else []

	def available(self, name):
		return bool(self.choices.get(name))

	def hasRates(self):
		return bool(self.rateChoices)

	def autoMode(self, modes, group):
		"""the mode saved with "Automat dupa canal" for a resolution of `modes` (its 50 Hz mode, else its first), or
		None when the rate files would all get the same mode (no rate files, SD, 3D): then the "Frecventa" row has
		no "Automat" for it"""
		if not self.rateChoices:
			return None
		members = groupModes(modes, group)
		if not members:
			return None
		fifty = [mode for mode in members if modeParts(mode)[1] == "50"]
		mode = (fifty or members)[0]
		if len(set(rateModes(mode, True, self.rateChoices).values())) < 2:
			return None
		return mode

	def rateRow(self, modes, group):
		"""the "Frecventa" row of a resolution, with "Automat dupa canal" where it changes something"""
		return rateChoices(modes, group, self.autoMode(modes, group) is not None)

	def splitMode(self, modes, mode, byChannel):
		"""(resolution, "Frecventa" value) shown for the saved mode and "Refresh rate by channel" """
		group = groupKey(mode)
		if byChannel and self.autoMode(modes, group) is not None:
			return group, AUTO_RATE
		return group, mode

	def joinMode(self, modes, group, rate):
		"""(mode, byChannel) saved for a resolution and a "Frecventa" value; None when they do not go together"""
		if rate == AUTO_RATE:
			mode = self.autoMode(modes, group)
			return (mode, True) if mode is not None else None
		if rate in modes and groupKey(rate) == group:
			return rate, False
		return None

	def rateAfterResolution(self, modes, group, previous):
		"""the "Frecventa" value when the resolution changes to `group`: "Automat" stays "Automat", a mode gives the
		mode with the same rate, otherwise the first of the row (50 Hz in the grouped order)"""
		values = [value for value, label in self.rateRow(modes, group)]
		if not values:
			return None
		if previous in values:
			return previous
		rate = modeParts(previous)[1] if previous and previous != AUTO_RATE else None
		for value in values:
			if rate and value != AUTO_RATE and modeParts(value)[1] == rate:
				return value
		return values[0]

	def writeZapmode(self, value):
		"""writes a zapmode value from the driver list; True when it got to the driver"""
		if not self.zapFile or value not in self.zapChoices:
			print("[VideoOutput] zapmode %s is not offered, not written" % value)
			return False
		return self.write(self.zapFile, value)

	def defaultMode(self):
		return defaultMode(self.choices["videomode"], self.preferred)

	def writePolicy(self, value):
		"""writes a policy value from the driver list (4:3 programmes); True when it got to the driver"""
		if value not in self.policyChoices:
			print("[VideoOutput] policy %s is not offered, not written" % value)
			return False
		return self.write(POLICY_FILE, value)

	def readPolicy(self):
		"""what the driver has in policy now (None in the emulator or without the file)"""
		return None if self.simulation else readText(self.root + POLICY_FILE)

	def readPreferred(self):
		"""reads again what the TV accepts (videomode_preferred, from its EDID): the TV can be switched on or
		changed after the receiver started"""
		if not self.simulation:
			self.preferred = self.readChoices("videomode_preferred")
		return self.preferred

	def screenModes(self, keep=()):
		"""the modes offered in Setari > Video: the driver modes the TV accepts (videomode_preferred), grouped by
		resolution and rate (sortModes); all driver modes when the TV list is missing, empty or has fewer than
		TV_MIN_MODES of them (a TV switched off or a cable taken out while the receiver starts can leave a short list,
		and one mode is no choice). The modes in `keep` (the saved one) stay even when the TV does not declare them.
		Only the order shown changes: self.choices["videomode"] keeps the driver order and stays the check for what is
		written."""
		offered = self.choices["videomode"]
		tv = set(self.preferred)
		if len(tv.intersection(offered)) < TV_MIN_MODES:
			return sortModes(offered)
		return sortModes([mode for mode in offered if mode in tv or mode in keep])

	def writeModeFiles(self, rates, fallback, write=None):
		"""writes {rate: value} in the order the u57 driver expects: videomode_50hz;
		videomode_60hz only if the first write worked; videomode = fallback only if one of the two failed or has
		no value; then videomode_24hz. Without rate files only videomode. [(file, value, written)] in write order."""
		write = write or self.write
		written = []

		def put(name, value):
			done = bool(write(name, value))
			written.append((name, value, done))
			return done

		if not self.rateChoices:
			if fallback:
				put("videomode", fallback)
			return written
		success = bool(rates.get(50)) and put(RATE_FILE[50], rates[50])
		if success:
			success = bool(rates.get(60)) and put(RATE_FILE[60], rates[60])
		if not success and fallback:
			put("videomode", fallback)
		if rates.get(24):
			put(RATE_FILE[24], rates[24])
		return written

	@staticmethod
	def modeReached(written):
		"""True if the mode got to the driver: both videomode_50hz and _60hz, or the videomode fallback (or
		videomode alone, without rate files), and videomode_24hz when it was written"""
		done = dict((name, ok) for name, value, ok in written)
		reached = (done.get(RATE_FILE[50]) and done.get(RATE_FILE[60])) or done.get("videomode", False)
		return bool(reached and done.get(RATE_FILE[24], True))

	def writeMode(self, mode, byChannel, write=None):
		"""writes the driver files for this mode (see writeModeFiles); a rate file that does not offer the mode is
		not written and counts as a failed write; videomode as fallback gets the 50 Hz mode"""
		rates = rateModes(mode, byChannel, self.rateChoices)
		for rate, name in RATE_FILES:
			if rate in self.rateChoices and rate not in rates:
				print("[VideoOutput] %s does not offer %s, left as it is" % (name, mode))
		fallback = rates.get(50, mode)
		if fallback not in self.choices["videomode"]:
			fallback = mode
		return self.writeModeFiles(rates, fallback, write)

	def modeFiles(self, mode, byChannel):
		"""[(driver file, value)] written for this mode when every write works (for the log and the tests)"""
		return [(name, value) for name, value, done in self.writeMode(mode, byChannel, lambda name, value: True)]

	def write(self, name, value):
		if self.simulation:
			print("[VideoOutput] simulation: %s would be set to %s" % (name, value))
			return True
		return writeText(self.root + name, value)

	def snapshot(self):
		"""what the driver uses now (every file this module writes), to go back to it"""
		if self.simulation:
			return {}
		names = [name for rate, name in RATE_FILES if rate in self.rateChoices]
		names += [current for name, attr, current, choices in self.SETTINGS if self.choices[name]]
		return dict((name, readText(self.root + name)) for name in names)

	def restore(self, previous):
		"""writes back a snapshot, in the same order as a new mode (videomode only as fallback, or when there are no
		rate files); only values the driver file offers; True if all got to the driver"""
		ok = True
		rates = {}
		for rate, name in RATE_FILES:
			value = previous.get(name)
			if value and value in self.rateChoices.get(rate, []):
				rates[rate] = value
		fallback = previous.get("videomode")
		if not (fallback and fallback in self.choices.get("videomode", [])):
			fallback = rates.get(50)
		if rates or fallback:
			ok = self.modeReached(self.writeModeFiles(rates, fallback))
		for name, attr, current, choices in self.SETTINGS:
			if name == "videomode":
				continue
			value = previous.get(current)
			if value and value in self.choices.get(name, []):
				ok = self.write(current, value) and ok
		return ok

	def apply(self, values):
		"""writes the given values (name -> value; "rate_by_channel" -> True/False for the video mode); only values
		from the driver list; True if all succeeded. self.lastModeReached = whether the video mode got to the driver
		(modeReached), None when no video mode was given: the screens do not ask about a mode the driver refused."""
		ok = True
		self.lastModeReached = None
		for name, attr, current, choices in self.SETTINGS:
			value = values.get(name)
			if not value:
				continue
			if value not in self.choices.get(name, []):
				print("[VideoOutput] %s is not offered for %s, not written" % (value, name))
				ok = False
				if name == "videomode":
					self.lastModeReached = False
				continue
			if name == "videomode":
				self.lastModeReached = self.modeReached(self.writeMode(value, bool(values.get("rate_by_channel"))))
				if not self.lastModeReached:
					print("[VideoOutput] the driver did not take the video mode %s" % value)
				ok = self.lastModeReached and ok
			else:
				ok = self.write(current, value) and ok
		return ok

	def applyConfig(self):
		values = {}
		for name, attr, current, choices in self.SETTINGS:
			element = configElement(attr)
			if element is not None:
				values[name] = element.value
		element = configElement(self.RATE_ATTR)
		values["rate_by_channel"] = element is not None and element.value
		return self.apply(values)

	def setMode(self, mode, byChannel=None):
		"""for other screens (start wizard): sets config.av.hds_videomode, applies it and saves it in memory; the
		caller writes the settings file (configfile.save()). False if the driver does not offer the mode."""
		element = configElement("hds_videomode")
		if element is None or mode not in self.choices["videomode"]:
			return False
		if mode not in element.choices:
			# offered by the driver but left out of the list by the TV list: it joins the list, or the value
			# would fall back to the default
			updateModeChoices(False, (mode,), self)
		element.value = mode
		rate = configElement(self.RATE_ATTR)
		if byChannel is not None and rate is not None:
			rate.value = byChannel
		ok = self.applyConfig()
		element.save()
		if rate is not None:
			rate.save()
		return ok


class _Timer:
	"""a one-shot eTimer for HdmiColors (made when the first look is put on the timer)"""

	def __init__(self, callback):
		from enigma import eTimer
		self.timer = eTimer()
		self.timer.callback.append(callback)

	def start(self, ms):
		self.timer.start(ms, True)


class HdmiColors:
	"""YCbCr or RGB on HDMI through hdmi_colorimetry (see the top of the file). offered: the driver file takes
	COLOR_WRITE and the HDMI driver state is readable (HiSilicon /proc/msp), or the emulator (simulation: the write is
	only logged and no look is put on the timer). The looks (step) run on the enigma2 thread from the timer. Setari >
	Video and the web page call tryNow when YCbCr is chosen there, Setari > Video calls resume when it opens (a look
	now); GET /api/video only reads (tvAccepts)."""

	def __init__(self, root=VIDEO, msp=MSP, pidFile=DAEMON_PID, simulation=False, timer=None):
		self.root = root
		self.msp = msp
		self.pidFile = pidFile
		self.simulation = simulation
		self.makeTimer = timer or _Timer
		self.timer = None
		self.pending = False       # a look is on the timer
		self.nextMs = None         # the delay of that look
		choices = readText(root + COLOR_FILE + "_choices")
		self.offered = bool(simulation or (choices and COLOR_WRITE in choices.split() and
			os.path.exists(root + COLOR_FILE) and os.path.exists(msp + COLOR_SINK)))
		self.written = False       # COLOR_WRITE got to the driver since this start
		self.writes = 0            # writes since the last change
		self.waits = 0             # looks with the daemon or the TV not ready, since the last change
		self.exhausted = False     # COLOR_WRITES writes without YCbCr on HDMI: no write until the next change
		self.refused = False       # the TV connected does not take YCbCr, or the link is DVI
		self.change = None         # changeKey() of the last look; another value = a change
		self.chosenGroup = None    # the resolution where YCbCr was chosen on a screen (written there even if held)
		self.said = None           # the last state written in the log by the looks (each one once per change)

	def tvAccepts(self):
		"""sinkYcbcr of the TV connected now; True in the emulator"""
		if self.simulation:
			return True
		return sinkYcbcr(readText(self.msp + COLOR_SINK))

	def daemonRuns(self):
		return self.simulation or os.path.exists(self.pidFile)

	def linkDvi(self):
		"""True when the HDMI driver sends DVI (a computer monitor): no YCbCr there"""
		if self.simulation:
			return False
		mode = mspField(readText(self.msp + COLOR_STATES[0]), "TMDSMode")
		return bool(mode) and mode.upper().startswith("DVI")

	def ycbcrNow(self):
		"""True when the HDMI driver was asked for YCbCr (hdmi0, the attributes of the daemon) or sends it (hdmi0_vo),
		read now and not kept (the daemon can put RGB back); in the emulator, after a write"""
		if self.simulation:
			return self.written
		return any(ycbcrSpace(mspField(readText(self.msp + name), "OutColorSpace")) for name in COLOR_STATES)

	def readSink(self):
		return None if self.simulation else readText(self.msp + COLOR_SINK)

	def readiness(self, sink):
		"""True = the write can be made now; None = not yet (the daemon does not run, no valid EDID in `sink`, the text of
		hdmi0_sink); False = not with this TV (no YCbCr 4:4:4 in its EDID, or a DVI link)"""
		if not self.daemonRuns():
			return None
		tv = True if self.simulation else sinkYcbcr(sink)
		if tv is None:
			return None
		return bool(tv) and not self.linkDvi()

	def ready(self):
		return self.readiness(self.readSink())

	@staticmethod
	def modeGroup():
		"""the resolution of the video mode set now (config.av.hds_videomode, also while a new mode is tried)"""
		element = configElement("hds_videomode")
		return groupKey(element.value) if element is not None else None

	def held(self):
		"""True when the video mode is in COLOR_HOLD_GROUPS and YCbCr was not chosen in that resolution on a screen"""
		group = self.modeGroup()
		return group in COLOR_HOLD_GROUPS and group != self.chosenGroup

	@staticmethod
	def changeKey(sink):
		"""what starts the writes again: the TV (edidKey), the video mode, "Refresh rate by channel", the standby"""
		mode = configElement("hds_videomode")
		rate = configElement(VideoOutput.RATE_ATTR)
		return (edidKey(sink), mode.value if mode is not None else None, rate.value if rate is not None else None,
			inStandby())

	def restart(self, key):
		"""a change: the writes, the waits and the log lines start again"""
		self.change = key
		self.writes = self.waits = 0
		self.exhausted = False
		self.said = None

	def say(self, text):
		"""a state of the looks in the log, once until it changes (the looks run every minute)"""
		if text != self.said:
			print("[VideoOutput] HDMI colours: %s" % text)
			self.said = text

	def write(self):
		"""one write of COLOR_WRITE; True when this write got to the driver"""
		self.writes += 1
		if self.simulation:
			print("[VideoOutput] simulation: %s would be set to %s" % (COLOR_FILE, COLOR_WRITE))
			done = True
		else:
			done = writeText(self.root + COLOR_FILE, COLOR_WRITE)
		self.written = done or self.written
		return done

	def tryNow(self):
		"""Setari > Video and the web page, when YCbCr is chosen: TRY_WRITTEN = COLOR_WRITE was written now (the picture
		changes at once, the screen asks), TRY_ALREADY = the output is YCbCr already, TRY_TV = this TV or link does not
		take YCbCr, TRY_LATER = the daemon or the TV is not ready or the write failed (the looks write it when they are
		ready). A choice made on a screen is a change, and it lets the looks write in a held resolution too."""
		if not self.offered:
			return TRY_LATER
		sink = self.readSink()
		self.restart(self.changeKey(sink))
		self.chosenGroup = self.modeGroup()
		if self.ycbcrNow():
			self.watch(COLOR_IDLE_MS)
			return TRY_ALREADY
		state = self.readiness(sink)
		if state is False:
			self.refused = True
			self.watch(COLOR_IDLE_MS)
			return TRY_TV
		if state is None or not self.write():
			self.watch(COLOR_WAIT_MS)
			return TRY_LATER
		print("[VideoOutput] HDMI colours: YCbCr written from the settings")
		self.watch(COLOR_CHECK_MS)
		return TRY_WRITTEN

	def start(self, value):
		"""at start: the first look, when YCbCr is the choice"""
		if value == COLOR_YCBCR and self.offered:
			self.step()

	def resume(self, value):
		"""when Setari > Video opens: a look now, so a TV switched on a moment ago gets YCbCr without waiting for the
		timer. Not a change (the writes are not counted again), and nothing while the look after a write is due (a
		second write would come before the daemon applied the first)."""
		if value != COLOR_YCBCR or not self.offered or (self.pending and self.nextMs == COLOR_CHECK_MS):
			return
		self.step()

	def afterStandby(self):
		"""at the end of the standby (Components/HdsStandbyTv.py, a moment after the HDMI output is on again): a look
		now instead of up to COLOR_IDLE_MS later, so a YCbCr write falls in the same seconds as the start of the output
		and the TV synchronizes once. The end of the standby is a change (changeKey), so the writes start again. Nothing
		while the look after a write is due."""
		element = colorElement()
		if not self.offered or element is None or element.value != COLOR_YCBCR:
			return False
		if self.pending and self.nextMs == COLOR_CHECK_MS:
			return False
		self.step()
		return True

	def step(self):
		"""one look: "rgb" chosen -> no more looks; YCbCr on HDMI -> nothing; not ready -> a look after COLOR_WAIT_MS
		(COLOR_IDLE_MS after COLOR_WAITS of them); a TV without YCbCr, the standby, a held resolution, COLOR_WRITES
		writes already -> nothing; else a write and a look after COLOR_CHECK_MS. The others end with a look after
		COLOR_IDLE_MS."""
		self.pending = False
		element = colorElement()
		if not self.offered or element is None or element.value != COLOR_YCBCR:
			return
		sink = self.readSink()
		key = self.changeKey(sink)
		if key != self.change:
			self.restart(key)
		if self.ycbcrNow():
			self.say("YCbCr")
			self.idle()
			return
		state = self.readiness(sink)
		if state is None:
			self.waits += 1
			if self.waits > COLOR_WAITS:
				self.say("the platform daemon or the TV is not ready, one look every %d s" % (COLOR_IDLE_MS // 1000))
			self.later(COLOR_WAIT_MS if self.waits <= COLOR_WAITS else COLOR_IDLE_MS)
			return
		self.refused = state is False
		if self.refused:
			self.say("the TV does not declare YCbCr 4:4:4 or the link is DVI, RGB stays")
		elif key[3]:
			pass                   # standby: written after it, the end of the standby is a change
		elif self.held():
			self.say("YCbCr is not written by itself in the %s modes, RGB stays" % self.modeGroup())
		elif self.exhausted or self.writes >= COLOR_WRITES:
			self.exhausted = True
			self.say("%s written %d times without YCbCr on HDMI, RGB stays until a change" % (COLOR_WRITE, self.writes))
		else:
			self.write()
			if not self.ycbcrNow():
				self.later(COLOR_CHECK_MS)
				return
			self.say("YCbCr")
		self.idle()

	def idle(self):
		"""the next look after COLOR_IDLE_MS (none in the emulator, where nothing changes)"""
		self.watch(COLOR_IDLE_MS)

	def watch(self, ms):
		if not self.simulation:
			self.later(ms)

	def later(self, ms):
		if self.timer is None:
			self.timer = self.makeTimer(self.step)
		self.pending = True
		self.nextMs = ms
		self.timer.start(ms)


videoOutput = None


def hdmiColors():
	"""the HdmiColors of the receiver (InitVideoOutput), or None"""
	return videoOutput.colors if videoOutput is not None else None


def updateModeChoices(reread=True, extra=(), output=None):
	"""the list of config.av.hds_videomode (Setari > Video) = the modes the TV accepts, plus the current and the
	saved mode and `extra`; reread = read videomode_preferred again first. The driver list stays the check for
	what is written (apply), so a saved mode is never refused because of the TV list."""
	output = output or videoOutput
	element = configElement("hds_videomode")
	if output is None or element is None:
		return
	if reread:
		output.readPreferred()
	keep = [element.value] + list(extra)
	if element.saved_value:
		keep.append(element.saved_value)
	modes = output.screenModes(keep)
	default = output.defaultMode()
	element.setChoices([(mode, modeLabel(mode)) for mode in modes], default=default if default in modes else element.value)


def videoElements():
	"""the saved settings of the video output that exist on this receiver: the mode, the HDMI ones and "Refresh rate
	by channel" (not zapmode: it cannot leave the TV black, so it needs no question)"""
	attrs = [attr for name, attr, current, choices in VideoOutput.SETTINGS] + [VideoOutput.RATE_ATTR]
	return [element for element in (configElement(attr) for attr in attrs) if element is not None]


def videoChanged():
	"""True when a video setting has a value that is not saved yet"""
	return any(element.isChanged() for element in videoElements())


def tryVideo(nav, output=None):
	"""applies the video settings as the elements hold them now (not saved yet), like Setari > Video before its
	question: (previous, shown). previous = what the driver had (snapshot), to go back to it; shown = None when the
	driver refused the mode (then the elements and the driver files are already back and the channel is not started
	again), else applyNow: True when the new mode is on screen now, False when it is used when a channel starts"""
	output = output or videoOutput
	previous = output.snapshot()
	output.applyConfig()
	if output.lastModeReached is False:
		# the picture did not change, so a "Yes" would save a mode nobody saw (applied again at every start)
		cancelVideo(previous, nav, False, output)
		return previous, None
	return previous, applyNow(nav, output)


def keepVideo(configfile, extra=()):
	"""a confirmed video setting: saved and written to the settings file at once (applied again at every start);
	`extra` = other elements saved with it (zapmode)"""
	for element in videoElements() + list(extra):
		element.save()
	configfile.save()


def cancelVideo(previous, nav, restart, output=None):
	"""back to the saved video settings: every driver file written goes back to `previous` (snapshot) and, when the
	channel was started with the new mode (restart), it starts again so the previous mode is on screen at once"""
	output = output or videoOutput
	for element in videoElements():
		element.cancel()
	output.restore(previous)
	if restart:
		applyNow(nav, output)


def timeshiftOn(nav):
	"""True if timeshift runs for the service playing now (starting it again would lose the buffer)"""
	try:
		from Screens.InfoBar import InfoBar
		if InfoBar.instance is not None and getattr(InfoBar.instance, "timeshift_enabled", False):
			return True
	except Exception:
		pass
	try:
		service = nav.getCurrentService()
		timeshift = service and service.timeshift()
		return bool(timeshift and timeshift.isTimeshiftActive())
	except Exception:
		return False


def restartService(nav):
	"""starts the channel playing now again, so the platform daemon uses the new rate files at once (it reads them
	only when a video starts: on the u57 receiver, values written minutes before were used only at the next
	zap). Not for a recording or stream played from a path (it would start again from the beginning) and not
	while timeshift runs (the buffer would be lost). Recordings keep running: they are services of their own and
	share the tuner with the channel. The channel already passed the parental control, so it is not asked again.
	True if the channel was started again."""
	ref = nav.getCurrentlyPlayingServiceReference()
	if ref is None:
		return False
	if ref.getPath():
		print("[VideoOutput] %s is played from a path: not started again, the mode is used at the next start" % ref.toString())
		return False
	if timeshiftOn(nav):
		print("[VideoOutput] timeshift runs: the channel is not started again, the mode is used at the next start")
		return False
	print("[VideoOutput] the channel starts again, so the new video mode is used now")
	nav.playService(ref, checkParentalControl=False, forceRestart=True)
	return True


def applyNow(nav, output=None):
	"""after the mode files were written (a new mode or a restore): True when the mode written is on screen now,
	either because the driver has no rate files (videomode is used at once) or because the channel playing was
	started again; False when it is used only when a channel starts (nothing playing, recording or timeshift)"""
	output = output or videoOutput
	if output is None or not output.hasRates():
		return True
	return restartService(nav)


def initPolicy(output):
	"""config.av.hds_policy43 (4:3 programmes) when the driver has policy with its list: the row shows what the driver
	has now (written by the "Aspect Ratio" row, Components/AVSwitch.py, which runs before), a choice made here is saved
	even when it equals that (save_forced), written at every start, at every change and again each time the "Aspect
	Ratio" row writes its own value (its notifier comes first). Nothing is written while nothing is saved here."""
	SystemInfo["HdsPolicy43"] = bool(output.policyChoices)
	if not output.policyChoices:
		return None
	now = output.readPolicy()
	default = now if now in output.policyChoices else (POLICY_DEFAULT if POLICY_DEFAULT in output.policyChoices
		else output.policyChoices[0])
	element = ConfigSelection(choices=[(value, policyLabel(value)) for value in output.policyChoices], default=default)
	element.save_forced = True
	setattr(config.av, POLICY_ATTR, element)

	def changed(el):
		# a change on a screen (tried at once, like zapmode) or its cancel (back to the value shown before)
		output.writePolicy(el.value)

	def afterAspect(el):
		# the "Aspect Ratio" row wrote its policy: a choice saved here comes back on top of it (only on a wide TV)
		if element.saved_value is not None and wideTv():
			output.writePolicy(element.value)

	element.addNotifier(changed, initial_call=False)
	aspect = configElement("aspectratio")
	if aspect is not None:
		aspect.addNotifier(afterAspect, initial_call=False)
	if element.saved_value is not None and wideTv():
		output.writePolicy(element.value)
	return element


def InitVideoOutput(root=None, msp=MSP, pidFile=DAEMON_PID, timer=None):
	"""msp, pidFile and timer: the HdmiColors sources (other ones only in the tests on a PC)"""
	global videoOutput
	videoOutput = VideoOutput(root)
	SystemInfo["HdsVideoOutput"] = True
	SystemInfo["HdsVideoSimulation"] = videoOutput.simulation
	for name, attr, current, choices in VideoOutput.SETTINGS:
		options = videoOutput.choices.get(name)
		if not options:
			continue
		if name == "videomode":
			labels = [(value, modeLabel(value)) for value in sortModes(options)]
			default = videoOutput.defaultMode()
		else:
			now = None if videoOutput.simulation else readText(videoOutput.root + current)
			labels = [(value, value) for value in options]
			default = now if now in options else options[0]
		element = ConfigSelection(choices=labels, default=default)
		# a choice equal to the default is written too: the default can differ from one start to the next
		element.save_forced = True
		setattr(config.av, attr, element)
	# the element was made with the whole driver list, so a saved mode the TV does not declare is still loaded;
	# the list shown in Setari > Video is then narrowed to what the TV accepts (plus that mode)
	updateModeChoices(False)
	if videoOutput.hasRates():
		# default No, and never offered in the start wizard: with Yes the TV resynchronizes at every channel with
		# another frame rate
		element = ConfigYesNo(default=False)
		element.save_forced = True
		setattr(config.av, VideoOutput.RATE_ATTR, element)
	# the mode and the rate option always go in the settings file (the next configfile.save() writes them),
	# so what is applied at start can be seen there; a saved mode the driver no longer offers is replaced
	for attr in ("hds_videomode", VideoOutput.RATE_ATTR):
		element = configElement(attr)
		if element is not None and element.saved_value != element.tostring(element.value):
			element.save()
	if videoOutput.simulation:
		print("[VideoOutput] no video driver files: video settings run as a simulation")
	# the saved choice comes back at start (and the default when nothing is saved)
	videoOutput.applyConfig()
	# zapmode: only when the driver has the file; the notifier writes the value now (the saved one or the default)
	# and at every change, so a choice on the screen is used from the next channel change
	SystemInfo["HdsZapMode"] = bool(videoOutput.zapChoices)
	if videoOutput.zapChoices:
		default = ZAP_DEFAULT if ZAP_DEFAULT in videoOutput.zapChoices else videoOutput.zapChoices[0]
		element = ConfigSelection(choices=[(value, zapLabel(value)) for value in videoOutput.zapChoices], default=default)
		setattr(config.av, ZAP_ATTR, element)
		output = videoOutput
		element.addNotifier(lambda element: output.writeZapmode(element.value))
	# 4:3 programmes (policy): only with the driver file and its list (see the top of the file)
	initPolicy(videoOutput)
	# HDMI colours: only where the platform daemon takes hdmi_colorimetry; the first look runs now when YCbCr is the
	# choice (HdmiColors.start, then the timer); nothing is written when the value changes on a screen, the screens
	# write it on OK (HdmiColors.tryNow)
	colors = HdmiColors(videoOutput.root, msp, pidFile, videoOutput.simulation, timer)
	videoOutput.colors = colors
	SystemInfo["HdsHdmiColors"] = colors.offered
	if colors.offered:
		element = ConfigSelection(choices=[(value, colorLabel(value)) for value in (COLOR_YCBCR, COLOR_RGB)],
			default=COLOR_DEFAULT)
		setattr(config.av, COLOR_ATTR, element)
		colors.start(element.value)
	return videoOutput
