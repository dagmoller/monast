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
#     * Neither the name of the <ORGANIZATION> nor the names of its contributors
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
import time
import pprint
import getopt
import thread
import threading
import traceback
import socket
import random
import Queue
import log
from AsteriskManager import AsteriskManager
from ConfigParser import SafeConfigParser

MONAST_CALLERID = "MonAst WEB"


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
	
	##
	## Class Initialization
	##
	def __init__(self, configFile):
		
		log.log('MonAst :: Initializing...')
		
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
				log.log('MonAst.threadSocketClient :: New client connection: %s' % str(addr))
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
						
						elif session and message.startswith('CliCommand'):
							self.clientCliCommand(threadId, message, session)
						
						elif message.upper() == 'BYE':
							localRunning = False
							
						else:
							output.append('NO SESSION')
							
						## Send messages to client
						#for msg in output:
						#	log.debug('MonAst.threadClient (%s) :: Sending: %s' % (threadId, msg))
						#	sock.send('%s\r\n' % msg)
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
				log.info('MonAst.threadClientQueueRemover :: Removing dead client session: %s' % session)
				del self.clientQueues[session]
			self.clientQueuelock.release()
			
			
	def threadCheckStatus(self, name, params):
		
		log.info('MonAst.threadChannelChecker :: Starting Thread...')
		time.sleep(10)
		while self.running:
			log.info('MonAst.threadChannelChecker :: Requesting Status...')
			self.AMI.send(['Action: Status'], self.handlerStatusFollow)
			
			self.queuesLock.acquire()
			for queue in self.queues:
				self.AMI.send(['Action: QueueStatus', 'Queue: %s' % queue])
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
		if self.monitoredUsers.has_key(user):
			self.monitoredUsers[user]['Status'] = Status
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
		self.meetme[Meetme][Usernum] = {'Uniqueid': Uniqueid, 'CallerIDNum': CallerIDNum, 'CallerIDName': CallerIDName}
		ch = self.channels[Uniqueid]
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
			del self.meetme[Meetme][Usernum]
			self.enqueue('MeetmeLeave: %s:::%s:::%s:::%s' % (Meetme, Uniqueid, Usernum, Duration))
		except Exception, e:
			log.error('MonAst.handlerMeetmeLeave :: Meetme or Usernum not found in self.meetme[\'%s\'][\'%s\']' % (Meetme, Usernum))
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
			log.log('MonAst.handlerStatusComplete :: Removing lost channel %s' % Uniqueid)
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
		
		
	def handlerQueueMemberAdded(self, lines):
		
		log.info('MonAst.handlerQueueMemberAdded :: Running...')
		dic = self.list2Dict(lines)
		
		Queue      = dic['Queue']
		Location   = dic['Location']
		MemberName = dic['MemberName']
		Penalty    = dic['Penalty']
		
		self.queuesLock.acquire()
		self.queues[Queue]['members'][Location] = {'penalty': Penalty, 'name': MemberName}
		self.enqueue('AddQueueMember: %s:::%s:::%s' % (Queue, Location, MemberName))
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
		self.queues[Queue]['clients'][Uniqueid] = {'Uniqueid': Uniqueid, 'Channel': Channel, 'CallerID': CallerID, 'CallerIDName': CallerIDName, 'Position': Position}
		self.queues[Queue]['stats']['Calls'] += 1
		self.enqueue('AddQueueClient: %s:::%s:::%s:::%s:::%s:::%s:::%s' % (Queue, Uniqueid, Channel, CallerID, CallerIDName, Position, Count))
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
		
		self.enqueue('AbandonedQueueClient: %s' % Uniqueid)
		
		
	def handlerQueueParams(self, lines):
		
		log.info('MonAst.handlerQueueParams :: Running...')
		dic = self.list2Dict(lines)
		
		Queue            = dic['Queue']
		Max              = dic['Max']
		Calls            = dic['Calls']
		Holdtime         = dic['Holdtime']
		Completed        = dic['Completed']
		Abandoned        = dic['Abandoned']
		ServiceLevel     = dic['ServiceLevel']
		ServicelevelPerf = dic['ServicelevelPerf']
		Weight           = dic['Weight']
		
		self.queuesLock.acquire()
		self.queues[Queue]['stats']['Max'] = int(dic['Max'])
		self.queues[Queue]['stats']['Calls'] = int(dic['Calls'])
		self.queues[Queue]['stats']['Holdtime'] = int(dic['Holdtime'])
		self.queues[Queue]['stats']['Completed'] = int(dic['Completed'])
		self.queues[Queue]['stats']['Abandoned'] = int(dic['Abandoned'])
		self.queues[Queue]['stats']['ServiceLevel'] = int(dic['ServiceLevel'])
		self.queues[Queue]['stats']['ServicelevelPerf'] = float(dic['ServicelevelPerf'])
		self.queues[Queue]['stats']['Weight'] = int(dic['Weight'])
		self.queuesLock.release()
		
		self.enqueue('QueueParams: %s:::%s:::%s:::%s:::%s:::%s:::%s:::%s:::%s' % \
					(Queue, Max, Calls, Holdtime, Completed, Abandoned, ServiceLevel, ServicelevelPerf, Weight))
	   
		
	##
	## AMI handlers for Actions/Commands
	##
	def _defaultParseConfig(self, lines, type):
		
		log.info('MonAst._defaultParseConfig :: Parsing %s...' % type)
		
		user = None
		tech = None
		if type == 'sip.conf':
			tech = 'SIP'
			self.AMI.send(['Action: SIPPeers'])
		if type == 'iax.conf':
			tech = 'IAX2'
			self.AMI.send(['Action: IAXPeers'])
		self.monitoredUsersLock.acquire()
		oldUsers = []
		newUsers = []
		# get actual users
		for user in self.monitoredUsers:
			if user.startswith(tech):
				oldUsers.append(user)
		for line in lines:
			if line.startswith('Category-') and not line.endswith(': general') and not line.endswith(': authentication'):
				user = '%s/%s' % (tech, line[line.find(': ') + 2:]) 
				if self.userDisplay['DEFAULT'] and not self.userDisplay.has_key(user):
					self.monitoredUsers[user] = {'Channeltype': tech, 'Status': '--', 'Calls': 0, 'CallerID': '--', 'Context': 'default', 'Variables': []}
				elif not self.userDisplay['DEFAULT'] and self.userDisplay.has_key(user):
					self.monitoredUsers[user] = {'Channeltype': tech, 'Status': '--', 'Calls': 0, 'CallerID': '--', 'Context': 'default', 'Variables': []}
				else:
					user = None
	
			if user:
				newUsers.append(user)
			
			if user and line.startswith('Line-'):
				tmp, param = line.split(': ')
				if param.startswith('callerid'):
					quotes = re.compile("['\"]")
					self.monitoredUsers[user]['CallerID'] = quotes.sub("", param[param.find('=')+1:])
				if param.startswith('context'):
					self.monitoredUsers[user]['Context'] = param[param.find('=')+1:]
				if param.startswith('setvar'):
					self.monitoredUsers[user]['Variables'].append(param[param.find('=')+1:])
		for user in [i for i in oldUsers if i not in newUsers]:
			log.log('User/Peer removed: %s' % user)
			del self.monitoredUsers[user]
		self.monitoredUsersLock.release()
		
	
	def handlerGetConfigSIP(self, lines):
		self._defaultParseConfig(lines, 'sip.conf')
	
	def handlerGetConfigIAX(self, lines):
		self._defaultParseConfig(lines, 'iax.conf')
	
	
	def handlerGetConfigMeetme(self, lines):
		
		log.info('MonAst.handlerGetConfigMeetme :: Parsing config...')
		
		self.meetmeLock.acquire()
		for line in lines:
			if line.startswith('Line-') and line.find('conf=') != -1:
				params = line[line.find('conf=')+5:].split(',')
				self.meetme[params[0]] = {}
		self.meetmeLock.release()
		
		# deve ser executado no parser do ultimo arquivo chamado pelo _GetConfig
		self.clientQueuelock.acquire()
		for session in self.clientQueues:
			self.clientQueues[session]['q'].put('Reload: 10')
		self.clientQueuelock.release()
		
		
	def handlerGetConfigQueues(self, lines):
		
		log.info('MonAst.handlerGetConfigQueues :: Parsing config...')
		
		self.queuesLock.acquire()
		
		queue     = None
		oldQueues = self.queues.keys()
		for line in lines:
			if line.startswith('Category-') and not line.endswith(': general'):
				queue = line[line.find(': ') + 2:]
				self.queues[queue] = {
					'members': {}, 
					'clients': {}, 
					'stats': {
						'Max': 0, 'Calls': 0, 'Holdtime': 0, 'Completed': 0, 'Abandoned': 0, 'ServiceLevel': 0, 'ServicelevelPerf': 0.0, 'Weight': 0
					}
				}
				if queue in oldQueues:
					oldQueues.remove(queue)
				
			if queue and line.startswith('Line-'):
				tmp, param = line.split(': ')
				if param.startswith('member') and param.find('Agent/') == -1:
					member = param[param.find('=')+1:].split(',')
					if len(member) == 3:
						self.queues[queue]['members'][member[0]] = {'penalty': member[1], 'name': member[2]}
					elif len(member) == 2:
						self.queues[queue]['members'][member[0]] = {'penalty': member[1], 'name': member[0]}
					elif len(member) == 1:
						self.queues[queue]['members'][member[0]] = {'penalty': 0, 'name': member[0]}			
		
		for queue in oldQueues:
			del self.queues[queue]
		
		self.queuesLock.release()
		
	
	def handlerStatusFollow(self, lines):
		
		log.info('MonAst.handlerStatusFollow :: Running...')
		self.channelStatus = []
		
		
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
				output.append('MeetmeRoom: %s' % meetme)
				for Usernum in self.meetme[meetme]:
					mm = self.meetme[meetme][Usernum]
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
					output.append('AddQueueMember: %s:::%s:::%s' % (queue, member, q['members'][member]['name']))
					
				clients = q['clients'].values()
				clients.sort(lambda x, y: cmp(x['Position'], y['Position']))
				for i in xrange(len(clients)):
					c = clients[i]
					output.append('AddQueueClient: %s:::%s:::%s:::%s:::%s:::%s:::%s' % (queue, c['Uniqueid'], c['Channel'], c['CallerID'], c['CallerIDName'], c['Position'], i))
					
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
		self.AMI.send(command)
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
		self.AMI.send(command)
		
		
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
			self.AMI.send(command)
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
		self.AMI.send(command)
	
	
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
		self.AMI.send(command)	
	
	
	def clientMeetmeKick(self, threadId, message):
		
		log.info('MonAst.clientMeetmeKick (%s) :: Running...' % threadId)
		action, Meetme, Usernum = message.split(':::')
		
		command = []
		command.append('Action: Command')
		command.append('Command: meetme kick %s %s' % (Meetme, Usernum))
		log.debug('MonAst.clientMeetmeKick (%s) :: Kiking usernum %s from meetme %s' % (threadId, Usernum, Meetme))
		self.AMI.send(command)
	
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
			self.AMI.send(command)
		except:
			log.error('MonAst.clientParkedHangup (%s) :: Exten %s not found on self.parked' % (threadId, Exten))
		self.parkedLock.release()
		
	
	def clientCliCommand(self, threadId, message, session):
		
		log.info('MonAst.clientCliCommand (%s) :: Running...' % threadId)
		action, cliCommand = message.split(':::')
		
		command = []
		command.append('Action: Command')
		command.append('Command: %s' % cliCommand)
		command.append('ActionID: %s' % session)
		log.debug('MonAst.clientCliCommand (%s) :: Executing CLI command: %s' % (threadId, cliCommand))
		self.AMI.send(command, self.handlerCliCommand, session)
	
	
	def _GetConfig(self):
		
		self.AMI.send(['Action: GetConfig', 'Filename: sip.conf'], self.handlerGetConfigSIP)
		self.AMI.send(['Action: GetConfig', 'Filename: iax.conf'], self.handlerGetConfigIAX)
		self.AMI.send(['Action: GetConfig', 'Filename: meetme.conf'], self.handlerGetConfigMeetme)
		self.AMI.send(['Action: GetConfig', 'Filename: queues.conf'], self.handlerGetConfigQueues)
		
	
	def start(self):
		
		self.tcc  = thread.start_new_thread(self.threadCheckStatus, ('threadCheckStatus', 2))
		self.tcs  = thread.start_new_thread(self.threadSocketClient, ('threadSocketClient', 2))
		self.tcqr = thread.start_new_thread(self.threadClientQueueRemover, ('threadClientQueueRemover', 2))
		
		self.AMI.start()
		
		try:
			while not self.AMI.isConnected:
				time.sleep(1)
				
			self._GetConfig()
				
			while self.running:
				time.sleep(1)
		except KeyboardInterrupt:
			self.running = False
			
		self.AMI.close()
	
	
def _usage():
	
	usage = """
	Usage: %s [options]
	
	Options:
		-h | --help                     => display this help
		-c | --config <config file>     => use alterantive config file instead /etc/monast.conf
		-i | --info                     => display INFO messages
		-d | --debug                    => display INFO + DEBUG messages
	""" % sys.argv[0]
	print usage
	sys.exit()
	
	
if __name__ == '__main__':

	try:
		opts, args = getopt.getopt(sys.argv[1:], 'hc:id', ['help', 'config=', 'info', 'debug'])
	except:
		_usage()
	
	configFile = '/etc/monast.conf'
	
	for o, a in opts:
		if o in ('-h', '--help'):
			_usage()
		if o in ('-c', '--config'):
			configFile = a
		if o in ('-i', '--info'):
			log.INFO = True
		if o in ('-d', '--debug'):
			log.DEBUG = True
			log.INFO  = True
			
	if not os.path.exists(configFile):
		print '  Config file "%s" not found.' % configFile
		print '  Run "%s --help" for help.' % sys.argv[0]
		sys.exit(1)

	monast = MonAst(configFile)
	monast.start()	
