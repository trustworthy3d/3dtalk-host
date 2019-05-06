#!/usr/bin/env python
#-*- coding:utf-8 -*-

import threading
from time import sleep
from dealaction import ActionManager
from util.twWebSocket import webSocketManager
from util.serial.gplSerial import serialManager
from datasync import DataSyncManager
from filelist import FileManager
from settings import settings
import userevents as Event
from octoprint.server import printer
_instance = None


class uartScreen(threading.Thread):	
	""" communicate to octoprint """
	def __init__(self,settingsManager=None,serialManager=None,eventManager=None):
		threading.Thread.__init__(self)
		self._settingsManager  = settingsManager
		self._serialManager    = serialManager
		self._eventManager     = eventManager
		self._thread_stop      = False
		self.work = threading.Thread(target=self._work)
		self.work.setDaemon(True)
		
	def _work(self):
		""" _work """
		self._eventManager.fire("action_init")
		self._eventManager.fire("action_serial_connect",payload={"port":self._settingsManager.get_config()["connect"]["port"],"action":"connect"})#VIRTUAL   /dev/ttyACM0
		milliseconds=0
		while not self._thread_stop:
			sleep(0.01)
			milliseconds+=1
			cmd = self._serialManager.receive()
			if cmd is not None:
				print "cmd_org:",cmd
			if cmd and len(cmd)>8:
				print "cmd:", cmd
				if cmd[5] in self._settingsManager.action_map:
					self._eventManager.fire(self._settingsManager.action_map[cmd[5]],payload={"command":cmd})
					pass
				else:
					pass
					
			elif milliseconds>999:
				milliseconds=0
				self._eventManager.fire("action_timer")
				
	def run(self):
		self.work.start()

def uartScreenManager(port=5000,payload={'port':5000,'language':"english"}):
	
	st=settings(init=True)
	
	try:
		sm = serialManager(port="/dev/ttyUSB0", baudrate=115200)#/dev/ttyUSB0
		st.set(["connect","port"],"/dev/ttyACM0",force=True)
		#st.set(["connect","port"],"VIRTUAL",force=True)
	except:
		print "open /dev/ttyUSB0 error "
		sm = serialManager(port="/dev/ttyUSB1", baudrate=115200)#/dev/ttyUSB0

	fm = FileManager(serialManager=sm)
	sync=DataSyncManager(serialManager=sm,settingsManager=st,printer=printer)	
	ac = ActionManager(addr="127.0.0.1",port=port,serialManager=sm,fileManager=fm,dataSyncManager=sync)

	ev = Event.eventManager()
	Event.CommandTrigger(ac)
	
	global _instance
	if _instance is None:
		_instance = uartScreen(settingsManager=st,serialManager=sm,eventManager=ev)		
		_instance.start()
	return _instance

def main(): 
	uartscreen = uartScreenManager()
	
if __name__ == "__main__":
	import logging
	main()
	logger = logging.getLogger(__name__)
	logger.info("test serial info")
