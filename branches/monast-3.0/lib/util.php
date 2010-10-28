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

require_once 'HTTP/Client.php';

function color($t)
{
    $t = trim(strtolower($t));
    switch ($t)
    {
        case 'down':
        case 'unregistered':
        case 'unreachable':
        case 'unknown':
        case 'unavailable':
        case 'invalid':
        case 'busy':
        case 'logged out':
            //return 'red';
            return '#ffb0b0';
            
        case 'ring':
        case 'ringing':
        case 'ring, in use':
        case 'in use':
        case 'dial':
        case 'lagged':
        case 'on hold':
            //return 'yellow';
            return '#ffffb0';
            
        case 'up':
        case 'link':
        case 'registered':
        case 'reachable':
        case 'unmonitored':
        case 'not in use':
        case 'logged in':
        case 'no alarm':
            //return 'green';
            return '#b0ffb0';
    }
    
    if (strpos($t, 'signal') != -1)
    {
    	$level = str_replace("%", "", str_replace("signal: ", "", $t));
    	if ($level >= 70)
    		return '#b0ffb0';
    	if ($level >= 40 && $level < 70)
    		return '#ffffb0';
    	if ($level < 40)
    		return '#ffb0b0';
    }
    
    return '#dddddd';
}

function getValor($nome, $location = 'request')
{
	$location = '_' . strtoupper($location);
	eval("\$location = &$$location;");
	
	if (isset($location[$nome]))
	{
		return $location[$nome];
	}
	return '';	
}

function setValor($nome, $valor, $location = 'session')
{
	$location = '_' . strtoupper($location);
	eval("\$location = &$$location;");
	
	$location[$nome] = $valor;
}

function print_pre($obj)
{
	echo "<pre>";
	print_r($obj);
	echo "</pre>";
}

define("MONAST_PYTHON_COOKIE_KEY", "MonAst::Cookie");
function doGet($path, $data = array())
{
	session_start();
	$cookieManager = getValor(MONAST_PYTHON_COOKIE_KEY, 'session');
	$cookieManager = $cookieManager ? unserialize($cookieManager) : null;
	session_write_close();
	
	$conn = new HTTP_Client(null, null, $cookieManager);
	$code = $conn->get("http://" . HOSTNAME . ':' . HOSTPORT . '/' . $path, $data);
	
	switch ($code)
	{
		case Pear::isError($code):
			if ($code->getCode() == 111 || strtolower($code->getMessage()) == "connection refused")
				return "ERROR :: Connection Refused";
			break;
		
		case 500:
			return "ERROR :: Internal Server Error";
			break;
	}
	
	$cookieManager = $conn->getCookieManager();
	$cookieManager->serializeSessionCookies(true);
	session_start();
	setValor(MONAST_PYTHON_COOKIE_KEY, serialize($cookieManager), 'session');
	session_write_close();
	
	$response = $conn->currentResponse();
	$body     = trim($response['body']);
	
	return $body;
}

?>