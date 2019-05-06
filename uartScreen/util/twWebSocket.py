#-*- coding=utf-8 -*-

import logging

import Queue
import threading
import websocket
from time import sleep 

_instance = None
sync_data = {"monotor":None}
########################################################################
class twWebSocket():
	""" twWebSocket """

	#----------------------------------------------------------------------
	def __init__(self, url="ws://127.0.0.1:5000/sockjs/websocket", header=[], 
	             enable_log=False, tracable=False, maxQueneSize=5, callback=None):
		"""Constructor"""
		websocket.enableTrace(tracable)
		self._ws = websocket.WebSocketApp(url, header, 
		                                  on_open=self._on_open, 
		                                  on_message=self._on_message, 
		                                  on_error=self._on_error, 
		                                  on_close=self._on_close, 
		                                  on_ping=self._on_ping)
		self._callback = callback
		self._monito_terminate = False
		self._message_quene = Queue.Queue(maxQueneSize)
		self._monito = threading.Thread(target=self._monitor)
		self._monito.daemon = True
	
		if enable_log:
			self._logger = logging.getLogger(__name__)
	
	#----------------------------------------------------------------------
	def _monitor(self):
		""" _monitor """
		while not self._monito_terminate:
			sleep(0.1)			
			if not self._message_quene.empty():
				message = self._message_quene.get_nowait()
				if self._callback:
					#print "dealResult:", self._callback(message)
					sync_data["monotor"]=self._callback(message)
				else:
					print "message",message
		
	#----------------------------------------------------------------------
	def _on_open(self, ws):
		""" _on_open """
		pass
	
	#----------------------------------------------------------------------
	def _on_message(self, ws, message):
		""" _on_message """
		#print " _on_message "
		#print "<n1<",type(message), "<n2<", message
		if message and not self._message_quene.full():
			self._message_quene.put_nowait(message)
	
	#----------------------------------------------------------------------
	def _on_error(self, ws, error):
		""" _on_error """
		pass
	
	#----------------------------------------------------------------------
	def _on_close(self, ws):
		""" _on_close """
		pass
	
	#----------------------------------------------------------------------
	def _on_ping(self, ws):
		""" _on_ping """
		pass
	
	#----------------------------------------------------------------------
	def start_loop(self):
		""" start_loop """
		self._monito.start()
		self._ws.run_forever()


#----------------------------------------------------------------------
def webSocketManager(url="ws://127.0.0.1:5000/sockjs/websocket", header=[], 
                     enable_log=False, tracable=False, maxQueneSize=5, callback=None):
	global _instance
	_instance = twWebSocket(url, header, enable_log, tracable, maxQueneSize, callback)
	return _instance
	

#----------------------------------------------------------------------

	
if __name__ == "__main__":
	print "ok"
	wsm = webSocketManager(url="ws://192.168.1.252:5000/sockjs/websocket")
	wsm.start_loop()
