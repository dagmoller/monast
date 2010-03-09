<?php

/*
* Copyright (c) 2008, Diego Aguirre
* All rights reserved.
* 
* Redistribution and use in source and binary forms, with or without modification,
* are permitted provided that the following conditions are met:
* 
*     * Redistributions of source code must retain the above copyright notice, 
*       this list of conditions and the following disclaimer.
*     * Redistributions in binary form must reproduce the above copyright notice, 
*       this list of conditions and the following disclaimer in the documentation 
*       and/or other materials provided with the distribution.
*     * Neither the name of the DagMoller nor the names of its contributors
*       may be used to endorse or promote products derived from this software 
*       without specific prior written permission.
* 
* THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
* ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED 
* WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED.
* IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, 
* INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, 
* BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, 
* DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF 
* LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE 
* OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED 
* OF THE POSSIBILITY OF SUCH DAMAGE.
*/

header('Content-Type: application/json;');

ini_set('error_reporting', 'E_ALL & ~E_NOTICE & ~E_WARNING');

set_time_limit(0);

require_once 'lib/include.php';

$json = new Services_JSON(SERVICES_JSON_LOOSE_TYPE);

$validActions = array
(
	'Reload', 
	'PeerStatus',
	'NewChannel', 
	'NewState',
	'Hangup', 
	'Dial', 
	'Link',
	'Unlink',
	'NewCallerid', 
	'Rename', 
	'MeetmeCreate',
	'MeetmeDestroy',
	'MeetmeJoin',
	'MeetmeLeave',
	'ParkedCall',
	'UnparkedCall',
	'CliResponse',
	'AddQueueMember',
	'RemoveQueueMember',
	'QueueMemberStatus',
	'AddQueueClient',
	'RemoveQueueClient',
	'AddQueueMemberCall',
	'RemoveQueueMemberCall',
	'QueueParams',
	'MonitorStart',
	'MonitorStop',
	'UpdateCallDuration',
	'doAlertInfo',
	'doAlertWarn',
	'doAlertError',
);
	
session_start();
$sessid   = session_id();
$username = getValor('username', 'session');
session_write_close();

$inicio     = time();
$buffer     = "";
$events     = array();
$lastEvents = array();

$isOk     = false;
$isStatus = false;
$complete = false;

$sock = socket_create(AF_INET, SOCK_STREAM, SOL_TCP);
if ($sock === false)
{
	$error  = "<font size='3'><b>Monast Error</b></font>\n<p>Could not create socket!<br>\n";
	$error .= "Reason: " . socket_strerror(socket_last_error()) . "</p>";
	
	echo $json->encode(array(array('Action' => 'Error', 'Message' => $error)));
	die;
}

$conn = socket_connect($sock, HOSTNAME, HOSTPORT);
if ($conn === false)
{
    $error  = "<font size='3'><b>Monast Error</b></font>\n<p>Could not connect to " . HOSTNAME . ":" . HOSTPORT . " (" . socket_strerror(socket_last_error()) . ").<br>\n";
	$error .= "Make sure monast.py is running so the panel can connect to its port properly.</p>";
    
	echo $json->encode(array(array('Action' => 'Error', 'Message' => $error)));
	die;
}

socket_write($sock, "SESSION: $sessid\r\n");
while ($message = socket_read($sock, 1024 * 16)) 
{
	$buffer .= $message;
	
	if ($buffer == "OK\r\n")
	{
		$buffer = "";
		$isOk   = true;
		socket_write($sock, "GET CHANGES\r\n");
	}
	elseif ($buffer == "NO SESSION\r\n")
	{
		$buffer       = "";
		$complete     = true;
		$lastEvents[] = array('Action' => 'Reload', 'Time' => 5000);
	}
	elseif ($buffer == "NO CHANGES\r\n")
	{
		$buffer = "";
		socket_write($sock, "GET CHANGES\r\n");
		sleep(1);
	}
	elseif (strpos($buffer, "ERROR: Authentication Required") !== false)
	{
		$buffer       = "";
		$complete     = true;
		$lastEvents[] = array('Action' => 'Reload', 'Time' => 1000);
	}
	elseif (strpos($buffer, "ERROR: ") !== false)
	{
		$complete     = true;
		$lastEvents[] = array('Action' => 'Error', 'Message' => str_replace("NO CHANGES", "", substr($buffer, 7)));
	}
	
	if (strpos($buffer, "BEGIN CHANGES") !== false)
		$isStatus = true;

	if (strpos($buffer, "END CHANGES") !== false)
	{
		$buffer   = trim(str_replace("BEGIN CHANGES\r\n", "", str_replace("END CHANGES\r\n", "", $buffer)));
		$isStatus = false;
		$complete = true;
	}
	
	if ($isOk && !$isStatus && !$complete)
	{
		session_start();
		$actions = getValor('Actions', 'session');
		if (count($actions) > 0)
		{
		    foreach ($actions as $action)
		    {
		    	$action = $json->decode($action);
		    	$action['Session']  = $sessid;
		    	$action['Username'] = $username;
		    	$action = $json->encode($action);
		        socket_write($sock, $action . "\r\n");
		    }
		    setValor('Actions', array());
		}
		session_write_close();
	}
	
	$now = time();
	
	if ($isOk && !$isStatus && $now >= (getValor('started', 'session') + MONAST_BROWSER_REFRESH))
	{
		$isOK         = false;
		$complete     = true;
		$lastEvents[] = array('Action' => 'Reload', 'Time' => 3000);
	}
		
	if ($isOk && !$isStatus && !$complete && $now >= ($inicio + MONAST_SOCKET_DURATION))
	{
		$isOK     = false;
		$complete = true;
	}
	
	if ($complete)
		socket_write($sock, "BYE\r\n");
}
socket_close($sock);

$messages = explode("\r\n", $buffer);
foreach ($messages as $idx => $message)
{
	if ($message)
	{
		$object = $json->decode($message);
		
		if ($object['Action'] == 'CliResponse')
			$object['Response'] = rawurlencode($object['Response']);
		
		if (array_search($object['Action'], $validActions) !== false)
			$events[] = $object;
		else 
			$events[] = array('Action' => 'None', 'Message' => $message);
	}
}

$events = array_merge($events, $lastEvents);

echo $json->encode($events);

?>
