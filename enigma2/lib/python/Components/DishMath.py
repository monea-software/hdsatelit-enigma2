# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Dish motor math for HDSatelit Image: USALS angle and DiSEqC 1.2 positioner commands.
# The angle follows lib/dvb/rotor_calc.cpp and the byte encoding follows
# lib/dvb/sec.cpp, so a motor gets the same command from our screens as from enigma2 on a channel change.
# Command bytes: Eutelsat DiSEqC bus functional specification 4.2. No enigma imports: tested on a PC.
import math

FRAMING = 0xE0          # command from master, no reply, first transmission
ADDRESS = 0x31          # polar / azimuth positioner

HALT = 0x60
LIMITS_OFF = 0x63
LIMIT_EAST = 0x66
LIMIT_WEST = 0x67
DRIVE_EAST = 0x68
DRIVE_WEST = 0x69
STORE = 0x6A
GOTO = 0x6B
GOTO_ANGLE = 0x6E

EARTH_FLATTENING = 1.00 / 298.257
SATELLITE_RADIUS = 42164.57     # km from earth centre
EARTH_RADIUS = 6378.14          # km, equatorial
GOTOX_TABLE = (0x00, 0x02, 0x03, 0x05, 0x06, 0x08, 0x0A, 0x0B, 0x0D, 0x0E)


def roundHalfAway(value):
	"""C round(): halves go away from zero (Python round() goes to the even number)"""
	return int(math.floor(abs(value) + 0.5)) * (1 if value >= 0 else -1)


def orbitalToDegrees(orbital_position):
	"""enigma2 orbital position (tenths, 0..3599, west stored as 3600 - x) -> degrees, east positive"""
	value = orbital_position % 3600
	return value / 10.0 if value <= 1800 else (value - 3600) / 10.0


def _siteVectors(sat_lon, site_lat, site_lon):
	lat = math.radians(site_lat)
	sin_lat, cos_lat = math.sin(lat), math.cos(lat)
	f = EARTH_FLATTENING
	station = EARTH_RADIUS / math.sqrt(1.0 - f * (2.0 - f) * sin_lat * sin_lat)
	ra = station * cos_lat
	rz = station * (1.0 - f) * (1.0 - f) * sin_lat
	delta = math.radians(sat_lon - site_lon)
	rx = SATELLITE_RADIUS * math.cos(delta) - ra
	ry = SATELLITE_RADIUS * math.sin(delta)
	north = -rx * sin_lat - rz * cos_lat
	zenith = rx * cos_lat - rz * sin_lat
	return north, zenith, ry


def _secLongitudes(sat_lon, site_lat, site_lon):
	"""the longitudes as sec.cpp passes them: satellite 0..360 east, site west as 360 - x"""
	return sat_lon % 360.0, site_lat, site_lon % 360.0


def elevation(sat_lon, site_lat, site_lon):
	"""observed elevation in degrees (with refraction, as rotor_calc.cpp); -99 when the satellite is far below"""
	north, zenith, ry = _siteVectors(*_secLongitudes(sat_lon, site_lat, site_lon))
	geometric = math.degrees(math.atan(zenith / math.sqrt(north * north + ry * ry)))
	if geometric > 10.2:
		observed = geometric + 0.01617 * (math.cos(math.radians(abs(geometric))) / math.sin(math.radians(abs(geometric))))
	else:
		x = abs(geometric + 0.589)
		refraction = abs(0.58804392 - 0.17941557 * x + 0.29906946E-1 * x * x - 0.25187400E-2 * x ** 3 + 0.82622101E-4 * x ** 4)
		observed = geometric + refraction
	if zenith < -3000:
		observed = -99.0
	return observed


def azimuth(sat_lon, site_lat, site_lon):
	"""azimuth in degrees from north, clockwise (as rotor_calc.cpp)"""
	north, zenith, ry = _siteVectors(*_secLongitudes(sat_lon, site_lat, site_lon))
	if north < 0:
		return 180.0 + math.degrees(math.atan(ry / north))
	value = 360.0 + math.degrees(math.atan(ry / north))
	return value - math.floor(value / 360.0) * 360.0


def hourAngle(sat_lon, site_lat, site_lon):
	"""polar mount hour angle in degrees (calcSatHourangle in rotor_calc.cpp)"""
	az = azimuth(sat_lon, site_lat, site_lon)
	el = elevation(sat_lon, site_lat, site_lon)
	lat = math.radians(site_lat)
	a = -math.cos(math.radians(el)) * math.sin(math.radians(az))
	b = math.sin(math.radians(el)) * math.cos(lat) - math.cos(math.radians(el)) * math.sin(lat) * math.cos(math.radians(az))
	value = 180.0 + math.degrees(math.atan(a / b))
	if az > 270:
		value = (value - 180.0) + 360.0
		if value > 360:
			value = 360.0 - (value - 360.0)
	if az < 90:
		value = 180.0 - value
	return value


def gotoAngleValue(sat_lon, site_lat, site_lon):
	"""the 16 bit value sent after 6E, exactly as sec.cpp builds it (east positive longitudes, north positive latitude)"""
	sat, lat, lon = _secLongitudes(sat_lon, site_lat, site_lon)
	angle = hourAngle(sat, lat, lon)
	if lat >= 0:
		tmp = roundHalfAway(abs(180.0 - angle) * 10.0)
		value = (tmp // 10) * 0x10 + GOTOX_TABLE[tmp % 10]
		value |= 0xE000 if angle < 180 else 0xD000
	elif angle < 180:
		tmp = roundHalfAway(abs(angle) * 10.0)
		value = ((tmp // 10) * 0x10 + GOTOX_TABLE[tmp % 10]) | 0xD000
	else:
		tmp = roundHalfAway(abs(360.0 - angle) * 10.0)
		value = ((tmp // 10) * 0x10 + GOTOX_TABLE[tmp % 10]) | 0xE000
	return value & 0xFFFF


def motorAngle(sat_lon, site_lat, site_lon):
	"""angle the motor turns to, for display: degrees, positive = east, negative = west (from the sent value)"""
	value = gotoAngleValue(sat_lon, site_lat, site_lon)
	whole = (value >> 4) & 0xFF
	tenth = GOTOX_TABLE.index(value & 0x0F) if (value & 0x0F) in GOTOX_TABLE else 0
	degrees = whole + tenth / 10.0
	return degrees if (value & 0xF000) == 0xE000 else -degrees


# --- commands (lists of bytes)

def halt():
	return [FRAMING, ADDRESS, HALT]


def limitsOff():
	return [FRAMING, ADDRESS, LIMITS_OFF]


def limitEast():
	return [FRAMING, ADDRESS, LIMIT_EAST]


def limitWest():
	return [FRAMING, ADDRESS, LIMIT_WEST]


def limitsOn():
	"""store 00 only switches the soft limits on again (spec 4.2 p. 20)"""
	return [FRAMING, ADDRESS, STORE, 0x00]


def store(position):
	if not 1 <= position <= 255:
		raise ValueError("stored positions are 1..255")
	return [FRAMING, ADDRESS, STORE, position]


def gotoStored(position):
	if not 0 <= position <= 255:
		raise ValueError("stored positions are 0..255 (0 = reference)")
	return [FRAMING, ADDRESS, GOTO, position]


def drive(east, seconds=None, steps=None):
	"""continuous drive (no argument), a time limit of 1..127 s, or 1..128 steps (signed byte, spec 4.2 p. 20)"""
	if seconds is not None and steps is not None:
		raise ValueError("either seconds or steps")
	if seconds is not None:
		if not 1 <= seconds <= 127:
			raise ValueError("seconds are 1..127")
		parameter = seconds
	elif steps is not None:
		if not 1 <= steps <= 128:
			raise ValueError("steps are 1..128")
		parameter = 0x100 - steps
	else:
		parameter = 0x00
	return [FRAMING, ADDRESS, DRIVE_EAST if east else DRIVE_WEST, parameter]


def gotoAngle(sat_lon, site_lat, site_lon):
	value = gotoAngleValue(sat_lon, site_lat, site_lon)
	return [FRAMING, ADDRESS, GOTO_ANGLE, value >> 8, value & 0xFF]


def toHex(command):
	"""format for eDVBDiseqcCommand.setCommandString"""
	return "".join("%02X" % byte for byte in command)


ALLOWED = {HALT: 3, LIMITS_OFF: 3, LIMIT_EAST: 3, LIMIT_WEST: 3, DRIVE_EAST: 4, DRIVE_WEST: 4, STORE: 4, GOTO: 4, GOTO_ANGLE: 5}


def isAllowed(command):
	"""only well formed positioner commands with our framing and address may be sent"""
	if len(command) < 3 or command[0] != FRAMING or command[1] != ADDRESS:
		return False
	if any(not 0 <= byte <= 255 for byte in command):
		return False
	length = ALLOWED.get(command[2])
	if length is None or len(command) != length:
		return False
	if command[2] == GOTO_ANGLE and (command[3] >> 4) not in (0xD, 0xE):
		return False
	return True


def isSafeOnly(command):
	"""what the test lock still allows: halt and switching the limits on"""
	return command in (halt(), limitsOn())
