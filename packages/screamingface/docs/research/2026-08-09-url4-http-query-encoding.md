# URL4 expression encoding at the HTTP `q=` boundary

Date: 2026-08-09
Scope: first-party sources in `packages/url4`, `apps/url4-cloud`, the ScreamingFace Python
client, and the locally cloned `screamingface-design` repository.

## Conclusion

Percent-encoding a URL4 expression when it is carried as the value of an HTTP `q` query
parameter is intentional. It is HTTP/URI transport encoding, not a second URL4 expression
syntax and not part of the expression stored in a leaderboard entry.

The layers are:

```text
URL4 expression (stored/readable)
    (candidate: ...)!''

HTTP transport
    GET /?q=%28candidate%3A%20...%29%21%27%27

URL4 Cloud handler (decoded q value)
    (candidate: ...)!''
```

The Python client preserves this separation: it retains the plain expression as `url4` and
passes it to HTTPX as `params={"q": url4}`, letting the HTTP client encode the query-parameter
value ([client transport, lines 310–319](../../src/screamingface/_engine/transport.py#L310-L319)).
URL4 Cloud declares `q` as a normal string query parameter and schedules the decoded value
([execution route, lines 396–449](../../../../apps/url4-cloud/src/url4_cloud/rest/routes.py#L396-L449)).

## Why the encoding is necessary

The URL4 design deliberately makes HTTP GET a first-class wire transport and puts only the
expression in `q=`; sibling query parameters carry protocol metadata
([URL4 Spec B, lines 31–51](../../../../../screamingface-design/kevin-mcdonough/docs/adrs/URL4-Spec-B.md#L31-L51)).
Once an expression is inside an HTTP query parameter, ordinary URI rules apply.

Encoding prevents expression content from being mistaken for HTTP structure. In particular,
an embedded `&` would otherwise start another query parameter. The design therefore requires
`&` inside an expression-bearing parameter to be sent as `%26`, followed by normal server-side
percent-decoding before URL4 parsing
([URL4 Spec B, lines 107–148](../../../../../screamingface-design/kevin-mcdonough/docs/adrs/URL4-Spec-B.md#L107-L148)).
The same transport boundary covers spaces, `#`, braces, percent signs, control characters, and
other characters HTTP clients or intermediaries cannot safely carry verbatim
([URL4 Spec B, lines 174–196](../../../../../screamingface-design/kevin-mcdonough/docs/adrs/URL4-Spec-B.md#L174-L196)).

The package implementation makes that policy explicit. Its URL4-native subrequest encoder keeps
the wire readable but escapes characters that would corrupt URL parsing, while its HTTP decoder
also accepts the fully percent-encoded form produced by standard clients such as HTTPX, browsers,
`URLSearchParams`, and `curl --data-urlencode`
([subrequest codec, lines 25–83](../../../url4/src/url4/core/subrequest.py#L25-L83),
[dual-convention decoder, lines 110–171](../../../url4/src/url4/core/subrequest.py#L110-L171)).
Conformance tests verify that spaces and structural characters round-trip and that fully encoded
relative, canonical, and `url4://` expressions decode to the author's original text
([wire tests, lines 65–98](../../../url4/tests/spec/test_wire_spec.py#L65-L98),
[wire tests, lines 108–137](../../../url4/tests/spec/test_wire_spec.py#L108-L137)).

Consequently, full percent-encoding by the Python client is valid and intended. URL4 also has a
more readable raw-structural wire convention, but a receiving node is designed to accept both;
callers should normally let their HTTP library encode `q` rather than concatenate a large raw
expression into a URL manually.

## What `url4://` means

`url4://` identifies a URL4-aware remote endpoint. It is semantic: unlike an ordinary `https://`
source, the receiver is expected to apply URL4 protocol behavior. On the wire, a remote
`url4://host/path` target maps to `https://host/path`
([URL4 Spec B, lines 198–218](../../../../../screamingface-design/kevin-mcdonough/docs/adrs/URL4-Spec-B.md#L198-L218)).
The package adapter performs exactly that translation
([HTTP I/O adapter, lines 17–25 and 70–79](../../../url4/src/url4/io/http.py#L17-L25),
[HTTP I/O adapter, lines 70–79](../../../url4/src/url4/io/http.py#L70-L79)).

The design's canonical remote form is
`url4://node/path?[protocol-params&]q=<expression>`; the expression itself does not acquire a
`url4://` prefix merely because it is sent to an engine
([URL4 Spec B, lines 53–63](../../../../../screamingface-design/kevin-mcdonough/docs/adrs/URL4-Spec-B.md#L53-L63)).
The design guide says the same thing in user-facing terms: `url4://host/path` maps to
`https://host/path`, and HTTP transport still requires normal percent-encoding
([URL4 rundown, lines 326–330](../../../../../screamingface-design/reports/url4-rundown.html#L326-L330),
[URL4 rundown, lines 340–358](../../../../../screamingface-design/reports/url4-rundown.html#L340-L358)).

For the local SF Engine, the engine origin is already supplied separately as
`http://127.0.0.1:9108`. A stored targetless expression such as `(candidate: ...)!''` is therefore
run as `GET http://127.0.0.1:9108/?q=<encoded-expression>`; prepending `url4://` to that expression
would change its syntax and meaning rather than make it more executable.
