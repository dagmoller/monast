
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
import time
import socket

DEBUG = False
INFO  = False

COLORED = False

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

def __write(msg, color):
	if COLORED:
		sys.stdout.write('\033[37;1m[%s]\033[0m \033[%d;1m%s\033[0m\n' % (time.ctime(), COLORS[color], msg))
	else:
		sys.stdout.write('[%s] %s\n' % (time.ctime(), msg))
	sys.stdout.flush()

def error(msg, color = None):
	if not color:
		color = 'red'
	__write('ERROR :: %s' % msg, color)

def log(msg, color = None):
	if not color:
		color = 'white'
	__write('LOG   :: %s' % msg, color)

def info(msg, color = None):
	if INFO:
		if not color:
			color = 'yellow'
		__write('INFO  :: %s' % msg, color)

def debug(msg, color = None):
	if DEBUG:
		if not color:
			color = 'cyan'
		__write('DEBUG :: %s' % msg.encode('string_escape'), color)
		
def formatTraceback(trace, prefix = '>>'):
	return '  %s %s ' % (prefix, ''.join(trace.format_exception(sys.exc_type, sys.exc_value, sys.exc_traceback)).replace('\n', '\n  %s ' % prefix))
	