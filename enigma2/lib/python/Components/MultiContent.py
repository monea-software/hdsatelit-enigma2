from enigma import eListboxPythonMultiContent, RT_HALIGN_LEFT, RT_VALIGN_TOP

def MultiContentTemplateColor(n): return 0xff000000 | n

def _i(valoare):
	"""o impartire in Python 3 da numar cu virgula; lista cere intregi"""
	return int(valoare) if isinstance(valoare, float) else valoare

def MultiContentEntryText(pos = (0, 0), size = (0, 0), font = 0, flags = RT_HALIGN_LEFT | RT_VALIGN_TOP, text = "", color = None, color_sel = None, backcolor = None, backcolor_sel = None, border_width = None, border_color = None):
	return (eListboxPythonMultiContent.TYPE_TEXT, _i(pos[0]), _i(pos[1]), _i(size[0]), _i(size[1]), font, flags, text, color, color_sel, backcolor, backcolor_sel, border_width, border_color)

# scale_flags este numele cerut de pluginuri pentru aceleasi fanioane ale pozelor din lista.
def MultiContentEntryPixmap(pos = (0, 0), size = (0, 0), png = None, backcolor = None, backcolor_sel = None, flags = 0, scale_flags = None):
	return (eListboxPythonMultiContent.TYPE_PIXMAP, _i(pos[0]), _i(pos[1]), _i(size[0]), _i(size[1]), png, backcolor, backcolor_sel, flags if scale_flags is None else flags | scale_flags)

def MultiContentEntryPixmapAlphaTest(pos = (0, 0), size = (0, 0), png = None, backcolor = None, backcolor_sel = None, flags = 0, scale_flags = None):
	return (eListboxPythonMultiContent.TYPE_PIXMAP_ALPHATEST, _i(pos[0]), _i(pos[1]), _i(size[0]), _i(size[1]), png, backcolor, backcolor_sel, flags if scale_flags is None else flags | scale_flags)

def MultiContentEntryPixmapAlphaBlend(pos = (0, 0), size = (0, 0), png = None, backcolor = None, backcolor_sel = None, flags = 0, scale_flags = None):
	return (eListboxPythonMultiContent.TYPE_PIXMAP_ALPHABLEND, _i(pos[0]), _i(pos[1]), _i(size[0]), _i(size[1]), png, backcolor, backcolor_sel, flags if scale_flags is None else flags | scale_flags)

def MultiContentEntryRectangle(pos = (0, 0), size = (0, 0), backgroundColor = None, backgroundColorSelected = None, borderWidth = None, borderColor = None, borderColorSelected = None, cornerRadius = 0, cornerEdges = 15):
	"""Un dreptunghi plin, cu chenar: un text gol. Colturile rotunjite nu se deseneaza."""
	return (eListboxPythonMultiContent.TYPE_TEXT, _i(pos[0]), _i(pos[1]), _i(size[0]), _i(size[1]), 0, RT_HALIGN_LEFT | RT_VALIGN_TOP, "", None, None, backgroundColor, backgroundColorSelected, borderWidth, borderColor)

def MultiContentEntryProgress(pos = (0, 0), size = (0, 0), percent = None, borderWidth = None, foreColor = None, backColor = None, backColorSelected = None):
	return (eListboxPythonMultiContent.TYPE_PROGRESS, _i(pos[0]), _i(pos[1]), _i(size[0]), _i(size[1]), percent, borderWidth, foreColor, backColor, backColorSelected)

