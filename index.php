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

header("Cache-Control: no-cache, must-revalidate");
header("Pragma: no-cache");
header("Expires: -1");

session_start();
$login = getValor('login', 'session');
$error = "";
setValor('started', time());
setValor('Actions', array());
$sessionId = session_id();
session_write_close();

$json     = new Services_JSON(SERVICES_JSON_LOOSE_TYPE);
$template = new TemplatePower('template/index.html');

if (!$login)
{
	$sock = @socket_create(AF_INET, SOCK_STREAM, SOL_TCP);
	if ($sock === false)
		$error = "Could not create socket!<br>" . socket_strerror(socket_last_error());
	else 
	{
		$conn = @socket_connect($sock, HOSTNAME, HOSTPORT);
		if ($conn === false)
		{
			$error  = "Could not connect to " . HOSTNAME . ":" . HOSTPORT . " (" . socket_strerror(socket_last_error()) . ").<br>";
			$error .= "Make sure monast.py is running so the panel can connect to its port properly.";
		}
	}
	
	if (!$error)
	{
		$buffer = "";
		socket_write($sock, "SESSION: $sessionId");
		while ($message = socket_read($sock, 1024 * 16)) 
		{
			$buffer .= $message;
			
			if ($buffer == "NEW SESSION" || $buffer == "OK")
			{
				$login = true;
				session_start();
				setValor('login', true);
				session_write_close();
				socket_write($sock, "BYE");
			}
			
			if ($buffer == "ERROR: Authentication Required")
			{
				session_start();
				setValor('login', false);
				session_write_close();
				socket_write($sock, "BYE");
			}
		}
		socket_close($sock);
	}
}

if ($error)
{
	$template->prepare();
	$template->newBlock('error');
	$template->assign('errorMessage', $error);
}
else
{
	if (!$login)
	{
		$template->prepare();
		$template->newBlock('login');
	}
	else 
	{
		$template->assignInclude('main', 'monast.php');
		$template->prepare();
	}
}

$template->printToScreen();

?>
