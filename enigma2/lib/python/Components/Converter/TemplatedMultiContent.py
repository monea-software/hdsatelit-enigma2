# Modificat de moneasoftware.com si hdsatelit.com, 2026
from Components.Converter.StringList import StringList

class TemplatedMultiContent(StringList):
	"""Turns a python tuple list into a multi-content list which can be used in a listbox renderer."""
	def __init__(self, args):
		StringList.__init__(self, args)
		from Components.HdsMarireText import procent
		# Capture the screen's text size once; theme adapters supply absolute geometry.
		self._textPercent = procent()
		from enigma import eListboxPythonMultiContent, gFont, RT_HALIGN_LEFT, RT_HALIGN_CENTER, RT_HALIGN_RIGHT, RT_VALIGN_TOP, RT_VALIGN_CENTER, RT_VALIGN_BOTTOM, RT_WRAP
		from Components.MultiContent import MultiContentEntryText, MultiContentEntryPixmap, MultiContentEntryPixmapAlphaTest, MultiContentEntryPixmapAlphaBlend, MultiContentTemplateColor, MultiContentEntryProgress
		l = locals()
		del l["self"] # cleanup locals a bit
		del l["args"]

		self.active_style = None
		self.template = eval(args, {}, l)
		assert "fonts" in self.template
		assert "itemHeight" in self.template
		assert "template" in self.template or "templates" in self.template
		assert "template" in self.template or "default" in self.template["templates"] # we need to have a default template

		if not "template" in self.template: # default template can be ["template"] or ["templates"]["default"]
			self.template["template"] = self.template["templates"]["default"][1]
			self.template["itemHeight"] = self.template["templates"]["default"][0]

	def changed(self, what):
		if not self.content:
			from enigma import eListboxPythonMultiContent
			self.content = eListboxPythonMultiContent()

			# also setup fonts (also given by source)
			index = 0
			for f in self.template["fonts"]:
				if getattr(self, "_textPercent", 100) != 100:
					from Components.HdsMarireText import fontCod
					f = fontCod(f.family, f.pointSize, self._textPercent)
				self.content.setFont(index, f)
				index += 1

		# if only template changed, don't reload list
		if what[0] == self.CHANGED_SPECIFIC and what[1] == "style":
			pass
		elif self.source:
			self.content.setList(self.source.list)

		self.setTemplate()
		self.downstream_elements.changed(what)
		self._fitRows()

	def doSuspend(self, suspended):
		if not suspended:
			self._fitRows()

	def _fitRows(self):
		# The widget exists on show, after its skin size has been applied.
		if getattr(self, "_textPercent", 100) <= 100 or not self.content or not self.source:
			return
		from enigma import eListbox, eSize
		for renderer in self.downstream_elements:
			instance = getattr(renderer, "instance", None)
			if instance is None or not hasattr(instance, "setContent"):
				continue
			size = instance.size()
			previous = getattr(renderer, "_hdsTemplateHeight", None)
			original = previous[1] if previous and previous[0] is instance and previous[2] == size.height() else size.height()
			height = original
			orientation = getattr(instance, "getOrientation", None)
			vertical = orientation is None or orientation() == getattr(eListbox, "orVertical", 1)
			if vertical and not getattr(self, "_itemWidthApplied", False):
				row = self.content.getItemSize().height()
				if original >= row:
					height = original // row * row
			renderer._hdsTemplateHeight = (instance, original, height)
			if height != size.height():
				instance.resize(eSize(size.width(), height))

	def setTemplate(self):
		if self.source:
			style = self.source.style

			if style == self.active_style and getattr(self, "_templateApplied", False):
				return

			# if skin defined "templates", that means that it defines multiple styles in a dict. template should still be a default
			templates = self.template.get("templates")
			template = self.template.get("template")
			itemheight = self.template["itemHeight"]
			selectionEnabled = self.template.get("selectionEnabled", True)
			scrollbarMode = self.template.get("scrollbarMode", "showOnDemand")

			if templates and style and style in templates: # if we have a custom style defined in the source, and different templates in the skin, look it up
				template = templates[style][1]
				itemheight = templates[style][0]
				if len(templates[style]) > 2:
					selectionEnabled = templates[style][2]
				if len(templates[style]) > 3:
					scrollbarMode = templates[style][3]

			# Resolve a grid cell before calling the native integer-only setters.
			itemwidth = self.template.get("itemWidth")
			if isinstance(itemheight, (tuple, list)):
				itemwidth, itemheight = itemheight
			percent = getattr(self, "_textPercent", 100)
			if percent != 100:
				# Always derive a fresh view from the original template, never the last style.
				# A vertical list keeps its column widths; a sized grid cell grows in both axes.
				horizontal = percent if itemwidth else 100
				template = [tuple(entry[:1]) + (entry[1] * horizontal // 100, entry[2] * percent // 100,
					entry[3] * horizontal // 100, entry[4] * percent // 100) + tuple(entry[5:]) for entry in template]
				itemheight = max(1, itemheight * percent // 100)
				if itemwidth:
					itemwidth = max(1, itemwidth * percent // 100)
			self.content.setTemplate(template)
			self.content.setItemHeight(itemheight)
			if itemwidth and hasattr(self.content, "setItemWidth"):
				self.content.setItemWidth(int(itemwidth))
				self._itemWidthApplied = True
			elif getattr(self, "_itemWidthApplied", False):
				self.content.setItemWidth(0)
				self._itemWidthApplied = False
			self.selectionEnabled = selectionEnabled
			self.scrollbarMode = scrollbarMode
			self.active_style = style
			self._templateApplied = True
