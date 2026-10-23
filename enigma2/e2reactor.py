# enigma2 reactor: based on pollreactor, which is
# Copyright (c) 2001-2004 Twisted Matrix Laboratories.
# See LICENSE for details.
# Modificat de moneasoftware.com si hdsatelit.com, 2026


"""
Maintainer: U{Felix Domke<mailto:tmbinc@elitedvb.net>}
"""

# System imports
import select, errno, sys, math

# Twisted imports
from twisted.python import log, failure
from twisted.internet import main, posixbase, error
#from twisted.internet.pollreactor import PollReactor, poller

from enigma import getApplication, eTimer

# globals
reads = {}
writes = {}
selectables = {}

POLL_DISCONNECTED = (select.POLLHUP | select.POLLERR | select.POLLNVAL)

class E2SharedPoll:
	def __init__(self):
		self.dict = { }
		self.eApp = getApplication()

	def register(self, fd, eventmask = select.POLLIN | select.POLLERR | select.POLLOUT):
		self.dict[fd] = eventmask
	
	def unregister(self, fd):
		del self.dict[fd]
	
	def poll(self, timeout = None):
		try:
			r = self.eApp.poll(timeout, self.dict)
		except KeyboardInterrupt:
			return None
		return r

poller = E2SharedPoll()

class PollReactor(posixbase.PosixReactorBase):
	"""A reactor that uses poll(2).

	eMainloop::poll(ms) does not keep a timeout on its own: 0 means no timeout at all, iterate() truncates a
	remainder under 1 ms to 0 again, and with an empty eTimer list poll(2) is not capped by the Twisted timeout.
	A delayed call could then wait until the next event on a Python descriptor (minutes on an idle box). So the
	timeout asked by Twisted is held by a single-shot eTimer that writes to the waker (a reader in the same poll),
	and wakeups from other threads (callFromThread) or from enigma2 callbacks running inside eApp.poll (callLater)
	go through the waker as well."""

	_in_poll = False
	_timeout_timer = None
	_timeout_conn = None

	def _armTimeout(self, ms):
		if self._timeout_timer is None:
			self._timeout_timer = eTimer()
			try:
				self._timeout_timer.callback.append(self._timeoutReached)
			except AttributeError:
				self._timeout_conn = self._timeout_timer.timeout.connect(self._timeoutReached)
		self._timeout_timer.start(ms, True)

	def _timeoutReached(self):
		# runs in eMainloop before the poll(2) of the same pass: the byte in the waker makes that poll return at once
		# with a Python event, so the loop goes back to Twisted
		self.wakeUp()

	def callFromThread(self, f, *args, **kwargs):
		"""Queue the call and wake the loop; safe from any thread. mytest.py sets supportsThreads() to False, and
		then Twisted uses the variant that only queues the call, without waking the loop."""
		assert callable(f), "%r is not callable" % (f,)
		self.threadCallQueue.append((f, args, kwargs))
		self.wakeUp()

	def _updateRegistration(self, fd):
		"""Register/unregister an fd with the poller."""
		try:
			poller.unregister(fd)
		except KeyError:
			pass

		mask = 0
		if fd in reads: mask = mask | select.POLLIN
		if fd in writes: mask = mask | select.POLLOUT
		if mask != 0:
			poller.register(fd, mask)
		else:
			if fd in selectables: del selectables[fd]
		
		
		poller.eApp.interruptPoll()

	def _dictRemove(self, selectable, mdict):
		try:
			# the easy way
			fd = selectable.fileno()
			# make sure the fd is actually real.  In some situations we can get
			# -1 here.
			mdict[fd]
		except:
			# the hard way: necessary because fileno() may disappear at any
			# moment, thanks to python's underlying sockets impl
			for fd, fdes in list(selectables.items()):
				if selectable is fdes:
					break
			else:
				# Hmm, maybe not the right course of action?  This method can't
				# fail, because it happens inside error detection...
				return
		if fd in mdict:
			del mdict[fd]
			self._updateRegistration(fd)

	def addReader(self, reader):
		"""Add a FileDescriptor for notification of data available to read.
		"""
		fd = reader.fileno()
		if fd not in reads:
			selectables[fd] = reader
			reads[fd] =  1
			self._updateRegistration(fd)

	def addWriter(self, writer, writes=writes, selectables=selectables):
		"""Add a FileDescriptor for notification of data available to write.
		"""
		fd = writer.fileno()
		if fd not in writes:
			selectables[fd] = writer
			writes[fd] =  1
			self._updateRegistration(fd)

	def removeReader(self, reader, reads=reads):
		"""Remove a Selectable for notification of data available to read.
		"""
		return self._dictRemove(reader, reads)

	def removeWriter(self, writer, writes=writes):
		"""Remove a Selectable for notification of data available to write.
		"""
		return self._dictRemove(writer, writes)

	def removeAll(self, reads=reads, writes=writes, selectables=selectables):
		"""Remove all selectables, and return a list of them."""
		if self.waker is not None:
			self.removeReader(self.waker)
		result = list(selectables.values())
		fds = list(selectables.keys())
		reads.clear()
		writes.clear()
		selectables.clear()
		for fd in fds:
			poller.unregister(fd)
			
		if self.waker is not None:
			self.addReader(self.waker)
		return result

	def doPoll(self, timeout,
			   reads=reads,
			   writes=writes,
			   selectables=selectables,
			   select=select,
			   log=log,
			   POLLIN=select.POLLIN,
			   POLLOUT=select.POLLOUT):
		"""Poll the poller for new events."""
		
		if timeout is not None:
			# at least 1 ms (0 would mean no timeout); the timeout itself is held by the eTimer;
			# at most 1 h, so eTimer.start never gets a value past a 32-bit int (24.8 days)
			timeout = min(3600000, max(1, int(math.ceil(timeout * 1000))))
			self._armTimeout(timeout)

		try:
			self._in_poll = True
			try:
				l = poller.poll(timeout)
			finally:
				self._in_poll = False
				if self._timeout_timer is not None:
					self._timeout_timer.stop()
			if l is None:
				if self.running:
					self.stop()
				l = [ ]
		except select.error as e:
			if e.errno == errno.EINTR:
				return
			else:
				raise
		_drdw = self._doReadOrWrite
		for fd, event in l:
			try:
				selectable = selectables[fd]
			except KeyError:
				# Handles the infrequent case where one selectable's
				# handler disconnects another.
				continue
			log.callWithLogger(selectable, _drdw, selectable, fd, event, POLLIN, POLLOUT, log)

	doIteration = doPoll

	def _doReadOrWrite(self, selectable, fd, event, POLLIN, POLLOUT, log, 
		faildict={
			error.ConnectionDone: failure.Failure(error.ConnectionDone()),
			error.ConnectionLost: failure.Failure(error.ConnectionLost())
		}):
		why = None
		inRead = False
		if event & POLL_DISCONNECTED and not (event & POLLIN):
			why = main.CONNECTION_LOST
		else:
			try:
				if event & POLLIN:
					why = selectable.doRead()
					inRead = True
				if not why and event & POLLOUT:
					why = selectable.doWrite()
					inRead = False
				if not selectable.fileno() == fd:
					why = error.ConnectionFdescWentAway('Filedescriptor went away')
					inRead = False
			except:
				log.deferr()
				why = sys.exc_info()[1]
		if why:
			self._disconnectSelectable(selectable, why, inRead)

	def callLater(self, *args, **kwargs):
		poller.eApp.interruptPoll()
		if self._in_poll:
			# called from an enigma2 callback inside eApp.poll: interruptPoll() does not stop the poll(2) that
			# follows in the same pass, the waker does
			self.wakeUp()
		return posixbase.PosixReactorBase.callLater(self, *args, **kwargs)

def install():
	"""Install the poll() reactor."""
	
	p = PollReactor()
	main.installReactor(p)

__all__ = ["PollReactor", "install"]
