# Modificat de moneasoftware.com si hdsatelit.com, 2026

notifications = [ ]

notificationAdded = [ ]

# notifications which are currently on screen (and might be closed by similiar notifications)
current_notifications = [ ]

def __AddNotification(fnc, screen, id, *args, **kwargs):
	notifications.append((fnc, screen, args, kwargs, id))
	for x in notificationAdded:
		x()

def AddNotification(screen, *args, **kwargs):
	AddNotificationWithCallback(None, screen, *args, **kwargs)

def AddNotificationWithCallback(fnc, screen, *args, **kwargs):
	__AddNotification(fnc, screen, None, *args, **kwargs)

def AddNotificationWithID(id, screen, *args, **kwargs):
	__AddNotification(None, screen, id, *args, **kwargs)

def AddModalNotification(text, timeout=-1, default=True, typeIcon=None, windowTitle=None, callback=None, type=None, **kwargs):
	"""HDSatelit: numele cerut de pluginurile altor imagini: o intrebare (MessageBox) in coada notificarilor, raspunsul la callback"""
	from Screens.MessageBox import MessageBox
	if type is None:
		type = typeIcon if typeIcon is not None else MessageBox.TYPE_YESNO
	kwargs.update(timeout=timeout, default=default, typeIcon=typeIcon, windowTitle=windowTitle)
	AddNotificationWithCallback(callback, MessageBox, text, type, **kwargs)

# we don't support notifications with callback and ID as this
# would require manually calling the callback on cancelled popups.

def RemovePopup(id):
	# remove similiar notifications
	print("RemovePopup, id =", id)
	for x in notifications:
		if x[4] and x[4] == id:
			print("(found in notifications)")
			notifications.remove(x)

	for x in current_notifications:
		if x[0] == id:
			print("(found in current notifications)")
			x[1].close()

from Screens.MessageBox import MessageBox

# optiuni: ce mai primeste MessageBox (titlu, fel, puncte)
def AddPopup(text, type, timeout, id = None, **optiuni):
	if id is not None:
		RemovePopup(id)
	print("AddPopup, id =", id)
	AddNotificationWithID(id, MessageBox, text = text, type = type, timeout = timeout, close_on_any_key = True, **optiuni)


# ---------------------------------------------------------------------------------------------------------------------
# Numele cerute de pluginurile scrise pentru celelalte imagini Enigma2 (OEA4, 11.11.2026). Toate trec prin coada de mai sus;
# nimic din ce exista nu se schimba.
ICON_DEFAULT = 0


def AddNotificationWithIDCallback(fnc, id, screen, *args, **kwargs):
	__AddNotification(fnc, screen, id, *args, **kwargs)


def AddNotificationWithUniqueIDCallback(fnc, id, screen, *args, **kwargs):
	"""Numai o notificare in asteptare cu acelasi id (a doua se pierde, cu apelul ei)."""
	for x in notifications:
		if x[4] and x[4] == id:
			return
	__AddNotification(fnc, screen, id, *args, **kwargs)


def AddNotificationParentalControl(fnc, screen, *args, **kwargs):
	AddNotificationWithCallback(fnc, screen, *args, **kwargs)


def AddPopupWithCallback(fnc, text, type, timeout, id=None):
	if id is not None:
		RemovePopup(id)
	AddNotificationWithIDCallback(fnc, id, MessageBox, text=text, type=type, timeout=timeout, close_on_any_key=False)


def isPendingOrVisibleNotificationID(id):
	return any(x[4] == id for x in notifications) or any(x[0] == id for x in current_notifications)


def showInfo(text, timeout=4):
	AddPopup(text, MessageBox.TYPE_INFO, timeout)


def showWarning(text, timeout=5):
	AddPopup(text, MessageBox.TYPE_WARNING, timeout)


def showError(text, timeout=5):
	AddPopup(text, MessageBox.TYPE_ERROR, timeout)


class NotificationCenter:
	"""Ce cheama pluginurile pe notificationCenter (mesaj de raspuns, informatie, avertisment, eroare); la noi totul
	merge prin coada notificarilor de mai sus."""
	def __init__(self):
		self.session = None

	def setup(self, session):
		self.session = session

	def addModalNotification(self, text, timeout=-1, list=None, default=True, typeIcon=None, windowTitle=None, callback=None):
		AddModalNotification(text, timeout=timeout, default=default, typeIcon=typeIcon, windowTitle=windowTitle, callback=callback)

	def showInfo(self, text, timeout=4):
		showInfo(text, timeout)

	def showWarning(self, text, timeout=5):
		showWarning(text, timeout)

	def showError(self, text, timeout=5):
		showError(text, timeout)


notificationCenter = NotificationCenter()


class _CoadaNotificarilor:
	"""notificationQueue: forma mai veche a cozii, pe care o folosesc EPGRefresh, EPGBackup, AutoTimer si Growlee
	(registerDomain la pornire, queue/current/addedCB la citire). Domeniile se tin minte; notificarile merg in aceeasi coada."""
	def __init__(self):
		self.domains = {}

	def registerDomain(self, id, name, deferred_callable=False):
		self.domains.setdefault(id, {"name": name, "deferred_callable": deferred_callable})

	@property
	def queue(self):
		return notifications

	@property
	def current(self):
		return current_notifications

	@property
	def addedCB(self):
		return notificationAdded

	def isPendingOrVisibleID(self, id):
		return isPendingOrVisibleNotificationID(id)


notificationQueue = _CoadaNotificarilor()
