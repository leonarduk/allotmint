function handler(event) {
    var request = event.request;
    var headers = request.headers;
    var host = headers.host.value;
    var protoHeader = headers['cloudfront-forwarded-proto'];
    var proto = protoHeader ? protoHeader.value : 'https';
    var canonical = 'app.allotmint.io';
    var uri = request.uri;
    var query = request.querystring;
    var qs = '';
    if (query && Object.keys(query).length > 0) {
        var qsParts = [];
        for (var key in query) {
            if (query.hasOwnProperty(key)) {
                var val = query[key].value;
                qsParts.push(key + '=' + val);
            }
        }
        if (qsParts.length > 0) {
            qs = '?' + qsParts.join('&');
        }
    }

    var targetHost = host !== canonical ? canonical : host;
    var targetUri = uri;
    if (uri.length > 1 && uri.endsWith('/')) {
        targetUri = uri.slice(0, -1);
    }
    var redirectNeeded =
        proto === 'http' || host !== canonical || targetUri !== uri;
    if (redirectNeeded) {
        return {
            statusCode: 301,
            statusDescription: 'Moved Permanently',
            headers: {
                location: {
                    value: 'https://' + targetHost + targetUri + qs,
                },
            },
        };
    }
    return request;
}
