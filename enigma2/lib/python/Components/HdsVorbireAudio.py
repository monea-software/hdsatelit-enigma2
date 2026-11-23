# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com & hdsatelit.com
# SPDX-License-Identifier: GPL-2.0-only
# Small ISO BMFF audio files from complete compressed frames, without recoding.
import struct
from Components import HdsRadioAnaliza as A


def box(kind, payload=b""):
	return struct.pack(">I4s", len(payload) + 8, kind) + payload


def full(kind, payload=b"", flags=0):
	return box(kind, struct.pack(">I", flags) + payload)


def ints(*values):
	return struct.pack(">" + "I" * len(values), *values)


class Biti(object):
	def __init__(self, data):
		self.n = int.from_bytes(data, "big")
		self.end = len(data) * 8
		self.pos = 0

	def get(self, n):
		if n < 0 or self.pos + n > self.end:
			raise ValueError("latm")
		self.pos += n
		return (self.n >> (self.end - self.pos)) & ((1 << n) - 1)

	def data(self, n):
		return self.get(n * 8).to_bytes(n, "big")


def latm(data):
	# One program/layer and frameLengthType 0, the normal broadcast LATM layout.
	samples, durations, asc, rate, channels = [], [], None, 0, 0
	i = 0
	while i + 3 <= len(data):
		n = A.lungime_loas(data, i)
		if not n or i + n > len(data):
			raise ValueError("latm")
		r = Biti(data[i + 3:i + n])
		if not r.get(1):
			if r.get(1) or not r.get(1) or r.get(6) or r.get(4) or r.get(3):
				raise ValueError("latm-config")
			start = r.pos
			aot = r.get(5)
			freq = r.get(4)
			rate = r.get(24) if freq == 15 else (A.FRECVENTE_AAC[freq] if freq < 13 else 0)
			channels = r.get(4)
			if aot in (5, 29):
				ext = r.get(4)
				if ext == 15:
					r.get(24)
				aot = r.get(5)
			if aot not in (1, 2, 3, 4) or not rate or not 1 <= channels <= 7 or r.get(1):
				raise ValueError("aac-config")
			if r.get(1):
				r.get(14)
			if r.get(1):
				raise ValueError("aac-extension")
			bits = r.pos - start
			value = (r.n >> (r.end - r.pos)) & ((1 << bits) - 1)
			new_asc = (value << ((8 - bits % 8) % 8)).to_bytes((bits + 7) // 8, "big")
			if asc is not None and new_asc != asc:
				raise ValueError("aac-change")
			asc = new_asc
			if r.get(3):
				raise ValueError("latm-frame")
			r.get(8)
			if r.get(1):
				while r.get(1):
					r.get(8)
				r.get(8)
			if r.get(1):
				r.get(8)
		if asc is None:
			raise ValueError("latm-config")
		length = 0
		while True:
			v = r.get(8)
			length += v
			if v != 255:
				break
		samples.append(r.data(length))
		durations.append(1024)
		i += n
	return samples, durations, rate, channels, asc


def impacheteaza(data, codec):
	samples, durations = [], []
	if codec == "loas":
		samples, durations, rate, channels, asc = latm(data)
		codec = "adts"
	else:
		i, asc, first = 0, None, None
		reader = {"adts": A.antet_adts, "ac3": A.antet_ac3, "eac3": A.antet_eac3}[codec]
		while i < len(data):
			h = reader(data, i)
			if not h or i + h[0] > len(data):
				raise ValueError("frame")
			if first is None:
				first = h
			if codec == "adts":
				rate, channels = h[1:3]
				if not 1 <= channels <= 7:
					raise ValueError("aac-channels")
				if (rate, channels, h[3]) != (first[1], first[2], first[3]) or data[i + 6] & 3:
					raise ValueError("aac-config")
				freq = A.FRECVENTE_AAC.index(rate)
				asc = ((h[3] << 11) | (freq << 7) | (channels << 3)).to_bytes(2, "big")
				head = 7 if data[i + 1] & 1 else 9
				samples.append(data[i + head:i + h[0]])
				durations.append(1024)
			else:
				rate, channels = h[2], h[3] + h[4]
				if (rate, channels) != (first[2], first[3] + first[4]):
					raise ValueError("ac3-config")
				samples.append(data[i:i + h[0]])
				durations.append(256 * h[7] if codec == "eac3" else 1536)
			i += h[0]
	if not samples or rate > 65535:
		raise ValueError("audio")
	if codec == "adts":
		specific = b"\x05" + bytes([len(asc)]) + asc
		decoder = b"\x40\x15\x00\x00\x00" + ints(256000, 192000) + specific
		es = b"\x00\x01\x00\x04" + bytes([len(decoder)]) + decoder + b"\x06\x01\x02"
		extra, tag = full(b"esds", b"\x03" + bytes([len(es)]) + es), b"mp4a"
	elif codec == "ac3":
		h = first
		value = ((data[4] >> 6) << 22) | (h[5] << 17) | ((data[5] & 7) << 14) | (h[6] << 11) | (h[4] << 10) | (((data[4] & 63) >> 1) << 5)
		extra, tag = box(b"dac3", value.to_bytes(3, "big")), b"ac-3"
	else:
		h = first
		# One independent substream. Dependent extensions need channel-location metadata.
		if not h[6] or any(not A.antet_eac3(s, 0)[6] for s in samples):
			raise ValueError("eac3-dependent")
		value = ((data[4] >> 6) << 22) | (h[5] << 17) | (h[8] << 9) | (h[4] << 8)
		extra, tag = box(b"dec3", struct.pack(">H", min(h[1], 8191) << 3) + value.to_bytes(3, "big")), b"ec-3"
	entry = box(tag, bytes(6) + struct.pack(">HHHIHHHHI", 1, 0, 0, 0, channels, 16, 0, 0, rate << 16) + extra)
	ftyp = box(b"ftyp", b"isom" + ints(512) + b"isomiso2mp41")
	mdat = box(b"mdat", b"".join(samples))
	matrix = ints(0x10000, 0, 0, 0, 0x10000, 0, 0, 0, 0x40000000)
	duration = sum(durations)
	millis = int(duration * 1000 / rate)
	mvhd = full(b"mvhd", ints(0, 0, 1000, millis, 0x10000) + b"\x01\x00" + bytes(10) + matrix + bytes(24) + ints(2))
	tkhd = full(b"tkhd", ints(0, 0, 1, 0, millis) + bytes(8) + struct.pack(">HHHH", 0, 0, 0x100, 0) + matrix + ints(0, 0), 7)
	mdhd = full(b"mdhd", ints(0, 0, rate, duration) + struct.pack(">HH", 0x55c4, 0))
	hdlr = full(b"hdlr", ints(0) + b"soun" + bytes(12) + b"HD Satelit\0")
	stts = full(b"stts", ints(len(durations)) + b"".join(ints(1, n) for n in durations))
	stsz = full(b"stsz", ints(0, len(samples)) + b"".join(ints(len(s)) for s in samples))
	stco = full(b"stco", ints(1, len(ftyp) + 8))
	stsc = full(b"stsc", ints(1, 1, len(samples), 1))
	stbl = box(b"stbl", full(b"stsd", ints(1) + entry) + stts + stsc + stsz + stco)
	dinf = box(b"dinf", full(b"dref", ints(1) + full(b"url ", flags=1)))
	minf = box(b"minf", full(b"smhd", bytes(4)) + dinf + stbl)
	moov = box(b"moov", mvhd + box(b"trak", tkhd + box(b"mdia", mdhd + hdlr + minf)))
	# The index precedes audio, so a service can read the upload without seeking.
	moov = moov.replace(stco, full(b"stco", ints(1, len(ftyp) + len(moov) + 8)), 1)
	return ftyp + moov + mdat
