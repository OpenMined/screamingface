# Changelog

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
