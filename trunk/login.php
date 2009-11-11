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

require_once 'lib/include.php';

session_start();

$json      = new Services_JSON(SERVICES_JSON_LOOSE_TYPE);
$saida     = array();
$sessionId = session_id();
$username  = getValor('username');
$secret    = getValor('secret'); 

$sock = @socket_create(AF_INET, SOCK_STREAM, SOL_TCP);
if ($sock === false)
{
	$saida['error']  = "<font size='3'><b>Monast Error</b></font>\n<p>Could not create socket!<br>\n";
	$saida['error'] .= socket_strerror(socket_last_error()) . "</p>";
}
else 
{
	$conn = @socket_connect($sock, HOSTNAME, HOSTPORT);
	if ($conn === false)
	{
		$saida['error']  = "<font size='3'><b>Monast Error</b></font>\n<p>Could not connect to " . HOSTNAME . ":" . HOSTPORT . " (" . socket_strerror(socket_last_error()) . ").<br>\n";
		$saida['error'] .= "Make sure monast.py is running so the panel can connect to its port properly.</p>";
	}
	else 
	{
		$buffer = "";
		$action = array('Action' => 'Login', 'username' => $username, 'secret' => $secret, 'session' => $sessionId);
		socket_write($sock, $json->encode($action));
		
		while ($message = socket_read($sock, 1024 * 16)) 
		{
			$buffer .= $message;
			
			if ($buffer == "OK")
			{
				setValor('login', true);
				setValor('username', $username);
				$saida['success'] = true;
				
				socket_write($sock, "BYE");
			}
			
			if (strpos($buffer, "ERROR: ") !== false)
			{
				$message        = str_replace("ERROR: ", "", $buffer);
				$saida['error'] = $message;
				
				socket_write($sock, "BYE");
			}
		}
		socket_close($sock);
	}
}

echo $json->encode($saida);

session_write_close();

?>