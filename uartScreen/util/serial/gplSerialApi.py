#-*- coding=utf-8 -*-

from gplSerial import gplSerial

class gplSerialApi():
	"""
	This is a class provide you some easier interfaces to operate serial port.
	"""
	# member variable of gplSerial class
	STATE_NONE = 0
	STATE_OPEN = 1
	STATE_CONNECTING  = 2
	STATE_OPERATIONAL = 3
	STATE_COLSED = 4
	STATE_ERROR  = 5 
	STATE_COLSED_WITH_ERROR = 6
	STATE_TRANSFERING_FILE  = 7
	
	def __init__(self, port=None, baudrate=None, kwargs=None, enable_seriallog=False):
		"""Constructor"""
		self._serial = None
		self._port   = port
		self._state  = None
		self._baudrate   = baudrate
		self._errorValue = None
		
		self._logger = None
		if enable_seriallog:
			self._enable_seriallog(enable_seriallog)
		
		if port and baudrate:
			self._open(port, baudrate, kwargs)
			
	def _changeState(self, newState):
		if self._state == newState:
			return
		
		if newState == self.STATE_COLSED or newState == self.STATE_COLSED_WITH_ERROR:
			pass
		
		oldState = self.getStateString()
		self._state = newState

	def getStateString(self):
		if self._state == self.STATE_NONE:
			return "Offline"
		if self._state == self.STATE_OPEN:
			return "Opening serial port"
		if self._state == self.STATE_CONNECTING:
			return "Connecting"
		if self._state == self.STATE_OPERATIONAL:
			return "Operational"
		if self._state == self.STATE_COLSED:
			return "Closed"
		if self._state == self.STATE_ERROR:
			return "Error: %s" % (self.getShortErrorString())
		if self._state == self.STATE_COLSED_WITH_ERROR:
			return "Error: %s" % (self.getShortErrorString())
		if self._state == self.STATE_TRANSFERING_FILE:
			return "Transfering file"
		return "?%d?" % (self._state)

	def getShortErrorString(self):
		if len(self._errorValue) < 20:
			return self._errorValue
		return self._errorValue[:20] + "..."