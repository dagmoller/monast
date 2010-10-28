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
setValor('Actions', array());
$servers   = array();
$server    = getValor('Server', 'session');
session_write_close();

$json     = new Services_JSON(SERVICES_JSON_LOOSE_TYPE);
$template = new TemplatePower('template/monast.html');

$response = doGet("listServers");
switch ($response)
{
	case "ERROR :: Connection Refused":
	case "ERROR :: Internal Server Error":
	case "ERROR :: Authentication Required":
	case "ERROR :: Request Not Found":
		session_start();
		setValor('login', false);
		session_write_close();
		header("Location: index.php");
		break;
		
	default:
		$servers = $json->decode($response);
		session_start();
		setValor('Servers', $servers);
		if (!$server || array_search($server, $servers) === false)
			setValor('Server', $servers[0]);
		session_write_close();
		break;
}

$status   = null;
$response = doGet("getStatus");
switch ($response)
{
	case "ERROR :: Connection Refused":
	case "ERROR :: Internal Server Error":
	case "ERROR :: Authentication Required":
	case "ERROR :: Request Not Found":
		session_start();
		setValor('login', false);
		session_write_close();
		header("Location: index.php");
		break;
		
	default:
		$status = $json->decode($response);
		break;
}

//print_pre($status);
//die;

$template->prepare();
$template->assign("templates", file_get_contents("template/templates.html"));
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

// Users/Peers
$techs = array_keys($status[$server]['peers']);
sort($techs);
foreach ($techs as $tech)
{
	$peers = $status[$server]['peers'][$tech];
	if (count($peers) > 0)
	{
		$template->newBlock('technology');
		$template->assign('technology', $tech);
		$template->assign('count', count($peers));
		
		foreach ($peers as $peer)
		{
			$template->newBlock('peer');
			$template->assign('peer', $peer['channel']);
			$template->assign('CallerID', htmlentities($peer['callerid']));
			$template->assign('status', $peer['status']);
			$template->assign('status-color', color($peer['status']));
			$template->assign('calls', $peer['calls'] . " call(s)");
			$template->assign('calls-color', ($peer['calls'] > 0 ? '#ffffb0' : '#b0ffb0'));
			$template->assign('time', "Latency: " . $peer['time'] . " ms");
		}
	}
}

// Queues
/*
foreach ($validActions['Queue'] as $idx => $queue)
{
	if ($idx % 2 == 0)
		$template->newBlock('queueDualDiv');
	
	$template->newBlock('queue');
	$template->assign('queue', $queue['Queue']);
}
unset($validActions['Queue']);
*/

// Channels and Bridges
foreach ($status[$server]['channels'] as $channel)
{
	$channel['channel'] = htmlentities($channel['channel']);
	
	$template->newBlock('process');
	$template->assign('json', $json->encode($channel));
}
foreach ($status[$server]['bridges'] as $bridge)
{
	$bridge['channel']        = htmlentities($bridge['channel']);
	$bridge['bridgedchannel'] = htmlentities($bridge['bridgedchannel']);
	
	$template->newBlock('process');
	$template->assign('json', $json->encode($bridge));
}

$template->printToScreen();

?>
