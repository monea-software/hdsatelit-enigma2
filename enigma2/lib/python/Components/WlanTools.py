# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# WiFi helpers for HDSatelit Image: reading wpa_cli output and writing wpa_supplicant.conf.
# No screens and no enigma imports, so everything here can be
# tested on a PC. Passwords are never printed and never passed on a command line.
import hashlib
import os
import re

SUPPLICANT_CONF = "/etc/wpa_supplicant.conf"
CTRL_INTERFACE = "/var/run/wpa_supplicant"

FLAG_RX = re.compile(r"\[([^\]]+)\]")
HEX64_RX = re.compile(r"^[0-9a-fA-F]{64}$")
COUNTRY_RX = re.compile(r"^[A-Z]{2}$")

SECURITY_OPEN = "open"
SECURITY_OWE = "owe"
SECURITY_WEP = "wep"
SECURITY_WPA = "wpa"
SECURITY_WPA2 = "wpa2"
SECURITY_WPA2_WPA3 = "wpa2-wpa3"
SECURITY_WPA3 = "wpa3"
SECURITY_ENTERPRISE = "enterprise"
SUPPORTED_SECURITY = (SECURITY_OPEN, SECURITY_OWE, SECURITY_WPA, SECURITY_WPA2, SECURITY_WPA2_WPA3, SECURITY_WPA3)

SIMPLE_ESCAPES = {"\\": 0x5c, "\"": 0x22, "e": 0x1b, "n": 0x0a, "r": 0x0d, "t": 0x09}


def decodeSsid(text):
	"""SSID as printed by wpa_supplicant (printable ASCII, \\xNN and simple escapes) -> the exact bytes"""
	result = bytearray()
	i = 0
	n = len(text)
	while i < n:
		c = text[i]
		if c == "\\" and i + 1 < n:
			nxt = text[i + 1]
			if nxt == "x" and i + 3 < n and re.match(r"[0-9a-fA-F]{2}", text[i + 2:i + 4]):
				result.append(int(text[i + 2:i + 4], 16))
				i += 4
				continue
			if nxt in SIMPLE_ESCAPES:
				result.append(SIMPLE_ESCAPES[nxt])
				i += 2
				continue
		result.extend(c.encode("utf-8"))
		i += 1
	return bytes(result)


def ssidName(ssid):
	"""bytes -> text for the screen; invalid UTF-8 is shown with the replacement character"""
	return ssid.decode("utf-8", "replace")


def isHiddenSsid(ssid):
	return not ssid or not ssid.strip(b"\0")


def band(frequency):
	if 2412 <= frequency <= 2484:
		return "2.4"
	if 5170 <= frequency <= 5895:
		return "5"
	if 5955 <= frequency <= 7115:
		return "6"
	return ""


def signalPercent(signal):
	"""dBm (negative, nl80211) or quality (positive, some wext drivers) -> 0..100 for display"""
	if signal > 0:
		return min(100, signal)
	return min(100, max(0, 2 * (signal + 100)))


def procWirelessLevel(iface, path="/proc/net/wireless"):
	"""signal level in dBm of the network the interface is joined to, from /proc/net/wireless (the drivers that do not
	answer wpa_cli signal_poll still fill it); None when unknown: no row, not joined (-256 or 0), not readable"""
	try:
		with open(path, "r", encoding="utf-8") as f:
			rows = f.read(16384).splitlines()[2:]
	except (IOError, OSError, UnicodeDecodeError):
		return None
	for row in rows:
		name, sep, rest = row.partition(":")
		if not sep or name.strip() != iface:
			continue
		fields = rest.split()
		if len(fields) < 3:
			return None
		try:
			level = int(float(fields[2].rstrip(".")))
		except ValueError:
			return None
		if 128 <= level <= 255:
			level -= 256   # an 8 bit value written without sign
		if level <= -256 or level == 0 or level > 0 or level < -120:
			return None
		return level
	return None


def securityFromFlags(flags):
	tokens = FLAG_RX.findall(flags)
	wpa_tokens = [x for x in tokens if x.startswith(("WPA-", "WPA2-", "RSN-"))]
	if any("EAP" in x for x in wpa_tokens):
		return SECURITY_ENTERPRISE
	sae = any("SAE" in x for x in wpa_tokens)
	psk_rsn = any(x.startswith(("WPA2-", "RSN-")) and "PSK" in x.replace("PSK-SHA256", "PSK") for x in wpa_tokens)
	psk_wpa = any(x.startswith("WPA-") and "PSK" in x for x in wpa_tokens)
	if sae and (psk_rsn or psk_wpa):
		return SECURITY_WPA2_WPA3
	if sae:
		return SECURITY_WPA3
	if psk_rsn:
		return SECURITY_WPA2
	if psk_wpa:
		return SECURITY_WPA
	if any("OWE" in x for x in tokens):
		return SECURITY_OWE
	if "WEP" in tokens:
		return SECURITY_WEP
	return SECURITY_OPEN


def parseScanResults(text):
	"""wpa_cli scan_results -> networks grouped by SSID and security, strongest first.
	Hidden networks, ad-hoc and mesh entries are left out."""
	groups = {}
	for line in text.splitlines():
		if not line or line.startswith("bssid"):
			continue
		fields = line.split("\t", 4)
		if len(fields) != 5:
			continue
		bssid, frequency, signal, flags, escaped = fields
		try:
			frequency = int(frequency)
			signal = int(signal)
		except ValueError:
			continue
		if "[IBSS]" in flags or "[MESH]" in flags:
			continue
		ssid = decodeSsid(escaped)
		if isHiddenSsid(ssid):
			continue
		security = securityFromFlags(flags)
		key = (ssid, security)
		network = groups.get(key)
		if network is None:
			network = groups[key] = {"ssid": ssid, "name": ssidName(ssid), "security": security,
				"signal": signal, "bssid": bssid, "bands": set()}
		elif signal > network["signal"]:
			network["signal"] = signal
			network["bssid"] = bssid
		if band(frequency):
			network["bands"].add(band(frequency))
	networks = []
	for network in groups.values():
		network["bands"] = sorted(network["bands"], key=float)
		network["percent"] = signalPercent(network["signal"])
		networks.append(network)
	networks.sort(key=lambda x: (-x["percent"], x["name"].lower()))
	return networks


def parseStatus(text):
	"""wpa_cli status (key=value lines) -> dict"""
	status = {}
	for line in text.splitlines():
		key, sep, value = line.partition("=")
		if sep:
			status[key.strip()] = value.strip()
	return status


def pskHex(password, ssid):
	"""WPA/WPA2 pre-shared key: PBKDF2-HMAC-SHA1(password, SSID, 4096, 32), as wpa_passphrase computes it"""
	return hashlib.pbkdf2_hmac("sha1", password.encode("utf-8"), ssid, 4096, 32).hex()


def checkPassword(security, password):
	"""None if the password can be used, else a short reason (English, translated by the screen)"""
	if security in (SECURITY_OPEN, SECURITY_OWE):
		return None
	if security not in SUPPORTED_SECURITY:
		return "This kind of network security is not supported"
	if security in (SECURITY_WPA, SECURITY_WPA2) and HEX64_RX.match(password):
		return None
	if any(ord(c) < 32 or ord(c) > 126 for c in password):
		return "The password may only contain letters, digits and the usual signs"
	if len(password) < 8:
		return "The password must have at least 8 characters"
	if security in (SECURITY_WPA, SECURITY_WPA2) and len(password) > 63:
		return "The password may have at most 63 characters"
	if security in (SECURITY_WPA2_WPA3, SECURITY_WPA3) and ("\"" in password or "\\" in password):
		# SAE keeps the password as a quoted string in the file
		return "For WPA3 the password may not contain quotes or backslashes"
	return None


def networkBlock(ssid, security, password="", hidden=False):
	"""network={...} block for wpa_supplicant.conf; the SSID is written as hex (exact bytes)"""
	reason = checkPassword(security, password)
	if reason:
		raise ValueError(reason)
	lines = ["network={", "\tssid=%s" % ssid.hex()]
	if hidden:
		lines.append("\tscan_ssid=1")
	if security == SECURITY_OPEN:
		lines.append("\tkey_mgmt=NONE")
	elif security == SECURITY_OWE:
		lines += ["\tkey_mgmt=OWE", "\tieee80211w=2"]
	else:
		psk = password.lower() if HEX64_RX.match(password) else None
		if security in (SECURITY_WPA, SECURITY_WPA2):
			lines += ["\tkey_mgmt=WPA-PSK", "\tproto=RSN WPA", "\tpsk=%s" % (psk or pskHex(password, ssid))]
		elif security == SECURITY_WPA2_WPA3:
			lines += ["\tkey_mgmt=SAE WPA-PSK WPA-PSK-SHA256", "\tieee80211w=1",
				"\tpsk=%s" % pskHex(password, ssid), "\tsae_password=\"%s\"" % password]
		elif security == SECURITY_WPA3:
			lines += ["\tkey_mgmt=SAE", "\tieee80211w=2", "\tsae_password=\"%s\"" % password]
	lines.append("}")
	return "\n".join(lines) + "\n"


def ssidFromConfValue(value):
	value = value.strip()
	if len(value) >= 2 and value[0] == "\"" and value[-1] == "\"":
		return value[1:-1].encode("utf-8")
	if value.startswith("P\"") and value.endswith("\""):
		return decodeSsid(value[2:-1])
	try:
		return bytes.fromhex(value)
	except ValueError:
		return None


def parseConf(text):
	"""wpa_supplicant.conf -> (global lines, [(ssid bytes or None, block text)])"""
	header = []
	blocks = []
	current = None
	ssid = None
	for line in text.splitlines():
		stripped = line.strip()
		if current is None:
			if stripped.startswith("network={"):
				current = [line]
				ssid = None
			elif stripped:
				header.append(line)
			continue
		current.append(line)
		if stripped.startswith("ssid="):
			ssid = ssidFromConfValue(stripped[5:])
		if stripped == "}":
			blocks.append((ssid, "\n".join(current) + "\n"))
			current = None
	if current is not None:
		# a block without its closing brace is kept as it was
		blocks.append((ssid, "\n".join(current) + "\n}\n"))
	return header, blocks


def isWildcardBlock(ssid, block):
	"""a network={...} block without ssid= and without bssid= matches ANY network: the default file of the
	wpa-supplicant package has one with key_mgmt=NONE, so the supplicant joined any open network in range (even when
	it was started only to search). Our screens never write such a block; it is dropped when the file is written."""
	if ssid is not None:
		return False
	return not any(line.strip().startswith("bssid=") for line in block.splitlines())


def cleanConf(text):
	"""(text without the blocks that match any network, how many were dropped)"""
	header, blocks = parseConf(text)
	kept = [(s, b) for s, b in blocks if not isWildcardBlock(s, b)]
	if len(kept) == len(blocks):
		return text, 0
	return "\n".join(header) + "\n\n" + "\n".join(b for s, b in kept), len(blocks) - len(kept)


def savedNetworks(text):
	"""the SSIDs (bytes) of the saved networks, in the order of the file, without the blocks that match any network
	and without the ones switched off (disabled=1)"""
	rez = []
	for ssid, block in parseConf(text)[1]:
		if ssid is None or ssid in rez:
			continue
		if any(line.strip().replace(" ", "") == "disabled=1" for line in block.splitlines()):
			continue
		rez.append(ssid)
	return rez


def updateConf(text, ssid, block, country=None):
	"""replaces the block for this SSID (or adds it); other networks and settings stay as they were, except the blocks
	that match any network (isWildcardBlock)"""
	header, blocks = parseConf(text)
	if not any(line.strip().startswith("ctrl_interface=") for line in header):
		header.insert(0, "ctrl_interface=%s" % CTRL_INTERFACE)
	if country and COUNTRY_RX.match(country):
		header = [line for line in header if not line.strip().startswith("country=")]
		header.append("country=%s" % country)
	blocks = [(s, b) for s, b in blocks if s != ssid and not isWildcardBlock(s, b)] + [(ssid, block)]
	return "\n".join(header) + "\n\n" + "\n".join(b for s, b in blocks)


def removeNetwork(text, ssid):
	header, blocks = parseConf(text)
	return "\n".join(header) + "\n\n" + "\n".join(b for s, b in blocks if s != ssid and not isWildcardBlock(s, b))


def writeConfAtomic(path, text):
	"""written to a temporary file (mode 600) and moved over the old one; True on success"""
	tmp = path + ".tmp"
	try:
		fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
		try:
			if hasattr(os, "fchmod"):
				os.fchmod(fd, 0o600)
			os.write(fd, text.encode("utf-8"))
			os.fsync(fd)
		finally:
			os.close(fd)
		os.replace(tmp, path)
		return True
	except (IOError, OSError) as err:
		print("[WlanTools] writing %s failed: %s" % (path, err.strerror or err))
		try:
			os.unlink(tmp)
		except OSError:
			pass
		return False


def getWlanDriver(iface, sysfs="/sys/class/net", procWireless="/proc/net/wireless"):
	"""nl80211 for cfg80211 drivers, wext for wireless extensions only, None if not a WiFi interface"""
	base = os.path.join(sysfs, iface)
	if os.path.exists(os.path.join(base, "phy80211")):
		return "nl80211"
	if os.path.isdir(os.path.join(base, "wireless")):
		return "wext"
	try:
		with open(procWireless, encoding="utf-8") as f:
			for line in f:
				if line.strip().startswith(iface + ":"):
					return "wext"
	except (IOError, OSError):
		pass
	return None


def interfaceLines(driver, conf=SUPPLICANT_CONF):
	"""lines for the wlan stanza in /etc/network/interfaces; udhcpc keeps trying while WiFi associates"""
	drivers = "nl80211,wext" if driver == "nl80211" else "wext"
	return "\twpa-conf %s\n\twpa-driver %s\n\tudhcpc_opts -b\n" % (conf, drivers)
