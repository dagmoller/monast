
import sys
import time
import socket

def __write(msg):
	sys.stdout.write('[%s] %s\n' % (time.ctime(), msg))
	sys.stdout.flush()
	
def info(msg):
	__write('INFO  :: %s' % msg)

def error(msg):
	__write('ERROR :: %s' % msg)

def log(msg):
	__write('LOG   :: %s' % msg)

def show(msg):
	__write('SHOW  :: %s' % msg.encode('string_escape'))
	