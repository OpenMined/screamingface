# Changelog

All notable changes to the ScreamingFace AI Gateway are documented here.
This project follows [Semantic Versioning](https://semver.org/) and uses
release tags of the form `aigateway-v<version>`.

## [1.0.0](https://github.com/OpenMined/screamingface/compare/aigateway-v0.2.0...aigateway-v1.0.0) (2026-08-05)


### ⚠ BREAKING CHANGES

* a deployment relying on the Cloudflare Access edge to attach `Cf-Access-Jwt-Assertion` must now send `Authorization: Bearer <token>` instead.

### Features

* admin console for gateway tenants and API-key credentials (OME-705) ([#451](https://github.com/OpenMined/screamingface/issues/451)) ([14d54f0](https://github.com/OpenMined/screamingface/commit/14d54f0a5eb1a8a272bce9a9d7804ae32783fd98))
* adopt the Cloudflare Access identity headers (OME-684) ([#444](https://github.com/OpenMined/screamingface/issues/444)) ([3e363de](https://github.com/OpenMined/screamingface/commit/3e363dee80d094cbe3c57b52fbdc20fdd2b16ac3))
* **aigateway/chart:** render AIGATEWAY_SECRET_KEY from the auth secret + extraEnv passthrough ([#448](https://github.com/OpenMined/screamingface/issues/448)) ([43bb903](https://github.com/OpenMined/screamingface/commit/43bb90372df22cf3103691d9a6be4d27cef09f78))
* **aigateway:** add actionable API key validation ([#420](https://github.com/OpenMined/screamingface/issues/420)) ([66deae0](https://github.com/OpenMined/screamingface/commit/66deae0a787612c8a320ee3ad98f92109c87633f))
* **aigateway:** add Hugging Face provider (SF-345) ([#356](https://github.com/OpenMined/screamingface/issues/356)) ([c556e6c](https://github.com/OpenMined/screamingface/commit/c556e6ce29543f4611e64e1cc239020315070592))
* **aigateway:** add OpenRouter BYOK provider (OME-428) ([#416](https://github.com/OpenMined/screamingface/issues/416)) ([7e38134](https://github.com/OpenMined/screamingface/commit/7e38134359b210b5236e958a4e5f83a974a98f16))
* **aigateway:** expose OpenRouter price and privacy routing controls ([#450](https://github.com/OpenMined/screamingface/issues/450)) ([008b209](https://github.com/OpenMined/screamingface/commit/008b209e759b42a0b6c18263189676a0b99e1be8))
* **aigateway:** expose provider parameter contracts ([#443](https://github.com/OpenMined/screamingface/issues/443)) ([4f9db97](https://github.com/OpenMined/screamingface/commit/4f9db97bfbda39cd200d23c28e510944f6b7fb4a))


### Bug Fixes

* **aigateway:** derive the Codex finish_reason instead of fabricating "stop" ([#501](https://github.com/OpenMined/screamingface/issues/501)) ([0571f44](https://github.com/OpenMined/screamingface/commit/0571f440df4cc341fe1f789a0b85d8066a9b1d12))
* **aigateway:** sanitize streaming provider errors ([#424](https://github.com/OpenMined/screamingface/issues/424)) ([c55c56c](https://github.com/OpenMined/screamingface/commit/c55c56cf33c572b3b1549a6553cf314ae8ffc335))
* **aigateway:** strip Datadog callback params, upgrade deps, unpin PyJWT ([#478](https://github.com/OpenMined/screamingface/issues/478)) ([30868c7](https://github.com/OpenMined/screamingface/commit/30868c7f2a78565420512263b2910c8c9aaaa570))
* **repo:** align aigateway and scoreboard Dockerfiles on Python 3.13 ([#502](https://github.com/OpenMined/screamingface/issues/502)) ([1513af0](https://github.com/OpenMined/screamingface/commit/1513af0c756defa1332e2abc4594612b2583abf7))


### Refactors

* **SF-348:** repo re-foundation — remove deprecated desktop/server + stale surface ([#371](https://github.com/OpenMined/screamingface/issues/371)) ([9a9cf82](https://github.com/OpenMined/screamingface/commit/9a9cf82dfde1085ef9e143571f8e8c547af67976))

## [0.2.0](https://github.com/OpenMined/screamingface/compare/aigateway-v0.1.0...aigateway-v0.2.0) (2026-05-11)


### Features

* **SF-138:** scaffold apps/aigateway/ standalone LiteLLM-compatible service ([#122](https://github.com/OpenMined/screamingface/issues/122)) ([3a66bf9](https://github.com/OpenMined/screamingface/commit/3a66bf9269f20848b7bc3fadca5809527b7bb901))


### Bug Fixes

* **ci:** correct release-please tag separator + enable workflow chain ([#154](https://github.com/OpenMined/screamingface/issues/154)) ([c51abc3](https://github.com/OpenMined/screamingface/commit/c51abc3ecae2028d9a333bf6b5881f8d8b3dc7d8))

## [Unreleased]

## [0.1.0]

- Initial release.
