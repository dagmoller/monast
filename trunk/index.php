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

header("Cache-Control: no-cache, must-revalidate");
header("Pragma: no-cache");
header("Expires: -1");

session_start();
$login    = getValor('login', 'session');
$username = getValor('username', 'session');
$errorTemplate = "";
$errorVars     = array();
setValor('Actions', array());
setValor('Servers', array());
session_write_close();

$template = new TemplatePower('template/index.html');

if (!$login)
{
	$response = doGet("isAuthenticated");
	switch ($response)
	{
		case "ERROR :: Connection Refused":
			$errorTemplate = "Language.connectionError";
			$errorVars     = array("HOSTNAME" => HOSTNAME, "HOSTPORT" => HOSTPORT, "RESPONSE" => $response);
			break;
			
		case "ERROR :: Request Not Found":
			$errorTemplate = "Language.requestError";
			$errorVars     = array("HOSTNAME" => HOSTNAME, "HOSTPORT" => HOSTPORT);
			break;
			
		case "ERROR :: Internal Server Error":
			$errorTemplate = "Language.internalServerError";
			$errorVars     = array("HOSTNAME" => HOSTNAME, "HOSTPORT" => HOSTPORT);
			break;
		
		case "ERROR: Authentication Required":
			session_start();
			setValor('login', false);
			setValor('username', '');
			session_write_close();
			break;
			
		case "OK":
			$login = true;
			session_start();
			setValor('login', true);
			session_write_close();
			break;
	}
}

if (!$errorTemplate)
{
	session_start();
	$errorTemplate = getValor('errorTemplate', 'session');
	$errorVars     = getValor('errorVars', 'session');
	setValor('errorTemplate', "");
	setValor('errorVars', "");
	session_write_close();
}

if ($errorTemplate)
{
	$template->prepare();
	$template->newBlock('error');
	$template->assign('errorTemplate', $errorTemplate);
	$template->assign('errorVars', monast_json_encode($errorVars, false));
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
		
		session_start();
		$servers = getValor('Servers', 'session');
		$server  = getValor('Server', 'session');
		session_write_close();
		if (count($servers) == 1)
		{
			$template->newBlock('singleServer');
			$template->assign('server', $server);
		}
		else
		{
			$template->newBlock('serverList');
			foreach ($servers as $serv)
			{
				$template->newBlock('optionServer');
				$template->assign('server', $serv);
				if ($serv == $server)
					$template->assign('selected', 'selected');
			}
		}
		
		if ($username)
			$template->newBlock('buttonLogout');
	}
}

if (defined("MONAST_LANGUAGE"))
	$template->assign("_ROOT.MONAST_LANGUAGE", MONAST_LANGUAGE);
else 
	$template->assign("_ROOT.MONAST_LANGUAGE", "en");

$template->printToScreen();

?>
