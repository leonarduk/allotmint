function handler(event) {
    var request = event.request;
    var headers = request.headers;
    var host = headers.host.value;
    var protoHeader = headers['cloudfront-forwarded-proto'];
    var proto =
        protoHeader &&
        (protoHeader.value === 'http' || protoHeader.value === 'https')
            ? protoHeader.value
            : null;
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

    var targetHost = host === canonical ? host : canonical;
    if (!/^[A-Za-z0-9.-]+$/.test(targetHost)) {
        targetHost = canonical;
    }
    var targetUri = uri;
    if (!/^\/[A-Za-z0-9\/._-]*$/.test(targetUri)) {
        targetUri = '/';
    }
    if (targetUri.length > 1 && targetUri.endsWith('/')) {
        targetUri = targetUri.slice(0, -1);
    }
    var redirectNeeded =
        proto !== 'https' || host !== canonical || targetUri !== uri;
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
