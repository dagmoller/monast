
# Copyright (c) 2008, Diego Aguirre
# All rights reserved.
# 
# Redistribution and use in source and binary forms, with or without modification,
# are permitted provided that the following conditions are met:
# 
#     * Redistributions of source code must retain the above copyright notice, 
#       this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright notice, 
#       this list of conditions and the following disclaimer in the documentation 
#       and/or other materials provided with the distribution.
#     * Neither the name of the DagMoller nor the names of its contributors
#       may be used to endorse or promote products derived from this software 
#       without specific prior written permission.
# 
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED 
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED.
# IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, 
# INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, 
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, 
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF 
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE 
# OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED 
# OF THE POSSIBILITY OF SUCH DAMAGE.

import sys
import pprint
import re
import thread
import threading
import time
import traceback
import socket
import Queue
import logging

import distutils.sysconfig
PYTHON_VERSION = distutils.sysconfig.get_python_version()

## Basic Logger
if float(PYTHON_VERSION) >= 2.4:
	logging.basicConfig(
		format  = "[%(asctime)s] %(levelname)-8s :: %(message)s",
		datefmt = '%a %b %d %H:%M:%S %Y'
	)
else:
	print "AsteriskManager is incompatible with your Python version (%s)" % PYTHON_VERSION
	print "It requires Python >= 2.4"
	sys.exit(1)

logging.NOTICE = 60	
logging.addLevelName(logging.NOTICE, "NOTICE")
log = logging.getLogger("AsteriskManager")


class AsteriskManager(threading.Thread):
	
	host     = None
	port     = None
	username = None
	password = None
	
	running         = True
	isConnected     = False
	isAuthenticated = False
	
	AMIVersion = None
	
	socket = None
	
	recvQueue = Queue.Queue()
	sendQueue = Queue.Queue()
	
	ping           = False
	pong           = False
	
	eventHandlers  = {}
	actionHandlers = {}
	
	tRead      = None
	tPing      = None
	tRecvQueue = None
	rSendQueue = None
	
	nextActionID = 0
	
	def __init__(self, host, port, username, password):
		
		log.log(logging.NOTICE, 'AsteriskManager :: Initializing...')
		
		self.host     = host
		self.port     = port
		self.username = username
		self.password = password
		
		threading.Thread.__init__(self)

	
	def threadRead(self, name, params):
		
		log.info('AsteriskManager.threadRead :: Starting Thread...')
		while self.running:
			try:
				buffer = ""
				while not buffer.endswith('\r\n\r\n'):
					buffer += self.socket.recv(1024)
				
				messages = buffer.strip().split('\r\n\r\n')
				for message in messages:
					self.recvQueue.put(message)
			
			except socket.error, e:
				if self.running:
					log.error('AsteriskManager.threadRead :: Error reading socket: %s' % e)
					self.isConnected = False
					time.sleep(10)
				
			except:
				log.exception('AsteriskManager.threadRead :: Unhandled Exception')
				self.isConnected = False
				time.sleep(10)
	
	
	def threadPing(self, name, params):
		
		log.info('AsteriskManager.threadPing :: Starting Thread...')
		time.sleep(60)
		count = 0
		while self.running:
			if self.isConnected:
				if self.ping and self.pong:
					log.info('AsteriskManager.threadPing :: PONG')
					self.ping = False
					self.pong = False
					time.sleep(60)
				
				if not self.ping and not self.pong:
					log.info('AsteriskManager.threadPing :: PING')
					count     = 0
					self.ping = True
					self.execute(['Action: PING'])
				
				if self.ping and not self.pong:
					if count == 60:
						log.warn('AsteriskManager.threadPing :: Ping timeout after 60 seconds. Reconnecting...')
						self.isConnected = False
						self.ping        = False
						self.disconnect()
					count += 1
					
			time.sleep(1)
			
				
	def threadRecvQueue(self, name, params):
		
		log.info('AsteriskManager.threadRecvQueue :: Starting Thread...')
		while self.running:
			msg = self.recvQueue.get()
			msg = msg.strip()
			log.debug(msg)
			
			if msg == 'Response: Pong':
				self.pong = True
				continue
			
			gAuth = re.compile('Asterisk Call Manager/([^\s^\r^\n]*)\r\nResponse: ([^\s^\r^\n]*)\r\nMessage: (.*)$').match(msg)
			if gAuth:
				self.AMIVersion = gAuth.group(1)
				response        = gAuth.group(2)
				message         = gAuth.group(3)
				
				if response == 'Error' and message == 'Authentication failed':
					log.error('AsteriskManager.threadRecvQueue :: Authentication failed')
				
				if response == 'Success' and message == 'Authentication accepted':
					log.log(logging.NOTICE, 'AsteriskManager.threadRecvQueue :: Authentication accepted')
					self.isAuthenticated = True									
			
			# Event Handlers
			gEvent = re.compile('^Event:[\s]([^\r^\n^\s]*)').match(msg)
			if gEvent:
				event = gEvent.group(1)
				try:
					if self.eventHandlers.has_key(event):
						log.info('AsteriskManager.threadRecvQueue :: Executing EventHandler for Event: %s' % event)
						self.eventHandlers[event](msg.split('\r\n'))
					elif self.eventHandlers.has_key('_DEFAULT'):
						log.info('AsteriskManager.threadRecvQueue :: Executing _DEFAULT handler for Event: %s' % event)
						self.eventHandlers['_DEFAULT'](msg.split('\r\n'))
					else:
						log.info('AsteriskManager.threadRecvQueue :: Unhandled Event %s' % event)
				except:
					log.exception('AsteriskManager.threadRecvQueue :: Unhandled Exception in EventHandler for Event %s' % event)
				
				continue
			
			# Responses with ActionID
			gActionID = re.compile('ActionID:[\s]([^\r^\n^\s]*)').search(msg)
			if gActionID:
				ActionID = gActionID.group(1)
				try:
					if self.actionHandlers.has_key(ActionID):
						log.info('AsteriskManager.threadRecvQueue :: Executing ActionHandler for ActionID: %s' % ActionID)
						self.actionHandlers[ActionID](msg.split('\r\n'))
					else:
						log.info('AsteriskManager.threadRecvQueue :: Unhandled Response for ActionID %s' % ActionID)
				except:
					log.exception('AsteriskManager.threadRecvQueue :: Unhandled Exception in ActionHandler for ActionID %s' % ActionID)
				
				if self.actionHandlers.has_key(ActionID):
					log.info('AsteriskManager.threadRecvQueue :: Unregister ActionHandler for ActionID: %s' % ActionID)
					del self.actionHandlers[ActionID]
					
				continue
			
	
	def threadSendQueue(self, name, params):
		
		log.info('AsteriskManager.threadSendQueue :: Starting Thread...')
		
		while self.running:
			if self.isConnected:
				lines = self.sendQueue.get()
				try:
					log.debug('%s' % '\r\n'.join(lines))
					self.socket.send('%s\r\n\r\n' % '\r\n'.join(lines))
				except socket.error, e:
					log.error('AsteriskManager.threadSendQueue :: Error sendind data: %s' % e)
			
			time.sleep(0.02)
					
	
	def getNextActionID(self):
		
		self.nextActionID += 1
		return 'ID.%06d' % self.nextActionID
	
	
	def execute(self, lines, handler = None, ActionID = None):
		
		if handler:
			if not ActionID:
				ActionID = self.getNextActionID()
			lines.append('ActionID: %s' % ActionID)
			log.info('AsteriskManager.execute :: Register ActionHandler for ActionID: %s' % ActionID)
			self.actionHandlers[ActionID] = handler
		
		self.sendQueue.put(lines)
	
	
	def login(self):
		log.log(logging.NOTICE, 'AsteriskManager.login :: Logging in...')
		self.execute(['Action: login', 'Username: %s' % self.username, 'Secret: %s' % self.password])
		
		
	def logoff(self):
		log.log(logging.NOTICE, 'AsteriskManager.logoff :: Logging off...')
		self.isAuthenticated = False
		self.execute(['Action: logoff'])
				
	
	def connect(self):
		
		while not self.isConnected:
			self.isAuthenticated = False
			try:
				log.log(logging.NOTICE, 'AsteriskManager.connect :: Trying to connect to %s:%s' % (self.host, self.port))
				self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
				self.socket.connect((self.host, self.port))
				self.isConnected = True
				self.login()
			except socket.error, e:
				log.error('AsteriskManager.connect :: Error connecting to %s:%s -- %s' % (self.host, self.port, e))
				time.sleep(30)
				
			if not self.tRead:
				self.tRead      = thread.start_new_thread(self.threadRead, ('threadRead', 1))
				self.tPing      = thread.start_new_thread(self.threadPing, ('threadPing', 1))
				self.tRecvQueue = thread.start_new_thread(self.threadRecvQueue, ('threadRecvQueue', 1))
				self.tSendQueue = thread.start_new_thread(self.threadSendQueue, ('threadSendQueue', 1))
	
	
	def disconnect(self):
		
		log.log(logging.NOTICE, 'AsteriskManager.disconnect :: Closing connection to %s:%s' % (self.host, self.port))
		try:
			self.socket.shutdown(2) # same as socket.SHUT_RDWR
			self.socket.close()
		except socket.error, e:
			log.error('AsteriskManager.disconnect :: Error closing connection to %s:%s -- %s' % (self.host, self.port, e))
	
	
	def close(self):
		
		log.log(logging.NOTICE, 'AsteriskManager.close :: Finishing...')
		self.running = False
	
				
	def registerEventHandler(self, event, handler):
		
		log.info('AsteriskManager.registerEventHandler :: Register EnventHandler: %s' % event)
		self.eventHandlers[event] = handler
		
		
	def unregisterEventHandler(self, event):
		
		log.info('AsteriskManager.unregisterEventHandler :: Unregister EnventHandler: %s' % event)
		try:
			del self.eventHandlers[event]
		except:
			log.error('AsteriskManager.unregisterEventHandler :: Event Handler not found: %s' % event)
			
			
	def run(self):
		
		try:
			while self.running:
				time.sleep(1)
				if not self.isConnected:
					self.connect()
		except:
			log.exception('AsteriskManager.run :: Unhandled Exception')
			self.running = False
		
		self.running = False
		if self.isAuthenticated:
			self.logoff()
			time.sleep(2)
		self.disconnect()
		
