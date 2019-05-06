#-*- coding=gbk -*-

import logging

import Queue
import threading
import json
from time import sleep 
import userevents as Event
import settings
from settings import default_settings
import subprocess,os
sync_data = {"monotor":None}

VERSONS="".center(12)
if os.path.exists("/udisk/update"):
	VERSONS="emergency".center(12)
else:
	VERSONS="2.1.0S1.1.20".center(12)

try:
	import sys
	sys.path.append("../../")
	from settings import valid_boolean_trues
except:
	valid_boolean_trues = [True, "true", "yes", "y", "1"]

_instance = None


status_addr=[""]
from time import *
def secs2str(secs):
	return strftime("%H:%M:%S",localtime(secs))
try:
	import socket,fcntl,struct
	def get_ip_address(ifname):
		try:
			s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) 
			ip = socket.inet_ntoa(fcntl.ioctl(s.fileno(), 0x8915,struct.pack('256s', ifname[:15]))[20:24])
		except:
			ip="No Connection"
		return ip
except:
	def get_ip_address(ifname):
		#s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) 
		#return socket.inet_ntoa(fcntl.ioctl(s.fileno(), 0x8915,struct.pack('256s', ifname[:15]))[20:24])
		return "127.0.0.1"   
########################################################################
class JsonParser(threading.Thread):
	""" DataSync """

	#----------------------------------------------------------------------
	def __init__(self, serialManager=None ,settingsManager=None,maxQueneSize=5, printer=None,enable_log=False,):
		"""Constructor"""
		self._logger = logging.getLogger(__name__)
		threading.Thread.__init__(self)
		self._parser_terminate = True
		self._original_data = Queue.Queue(maxQueneSize)
		self._result_data = Queue.Queue(maxQueneSize)
		self._serialManager = serialManager
		self._settingsManager  = settingsManager
		self.firstrun=True
		self.restart_times=0
		self.printover=False
		
		self._temperatureBacklog = []
		self._temperatureBacklogMutex = threading.Lock()
		self._logBacklog = []
		self._logBacklogMutex = threading.Lock()
		self._messageBacklog = []
		self._messageBacklogMutex = threading.Lock()	
		self._printer = printer
		if self._printer is not None:
			self._printer.registerCallback(self)
		
		if enable_log:
			self._logger = logging.getLogger(__name__)

	#----------------------------------------------------------------------
	def getFromDict(self, data, callback=None, asdict=False):
		""" getFromDict """
		if isinstance(data, dict):
			if isinstance(callback, (tuple, list)):
				if len(callback) == 0:
					return None

				while len(callback) > 0:
					key = callback.pop(0)
					if isinstance(data, dict):
						if key in data.keys():
							data = data[key]
						else:
							data = None
					elif isinstance(data, (tuple, list)):
						callback.insert(0, key)
						data = self.getFromList(data, callback)

			if asdict and isinstance(callback, str):
				results = {}
				results[callback] = data
				return results
			else:
				return data

	#----------------------------------------------------------------------
	def getFromList(self, data, callback=None, asdict=False):
		""" getFromList """
		if isinstance(data, (tuple, list)):
			result = []
			for item in data:
				if isinstance(item, dict):
					return self.getFromDict(item, callback, asdict)
				elif isinstance(item, (tuple, list)):
					return self.getFromList(data, callback, asdict)
				else:
					result.append(item)

				if asdict and isinstance(callback, str):
					results= {}
					results[callback] = result
					return results
				else:
					return result

	#----------------------------------------------------------------------
	def get(self, data, callback=None, asdict=False):
		""" get """
		if isinstance(data, dict):
			return self.getFromDict(data, callback, asdict)
		elif isinstance(data, (tuple, list)):
			return self.getFromList(data, callback, asdict)
		else:
			return data

	#----------------------------------------------------------------------
	def getInt(self, data, callback=None):
		""" getInt """
		value = self.get(data, callback)
		if value is None:
			return None

		try:
			return int(value)
		except:
			return None

	#----------------------------------------------------------------------
	def getFloat(self, data, callback=None):
		""" getInt """
		value = self.get(data, callback)
		if value is None:
			return None

		try:
			return float(value)
		except:
			return None

	#----------------------------------------------------------------------
	def getFloat(self, data, callback=None):
		""" getInt """
		value = self.get(data, callback)
		if value is None:
			return None

		try:
			return float(value)
		except:
			return None

	#----------------------------------------------------------------------
	def getBoolean(self, data, callback=None):
		""" getInt """
		value = self.get(data, callback)
		if value is None:
			return None

		if isinstance(value, bool):
			return value
		return value.lower() in valid_boolean_trues

	#----------------------------------------------------------------------
	def executeSystemCommand(self, command):
		print "executeSystemCommand"
		def commandExecutioner(command):
			self._logger.info("Executing system command: %s" % command)
			subprocess.Popen(command, shell=True)

		try:
			if isinstance(command, (list, tuple, set)):
				for c in command:
					commandExecutioner(c)
			else:
				commandExecutioner(command)
		except subprocess.CalledProcessError, e:
			self._logger.warn("Command failed with return code %i: %s" % (e.returncode, e.message))
		except Exception, ex:
			self._logger.exception("Command failed")
	def reloadip(self):
		sleep(2)
		self.firstrun=True
	def deal(self, data, callback=None):
		""" deal """
		#print "sunlongcan websocket data "
		value_path = {
		    #file's name and size
		    "name": ["current", "job", "file", "name"], 
		    "size": ["current", "job", "file", "size"], 
		    #tempurature
		    "bed_actual": ["current", "temps", "bed", "actual"],
		    "bed_target": ["current", "temps", "bed", "target"],
		    "tool0_actual": ["current", "temps", "tool0", "actual"],
		    "tool0_target": ["current", "temps", "tool0", "target"],
		    "tool1_actual": ["current", "temps", "tool1", "actual"],
		    "tool1_target": ["current", "temps", "tool1", "target"],
		    "tool2_actual": ["current", "temps", "tool2", "actual"],
		    "tool2_target": ["current", "temps", "tool2", "target"],
		    #status
		    "stateString":["current","state","stateString"],
		    "operational":["current","state","flags","operational"],
		    "paused":["current","state","flags","paused"],
		    "printing":["current","state","flags","printing"],
		    "error":["current","state","flags","error"],
		    "ready":["current","state","flags","ready"],
		    "closedOrError":["current","state","flags","closedOrError"],
		    #progress
		    "completion":["current","progress","completion"],
		    "printTime":["current","progress","printTime"]

		}		
		if isinstance(data, str):
			try:
				data = json.loads(data)
			except:
				return
		#print "data:",data
		result={}
		if isinstance(data, dict):
			for key in value_path.iterkeys():
				result[key] = self.get(data, value_path[key])
				#if result[key]:
					#print result[key]
		#print type(result["error"]),result["error"] 
		#self._serialManager.send("\x5A\xA5{0}\x82{1}{2}".format(chr(8+3),self._settingsManager.get_config()["uart_display"]["label"]["host_ip_text"],"IP地址："))
		#self._serialManager.send("\x5A\xA5{0}\x82{1}{2}".format(chr(8+3),self._settingsManager.get_config()["uart_display"]["label"]["stateString_text"],"机器状态："))		
		if self.firstrun:
			self.firstrun=False
			#print "firstrun"
			self._settingsManager.set(["network","host_ip"],str(get_ip_address("wlan0")))
			
			
			#print "firstrun",self._settingsManager.get_config()["network"]["host_ip"]
			if self._settingsManager.get_config()["network"]["host_ip"]=="192.168.0.1":
				self._settingsManager.set(["network","host_ip"],str(get_ip_address("eth0")))
			if self._settingsManager.get_config()["network"]["host_ip"]=="No Connection":
				self._settingsManager.set(["network","host_ip"],str(get_ip_address("wlan0")))
			if self._settingsManager.get_config()["network"]["host_ip"]=="No Connection":
				self.firstrun=True
				self.restart_times+=1
			if self.restart_times==30:
				self.restart_times=0
				self.executeSystemCommand("sudo sudo /sbin/ifdown wlan0")
				self.executeSystemCommand("sudo sudo /sbin/ifup wlan0")	
		#防止屏幕IP消失
		str_send=self._settingsManager.get_config()["network"]["host_ip"]+"                        "
		self._serialManager.send("\x5A\xA5{0}\x82{1}{2}".format(chr(16+3),self._settingsManager.get_config()["uart_display"]["homepage"]["host_ip"],str_send))
		#self._serialManager.send("\x5A\xA5{0}\x82{1}{2}".format(chr(12+3),self._settingsManager.get_config()["uart_display"]["about"]["versons"],self._settingsManager.get_config()["machine"]["versons"]))
		self._serialManager.send("\x5A\xA5{0}\x82{1}{2}".format(chr(12+3),self._settingsManager.get_config()["uart_display"]["about"]["versons"],VERSONS))
		self._serialManager.send("\x5A\xA5{0}\x82{1}{2}".format(chr(10+3),self._settingsManager.get_config()["uart_display"]["about"]["serialNumber"],self._settingsManager.get_config()["machine"]["serialNumber"]))
		
		if result["error"]:
			self._settingsManager.set(["status","error"],True,force=True)
		else :
			self._settingsManager.set(["status","error"],False,force=True)
			
		str_send = self._settingsManager.get_config()["languaes"][self._settingsManager.get_config()["machine"]["current_language"]].get(result["stateString"],10*" ")+"           "
		if str_send==" "*21:                                                                                                                                                           
			str_send="Error            "
		self._serialManager.send("\x5A\xA5{0}\x82{1}{2}".format(chr(12+3),self._settingsManager.get_config()["uart_display"]["homepage"]["stateString"],str_send))
		
		if result["tool0_actual"]!=None:
			str_send=str(result["tool0_actual"])+"                        "
			self._serialManager.send("\x5A\xA5{0}\x82{1}{2}".format(chr(6+3),self._settingsManager.get_config()["uart_display"]["homepage"]["tool0_actual"],str_send))
		if result["tool1_actual"]!=None:
			str_send=str(result["tool1_actual"])+"                        "
			self._serialManager.send("\x5A\xA5{0}\x82{1}{2}".format(chr(6+3),self._settingsManager.get_config()["uart_display"]["homepage"]["tool1_actual"],str_send))
		if result["tool2_actual"]!=None:
			str_send=str(result["tool2_actual"])+"                        "
			self._serialManager.send("\x5A\xA5{0}\x82{1}{2}".format(chr(6+3),self._settingsManager.get_config()["uart_display"]["homepage"]["tool2_actual"],str_send))
		if result["bed_actual"]!=None:
			str_send=str(result["bed_actual"])+"                        "
			self._serialManager.send("\x5A\xA5{0}\x82{1}{2}".format(chr(6+3),self._settingsManager.get_config()["uart_display"]["homepage"]["bed_actual"],str_send))
	
		if result["tool0_target"]!=None:
			self._settingsManager.set(["status","tool0_target"],result["tool0_target"],force=True)
		if result["tool1_target"]!=None:
			self._settingsManager.set(["status","tool1_target"],result["tool0_target"],force=True)
		if result["tool2_target"]!=None:
			self._settingsManager.set(["status","tool0_target"],result["tool2_target"],force=True)
		if result["bed_target"]!=None:
			self._settingsManager.set(["status","tool1_target"],result["bed_target"],force=True)	
			
		if result["name"] is not None:
			str_send=str(result["name"])+"                        "
			self._serialManager.send("\x5A\xA5{0}\x82{1}{2}".format(chr(24+3),self._settingsManager.get_config()["uart_display"]["homepage"]["name"],str_send))

		str_send=result["size"]
		if str_send is not None:
			if str_send/1024<1024:
				str_send=str(str_send/1024)+"k              "
			else:
				str_send=str("%.2f"%(str_send/1024/1024.0))+"M              "
		else:
			str_send="               "
		self._serialManager.send("\x5A\xA5{0}\x82{1}{2}".format(chr(10+3),self._settingsManager.get_config()["uart_display"]["homepage"]["size"],str_send))

		str_send=result["printTime"]
		if type(str_send) is int:
			if str_send>360000:
				str_send="{0:03d}:{1:02d}:{2:02d} ".format((str_send/60/60)%1000,(str_send/60)%60,str_send%60)
			else:
				str_send="{0:02d}:{1:02d}:{2:02d} ".format((str_send/60/60)%100,(str_send/60)%60,str_send%60)
		else:
			str_send="00:00:00 "

		self._serialManager.send("\x5A\xA5{0}\x82{1}{2}".format(chr(9+3),self._settingsManager.get_config()["uart_display"]["homepage"]["printTime"],str_send))


		str_send=result["completion"]
		if str_send is not None:
			#print type(str_send),str_send,self.printover 
			if self.printover is False and str_send==100:
				#settings().set(["status","motor_disable"],True,force=True)
				self.printover = True
				self._serialManager.send("\x5A\xA5\x04\x80\x03\x00{0}".format(chr(self._settingsManager.get_config()["page_jump"]["print_end"][self._settingsManager.get_config()["machine"]["current_language"]])))

				#print "complete"
			elif  self.printover is True and str_send<1:
				self.printover = False
				self._serialManager.send("\x5A\xA5\x04\x80\x03\x00{0}".format(chr(self._settingsManager.get_config()["page_jump"]["home_page"][self._settingsManager.get_config()["machine"]["current_language"]])))
			str_send=str("%.1f"%str_send)+"%                       "
			
		else:
			str_send="                        "
		self._serialManager.send("\x5A\xA5{0}\x82{1}{2}".format(chr(6+3),self._settingsManager.get_config()["uart_display"]["homepage"]["completion"],str_send))

		if result["paused"] is True:
			self._serialManager.send("\x5A\xA5{0}\x82{1}\x00{2}".format(chr(5),self._settingsManager.get_config()["uart_display"]["print_paused"],chr(39)))
		else:
			self._serialManager.send("\x5A\xA5{0}\x82{1}\x00{2}".format(chr(5),self._settingsManager.get_config()["uart_display"]["print_paused"],chr(38)))
		return result

	def sendCurrentData(self, data):
		with self._temperatureBacklogMutex:
			temperatures = self._temperatureBacklog
			self._temperatureBacklog = []

		with self._logBacklogMutex:
			logs = self._logBacklog
			self._logBacklog = []

		with self._messageBacklogMutex:
			messages = self._messageBacklog
			self._messageBacklog = []

		data.update({
			"temps": temperatures,
			"logs": logs,
			"messages": messages
		})
		
		sync_data["monotor"]=self.deal(data={"current":data})
		#print "sync_data:",sync_data
		#print "sync_sendCurrentData",{"current":data},"sendCurrentData"
	def sendHistoryData(self, data):
		pass
		#("history", data)		
	def addLog(self, data):
		with self._logBacklogMutex:
			self._logBacklog.append(data)

	def addMessage(self, data):
		with self._messageBacklogMutex:
			self._messageBacklog.append(data)

	def addTemperature(self, data):
		with self._temperatureBacklogMutex:
			self._temperatureBacklog.append(data)

#----------------------------------------------------------------------
def DataSyncManager(serialManager=None,settingsManager=None,maxQueneSize=5,printer=None):
	global _instance
	if _instance is None:
		_instance = JsonParser(serialManager,settingsManager,maxQueneSize,printer)
	return _instance


#----------------------------------------------------------------------
def debugJsonParse():
	js = JsonParser()
	print js.deal("{\"current\": {\"logs\": [\"Recv: ok 2406\", \"Send: N2408 G1 F5400 X125.820 Y38.509 E500.71663*0\", \"Recv: ok 2407\", \"Send: N2409 G0 F9000 X125.012 Y38.509*74\", \"Recv: ok 2408\", \"Send: N2410 G1 F5400 X120.492 Y43.030 E501.03925*3\", \"Recv: ok 2409\", \"Send: N2411 G0 F9000 X119.684 Y43.030*70\", \"Recv: ok 2410\", \"Send: N2412 G1 F5400 X124.205 Y38.509 E501.36191*15\", \"Recv: ok 2411\", \"Send: N2413 G0 F9000 X123.397 Y38.509*73\", \"Recv: ok 2412\", \"Send: N2414 G1 F5400 X118.877 Y43.030 E501.68453*10\", \"Recv: ok 2413\", \"Send: N2415 G0 F9000 X118.069 Y43.030*70\", \"Recv: ok 2414\", \"Send: N2416 G1 F5400 X122.590 Y38.509 E502.00719*6\", \"Recv: ok 2415\", \"Send: N2417 G0 F9000 X121.782 Y38.509*79\", \"Recv: ok 2416\", \"Send: N2418 G1 F5400 X117.262 Y43.030 E502.32981*9\", \"Recv: ok 2417\", \"Send: N2419 G0 F9000 X116.454 Y43.030*78\", \"Recv: ok 2418\", \"Send: N2420 G1 F5400 X120.975 Y38.509 E502.65247*11\", \"Recv: ok 2419\", \"Send: N2421 G0 F9000 X120.167 Y38.509*70\", \"Recv: ok 2420\", \"Send: N2422 G1 F5400 X115.647 Y43.030 E502.97509*2\", \"Recv: ok 2421\", \"Send: N2423 G0 F9000 X114.839 Y43.030*66\", \"Recv: ok 2422\", \"Send: N2424 G1 F5400 X119.360 Y38.509 E503.29775*6\", \"Recv: ok 2423\", \"Send: N2425 G0 F9000 X118.552 Y38.509*75\", \"Recv: ok 2424\", \"Send: N2426 G1 F5400 X114.032 Y43.030 E503.62037*0\", \"Recv: ok 2425\", \"Send: N2427 G0 F9000 X113.224 Y43.030*71\", \"Recv: ok 2426\", \"Send: N2428 G1 F5400 X117.745 Y38.509 E503.94303*4\", \"Recv: ok 2427\", \"Send: N2429 G0 F9000 X116.937 Y38.509*70\", \"Recv: ok 2428\", \"Send: N2430 G1 F5400 X112.417 Y43.030 E504.26565*7\", \"Recv: ok 2429\", \"Send: N2431 G0 F9000 X111.609 Y43.030*73\", \"Recv: ok 2430\", \"Send: N2432 G1 F5400 X116.130 Y38.509 E504.58831*7\", \"Recv: ok 2431\", \"Send: N2433 G0 F9000 X115.322 Y38.509*64\", \"Recv: ok 2432\", \"Send: N2434 G1 F5400 X110.802 Y43.030 E504.91093*9\", \"Recv: ok 2433\", \"Send: N2435 G0 F9000 X109.994 Y43.030*79\", \"Recv: ok 2434\", \"Send: N2436 G1 F5400 X114.515 Y38.509 E505.23359*10\", \"Recv: ok 2435\", \"Send: N2437 G0 F9000 X113.707 Y38.509*65\", \"Recv: ok 2436\", \"Send: N2438 G1 F5400 X109.187 Y43.030 E505.55621*15\", \"Recv: ok 2437\", \"Send: N2439 G0 F9000 X108.379 Y43.030*75\", \"Recv: ok 2438\", \"Send: N2440 G1 F5400 X112.900 Y38.509 E505.87887*3\", \"Recv: ok 2439\", \"Send: N2441 G0 F9000 X112.092 Y38.509*74\", \"Recv: ok 2440\", \"Send: N2442 G1 F5400 X107.572 Y43.030 E506.20149*10\", \"Recv: ok 2441\", \"Send: N2443 G0 F9000 X106.764 Y43.030*64\", \"Recv: ok 2442\", \"Send: N2444 G1 F5400 X111.285 Y38.509 E506.52415*14\", \"Recv: ok 2443\", \"Send: N2445 G0 F9000 X110.477 Y38.509*67\", \"Recv: ok 2444\", \"Send: N2446 G1 F5400 X105.957 Y43.030 E506.84677*3\", \"Recv: ok 2445\", \"Send: N2447 G0 F9000 X105.149 Y43.030*78\", \"Recv: ok 2446\", \"Send: N2448 G1 F5400 X109.670 Y38.509 E507.16943*10\", \"Recv: ok 2447\", \"Send: N2449 G0 F9000 X108.862 Y38.509*78\", \"Recv: ok 2448\", \"Send: N2450 G1 F5400 X104.342 Y43.030 E507.49205*10\", \"Recv: ok 2449\", \"Send: N2451 G0 F9000 X103.534 Y43.030*65\", \"Recv: ok 2450\", \"Send: N2452 G1 F5400 X108.055 Y38.509 E507.81471*3\", \"Recv: ok 2451\", \"Send: N2453 G0 F9000 X107.247 Y38.509*71\", \"Recv: ok 2452\", \"Send: N2454 G1 F5400 X102.727 Y43.030 E508.13733*15\", \"Recv: ok 2453\", \"Send: N2455 G0 F9000 X101.919 Y43.030*68\", \"Recv: ok 2454\", \"Send: N2456 G1 F5400 X106.440 Y38.509 E508.45999*5\", \"Recv: ok 2455\", \"Send: N2457 G0 F9000 X105.632 Y38.509*71\", \"Recv: ok 2456\", \"Send: N2458 G1 F5400 X101.112 Y43.030 E508.78261*15\", \"Recv: ok 2457\", \"Send: N2459 G0 F9000 X100.304 Y43.030*79\", \"Recv: ok 2458\", \"Send: N2460 G1 F5400 X104.825 Y38.509 E509.10527*5\", \"Recv: ok 2459\", \"Send: N2461 G0 F9000 X104.017 Y38.509*66\", \"Recv: ok 2460\", \"Send: N2462 G1 F5400 X99.496 Y43.030 E509.42793*63\", \"Recv: ok 2461\", \"Send: N2463 G0 F9000 X98.689 Y43.030*118\", \"Recv: ok 2462\", \"Send: N2464 G1 F5400 X103.210 Y38.509 E509.75059*5\", \"Recv: ok 2463\", \"Send: N2465 G0 F9000 X102.402 Y38.509*64\", \"Recv: ok 2464\", \"Send: N2466 G1 F5400 X97.881 Y43.030 E510.07325*63\", \"Recv: ok 2465\", \"Send: N2467 G0 F9000 X97.074 Y43.030*121\", \"Recv: ok 2466\", \"Send: N2468 G1 F5400 X101.594 Y38.509 E510.39587*6\", \"Recv: ok 2467\", \"Send: N2469 G0 F9000 X100.787 Y38.509*64\", \"Recv: ok 2468\", \"Send: N2470 G1 F5400 X96.266 Y43.030 E510.71853*49\", \"Recv: ok 2469\", \"Send: N2471 G0 F9000 X95.459 Y43.030*119\", \"Recv: ok 2470\", \"Send: N2472 G1 F5400 X99.979 Y38.509 E511.04115*50\", \"Recv: ok 2471\", \"Send: N2473 G0 F9000 X99.172 Y38.509*118\", \"Recv: ok 2472\", \"Send: N2474 G1 F5400 X94.651 Y43.030 E511.36381*49\", \"Recv: ok 2473\", \"Send: N2475 G0 F9000 X93.844 Y43.030*117\", \"Recv: ok 2474\", \"Send: N2476 G1 F5400 X98.364 Y38.509 E511.68643*63\", \"Recv: ok 2475\", \"Send: N2477 G0 F9000 X97.557 Y38.509*127\", \"Recv: ok 2476\", \"Send: N2478 G1 F5400 X93.036 Y43.030 E512.00909*49\", \"Recv: ok 2477\", \"Send: N2479 G0 F9000 X92.868 Y43.198*117\", \"Recv: ok 2478\", \"Send: N2480 G1 F5400 X88.348 Y47.718 E512.33167*63\", \"Recv: ok 2479\", \"Send: N2481 G0 F9000 X88.348 Y48.525*121\", \"Recv: ok 2480\", \"Send: N2482 G1 F5400 X92.868 Y44.006 E512.65422*51\", \"Recv: ok 2481\", \"Send: N2483 G0 F9000 X92.868 Y44.813*125\", \"Recv: ok 2482\", \"Send: N2484 G1 F5400 X88.348 Y49.333 E512.97681*57\", \"Recv: ok 2483\", \"Send: N2485 G0 F9000 X88.348 Y50.140*115\", \"Recv: ok 2484\", \"Send: N2486 G1 F5400 X92.868 Y45.621 E513.29936*52\", \"Recv: ok 2485\", \"Send: N2487 G0 F9000 X92.868 Y46.428*127\", \"Recv: ok 2486\", \"Send: N2488 G1 F5400 X88.348 Y50.948 E513.62195*50\", \"Recv: ok 2487\", \"Send: N2489 G0 F9000 X88.348 Y51.755*124\", \"Recv: ok 2488\", \"Send: N2490 G1 F5400 X92.868 Y47.236 E513.94450*56\", \"Recv: ok 2489\", \"Send: N2491 G0 F9000 X92.868 Y48.043*127\", \"Recv: ok 2490\", \"Send: N2492 G1 F5400 X88.348 Y52.563 E514.26709*58\", \"Recv: ok 2491\", \"Send: N2493 G0 F9000 X88.348 Y53.371*119\", \"Recv: ok 2492\", \"Send: N2494 G1 F5400 X92.868 Y48.851 E514.58967*54\", \"Recv: ok 2493\", \"Send: N2495 G0 F9000 X92.868 Y49.658*118\", \"Recv: ok 2494\", \"Send: N2496 G1 F5400 X88.348 Y54.178 E514.91226*50\", \"Recv: ok 2495\", \"Send: N2497 G0 F9000 X88.348 Y53.921*124\", \"Recv: ok 2496\", \"Send: N2498 G1 F5400 X88.910 Y53.359 E514.95237*57\", \"Recv: ok 2497\", \"Send: N2499 G0 F9000 X88.655 Y54.179*121\", \"Recv: ok 2498\", \"Send: N2500 G1 F5400 X89.475 Y53.359 E515.01089*61\", \"Recv: ok 2499\", \"Send: N2501 G0 F9000 X89.154 Y54.179*126\", \"Recv: ok 2500\", \"Send: N2502 G1 F5400 X92.868 Y50.466 E515.27592*54\", \"Recv: ok 2501\", \"Send: N2503 G0 F9000 X92.868 Y51.273*124\", \"Recv: ok 2502\", \"Send: N2504 G1 F5400 X89.962 Y54.179 E515.48332*59\", \"Recv: ok 2503\", \"Send: N2505 G0 F9000 X89.787 Y54.179*114\", \"Recv: ok 2504\", \"Send: N2506 G1 F5400 X90.607 Y53.359 E515.54184*56\", \"Recv: ok 2505\", \"Send: N2507 G0 F9000 X90.352 Y54.179*116\", \"Recv: ok 2506\", \"Send: N2508 G1 F5400 X91.172 Y53.359 E515.60036*61\", \"Recv: ok 2507\", \"Send: N2509 G0 F9000 X90.769 Y54.179*118\", \"Recv: ok 2508\", \"Send: N2510 G1 F5400 X92.868 Y52.081 E515.75013*49\", \"Recv: ok 2509\", \"Send: N2511 G0 F9000 X92.868 Y52.888*114\", \"Recv: ok 2510\", \"Send: N2512 G1 F5400 X91.577 Y54.179 E515.84227*56\", \"Recv: ok 2511\", \"Send: N2513 G0 F9000 X91.484 Y54.179*124\", \"Recv: ok 2512\", \"Send: N2514 G1 F5400 X92.304 Y53.359 E515.90079*52\", \"Recv: ok 2513\", \"Send: N2515 G0 F9000 X92.049 Y54.179*124\", \"Recv: ok 2514\", \"Send: N2516 G1 F5400 X92.868 Y53.361 E515.95920*60\", \"Recv: ok 2515\", \"Send: N2517 G0 F9000 X92.384 Y54.179*124\", \"Recv: ok 2516\", \"Send: N2518 G1 F5400 X92.741 Y53.937 E515.99365*56\", \"Recv: ok 2517\", \"Send: N2519 G1 X92.868 Y53.926 E516.00008*81\", \"Recv: ok 2518\", \"Send: N2520 G0 F9000 X90.918 Y54.179*117\", \"Recv: ok 2519\", \"Send: N2521 G1 F5400 X91.738 Y53.359 E516.05860*53\", \"Recv: ok 2520\", \"Send: N2522 G0 F9000 X90.041 Y53.359*117\", \"Recv: ok 2521\", \"Send: N2523 G1 F5400 X89.221 Y54.179 E516.11712*59\", \"Recv: ok 2522\", \"Send: N2524 G0 F9000 X88.348 Y46.910*115\", \"Recv: ok 2523\", \"Send: N2525 G1 F5400 X96.749 Y38.509 E516.71669*58\", \"Recv: ok 2524\", \"Send: N2526 G0 F9000 X95.942 Y38.509*112\", \"Recv: ok 2525\", \"Send: N2527 G1 F5400 X88.348 Y46.103 E517.25867*53\", \"Recv: ok 2526\", \"Send: N2528 G0 F9000 X88.348 Y45.295*122\", \"Recv: ok 2527\", \"Send: N2529 G1 F5400 X95.134 Y38.509 E517.74298*55\", \"Recv: ok 2528\", \"Send: N2530 G0 F9000 X94.327 Y38.509*127\", \"Recv: ok 2529\", \"Send: N2531 G1 F5400 X88.348 Y44.488 E518.16969*54\", \"Recv: ok 2530\", \"Send: N2532 G0 F9000 X88.348 Y43.680*119\", \"Recv: ok 2531\", \"Send: N2533 G1 F5400 X93.519 Y38.509 E518.53874*51\", \"Recv: ok 2532\", \"Send: N2534 G0 F9000 X92.712 Y38.509*127\", \"Recv: ok 2533\", \"Send: N2535 G1 F5400 X88.348 Y42.873 E518.85019*56\", \"Recv: ok 2534\", \"Send: N2536 G0 F9000 X88.348 Y42.065*127\", \"Recv: ok 2535\", \"Send: N2537 G1 F5400 X91.904 Y38.509 E519.10398*58\", \"Recv: ok 2536\", \"Send: N2538 G0 F9000 X91.097 Y38.509*122\", \"Recv: ok 2537\", \"Send: N2539 G1 F5400 X88.348 Y41.258 E519.30017*53\", \"Recv: ok 2538\", \"Send: N2540 G0 F9000 X88.348 Y40.450*126\", \"Recv: ok 2539\", \"Send: N2541 G1 F5400 X90.289 Y38.509 E519.43870*63\", \"Recv: ok 2540\", \"Send: N2542 G0 F9000 X89.482 Y38.509*126\", \"Recv: ok 2541\", \"Send: N2543 G1 F5400 X88.348 Y39.643 E519.51963*52\", \"Recv: ok 2542\", \"Send: N2544 G0 F9000 X88.348 Y38.835*122\", \"Recv: ok 2543\", \"Send: N2545 G1 F5400 X88.674 Y38.509 E519.54289*62\", \"Recv: ok 2544\", \"Send: N2546 G0 F9000 X149.897 Y41.021*78\", \"Recv: ok 2545\", \"Send: N2547 G1 F5400 X150.716 Y40.201 E519.60138*3\", \"Recv: ok 2546\", \"Send: N2548 G0 F9000 X151.158 Y38.370 Z3.300*30\", \"Recv: ok 2547\", \"Send: N2549 G1 F3000 X151.158 Y43.170 E519.84361*0\", \"Recv: ok 2548\", \"Send: N2550 G1 X93.009 Y43.170 E522.77812*92\", \"Recv: ok 2549\", \"Send: N2551 G1 X93.009 Y54.620 E523.35595*92\", \"Recv: ok 2550\", \"Send: N2552 G1 X88.209 Y54.620 E523.59818*85\", \"Recv: ok 2551\", \"Send: N2553 G1 X88.209 Y38.370 E524.41824*95\", \"Recv: ok 2552\", \"Send: N2554 G1 X151.158 Y38.370 E527.59498*107\", \"Recv: ok 2553\", \"Send: N2555 G0 F9000 X151.558 Y37.970*71\", \"Recv: ok 2554\", \"Send: N2556 G1 F2400 X151.558 Y43.570 E527.87759*10\", \"Recv: ok 2555\", \"Send: N2557 G1 X93.409 Y43.570 E530.81210*89\", \"Recv: ok 2556\", \"Send: N2558 G1 X93.409 Y55.020 E531.38992*83\", \"Recv: ok 2557\", \"Send: N2559 G1 X87.809 Y55.020 E531.67253*87\", \"Recv: ok 2558\", \"Send: N2560 G1 X87.809 Y37.970 E532.53296*88\", \"Recv: ok 2559\", \"Send: N2561 G1 X151.558 Y37.970 E535.75008*108\", \"Recv: ok 2560\", \"Send: N2562 G0 F9000 X150.798 Y38.509*65\", \"Recv: ok 2561\", \"Send: N2563 G1 F5400 X151.017 Y38.728 E535.76570*2\", \"Recv: ok 2562\", \"Send: N2564 G0 F9000 X150.349 Y38.509*79\", \"Recv: ok 2563\", \"Send: N2565 G1 F5400 X151.017 Y39.177 E535.81338*11\", \"Recv: ok 2564\", \"Send: N2566 G0 F9000 X150.232 Y38.509*64\", \"Recv: ok 2565\", \"Send: N2567 G1 F5400 X151.017 Y39.294 E535.86940*5\", \"Recv: ok 2566\", \"Send: N2568 G0 F9000 X150.197 Y39.040*75\", \"Recv: ok 2567\", \"Send: N2569 G1 F5400 X151.017 Y39.860 E535.92793*15\", \"Recv: ok 2568\", \"Send: N2570 G0 F9000 X149.542 Y38.509*79\", \"Recv: ok 2569\", \"Send: N2571 G1 F5400 X151.017 Y39.984 E536.03319*0\", \"Recv: ok 2570\", \"Send: N2572 G0 F9000 X151.017 Y40.792*78\", \"Recv: ok 2571\", \"Send: N2573 G1 F5400 X148.734 Y38.509 E536.19613*0\", \"Recv: ok 2572\", \"Send: N2574 G0 F9000 X150.197 Y40.171*75\"], \"offsets\": {}, \"messages\": [\"ok 2406\", \"ok 2407\", \"ok 2408\", \"ok 2409\", \"ok 2410\", \"ok 2411\", \"ok 2412\", \"ok 2413\", \"ok 2414\", \"ok 2415\", \"ok 2416\", \"ok 2417\", \"ok 2418\", \"ok 2419\", \"ok 2420\", \"ok 2421\", \"ok 2422\", \"ok 2423\", \"ok 2424\", \"ok 2425\", \"ok 2426\", \"ok 2427\", \"ok 2428\", \"ok 2429\", \"ok 2430\", \"ok 2431\", \"ok 2432\", \"ok 2433\", \"ok 2434\", \"ok 2435\", \"ok 2436\", \"ok 2437\", \"ok 2438\", \"ok 2439\", \"ok 2440\", \"ok 2441\", \"ok 2442\", \"ok 2443\", \"ok 2444\", \"ok 2445\", \"ok 2446\", \"ok 2447\", \"ok 2448\", \"ok 2449\", \"ok 2450\", \"ok 2451\", \"ok 2452\", \"ok 2453\", \"ok 2454\", \"ok 2455\", \"ok 2456\", \"ok 2457\", \"ok 2458\", \"ok 2459\", \"ok 2460\", \"ok 2461\", \"ok 2462\", \"ok 2463\", \"ok 2464\", \"ok 2465\", \"ok 2466\", \"ok 2467\", \"ok 2468\", \"ok 2469\", \"ok 2470\", \"ok 2471\", \"ok 2472\", \"ok 2473\", \"ok 2474\", \"ok 2475\", \"ok 2476\", \"ok 2477\", \"ok 2478\", \"ok 2479\", \"ok 2480\", \"ok 2481\", \"ok 2482\", \"ok 2483\", \"ok 2484\", \"ok 2485\", \"ok 2486\", \"ok 2487\", \"ok 2488\", \"ok 2489\", \"ok 2490\", \"ok 2491\", \"ok 2492\", \"ok 2493\", \"ok 2494\", \"ok 2495\", \"ok 2496\", \"ok 2497\", \"ok 2498\", \"ok 2499\", \"ok 2500\", \"ok 2501\", \"ok 2502\", \"ok 2503\", \"ok 2504\", \"ok 2505\", \"ok 2506\", \"ok 2507\", \"ok 2508\", \"ok 2509\", \"ok 2510\", \"ok 2511\", \"ok 2512\", \"ok 2513\", \"ok 2514\", \"ok 2515\", \"ok 2516\", \"ok 2517\", \"ok 2518\", \"ok 2519\", \"ok 2520\", \"ok 2521\", \"ok 2522\", \"ok 2523\", \"ok 2524\", \"ok 2525\", \"ok 2526\", \"ok 2527\", \"ok 2528\", \"ok 2529\", \"ok 2530\", \"ok 2531\", \"ok 2532\", \"ok 2533\", \"ok 2534\", \"ok 2535\", \"ok 2536\", \"ok 2537\", \"ok 2538\", \"ok 2539\", \"ok 2540\", \"ok 2541\", \"ok 2542\", \"ok 2543\", \"ok 2544\", \"ok 2545\", \"ok 2546\", \"ok 2547\", \"ok 2548\", \"ok 2549\", \"ok 2550\", \"ok 2551\", \"ok 2552\", \"ok 2553\", \"ok 2554\", \"ok 2555\", \"ok 2556\", \"ok 2557\", \"ok 2558\", \"ok 2559\", \"ok 2560\", \"ok 2561\", \"ok 2562\", \"ok 2563\", \"ok 2564\", \"ok 2565\", \"ok 2566\", \"ok 2567\", \"ok 2568\", \"ok 2569\", \"ok 2570\", \"ok 2571\", \"ok 2572\"], \"job\": {\"estimatedPrintTime\": 3796.982645192328, \"file\": {\"origin\": \"local\", \"date\": 1429713171, \"name\": \"test2.gcode\", \"size\": 1194761}, \"filament\": {\"tool0\": {\"volume\": 17.191632929243475, \"length\": 7229.841089999998}}}, \"temps\": [], \"state\": {\"state\": 6, \"stateString\": \"Printing\", \"flags\": {\"operational\": true, \"paused\": false, \"printing\": true, \"sdReady\": false, \"error\": false, \"ready\": true, \"closedOrError\": false}}, \"currentZ\": 3.3, \"progress\": {\"completion\": 6.992109719014933, \"printTimeLeft\": 92, \"printTime\": 6, \"filepos\": 83539}}}")
	print "aaaaaaaaa<<<<<<<<"


if __name__ == "__main__":
	debugJsonParse()
