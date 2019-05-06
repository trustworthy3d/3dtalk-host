from __future__ import absolute_import

import os, threading, logging, time

try:
	from octoprint.util.avr_isp import stk500v2
	from octoprint.util.avr_isp import ispBase
	from octoprint.util.avr_isp import intelHex
	
	from octoprint.settings import settings
	from octoprint.server import printer
except:
	from avr_isp import stk500v2
	from avr_isp import ispBase
	from avr_isp import intelHex


class InstallFirmware():
	def __init__(self, filename=None, port=None, progressCallback=None):
		self._logger = logging.getLogger(__name__)
		if port is None:
			port = settings().sureSerialPort()
		if filename is None:
			filename = getDefaultFirmware()
		if filename is None:
			self._logger.warn("has no firmware file!")
			return
		
		self._filename = filename
		self._port = port

		threading.Thread(target=self.run, args=(progressCallback,)).start()

	def run(self, progressCallback=None):
		try: printer.disconnect()
		except: pass
		time.sleep(0.5)

		hexFile = intelHex.readHex(self._filename)
		programmer = stk500v2.Stk500v2()
		programmer.progressCallback = progressCallback if progressCallback else self.onProgress

		try: programmer.connect(self._port)
		except ispBase.IspError:
			self._logger.error('Failed to find machine for firmware upgrade! Is your machine had been connected?')
				
		if programmer.isConnected():
			self._logger.info("Uploading firmware...")
			try:
				programmer.programChip(hexFile)
				self._logger.info("Done! Installed firmware: %s" % (os.path.basename(self._filename)))
			except ispBase.IspError as e:
				self._logger.error("Failed to write firmware.\n" + str(e))
			try: programmer.close()
			except: pass
			time.sleep(0.5)

		printer.connect(port=self._port, baudrate=settings().get(["serial", "baudrate"]))
		
	def onProgress(self, value, max):
		print value, max


if __name__ == "__main__":
	InstallFirmware("D:/dtemp/arduino/Repetier.cpp.hex", "COM5")
	import time
	time.sleep(30)
