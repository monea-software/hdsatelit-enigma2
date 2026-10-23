# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Block device names: which disk a partition belongs to and which disk holds the running system.
No enigma imports, so it can be tested on a PC."""
import re

PARTITION_P_RX = re.compile(r"^(mmcblk[0-9]+|nvme[0-9]+n[0-9]+)p[0-9]+$")
SPECIAL_MMC_RX = re.compile(r"^mmcblk[0-9]+(rpmb|boot[0-9]+)$")

def diskOfPartition(name):
	"""mmcblk0p10 -> mmcblk0, nvme0n1p2 -> nvme0n1, sda1 -> sda; a disk name is returned unchanged"""
	m = PARTITION_P_RX.match(name)
	if m:
		return m.group(1)
	if name.startswith("mmcblk") or name.startswith("nvme"):
		return name
	return name.rstrip("0123456789")

def isSpecialMmcArea(name):
	"""eMMC boot and replay protected areas: never storage for recordings"""
	return SPECIAL_MMC_RX.match(name) is not None

def rootDeviceName(cmdline, mounts):
	"""disk holding the system: root=/dev/... from the kernel command line, else the device mounted on /
	mounts is a list of (source, mountpoint) pairs"""
	for arg in cmdline.split():
		if arg.startswith("root=/dev/"):
			return diskOfPartition(arg[len("root=/dev/"):])
	for source, mountpoint in mounts:
		if mountpoint == "/" and source.startswith("/dev/"):
			return diskOfPartition(source[len("/dev/"):])
	return None
