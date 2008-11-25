#!/usr/bin/python -u

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

import os
import re
import sys
sys.path.append('amapi')
import time
import pprint
import thread
import threading
import traceback
import socket
import random
import Queue
import logging
import optparse
from AsteriskManager import AsteriskManager
from ConfigParser import SafeConfigParser

import distutils.sysconfig
PYTHON_VERSION = distutils.sysconfig.get_python_version()

MONAST_CALLERID = "MonAst WEB"

AST_DEVICE_STATES = { # copied from include/asterisk/devicestate.h
	'0': 'Unknown',
	'1': 'Not In Use',
	'2': 'In Use',
	'3': 'Busy',
	'4': 'Invalid',
	'5': 'Unavailable',
	'6': 'Ringing',
	'7': 'Ring, In Use',
	'8': 'On Hold'
}

COLORS = {
	'black'  : 30,
	'red'    : 31,
	'green'  : 32,
	'yellow' : 33,
	'blue'   : 34,
	'magenta': 35,
	'cyan'   : 36,
	'white'  : 37
}

## deamonize

## Global Logger
logging.NOTICE = 60
logging.addLevelName(logging.NOTICE, "NOTICE")

LEVEL_COLORS = {
	logging.NOTICE   : 'white',
	logging.INFO     : 'yellow',
	logging.ERROR    : 'red',
	logging.WARNING  : 'magenta',
	logging.DEBUG    : 'cyan',
}

class ColorFormatter(logging.Formatter):
	def __init__(self, fmt = None, datefmt = None):
		logging.Formatter.__init__(self, fmt, datefmt)
	
	def color(self, levelno, msg):
		return '\033[%d;1m%s\033[0m' % (COLORS[LEVEL_COLORS[levelno]], msg)
	
	def formatTime(self, record, datefmt):
		if hasattr(logging, 'COLORED'):
			return '\033[37;1m%s\033[0m' % logging.Formatter.formatTime(self, record, datefmt)
		else:
			return logging.Formatter.formatTime(self, record, datefmt)
	
	def format(self, record):
		if record.levelname == 'DEBUG':
			record.msg = record.msg.encode('string_escape')
		
		if hasattr(logging, 'COLORED'):
			record.name      = self.color(record.levelno, record.name)
			record.module    = self.color(record.levelno, record.module)
			record.msg       = self.color(record.levelno, record.msg)
			record.levelname = self.color(record.levelno, record.levelname)

			if float(PYTHON_VERSION) >= 2.5:
				record.funcName  = self.color(record.levelno, record.funcName)
			
			if record.exc_info:
				record.exc_text  = self.color(record.levelno, '>> %s' % self.formatException(record.exc_info).replace('\n', '\n>> '))
		
		return logging.Formatter.format(self, record)


class MyConfigParser(SafeConfigParser):
	def optionxform(self, optionstr):
		return optionstr


class MonAst:
	
	##
	## Internal Params
	##
	
	running         = True
	
	configFile      = None
	
	AMI             = None
	
	bindPort        = None
	socketClient    = None
	
	defaultContext  = None
	transferContext = None
	
	meetmeContext   = None
	meetmePrefix    = None
	
	userDisplay     = {}
	
	enqueue        = Queue.Queue()
	
	clientSocks    = {}
	clientQueues   = {}
	parked         = {}
	meetme         = {}
	calls          = {}
	channels       = {}
	monitoredUsers = {}
	queues         = {}

	clientSockLock     = threading.RLock()
	clientQueuelock    = threading.RLock()
	parkedLock         = threading.RLock()
	meetmeLock         = threading.RLock()
	callsLock          = threading.RLock()
	channelsLock       = threading.RLock()
	monitoredUsersLock = threading.RLock()
	queuesLock         = threading.RLock()
	
	channelStatus = []
	
	queueMemberStatus = {}
	queueClientStatus = {}
	
	queueStatusFirst = False
	queueStatusOrder = []
	
	##
	## Class Initialization
	##
	def __init__(self, configFile):
		
		log.log(logging.NOTICE, 'MonAst :: Initializing...')
		
		self.configFile = configFile
		
		cp = MyConfigParser()
		cp.read(self.configFile)
		
		host     = cp.get('global', 'hostname')
		port     = int(cp.get('global', 'hostport'))
		username = cp.get('global', 'username')
		password = cp.get('global', 'password')
		
		self.bindPort       = int(cp.get('global', 'bind_port'))
		
		self.defaultContext  = cp.get('global', 'default_context')
		self.transferContext = cp.get('global', 'transfer_context')
		
		self.meetmeContext = cp.get('global', 'meetme_context')
		self.meetmePrefix  = cp.get('global', 'meetme_prefix')
		
		if cp.get('users', 'default') == 'show':
			self.userDisplay['DEFAULT'] = True 
		else:
			self.userDisplay['DEFAULT'] = False
		
		for user, display in cp.items('users'):
			if user.startswith('SIP') or user.startswith('IAX2'): 
				if (self.userDisplay['DEFAULT'] and display == 'hide') or (not self.userDisplay['DEFAULT'] and display == 'show'):
					self.userDisplay[user] = True
			
			if display == 'force':
				tech, peer = user.split('/')
				self.monitoredUsers[user] = {'Channeltype': tech, 'Status': '--', 'Calls': 0, 'CallerID': '--', 'Context': self.defaultContext, 'Variables': []}
				
		try:
			self.socketClient = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			self.socketClient.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
			self.socketClient.bind(('0.0.0.0', self.bindPort))
			self.socketClient.listen(10)
		except socket.error, e:
			log.error("MonAst.__init__ :: Cound not open socket on port %d, cause: %s" % (self.bindPort, e))
			sys.exit(1)
			
		self.AMI = AsteriskManager(host, port, username, password)
		
		self.AMI.registerEventHandler('Reload', self.handlerReload)
		self.AMI.registerEventHandler('ChannelReload', self.handlerChannelReload)
		self.AMI.registerEventHandler('PeerEntry', self.handlerPeerEntry)
		self.AMI.registerEventHandler('PeerStatus', self.handlerPeerStatus)
		self.AMI.registerEventHandler('Newchannel', self.handlerNewchannel)
		self.AMI.registerEventHandler('Newstate', self.handlerNewstate)
		self.AMI.registerEventHandler('Hangup', self.handlerHangup)
		self.AMI.registerEventHandler('Dial', self.handlerDial)
		self.AMI.registerEventHandler('Link', self.handlerLink)
		self.AMI.registerEventHandler('Unlink', self.handlerUnlink)
		self.AMI.registerEventHandler('Newcallerid', self.handlerNewcallerid)
		self.AMI.registerEventHandler('Rename', self.handlerRename)
		self.AMI.registerEventHandler('MeetmeJoin', self.handlerMeetmeJoin)
		self.AMI.registerEventHandler('MeetmeLeave', self.handlerMeetmeLeave)
		self.AMI.registerEventHandler('ParkedCall', self.handlerParkedCall)
		self.AMI.registerEventHandler('UnParkedCall', self.handlerUnParkedCall)
		self.AMI.registerEventHandler('ParkedCallTimeOut', self.handlerParkedCallTimeOut)
		self.AMI.registerEventHandler('ParkedCallGiveUp', self.handlerParkedCallGiveUp)
		self.AMI.registerEventHandler('Status', self.handlerStatus)
		self.AMI.registerEventHandler('StatusComplete', self.handlerStatusComplete)
		self.AMI.registerEventHandler('QueueMemberAdded', self.handlerQueueMemberAdded)
		self.AMI.registerEventHandler('QueueMemberRemoved', self.handlerQueueMemberRemoved)
		self.AMI.registerEventHandler('Join', self.handlerJoin) # Queue Join
		self.AMI.registerEventHandler('Leave', self.handlerLeave) # Queue Leave
		self.AMI.registerEventHandler('QueueCallerAbandon', self.handlerQueueCallerAbandon)
		self.AMI.registerEventHandler('QueueParams', self.handlerQueueParams)
		self.AMI.registerEventHandler('QueueMember', self.handlerQueueMember)
		self.AMI.registerEventHandler('QueueMemberStatus', self.handlerQueueMemberStatus)
		self.AMI.registerEventHandler('QueueMemberPaused', self.handlerQueueMemberPaused)
		self.AMI.registerEventHandler('QueueEntry', self.handlerQueueEntry)
		self.AMI.registerEventHandler('QueueStatusComplete', self.handlerQueueStatusComplete)
	
	
	def list2Dict(self, lines):
		dic = {}
		for line in lines:
			tmp = line.split(':')
			if len(tmp) == 1:
				dic[tmp[0].strip()] = ''
			elif len(tmp) == 2:
				dic[tmp[0].strip()] = tmp[1].strip()
			elif len(tmp) >= 3:
				dic[tmp[0].strip()] = ''.join(tmp[1:])
									
		return dic
	
	
	def threadSocketClient(self, name, params):
		
		log.info('MonAst.threadClientSocket :: Starting Thread...')
		while self.running:
			try:
				(sc, addr) = self.socketClient.accept()
				log.info('MonAst.threadSocketClient :: New client connection: %s' % str(addr))
				self.clientSockLock.acquire()
				threadId  = 'threadClient-%s' % random.random()
				self.clientSocks[threadId] = thread.start_new_thread(self.threadClient, (threadId, sc, addr))
				self.clientSockLock.release()
			except:
				log.error('MonAst.threadClientSocket :: Unhandled Exception: \n%s' % log.formatTraceback(traceback))
				
				
	def threadClient(self, threadId, sock, addr):
		
		log.info('MonAst.threadClient (%s) :: Starting Thread...' % threadId)
		session      = None
		localRunning = True
		count        = 0
		
		try:
			while self.running and localRunning:
				message = sock.recv(1024)
				if message.strip():
					messages = message.strip().split('\r\n')
					for message in messages:
						log.debug('MonAst.threadClient (%s) :: Received: %s' % (threadId, message))
						
						output = []
						
						if message.upper().startswith('SESSION: '):
							session = message[9:]
							self.clientQueuelock.acquire()
							try:
								self.clientQueues[session]['t'] = time.time()
								output.append('OK')
							except KeyError:
								self.clientQueues[session] = {'q': Queue.Queue(), 't': time.time()}
								output.append('NEW SESSION')
								log.log(logging.NOTICE, 'MonAst.threadClient (%s) :: New client session: %s' % (threadId, session))
							self.clientQueuelock.release()
						
						elif session and message.upper() == 'GET STATUS':
							output = self.clientGetStatus(threadId, session)
						
						elif session and message.upper() == 'GET CHANGES':
							output = self.clientGetChanges(threadId, session)
						
						elif session and message.startswith('OriginateCall'):
							self.clientOriginateCall(threadId, message)
							
						elif session and message.startswith('OriginateDial'):
							self.clientOriginateDial(threadId, message)
							
						elif session and message.startswith('HangupChannel'):
							self.clientHangupChannel(threadId, message)
						
						elif session and message.startswith('TransferCall'):
							self.clientTransferCall(threadId, message)
						
						elif session and message.startswith('ParkCall'):
							self.clientParkCall(threadId, message)
						
						elif session and message.startswith('MeetmeKick'):
							self.clientMeetmeKick(threadId, message)
						
						elif session and message.startswith('ParkedHangup'):
							self.clientParkedHangup(threadId, message)
							
						elif session and message.startswith('AddQueueMember'):
							self.clientAddQueueMember(threadId, message)
							
						elif session and message.startswith('RemoveQueueMember'):
							self.clientRemoveQueueMember(threadId, message)
							
						elif session and message.startswith('PauseQueueMember'):
							self.clientPauseQueueMember(threadId, message)
							
						elif session and message.startswith('UnpauseQueueMember'):
							self.clientUnpauseQueueMember(threadId, message)
						
						elif session and message.startswith('CliCommand'):
							self.clientCliCommand(threadId, message, session)
						
						elif message.upper() == 'BYE':
							localRunning = False
							
						else:
							output.append('NO SESSION')
							
						## Send messages to client
						if len(output) > 0:
							log.debug('MonAst.threadClient (%s) :: Sending: %s\r\n' % (threadId, '\r\n'.join(output)))
							sock.send('%s\r\n' % '\r\n'.join(output))
				
				else:
					count += 1
					if count == 10:
						log.error('MonAst.threadClient (%s) :: Loose connection, dropping client.' % threadId)
						break
					
		except socket.error, e:
			log.error('MonAst.threadClient (%s) :: Socket Error: %s' % (threadId, e))
		except:
			log.error('MonAst.threadClient (%s) :: Unhandled Exception: \n%s' % (threadId, log.formatTraceback(traceback)))
			
		try:
			sock.close()
		except:
			pass
		
		log.info('MonAst.threadClient (%s) :: Finishing Thread...' % threadId)
		
		self.clientSockLock.acquire()
		del self.clientSocks[threadId]
		self.clientSockLock.release()
		
		
	def threadClientQueueRemover(self, name, params):
		
		log.info('MonAst.threadClientQueueRemover :: Starting Thread...')
		while self.running:
			time.sleep(60)
			self.clientQueuelock.acquire()
			dels = []
			now = time.time()
			for session in self.clientQueues:
				past = self.clientQueues[session]['t']
				if int(now - past) > 600:
					dels.append(session)
			for session in dels:
				log.log(logging.NOTICE, 'MonAst.threadClientQueueRemover :: Removing dead client session: %s' % session)
				del self.clientQueues[session]
			self.clientQueuelock.release()
			
			
	def threadCheckStatus(self, name, params):
		
		log.info('MonAst.threadChannelChecker :: Starting Thread...')
		time.sleep(10)
		while self.running:
			log.info('MonAst.threadChannelChecker :: Requesting Status...')
			
			self.channelStatus = []
			self.AMI.execute(['Action: Status'])
			
			self.queuesLock.acquire()
			for queue in self.queues:
				self.queueStatusOrder.append(queue)
				self.queueMemberStatus[queue] = []
				self.queueClientStatus[queue] = []
				self.AMI.execute(['Action: QueueStatus', 'Queue: %s' % queue])
			self.queuesLock.release()
			
			time.sleep(60)
	
	
	def enqueue(self, msg, session = None):
		
		self.clientQueuelock.acquire()
		if session:
			self.clientQueues[session]['q'].put(msg)
		else:
			for session in self.clientQueues:
				self.clientQueues[session]['q'].put(msg)
		self.clientQueuelock.release()
	
	
	##
	## AMI Handlers for Events
	##
	def handlerReload(self, lines):
		
		log.info('MonAst.handlerReload :: Running...')
		self._GetConfig()
		
		
	def handlerChannelReload(self, lines):
		
		log.info('MonAst.handlerChannelReload :: Running...')
		dic = self.list2Dict(lines)
		
		Channel      = dic['Channel']
		ReloadReason = dic['ReloadReason']
		
		self._GetConfig()
		
		
	def handlerPeerEntry(self, lines):
		
		log.info('MonAst.handlerPeerEntry :: Running...')
		dic = self.list2Dict(lines)
		
		Status      = dic['Status']
		Channeltype = dic['Channeltype']
		ObjectName  = dic['ObjectName']
		
		if Status.startswith('OK'):
			Status = 'Registered'
		elif Status.find('(') != -1:
			Status = Status[0:Status.find('(')]
		
		self.monitoredUsersLock.acquire()
		user = '%s/%s' % (Channeltype, ObjectName)
		
		if self.userDisplay['DEFAULT'] and not self.userDisplay.has_key(user):
			self.monitoredUsers[user] = {'Channeltype': Channeltype, 'Status': Status, 'Calls': 0, 'CallerID': '--', 'Context': 'default', 'Variables': []}
		elif not self.userDisplay['DEFAULT'] and self.userDisplay.has_key(user):
			self.monitoredUsers[user] = {'Channeltype': Channeltype, 'Status': Status, 'Calls': 0, 'CallerID': '--', 'Context': 'default', 'Variables': []}
		else:
			user = None
		
		if user:
			self.AMI.execute(['Action: Command', 'Command: %s show peer %s' % (Channeltype.lower(), ObjectName)], self._defaultParseConfigPeers, user)
		
		self.monitoredUsersLock.release()
		
	
	def handlerPeerStatus(self, lines):
		
		log.info('MonAst.handlerPeerStatus :: Running...')
		dic = self.list2Dict(lines)
		
		Peer       = dic['Peer']
		PeerStatus = dic['PeerStatus']
		
		self.monitoredUsersLock.acquire()
		if self.monitoredUsers.has_key(Peer):
			mu = self.monitoredUsers[Peer]
			mu['Status'] = PeerStatus
			self.enqueue('PeerStatus: %s:::%s:::%s' % (Peer, mu['Status'], mu['Calls']))
		self.monitoredUsersLock.release()
					
	
	def handlerNewchannel(self, lines):
		
		log.info('MonAst.handlerNewchannel :: Running...')
		dic = self.list2Dict(lines)
		
		Channel      = dic['Channel']
		State        = dic['State']
		CallerIDNum  = dic['CallerIDNum']
		CallerIDName = dic['CallerIDName']
		Uniqueid     = dic['Uniqueid']
					
		self.channelsLock.acquire()
		self.channels[Uniqueid] = {'Channel': Channel, 'State': State, 'CallerIDNum': CallerIDNum, 'CallerIDName': CallerIDName}
		self.channelsLock.release()
		
		self.monitoredUsersLock.acquire()
		user = Channel
		if Channel.rfind('-') != -1:
			user = Channel[:Channel.rfind('-')]
		if self.monitoredUsers.has_key(user):
			self.monitoredUsers[user]['Calls'] += 1
			self.enqueue('PeerStatus: %s:::%s:::%s' % (user, self.monitoredUsers[user]['Status'], self.monitoredUsers[user]['Calls']))
		self.monitoredUsersLock.release()
		
		self.enqueue('NewChannel: %s:::%s:::%s:::%s:::%s' % (Channel, State, CallerIDNum, CallerIDName, Uniqueid))
		
		
	def handlerNewstate(self, lines):
		
		log.info('MonAst.handlerNewstate :: Running...')
		dic = self.list2Dict(lines)
		
		Channel      = dic['Channel']
		State        = dic['State']
		CallerID     = dic['CallerID']
		CallerIDName = dic['CallerIDName']
		Uniqueid     = dic['Uniqueid']
					
		self.channelsLock.acquire()
		try:
			self.channels[Uniqueid]['State'] = State
			self.enqueue('NewState: %s:::%s:::%s:::%s:::%s' % (Channel, State, CallerID, CallerIDName, Uniqueid))
		except:
			pass
		self.channelsLock.release()
		
		
	def handlerHangup(self, lines):
		
		log.info('MonAst.handlerHangup :: Running...')
		dic = self.list2Dict(lines)
		
		Channel   = dic['Channel']
		Uniqueid  = dic['Uniqueid']
		Cause     = dic['Cause']
		Cause_txt = dic['Cause-txt']
					
		self.channelsLock.acquire()
		try:
			del self.channels[Uniqueid]
			self.enqueue('Hangup: %s:::%s:::%s:::%s' % (Channel, Uniqueid, Cause, Cause_txt))
		except:
			pass
		self.channelsLock.release()
		
		self.callsLock.acquire()
		toDelete = None
		for id in self.calls:
			if id.find(Uniqueid) != -1 and self.calls[id]['Status'] == 'Dial':
				toDelete = id
				break
		if toDelete:
			del self.calls[toDelete]
			src, dst = toDelete.split('-')
			self.enqueue('Unlink: FAKE:::FAKE:::%s:::%s:::FAKE:::FAKE' % (src, dst))
		self.callsLock.release()
		
		self.monitoredUsersLock.acquire()
		user = Channel
		if Channel.rfind('-') != -1:
			user = Channel[:Channel.rfind('-')]
		if self.monitoredUsers.has_key(user) and self.monitoredUsers[user]['Calls'] > 0:
			self.monitoredUsers[user]['Calls'] -= 1
			self.enqueue('PeerStatus: %s:::%s:::%s' % (user, self.monitoredUsers[user]['Status'], self.monitoredUsers[user]['Calls']))
		self.monitoredUsersLock.release()
		
		
	def handlerDial(self, lines):
		
		log.info('MonAst.handlerDial :: Running...')
		dic = self.list2Dict(lines)
		
		Source       = dic['Source']
		Destination  = dic['Destination']
		CallerID     = dic['CallerID']
		CallerIDName = dic['CallerIDName']
		SrcUniqueID  = dic['SrcUniqueID']
		DestUniqueID = dic['DestUniqueID']
					
		self.callsLock.acquire()
		self.calls['%s-%s' % (SrcUniqueID, DestUniqueID)] = {
			'Source': Source, 'Destination': Destination, 'CallerID': CallerID, 'CallerIDName': CallerIDName, 
			'SrcUniqueID': SrcUniqueID, 'DestUniqueID': DestUniqueID, 'Status': 'Dial', 'startTime': 0
		}
		self.callsLock.release()
		
		self.enqueue('Dial: %s:::%s:::%s:::%s:::%s:::%s' % (Source, Destination, CallerID, CallerIDName, SrcUniqueID, DestUniqueID))
		
		
	def handlerLink(self, lines):
		
		log.info('MonAst.handlerLink :: Running...')
		dic = self.list2Dict(lines)
		
		Channel1  = dic['Channel1']
		Channel2  = dic['Channel2']
		Uniqueid1 = dic['Uniqueid1']
		Uniqueid2 = dic['Uniqueid2']
		CallerID1 = dic['CallerID1']
		CallerID2 = dic['CallerID2']
					
		self.callsLock.acquire()
		try:
			self.calls['%s-%s' % (Uniqueid1, Uniqueid2)]['Status'] = 'Link'
			if self.calls['%s-%s' % (Uniqueid1, Uniqueid2)]['startTime'] == 0:
				self.calls['%s-%s' % (Uniqueid1, Uniqueid2)]['startTime'] = time.time()
		except:
			self.calls['%s-%s' % (Uniqueid1, Uniqueid2)] = {
				'Source': Channel1, 'Destination': Channel2, 'CallerID': CallerID1, 'CallerIDName': '', 
				'SrcUniqueID': Uniqueid1, 'DestUniqueID': Uniqueid2, 'Status': 'Link', 'startTime': time.time()
			}
		Seconds = time.time() - self.calls['%s-%s' % (Uniqueid1, Uniqueid2)]['startTime']
		self.enqueue('Link: %s:::%s:::%s:::%s:::%s:::%s:::%d' % (Channel1, Channel2, Uniqueid1, Uniqueid2, CallerID1, CallerID2, Seconds))
		self.callsLock.release()
		
		
	def handlerUnlink(self, lines):
		
		log.info('MonAst.handlerLink :: Running...')
		dic = self.list2Dict(lines)
		
		Channel1  = dic['Channel1']
		Channel2  = dic['Channel2']
		Uniqueid1 = dic['Uniqueid1']
		Uniqueid2 = dic['Uniqueid2']
		CallerID1 = dic['CallerID1']
		CallerID2 = dic['CallerID2']
					
		self.callsLock.acquire()
		try:
			del self.calls['%s-%s' % (Uniqueid1, Uniqueid2)]
			self.enqueue('Unlink: %s:::%s:::%s:::%s:::%s:::%s' % (Channel1, Channel2, Uniqueid1, Uniqueid2, CallerID1, CallerID2))
		except:
			pass
		self.callsLock.release()
		
		
	def handlerNewcallerid(self, lines):
		
		log.info('MonAst.handlerNewcallerid :: Running...')
		dic = self.list2Dict(lines)
		
		Channel        = dic['Channel']
		CallerID       = dic['CallerID']
		CallerIDName   = dic['CallerIDName']
		Uniqueid       = dic['Uniqueid']
		CIDCallingPres = dic['CID-CallingPres']
					
		self.channelsLock.acquire()
		self.channels[Uniqueid]['CallerIDName'] = CallerIDName
		self.channels[Uniqueid]['CallerIDNum']  = CallerID
		self.channelsLock.release()
		
		self.enqueue('NewCallerid: %s:::%s:::%s:::%s:::%s' % (Channel, CallerID, CallerIDName, Uniqueid, CIDCallingPres))
		
		
	def handlerRename(self, lines):
		
		log.info('MonAst.handlerRename :: Running...')
		dic = self.list2Dict(lines)
		
		Oldname      = dic['Oldname']
		Newname      = dic['Newname']
		Uniqueid     = dic['Uniqueid']
		CallerIDName = ''
		CallerID     = ''
					
		try:
			self.channelsLock.acquire()
			self.channels[Uniqueid]['Channel'] = Newname
			self.channelsLock.release()
		
			self.callsLock.acquire()
			for call in self.calls:
				SrcUniqueID, DestUniqueID = call.split('-')
				key = None
				if (SrcUniqueID == Uniqueid):
					key = 'Source'
				if (DestUniqueID == Uniqueid):
					key = 'Destination'
				if key:
					self.calls[call][key] = Newname
					CallerIDName = self.calls[call]['CallerIDName']
					CallerID     = self.calls[call]['CallerID']
					break							
			self.callsLock.release()
			
			self.enqueue('Rename: %s:::%s:::%s:::%s:::%s' % (Oldname, Newname, Uniqueid, CallerIDName, CallerID))
		except:
			log.error('MonAst.handlerRename :: Channel %s not found in self.channels, ignored.' % Oldname)
			
			
	def handlerMeetmeJoin(self, lines):
		
		log.info('MonAst.handlerMeetmeJoin :: Running...')
		dic = self.list2Dict(lines)
		
		Uniqueid     = dic['Uniqueid']
		Meetme       = dic['Meetme']
		Usernum      = dic['Usernum']
		CallerIDNum  = dic.get('CallerIDNum', None)
		CallerIDName = dic.get('CallerIDName', None)
					
		self.meetmeLock.acquire()
		self.channelsLock.acquire()
		ch = self.channels[Uniqueid]
		try:
			self.meetme[Meetme]['users'][Usernum] = {'Uniqueid': Uniqueid, 'CallerIDNum': CallerIDNum, 'CallerIDName': CallerIDName}
		except KeyError:
			self.meetme[Meetme] = {
					'dynamic': True,
					'users'  : {Usernum: {'Uniqueid': Uniqueid, 'CallerIDNum': CallerIDNum, 'CallerIDName': CallerIDName}}
			}
			self.enqueue('MeetmeCreate: %s' % Meetme)
		self.enqueue('MeetmeJoin: %s:::%s:::%s:::%s:::%s:::%s' % (Meetme, Uniqueid, Usernum, ch['Channel'], CallerIDNum, CallerIDName))
		self.channelsLock.release()
		self.meetmeLock.release()
					
					
	def handlerMeetmeLeave(self, lines):
		
		log.info('MonAst.handlerMeetmeLeave :: Running...')
		dic = self.list2Dict(lines)
		
		Uniqueid = dic['Uniqueid']
		Meetme   = dic['Meetme']
		Usernum  = dic['Usernum']
		Duration = dic['Duration']
					
		self.meetmeLock.acquire()
		try:
			del self.meetme[Meetme]['users'][Usernum]
			self.enqueue('MeetmeLeave: %s:::%s:::%s:::%s' % (Meetme, Uniqueid, Usernum, Duration))
			if (self.meetme[Meetme]['dynamic'] and len(self.meetme[Meetme]['users']) == 0):
				del self.meetme[Meetme]
				self.enqueue('MeetmeDestroy: %s' % Meetme)
		except Exception, e:
			log.error('MonAst.handlerMeetmeLeave :: Meetme or Usernum not found in self.meetme[\'%s\'][\'users\'][\'%s\']' % (Meetme, Usernum))
		self.meetmeLock.release()
		
		
	def handlerParkedCall(self, lines):
		
		log.info('MonAst.handlerParkedCall :: Running...')
		dic = self.list2Dict(lines)
		
		Exten        = dic['Exten']
		Channel      = dic['Channel']
		From         = dic['From']
		Timeout      = dic['Timeout']
		CallerID     = dic['CallerID']
		CallerIDName = dic['CallerIDName']
					
		self.parkedLock.acquire()
		self.parked[Exten] = {'Channel': Channel, 'From': From, 'Timeout': Timeout, 'CallerID': CallerID, 'CallerIDName': CallerIDName}
		self.enqueue('ParkedCall: %s:::%s:::%s:::%s:::%s:::%s' % (Exten, Channel, From, Timeout, CallerID, CallerIDName))
		self.parkedLock.release()
					
					
	def handlerUnParkedCall(self, lines):
		
		log.info('MonAst.handlerUnParkedCall :: Running...')
		dic = self.list2Dict(lines)
		
		Exten        = dic['Exten']
		Channel      = dic['Channel']
		From         = dic['From']
		CallerID     = dic['CallerID']
		CallerIDName = dic['CallerIDName']
					
		self.parkedLock.acquire()
		try:
			del self.parked[Exten]
			self.enqueue('UnparkedCall: %s' % (Exten))
		except:
			log.error('MonAst.handlerUnParkedCall :: Parked Exten not found: %s' % Exten)
		self.parkedLock.release()
		
	
	def handlerParkedCallTimeOut(self, lines):
		
		log.info('MonAst.handlerParkedCallTimeOut :: Running...')
		dic = self.list2Dict(lines)
		
		Exten        = dic['Exten']
		Channel      = dic['Channel']
		CallerID     = dic['CallerID']
		CallerIDName = dic['CallerIDName']
					
		self.parkedLock.acquire()
		try:
			del self.parked[Exten]
			self.enqueue('UnparkedCall: %s' % (Exten))
		except:
			log.error('MonAst.handlerParkedCallTimeOut :: Parked Exten not found: %s' % Exten)
		self.parkedLock.release()
		
	
	def handlerParkedCallGiveUp(self, lines):
		
		log.info('MonAst.handlerParkedCallGiveUp :: Running...')
		dic = self.list2Dict(lines)
		
		Exten        = dic['Exten']
		Channel      = dic['Channel']
		CallerID     = dic['CallerID']
		CallerIDName = dic['CallerIDName']
					
		self.parkedLock.acquire()
		try:
			del self.parked[Exten]
			self.enqueue('UnparkedCall: %s' % (Exten))
		except:
			log.error('MonAst.handlerParkedCallGiveUp :: Parked Exten not found: %s' % Exten)
		self.parkedLock.release()
		
		
	def handlerStatus(self, lines):
		
		log.info('MonAst.handlerStatus :: Running...')
		dic = self.list2Dict(lines)
		
		Channel      = dic['Channel']
		CallerIDNum  = dic['CallerIDNum']
		CallerIDName = dic['CallerIDName']
		State        = dic['State']
		Seconds      = dic.get('Seconds', 0)
		Link         = dic.get('Link', '')
		Uniqueid     = dic['Uniqueid']
					
		self.channelStatus.append(Uniqueid)
		
		self.channelsLock.acquire()
		if not self.channels.has_key(Uniqueid):
			self.channels[Uniqueid] = {'Channel': Channel, 'State': State, 'CallerIDNum': CallerIDNum, 'CallerIDName': CallerIDName}
			self.monitoredUsersLock.acquire()
			user = Channel
			if Channel.rfind('-') != -1:
				user = Channel[:Channel.rfind('-')]
			if self.monitoredUsers.has_key(user):
				self.monitoredUsers[user]['Calls'] += 1
				self.enqueue('PeerStatus: %s:::%s:::%s' % (user, self.monitoredUsers[user]['Status'], self.monitoredUsers[user]['Calls']))
			self.monitoredUsersLock.release()
			self.enqueue('NewChannel: %s:::%s:::%s:::%s:::%s' % (Channel, State, CallerIDNum, CallerIDName, Uniqueid))
			if Link:
				for UniqueidLink in self.channels:
					if self.channels[UniqueidLink]['Channel'] == Link:
						self.callsLock.acquire()
						self.calls['%s-%s' % (Uniqueid, UniqueidLink)] = {
							'Source': Channel, 'Destination': Link, 'CallerID': CallerIDNum, 'CallerIDName': CallerIDName, 
							'SrcUniqueID': Uniqueid, 'DestUniqueID': UniqueidLink, 'Status': 'Link', 'startTime': time.time() - int(Seconds)
						}
						self.callsLock.release()
						self.enqueue('Link: %s:::%s:::%s:::%s:::%s:::%s:::%d' % \
									(Channel, Link, Uniqueid, UniqueidLink, CallerIDNum, self.channels[UniqueidLink]['CallerIDNum'], int(Seconds)))
		self.channelsLock.release()
		
		
	def handlerStatusComplete(self, lines):
		
		log.info('MonAst.handlerStatusComplete :: Running...')
		dic = self.list2Dict(lines)
		
		self.channelsLock.acquire()
		self.callsLock.acquire()
		lostChannels = [i for i in self.channels.keys() if i not in self.channelStatus]
		for Uniqueid in lostChannels:
			log.log(logging.NOTICE, 'MonAst.handlerStatusComplete :: Removing lost channel %s' % Uniqueid)
			try:
				Channel = self.channels[Uniqueid]['Channel']
				del self.channels[Uniqueid]
				self.enqueue('Hangup: %s:::%s:::FAKE:::FAKE' % (Channel, Uniqueid))
			except:
				pass
			
			toDelete = None
			for id in self.calls:
				if id.find(Uniqueid) != -1 and self.calls[id]['Status'] == 'Dial':
					toDelete = id
					break
			if toDelete:
				del self.calls[toDelete]
				src, dst = toDelete.split('-')
				self.enqueue('Unlink: FAKE:::FAKE:::%s:::%s:::FAKE:::FAKE' % (src, dst))
			
			self.monitoredUsersLock.acquire()
			user = Channel
			if Channel.rfind('-') != -1:
				user = Channel[:Channel.rfind('-')]
			if self.monitoredUsers.has_key(user) and self.monitoredUsers[user]['Calls'] > 0:
				self.monitoredUsers[user]['Calls'] -= 1
				self.enqueue('PeerStatus: %s:::%s:::%s' % (user, self.monitoredUsers[user]['Status'], self.monitoredUsers[user]['Calls']))
			self.monitoredUsersLock.release()
		self.callsLock.release()
		self.channelsLock.release()
	
	
	def handlerQueueMember(self, lines):
		
		log.info('MonAst.handlerQueueMember :: Running...')
		dic = self.list2Dict(lines)
		
		Queue      = dic['Queue']
		Name       = dic['Name']
		Location   = dic['Location']
		Penalty    = dic['Penalty']
		CallsTaken = dic['CallsTaken']
		LastCall   = dic['LastCall']
		Status     = dic['Status']
		Paused     = dic['Paused']
		
		self.queuesLock.acquire()
		try:
			self.queues[Queue]['members'][Location]['Penalty']    = Penalty
			self.queues[Queue]['members'][Location]['CallsTaken'] = CallsTaken
			self.queues[Queue]['members'][Location]['LastCall']   = LastCall
			self.queues[Queue]['members'][Location]['Status']     = Status
			self.queues[Queue]['members'][Location]['Paused']     = Paused
			self.enqueue('QueueMemberStatus: %s:::%s:::%s:::%s:::%s:::%s:::%s' % (Queue, Location, Penalty, CallsTaken, LastCall, AST_DEVICE_STATES[Status], Paused))
		except KeyError:
			self.queues[Queue]['members'][Location] = {
				'Name': Name, 'Penalty': Penalty, 'CallsTaken': CallsTaken, 'LastCall': LastCall, 'Status': Status, 'Paused': Paused
			}
			self.enqueue('AddQueueMember: %s:::%s:::%s:::%s:::%s:::%s:::%s:::%s' % (Queue, Location, Name, Penalty, CallsTaken, LastCall, AST_DEVICE_STATES[Status], Paused))
		self.queueMemberStatus[Queue].append(Location)
		self.queuesLock.release()
		
		
	def handlerQueueMemberStatus(self, lines):
		
		log.info('MonAst.handlerQueueMemberStatus :: Running...')
		dic = self.list2Dict(lines)
		
		lines.append('Name: %s' % dic['MemberName'])
		self.handlerQueueMember(lines)
		
		
	def handlerQueueMemberPaused(self, lines):
		
		log.info('MonAst.handlerQueueMemberPaused :: Running...')
		dic = self.list2Dict(lines)
		
		Queue    = dic['Queue']
		Location = dic['Location']
		
		self.queuesLock.acquire()
		lines.append('Penalty: %s' % self.queues[Queue]['members'][Location]['Penalty'])
		lines.append('CallsTaken: %s' % self.queues[Queue]['members'][Location]['CallsTaken'])
		lines.append('LastCall: %s' % self.queues[Queue]['members'][Location]['LastCall'])
		lines.append('Status: %s' % self.queues[Queue]['members'][Location]['Status'])
		lines.append('Name: %s' % dic['MemberName'])
		self.queuesLock.release()
		
		self.handlerQueueMember(lines)
		
		
	def handlerQueueEntry(self, lines):
		
		log.info('MonAst.handlerQueueEntry :: Running...')
		dic = self.list2Dict(lines)
		
		Queue        = dic['Queue']
		Position     = dic['Position']
		Channel      = dic['Channel']
		CallerID     = dic['CallerID']
		CallerIDName = dic['CallerIDName']
		Wait         = dic['Wait']
		Uniqueid     = None
		
		# I need to get Uniqueid from this entry
		self.channelsLock.acquire()
		for Uniqueid in self.channels:
			if self.channels[Uniqueid]['Channel'] == Channel:
				break
		self.channelsLock.release()
		
		self.queuesLock.acquire()
		self.queueClientStatus[Queue].append(Uniqueid)
		Count = len(self.queueClientStatus[Queue])
		try:
			self.queues[Queue]['clients'][Uniqueid]['Position'] = Position			
		except KeyError:
			self.queues[Queue]['clients'][Uniqueid] = {'Uniqueid': Uniqueid, 'Channel': Channel, 'CallerID': CallerID, 'CallerIDName': CallerIDName, \
													'Position': Position, 'JoinTime': time.time() - int(Wait)}
			self.enqueue('AddQueueClient: %s:::%s:::%s:::%s:::%s:::%s:::%s:::%s' % (Queue, Uniqueid, Channel, CallerID, CallerIDName, Position, Count, Wait))
		self.queuesLock.release()
		
		
	def handlerQueueMemberAdded(self, lines):
		
		log.info('MonAst.handlerQueueMemberAdded :: Running...')
		dic = self.list2Dict(lines)
		
		Queue      = dic['Queue']
		Location   = dic['Location']
		MemberName = dic['MemberName']
		Penalty    = dic['Penalty']
		
		self.queuesLock.acquire()
		self.queues[Queue]['members'][Location] = {'Name': MemberName, 'Penalty': Penalty, 'CallsTaken': 0, 'LastCall': 0, 'Status': '0', 'Paused': 0} 
		self.enqueue('AddQueueMember: %s:::%s:::%s:::%s:::%s:::%s:::%s:::%s' % (Queue, Location, MemberName, Penalty, 0, 0, AST_DEVICE_STATES['0'], 0))
		self.queuesLock.release()
		
		
	def handlerQueueMemberRemoved(self, lines):
		
		log.info('MonAst.handlerQueueMemberRemoved :: Running...')
		dic = self.list2Dict(lines)
		
		Queue      = dic['Queue']
		Location   = dic['Location']
		MemberName = dic['MemberName']
		
		self.queuesLock.acquire()
		try:
			del self.queues[Queue]['members'][Location]
			self.enqueue('RemoveQueueMember: %s:::%s:::%s' % (Queue, Location, MemberName))
		except KeyError:
			log.error("MonAst.handlerQueueMemberRemoved :: Queue or Member not found in self.queues['%s']['members']['%s']" % (Queue, Location))
		self.queuesLock.release()
		
		
	def handlerJoin(self, lines): # Queue Join
		
		log.info('MonAst.handlerJoin :: Running...')
		dic = self.list2Dict(lines)
		
		Channel      = dic['Channel']
		CallerID     = dic['CallerID']
		CallerIDName = dic['CallerIDName']
		Queue        = dic['Queue']
		Position     = dic['Position']
		Count        = dic['Count']
		Uniqueid     = dic['Uniqueid']
		
		self.queuesLock.acquire()
		self.queues[Queue]['clients'][Uniqueid] = {'Uniqueid': Uniqueid, 'Channel': Channel, 'CallerID': CallerID, 'CallerIDName': CallerIDName, \
												'Position': Position, 'JoinTime': time.time()}
		self.queues[Queue]['stats']['Calls'] += 1
		self.enqueue('AddQueueClient: %s:::%s:::%s:::%s:::%s:::%s:::%s:::%s' % (Queue, Uniqueid, Channel, CallerID, CallerIDName, Position, Count, 0))
		self.queuesLock.release()
		
	
	def handlerLeave(self, lines): # Queue Leave
		
		log.info('MonAst.handlerLeave :: Running...')
		dic = self.list2Dict(lines)
	
		Channel      = dic['Channel']
		Queue        = dic['Queue']
		Count        = dic['Count']
		Uniqueid     = dic['Uniqueid']
		
		self.queuesLock.acquire()
		try:
			cause = ''
			if self.queues[Queue]['clients'][Uniqueid].has_key('Abandoned'):
				cause = 'Abandoned'
				self.queues[Queue]['stats']['Abandoned'] += 1
			else:
				cause = 'Completed'
				self.queues[Queue]['stats']['Completed'] += 1
			self.queues[Queue]['stats']['Calls'] -= 1
			
			del self.queues[Queue]['clients'][Uniqueid]
			self.enqueue('RemoveQueueClient: %s:::%s:::%s:::%s:::%s' % (Queue, Uniqueid, Channel, Count, cause))
		except KeyError:
			log.error("MonAst.handlerLeave :: Queue or Client not found in self.queues['%s']['clients']['%s']" % (Queue, Uniqueid))
		self.queuesLock.release()
		
		
	def handlerQueueCallerAbandon(self, lines):
		
		log.info('MonAst.handlerQueueCallerAbandon :: Running...')
		dic = self.list2Dict(lines)
		
		Queue    = dic['Queue']
		Uniqueid = dic['Uniqueid']
		
		self.queuesLock.acquire()
		self.queues[Queue]['clients'][Uniqueid]['Abandoned'] = True
		self.queuesLock.release()
		
		#self.enqueue('AbandonedQueueClient: %s' % Uniqueid)
		
		
	def handlerQueueParams(self, lines):
		
		log.info('MonAst.handlerQueueParams :: Running...')
		dic = self.list2Dict(lines)
		
		Queue            = dic['Queue']
		Max              = int(dic['Max'])
		Calls            = int(dic['Calls'])
		Holdtime         = int(dic['Holdtime'])
		Completed        = int(dic['Completed'])
		Abandoned        = int(dic['Abandoned'])
		ServiceLevel     = int(dic['ServiceLevel'])
		ServicelevelPerf = float(dic['ServicelevelPerf'])
		Weight           = int(dic['Weight'])
		
		self.queuesLock.acquire()
		if self.queues.has_key(Queue):
			self.queues[Queue]['stats']['Max']              = Max
			self.queues[Queue]['stats']['Calls']            = Calls
			self.queues[Queue]['stats']['Holdtime']         = Holdtime
			self.queues[Queue]['stats']['Completed']        = Completed
			self.queues[Queue]['stats']['Abandoned']        = Abandoned
			self.queues[Queue]['stats']['ServiceLevel']     = ServiceLevel
			self.queues[Queue]['stats']['ServicelevelPerf'] = ServicelevelPerf
			self.queues[Queue]['stats']['Weight']           = Weight
		else:
			self.queues[Queue] = {
				'members': {}, 
				'clients': {}, 
				'stats': {
					'Max': Max, 'Calls': Calls, 'Holdtime': Holdtime, 'Completed': Completed, 'Abandoned': Abandoned, 'ServiceLevel': ServiceLevel, \
					'ServicelevelPerf': ServicelevelPerf, 'Weight': Weight
				}
			}
			self.queueMemberStatus[Queue] = []
			self.queueClientStatus[Queue] = []
			self.queueStatusFirst         = True
			self.queueStatusOrder.append(Queue)
		self.queuesLock.release()
		
		self.enqueue('QueueParams: %s:::%s:::%s:::%s:::%s:::%s:::%s:::%s:::%s' % \
					(Queue, Max, Calls, Holdtime, Completed, Abandoned, ServiceLevel, ServicelevelPerf, Weight))
		
		
	def handlerQueueStatusComplete(self, lines):
		
		log.info('MonAst.handlerQueueStatusComplete :: Running...')
		
		self.queuesLock.acquire()
		
		size = 0
		if self.queueStatusFirst:
			size = len(self.queueStatusOrder)
			self.queueStatusFirst = False
		elif len(self.queueStatusOrder) > 0:
			size = 1			
		
		for i in xrange(size):
			try:
				queue       = self.queueStatusOrder.pop(0)
				lostMembers = [i for i in self.queues[queue]['members'].keys() if i not in self.queueMemberStatus[queue]]
				for member in lostMembers:
					log.log(logging.NOTICE, 'MonAst.handlerQueueStatusComplete :: Removing lost member %s from queue %s' % (member, queue))
					del self.queues[queue]['members'][member]
					self.enqueue('RemoveQueueMember: %s:::%s:::FAKE' % (queue, member))
				
				lostClients = [i for i in self.queues[queue]['clients'].keys() if i not in self.queueClientStatus[queue]]
				for client in lostClients:
					log.log(logging.NOTICE, 'MonAst.handlerQueueStatusComplete :: Removing lost client %s from queue %s' % (client, queue))
					Channel = self.queues[queue]['clients'][client]['Channel']
					del self.queues[queue]['clients'][client]
					Count = len(self.queues[queue]['clients'])
					self.enqueue('RemoveQueueClient: %s:::%s:::%s:::%s:::FAKE' % (queue, client, Channel, Count))
			except:
				log.error('MonAst.handlerQueueStatusComplete :: Unhandled Exception: \n%s' % log.formatTraceback(traceback))
		self.queuesLock.release()
		
		
	##
	## AMI handlers for Actions/Commands
	##
	def _defaultParseConfigPeers(self, lines):
		
		log.info('MonAst._defaultParseConfigPeers :: Running...')
		result = lines[3]
		
		user = lines[2].split(': ')[1]
		
		CallerID  = None
		Context   = None
		Variables = None
		
		try:
			CallerID = re.compile("['\"]").sub("", re.search('Callerid[\s]+:[\s](.*)\n', result).group(1))
			if CallerID == ' <>':
				CallerID = '--'
		except:
			CallerID = '--'
		
		try:
			Context = re.search('Context[\s]+:[\s](.*)\n', result).group(1)
		except:
			Context = 'default'
		
		try:
			tmp       = result[result.find('Variables'):]
			tmp       = tmp[tmp.find(':\n') + 2:]
			Variables = re.compile('^[\s]+(.*)\n', re.MULTILINE)
			Variables = Variables.findall(tmp)
			Variables = [i.replace(' = ', '=') for i in Variables]
		except:
			Variables = []
		
		self.monitoredUsersLock.acquire()
		if self.monitoredUsers.has_key(user):
			self.monitoredUsers[user]['CallerID']  = CallerID
			self.monitoredUsers[user]['Context']   = Context
			self.monitoredUsers[user]['Variables'] = Variables
		self.monitoredUsersLock.release()
		
		
	def handlerParseIAXPeers(self, lines):
		
		log.info('MonAst.handlerParseIAXPeers :: Running...')
		
		for line in lines[2:-1]:
			name = re.search('^([^\s]*).*', line).group(1)
			if name.find('/') != -1:
				name = name[:name.find('/')]
			
			self.handlerPeerEntry(['Channeltype: IAX2', 'ObjectName: %s' % name, 'Status: --'])
	
	
	def handlerGetConfigMeetme(self, lines):
		
		log.info('MonAst.handlerGetConfigMeetme :: Parsing config...')
		
		self.meetmeLock.acquire()
		for line in lines:
			if line.startswith('Line-') and line.find('conf=') != -1:
				params = line[line.find('conf=')+5:].split(',')
				self.meetme[params[0]] = {'dynamic': False, 'users': {}}
		self.meetmeLock.release()
		
		
	def handlerCliCommand(self, lines):
		
		log.info('MonAst.handlerCliCommand :: Running...')

		ActionID = lines[2][10:]
		Response = lines[3].replace('--END COMMAND--', '')

		self.enqueue('CliResponse: %s' % Response.replace('\n', '<br>'), ActionID)
	
	
	##
	## Handlers for Client Commands
	##
	def clientGetStatus(self, threadId, session):
		
		log.info('MonAst.clientGetStatus (%s) :: Running...' % threadId)
		
		output = []
		
		self.clientQueuelock.acquire()
		self.monitoredUsersLock.acquire()
		self.channelsLock.acquire()
		self.callsLock.acquire()
		self.meetmeLock.acquire()
		self.parkedLock.acquire()
		self.queuesLock.acquire()
		
		try:
			self.clientQueues[session]['t'] = time.time()
			output.append('BEGIN STATUS')
			
			usersWithCid    = []
			usersWithoutCid = []
			for user in self.monitoredUsers:
				if self.monitoredUsers[user]['CallerID'] != '--':
					usersWithCid.append((user, self.monitoredUsers[user]['CallerID']))
				else:
					usersWithoutCid.append((user, user))
			usersWithCid.sort(lambda x, y: cmp(x[1].lower(), y[1].lower()))
			usersWithoutCid.sort(lambda x, y: cmp(x[1].lower(), y[1].lower()))
			users = usersWithCid + usersWithoutCid
			for user, CallerID in users:
				mu = self.monitoredUsers[user]
				output.append('PeerStatus: %s:::%s:::%s:::%s' % (user, mu['Status'], mu['Calls'], CallerID))
			for Uniqueid in self.channels:
				ch = self.channels[Uniqueid]
				output.append('NewChannel: %s:::%s:::%s:::%s:::%s' % (ch['Channel'], ch['State'], ch['CallerIDNum'], ch['CallerIDName'], Uniqueid))
			for call in self.calls:
				c = self.calls[call]
				src, dst = call.split('-')
				try:
					output.append('Call: %s:::%s:::%s:::%s:::%s:::%s:::%s:::%s:::%d' % (c['Source'], c['Destination'], c['CallerID'], c['CallerIDName'], \
													self.channels[dst]['CallerIDNum'], c['SrcUniqueID'], c['DestUniqueID'], c['Status'], time.time() - c['startTime']))
				except:
					log.error('MonAst.clientGetStatus (%s) :: Unhandled Exception \n%s' % (threadId, log.formatTraceback(traceback)))
			meetmeRooms = self.meetme.keys()
			meetmeRooms.sort()
			for meetme in meetmeRooms:
				output.append('MeetmeCreate: %s' % meetme)
				for Usernum in self.meetme[meetme]['users']:
					mm = self.meetme[meetme]['users'][Usernum]
					ch = self.channels[mm['Uniqueid']]
					output.append('MeetmeJoin: %s:::%s:::%s:::%s:::%s:::%s' % (meetme, mm['Uniqueid'], Usernum, ch['Channel'], mm['CallerIDNum'], mm['CallerIDName']))
			
			parkedCalls = self.parked.keys()
			parkedCalls.sort()
			for Exten in parkedCalls:
				pc = self.parked[Exten]
				output.append('ParkedCall: %s:::%s:::%s:::%s:::%s:::%s' % (Exten, pc['Channel'], pc['From'], pc['Timeout'], pc['CallerID'], pc['CallerIDName']))
				
			queues = self.queues.keys()
			queues.sort()
			for queue in queues:
				q = self.queues[queue]
				output.append('Queue: %s' % queue)
				members = q['members'].keys()
				members.sort()
				for member in members:
					m = q['members'][member]
					output.append('AddQueueMember: %s:::%s:::%s:::%s:::%s:::%s:::%s:::%s' % (queue, member, m['Name'], \
						m['Penalty'], m['CallsTaken'], m['LastCall'], AST_DEVICE_STATES[m['Status']], m['Paused']))
					
				clients = q['clients'].values()
				clients.sort(lambda x, y: cmp(x['Position'], y['Position']))
				for i in xrange(len(clients)):
					c = clients[i]
					output.append('AddQueueClient: %s:::%s:::%s:::%s:::%s:::%s:::%s:::%s' % (queue, c['Uniqueid'], c['Channel'], c['CallerID'], \
									c['CallerIDName'], c['Position'], i, time.time() - c['JoinTime']))
					
				Max              = q['stats']['Max']
				Calls            = q['stats']['Calls']
				Holdtime         = q['stats']['Holdtime']
				Completed        = q['stats']['Completed']
				Abandoned        = q['stats']['Abandoned']
				ServiceLevel     = q['stats']['ServiceLevel']
				ServicelevelPerf = q['stats']['ServicelevelPerf']
				Weight           = q['stats']['Weight']
				
				output.append('QueueParams: %s:::%s:::%s:::%s:::%s:::%s:::%s:::%s:::%s' % \
							(queue, Max, Calls, Holdtime, Completed, Abandoned, ServiceLevel, ServicelevelPerf, Weight))
			
			output.append('END STATUS')
		except:
			log.error('MonAst.clientGetStatus (%s) :: Unhandled Exception \n%s' % (threadId, log.formatTraceback(traceback)))
		
		self.queuesLock.release()
		self.parkedLock.release()
		self.meetmeLock.release()
		self.callsLock.release()
		self.channelsLock.release()
		self.monitoredUsersLock.release()
		self.clientQueuelock.release()
	
		return output
	
	
	def clientGetChanges(self, threadId, session):
		
		log.info('MonAst.clientGetChanges (%s) :: Running...' % threadId)
		
		output = []
		
		self.clientQueuelock.acquire()
		self.clientQueues[session]['t'] = time.time()
		output.append('BEGIN CHANGES')
		while True:
			try:
				msg = self.clientQueues[session]['q'].get(False)
				output.append(msg)
			except Queue.Empty:
				break
		output.append('END CHANGES')
		self.clientQueuelock.release()
		
		return output
	
	
	def clientOriginateCall(self, threadId, message):
		
		log.info('MonAst.clientOriginateCall (%s) :: Running...' % threadId)
		action, src, dst, type = message.split(':::')
		
		self.monitoredUsersLock.acquire()
		Context = self.monitoredUsers[src]['Context']
		if type == 'meetme':
			Context = self.meetmeContext
			dst     = '%s%s' % (self.meetmePrefix, dst)
		command = []
		command.append('Action: Originate')
		command.append('Channel: %s' % src)
		command.append('Exten: %s' % dst)
		command.append('Context: %s' % Context)
		command.append('Priority: 1')
		command.append('CallerID: %s' % MONAST_CALLERID)
		for var in self.monitoredUsers[src]['Variables']:
			command.append('Variable: %s' % var)
		log.debug('MonAst.clientOriginateCall (%s) :: From %s to exten %s@%s' % (threadId, src, dst, Context))
		self.AMI.execute(command)
		self.monitoredUsersLock.release()
		
	
	def clientOriginateDial(self, threadId, message):
		
		log.info('MonAst.clientOriginateDial (%s) :: Running...' % threadId)
		action, src, dst, type = message.split(':::')

		command = []
		command.append('Action: Originate')
		command.append('Channel: %s' % src)
		command.append('Application: Dial')
		command.append('Data: %s|30|rTt' % dst)
		command.append('CallerID: %s' % MONAST_CALLERID)
		
		log.debug('MonAst.clientOriginateDial (%s) :: From %s to %s' % (threadId, src, dst))
		self.AMI.execute(command)
		
		
	def clientHangupChannel(self, threadId, message):
		
		log.info('MonAst.clientHangupChannel (%s) :: Running...' % threadId)
		action, Uniqueid = message.split(':::')
		
		self.channelsLock.acquire()
		try:
			Channel = self.channels[Uniqueid]['Channel']
			command = []
			command.append('Action: Hangup')
			command.append('Channel: %s' % Channel)
			log.debug('MonAst.clientHangupChannel (%s) :: Hangup channel %s' % (threadId, Channel))
			self.AMI.execute(command)
		except:
			log.error('MonAst.clientHangupChannel (%s) :: Uniqueid %s not found on self.channels' % (threadId, Uniqueid))
		self.channelsLock.release()
	
	
	def clientTransferCall(self, threadId, message):
		
		log.info('MonAst.clientTransferCall (%s) :: Running...' % threadId)
		action, src, dst, type = message.split(':::')
							
		Context      = self.transferContext
		SrcChannel   = None
		ExtraChannel = None
		if type == 'peer':
			self.channelsLock.acquire()
			SrcChannel  = self.channels[src]['Channel']
			self.channelsLock.release()
			tech, exten = dst.split('/')
			try:
				exten = int(exten)
			except:
				self.monitoredUsersLock.acquire()
				exten = self.monitoredUsers[dst]['CallerID']
				exten = exten[exten.find('<')+1:exten.find('>')]
				self.monitoredUsersLock.release()
		elif type == 'meetme':
			self.channelsLock.acquire()
			tmp = src.split('-')
			if len(tmp) == 2:
				SrcChannel   = self.channels[tmp[0]]['Channel']
				ExtraChannel = self.channels[tmp[1]]['Channel']
			else:
				SrcChannel   = self.channels[tmp[0]]['Channel']
			self.channelsLock.release()
			Context = self.meetmeContext
			exten   = '%s%s' % (self.meetmePrefix, dst)

		command = []
		command.append('Action: Redirect')
		command.append('Channel: %s' % SrcChannel)
		if ExtraChannel:
			command.append('ExtraChannel: %s' % ExtraChannel)
		command.append('Exten: %s' % exten)
		command.append('Context: %s' % Context)
		command.append('Priority: 1')
		
		log.debug('MonAst.clientTransferCall (%s) :: Transferring %s and %s to %s@%s' % (threadId, SrcChannel, ExtraChannel, exten, Context))
		self.AMI.execute(command)
	
	
	def clientParkCall(self, threadId, message):

		log.info('MonAst.clientParkCall (%s) :: Running...' % threadId)
		action, park, announce = message.split(':::')

		self.channelsLock.acquire()
		ParkChannel   = self.channels[park]['Channel']
		AnouceChannel = self.channels[announce]['Channel']
		self.channelsLock.release()
		command = []
		command.append('Action: Park')
		command.append('Channel: %s' % ParkChannel)
		command.append('Channel2: %s' % AnouceChannel)
		#ommand.append('Timeout: 45')
		log.debug('MonAst.clientParkCall (%s) :: Parking Channel %s and announcing to %s' % (threadId, ParkChannel, AnouceChannel))
		self.AMI.execute(command)	
	
	
	def clientMeetmeKick(self, threadId, message):
		
		log.info('MonAst.clientMeetmeKick (%s) :: Running...' % threadId)
		action, Meetme, Usernum = message.split(':::')
		
		command = []
		command.append('Action: Command')
		command.append('Command: meetme kick %s %s' % (Meetme, Usernum))
		log.debug('MonAst.clientMeetmeKick (%s) :: Kiking usernum %s from meetme %s' % (threadId, Usernum, Meetme))
		self.AMI.execute(command)
	
	def clientParkedHangup(self, threadId, message):
		
		log.info('MonAst.clientParkedHangup (%s) :: Running...' % threadId)
		action, Exten = message.split(':::')
		
		self.parkedLock.acquire()
		try:
			Channel = self.parked[Exten]['Channel']
			command = []
			command.append('Action: Hangup')
			command.append('Channel: %s' % Channel)
			log.debug('MonAst.clientParkedHangup (%s) :: Hangup parcked channel %s' % (threadId, Channel))
			self.AMI.execute(command)
		except:
			log.error('MonAst.clientParkedHangup (%s) :: Exten %s not found on self.parked' % (threadId, Exten))
		self.parkedLock.release()
		
		
	def clientAddQueueMember(self, threadId, message):
		
		log.info('MonAst.clientAddQueueMember (%s) :: Running...' % threadId)
		action, queue, member = message.split(':::')
		
		self.monitoredUsersLock.acquire()
		MemberName = self.monitoredUsers[member]['CallerID']
		if MemberName == '--':
			MemberName = member
		command = []
		command.append('Action: QueueAdd')
		command.append('Queue: %s' % queue)
		command.append('Interface: %s' % member)
		#command.append('Penalty: 10')
		command.append('MemberName: %s' % MemberName)
		log.debug('MonAst.clientAddQueueMember (%s) :: Adding member %s to queue %s' % (threadId, member, queue))
		self.AMI.execute(command)
		self.monitoredUsersLock.release()
		
		
	def clientRemoveQueueMember(self, threadId, message):
		
		log.info('MonAst.clientRemoveQueueMember (%s) :: Running...' % threadId)
		action, queue, member = message.split(':::')
		
		command = []
		command.append('Action: QueueRemove')
		command.append('Queue: %s' % queue)
		command.append('Interface: %s' % member)
		log.debug('MonAst.clientRemoveQueueMember (%s) :: Removing member %s from queue %s' % (threadId, member, queue))
		self.AMI.execute(command)
		
		
	def clientPauseQueueMember(self, threadId, message):
		
		log.info('MonAst.clientPauseQueueMember (%s) :: Running...' % threadId)
		action, queue, member = message.split(':::')
		
		command = []
		command.append('Action: QueuePause')
		command.append('Queue: %s' % queue)
		command.append('Interface: %s' % member)
		command.append('Paused: 1')
		log.debug('MonAst.clientAddQueueMember (%s) :: Pausing member %s on queue %s' % (threadId, member, queue))
		self.AMI.execute(command)
		
	def clientUnpauseQueueMember(self, threadId, message):
		
		log.info('MonAst.clientPauseQueueMember (%s) :: Running...' % threadId)
		action, queue, member = message.split(':::')
		
		command = []
		command.append('Action: QueuePause')
		command.append('Queue: %s' % queue)
		command.append('Interface: %s' % member)
		command.append('Paused: 0')
		log.debug('MonAst.clientUnpauseQueueMember (%s) :: Unpausing member %s on queue %s' % (threadId, member, queue))
		self.AMI.execute(command)
		
	
	def clientCliCommand(self, threadId, message, session):
		
		log.info('MonAst.clientCliCommand (%s) :: Running...' % threadId)
		action, cliCommand = message.split(':::')
		
		command = []
		command.append('Action: Command')
		command.append('Command: %s' % cliCommand)
		command.append('ActionID: %s' % session)
		log.debug('MonAst.clientCliCommand (%s) :: Executing CLI command: %s' % (threadId, cliCommand))
		self.AMI.execute(command, self.handlerCliCommand, session)
	
	
	def _GetConfig(self):
		
		self.monitoredUsersLock.acquire()
		self.monitoredUsers = {}
		self.monitoredUsersLock.release()
		
		self.meetmeLock.acquire()
		self.meetme = {}
		self.meetmeLock.release()
		
		self.queuesLock.acquire()
		self.queues = {}
		self.queuesLock.release()
		
		self.AMI.execute(['Action: SIPpeers'])
		self.AMI.execute(['Action: IAXpeers'], self.handlerParseIAXPeers)
		self.AMI.execute(['Action: GetConfig', 'Filename: meetme.conf'], self.handlerGetConfigMeetme)
		self.AMI.execute(['Action: QueueStatus'])
		
		self.clientQueuelock.acquire()
		for session in self.clientQueues:
			self.clientQueues[session]['q'].put('Reload: 10')
		self.clientQueuelock.release()
		
	
	def start(self):
		
		self.AMI.start()
		
		try:
			while not self.AMI.isConnected or not self.AMI.isAuthenticated:
				time.sleep(1)
			
			self.tcc  = thread.start_new_thread(self.threadCheckStatus, ('threadCheckStatus', 2))
			self.tcs  = thread.start_new_thread(self.threadSocketClient, ('threadSocketClient', 2))
			self.tcqr = thread.start_new_thread(self.threadClientQueueRemover, ('threadClientQueueRemover', 2))
			
			self._GetConfig()
				
			while self.running:
				time.sleep(1)
		except KeyboardInterrupt:
			log.info('MonAst.start :: Received KeyboardInterrupt -- Shutting Down')
			self.running = False
			
		self.AMI.close()
		
		time.sleep(2)
		log.log(logging.NOTICE, 'Monast :: Finished...')
	
	
if __name__ == '__main__':

	opt = optparse.OptionParser()
	opt.add_option('-c', '--config',
		dest    = "configFile",
		default = '/etc/monast.conf',
		help    = "use this config file instead of /etc/monast.conf"
	)
	opt.add_option('--info',
		dest   = "info",
		action = "store_true",
		help   = "display INFO messages"
	)
	opt.add_option('--debug',
		dest   = "debug",
		action = "store_true",
		help   = "display DEBUG messages"
	)
	opt.add_option('--colored',
		dest   = "colored",
		action = "store_true",
		help   = "display colored log messages"
	)
	opt.add_option('-d', '--daemon',
		dest   = "daemon",
		action = "store_true",
		help   = "deamonize (fork in background)"
	)
	opt.add_option('-l', '--logfile',
		dest    = "logfile",
		default = "/var/log/monast.log",
		help    = "use this log file instead of /var/log/monast.log"
	)
	
	(options, args) = opt.parse_args()

	if not os.path.exists(options.configFile):
		print '  Config file "%s" not found.' % options.configFile
		print '  Run "%s --help" for help.' % sys.argv[0]
		sys.exit(1)

	if options.daemon:
		if os.fork() == 0:
			os.setsid()
			if os.fork() == 0:
				pass
			else:
				os._exit(0)
		else:
			os._exit(0)
		
		print 'MonAst daemonized with pid %s' % os.getpid()

	if options.info:
		logging.getLogger("").setLevel(logging.INFO)
		
	if options.debug:
		logging.getLogger("").setLevel(logging.DEBUG)
	
	basicLogFormat = "[%(asctime)s] %(levelname)-8s :: %(message)s"
	
	if options.colored and not options.daemon:
		logging.COLORED = True
		basicLogFormat  = "[%(asctime)s] %(levelname)-19s :: %(message)s"
	
	fmt  = ColorFormatter(basicLogFormat, '%a %b %d %H:%M:%S %Y')
	hdlr = None
	if options.daemon:
		hdlr = logging.FileHandler(options.logfile)
	else:
		hdlr = logging.StreamHandler(sys.stdout)
	hdlr.setFormatter(fmt)
	if (len(logging.getLogger("").handlers) == 1):
		logging.getLogger("").handlers[0] = hdlr
	else:
		logging.getLogger("").addHandler(hdlr)
	
	log = logging.getLogger("MonAst")
	
	monast = MonAst(options.configFile)
	monast.start()

	hdlr.close()
