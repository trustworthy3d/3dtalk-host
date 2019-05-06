
import threading

from gplSerial import serialManager


def debugSerial():
	serial = serialManager("COM3", 115200)

	def doSend():
		while True:
			print "please input>",
			string = raw_input()
			if string is not None:
				serial.send(string)
				
	def doReceive():
		while True:
			string = serial.receive()
			if string is not None:
				print string
	
	sender = threading.Thread(target=doSend)
	receiver = threading.Thread(target=doReceive)

	sender.start()
	receiver.start()
	
	sender.join()
	receiver.join()
	
if __name__ == '__main__':
	debugSerial()
	