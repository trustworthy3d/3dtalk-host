#!/usr/bin/env python
# -*- coding: gbk-*-
from settings import settings,key_actions
from datasync import sync_data
from werkzeug.utils import secure_filename
import json,os

GCODE_EXTENSIONS = ["gcode", "gco", "g", "3dt"] #modify by kevin, for support *.3dt file
STL_EXTENSIONS = ["stl"]
SUPPORTED_EXTENSIONS = GCODE_EXTENSIONS + STL_EXTENSIONS

_instance=None
Dwin_list={
    "list_addr":["\x03\x00","\x03\x30","\x03\x60","\x03\x90","\x03\xC0"],
    "status":"idle",
    "current_path":"local",
    "page_size":5,
    "page_total":0,
    "page_current":0,
    "select_item":{"page":-1,"item":0},
    "available_select":0,
    "page_file":[],
    "page_mod":0
}
class FileList():
	def __init__(self,serialManager=None):
		self._serialManager = serialManager
		self._uploadFolder = None
		self.content ={"files":[]}
	#print "__init__"
	
	def _getBasicFilename(self, filename):
		if filename.startswith(self._uploadFolder):
			return filename[len(self._uploadFolder + os.path.sep):]
		else:
			return filename
		
	def isGcodeFileName(self,filename):
		return "." in filename and filename.rsplit(".", 1)[1].lower() in GCODE_EXTENSIONS
	
	def isSTLFileName(self,filename):
		return "." in filename and filename.rsplit(".", 1)[1].lower() in STL_EXTENSIONS	
	
	def isAllowedFile(self,filename, extensions):
		return "." in filename and filename.rsplit(".", 1)[1] in extensions
	
	def getAbsolutePath(self, filename, mustExist=True):
		filename = self._getBasicFilename(filename)

		if not self.isAllowedFile(filename.lower(), set(SUPPORTED_EXTENSIONS)):
			return None

		# TODO: detect which type of file and add in the extra folder portion 
		secure = os.path.join(self._uploadFolder, secure_filename(self._getBasicFilename(filename)))
		if mustExist and (not os.path.exists(secure) or not os.path.isfile(secure)):
			return None

		return secure
	
	def getFileData(self, filename):
		if not filename:
			return

		filename = self._getBasicFilename(filename)
		
		# TODO: Make this more robust when STLs will be viewable from the client
		if self.isSTLFileName(filename):
			return
		
		absolutePath = self.getAbsolutePath(filename)
		if absolutePath is None:
			return None
	
		statResult = os.stat(absolutePath)
		fileData = {
	                "name": filename,
	                "size": statResult.st_size,
	                "origin": self._uploadFolder,
	                "date": int(statResult.st_ctime)
	        }
		return fileData	
	
	
	def getAllFileData(self, path):
		files = []
		for osFile in os.listdir(path):
			fileData = self.getFileData(osFile)
			if fileData is not None:
				files.append(fileData)
		return files
	
	def getFileList(self,filespath):
		files = self.getAllFileData(filespath)
		 
		return files

	def deal(self, data, callback=None):	
		if isinstance(data, str):
			try:
				data = json.loads(data)
			except:
				return
		result = []
		page_files={}
		filetotalnum = len(data["files"])
		data["files"].sort(key=lambda obj:obj.get('date'))
		data["files"].reverse()
		Dwin_list["page_total"]=filetotalnum/Dwin_list["page_size"]
		Dwin_list["page_mod"]=filetotalnum%Dwin_list["page_size"] #To avoid the end the empty pages
		if(filetotalnum>0):	    
			for page in range(Dwin_list["page_total"]):
				for key in range(Dwin_list["page_size"]):
					page_files[key]=data["files"][page*Dwin_list["page_size"]+key]["name"]
				result.append(page_files)
				page_files={}
			for key in range(filetotalnum%Dwin_list["page_size"]):
				page_files[key]=data["files"][filetotalnum-filetotalnum%Dwin_list["page_size"]+key]["name"]
			result.append(page_files)
			#print result
		return result
	def file_path_update(self,resp=0,payload=None):
			
		if payload is not None:
			self._uploadFolder=payload["filespath"]
			self.content["files"]=self.getFileList(self._uploadFolder)
			if self.content["files"] != None:
				Dwin_list["page_file"]=self.deal(self.content)
			
		elif resp < Dwin_list["page_total"]:
			Dwin_list["page_current"]=resp
		elif Dwin_list["page_mod"]==0:#Avoid at the end of the empty pages
			Dwin_list["page_current"]=Dwin_list["page_total"]-1
		else:
			Dwin_list["page_current"]=Dwin_list["page_total"]
		self._serialManager.send("\x5A\xA5{0}\x82{1}\x00{2}".format(chr(5),"\x00\x2d",chr(Dwin_list["page_current"]+1)))	

		if len(Dwin_list["page_file"])!=0:  
			file_num=len(Dwin_list["page_file"][Dwin_list["page_current"]])
			Dwin_list["available_select"]=file_num
		else:
			file_num=0
			
		if Dwin_list["page_current"]!=Dwin_list["select_item"]["page"]:
			self.high_light_selection()
		else:
			self.high_light_selection(payload={"selctline":Dwin_list["select_item"]["item"]})
			
		for index in range(Dwin_list["page_size"]):
			str_send="                        "
			self._serialManager.send("\x5A\xA5{0}\x82{1}{2}".format(chr(len(str_send)+3),Dwin_list["list_addr"][index],str_send))	
		if(file_num>0):
			for index in range(file_num):
				str_send=Dwin_list["page_file"][Dwin_list["page_current"]][index]+"                        "
				self._serialManager.send("\x5A\xA5{0}\x82{1}{2}".format(chr(24+3),Dwin_list["list_addr"][index],str_send))
		
		if file_num==0 and Dwin_list["current_path"]!="local":
			return True		
		return False
	
		
		
	def list_update(self,resp=0,content=None):
		#when content is None means that page change otherwise means file path change,the resp also has multifunction

		if content!=None:
			#print "good",content
			Dwin_list["page_file"]=self.deal(content)
			
		elif resp < Dwin_list["page_total"]:
			Dwin_list["page_current"]=resp
		elif Dwin_list["page_mod"]==0:#Avoid at the end of the empty pages
			Dwin_list["page_current"]=Dwin_list["page_total"]-1
		else:
			Dwin_list["page_current"]=Dwin_list["page_total"]
		self._serialManager.send("\x5A\xA5{0}\x82{1}\x00{2}".format(chr(5),"\x00\x2d",chr(Dwin_list["page_current"]+1)))	

		if len(Dwin_list["page_file"])!=0:  
			file_num=len(Dwin_list["page_file"][Dwin_list["page_current"]])
			Dwin_list["available_select"]=file_num
		else:
			file_num=0
			
		if Dwin_list["page_current"]!=Dwin_list["select_item"]["page"]:
			self.high_light_selection()
		else:
			self.high_light_selection(payload={"selctline":Dwin_list["select_item"]["item"]})
			
		for index in range(Dwin_list["page_size"]):
			str_send="                        "
			self._serialManager.send("\x5A\xA5{0}\x82{1}{2}".format(chr(len(str_send)+3),Dwin_list["list_addr"][index],str_send))	
		if(file_num>0):
			for index in range(file_num):
				str_send=Dwin_list["page_file"][Dwin_list["page_current"]][index]+"                        "
				self._serialManager.send("\x5A\xA5{0}\x82{1}{2}".format(chr(24+3),Dwin_list["list_addr"][index],str_send))
		
		if file_num==0 and Dwin_list["current_path"]!="local":
			return True		
		return False
	

	def high_light_selection(self,payload={"selctline":-1}):
		if isinstance(payload,dict):
			if payload["selctline"] in [-1,0,1,2,3,4]:
				selctline = payload["selctline"]
			else:
				selctline=-1	
		if selctline<Dwin_list["available_select"]:
			if sync_data["monotor"]["stateString"] is not None and sync_data["monotor"]["stateString"]!="Operational":
				selctline=-1#Only the Operational status allows printing
			if selctline!=-1:#Print documents only changes here 
				Dwin_list["select_item"]["item"]=selctline
				Dwin_list["select_item"]["page"]=Dwin_list["page_current"]
			for i in range(5):
				if i==selctline:
					self._serialManager.send("\x5A\xA5\x05\x82{0}\xF8\x00".format(key_actions["print"]["discrible"][i]))	
				else:
					self._serialManager.send("\x5A\xA5\x05\x82{0}\x00\x00".format(key_actions["print"]["discrible"][i]))


def FileManager(serialManager=None):
	global _instance
	if _instance is None:
		_instance=FileList(serialManager)
	return _instance

if __name__=="__main__":
	hc=FileManager()
	print "ok"
