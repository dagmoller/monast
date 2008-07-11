
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
*     * Neither the name of the <ORGANIZATION> nor the names of its contributors
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

var mantemHide = false;
/*
* Classe do DIV que mostra o STATUS...
*/
ProgressDiv = function(divId)
{
	var _width  = 400;
	this._width = _width;
	
	this._div    = document.createElement('div');
	this._div.id = 'status_div_' + divId;
	
	this._div.className = 'div-message';
	//this._div.class     = 'div-message';
	
	this._div.style.width = _width + 'px';
	
	this._putDivInDocument = function()
	{
		document.body.appendChild(this._div);
	}

	this._setPosition = function()
	{
		var _top  = (document.body.clientHeight + (document.body.scrollTop * 2)) / 2 - 100;
		var _left = (document.body.clientWidth + (document.body.scrollLeft * 2)) / 2 - (_width / 2);
		
		this._div.style.top  = _top + 'px';
		this._div.style.left = _left + 'px';
	}

	this._hideFields = function(hide)
	{
		mantemHide = hide;
		//var inputs    = document.getElementsByTagName('input');
		var selects   = document.getElementsByTagName('select');
		var textareas = document.getElementsByTagName('textarea');
		
		var status = (hide ? 'hidden' : 'visible');
		/*
		for (i = 0; i < inputs.length; i++)
		{
			inputs[i].style.visibility = status;
		}*/
		for (i = 0; i < selects.length; i++)
		{
			selects[i].style.visibility = status;
		}
		for (i = 0; i < textareas.length; i++)
		{
			textareas[i].style.visibility = status;
		}
	}	

	this.show = function()
	{
		this._setPosition();
		this._hideFields(true);
		this._div.style.visibility = 'visible';
	}
	
	this.hide = function(checkAjax)
	{
		this._div.style.visibility = 'hidden';

		if (checkAjax == true)
		{
			for (i = 0; i < ajaxCall._listaAjax.length; i++)
			{
				if (ajaxCall._listaAjax[i].lock)
				{
					return;
				}
			}
		}
		this._hideFields(false);
	}

	this.setMessage = function(message, isErrorMessage, appendMessage)
	{
		var msg = '<center><font color="black">' + message + '</font></center>';
		
		this._div.innerHTML = msg;
	}
	
	this.setErrorMessage = function(message, description)
	{
		var msg = '<center><font color="red">' + message + '</font></center>';
		msg = msg + '<hr><font color="black">' + description + '</font>';
		msg = msg + '<br><hr><center><button class="botao" onClick="unhideAll(\'' + this._div.id + '\')">OK</button></center>';
		
		this._div.innerHTML   = msg;
	}
}

function unhideAll(id_div)
{
	for (i = 0; i < ajaxCall._listaAjax.length; i++)
	{
		ajaxCall._listaAjax[i]._progressDiv.hide(true);
	}
}

function replaceAll( str, from, to ) 
{
	var idx = str.indexOf( from );
	while ( idx > -1 ) 
	{
		str = str.replace( from, to );
		idx = str.indexOf( from );
	}
	return str;
}

// Definicoes para mensgens do AJAX...
_waitMessage    = new Array();
_waitMessage[0] = 'Estabelecendo conex�o, aguarde...';
_waitMessage[1] = 'Carregando dados do servidor...';
_waitMessage[2] = 'Carga completa...';
_waitMessage[3] = 'Processando dados, aguarde...';
_waitMessage[4] = 'Finalizando...';

/*
* Classe para trabalhar com AJAX.
*/
AjaxCallObject = function()
{
	this._listaAjax = new Array();
	
	this.init = function(showProgress, debug)
	{		
		var nextId     = this._listaAjax.length;
		var createNew  = false;
		
		if (nextId == 0)
		{
			createNew = true;
		}
		else
		{
			for (i = 0; i < nextId; i++)
			{
				if (!this._listaAjax[i].lock)
				{
					nextId = i;
					break;
				}
				
				if ((i + 1) == nextId)
				{
					createNew = true;
					break;
				}
			}
		}
		
		if (createNew)
		{
			//alert('Criado ajax: ' + nextId);
			this._listaAjax[nextId]              = function(){}
			this._listaAjax[nextId]._ajax        = this._createNewAjax(nextId);
			this._listaAjax[nextId]._progressDiv = new ProgressDiv(nextId);
			this._listaAjax[nextId]._progressDiv._putDivInDocument();
			this._listaAjax[nextId]._showProgressDiv = true;
			this._clean(nextId);
			this._listaAjax[nextId].lock = true;
		}
		else
		{
			//alert('Reuso do ajax: ' + nextId);
			this._clean(nextId);
			this._listaAjax[i].lock = true;
		}
		
		if (showProgress == false)
		{
			this._listaAjax[nextId]._showProgressDiv = false;
		}
		
		if (debug == true)
		{
			this._listaAjax[nextId]._debug = true;
		}
		
		return nextId;
	}
	
	this._createNewAjax = function()
	{
		var ajax = null;
		try
		{
			ajax = new XMLHttpRequest();
		}
		catch(e)
		{
			try
			{
				ajax = new ActiveXObject("Msxml2.XMLHTTP");
			}
			catch (e)
			{
				try
				{
					ajax = new ActiveXObject("Microsoft.XMLHTTP");
				}
				catch (e)
				{
					alert('Impossíel criar requisição AJAX!');
					return;
				}
			}
		}
		return ajax;
	}

	this._clean = function(id)
	{
		this._listaAjax[id]._url          = '';
		this._listaAjax[id]._method       = 'GET';
		this._listaAjax[id]._params       = 'isAjax=1';
		this._listaAjax[id]._isAsync      = true;
	
		this._listaAjax[id]._headers = new Array();
		this._listaAjax[id]._headers['Content-Type'] = 'application/x-www-form-urlencoded';
		
		this._listaAjax[id]._responseType     = 'TEXT';
		this._listaAjax[id]._responseFunction = function() {}
		
		this._listaAjax[id].lock = false;
		
		this._listaAjax[id]._debug = false;
	}
	
	this.getAjaxObject = function(id)
	{
		return this._listaAjax[id]._ajax;
	}
	
	this.setURL = function(id, url)
	{
		this._listaAjax[id]._url = url;
	}

	this.setMethod = function(id, method)
	{
		this._listaAjax[id]._method = method;
	}

	this.setParams = function(id, params)
	{
		this._params = params;
	}
	
	this.addParam = function(id, paramName, paramValue)
	{
		this._listaAjax[id]._params = this._listaAjax[id]._params + '&' + escape(paramName) + '=' + escape(paramValue);
	}

	this.addHeader = function(id, headerName, headerValue)
	{
		this._listaAjax[id]._headers[headerName] = headerValue;
	}

	this.setResponseType = function(id, responseType)
	{
		this._listaAjax[id]._responseType = responseType.toUpperCase();
	}

	this.setResponseFunction = function(id, responseFunction)
	{
		this._listaAjax[id]._responseFunction = responseFunction;
	}
	
	this.useParamsFromForm = function(ajaxId, formName)
	{
		var form  = document.forms[formName];
		var itens = new Array();
		
		for (i = 0; i < form.length; i++)
		{
			var id    = form[i].id;
			var name  = form[i].name;
			var value = form[i].value;
			var type  = form[i].type;
			
			id = (id ? id : name);
			
			if (!form[i].disabled)
			{			
				if (type == 'text' || type == 'textarea' || type == 'hidden' || type == 'password')
				{
					itens[i] = id + '=' + escape(value);
				}
				else if (type == 'checkbox' && form[i].checked)
				{
					itens[i] = id + '=' + escape(value);
				}
				else if (type.indexOf('select') != -1)
				{
					if (form[i].multiple)
					{
						var list = new Array();
						for (j = 0; j < form[i].options.length; j++)
						{
							if (form[i].options[j].selected)
							{
								list[list.length] = id + '=' + escape(form[i].options[j].value);
							}
						}
						itens[i] = list.join('&');
					}
					else
					{
						itens[i] = id + '=' + escape(form[i].options[form[i].selectedIndex].value);
					}
				}
				else if (type == 'radio')
				{
					if (form[i].checked)
					{
						itens[i] = id + '=' + escape(value);
					}
				}
			}
		}
		this._listaAjax[ajaxId]._params = 'isAjax=1&' + itens.join('&');
	}
	
	this._responseMethod = function(ajaxId)
	{
		var ajax = ajaxCall._listaAjax[ajaxId]._ajax;
		
		if (ajaxCall._listaAjax[ajaxId]._showProgressDiv)
		{
			ajaxCall._listaAjax[ajaxId]._progressDiv.show();
			ajaxCall._listaAjax[ajaxId]._progressDiv.setMessage(_waitMessage[ajax.readyState]);
		}

		//this.debugMessage(ajaxId, 'readyState: ' + ajax.readyState)
		
		if (ajax.readyState == 4)
		{
			if (ajax.status == 200)
			{
				this.debugMessage(ajaxId, 'responseText: ' + ajaxCall._listaAjax[ajaxId]._ajax.responseText);
				try
				{				
					if (ajaxCall._listaAjax[ajaxId]._responseType == 'XML')
					{
						eval('ajaxCall._listaAjax[' + ajaxId + ']._responseFunction(ajaxCall._listaAjax[' + ajaxId + ']._ajax.responseXML)');
					}
					else if (ajaxCall._listaAjax[ajaxId]._responseType == 'OBJ')
					{
						var json = new JSON();
						var obj  = json.decode(ajaxCall._listaAjax[ajaxId]._ajax.responseText);

						eval('ajaxCall._listaAjax[' + ajaxId + ']._responseFunction(obj)');
					}
					else
					{
						eval('ajaxCall._listaAjax[' + ajaxId + ']._responseFunction(ajaxCall._listaAjax[' + ajaxId + ']._ajax.responseText)');
					}
					ajaxCall._listaAjax[ajaxId].lock = false;

					if (ajaxCall._listaAjax[ajaxId]._showProgressDiv)
					{
						ajaxCall._listaAjax[ajaxId]._progressDiv.hide(true);
					}
				}
				catch (error)
				{
					__content = '<br><hr><center><b><font color="red">!! erro processando a resposta AJAX !!</font></b></center></br><hr><div align="left">' + error + '</div>';
					return;
				}
			}
			else
			{
				var msg = ajax.status + ' - ' + ajax.statusText;
				__content = '<br><hr><center><b><font color="red">!! Ocorreu um erro durante a requisição !!</font></b></center></br><hr><div align="left">' + msg + '</div>';
				return;
			}
		}
	}
	
	this.doCall = function(id)
	{
		if (this._listaAjax[id]._method == 'GET')
		{
			if (this._listaAjax[id]._url.indexOf('?') != -1)
			{
				this._listaAjax[id]._ajax.open(this._listaAjax[id]._method, this._listaAjax[id]._url, this._listaAjax[id]._isAsync);
			}
			else
			{
				this._listaAjax[id]._ajax.open(this._listaAjax[id]._method, this._listaAjax[id]._url + '?' + this._listaAjax[id]._params, this._listaAjax[id]._isAsync);
			}
		}
		else
		{
			this._listaAjax[id]._ajax.open(this._listaAjax[id]._method, this._listaAjax[id]._url, this._listaAjax[id]._isAsync);
		}
		this.debugMessage(id, 'URL: ' + this._listaAjax[id]._url + '?' + unescape(this._listaAjax[id]._params));
		
		for (key in this._listaAjax[id]._headers)
		{
			this._listaAjax[id]._ajax.setRequestHeader(key, this._listaAjax[id]._headers[key]);
		}
		
		var _this = this;
		this._listaAjax[id]._ajax.onreadystatechange = function(){_this._responseMethod(id)};
		
		if (this._listaAjax[id]._method == 'GET')
		{
			this._listaAjax[id]._ajax.send(null);
		}
		else
		{
			this._listaAjax[id]._ajax.send(this._listaAjax[id]._params);
		}
	}
	
	this.debugMessage = function(id, message)
	{
		if (this._listaAjax[id]._debug)
		{
			var debugArea = document.getElementById('__debug_area');
			if (!debugArea)
			{
				debugArea = document.createElement('textarea');
				debugArea.id = '__debug_area';
				debugArea.cols = '150';
				debugArea.rows = '15';
				document.body.appendChild(debugArea);
			}			
			debugArea.value = debugArea.value + 'Ajax ID: ' + id + ' - ' + message + '\n';
		}
	}
}
var ajaxCall = new AjaxCallObject();

/*
    json.js
    2006-09-27

    This file adds these methods to JavaScript:

        object.toJSONString()

            This method produces a JSON text from an object. The
            object must not contain any cyclical references.

        array.toJSONString()

            This method produces a JSON text from an array. The
            array must not contain any cyclical references.

        string.parseJSON()

            This method parses a JSON text to produce an object or
            array. It will return false if there is an error.

    It is expected that these methods will formally become part of the
    JavaScript Programming Language in the Fourth Edition of the
    ECMAScript standard.
*/

JSON = function()
{
	this.encode = function(obj)
	{
		if (obj instanceof Object)
		{
			return ___JSONParser.object(obj);
		}
		else if (obj instanceof Array)
		{
			return ___JSONParser.array(obj);
		}
		else
		{
			return ___JSONParser.string(obj);
		}
	}
	
	this.decode = function(jsonString)
	{
		//var regExp = /\{.*\}/;
		//var jsonString = jsonString.match(regExp)[0];
		 
		return eval('(' + jsonString + ')');
	}
	
	this.serialize = function(obj)
	{
		return this.encode(obj);
	}
	
	this.deserialize = function(obj)
	{
		return this.decode(obj);
	}
}

var ___JSONm = {
	'\b': '\\b',
	'\t': '\\t',
	'\n': '\\n',
	'\f': '\\f',
	'\r': '\\r',
	'"' : '\\"',
	'\\': '\\\\'
};

var ___JSONParser = {
	array: function (x) {
		var a = ['['], b, f, i, l = x.length, v;
		for (i = 0; i < l; i += 1) {
			v = x[i];
			f = ___JSONParser[typeof v];
			if (f) {
				v = f(v);
				if (typeof v == 'string') {
					if (b) {
						a[a.length] = ',';
					}
					a[a.length] = v;
					b = true;
				}
			}
		}
		a[a.length] = ']';
		return a.join('');
	},
	'boolean': function (x) {
		return String(x);
	},
	'null': function (x) {
		return "null";
	},
	number: function (x) {
		return isFinite(x) ? String(x) : 'null';
	},
	object: function (x) {
		if (x) {
			//if (x instanceof Array) {
			//	return ___JSONParser.array(x);
			//}
			var a = ['{'], b, f, i, v;
			for (i in x) {
				v = x[i];
				f = ___JSONParser[typeof v];
				if (f) {
					v = f(v);
					if (typeof v == 'string') {
						if (b) {
							a[a.length] = ',';
						}
						a.push(___JSONParser.string(i), ':', v);
						b = true;
					}
				}
			}
			a[a.length] = '}';
			return a.join('');
		}
		return 'null';
	},
	string: function (x) {
		if (/["\\\x00-\x1f]/.test(x)) {
                    x = x.replace(/([\x00-\x1f\\"])/g, function(a, b) {
		var c = ___JSONm[b];
		if (c) {
			return c;
		}
		c = b.charCodeAt();
		return '\\u00' +
		Math.floor(c / 16).toString(16) +
		(c % 16).toString(16);
                    });
	}
	return '"' + x + '"';
}};

// Obfuscator DIV
var __scrollXValue = 0;
var __scrollYValue = 0;
var __content = '';

function showLoading(clearContent)
{
	var obfIn = document.getElementById('obfuscatorIn');
	var obfLd = document.getElementById('obfuscatorLd');

	if (clearContent)
	{
		__content = '';
	}

	if (__content == '')
	{
		obfLd.style.visibility = 'visible';
		obfLd.style.display    = 'inline';
		setTimeout("showLoading()", 2000);
	}
	else if (__content != '&nbsp;')
	{
		obfIn.innerHTML = __content;
		obfLd.style.visibility = 'hidden';
		obfLd.style.display    = 'none';
		obfIn.style.height     = 'auto';

		if (__content.indexOf('executeJson()') != -1)
		{
			var r = new RegExp(/\@\{.*\}/);
			var j = r.exec(__content);
			if (j != null)
			{
				var json = new JSON();
				for (i = 0; i < j.length; i++)
				{
					var obj = json.decode(j[i].substring(1));
					for (k in obj)
					{
						var c = document.getElementById(k);
						c.innerHTML = obj[k];
					}
				}
			}
		}

		/* // Este codigo nao funciona no IE.
		var scripts = obfIn.getElementsByTagName('script');
		for (i = 0; i < scripts.length; i++)
		{
			if (scripts[i].text)
			{
				var script = document.createElement('script');
				script.text = scripts[i].text;
				document.body.appendChild(script);
			}
		} */
	}
}

var __ajaxContentType = '';
Obfuscator = function(widthIn, heightIn)
{
	var topMargin = 50;

	this.ie     = document.all && !window.opera;
	this._obf   = document.getElementById('obfuscator');
	this._obfIn = document.getElementById('obfuscatorIn');
	this._obfCl = document.getElementById('obfuscatorCl');
	this._obfLd = document.getElementById('obfuscatorLd');

	var width       = (this.ie ? document.documentElement.clientWidth : window.innerWidth);
	var height      = (this.ie ? document.documentElement.clientHeight : window.innerHeight);
	var tmpWidth    = (this.ie ? document.body.clientWidth : (!window.opera ? document.width : document.body.offsetWidth));
	var tmpHeight   = (this.ie ? document.body.clientHeight + 20 : (!window.opera ? document.height : document.body.offsetHeight));
	var scrollXSize = (this.ie ? document.documentElement.scrollLeft : (!window.opera ? window.scrollX : document.body.scrollLeft));
	var scrollYSize = (this.ie ? document.documentElement.scrollTop : (!window.opera ? window.scrollY : document.body.scrollTop));

	if (!this._obf)
	{
		widthIn  = (widthIn ? widthIn : 500);
		heightIn = (heightIn ? heightIn : 300);
	}
	
	this._obf.style.top    = 0;
	this._obf.style.left   = 0;
	this._obf.style.width  = (width > tmpWidth ? width : tmpWidth)  + 'px'; 
	this._obf.style.height = (height > tmpHeight ? height : tmpHeight) + 2000 + 'px';
	
	if (widthIn)
	{
		this._obfIn.style.width = (widthIn > width ? width : widthIn) + 'px';
		this._obfIn.style.left  = ((width / 2) - (widthIn / 2)) + scrollXSize + 'px';

		this._obfCl.style.left = parseInt(this._obfIn.style.left.replace('px', '')) + parseInt(this._obfIn.style.width.replace('px', '')) - 53 + 'px';
		this._obfLd.style.left = ((width / 2) - (100 / 2)) + scrollXSize + 'px';
	}

	if (heightIn)
	{
		this._obfIn.style.height = (heightIn > height ? height : heightIn) + 'px';
		this._obfIn.style.top    = topMargin + scrollYSize + 'px';

		this._obfCl.style.top  = parseInt(this._obfIn.style.top.replace('px', '')) - 17 + 'px';
		this._obfLd.style.top  = (parseInt(this._obfIn.style.height.replace('px', '')) / 2) + parseInt(this._obfIn.style.top.replace('px', '')) + 'px';
	}

	this.obfuscate = function()
	{
		this._obfIn.innerHTML = '';

		__scrollXValue = (this.ie ? document.documentElement.scrollLeft : (!window.opera ? window.scrollX : document.body.scrollLeft));
		__scrollYValue = (this.ie ? document.documentElement.scrollTop : (!window.opera ? window.scrollY : document.body.scrollTop));

		this._obf.style.visibility   = 'visible';
		this._obf.style.display      = 'inline';
		this._obfIn.style.visibility = 'visible';
		this._obfIn.style.display    = 'inline';
		this._obfCl.style.visibility = 'visible';
		this._obfCl.style.display    = 'inline';
		__content = '';

		showSelects(false);
	}

	this.restore = function()
	{
		this._obf.style.visibility   = 'hidden';
		this._obf.style.display      = 'none';
		this._obfIn.style.visibility = 'hidden';
		this._obfIn.style.display    = 'none';
		this._obfCl.style.visibility = 'hidden';
		this._obfCl.style.display    = 'none';
		this._obfLd.style.visibility = 'hidden';
		this._obfLd.style.display    = 'none';
		__content = '&nbsp;';

		showSelects(true);
	}

	this._putAjaxIn = function(content)
	{
		__content = content;
	}

	this.setAjaxContent = function(url)
	{
		showLoading();
		this._obfIn.innerHTML = '';

		var ajaxId = ajaxCall.init(false);
		ajaxCall.setURL(ajaxId, url);
		ajaxCall.setResponseFunction(ajaxId, this._putAjaxIn);
		
		if (__ajaxContentType != '')
		{
			ajaxCall.addHeader(ajaxId, 'Content-Type', __ajaxContentType);
		}

		ajaxCall.doCall(ajaxId);
	}

	this.setContent = function(content)
	{
		this._obfIn.innerHTML    = content;
		this._obfIn.style.height = 'auto';
	}
}

__obfDD = null;
function openObfuscator(url, width, height)
{
	width  = (width ? width : 500);
	height = (height ? height : 320);

	var obf = new Obfuscator(width, height);
	obf.obfuscate();
	obf.setAjaxContent(url);
	__obfDD = obf;
}

function openImageObfuscator(imgUrl, width, height)
{
	var obf = new Obfuscator(width, height);
	obf.obfuscate();

	var myImg = new Image();
	myImg.src = imgUrl;
	myImg.style.margin = '5px 0px';
	obf._obfIn.appendChild(myImg);
}

function closeObfuscator()
{
	var obf = new Obfuscator();
	obf.restore();
}


// artimanhas para envio de form via ajax

function __responseFunction(content)
{
	// testa se eh uma JSONString...
	if (content.match(/^\{.*\}/))
	{
		var json = new JSON();
		__processJSONObject(json.decode(content));
	}
	else
	{
		__content = content;
	}
}

function __processJSONObject(obj)
{
	__content = '&nbsp;';
	if (obj['doAlert'])
	{
		alert(obj['doAlert']);
	}

	if (obj['doAction'])
	{
		eval(obj['doAction']);
	}

	if (obj['doCallHref'])
	{
		location.href = obj['doCallHref']; 
	}

	if (obj['doReload'])
	{
		location.reload();
	}

	if (obj['doFormSubmit']) 
	{
		try {
			document.getElementById(getNetuiTagName(obj['doFormSubmit'])).submit();
		} catch (e) {
			document.getElementById(obj['doFormSubmit']).submit();
		}
	}
}

function sendFormViaAjax(fn)
{
	var f = document.getElementById(fn);
	showLoading(true);

	var ajaxId = ajaxCall.init(false);
	ajaxCall.setMethod(ajaxId, 'post');
	ajaxCall.setURL(ajaxId, f.action);
	ajaxCall.useParamsFromForm(ajaxId, fn);
	ajaxCall.setResponseFunction(ajaxId, __responseFunction);
	ajaxCall.doCall(ajaxId);
}

// deve ser usado no onMouseUp do anchor que faz o formSubmit.
var __debug = false;
function sendFormViaIframe(fn)
{
	var f = document.getElementById(fn);
	showLoading(true);
	
	f.target = '__ifPostForm';

	var iframePost = document.getElementById('__ifPostForm');
	if (__debug)
	{
		closeObfuscator();
		iframePost.style.width      = '800px';
		iframePost.style.height     = '600px';
		iframePost.style.visibility = 'visible';
		iframePost.style.display    = 'block';
	}
	else
	{
		if (document.all && !window.opera) // IE! o IE nao possui onLoad no iframe!!!
		{
			iframePost.onreadystatechange = function()
			{
				var iframePost = document.getElementById('__ifPostForm');
				if (iframePost.readyState == 'complete')
				{
					__responseFunction(__ifPostForm.document.body.innerHTML);
				}
			}
		}
		else // Mozilla Based... 
		{
			iframePost.onload = function()
			{
				__responseFunction(__ifPostForm.document.body.innerHTML);
			}
		}
	}
}
