# Modificat de moneasoftware.com si hdsatelit.com, 2026
from .HTMLComponent import HTMLComponent
from .GUIComponent import GUIComponent

from Tools.FuzzyDate import FuzzyTime

from enigma import eListboxPythonMultiContent, eListbox, \
	RT_HALIGN_LEFT, RT_HALIGN_RIGHT, RT_VALIGN_CENTER
from timer import TimerEntry
from Tools.Directories import resolveFilename, SCOPE_CURRENT_SKIN
from skin import getListFont, getParameterFromSkin, getListPixmap, centerPixmap, listRect


def _nuPoate(timer):
	"""Inregistrarea care trebuia sa fi pornit si nu poate (aceeasi regula ca detaliile de sub lista si pagina web:
	Components/HdsInregistrariProgramate.stare)."""
	try:
		from Components import HdsInregistrariProgramate as HIP
		return HIP.stare(timer, False) == HIP.STARE_NU_POATE
	except Exception:
		return False

# The rows are drawn here; the skin can set their look (HDSatelit names, defaults = the 2011 look):
#   <alias name="TimerList0"/>: font of the channel and row height; <alias name="TimerList1"/>: the other lines
#   TimerListName, TimerListDescription, TimerListTime, TimerListState, TimerListIcon: x,y,w,h of the channel,
#   the name of the timer, the time line, the state and the icon of a disabled timer (x below 0 counts from the
#   right edge of the row, w of 0 or below reaches the right edge minus |w|)
#   <hdsparameters>: TimerListImage ("...%s.png", %s = disabled)

class TimerList(HTMLComponent, GUIComponent, object):
#
#  | <Service>     <Name of the Timer>  |
#  | <start, end>              <state>  |
#
	def buildTimerEntry(self, timer, processed):
		width = self.l.getItemSize().width()
		res = [ None ]
		x, y, w, h = listRect(getParameterFromSkin("TimerListName", (0, 0, 0, 30))[0], width)
		res.append((eListboxPythonMultiContent.TYPE_TEXT, x, y, w, h, 0, RT_HALIGN_LEFT|RT_VALIGN_CENTER, timer.service_ref.getServiceName()))
		x, y, w, h = listRect(getParameterFromSkin("TimerListDescription", (0, 30, 0, 20))[0], width)
		res.append((eListboxPythonMultiContent.TYPE_TEXT, x, y, w, h, 1, RT_HALIGN_LEFT|RT_VALIGN_CENTER, timer.name))
		x, y, w, h = listRect(getParameterFromSkin("TimerListTime", (0, 50, -150, 20))[0], width)

		repeatedtext = ""
		# comutarea spusa in cuvinte, ca in detaliile de sub lista (HdsInregistrariProgramate.textCe)
		zap = _("doar schimbă canalul")
		days = ( _("Mon"), _("Tue"), _("Wed"), _("Thu"), _("Fri"), _("Sat"), _("Sun") )
		if timer.repeated:
			flags = timer.repeated
			count = 0
			for d in (0, 1, 2, 3, 4, 5, 6):
					if (flags & 1 == 1):
						if (count != 0):
							repeatedtext += ", "
						repeatedtext += days[d]
						count += 1
					flags = flags >> 1
			if timer.justplay:
				if timer.end - timer.begin < 4: # rounding differences
					res.append((eListboxPythonMultiContent.TYPE_TEXT, x, y, w, h, 1, RT_HALIGN_LEFT|RT_VALIGN_CENTER, repeatedtext + ((" %s, " + zap) % (FuzzyTime(timer.begin)[1]))))
				else:
					res.append((eListboxPythonMultiContent.TYPE_TEXT, x, y, w, h, 1, RT_HALIGN_LEFT|RT_VALIGN_CENTER, repeatedtext + ((" %s ... %s (%d " + _("mins") + ") ") % (FuzzyTime(timer.begin)[1], FuzzyTime(timer.end)[1], (timer.end - timer.begin) // 60)).rstrip() + ", " + zap))
			else:
				res.append((eListboxPythonMultiContent.TYPE_TEXT, x, y, w, h, 1, RT_HALIGN_LEFT|RT_VALIGN_CENTER, repeatedtext + ((" %s ... %s (%d " + _("mins") + ")") % (FuzzyTime(timer.begin)[1], FuzzyTime(timer.end)[1], (timer.end - timer.begin) // 60))))
		else:
			if timer.justplay:
				if timer.end - timer.begin < 4:
					res.append((eListboxPythonMultiContent.TYPE_TEXT, x, y, w, h, 1, RT_HALIGN_LEFT|RT_VALIGN_CENTER, repeatedtext + (("%s, %s, " + zap) % (FuzzyTime(timer.begin)))))
				else:
					res.append((eListboxPythonMultiContent.TYPE_TEXT, x, y, w, h, 1, RT_HALIGN_LEFT|RT_VALIGN_CENTER, repeatedtext + (("%s, %s ... %s (%d " + _("mins") + ") ") % (FuzzyTime(timer.begin) + FuzzyTime(timer.end)[1:] + ((timer.end - timer.begin) // 60,))).rstrip() + ", " + zap))
			else:
				res.append((eListboxPythonMultiContent.TYPE_TEXT, x, y, w, h, 1, RT_HALIGN_LEFT|RT_VALIGN_CENTER, repeatedtext + (("%s, %s ... %s (%d " + _("mins") + ")") % (FuzzyTime(timer.begin) + FuzzyTime(timer.end)[1:] + ((timer.end - timer.begin) // 60,)))))

		if not processed:
			if timer.state == TimerEntry.StateWaiting:
				state = _("waiting")
			elif timer.state == TimerEntry.StatePrepared:
				state = _("about to start")
			elif timer.state == TimerEntry.StateRunning:
				if timer.justplay:
					state = _("zapped")
				else:
					state = _("recording...")
			elif timer.state == TimerEntry.StateEnded:
				state = _("done!")
			else:
				state = _("<unknown>")
		else:
			state = _("done!")

		if timer.disabled:
			state = _("disabled")
		elif not processed and _nuPoate(timer):
			# ora a trecut, iar incercarea a cazut (fara disc, fara tuner): nu „în așteptare”
			state = _("nu pornește")

		x, y, w, h = listRect(getParameterFromSkin("TimerListState", (-150, 50, 150, 20))[0], width)
		res.append((eListboxPythonMultiContent.TYPE_TEXT, x, y, w, h, 1, RT_HALIGN_RIGHT|RT_VALIGN_CENTER, state))

		if timer.disabled:
			png, from_skin = getListPixmap("TimerListImage", "disabled", resolveFilename(SCOPE_CURRENT_SKIN, "skin_default/icons/redx.png"))
			if png is not None:
				rect, skinned = getParameterFromSkin("TimerListIcon", (490, 5, 40, 40))
				rect = listRect(rect, width)
				if skinned:
					rect = centerPixmap(rect, png)
				res.append((from_skin and eListboxPythonMultiContent.TYPE_PIXMAP_ALPHABLEND or eListboxPythonMultiContent.TYPE_PIXMAP_ALPHATEST, rect[0], rect[1], rect[2], rect[3], png))
		return res

	def __init__(self, list):
		GUIComponent.__init__(self)
		self.l = eListboxPythonMultiContent()
		self.l.setBuildFunc(self.buildTimerEntry)
		font, height = getListFont("TimerList0", ("Regular", 20, 70))
		self.l.setFont(0, font)
		self.l.setFont(1, getListFont("TimerList1", ("Regular", 18))[0])
		self.l.setItemHeight(height)
		self.l.setList(list)

	def getCurrent(self):
		cur = self.l.getCurrentSelection()
		return cur and cur[0]

	GUI_WIDGET = eListbox

	def postWidgetCreate(self, instance):
		instance.setContent(self.l)

	def moveToIndex(self, index):
		self.instance.moveSelectionTo(index)

	def getCurrentIndex(self):
		return self.instance.getCurrentIndex()

	currentIndex = property(getCurrentIndex, moveToIndex)
	currentSelection = property(getCurrent)

	def moveDown(self):
		self.instance.moveSelection(self.instance.moveDown)

	def invalidate(self):
		self.l.invalidate()

	def entryRemoved(self, idx):
		self.l.entryRemoved(idx)
