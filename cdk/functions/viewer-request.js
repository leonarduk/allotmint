function handler(event) {
    var request = event.request;
    var headers = request.headers;
    var host = headers.host.value;
    var protoHeader = headers['cloudfront-forwarded-proto'];
    // 'cloudfront-forwarded-proto' is added by CloudFront for origin-request
    // events; it may be absent on viewer-request events.  The distribution's
    // ViewerProtocolPolicy.REDIRECT_TO_HTTPS guarantees that every request
    // reaching this function is already HTTPS, so treat a missing or
    // unrecognised value as 'https'.  Defaulting to null instead caused an
    // infinite self-redirect loop (proto !== 'https' → 301 to the same HTTPS
    // URL → proto still absent → 301 again) when no custom domain was
    // configured, resulting in ERR_TOO_MANY_REDIRECTS for Chrome users.
    // See issue #3763.
    var proto = protoHeader && protoHeader.value === 'http' ? 'http' : 'https';
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
    if (canonical && host !== canonical) {
        targetHost = canonical;
    }
    if (!/^[A-Za-z0-9.-]+$/.test(targetHost)) {
        if (canonical) {
            targetHost = canonical;
        } else {
            // No canonical host is configured for this deployment and the
            // incoming Host header fails the safety check, so there is no
            // trustworthy value to build a redirect Location from. Returning
            // it verbatim would be a host-header injection / open redirect
            // (see issue #3693 review). Pass the request through unmodified;
            // ViewerProtocolPolicy.REDIRECT_TO_HTTPS at the distribution
            // level still enforces the HTTPS upgrade for this viewer.
            return request;
        }
    }
    var targetUri = uri;
    if (!/^\/[A-Za-z0-9\/._-]*$/.test(targetUri)) {
        targetUri = '/';
    }
    if (targetUri.length > 1 && targetUri.endsWith('/')) {
        targetUri = targetUri.slice(0, -1);
    }
    // The distribution's ViewerProtocolPolicy.REDIRECT_TO_HTTPS already forces
    // an HTTPS upgrade, so `proto !== 'https'` is largely redundant here.
    // It is intentionally kept as defense-in-depth (e.g. for the
    // cloudfront-forwarded-proto header path, and in case the distribution
    // policy ever changes) and folded into the same single 301 alongside
    // host/URI canonicalization, avoiding a double redirect round-trip.
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
