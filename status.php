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
	'UpdateCallDuration'
);
	
session_start();
$sessid = session_id();
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
	$error  = "!! Monast Error !!\n\nCould not create socket!\n";
	$error .= "reason: " . socket_strerror(socket_last_error());
	echo $json->encode(array(array('Action' => 'Error', 'Message' => $error)));
	die;
}

$conn = socket_connect($sock, HOSTNAME, HOSTPORT);
if ($conn === false)
{
	$error  = "!! MonAst ERROR !!\n\nCould not connect to " . HOSTNAME . ":" . HOSTPORT . ": " . socket_strerror(socket_last_error()) . "\n";
    $error .= "Make sure monast.py is running so the panel can connect to its port properly.";
	echo $json->encode(array(array('Action' => 'Error', 'Message' => $error)));
	die;
}

socket_write($sock, "SESSION: $sessid");
while ($message = socket_read($sock, 1024 * 16)) 
{
	$buffer .= $message;
	
	if ($buffer == "OK")
	{
		$buffer = "";
		$isOk   = true;
		socket_write($sock, "GET CHANGES");
	}
	elseif ($buffer == "NO SESSION")
	{
		$buffer       = "";
		$complete     = true;
		$lastEvents[] = array('Action' => 'Reload', 'Time' => 5000);
	}
	elseif ($buffer == "NO CHANGES")
	{
		$buffer = "";
		socket_write($sock, "GET CHANGES");
		sleep(1);
	}
	
	if (strpos($buffer, "BEGIN CHANGES") !== false)
		$isStatus = true;

	if (strpos($buffer, "END CHANGES") !== false)
	{
		$buffer   = trim(str_replace("BEGIN CHANGES", "", str_replace("END CHANGES", "", $buffer)));
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
		socket_write($sock, "BYE");
}
socket_close($sock);

$messages = explode("\r\n", $buffer);
foreach ($messages as $idx => $message)
{
	if ($message)
	{
		$object = $json->decode($message);
		if (array_search($object['Action'], $validActions) !== false)
			$events[] = $object;
		else 
			$events[] = array('Action' => 'None', 'Message' => $message);
	}
}

$events = array_merge($events, $lastEvents);

echo $json->encode($events);

?>
