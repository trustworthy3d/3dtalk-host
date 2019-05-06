#-*- coding=utf-8 -*-

import logging

import httplib2
import urllib
import json

_instance = None

########################################################################
class HttpClient():
	""" HttpClient """

	#----------------------------------------------------------------------
	def __init__(self, addr="127.0.0.1", port=5000, enable_log=False):
		"""Constructor"""
		self._addr = addr
		self._port = port
		self._url  = "http://" + str(addr) + ":" + str(port)
		self._http = httplib2.Http(timeout=3)
		self._cookie = None
        
		if enable_log:
			self._logger = logging.getLogger(__name__)
        
	#----------------------------------------------------------------------
	def _httpRequest(self, url=None, path="/", method="POST", data=None, dataType="json", cookie=None, callback=None):
		""" _httpRequest """
		#print path
		if path:
			url = self._url + str(path)
		elif url:
			url = url
		else:
			url = self._url

		if "json" == dataType:
			data = json.dumps(data)
		else:
			data = urllib.urlencode(data)

		headers = {'Content-Type': 'application/{0}; charset=UTF-8'.format(dataType)}
		#print url
		#print headers
		#print data
		if cookie:
			headers["Cookie"] = cookie
		elif self._cookie:
			headers["Cookie"] = self._cookie
			
		#print "cookie",headers["Cookie"]
		#print url, "<=1=>", data
		#print headers
			
		try:
			resp, content = self._http.request(url, method=method, body=data, headers=headers)
			#print resp, content 
		except:
			print "ERROR: *** Network inaccessible! ***"
			resp, content = None, None
        
		if callback:
			return callback(resp, content)
		else:
			return resp, content
		
	#----------------------------------------------------------------------
	def setCookie(self, cookie=None):
		""" setCookie """
		if cookie:
			self._cookie = cookie
			
	#----------------------------------------------------------------------
	def resetCookie(self):
		""" resetCookie """
		self._cookie = None
		
	#----------------------------------------------------------------------
	def httpGet(self, path='/', data=None, dataType="json", callback=None, cookie=None, url=None):
		""" httpGet """
		return self._httpRequest(url, path, "GET", data, dataType, cookie, callback)
        
	#----------------------------------------------------------------------
	def httpPost(self, path='/', data=None, dataType="json", callback=None, cookie=None, url=None):
		""" httpPost """
		return self._httpRequest(url, path, "POST", data, dataType, cookie, callback)
    
	#----------------------------------------------------------------------
	def httpDelete(self, path='/', data=None, dataType="json", callback=None, cookie=None, url=None):
		""" httpDelete """
		return self._httpRequest(url, path, "DELETE", data, dataType, cookie, callback)
	
	#----------------------------------------------------------------------
	def httpPut(self, path='/', data=None, dataType="json", callback=None, cookie=None, url=None):
		""" httpPut """
		return self._httpRequest(url, path, "PUT", data, dataType, cookie, callback)	


#----------------------------------------------------------------------
def HttpClientManager(addr="127.0.0.1", port=5000, enable_log=False):
	global _instance
	if _instance is None:
		_instance = HttpClient(addr, port, enable_log)
	return _instance


#----------------------------------------------------------------------
def debugHttpClient():
	th = HttpClient()
	print th.httpGet()
	print th.httpGet(path="/api/settings")
	print th.httpPost(path="/api/files/changeFilesPath",data={"filespath": "example"})
	print th.httpDelete("/api/files/local/maotouyingbitong.gcode")

if __name__ == "__main__":
	debugHttpClient()

    
