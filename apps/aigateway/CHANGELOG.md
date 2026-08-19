# Changelog

All notable changes to the ScreamingFace AI Gateway are documented here.
This project follows [Semantic Versioning](https://semver.org/) and uses
release tags of the form `aigateway-v<version>`.

## [1.0.0](https://github.com/OpenMined/screamingface/compare/aigateway-v0.2.1...aigateway-v1.0.0) (2026-08-19)


### ⚠ BREAKING CHANGES

* a deployment relying on the Cloudflare Access edge to attach `Cf-Access-Jwt-Assertion` must now send `Authorization: Bearer <token>` instead.

### Features

* admin console for gateway tenants and API-key credentials (OME-705) ([#451](https://github.com/OpenMined/screamingface/issues/451)) ([14d54f0](https://github.com/OpenMined/screamingface/commit/14d54f0a5eb1a8a272bce9a9d7804ae32783fd98))
* adopt the Cloudflare Access identity headers (OME-684) ([#444](https://github.com/OpenMined/screamingface/issues/444)) ([3e363de](https://github.com/OpenMined/screamingface/commit/3e363dee80d094cbe3c57b52fbdc20fdd2b16ac3))
* **aigateway/chart:** render AIGATEWAY_SECRET_KEY from the auth secret + extraEnv passthrough ([#448](https://github.com/OpenMined/screamingface/issues/448)) ([43bb903](https://github.com/OpenMined/screamingface/commit/43bb90372df22cf3103691d9a6be4d27cef09f78))
* **aigateway:** add actionable API key validation ([#420](https://github.com/OpenMined/screamingface/issues/420)) ([66deae0](https://github.com/OpenMined/screamingface/commit/66deae0a787612c8a320ee3ad98f92109c87633f))
* **aigateway:** add direct OpenAI API-key provider ([#630](https://github.com/OpenMined/screamingface/issues/630)) ([bab02e3](https://github.com/OpenMined/screamingface/commit/bab02e3e8aeea1a798e3f62750c197d59bffbe81))
* **aigateway:** add global exact-request cache ([#507](https://github.com/OpenMined/screamingface/issues/507)) ([4f2a55e](https://github.com/OpenMined/screamingface/commit/4f2a55eacd06b28f8cf9506d37398c0e0fdebf30))
* **aigateway:** add OpenRouter BYOK provider (OME-428) ([#416](https://github.com/OpenMined/screamingface/issues/416)) ([7e38134](https://github.com/OpenMined/screamingface/commit/7e38134359b210b5236e958a4e5f83a974a98f16))
* **aigateway:** add per-provider call usage accounting ([#567](https://github.com/OpenMined/screamingface/issues/567)) ([72b35d7](https://github.com/OpenMined/screamingface/commit/72b35d7c0527bc32ba76e7100a366e126e3a0414))
* **aigateway:** cache OpenRouter native web search ([79f21d6](https://github.com/OpenMined/screamingface/commit/79f21d6067cb54de9a87beefcf2ad0d960aaa3c5))
* **aigateway:** expand HuggingFace + Anthropic model seeds with live-verified ids ([#583](https://github.com/OpenMined/screamingface/issues/583)) ([a0a1cb2](https://github.com/OpenMined/screamingface/commit/a0a1cb2a0262be375623f2a5819e28c963e42252))
* **aigateway:** expand OpenRouter model seed with 58 live-verified slugs ([#581](https://github.com/OpenMined/screamingface/issues/581)) ([59543a4](https://github.com/OpenMined/screamingface/commit/59543a44dabee60f3ecf56650540f1d943a8eb66))
* **aigateway:** expose model, provider, and search contracts ([2bee805](https://github.com/OpenMined/screamingface/commit/2bee8054969f2cb97b5150d7ee32636367b251ef))
* **aigateway:** expose OpenRouter price and privacy routing controls ([#450](https://github.com/OpenMined/screamingface/issues/450)) ([008b209](https://github.com/OpenMined/screamingface/commit/008b209e759b42a0b6c18263189676a0b99e1be8))
* **aigateway:** expose provider discovery ([c6161cf](https://github.com/OpenMined/screamingface/commit/c6161cf1d7852781d8a329acf96967eb66398d22))
* **aigateway:** expose provider parameter contracts ([#443](https://github.com/OpenMined/screamingface/issues/443)) ([4f9db97](https://github.com/OpenMined/screamingface/commit/4f9db97bfbda39cd200d23c28e510944f6b7fb4a))
* **aigateway:** log the concurrency limit applied per provider ([9689fac](https://github.com/OpenMined/screamingface/commit/9689fac4c8de7693f4e35c33ef01595e0402e1d4))
* **aigateway:** make tool-bearing requests cacheable per provider ([b60d997](https://github.com/OpenMined/screamingface/commit/b60d997e6fc00a12649024275e8c9502584db900))
* **aigateway:** make web-search-backed requests cacheable ([74069f1](https://github.com/OpenMined/screamingface/commit/74069f164d7b858752a6a23ea5fb6d81fdee4a57))
* **aigateway:** project provider-neutral web search ([d331575](https://github.com/OpenMined/screamingface/commit/d3315750374e813ef6f07e7ff9147f12c43498e0))
* **aigateway:** register benchmark model seeds ([d8525e0](https://github.com/OpenMined/screamingface/commit/d8525e08ecebbab63dac37a441763961dfe785f1))
* **aigateway:** register the open-weight notebook lineup members ([770257d](https://github.com/OpenMined/screamingface/commit/770257dccbb18fdbff596d903d9f6d3f93047f21))
* **aigateway:** stop forcing the OpenRouter web-search engine ([1d4c93d](https://github.com/OpenMined/screamingface/commit/1d4c93de6d06f0bdb99dc535078c84328f26c3d5))
* **models:** register the HealthBench judge route openrouter/openai/gpt-5.4 ([3021a73](https://github.com/OpenMined/screamingface/commit/3021a7372ee50ab74e147b168ed61a02462ef194))
* **screamingface-engine:** rename apps/url4-cloud to apps/screamingface-engine ([3246d96](https://github.com/OpenMined/screamingface/commit/3246d96d05673e0707cf938cae65de2e696154c8))
* **url4-cloud:** add HealthBench challenge protocols ([3c0bef1](https://github.com/OpenMined/screamingface/commit/3c0bef18422b8bb4db7aaf2acff5b8facfcff193))
* **url4-cloud:** derive the web-search mechanism from the provider ([8059f7c](https://github.com/OpenMined/screamingface/commit/8059f7c321c10521f89a47ebc5354065cc105de7))


### Bug Fixes

* **aigateway:** close implicit web-search bypass ([2146fa0](https://github.com/OpenMined/screamingface/commit/2146fa0dd8aac9e50d1afd7733e6ec9addd180a5))
* **aigateway:** configure app logging so INFO records actually emit ([e0766e2](https://github.com/OpenMined/screamingface/commit/e0766e2299704a35bef67619caad6ab81c4f08cb))
* **aigateway:** derive the Codex finish_reason instead of fabricating "stop" ([#501](https://github.com/OpenMined/screamingface/issues/501)) ([0571f44](https://github.com/OpenMined/screamingface/commit/0571f440df4cc341fe1f789a0b85d8066a9b1d12))
* **aigateway:** enable OpenRouter in prod chart values ([#533](https://github.com/OpenMined/screamingface/issues/533)) ([7ad2ed3](https://github.com/OpenMined/screamingface/commit/7ad2ed35a3f0efa8087d8be5989c5a258adfe045))
* **aigateway:** preserve web search cache bypass ([e2c5eae](https://github.com/OpenMined/screamingface/commit/e2c5eaebe23f8273cb33bf0cabd21e3d900b0f88))
* **aigateway:** refuse :online ahead of the cache read ([9f0e8e8](https://github.com/OpenMined/screamingface/commit/9f0e8e8411c367caf2ec97f6aa8a7db0a151549f))
* **aigateway:** roll Pods when the ConfigMap changes ([9f1d525](https://github.com/OpenMined/screamingface/commit/9f1d5256aed79f0a018e01fe408b37c59ad24d86))
* **aigateway:** roll Pods when the ConfigMap changes ([cc1b0ac](https://github.com/OpenMined/screamingface/commit/cc1b0acea2a48c2a394f7cf9cd45183b2d2ef15b))
* **aigateway:** sanitize streaming provider errors ([#424](https://github.com/OpenMined/screamingface/issues/424)) ([c55c56c](https://github.com/OpenMined/screamingface/commit/c55c56cf33c572b3b1549a6553cf314ae8ffc335))
* **aigateway:** strip Datadog callback params, upgrade deps, unpin PyJWT ([#478](https://github.com/OpenMined/screamingface/issues/478)) ([30868c7](https://github.com/OpenMined/screamingface/commit/30868c7f2a78565420512263b2910c8c9aaaa570))
* **py-screamingface:** raise local stack openrouter gateway concurrency to 32 ([25851fd](https://github.com/OpenMined/screamingface/commit/25851fdfa7a2ca50922b81a4dfc36da2febf67d9))
* **repo:** align aigateway and scoreboard Dockerfiles on Python 3.13 ([#502](https://github.com/OpenMined/screamingface/issues/502)) ([1513af0](https://github.com/OpenMined/screamingface/commit/1513af0c756defa1332e2abc4594612b2583abf7))


### Documentation

* additively refresh repo READMEs — product framing + doc links ([c41c3b5](https://github.com/OpenMined/screamingface/commit/c41c3b5813014020b424aab10bd94648a807f361))
* additively refresh repo READMEs — product framing + doc links ([bed4b12](https://github.com/OpenMined/screamingface/commit/bed4b121a4c0569bb31923a258feb0dcbefa3325))
* **aigateway:** anonymize deployment examples ([#525](https://github.com/OpenMined/screamingface/issues/525)) ([6abd6af](https://github.com/OpenMined/screamingface/commit/6abd6af70f69bb425b17058fe05548709476c778))
* **screamingface-engine:** update agent config, diagrams and stale paths ([1d2c047](https://github.com/OpenMined/screamingface/commit/1d2c047b2c522dee3df2dc9ea920d36f05584eea))

## [0.2.0](https://github.com/OpenMined/screamingface/compare/aigateway-v0.1.0...aigateway-v0.2.0) (2026-05-11)


### Features

* **SF-138:** scaffold apps/aigateway/ standalone LiteLLM-compatible service ([#122](https://github.com/OpenMined/screamingface/issues/122)) ([3a66bf9](https://github.com/OpenMined/screamingface/commit/3a66bf9269f20848b7bc3fadca5809527b7bb901))


### Bug Fixes

* **ci:** correct release-please tag separator + enable workflow chain ([#154](https://github.com/OpenMined/screamingface/issues/154)) ([c51abc3](https://github.com/OpenMined/screamingface/commit/c51abc3ecae2028d9a333bf6b5881f8d8b3dc7d8))

## [Unreleased]

## [0.1.0]

- Initial release.
