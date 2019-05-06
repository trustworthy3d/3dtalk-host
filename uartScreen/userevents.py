# coding=utf-8

__author__ = "Lars Norpchen"
__author__ = "Gina Häußge <osd@foosel.net>"
__license__ = 'GNU Affero General Public License http://www.gnu.org/licenses/agpl.html'

import logging
import Queue
import threading
from util.events import GenericEventListener
from util.events import eventManager


class CommandTrigger(GenericEventListener):
		
	def __init__(self, action):
		GenericEventListener.__init__(self)
		self._logger = logging.getLogger(__name__)
		self._action = action
		self._subscriptions = {}

		self._initSubscriptions()	

	def _initSubscriptions(self):
		"""
		Subscribes all events as defined in "events > $triggerType > subscriptions" in the settings with their
		respective commands.
		"""
		eventsToSubscribe = []
		
		
		for event in self._action.getMethodsMap():

			if not event in self._subscriptions.keys():
				self._subscriptions[event] = []
			self._subscriptions[event].append(self._action.getMethodsMap()[event])

			if not event in eventsToSubscribe:
				eventsToSubscribe.append(event)
		self.subscribe(eventsToSubscribe)

	def eventCallback(self, event, payload):
		"""
		Event callback, iterates over all subscribed commands for the given event, processes the command
		string and then executes the command via the abstract executeCommand method.
		"""

		GenericEventListener.eventCallback(self, event, payload)

		if not event in self._subscriptions:
			return
		for callback in self._subscriptions[event]:
			try:
				if isinstance(callback, (tuple, list, set)):
					processedCommand = []
					for c in callback:
						c(payload)
				else:
					callback(payload)
			except KeyError, e:
				self._logger.warn("There was an error processing one or more placeholders in the following callback: %s" % callback)

