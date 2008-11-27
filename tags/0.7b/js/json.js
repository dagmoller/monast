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
