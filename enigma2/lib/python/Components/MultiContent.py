from enigma import eListboxPythonMultiContent, RT_HALIGN_LEFT, RT_VALIGN_TOP

def MultiContentTemplateColor(n): return 0xff000000 | n

def _i(valoare):
	"""o impartire in Python 3 da numar cu virgula; lista cere intregi"""
	return int(valoare) if isinstance(valoare, float) else valoare

def _c(culoare):
	"""O culoare data ca text ("#00ff0000" sau numele unei culori din tema), cum o primesc si alte imagini, devine numarul
	cerut de desenarea listei; numerele si None raman cum sunt. O culoare pe care tema n-o stie: None (culoarea listei)."""
	if not isinstance(culoare, str):
		return culoare
	try:
		from skin import parseColor
		return parseColor(culoare).argb()
	except Exception as e:
		print("[MultiContent] culoarea %r nu se poate citi: %s" % (culoare, e))
		return None

# cornerRadius, cornerEdges, textBColor, textBWidth: le dau temele si pluginurile externe; desenarea din imagine nu le stie
# inca, sunt primite si lasate deoparte, iar tuplul trimis listei e acelasi ca fara ele
def MultiContentEntryText(pos = (0, 0), size = (0, 0), font = 0, flags = RT_HALIGN_LEFT | RT_VALIGN_TOP, text = "", color = None, color_sel = None, backcolor = None, backcolor_sel = None, border_width = None, border_color = None, cornerRadius = None, cornerEdges = None, textBColor = None, textBWidth = None):
	return (eListboxPythonMultiContent.TYPE_TEXT, _i(pos[0]), _i(pos[1]), _i(size[0]), _i(size[1]), font, flags, text, _c(color), _c(color_sel), _c(backcolor), _c(backcolor_sel), border_width, _c(border_color))

# scale_flags este numele cerut de pluginuri pentru aceleasi fanioane ale pozelor din lista.
def MultiContentEntryPixmap(pos = (0, 0), size = (0, 0), png = None, backcolor = None, backcolor_sel = None, flags = 0, scale_flags = None, cornerRadius = None, cornerEdges = None):
	return (eListboxPythonMultiContent.TYPE_PIXMAP, _i(pos[0]), _i(pos[1]), _i(size[0]), _i(size[1]), png, _c(backcolor), _c(backcolor_sel), flags if scale_flags is None else flags | scale_flags)

def MultiContentEntryPixmapAlphaTest(pos = (0, 0), size = (0, 0), png = None, backcolor = None, backcolor_sel = None, flags = 0, scale_flags = None, cornerRadius = None, cornerEdges = None):
	return (eListboxPythonMultiContent.TYPE_PIXMAP_ALPHATEST, _i(pos[0]), _i(pos[1]), _i(size[0]), _i(size[1]), png, _c(backcolor), _c(backcolor_sel), flags if scale_flags is None else flags | scale_flags)

def MultiContentEntryPixmapAlphaBlend(pos = (0, 0), size = (0, 0), png = None, backcolor = None, backcolor_sel = None, flags = 0, scale_flags = None, cornerRadius = None, cornerEdges = None):
	return (eListboxPythonMultiContent.TYPE_PIXMAP_ALPHABLEND, _i(pos[0]), _i(pos[1]), _i(size[0]), _i(size[1]), png, _c(backcolor), _c(backcolor_sel), flags if scale_flags is None else flags | scale_flags)

def MultiContentEntryRectangle(pos = (0, 0), size = (0, 0), backgroundColor = None, backgroundColorSelected = None, borderWidth = None, borderColor = None, borderColorSelected = None, cornerRadius = 0, cornerEdges = 15):
	"""Un dreptunghi plin, cu chenar: un text gol. Colturile rotunjite nu se deseneaza."""
	return (eListboxPythonMultiContent.TYPE_TEXT, _i(pos[0]), _i(pos[1]), _i(size[0]), _i(size[1]), 0, RT_HALIGN_LEFT | RT_VALIGN_TOP, "", None, None, _c(backgroundColor), _c(backgroundColorSelected), borderWidth, _c(borderColor))

# Bara de progres din lista. Argumentele, in ordine, si tuplul sunt ale OE-Alliance, adica ce citeste desenarea listei
# (lib/gui/elistboxcontent.cpp, TYPE_PROGRESS): x, y, latimea, inaltimea, procentul, chenarul, apoi foreColor,
# foreColorSelected, backColor, backColorSelected. Fara foreColorSelected, pluginurile care il dau cadeau la fiecare rand
# (TypeError), iar culorile date dupa nume ajungeau pe locul vecinului. borderColor, borderColorSelected, culorile
# degradeului si colturile le dau pluginurile scrise pentru alte imagini: primite si lasate deoparte, ca la text.
def MultiContentEntryProgress(pos = (0, 0), size = (0, 0), percent = None, borderWidth = None, foreColor = None, foreColorSelected = None, backColor = None, backColorSelected = None, borderColor = None, borderColorSelected = None, startColor = None, midColor = None, endColor = None, startColorSelected = None, midColorSelected = None, endColorSelected = None, cornerRadius = None, cornerEdges = None):
	return (eListboxPythonMultiContent.TYPE_PROGRESS, _i(pos[0]), _i(pos[1]), _i(size[0]), _i(size[1]), _i(percent), _i(borderWidth), _c(foreColor), _c(foreColorSelected), _c(backColor), _c(backColorSelected))

# Bara de progres umpluta cu o poza (TYPE_PROGRESS_PIXMAP), ca in OE-Alliance: dupa procent vine poza, apoi ca mai sus.
def MultiContentEntryProgressPixmap(pos = (0, 0), size = (0, 0), percent = None, pixmap = None, borderWidth = None, foreColor = None, foreColorSelected = None, backColor = None, backColorSelected = None, borderColor = None, borderColorSelected = None, cornerRadius = None, cornerEdges = None):
	return (eListboxPythonMultiContent.TYPE_PROGRESS_PIXMAP, _i(pos[0]), _i(pos[1]), _i(size[0]), _i(size[1]), _i(percent), pixmap, _i(borderWidth), _c(foreColor), _c(foreColorSelected), _c(backColor), _c(backColorSelected))
