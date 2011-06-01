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

ini_set('error_reporting', 'E_ALL & ~E_NOTICE & ~E_WARNING');

set_time_limit(0);

require_once 'lib/include.php';

session_start();
$username = getValor('username', 'session');
$server   = getValor('Server', 'session');
session_write_close();

$start      = time();
$current    = time();
$complete   = false;
$error      = "";
$updates    = array();
$lastEvents = array();

while (!$complete)
{
	$response = doGet("getUpdates", array("servername" => $server));
	switch ($response)
	{
		case "ERROR :: Connection Refused":
			$error  = "<font size='3'><b>Monast Error</b></font>\n<p>Could not connect to " . HOSTNAME . ":" . HOSTPORT . " ($response).<br>\n";
			$error .= "Make sure monast.py is running so the panel can connect to its port properly.</p>";
			break;
			
		case "ERROR :: Request Not Found":
			$error  = "The request to http://" . HOSTNAME . ":" . HOSTPORT . "/getUpdates was not found.<br>";
			$error .= "Make sure monast.py is running so the panel can connect to its port properly.";
			break;
			
		case "ERROR :: Internal Server Error":
			$error  = "We got an \"Internal Server Error\" connecting to http://" . HOSTNAME . ":" . HOSTPORT . "/getUpdates.<br>";
			$error .= "Please lookup log file and report errors at http://monast.sf.net";
			break;
		
		case "ERROR: Authentication Required":
			session_start();
			setValor('login', false);
			setValor('username', '');
			session_write_close();
			$lastEvents[] = array('action' => 'Reload', 'time' => 100);
			break;
		
		case "NO UPDATES":
			session_start();
			$actions    = getValor('Actions', 'session');
			$lastReload = getValor('LastReload', 'session');
			session_write_close();
			if (count($actions) > 0)
			{
			    foreach ($actions as $action)
			    {
			    	$action = monast_json_decode($action);
			    	if ($action['action'] == "ChangeServer")
			    	{
			    		session_start();
			    		setValor('Server', $action['server']);
			    		session_write_close();
			    		$lastEvents[] = array('action' => 'Reload', 'time' => 100);
			    		$complete = true;
			    		break;
			    	}
			    	elseif ($action['action'] == "Logout")
			    	{
			    		$tmp          = doGet('doLogout');
			    		$lastEvents[] = array('action' => 'Reload', 'time' => 100);
			    		$complete     = true;
			    		break;
			    	}
			    	elseif ($action['action'] == "Reload")
			    	{
			    		$lastEvents[] = array('action' => 'Reload', 'time' => 100);
			    		$complete     = true;
			    		break;
			    	}
			    	else
			    	{
			    		$action['server'] = $server;
			    		$tmp      = doGet('doAction', $action);
			    		$complete = true;
			    		break;
			    	}
			    }
			    session_start();
			    setValor('Actions', array());
			    session_write_close();
			}
			
			if (time() - $lastReload >= MONAST_BROWSER_REFRESH)
			{
				$lastEvents[] = array('action' => 'Reload', 'time' => 100);
				$complete     = true;
				break;
			}
			
			sleep(1);
			$current = time();
			if ($current - $start > MONAST_SOCKET_DURATION)
				$complete = true;
			break;
			
		default:
			$updates  = monast_json_decode($response);
			$complete = true;
			break;
	}
	
	if ($error)
	{
		echo monast_json_encode(array(array('action' => 'Error', 'message' => $error)), true);
		die;
	}
	
	if ($complete)
		break;
}

$events = array_merge($updates, $lastEvents);

echo monast_json_encode($events, true);

?>
