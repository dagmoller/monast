<?php

/*
* Copyright (c) 2008-2011, Diego Aguirre
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
setValor('LastReload', time());
$servers   = array();
$server    = getValor('Server', 'session');
$errors    = array();
session_write_close();

$template = new TemplatePower('template/monast.html');

$response = doGet("listServers");
switch ($response)
{
	case "ERROR :: Connection Refused":
	case "ERROR :: Authentication Required":
		session_start();
		setValor('login', false);
		session_write_close();
		header("Location: index.php");
		die;
		break;

	case "ERROR :: Request Not Found":
		$error  = "The request to http://" . HOSTNAME . ":" . HOSTPORT . "/getUpdates was not found.<br>";
		$error .= "Make sure monast.py is running so the panel can connect to its port properly.";
		session_start();
		setValor('error', $error);
		session_write_close();
		header("Location: index.php");
		die;
		break;

	case "ERROR :: Internal Server Error":
		$error  = "We got \"Internal Server Error\" connecting to http://" . HOSTNAME . ":" . HOSTPORT . "/getUpdates.<br>";
		$error .= "Please lookup log file and report errors at http://monast.sf.net";
		session_start();
		setValor('error', $error);
		session_write_close();
		header("Location: index.php");
		die;
		break;
		
	default:
		$servers = monast_json_decode($response);
		sort($servers);
		session_start();
		setValor('Servers', $servers);
		if (!$server || array_search($server, $servers) === false)
		{
			$server = $servers[0];
			setValor('Server', $server);
		}
		session_write_close();
		break;
}

$status   = null;
$response = doGet("getStatus", array("servername" => $server));
switch ($response)
{
	case "ERROR :: Connection Refused":
	case "ERROR :: Authentication Required":
		session_start();
		setValor('login', false);
		session_write_close();
		header("Location: index.php");
		die;
		break;

	case "ERROR :: Request Not Found":
		$error  = "The request to http://" . HOSTNAME . ":" . HOSTPORT . "/getUpdates was not found.<br>";
		$error .= "Make sure monast.py is running so the panel can connect to its port properly.";
		session_start();
		setValor('error', $error);
		session_write_close();
		header("Location: index.php");
		die;
		break;

	case "ERROR :: Internal Server Error":
		$error  = "We got an Internal Server Error connecting to http://" . HOSTNAME . ":" . HOSTPORT . "/getUpdates.<br>";
		$error .= "Please lookup log file and report errors at http://monast.sf.net";
		session_start();
		setValor('error', $error);
		session_write_close();
		header("Location: index.php");
		die;
		break;

	default:
		$status = monast_json_decode($response);
		break;
}

$template->prepare();
$template->assign("templates", file_get_contents("template/template_custom.html") . file_get_contents("template/template_default.html"));
$template->assign('MONAST_CALL_TIME', MONAST_CALL_TIME ? 'true' : 'false');
$template->assign('MONAST_BLINK_ONCHANGE', MONAST_BLINK_ONCHANGE ? 'true' : 'false');
$template->assign('MONAST_BLINK_COUNT', MONAST_BLINK_COUNT);
$template->assign('MONAST_BLINK_INTERVAL', MONAST_BLINK_INTERVAL);
$template->assign('MONAST_KEEP_CALLS_SORTED', MONAST_KEEP_CALLS_SORTED ? 'true' : 'false');
$template->assign('MONAST_KEEP_PARKEDCALLS_SORTED', MONAST_KEEP_PARKEDCALLS_SORTED ? 'true' : 'false');

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
			$template->newBlock('process');
			$template->assign('json', monast_json_encode($peer));
		}
	}
}

// Channels and Bridges
foreach ($status[$server]['channels'] as $channel)
{
	$channel['channel'] = htmlentities($channel['channel']);
	
	$template->newBlock('process');
	$template->assign('json', monast_json_encode($channel));
}
foreach ($status[$server]['bridges'] as $bridge)
{
	$bridge['channel']        = htmlentities($bridge['channel']);
	$bridge['bridgedchannel'] = htmlentities($bridge['bridgedchannel']);
	
	$template->newBlock('process');
	$template->assign('json', monast_json_encode($bridge));
}

// Meetmes
foreach ($status[$server]['meetmes'] as $meetme)
{
	$template->newBlock('process');
	$template->assign('json', monast_json_encode($meetme));
}

// Parked Calls
foreach ($status[$server]['parkedCalls'] as $parked)
{
	$template->newBlock('process');
	$template->assign('json', monast_json_encode($parked));
}

// Queues
foreach ($status[$server]['queues'] as $queue)
{
	$template->newBlock('process');
	$template->assign('json', monast_json_encode($queue));
}
foreach ($status[$server]['queueMembers'] as $queueMember)
{
	$template->newBlock('process');
	$template->assign('json', monast_json_encode($queueMember));
}
foreach ($status[$server]['queueClients'] as $queueClient)
{
	$template->newBlock('process');
	$template->assign('json', monast_json_encode($queueClient));
}
foreach ($status[$server]['queueCalls'] as $queueCall)
{
	$template->newBlock('process');
	$template->assign('json', monast_json_encode($queueCall));
}

$template->printToScreen();

?>
