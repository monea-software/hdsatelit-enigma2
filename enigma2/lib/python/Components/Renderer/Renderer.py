from Components.GUIComponent import GUIComponent
from Components.Element import Element

class Renderer(GUIComponent, Element):
	def __init__(self):
		Element.__init__(self)
		GUIComponent.__init__(self)

	def onShow(self):
		self.suspended = False

	def onHide(self):
		self.suspended = True

	# Link to the source with a single text request (TSR, MI7: Label and the text renderers of external skins). The
	# downstream link is made before the request, so when the first request raises (a skin converter that fails in
	# getText, for example one given an argument it does not know), the link is undone before the error goes up:
	# readSkin then skips the widget and nothing is left that the converter would call later (its Poll timer, from C++).
	# This is the end state of Element.connect, where the request came before connectDownstream (0.7.6 and OE-Alliance).
	# Only lists in RAM are touched.
	def connectSingleRequest(self, source):
		assert not self.SINGLE_SOURCE or self.source is None
		self.sources.append(source)
		self.source = source
		source.connectDownstream(self)
		try:
			self.changed((self.CHANGED_DEFAULT,))
		except Exception:
			undoDownstream(source, self)
			raise


def undoDownstream(source, element):
	"""Remove element from the downstream list of source without disconnectDownstream (that one would disconnect and
	destroy a converter left without downstream elements, which Element.connect never did)."""
	try:
		while element in source.downstream_elements:
			source.downstream_elements.remove(element)
		if source.master is element:
			source.master = None
	except Exception:
		pass
