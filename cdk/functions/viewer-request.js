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
    // __CANONICAL_HOST__ is substituted at CDK synth time (see
    // static_site_stack.py): a JSON string holding the configured custom
    // domain when this deployment has one (alias + ACM certificate + DNS
    // record), or `null` when it does not. When it is `null`,
    // host-based canonicalization is skipped entirely so the function never
    // redirects viewers to a domain that has no DNS record for this
    // distribution — see issue #3693 (production outage caused by an
    // unconditional redirect to a non-existent custom domain).
    var canonical = __CANONICAL_HOST__;
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

    var targetHost = host;
    if (canonical) {
        targetHost = host === canonical ? host : canonical;
        if (!/^[A-Za-z0-9.-]+$/.test(targetHost)) {
            targetHost = canonical;
        }
    }
    var targetUri = uri;
    if (!/^\/[A-Za-z0-9\/._-]*$/.test(targetUri)) {
        targetUri = '/';
    }
    if (targetUri.length > 1 && targetUri.endsWith('/')) {
        targetUri = targetUri.slice(0, -1);
    }
    var redirectNeeded =
        proto !== 'https' ||
        (canonical !== null && host !== canonical) ||
        targetUri !== uri;
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
