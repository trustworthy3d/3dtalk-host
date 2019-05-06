# coding=utf-8

__author__ = "Lars Norpchen"
__author__ = "Gina Häußge <osd@foosel.net>"
__license__ = 'GNU Affero General Public License http://www.gnu.org/licenses/agpl.html'

import logging
import Queue
import threading

_instance = None

def eventManager():
	global _instance
	if _instance is None:
		_instance = EventManager()
	return _instance


class EventManager(object):
	"""
	Handles receiving events and dispatching them to subscribers
	"""

	def __init__(self):
		self._registeredListeners = {}
		self._logger = logging.getLogger(__name__)

		self._queue = Queue.PriorityQueue()
		self._worker = threading.Thread(target=self._work)
		self._worker.daemon = True
		self._worker.start()

	def _work(self):
		while True:
			(event, payload) = self._queue.get(True)
			eventListeners = self._registeredListeners.get(event, None)
			if eventListeners is None:
				return
			self._logger.debug("Firing event: %s (Payload: %r)" % (event, payload))

			for listener in eventListeners:
				self._logger.debug("Sending action to %r" % listener)
				try:
					listener(event, payload)
				except:
					self._logger.exception("Got an exception while sending event %s (Payload: %r) to %s" % (event, payload, listener))

	def fire(self, event, payload=None):
		"""
		Fire an event to anyone subscribed to it

		Any object can generate an event and any object can subscribe to the event's name as a string (arbitrary, but
		case sensitive) and any extra payload data that may pertain to the event.

		Callbacks must implement the signature "callback(event, payload)", with "event" being the event's name and
		payload being a payload object specific to the event.
		"""
		#print "in fire"
		if not event in self._registeredListeners.keys():
			return
		self._queue.put((event, payload), 0)

	def subscribe(self, event, callback):
		"""
		Subscribe a listener to an event -- pass in the event name (as a string) and the callback object
		"""

		if not event in self._registeredListeners.keys():
			self._registeredListeners[event] = []

		if callback in self._registeredListeners[event]:
			# callback is already subscribed to the event
			return

		self._registeredListeners[event].append(callback)
		self._logger.debug("Subscribed listener %r for event %s" % (callback, event))

	def unsubscribe (self, event, callback):
		"""
		Unsubscribe a listener from an event -- pass in the event name (as string) and the callback object
		"""

		if not event in self._registeredListeners:
			# no callback registered for callback, just return
			return

		if not callback in self._registeredListeners[event]:
			# callback not subscribed to event, just return
			return

		self._registeredListeners[event].remove(callback)
		self._logger.debug("Unsubscribed listener %r for event %s" % (callback, event))


class GenericEventListener(object):
	"""
	The GenericEventListener can be subclassed to easily create custom event listeners.
	"""

	def __init__(self):
		self._logger = logging.getLogger(__name__)

	def subscribe(self, events):
		"""
		Subscribes the eventCallback method for all events in the given list.
		"""

		for event in events:
			eventManager().subscribe(event, self.eventCallback)

	def unsubscribe(self, events):
		"""
		Unsubscribes the eventCallback method for all events in the given list
		"""

		for event in events:
			eventManager().unsubscribe(event, self.eventCallback)

	def eventCallback(self, event, payload):
		"""
		Actual event callback called with name of event and optional payload. Not implemented here, override in
		child classes.
		"""
		pass
