# Changelog

## [1.4.0](https://github.com/OpenMined/screamingface/compare/url4-cloud-v1.3.0...url4-cloud-v1.4.0) (2026-08-18)


### Features

* `sf.CorrectiveLoop` and `sf.SelfCorrective` Independent Decision Protocols ([3c61290](https://github.com/OpenMined/screamingface/commit/3c612909d4f22df38ccf6aa8b53d1e084724231e))
* **aigateway:** register the open-weight notebook lineup members ([770257d](https://github.com/OpenMined/screamingface/commit/770257dccbb18fdbff596d903d9f6d3f93047f21))
* **benchmarks:** flatten public identities ([dfd8eb9](https://github.com/OpenMined/screamingface/commit/dfd8eb97b431d9ae02cf51edc334bd357c0b9b10))
* **benchmarks:** report corrective loop execution ([a644505](https://github.com/OpenMined/screamingface/commit/a644505d58054fc415380f5539257a6d67d62d40))
* **benchmarks:** report corrective loop execution ([7f92c69](https://github.com/OpenMined/screamingface/commit/7f92c696646367062a23aec7ac22e16bce070cae))
* DRACO check surface (draco-pass.v1) — sf.CorrectiveLoop runs on DRACO ([7ea9b7b](https://github.com/OpenMined/screamingface/commit/7ea9b7bc63d2f18ad31b901460eaed954f68ecbb))
* report real run cost from provider-authored OpenRouter evidence ([05d85f1](https://github.com/OpenMined/screamingface/commit/05d85f1fb136b24c8d8b43f4bf656e6c93a93f20))
* rubric_check component — sf.CorrectiveLoop runs on HealthBench ([bba683d](https://github.com/OpenMined/screamingface/commit/bba683def740b9f0840ba32a03f397343d5166ff))
* **screamingface:** enhance LeaderboardScore with scoreboard_url and improve HTML rendering ([24855ce](https://github.com/OpenMined/screamingface/commit/24855ce4856093aa6f0500fc2b1a1a5e146606d9))
* **url4-cloud:** add the declared model registry ([c7091c2](https://github.com/OpenMined/screamingface/commit/c7091c29bebf352dfd15593d5e9abdd0c6a30b54))
* **url4-cloud:** capture member and synthesis outputs in benchmark case artifacts ([8d70086](https://github.com/OpenMined/screamingface/commit/8d700860ba96c97eacf158d4c151629da9dfad67))
* **url4-cloud:** capture member and synthesis outputs in benchmark case artifacts ([28d8752](https://github.com/OpenMined/screamingface/commit/28d8752800359a2aff272694bdda26865ca364bb))
* **url4-cloud:** extract rubric_check and onboard HealthBench as configuration only ([b39c8d3](https://github.com/OpenMined/screamingface/commit/b39c8d3af45772ac9212f2567696828e73329021))
* **url4-cloud:** give DRACO a paid check surface so CorrectiveLoop runs on it ([4a8b77a](https://github.com/OpenMined/screamingface/commit/4a8b77ad4a4b59607c965a02a125156dd6fb8c99))
* **url4-cloud:** implement benchmark failure policy ([ebc6a96](https://github.com/OpenMined/screamingface/commit/ebc6a960033220df1c3ea677276d03f20135750c))
* **url4-cloud:** implement benchmark failure policy ([599d451](https://github.com/OpenMined/screamingface/commit/599d4510c9fa68974087f6fb30424a4d14f43d49))
* **url4-cloud:** lift the corrective loop into a generic ensemble substrate behind a check-surface port ([e1f18a2](https://github.com/OpenMined/screamingface/commit/e1f18a2b3cbc775128a5cc137fe923fcb51edf8d))
* **url4-cloud:** merge the model registry into the declared world ([3a53274](https://github.com/OpenMined/screamingface/commit/3a532748ac98f42171da97d8a6384287d72e53b5))
* **url4-cloud:** populate the declared model world from aigateway's compiled seeds ([90a104e](https://github.com/OpenMined/screamingface/commit/90a104e39186801553103b9342b60dcd64677562))
* **url4-cloud:** price runs from provider-authored cost evidence ([884aedd](https://github.com/OpenMined/screamingface/commit/884aedd6aad3af0bf2c647decb696feaab865d85))
* **url4-cloud:** record why a Run stream ended ([dabaf05](https://github.com/OpenMined/screamingface/commit/dabaf0504d2cfe72a877fda0ca9c5fe1286c4002))
* **url4-cloud:** route colon-bearing model ids via a ~ encoding ([3d1037a](https://github.com/OpenMined/screamingface/commit/3d1037a746fdedaa1dc583c8fe30836dc105f4b6))
* **url4-cloud:** route colon-bearing model ids via a ~ encoding ([d91d3d5](https://github.com/OpenMined/screamingface/commit/d91d3d505e7fa4b7ff76df9fed12ce75e7f33929))
* **url4-cloud:** seed the declared model world from every compiled provider ([3026b67](https://github.com/OpenMined/screamingface/commit/3026b6707affd0ff55b0aeea6040e57b8a9607ea))


### Bug Fixes

* address Filip's PR [#626](https://github.com/OpenMined/screamingface/issues/626) review (both passes on bf7f12f) ([99ab98c](https://github.com/OpenMined/screamingface/commit/99ab98c3b76b509170cb9b13ef0b99fb211949a4))
* attribute and remove websocket_disconnected drops ([151d257](https://github.com/OpenMined/screamingface/commit/151d2575d7777c2b19a560816ff91244bcb96011))
* **benchmarks:** preserve outcomes through grading failures ([6f16122](https://github.com/OpenMined/screamingface/commit/6f16122b9e9d94ca5f074ac0ce1abee842ffbd42))
* **benchmarks:** preserve outcomes through grading failures ([c3f3f97](https://github.com/OpenMined/screamingface/commit/c3f3f97a52f72bc6fe37436b1c73f7911802341e))
* close corrective loop review gaps ([3f7cacd](https://github.com/OpenMined/screamingface/commit/3f7cacdc6c5e43f405170689dfc22be1ff7c7743))
* complete corrective recipe execution contracts ([2229ff0](https://github.com/OpenMined/screamingface/commit/2229ff0e031a94688033c108d5538f8c321a9a51))
* reconcile DRACO adapter with merged loop contracts ([cf9d9d6](https://github.com/OpenMined/screamingface/commit/cf9d9d622d7e42df80ec58d9555c5307bf14b3af))
* **url4-cloud:** aggregate DRACO 5-pass verdicts into check outcomes ([d0f5b3a](https://github.com/OpenMined/screamingface/commit/d0f5b3a0f4f366a67c40be48a10a73d4f1235821))
* **url4-cloud:** carry DRACO check invocations through corrective loops ([7a1afb6](https://github.com/OpenMined/screamingface/commit/7a1afb622fae1b9bbf3bcad256037f46ccb7ef43))
* **url4-cloud:** carry every token class into the run totals ([c29d591](https://github.com/OpenMined/screamingface/commit/c29d591ed0c5305e398f08a1b456d0b9fee41ea3))
* **url4-cloud:** enforce LANL refusal identity ([97c56ef](https://github.com/OpenMined/screamingface/commit/97c56efdecbb9ee71474c3964a922fe32d249c7b))
* **url4-cloud:** keep check bookkeeping out of model params ([263e9e3](https://github.com/OpenMined/screamingface/commit/263e9e331ebc34bab91e61afff768267d4826257))
* **url4-cloud:** keep provider refusals visible end-to-end ([6f00cf7](https://github.com/OpenMined/screamingface/commit/6f00cf7d76038ed50c4785797fcad076e640e559))
* **url4-cloud:** keep provider refusals visible end-to-end (OME-825) ([05170eb](https://github.com/OpenMined/screamingface/commit/05170eb2ead276d7392cded7780112108dd289a6))
* **url4-cloud:** keep the LANL protocol label at v1 ([59737df](https://github.com/OpenMined/screamingface/commit/59737df7ee9dd89d56685305d0371d62dce2419d))
* **url4-cloud:** make local mode reach a successful run out of the box ([b698fcf](https://github.com/OpenMined/screamingface/commit/b698fcffd20d3dbe19c17a7b6654e302adeaf6ee))
* **url4-cloud:** make local mode reach a successful run out of the box ([f6964de](https://github.com/OpenMined/screamingface/commit/f6964deeb0f77827957e68a3bcac93e4a4459c22))
* **url4-cloud:** name token exhaustion and unstarve the DRACO check judge ([587c80e](https://github.com/OpenMined/screamingface/commit/587c80e7125a5cecae853b362c14141949dd5056))
* **url4-cloud:** preserve rubric check invocation contracts ([9313586](https://github.com/OpenMined/screamingface/commit/931358632e48756cdd5e8b2f1d3e8616d3140a17))
* **url4-cloud:** raise the local concurrent run ceiling above the Client fan-out ([7cbe4c8](https://github.com/OpenMined/screamingface/commit/7cbe4c8c4ab77e1bcbc05aaba28a359ec46a3dbc))
* **url4-cloud:** raise the local concurrent run ceiling above the Client fan-out ([0cdd068](https://github.com/OpenMined/screamingface/commit/0cdd068c89cac679d5dcceb22cb724d3367d6d90))
* **url4-cloud:** stop counting a cache hit's replayed tokens as consumed ([9fec9d7](https://github.com/OpenMined/screamingface/commit/9fec9d7f7b6677d30a882dc207cf9815c21252d9))

## [1.3.0](https://github.com/OpenMined/screamingface/compare/url4-cloud-v1.2.1...url4-cloud-v1.3.0) (2026-08-13)


### Features

* **url4-cloud:** enforce benchmark result contract ([3121933](https://github.com/OpenMined/screamingface/commit/3121933370f9837ef88e14a6561603d2dfd31c71))
* **url4-cloud:** enforce benchmark result contract ([b9e8eb8](https://github.com/OpenMined/screamingface/commit/b9e8eb8c0f7d006777fe927851068eca4d0e7893))


### Bug Fixes

* **url4-cloud:** complete benchmark result invariants ([529d779](https://github.com/OpenMined/screamingface/commit/529d7790b4ff91c745672fb28147bf7c78d5ef9c))
* **url4-cloud:** dedupe duplicate rubric judgements in HealthBench checks ([e7585cc](https://github.com/OpenMined/screamingface/commit/e7585cc200ff7c0b984e97fde69b3d9d2309445e))
* **url4-cloud:** retain malformed HealthBench evaluation rows as failed Cases ([90bd3f0](https://github.com/OpenMined/screamingface/commit/90bd3f008b18a401dfa8af4a9695352393f9b5fc))


### Refactors

* **url4-cloud:** extract benchmark evaluation capabilities ([17f7643](https://github.com/OpenMined/screamingface/commit/17f7643b99a9cf38615cde381584713414742d59))
* **url4-cloud:** extract benchmark evaluation capabilities ([3c295a3](https://github.com/OpenMined/screamingface/commit/3c295a3c9dc694a22d2ee5be186b462d5ac9cd9b))

## [1.2.1](https://github.com/OpenMined/screamingface/compare/url4-cloud-v1.2.0...url4-cloud-v1.2.1) (2026-08-12)


### Documentation

* additively refresh repo READMEs — product framing + doc links ([c41c3b5](https://github.com/OpenMined/screamingface/commit/c41c3b5813014020b424aab10bd94648a807f361))
* additively refresh repo READMEs — product framing + doc links ([bed4b12](https://github.com/OpenMined/screamingface/commit/bed4b121a4c0569bb31923a258feb0dcbefa3325))

## [1.2.0](https://github.com/OpenMined/screamingface/compare/url4-cloud-v1.1.0...url4-cloud-v1.2.0) (2026-08-10)


### Features

* **url4-cloud:** add engine benchmark foundation ([a888401](https://github.com/OpenMined/screamingface/commit/a888401267d561dd18a3a7402f0870f45a858f36))
* **url4-cloud:** add Engine benchmark foundation ([bff2b4e](https://github.com/OpenMined/screamingface/commit/bff2b4e8298e75239626641a08067dbbc216a716))
* **url4-cloud:** deploy DRACO benchmark protocol ([529f316](https://github.com/OpenMined/screamingface/commit/529f316611b8d515a76bc09af1955694ea8796ab))
* **url4-cloud:** deploy DRACO benchmark protocol ([2b2f264](https://github.com/OpenMined/screamingface/commit/2b2f264a26df8af7cab2272f00b6dc2898f41b43))
* **url4-cloud:** expose only executable models ([9a1ea5a](https://github.com/OpenMined/screamingface/commit/9a1ea5af0608cc0c6e8f62dd631eccc1751ad997))
* **url4-cloud:** expose only executable models ([08ac80d](https://github.com/OpenMined/screamingface/commit/08ac80d9790e677f761b831f3425492e31112a34))
* **url4-cloud:** expose provider connections ([cea8b66](https://github.com/OpenMined/screamingface/commit/cea8b662dd8f5f484c85cca9d2b88ff5244f84e4))
* **url4-cloud:** expose provider connections ([d871689](https://github.com/OpenMined/screamingface/commit/d871689aa772b302338f4e47e15f7e68c9ee0ae8))
* **url4-cloud:** proxy model parameter contracts ([89b6c28](https://github.com/OpenMined/screamingface/commit/89b6c28852684309760d82310b465c4b5f4678a1))
* **url4-cloud:** proxy model parameter contracts ([d9db1e6](https://github.com/OpenMined/screamingface/commit/d9db1e6c68e564f2633d12fc6dfeed6d0d12638c))
* **url4:** per-run cache policy for the aigateway global response cache ([#518](https://github.com/OpenMined/screamingface/issues/518)) ([245e0a4](https://github.com/OpenMined/screamingface/commit/245e0a478d0c4d7635a90cf06a50b5b2ddf37d93))


### Bug Fixes

* **url4-cloud:** bind caller exclusions on a default-on search route ([d7d9af8](https://github.com/OpenMined/screamingface/commit/d7d9af8fa0ebb282f11dc77f2af26c21c8138c29))
* **url4-cloud:** bind Candidate outcomes to one model call ([9e79ed5](https://github.com/OpenMined/screamingface/commit/9e79ed57b17f604679994c569802be9e96826a5e))
* **url4-cloud:** report absent DRACO accuracy axis and correct asset claims ([c45876c](https://github.com/OpenMined/screamingface/commit/c45876cfaca25b1e63fa8ca34eeaf29ef90bb4d0))
* **url4-cloud:** scope declared-world failures to discovery ([08cc9d0](https://github.com/OpenMined/screamingface/commit/08cc9d0ba14473e7af86404a17aa667256524ac3))
* **url4-cloud:** validate every relative route and publish the Candidate binding ([2531b6d](https://github.com/OpenMined/screamingface/commit/2531b6d00d0ce061c399c50d24f4700d78859224))


### Refactors

* **url4-cloud:** clean DRACO module boundaries ([a70321b](https://github.com/OpenMined/screamingface/commit/a70321badb7ad0d167a192e722916ee9b9f22783))
* **url4-cloud:** make the local gateway address a setting ([24775b8](https://github.com/OpenMined/screamingface/commit/24775b8a81628327955b64798bbf6ff6666a077d))

## [1.1.0](https://github.com/OpenMined/screamingface/compare/url4-cloud-v1.0.0...url4-cloud-v1.1.0) (2026-08-05)


### Features

* **url4-cloud:** capture finish_reason and refusal, classify a refused turn ([#506](https://github.com/OpenMined/screamingface/issues/506)) ([b594d6f](https://github.com/OpenMined/screamingface/commit/b594d6fcc11b10c4593d1fbe4d95ab3c7adc4bc1))


### Bug Fixes

* **url4-cloud:** move both Docker build stages to Python 3.13 together ([#481](https://github.com/OpenMined/screamingface/issues/481)) ([0c45a5a](https://github.com/OpenMined/screamingface/commit/0c45a5ae365fd5df20b6d607161d7bcdeb0aed2c))

## [1.0.0](https://github.com/OpenMined/screamingface/compare/url4-cloud-v0.1.0...url4-cloud-v1.0.0) (2026-07-31)


### ⚠ BREAKING CHANGES

* a deployment relying on the Cloudflare Access edge to attach `Cf-Access-Jwt-Assertion` must now send `Authorization: Bearer <token>` instead.

### Features

* adopt the Cloudflare Access identity headers (OME-684) ([#444](https://github.com/OpenMined/screamingface/issues/444)) ([3e363de](https://github.com/OpenMined/screamingface/commit/3e363dee80d094cbe3c57b52fbdc20fdd2b16ac3))
* **url4-cloud:** add ai.url4.error outbound nack frame + bridge emission ([d076ec7](https://github.com/OpenMined/screamingface/commit/d076ec762c6920efdcd10a119aafa5126acac441))
* **url4-cloud:** add url4_cloud_nats CloudEvents bus (OME-516) ([fa2ecf0](https://github.com/OpenMined/screamingface/commit/fa2ecf066d7abda1259f535f9efef3ecf73f2cb9))
* **url4-cloud:** app-served Scalar + AsyncAPI reference pages ([ecc0d73](https://github.com/OpenMined/screamingface/commit/ecc0d73beefb673666acced4eddc226e0421b7be))
* **url4-cloud:** auth capability token + JWT + RFC 9457 Bearer guard (OME-517) ([0ccf78a](https://github.com/OpenMined/screamingface/commit/0ccf78ad29a9941e5be4f7360fa3b78f2293dc48))
* **url4-cloud:** CloudEvents WebSocket bridge with resume + heartbeat (OME-521) ([0909f25](https://github.com/OpenMined/screamingface/commit/0909f25ac65e6d3d7e6ed28e7f8e848b70a336cf))
* **url4-cloud:** declutter REST docs + document Prefer sync/async ([bccb5ee](https://github.com/OpenMined/screamingface/commit/bccb5ee09c038d3052c4307265b896e2d1d894ef))
* **url4-cloud:** dedicated URL4-Capability header, decoupled from Authorization ([79f6e9d](https://github.com/OpenMined/screamingface/commit/79f6e9dc768bf256035efa73ced7fe6920ded7de))
* **url4-cloud:** document REST responses on GET / and DELETE / ([5715c1c](https://github.com/OpenMined/screamingface/commit/5715c1cc094a4f3985b08d38ed39eaffb56252d0))
* **url4-cloud:** embed sync/async/streaming diagrams in the served docs ([ea5c04f](https://github.com/OpenMined/screamingface/commit/ea5c04f8a9a93c5f37e4b6ed8eddf53f12cabca7))
* **url4-cloud:** JobRunner port + k8s/docker adapters (OME-519) ([cf86281](https://github.com/OpenMined/screamingface/commit/cf86281b8a30d02954afcdad969636f45d4dd611))
* **url4-cloud:** k8s deploy + namespace RBAC bootstrap + Helm chart (OME-522) ([abadb9a](https://github.com/OpenMined/screamingface/commit/abadb9ae0dc1ef850209e1a51a40b00e04caf61f))
* **url4-cloud:** OpenAPI 3.1 + AsyncAPI 3.0 + Scalar + ops endpoints (OME-523) ([0d4f132](https://github.com/OpenMined/screamingface/commit/0d4f1321fb2687d6b0498ed8258e4047f02136de))
* **url4-cloud:** render /asyncapi with Scalar, unify the doc viewers ([ad4cc2f](https://github.com/OpenMined/screamingface/commit/ad4cc2f811ac9dac82809aca926109c3c2879b9b))
* **url4-cloud:** REST control plane — /token, GET start (Prefer sync/async), DELETE (OME-518) ([cb75b9c](https://github.com/OpenMined/screamingface/commit/cb75b9c2a3d3bc2225f431820b9f059f0d449da4))
* **url4-cloud:** runner Job entrypoint — execute + publish CloudEvents lifecycle (OME-520) ([94c2492](https://github.com/OpenMined/screamingface/commit/94c24928f95981a4a459a41b6f833e1cb86a53d9))
* **url4-cloud:** scaffold apps/url4-cloud (OME-514) ([11dfb39](https://github.com/OpenMined/screamingface/commit/11dfb39b39a3e76c9a4d6504db8ec6288fa16d2e))
* **url4-cloud:** unify docs into /docs (Scalar REST + AsyncAPI switcher) ([47d3ddd](https://github.com/OpenMined/screamingface/commit/47d3ddd63f7dea45f2c404b217f284f00c9d52b8))
* **url4-cloud:** url4 engine integration — backend/runner/shared split, observer seam, local mode ([#425](https://github.com/OpenMined/screamingface/issues/425)) ([ac888c5](https://github.com/OpenMined/screamingface/commit/ac888c5c5a56fb92b36760675c0cce8fcafc144c))
* **url4-cloud:** url4_cloud_protocol frame models + taxonomy invariants (OME-515) ([18ed7bf](https://github.com/OpenMined/screamingface/commit/18ed7bf18c385fd724afaa41be093e313b62cf96))


### Bug Fixes

* **url4-cloud:** style the AsyncAPI viewer via cssImportPath (shadow DOM) ([5fc2995](https://github.com/OpenMined/screamingface/commit/5fc29950ed6e12421c3464a876a900e100915351))
* **url4-cloud:** use JSON-Schema `examples` array, not singular `example` ([9099e36](https://github.com/OpenMined/screamingface/commit/9099e3635671526811dae0f57428e4e73292d8cd))


### Refactors

* **url4-cloud:** align protocol to CloudEvents 1.0 + OTel standards (OME-526) ([471a595](https://github.com/OpenMined/screamingface/commit/471a595306496fdc8718383a79ac46708ca0e3b0))
* **url4-cloud:** drop ai.url4.execute from the WS inbound surface ([a9314d8](https://github.com/OpenMined/screamingface/commit/a9314d8b8be3986368926fbcb2b5ddb10b1fcb45))
* **url4-cloud:** rename url4_cloud_protocol -&gt; url4_streaming_protocol (OME-527) ([3c40529](https://github.com/OpenMined/screamingface/commit/3c40529c8d75e8fca7c48cfcbea7116b0eca33fc))


### Documentation

* **url4-cloud:** record the AsyncAPI payload-dialect decision (no schemaFormat) ([18a2a58](https://github.com/OpenMined/screamingface/commit/18a2a580a7a1e5545da4b537d26ad847c0e96a1c))
