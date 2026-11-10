# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com si hdsatelit.com
# SPDX-License-Identifier: GPL-2.0-only
import skin
from enigma import eLabel, ePoint, eSize, eTimer, eWidget
from .Renderer import Renderer


class RunningText(Renderer):
	"""Text decupat, cu o singura miscare comandata de timer."""

	GUI_WIDGET = eWidget
	_DEFAULTS = {
		"movetype": "running", "direction": "left", "step": 1,
		"steptime": 80, "startdelay": 5000, "repeat": 0,
		"always": 0, "wrap": 0, "startpoint": None,
	}

	def __init__(self):
		Renderer.__init__(self)
		self.label = None
		self.timer = eTimer()
		self.timer.callback.append(self._tick)
		self.onVisibilityChange.append(self._visibility)
		self._shown = True
		self._text = ""
		self._active = False
		self._options = self._DEFAULTS.copy()
		self.direction = "left"

	def postWidgetCreate(self, instance):
		self.label = eLabel(instance)
		self.label.setText(self._text)

	def preWidgetRemove(self, instance):
		self.timer.stop()
		self._active = False
		self.label = None

	def destroy(self):
		self.timer.stop()
		self._active = False
		self.timer.callback.remove(self._tick)
		Renderer.destroy(self)

	def _option(self, name, value):
		name = name.strip().lower()
		if name not in self._DEFAULTS and name != "nowrap":
			return False
		value = str(value).strip().lower()
		if name in ("movetype", "direction"):
			allowed = ("running", "swimming", "none") if name == "movetype" else ("left", "right", "top", "bottom")
			if value in allowed:
				self._options[name] = value
			return True
		if name in ("always", "wrap", "nowrap"):
			if value in ("1", "true", "yes", "on", "0", "false", "no", "off"):
				number = int(value in ("1", "true", "yes", "on"))
				self._options["wrap" if name == "nowrap" else name] = 1 - number if name == "nowrap" else number
			return True
		try:
			number = int(value)
		except (ValueError, TypeError, OverflowError):
			return True
		# Valorile gresite pastreaza implicitul, fara timer prea rapid.
		low, high = {
			"step": (1, 10000), "steptime": (1, 60000),
			"startdelay": (0, 3600000), "repeat": (0, 1000000),
			"startpoint": (-1000000, 1000000),
		}[name]
		if low <= number <= high:
			self._options[name] = number
		return True

	def applySkin(self, desktop, parent):
		self.timer.stop()
		self._options = self._DEFAULTS.copy()
		attributes = self.skinAttributes
		container, label = [], []
		for name, value in attributes or []:
			if name.lower() == "options":
				for part in str(value).replace(";", ",").split(","):
					key, separator, option = part.partition("=")
					if separator:
						self._option(key, option)
					elif key.strip().lower() in ("wrap", "nowrap"):
						self._option(key, "1")
			elif self._option(name, value):
				pass
			elif name in ("position", "size", "zPosition"):
				container.append((name, value))
			else:
				label.append((name, value))
				if name in ("backgroundColor", "transparent"):
					container.append((name, value))
		self.skinAttributes = container if attributes is not None else None
		try:
			result = Renderer.applySkin(self, desktop, parent)
		finally:
			self.skinAttributes = attributes
		if self.label is not None:
			skin.applyAllAttributes(self.label, desktop, label, parent.scale)
			self.changed((self.CHANGED_DEFAULT,), force=True)
		return result

	def changed(self, what, force=False):
		text = "" if what[0] == self.CHANGED_CLEAR else getattr(self.source, "text", self._text)
		if text is None:
			text = ""
		elif isinstance(text, bytes):
			text = text.decode("utf-8", "replace")
		elif not isinstance(text, str):
			text = str(text)
		if not force and text == self._text:
			return
		# SWIG nu accepta caractere Unicode surogat.
		text = "".join(char for char in text if not 0xD800 <= ord(char) <= 0xDFFF)
		if not force and text == self._text:
			return
		self._text = text
		self._layout()

	def _layout(self):
		self.timer.stop()
		self._active = False
		if self.instance is None or self.label is None:
			return
		self.label.setText(self._text)
		box = self.instance.size()
		width, height = box.width(), box.height()
		if width <= 0 or height <= 0:
			return
		self.label.setNoWrap(not self._options["wrap"])
		self.label.resize(eSize(width, height))
		measured = self.label.calculateSize()
		content_width = width if self._options["wrap"] else max(width, measured.width())
		content_height = max(height, measured.height())
		# Cutia copilului tine textul intreg. Parintele il decupeaza.
		self.label.resize(eSize(content_width, content_height))
		self.direction = self._options["direction"]
		self._horizontal = self.direction in ("left", "right")
		self._sign = -1 if self.direction in ("left", "top") else 1
		self._extent = width if self._horizontal else height
		self._content = measured.width() if self._horizontal else measured.height()
		self._content = max(1, self._content)
		self._low = min(0, self._extent - self._content)
		self._high = max(0, self._extent - self._content)
		self._position = self._low if self._sign > 0 else self._high
		if self._content <= self._extent and (not self._options["always"] or self._options["movetype"] == "none"):
			self._position = 0
		if self._options["startpoint"] is not None:
			lower, upper = (-self._content, self._extent)
			if self._options["movetype"] == "swimming":
				lower, upper = self._low, self._high
			self._position = max(lower, min(upper, self._options["startpoint"]))
		self._initial = self._position
		self._passes = self._turns = 0
		self._move()
		self._active = bool(self._text and self._options["movetype"] != "none" and
			(self._content > self._extent or self._options["always"]))
		if self._options["movetype"] == "swimming" and self._low == self._high:
			self._active = False
		if self._active and self._content < self._extent:
			self.label.resize(eSize(self._content if self._horizontal else content_width,
				content_height if self._horizontal else self._content))
		self._schedule(self._options["startdelay"])

	def _move(self):
		self.label.move(ePoint(self._position if self._horizontal else 0,
			0 if self._horizontal else self._position))

	def _schedule(self, delay):
		if self._active and self._shown and self.visible and self.instance is not None and self.instance.isVisible():
			self.timer.start(max(1, delay), True)

	def _tick(self):
		if not self._active or not self._shown or not self.visible or self.label is None or not self.instance.isVisible():
			return
		self._position += self._sign * self._options["step"]
		delay = self._options["steptime"]
		if self._options["movetype"] == "swimming":
			end = self._low if self._sign < 0 else self._high
			if (self._position - end) * self._sign >= 0:
				self._position = end
				self._sign = -self._sign
				self._turns += 1
				if self._turns % 2 == 0:
					self._passes += 1
				delay = self._options["startdelay"]
		else:
			end = -self._content if self._sign < 0 else self._extent
			if (self._position - end) * self._sign >= 0:
				self._passes += 1
				self._position = self._extent if self._sign < 0 else -self._content
				delay = self._options["startdelay"]
		if self._options["repeat"] and self._passes >= self._options["repeat"]:
			self._active = False
			self._position = self._initial
		self._move()
		self._schedule(delay)

	def _visibility(self, visible):
		self.timer.stop()
		if visible:
			self._schedule(self._options["startdelay"])

	def onShow(self):
		Renderer.onShow(self)
		self._shown = True
		self._schedule(self._options["startdelay"])

	def onHide(self):
		self._shown = False
		self.timer.stop()
		Renderer.onHide(self)
