#-*- coding=utf-8 -*-

import os               #平台相关模块
import glob             #文件搜索模块

try:
	import _winreg      #windows注册表
except:
	pass

#
#自动搜索可用的串口号
#specifiedSerial：指定特定的串口号
#additionalSerials: 附加的串口号
#
def getSerialList(specifiedSerial=None, additionalSerials=[]):
	serialList = []
	if os.name == "nt":       #windows平台
		try:
			key = _winreg.OpenKey(_winreg.HKEY_LOCAL_MACHINE,"HARDWARE\\DEVICEMAP\\SERIALCOMM")
			i = 0
			while(True):
				serialList += [_winreg.EnumValue(key, i)[1]]
				i += 1
		except:
			pass		
	elif os.name == "posix":  #Linux平台
		serialList = serialList \
		    + glob.glob("/dev/ttyUSB*") \
		    + glob.glob("/dev/ttyACM*") \
		    + glob.glob("/dev/ttyAMA*") \
		    + glob.glob("/dev/tty.usb*") \
		    + glob.glob("/dev/cu.*") \
		    + glob.glob("/dev/cuaU*") \
		    + glob.glob("/dev/rfcomm*")
	
	for additionalSerial in additionalSerials:
		if additionalSerial not in serialList:
			serialList.append(additionalSerial)
			
	if specifiedSerial in serialList:
		serialList.remove(specifiedSerial)
		serialList.insert(0, specifiedSerial)
		
	return serialList


#
#返回一系列常用波特率
#specifiedSerial：指定特定的波特率
#additionalSerials: 附加的波特率
#
def getBaudrateList(specifiedBaudrate=None, additionalBaudrates=[]):
	baudrateList = [250000, 230400, 115200, 57600, 38400, 19200, 9600]
	
	for additionalBaudrate in additionalBaudrates:
		if additionalBaudrate not in baudrateList:
			baudrateList.append(additionalBaudrate)
			
	if specifiedBaudrate in baudrateList:
		baudrateList.remove(specifiedBaudrate)
		baudrateList.insert(0, specifiedBaudrate)
		
	return baudrateList


if __name__ == "__main__":
	print "current serial port list:", getSerialList()
	print "common baudrate list:", getBaudrateList()