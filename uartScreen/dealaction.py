#!/usr/bin/env python
#-*- coding:utf-8 -*-

from util.httpclient import HttpClientManager
from filelist import Dwin_list
from filelist import FileManager
from octoprint.settings import settings as octoSettings
from settings import settings,default_settings
from datasync import sync_data
from octoprint.server import gcodeManager
import logging,json,threading,os,subprocess,time
from time import sleep 
from binascii import hexlify, unhexlify
from localserver.api import printer
from localserver.api import connection
from localserver.api import files
from localserver.api import job
from util.serial.gplSerial import serialManager
#from octoprint.localserver.api import printer
#from octoprint.localserver.api import connection
#from octoprint.localserver.api import files
#from octoprint.localserver.api import job


_instance=None
toVisualHex = lambda data: " ".join([hexlify(c) for c in data]).upper()
toHex = lambda data: "".join([unhexlify(data[i:i+2]) for i in xrange(0, len(data), 2)])	
read_rtc = "\x5A\xA5\x03\x81\x20\x07" #读取DGUS的实时时钟
#write_rtc= "\x5A\xA5\x0A\x80\x1F\x5A" #向DGUS的实时时钟写时间

class DealAction():
	def __init__(self,addr,port=5000,serialManager=None,fileManager=None,dataSyncManager=None):
		self._logger = logging.getLogger(__name__)
		self.extrude=False
		self._addr=addr
		self._port=port
		self.httpclient=HttpClientManager(addr=self._addr,port=self._port)
		self._serialManager = serialManager
		self._fileManager = fileManager
		self._dataSyncManager=dataSyncManager
		self._active = threading.Event()
		self._active.clear()	
		self._worker = threading.Thread(target=self._work)
		self._worker.daemon = True
		self._worker.start()
		self.reset=0
		self.current_code=0 #used for level bed
		#self.ispause=False
		self.extrude_out=True
		self.extrude_run= False
		self.extrude_times=0 
		self.get_serialNumber  = False
		self._motor_disable = False
		#self.pasue_record={"x":0,"y":0,"z":-10}
	
	def tool_icon_set(self,witch=0,action="on"):
		tool_addr=["\x00\x3c","\x00\x3e","\x00\x3d","\x00\x3f"]
		select_tool_icon={"\x00\x3c":{"on":36,"off":32},
		                  "\x00\x3e":{"on":37,"off":33},
		                  "\x00\x3d":{"on":36,"off":32},
		                  "\x00\x3f":{"on":37,"off":33}
		                  }
		self._serialManager.send("\x5A\xA5{0}\x82{1}\x00{2}".format(chr(5),tool_addr[witch],chr(select_tool_icon[tool_addr[witch]][action]))) 	
	def clear_progress_bar(self):
		select_progress=["\x00\x25","\x00\x26","\x00\x27","\x00\x28","\x00\x29"]
		for i in range(5):
			self._serialManager.send("\x5A\xA5{0}\x82{1}\x00{2}".format(chr(5),select_progress[i],chr(65))) 
	
	def copyFile(self):
		select_progress=["\x00\x25","\x00\x26","\x00\x27","\x00\x28","\x00\x29"]
		while True:
			sleep(0.1)
			#print "dealaction:", gcodeManager._copyPercent#,Dwin_list["select_item"]["item"]
			self._serialManager.send("\x5A\xA5{0}\x82{1}\x00{2}".format(chr(5),select_progress[Dwin_list["select_item"]["item"]],chr(39+int(gcodeManager._copyPercent)/4))) 
			if gcodeManager._copyPercent==100:
				break
	def _work(self):
		tool_action=None
		tool_map={"tool0":"tool0_actual","tool1":"tool1_actual"}
		
		while True:
			for i in range(4):#All extrusion head recovery closed
				self.tool_icon_set(i,"off")
			settings().set(["status","tool"],"null",force=True)
			self._active.wait()
			# brefore load reset
			if self.extrude_out is True:
				self.extrude_out = False
				if sync_data["monotor"]["stateString"] is not None and sync_data["monotor"]["stateString"]=="Operational":
					printer.printerCommand(data= {"commands":settings().get_config()["material"]["init_action"]})	
			extrude_reverse=True
			while  self.extrude==True:
				sleep(1)
				if self.extrude_run or settings().get_config()["status"]["tool"]!="null" and sync_data["monotor"][tool_map[settings().get_config()["status"]["tool"]]]!=None and sync_data["monotor"][tool_map[settings().get_config()["status"]["tool"]]] >=settings().get_config()["status"]["target_temp"]-2:
					self.extrude_run =True
					printer.printerCommand(data= {"command":"G91"})
					if settings().get_config()["status"]["tool_step"]>0:
						self.extrude_times=0
						printer.printerCommand(data= {"command":"G1 E5 F150"})
						sleep(1.5)
					elif settings().get_config()["status"]["tool_step"]<0:
						if extrude_reverse:
							extrude_reverse=False
							printer.printerCommand(data= {"command":"G1 E10 F500"})
							printer.printerCommand(data= {"command":"G1 E-20 F900"})
							sleep(1)
							
						self.extrude_times+=1
						if self.extrude_times<15:
							printer.printerCommand(data= {"command":"G1 E-5 F300"})
							sleep(0.5)
						elif self.extrude_times<60:
							printer.printerCommand(data= {"command":"G1 E-10 F1200"})
						else:
							pass
				printer.printerCommand(data= {"commands":["G90","M105"]})					
			
				
				
	def set_temp(self,payload={"target_temp":0}):
		if payload["target_temp"] in [0,190,230]:
			target_temp = payload["target_temp"]
		else:
			target_temp=0
		if self.extrude is False:
			if settings().get_config()["status"]["target_temp"]==190:
				settings().set(["status","target_temp"],230,force=True)
				self._serialManager.send("\x5A\xA5{0}\x82{1}\x00{2}".format(chr(5),"\x00\x3b",chr(31)))	
			else:
				settings().set(["status","target_temp"],190,force=True)
				self._serialManager.send("\x5A\xA5{0}\x82{1}\x00{2}".format(chr(5),"\x00\x3b",chr(30)))
				
	def tool_ctrl(self,payload={"witchE":"tool0","action":"extrade"}):
		tool_icon_map={"tool0":{"takeback":0,"extrade":1},"tool1":{"takeback":2,"extrade":3}}
		if payload["witchE"] in ["tool0","tool1","tool2"]:
			witchE = payload["witchE"]
		else:
			witchE="tool0"		
		if payload["action"] in ["extrade","takeback"]:
			action = payload["action"]
		else:
			action="extrade"
		step={"extrade":5,"takeback":-5}
		settings().set(["status","tool_step"],step[action],force=True)
		if settings().get_config()["status"]["tool"]!=witchE or settings().get_config()["status"]["last_set_temp"]!=settings().get_config()["status"]["target_temp"]:
			printer.printerToolCommand(request={"command":"target","targets":{witchE:settings().get_config()["status"]["target_temp"]}})
			printer.printerToolCommand(request={"command":"select","tool":witchE})
			settings().set(["status","last_set_temp"],settings().get_config()["status"]["target_temp"],force=True)
			settings().set(["status","tool"],witchE,force=True)
			
		for i in range(4):#All extrusion tool icon recovery closed
			self.tool_icon_set(i,"off")	
		self.tool_icon_set(tool_icon_map[settings().get_config()["status"]["tool"]][action],"on")	
		
		self.extrude=True
		self.extrude_run=False
		self._active.set()
			
	def tool_stop(self,payload=None):
		
		self._active.clear()
		if payload["command"][8]=='\x01':
			self.extrude_out=True
		settings().set(["status","tool"],"null",force=True)
		
		if self.extrude is True:
			pass
			
		self.extrude=False
		self.extrude_run=False
			
		if sync_data["monotor"]["stateString"] is not None:
			if sync_data["monotor"]["stateString"] == "Operational":
				printer.printerToolCommand(request={"command":"target","targets":{"tool0":0}})
				#printer.printerToolCommand(request={"command":"target","targets":{"tool1":0}})				
			else:
				printer.printerToolCommand(request={"command":"target","targets":{"tool0":170}})
				#printer.printerToolCommand(request={"command":"target","targets":{"tool1":0}})
		
		print "tool_stop"
		
			
	def initSystemTime(self, utcMilliSecs=None):
		dat = ""
		if isinstance(utcMilliSecs, float):
			tm_year, tm_mon, tm_mday, tm_hour, tm_min, tm_sec, tm_wday, tm_yday, tm_isdst = time.localtime(utcMilliSecs)
			dat = "{0}{1}{2}{3}{4}{5}{6}{7}".format(write_rtc, chr(tm_year%100), chr(tm_mon), chr(tm_mday), \
		                                                                                        chr(tm_wday), chr(tm_hour), chr(tm_min), chr(tm_sec))
		else:
			dat = read_rtc
		try: self._serialManager.send(dat)
		except: pass
	
	def login_in(self, path="/api/login", username=None, password=None, remember=True, passive=True, callback=None):
		""" login """
		if not (username or password):
			username = "root"
			password = "ouring"
		data = {"user": username, "pass": password, "remember": str(remember).lower(), "passive": str(passive).lower()}
		resp, content = self.httpclient.httpPost(path, data, dataType="x-www-form-urlencoded", callback=callback)
		#print "resp, content =",resp, content
		try:
			if '200' == resp["status"]:
				self.httpclient.setCookie(resp["set-cookie"])
		except: pass
		return resp, content		
	
	def _serial_connect(self,payload={"port":"VIRTUAL","action":"connect"}):

		if isinstance(payload,dict):
			if payload["port"] in ["COM5","VIRTUAL","/dev/ttyACM0"]:
				port = payload["port"]
			else:
				port="VIRTUAL"
			if payload["action"] in ["connect","disconnect"]:
				action = payload["action"]
			else:
				action="connect"
		if sync_data["monotor"]["stateString"] is not None and sync_data["monotor"]["stateString"]!="Operational":
			connection.connectionCommand(request={"command":action,"port":port,"baudrate":115200,"autoconnect":True})
		elif sync_data["monotor"]["stateString"] is None:
			connection.connectionCommand(request={"command":action,"port":port,"baudrate":115200,"autoconnect":True})
		#connection.connectionCommand(request={"command":action,"port":port,"baudrate":115200,"autoconnect":True})
		
	def file_path(self,payload={"path":"local","callback":None}):
		self.clear_progress_bar()
		Dwin_list["select_item"]["page"]=-1 #Avoid to print an empty file
		Dwin_list["page_current"]=0 #Path is changed when switching back to the home page
		if payload["path"] in ["local","usb"]:
			path = payload["path"]
		else:
			path="local"
		Dwin_list["current_path"]=path
		files.changeFilesPath(data={"filespath":path})
		self._fileManager.file_path_update(payload={"filespath":settings().get_config()["filemanager"][path]})
		
	
	def print_ctrl(self,payload={"action":"pause","callback":None}):
		self.clear_progress_bar()
		if payload["action"] in ["print","pause","cancel","copy","delete"]:
			action = payload["action"]
		else:
			action="pause"
		if payload["callback"]!=None:
			callback = payload["callback"]
		else:
			callback=None
		if action=="print" and Dwin_list["select_item"]["page"]==Dwin_list["page_current"]:
			files.gcodeFileCommand(filename=Dwin_list["page_file"][Dwin_list["select_item"]["page"]][Dwin_list["select_item"]["item"]], target="local",request={"command":"select","print":True})
		elif action=="pause" and sync_data["monotor"]["stateString"] is not None and sync_data["monotor"]["stateString"]!="Operational":
			job.controlJob(request={"command":"pause"})	
		elif action=="cancel":
			settings().set(["status","motor_disable"],False,force=True)
			job.controlJob(request={"command":"cancel"})
		elif action=="copy"and Dwin_list["select_item"]["page"]==Dwin_list["page_current"]:
			files.copyFile(data={"filename":Dwin_list["page_file"][Dwin_list["select_item"]["page"]][Dwin_list["select_item"]["item"]],"target":"local"})
			self.copyFile()
		elif action=="delete" and Dwin_list["select_item"]["page"]==Dwin_list["page_current"]:#Only allow operation in the current page
			files.deleteGcodeFile(filename=Dwin_list["page_file"][Dwin_list["select_item"]["page"]][Dwin_list["select_item"]["item"]], target="local")
			if  Dwin_list["select_item"]["page"]!=0 and Dwin_list["page_mod"]==1 and Dwin_list["select_item"]["page"] == Dwin_list["page_total"]:#If the current page only one, delete it after a jump back to the previous page
				Dwin_list["page_current"]-=1
			Dwin_list["select_item"]["page"]=-1 #Avoid multiple delete
			self._fileManager.file_path_update(payload={"filespath":settings().get_config()["filemanager"][Dwin_list["current_path"]]})
	
	def tool_step_set(self,payload={"step":1}):
		if payload["step"] in [1,10]:
			settings().set(["printerParameters","step"],payload["step"],force=True)
			#settings().save(force=True)
		if payload["step"]==1:
			self._serialManager.send("\x5A\xA5{0}\x82{1}\x00{2}".format(chr(5),"\x00\x31",chr(3)))
			self._serialManager.send("\x5A\xA5{0}\x82{1}\x00{2}".format(chr(5),"\x00\x32",chr(4)))
		elif payload["step"]==10:
			self._serialManager.send("\x5A\xA5{0}\x82{1}\x00{2}".format(chr(5),"\x00\x31",chr(2)))
			self._serialManager.send("\x5A\xA5{0}\x82{1}\x00{2}".format(chr(5),"\x00\x32",chr(5)))
		
	def motor_jog(self,payload={"axial":'x',"distance":10}):
		motor_code = "G1 %s%d F%d"%(payload["axial"].upper(),
		                            settings().get_config()["printerParameters"]["step"]*payload["distance"]*settings().get_config()["printerParameters"]["invertAxes"][payload["axial"]],
		                            settings().get_config()["printerParameters"]["movementSpeed"][payload["axial"]]
		                            )
		print "motor_jog"
		if sync_data["monotor"]["stateString"] is not None and sync_data["monotor"]["stateString"]=="Operational":
			printer.printerCommand(data= {"commands":["G91",motor_code,"G90"]})

	def motor_reset(self,payload={"axes":["x","y","z"]}):
	
		if sync_data["monotor"]["stateString"] is not None and sync_data["monotor"]["stateString"]=="Operational":
			printer.printerPrintheadCommand(request= {"command":"home","axes":payload["axes"]})
			
	def level_bed(self,payload={"action":"finish"}):
		if payload["action"] in ["start","next","finish"]:
			action = payload["action"]
		else:
			action="finish"
		if action=="start":
			printer.printerCommand(data= {"commands":settings().get_config()["level_bed"]["start"]})
			self.current_code = 0
		elif action =="next":
			axes_xy=settings().get_config()["level_bed"]["next"][self.current_code]
			if axes_xy is not None:
				printer.printerCommand(data= {"commands":["G1 Z10 F1200","G1 %s F%s"%(axes_xy,settings().get_config()["level_bed"]["level_speed"]),"G1 Z-10 F1200"]})
				self.current_code +=1
			else:
				self._serialManager.send("\x5A\xA5\x04\x80\x03\x00{0}".format(chr(settings().get_config()["page_jump"]["level_bed"][settings().get_config()["machine"]["current_language"]])))
		elif action =="finish":
			self.extrude_flag=False #当调平过后立即换料，此标志将不会被消除。
			printer.printerCommand(data= {"commands":settings().get_config()["level_bed"]["finish"]})
				
	def select_language(self,payload={"language":"chinese"}):
		if payload["language"] in settings().get_config()["machine"]["available_languages"]:
			settings().set(["machine","current_language"],payload["language"],force=True)
		else:
			settings().set(["machine","current_language"],"chinese",force=True)	
		settings().save(force=True)
		
	def fan_ctrl(self,payload=None):

		if settings().get_config()["status"]["fan"] =="disable":
			settings().set(["status","fan"],"enable",force=True)
			printer.printerCommand(data= {"command":"M106"})
			self._serialManager.send("\x5A\xA5{0}\x82{1}\x00{2}".format(chr(5),"\x00\x40",chr(20)))
		elif settings().get_config()["status"]["fan"]=="enable":
			settings().set(["status","fan"],"disable",force=True)
			printer.printerCommand(data= {"command":"M106 S0"})
			self._serialManager.send("\x5A\xA5{0}\x82{1}\x00{2}".format(chr(5),"\x00\x40",chr(21)))
					
	def motor_disable(self,payload=None):
		settings().set(["status","motor_disable"],True,force=True)
		if sync_data["monotor"]["stateString"] is not None and sync_data["monotor"]["stateString"]=="Operational":	
			if settings().get_config()["machine"]["current_type"] in ["3DTALK MINI"]:
				printer.printerCommand(data= {"commands":["G90","G1 Z150 F500","G90"]})
			printer.printerCommand(data= {"command":"M84"})	
		
		
	def water_cooling(self,payload=None):
		if settings().get_config()["status"]["water_cooling"]=="disable":
			settings().set(["status","water_cooling"],"enable",force=True)
			printer.printerCommand(data= {"command":"PumpOn"})
			self._serialManager.send("\x5A\xA5{0}\x82{1}\x00{2}".format(chr(5), settings().get_config()["uart_display"]["water_cooling"],chr(67)))
		elif settings().get_config()["status"]["water_cooling"]=="enable":
			settings().set(["status","water_cooling"],"disable",force=True)	
			printer.printerCommand(data= {"command":"PumpOff"})
			self._serialManager.send("\x5A\xA5{0}\x82{1}\x00{2}".format(chr(5), settings().get_config()["uart_display"]["water_cooling"],chr(66)))
	def chamber(self,payload=None):
		#print "action_chamber"
		if sync_data["monotor"]["stateString"] is not None and sync_data["monotor"]["stateString"]=="Operational":
			self.water_cooling()
			if settings().get_config()["status"]["chamber"] =="disable":
				# ##############################控制水冷###############################
				settings().set(["status","water_cooling"],"enable",force=True)
				printer.printerCommand(data= {"command":"PumpOn"})
				self._serialManager.send("\x5A\xA5{0}\x82{1}\x00{2}".format(chr(5), settings().get_config()["uart_display"]["water_cooling"],chr(67)))	
				# #####################################################################
				
				settings().set(["status","chamber"],"enable",force=True)
				printer.printerToolCommand(request={"command":"target","targets":{"tool2":50}})
				printer.printerBedCommand(request={"command":"target","target":50})
				#print settings().get_config()["uart_display"]["pre_heat"]
				self._serialManager.send("\x5A\xA5{0}\x82{1}\x00{2}".format(chr(5), settings().get_config()["uart_display"]["pre_heat"],chr(29)))
			elif settings().get_config()["status"]["chamber"]=="enable":
				# ##############################控制水冷###############################
				settings().set(["status","water_cooling"],"disable",force=True)
				printer.printerCommand(data= {"command":"PumpOff"})
				self._serialManager.send("\x5A\xA5{0}\x82{1}\x00{2}".format(chr(5), settings().get_config()["uart_display"]["water_cooling"],chr(66)))			
				# #####################################################################
				
				settings().set(["status","chamber"],"disable",force=True)
				printer.printerToolCommand(request={"command":"target","targets":{"tool2":0}})
				printer.printerBedCommand(request={"command":"target","target":0})
				self._serialManager.send("\x5A\xA5{0}\x82{1}\x00{2}".format(chr(5), settings().get_config()["uart_display"]["pre_heat"],chr(28)))
			
	def factory_reset(self,payload=None):
		self.reset=1
		#print "factory_reset"
	def hotspot_reset(self,payload=None):
		self.reset=2
		#print "hotspot_reset"
	def wipe_userdata(self,payload=None):
		self.reset=3
		#print "wipe_userdata"	
	def reset_confirm(self,payload=None):
		
		print "self.reset:",self.reset
		if self.reset==1:
			while os.path.exists("/.uartscreen"):
				self.executeSystemCommand("sudo rm /.uartscreen -Rf")
				sleep(1)
			while os.path.exists("/.octoprint"):
				if os.path.exists("/root/.octoprint"):
					self.executeSystemCommand("sudo rm /root/.octoprint -Rf")
				self.executeSystemCommand("sudo rm /.octoprint -Rf")
				sleep(1)
			if os.path.exists("/udisk/update"):
				if os.path.exists("/home/pi/OctoPrint.egg/octoprint_org/src/octoprint"):
					self.executeSystemCommand("sudo rm /home/pi/OctoPrint.egg/octoprint_org/src/octoprint -Rf")
					sleep(1.5)

				if os.path.exists("/home/pi/OctoPrint.egg/octoprint_org/src/octoprint") is  False:
					self.executeSystemCommand("sudo cp /udisk/update/src/octoprint /home/pi/OctoPrint.egg/octoprint_org/src/ -Rf")
				sleep(0.5)
				self._serialManager.send("\x5A\xA5\x04\x80\x03\x00{0}".format(chr(settings().get_config()["page_jump"]["update"][settings().get_config()["machine"]["current_language"]])))
				self.executeSystemCommand("sudo cp /udisk/update/src/octoprint/uartScreen/script/etc/network/* /etc/network/ -Rf")
				self.executeSystemCommand("sudo cp /udisk/update/src/octoprint/uartScreen/script/usr/bin/* /usr/bin/ -Rf")
				
				sleep(1)
				self.dgus_update()
			else:
				#self.executeSystemCommand("sudo wipe_userdata")
				self.executeSystemCommand("sudo create_wifi {0} 12345678".format(settings().get_config()["machine"]["serialNumber"]))
				self._serialManager.send("\x5A\xA5\x04\x80\x03\x00{0}".format(chr(settings().get_config()["page_jump"]["home_page"][settings().get_config()["machine"]["current_language"]])))
				
		elif self.reset==2:
			self.executeSystemCommand("sudo create_wifi {0} 12345678".format(settings().get_config()["machine"]["serialNumber"]))
			self._serialManager.send("\x5A\xA5\x04\x80\x03\x00{0}".format(chr(settings().get_config()["page_jump"]["home_page"][settings().get_config()["machine"]["current_language"]])))
			
		elif self.reset==3:
			self.executeSystemCommand("sudo wipe_userdata")
			self._serialManager.send("\x5A\xA5\x04\x80\x03\x00{0}".format(chr(settings().get_config()["page_jump"]["home_page"][settings().get_config()["machine"]["current_language"]])))
		self.reset=0
		

	def setSystemTime(self, path="/api/system/time", utcMilliSecs=None, callback=None):
		if utcMilliSecs is None:
			return self.httpclient.httpGet(path, callback=callback)
		else:
			data = {"utcMilliSecs": utcMilliSecs}
			#print "utcMilliSecs::",data
			return self.httpclient.httpPost(path, data, callback=callback)
			
	def executeSystemCommand(self, command):
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
			
	def delayToDoSomething(self, secs=3, action=None, **kws):
			def delay(secs, action, **kws):
				time.sleep(secs)
				if action and callable(action):
					action(**kws)
		
			temp = threading.Thread(target=delay, args=(secs, action), kwargs=kws)
			temp.daemon = True
			temp.start()
			
	def getMethodsMap(self):
		_funcs_dict = {}
		funcs_name = filter(lambda et:et.startswith("action"), dir(self))
		for func_name in funcs_name:
			func = getattr(self, func_name)
			if func and callable(func):
				_funcs_dict[func_name] = func
	
		return _funcs_dict
	def action_time_init(self,payload=None):
		#print "action_time_init",payload["command"]
		cmd=payload["command"]
		try:
			t = (2000+(ord(cmd[6])/16)*10+ord(cmd[6])%16,(ord(cmd[7])/16)*10+ord(cmd[7])%16,(ord(cmd[8])/16)*10+ord(cmd[8])%16,(ord(cmd[10])/16)*10+ord(cmd[10])%16,(ord(cmd[11])/16)*10+ord(cmd[11])%16,(ord(cmd[12])/16)*10+ord(cmd[12])%16, 0, 0, 0)
			utcMilliSecs = time.mktime(t)
			self.delayToDoSomething(secs=5,action=self.setSystemTime,utcMilliSecs=utcMilliSecs)
	
		except:
			print "error inittime"
			pass
		
	def machine_type_init(self,payload={"type":"3DTALK MINI"}):
		if settings().get(["firstrun"]) or os.path.exists("/udisk/update"):
			#print " firstrun action_machine_type:",payload["type"]	
			settings().set(["machine","current_type"],payload["type"],force=True)
			if payload["type"] in ["3DTALK MINI"]:
				settings().set(["page_jump","update"],{"chinese":10,"english":10,"chinese_tw":10},force=True)
			if payload["type"] in ["3DTALK II"]:
				settings().set(["printerParameters","platform"],{"x":255,"y":255,"z":200},force=True)
				settings().set(["printerParameters","invertAxes"],{"x":1,"y":1,"z":-1},force=True)
				settings().set(["printerParameters","movementSpeed"],{"x": 6000,"y": 6000,"z": 1200,"e": 300},force=True)
				settings().set(["level_bed","level_speed"],3200,force=True)
				settings().set(["level_bed","start"],["G28","G21","G90"],force=True)
				settings().set(["level_bed","next"],{0:"X127 Y22",1:"X221 Y226",2:"X33 Y226",3:"X127 Y113",4:None},force=True)
				settings().set(["level_bed","finish"],["G1 Z100 F900","G28 X0Y0"],force=True)
				settings().set(["material","init_action"],["G21","G90","G28","G1 X127 Y127 Z100 F900"],force=True)
				settings().set(["page_jump","home_page"],{"chinese":1,"english":19,"chinese_tw":37},force=True)
				settings().set(["page_jump","print_end"],{"chinese":16,"english":34,"chinese_tw":52},force=True)
				settings().set(["page_jump","level_bed"],{"chinese":8,"english":26,"chinese_tw":44},force=True)
				settings().set(["page_jump","update"],{"chinese":17,"english":35,"chinese_tw":53},force=True)
	
			elif payload["type"] in ["3DTALK PRO400"]:
				settings().set(["printerParameters","platform"],{"x":380,"y":360,"z":396},force=True)
				settings().set(["printerParameters","invertAxes"],{"x":1,"y":-1,"z":-1},force=True)
				settings().set(["printerParameters","movementSpeed"],{"x": 6000,"y": 6000,"z": 1200,"e": 300},force=True)
				settings().set(["level_bed","level_speed"],6000,force=True)
				settings().set(["level_bed","start"],["G28","G21","G90"],force=True)
				settings().set(["level_bed","next"],{0:"X40 Y40",1:"X360 Y40",2:"X360 Y360",3:"X40 Y360",4:"X190 Y180",5:None},force=True)
				settings().set(["level_bed","finish"],["G1 Z145 F1500","G1 Y30 F9000","G28 X0Y0"],force=True)
				settings().set(["material","init_action"],["G21","G90","G28 X0 Y0","G1 X190 Y360 F3200","M84"],force=True)
				settings().set(["page_jump","home_page"],{"chinese":1,"english":14,"chinese_tw":37},force=True)
				settings().set(["page_jump","print_end"],{"chinese":9,"english":22,"chinese_tw":45},force=True)
				settings().set(["page_jump","level_bed"],{"chinese":7,"english":20,"chinese_tw":43},force=True)
				settings().set(["page_jump","update"],{"chinese":0,"english":0,"chinese_tw":0},force=True)
			elif payload["type"] in ["3DTALK PRO600"]:
				pass
				
			settings().set(["firstrun"],False,force=True)
			settings().save(force=True)
			
		self._serialManager.send("\x5A\xA5\x04\x80\x03\x00{0}".format(chr(settings().get(["page_jump","home_page"])[settings().get(["machine","current_language"])])))
	
		
	def action_machine_type(self,payload=None):
		if ord(payload["command"][8])<len(settings().get(["machine","available_type"])): 
			self.machine_type_init(payload={"type":settings().get(["machine","available_type"])[ord(payload["command"][8])]})	
		
	def action_init(self,payload=None):
		if settings().get(["firstrun"]) or os.path.exists("/udisk/update"):
			self._serialManager.send("\x5A\xA5\x04\x80\x03\x00{0}".format(chr(0)))
			if  os.path.exists("/udisk/update"):
				self.reset=1
				self.reset_confirm()
				#verson_now="verson_now"//避免重复升级
				#verson_new="verson_new"
				#with open('/home/pi/OctoPrint.egg/octoprint_org/src/octoprint/uartScreen/verson') as vf_now:
					#verson_now=vf_now.readline()
				#with open('/home/pi/udisk/update/src/octoprint/uartScreen/verson') as vf_new:
					#verson_new=vf_new.readline()
				
				#if verson_now!=verson_new:
					#self.reset=1
					#self.reset_confirm()
				#else:
					#self._serialManager.send("\x5A\xA5\x04\x80\x03\x00{0}".format(chr(settings().get(["page_jump","home_page"])[settings().get(["machine","current_language"])])))	
		
		else:
			#if settings().get(["machine","current_type"]) in ["3DTALK II"]:
				#self._serialManager.send("\x5A\xA5\x04\x80\x03\x00{0}".format(chr(settings().get(["page_jump","check_jump"])[settings().get(["machine","current_language"])])))	
			#else:
			self._serialManager.send("\x5A\xA5\x04\x80\x03\x00{0}".format(chr(settings().get(["page_jump","home_page"])[settings().get(["machine","current_language"])])))			
		
		self._serialManager.send(read_rtc)
		
		settings().set(["status","target_temp"],190,force=True)#The original icon icon to 190 degrees Celsius 
		self._serialManager.send("\x5A\xA5{0}\x82{1}\x00{2}".format(chr(5),"\x00\x3b",chr(30)))
		settings().set(["status","fan"],"disable",force=True)
		self._serialManager.send("\x5A\xA5{0}\x82{1}\x00{2}".format(chr(5),"\x00\x40",chr(21)))		
		
		if settings().get_config()["printerParameters"]["step"]==10:
			self._serialManager.send("\x5A\xA5{0}\x82{1}\x00{2}".format(chr(5),"\x00\x31",chr(2)))
			self._serialManager.send("\x5A\xA5{0}\x82{1}\x00{2}".format(chr(5),"\x00\x32",chr(5)))
		else:
			self._serialManager.send("\x5A\xA5{0}\x82{1}\x00{2}".format(chr(5),"\x00\x31",chr(3)))
			self._serialManager.send("\x5A\xA5{0}\x82{1}\x00{2}".format(chr(5),"\x00\x32",chr(4)))	
		self._serialManager.send("\x5A\xA5{0}\x82{1}\x00{2}".format(chr(5), settings().get_config()["uart_display"]["pre_heat"],chr(28)))	
		self._serialManager.send("\x5A\xA5{0}\x82{1}\x00{2}".format(chr(5), settings().get_config()["uart_display"]["water_cooling"],chr(66)))
		
		self._serialManager.send("\x5A\xA5{0}\x82{1}\x00{2}".format(chr(5), settings().get_config()["uart_display"]["languages"]["status"],chr(0)))	
		
	def action_serial_connect(self,payload={"port":"VIRTUAL","action":"connect"}):
		#self.delayToDoSomething(secs=2,action=self.login_in)
		self.delayToDoSomething(secs=1,action=self._serial_connect,payload=payload)
		
	def action_file_path(self,payload=None):
		#print "action_file_path",payload
		self.file_path(payload={"path":["local","usb"][ord(payload["command"][8])],"callback":self._fileManager.list_update})
	def action_value(self,payload=None):
		#print "action_value",payload
		self._fileManager.file_path_update(ord(payload["command"][8])-1)
		
	def action_slected_line(self,payload=None):
		#print "action_slected_line",payload
		if ord(payload["command"][8]) in range(5):
			self._fileManager.high_light_selection(payload={"selctline":ord(payload["command"][8])})
	
	def action_print_ctrl(self,payload=None):
		#print "action_print_ctrl",payload
		if ord(payload["command"][8]) in range(5):
			self.print_ctrl(payload={"action":["print","pause","cancel","delete","copy"][ ord(payload["command"][8])],"callback":[None,None,None,self._fileManager.list_update,None][ ord(payload["command"][8])]})
	
	def action_language(self,payload=None):
		#print "action_language"
		if ord(payload["command"][8]) in range(3):
			self.select_language(payload={"language":["chinese","chinese_tw","english"][ord(payload["command"][8])]})
		
	def action_level_bed(self,payload=None):
		#print "action_level_bed"
		if sync_data["monotor"]["stateString"] is not None and sync_data["monotor"]["stateString"]=="Operational":
			if ord(payload["command"][8]) in range(3):
				self.level_bed(payload={"action":["start","next","finish"][ord(payload["command"][8])]})		
	
	def action_temp_select(self,payload=None):
		#print "action_temp_select"
		self.set_temp()
		
	def action_material(self,payload=None):
		#print "action_material",payload
		if ord(payload["command"][7]) in range(2) and ord(payload["command"][8]) in range(2):
			if sync_data["monotor"]["stateString"] is not None and sync_data["monotor"]["stateString"]!="Printing":			
				self.tool_ctrl(payload={"witchE":["tool0","tool1"][ord(payload["command"][7])],"action":["takeback","extrude"][ord(payload["command"][8])]})	
	def action_material_stop(self,payload=None):
		#print "action_tool_stop"
		self.tool_stop(payload)
		
	def action_step(self,payload=None):
		#print "action_step",payload
		if ord(payload["command"][8]) in [1,10]:
			self.tool_step_set(payload={"step":ord(payload["command"][8])})
			
	def action_move(self,payload=None):
		#print "action_move",payload
		if sync_data["monotor"]["stateString"] is not None and sync_data["monotor"]["stateString"]=="Operational":
			if ord(payload["command"][7]) in range(3) and ord(payload["command"][8]) in range(2):
				self.motor_jog(payload={"axial":['x','y','z'][ord(payload["command"][7])],"distance":[1,-1][ord(payload["command"][8])]})
	def action_move_continuous(self,payload=None):	
		#print "action_move_continuous",ord(payload["command"][8])	
		#printer.printerCommand(data= {"commands":["G91","G1 X-1 F600","G90"]})	
		#if ord(payload["command"][8])%5==0:
		if sync_data["monotor"]["stateString"] is not None and sync_data["monotor"]["stateString"]=="Operational":
			#printer.printerCommand(data= {"commands":["G91","G1 Z-1 F600","G90"]})	
			self._xyz_move_continuous("z", -1)
			
	def action_x_left_continuous(self,payload=None):
		if sync_data["monotor"]["stateString"] is not None and sync_data["monotor"]["stateString"]=="Operational":
			#printer.printerCommand(data= {"commands":["G91","G1 X1 F600","G90"]})
			self._xyz_move_continuous("x", 1)
				
	def action_x_right_continuous(self,payload=None):
		if sync_data["monotor"]["stateString"] is not None and sync_data["monotor"]["stateString"]=="Operational":
			#printer.printerCommand(data= {"commands":["G91","G1 X-1 F600","G90"]})	
			self._xyz_move_continuous("x", -1)
				
	def action_y_forward_continuous(self,payload=None):
		if sync_data["monotor"]["stateString"] is not None and sync_data["monotor"]["stateString"]=="Operational":
			#printer.printerCommand(data= {"commands":["G91","G1 Y1 F600","G90"]})
			self._xyz_move_continuous("y", 1)
				
	def action_y_backward_continuous(self,payload=None):
		if sync_data["monotor"]["stateString"] is not None and sync_data["monotor"]["stateString"]=="Operational":
			#printer.printerCommand(data= {"commands":["G91","G1 Y-1 F600","G90"]})
			self._xyz_move_continuous("y", -1)
				
	def action_z_up_continuous(self,payload=None):
		if sync_data["monotor"]["stateString"] is not None and sync_data["monotor"]["stateString"]=="Operational":
			#printer.printerCommand(data= {"commands":["G91","G1 Z-1 F600","G90"]})
			self._xyz_move_continuous("z", -1)
				
	def action_z_down_continuous(self,payload=None):
		if sync_data["monotor"]["stateString"] is not None and sync_data["monotor"]["stateString"]=="Operational":
			#printer.printerCommand(data= {"commands":["G91","G1 Z1 F600","G90"]})
			self._xyz_move_continuous("z", 1)
			
	def _xyz_move_continuous(self, axis, amount):
		moveRange = octoSettings().get(["printerParameters", "moveRange", axis])
		axisCurPos = printer.printer._axisCurPos[axis]
		targetPos = axisCurPos + amount
		if moveRange > 0:
			#ranges = range(0, moveRange+1, 1)
			if targetPos < 0 or targetPos > moveRange:
				return
		else:
			#ranges = range(0, moveRange-1, -1)
			if targetPos > 0 or targetPos < moveRange:
				return
		printer.printerCommand(data={"commands":["G91", "G1 %s%.4f F600" % (axis.upper(), amount), "G90"]})
		printer.printer._axisCurPos[axis] = targetPos
				
	def action_reset(self,payload=None):
		#print "action_reset",payload
		if sync_data["monotor"]["stateString"] is not None and sync_data["monotor"]["stateString"]=="Operational":
			if ord(payload["command"][8]) in [0,1]:
				self.motor_reset(payload={"axes":[["x","y"],["z"]][ord(payload["command"][8])]})
	
	def action_switch(self,payload=None):
		print "action_switch",payload
		if ord(payload["command"][8]) in range(4):
			[self.fan_ctrl,self.motor_disable,self.water_cooling,self.chamber][ord(payload["command"][8])]()			
		
	def action_setings(self,payload=None):
		print "action_setings",payload
		if ord(payload["command"][8]) in [1,2,3]:
			self.reset=ord(payload["command"][8])
		elif ord(payload["command"][8]) in [4]:
			self.reset_confirm()		
		
	def action_timer(self,payload=None):
		print "action_timer"
		#self._dataSyncManager.reloadip()
		#self._dataSyncManager.reloadip()
		if self.get_serialNumber is False:
			try:
				sn=printer.getSerialNumber()
				if sn!="C000000000":
					self.get_serialNumber = True
					settings().set(["machine","serialNumber"],sn,force=True)
					settings().save(force=True)	
			except:
				pass	
			
	def dgus_update(self):
		
		try:
			self._serialManager._close()
		except:
			print "close again"
			try:
				self._serialManager._close()
			except:
				print "close error"
		sleep(1)
		serial = serialManager(port="/dev/ttyUSB0", baudrate=115200, enable_seriallog=True)
		sleep(1)
		DWIN_SET_PATH="/udisk/update/DWIN_SET"
		
		font0_lib_head=['\x5A','\xA5','\x04','\x80','\xF3','\x5A',chr(0)]
		font66_lib_head=['\x5A','\xA5','\x04','\x80','\xF3','\x5A',chr(66)]
		ico_lib_head=['\x5A','\xA5','\x04','\x80','\xF3','\x5A',chr(40)]
		config_13_head=['\x5A','\xA5','\x04','\x80','\xF3','\x5A','\x0D']
		config_14_head=['\x5A','\xA5','\x04','\x80','\xF3','\x5A','\x0E']
		
		
		if os.path.exists("{0}/0_DWIN_ASC.HZK".format(DWIN_SET_PATH)):
			f=open('{0}/0_DWIN_ASC.HZK'.format(DWIN_SET_PATH), 'rb')
			count=0	
			font0_lib_bin=f.read(256*1024)
			for i in ico_lib_head:		
				serial._serial.write(i)	
			
			while True:
				recv = serial.receive()
				sleep(0.01)
				if recv is not None:
					print "recv: ", recv,"len:",len(font0_lib_bin)
					
					for i in font0_lib_bin:
						
							serial._serial.write(i)
					sleep(1)
					if len(font0_lib_bin)<256*1024:
						print "complete font0_lib load"
						break
					
					count+=1
					font0_lib_bin=f.read(256*1024)
					font0_lib_head[6]=chr(0+count)
					for i in font0_lib_head:		
						serial._serial.write(i)				
							
			f.close()	
		
		if os.path.exists('{0}/66_宋12.DZK'.format(DWIN_SET_PATH)):
			f=open('{0}/66_宋12.DZK'.format(DWIN_SET_PATH), 'rb')
			count=0	
			font66_lib_bin=f.read(256*1024)
			for i in ico_lib_head:		
				serial._serial.write(i)	
			
			while True:
				recv = serial.receive()
				sleep(0.01)
				if recv is not None:
					print "recv: ", recv,"len:",len(font66_lib_bin)
					
					for i in font66_lib_bin:
						
							serial._serial.write(i)
					sleep(1)
					if len(font66_lib_bin)<256*1024:
						print "complete font66_lib load"
						break
					
					count+=1
					font66_lib_bin=f.read(256*1024)
					font66_lib_head[6]=chr(66+count)
					for i in font66_lib_head:		
						serial._serial.write(i)				
							
			f.close()	
		
		if os.path.exists('{0}/40.ICO'.format(DWIN_SET_PATH)):
			f=open('{0}/40.ICO'.format(DWIN_SET_PATH), 'rb')
			count=0	
			ico_lib_bin=f.read(256*1024)
			for i in ico_lib_head:		
				serial._serial.write(i)	
			
			while True:
				recv = serial.receive()
				sleep(0.01)
				if recv is not None:
					print "recv: ", recv,"len:",len(ico_lib_bin)
					
					for i in ico_lib_bin:
						
							serial._serial.write(i)
					sleep(1)
					if len(ico_lib_bin)<256*1024:
						print "complete ico_lib_bin load"
						break
					
					count+=1
					ico_lib_bin=f.read(256*1024)
					ico_lib_head[6]=chr(40+count)
					for i in ico_lib_head:		
						serial._serial.write(i)				
							
			f.close()	
		
		if os.path.exists('{0}/13.bin'.format(DWIN_SET_PATH)):
			f=open('{0}/13.bin'.format(DWIN_SET_PATH), 'rb')
			config_13_bin=f.read()
			f.close()
			
			for i in config_13_head:		
				serial._serial.write(i)	
				
			while True:
				recv = serial.receive()
				sleep(0.01)
				if recv is not None:
					print "recv: ", recv
					for i in config_13_bin:
							serial._serial.write(i)
					sleep(1)
					print "complete 13.bin load"
					break	
				
		if os.path.exists('{0}/14.bin'.format(DWIN_SET_PATH)):	
			f=open('{0}/14.bin'.format(DWIN_SET_PATH), 'rb')
			config_14_bin=f.read()
			f.close()				
			for i in config_14_head:		
				serial._serial.write(i)	
						
			while True:
				recv = serial.receive()
				sleep(0.01)
				if recv is not None:
					print "recv: ", recv
					for i in config_14_bin:
							serial._serial.write(i)
					sleep(1)
					print "complete 14.bin load"
					break						
		
		load_img_list=sorted(filter(lambda et:et.endswith(".bmp"), os.listdir(DWIN_SET_PATH)))
		print load_img_list
		
		#for i in load_img_list:
		for bmp_i in load_img_list:
			print int(bmp_i.replace(".bmp",""))
			list_str=['\x5A','\xA5','\x06','\x80','\xF5','\x5A','\x00','\x00',chr(int(bmp_i.replace(".bmp","")))]
			
			f=open('{0}/{1}'.format(DWIN_SET_PATH,bmp_i), 'rb')
			bmp_head=f.read(54)
			biWidth=ord(bmp_head[21])*0x1000000+ord(bmp_head[20])*0x10000+ord(bmp_head[19])*0x100+ord(bmp_head[18])
			biHeight=ord(bmp_head[25])*0x1000000+ord(bmp_head[24])*0x10000+ord(bmp_head[23])*0x100+ord(bmp_head[22])
			#print "biWidth:%d"%(biWidth),"biHeight:%d"%(biHeight)
			bmp_body=f.read()
			f.close()
			
			img5r6g5b=[]
			for i in range(biWidth*biHeight):
				b=ord(bmp_body[3*i])&0xF8
				g=ord(bmp_body[3*i+1])&0xFC
				r=ord(bmp_body[3*i+2])&0xF8
				img5r6g5b.append((r + (g >> 5))&0xff)
				img5r6g5b.append((((g << 3) + (b >> 3))&0xff))	
				

			for i in list_str:		
				serial._serial.write(i)	
				
			while True:
					recv = serial.receive()
					sleep(0.01)
					if recv is not None:
						print "recv: ", recv
						for i in range(biHeight):
							for j in range(biWidth*2):
								serial._serial.write(chr(img5r6g5b[biWidth*2*(biHeight-1-i)+j]))
						sleep(1)
						#serial._serial.write("\x5A\xA5{0}\x82{1}{2}".format(chr(12+3),self._settingsManager.get_config()["uart_display"]["about"]["versons"],chr(int(bmp_i.replace(".bmp","")))))
						#serial._serial.write("\x5A\xA5\x04\x80\x03\x00{0}".format(chr(0)))
						serial._serial.write("\x5A\xA5\x04\x80\x03\x00{0}".format(chr(int(bmp_i.replace(".bmp","")))))
						#sleep(1)
						break
		serial._serial.write("\x5A\xA5\x04\x80\x03\x00{0}".format(chr(100)))
		
		while os.path.exists("/udisk/update"):
			sleep(1)
		self.executeSystemCommand("sudo reboot")
				
										
def ActionManager(addr="127.0.0.1",port=5000,serialManager=None,fileManager=None,dataSyncManager=None):
	global _instance
	if _instance is None:
		print "_instance ActionManager"
		_instance=DealAction(addr,port,serialManager,fileManager,dataSyncManager)
	return _instance

if __name__=="__main__":
	ac=ActionManager()
	ac.serial_connect("ttyUSB0","disconnect")
	print "ok"
