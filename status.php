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

$inicio = time();

$errno  = null;
$errstr = null;
$fp     = @fsockopen(HOSTNAME, HOSTPORT, $errno, $errstr, 60);

if ($errstr)
{
    $error  = "!! MonAst ERROR !!\n\nCould not connect to " . HOSTNAME . ":" . HOSTPORT . ": $errstr\n";
    $error .= "Make sure monast.py is running so the panel can connect to its port properly.";
	echo $json->encode(array(array('Action' => 'Error', 'Message' => $error)));
	die;
}

fwrite($fp, "SESSION: $sessid\r\n");

$isStatus = false;
$isOK     = false;
$events   = array();
$complete = false;

while (!feof($fp))
{
	if ($isOK && !$isStatus && !$complete)
	{
		fwrite($fp, "GET CHANGES\r\n");
		sleep(1);
	}
	
	$messages = fread($fp, 1024 * 64);
	$messages = explode("\r\n", $messages);
	
	foreach ($messages as $idx => $message)
	{
		if ($message)
		{
			if ($message == "OK")
			{
				fwrite($fp, "GET CHANGES\r\n");
				$isOK = true;
			}
			elseif ($message == "BEGIN CHANGES")
			{
				$isStatus = true;
			}
			elseif ($message == "END CHANGES")
			{
				$isStatus = false;
				if (count($events) > 0)
					$complete = true;
			}
			elseif ($isStatus)
			{
				$object = $json->decode($message);
				
				if (array_search($object['Action'], $validActions) !== false)
					$events[] = $object;
				else 
					$events[] = array('Action' => 'None', 'Message' => $message);
			}
		}
	}
	
	session_start();
	$actions = getValor('Actions', 'session');
	if (count($actions) > 0)
	{
	    foreach ($actions as $action)
	    {
	        fwrite($fp, "$action\r\n");
	    }
	    setValor('Actions', array());
	}
	session_write_close();
	
	$now = time();
	if ($now >= ($inicio + MONAST_SOCKET_DURATION) && !$isStatus && $isOK)
	{
		$isOK = false;
		fwrite($fp, "BYE\r\n");
		
		if ($now >= (getValor('started', 'session') + MONAST_BROWSER_REFRESH))
		{
			$events[] = array('Action' => 'Reload', 'Time' => 3000);
		}
		break;
	}
	
	if ($complete)
	{
		fwrite($fp, "BYE\r\n");
		break;
	}
}

fclose($fp);

echo $json->encode($events);

?>
