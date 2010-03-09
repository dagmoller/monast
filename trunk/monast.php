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

require_once 'lib/include.php';

session_start();
setValor('started', time());
setValor('Actions', array());
$sessionId = session_id();
session_write_close();

$validActions = array
(
	'PeerStatus'         => array(), 
	'NewChannel'         => array(), 
	'Call'               => array(), 
	'MeetmeCreate'       => array(), 
	'MeetmeJoin'         => array(), 
	'ParkedCall'         => array(), 
	'Queue'              => array(), 
	'AddQueueMember'     => array(), 
	'AddQueueClient'     => array(), 
	'AddQueueMemberCall' => array(), 
	'QueueParams'        => array()
);

$json     = new Services_JSON(SERVICES_JSON_LOOSE_TYPE);
$template = new TemplatePower('template/monast.html');
$isStatus = false;
$buffer   = "";

$sock = @socket_create(AF_INET, SOCK_STREAM, SOL_TCP);
if ($sock === false)
{
	session_start();
	setValor('login', false);
	session_write_close();
	header("Location: index.php");
}
else 
{
	$conn = @socket_connect($sock, HOSTNAME, HOSTPORT);
	if ($conn === false)
	{
		session_start();
		setValor('login', false);
		session_write_close();
		header("Location: index.php");
	}
	else 
	{
		socket_write($sock, "SESSION: $sessionId\r\n");
		while ($message = socket_read($sock, 1024 * 16)) 
		{
			$buffer .= $message;
			
			if ($buffer == "NEW SESSION\r\n" || $buffer == "OK\r\n")
			{
				$buffer = "";
				socket_write($sock, "GET STATUS\r\n");
			}
			
			if ($buffer == "ERROR: Authentication Required\r\n")
			{
				session_start();
				setValor('login', false);
				session_write_close();
				socket_write($sock, "BYE\r\n");
				header("Location: index.php");
			}
			
			if (strpos($buffer, "BEGIN STATUS\r\n") !== false)
				$isStatus = true;
				
			if (strpos($buffer, "END STATUS\r\n") !== false)
			{
				$buffer   = trim(str_replace("BEGIN STATUS\r\n", "", str_replace("END STATUS\r\n", "", $buffer)));
				$isStatus = false;
				socket_write($sock, "BYE\r\n");
			}
		}
		socket_close($sock);
	}
}

$messages = explode("\r\n", $buffer);
foreach ($messages as $idx => $message)
{
	$object = $json->decode($message);
	if (array_key_exists($object['Action'], $validActions))
		$validActions[$object['Action']][] = $object;
}

$template->prepare();

$template->assign('MONAST_CALL_TIME', MONAST_CALL_TIME ? 'true' : 'false');

if (MONAST_CLI_TAB)
{
	$template->newBlock('cli_tab');
	$template->newBlock('cli_tab_div');
}

if (MONAST_DEBUG_TAB || getValor('debug'))
{
	$template->newBlock('debug_tab');
	$template->newBlock('debug_tab_div');
}

// Counter
$peerCounter = array();
foreach ($validActions['PeerStatus'] as $idx => $peer)
{
	list($tech, $tmp) = explode('/', $peer['Peer']);
	
	if (array_key_exists($tech, $peerCounter))
		$peerCounter[$tech] += 1;
	else 
		$peerCounter[$tech] = 1;
}

// Peers
$lastTech = null;
foreach ($validActions['PeerStatus'] as $idx => $peer)
{
	list($tech, $tmp) = explode('/', $peer['Peer']);
	
	if ($tech != $lastTech)
	{
		$lastTech = $tech;
		$template->newBlock('technology');
		$template->assign('technology', $tech);
		$template->assign('count', $peerCounter[$tech]);
	}
    
    $template->newBlock('peer');
    $template->assign('peer', $peer['Peer']);
    $template->assign('CallerID', str_replace('<', '&lt;', str_replace('>', '&gt;', $peer['CallerID'])));
    $template->assign('status', $peer['Status']);
    $template->assign('status-color', color($peer['Status']));
    $template->assign('calls', $peer['Calls'] . " call(s)");
    $template->assign('calls-color', ($peer['Calls'] > 0 ? '#ffffb0' : '#b0ffb0'));
}
unset($validActions['PeerStatus']);

// Queues
foreach ($validActions['Queue'] as $idx => $queue)
{
	if ($idx % 2 == 0)
		$template->newBlock('queueDualDiv');
	
	$template->newBlock('queue');
	$template->assign('queue', $queue['Queue']);
}
unset($validActions['Queue']);

// All Other Actions
foreach ($validActions as $item => $actions)
{
	foreach ($actions as $action)
	{
		$template->newBlock('process');
		$template->assign('json', $json->encode($action));
	}
}

$template->printToScreen();

?>
