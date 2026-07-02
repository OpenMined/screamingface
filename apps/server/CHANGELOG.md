# Changelog

All notable changes to the ScreamingFace Server are documented here.
This project follows [Semantic Versioning](https://semver.org/) and uses
release tags of the form `server-v<version>`.

## [0.3.0](https://github.com/OpenMined/screamingface/compare/server-v0.2.1...server-v0.3.0) (2026-07-02)


### Features

* **aigateway:** add Hugging Face provider (SF-345) ([#356](https://github.com/OpenMined/screamingface/issues/356)) ([c556e6c](https://github.com/OpenMined/screamingface/commit/c556e6ce29543f4611e64e1cc239020315070592))


### Bug Fixes

* start server container with sf run (SF-326) ([#345](https://github.com/OpenMined/screamingface/issues/345)) ([312ec8d](https://github.com/OpenMined/screamingface/commit/312ec8d11efa2e6755a4ee25d3b2533118794424))

## [0.2.1](https://github.com/OpenMined/screamingface/compare/server-v0.2.0...server-v0.2.1) (2026-06-24)


### Bug Fixes

* **server:** enable Tortoise global fallback so DB reads work under uvicorn ([#223](https://github.com/OpenMined/screamingface/issues/223)) ([592d59a](https://github.com/OpenMined/screamingface/commit/592d59ab9f636081d6e6cb1462f0a9a51c5c56f4))
* **server:** exclude no-auth runners from /backends/status credential walk (SF-246) ([#262](https://github.com/OpenMined/screamingface/issues/262)) ([ff4320b](https://github.com/OpenMined/screamingface/commit/ff4320b2b2fcc6edcaf7b7b9381a3108bad6fdfe))
* **server:** resolve $prompt url4 in-process to avoid /ensemble 401 self-loop ([#224](https://github.com/OpenMined/screamingface/issues/224)) ([b58fb08](https://github.com/OpenMined/screamingface/commit/b58fb08c0fae4a25ab027a8bbf73513d44172ff1))
* **url4:** JSON-escape $item/$var substitutions inside json_blob intents (SF-235) ([#242](https://github.com/OpenMined/screamingface/issues/242)) ([7b65d46](https://github.com/OpenMined/screamingface/commit/7b65d469f8deef9a6eca3744dcce80cae5d4ad43))
* **url4:** surface on_error=collect failures via X-SF-Collected-Errors header + span attr ([#243](https://github.com/OpenMined/screamingface/issues/243)) ([5b7c9dc](https://github.com/OpenMined/screamingface/commit/5b7c9dc708837c826a1feb766c59c860cd602a59))

## [0.2.0](https://github.com/OpenMined/screamingface/compare/server-v0.1.0...server-v0.2.0) (2026-05-18)


### Features

* add --session-id flag to sf run CLI ([8488ead](https://github.com/OpenMined/screamingface/commit/8488ead9de24f7cade6b3ad84e25f9d162ca0f53))
* add test coverage reporting to CI ([5424745](https://github.com/OpenMined/screamingface/commit/5424745be343cea27a2a2a262763b7c6097a1215))
* **backends:** direct API access for all 3 providers + 74 YAML e2e tests ([6ff26f4](https://github.com/OpenMined/screamingface/commit/6ff26f4a09925ebc33658f6e5e2181a11d7208b0))
* claude-frontend typed models, cached url4 context injection, and request tracing ([fbdf8fe](https://github.com/OpenMined/screamingface/commit/fbdf8fe93809f3200c1f31b1854f9ca547252cdd))
* e2e testing pipeline, OTel trace coverage, configurable context embedding ([b2c46f5](https://github.com/OpenMined/screamingface/commit/b2c46f58d0d1b75036c4e025b633b34364796b9c))
* e2e testing pipeline, OTel tracing, configurable embedding, session edit ([7587f93](https://github.com/OpenMined/screamingface/commit/7587f93ed480f04c1648f82ba6bcc5a4927d9a72))
* FrontendRegistry, mitmproxy_intercept routing, desktop plugin settings UI ([8ff63ec](https://github.com/OpenMined/screamingface/commit/8ff63eceff8139ff68597073e923510bd0367a86))
* per-session proxy, url4 interpreter, /ensemble + /claude endpoints ([91e7ff2](https://github.com/OpenMined/screamingface/commit/91e7ff2c499bac8bfaeacae929d5ec4fd329777e))
* scaffold ScreamingFace server with plugin-based architecture ([0de4f4c](https://github.com/OpenMined/screamingface/commit/0de4f4c96710a419a58ffc4cbd2bd89b5b9627cb))
* **SF-105:** ollama_backend_api direct API backend plugin ([#94](https://github.com/OpenMined/screamingface/issues/94)) ([5cdc3fc](https://github.com/OpenMined/screamingface/commit/5cdc3fcf1b398ca5491940145a3b87da74580e05))
* **SF-157:** python_runner subprocess runner (DEMO-010) ([#165](https://github.com/OpenMined/screamingface/issues/165)) ([b08253e](https://github.com/OpenMined/screamingface/commit/b08253e51daa5bf6182ba3b5e4b29362657e9d48))
* **SF-160:** eval_runs plugin — benchmark run persistence (DEMO-014) ([#164](https://github.com/OpenMined/screamingface/issues/164)) ([58fef87](https://github.com/OpenMined/screamingface/commit/58fef8713b6d24d4c31fb9930413f9efcb9a5d20))
* **SF-197:** state plugin — generic stateful storage core (DEMO-014.0) ([#163](https://github.com/OpenMined/screamingface/issues/163)) ([491afd5](https://github.com/OpenMined/screamingface/commit/491afd587377662aa8c03c259f2fdaf4804a65ba))
* **SF-78:** llm-base plugin + claude-backend-api plugin scaffold ([0af5af4](https://github.com/OpenMined/screamingface/commit/0af5af48feeb387cae1fb60d57fe9534f4651f69))
* **SF-79:** Ensemble fan-out-reduce + claude-backend-api defaults & desktop fixes ([#60](https://github.com/OpenMined/screamingface/issues/60)) ([b604ef0](https://github.com/OpenMined/screamingface/commit/b604ef064287c1461f61bcf564d33e8642be9764))
* **SF-79:** Stage A — url4 parser extension for /backend()!&lt;intent&gt; syntax ([8599c6e](https://github.com/OpenMined/screamingface/commit/8599c6e0e9afd7aae2f7da7cd5f12db8750f54b6))
* **SF-79:** Stage B — dispatch Url4BackendCall through plugin registry ([35720ad](https://github.com/OpenMined/screamingface/commit/35720add16d07ed9fa87ed77a7d273c16086359f))
* **SF-79:** Stage C — EnsembleInterpreter fan-out-reduce ([d3b34a6](https://github.com/OpenMined/screamingface/commit/d3b34a63dc68985cdf529c61e0c4a77d1c557670))
* **SF-80:** codex-backend-api plugin — OpenAI Responses API via Codex OAuth ([#61](https://github.com/OpenMined/screamingface/issues/61)) ([332931f](https://github.com/OpenMined/screamingface/commit/332931f4767201181db164f418f6ea8be5dca44f))
* **SF-85:** codex-frontend plugin — session proxy for Codex CLI ([#62](https://github.com/OpenMined/screamingface/issues/62)) ([505d95c](https://github.com/OpenMined/screamingface/commit/505d95c25dc1f9f4621449d58e703fd399becba0))
* **SF-86:** gemini-frontend + gemini-backend-api plugins ([#63](https://github.com/OpenMined/screamingface/issues/63)) ([1e816ef](https://github.com/OpenMined/screamingface/commit/1e816efdc868f82148946c9a3aba370d850b22fe))
* **SF-87:** product tags on all plugins + grouped Settings UI ([#72](https://github.com/OpenMined/screamingface/issues/72)) ([872348a](https://github.com/OpenMined/screamingface/commit/872348a27817b3eb6dd5d95237764c2d8228a77c))
* **SF-88:** named + weighted source labels in backend calls ([03f5c07](https://github.com/OpenMined/screamingface/commit/03f5c074123b99e9978263bc406d4d5a207e8cd0))
* **SF-89:** context packing in backend calls — /path('context')!intent ([09d8534](https://github.com/OpenMined/screamingface/commit/09d85341e1850b3743f28bac8f9e47eab095b804))
* **SF-90:** variable references in reducer intent ($name substitution) ([c3cec58](https://github.com/OpenMined/screamingface/commit/c3cec58f6c5d9077c394a41005742c1565650a41))
* **SF-91:** collection iteration — source*(body)!intent with $item binding ([6e78d1a](https://github.com/OpenMined/screamingface/commit/6e78d1a85298cece1c857b19d89625f12b96bf69))
* **SF-92:** source expansion — *source expands collection into items ([5bf56af](https://github.com/OpenMined/screamingface/commit/5bf56af8e7a36a08c09bb4e4db4db906b01f73c4))
* **SF-93:** intent broadcasting — !* operator applies intent per-source ([d343271](https://github.com/OpenMined/screamingface/commit/d3432715b0690a0c195d3c4df565e8b0390cf71f))
* **SF-95:** ollama_frontend transparent proxy plugin ([#89](https://github.com/OpenMined/screamingface/issues/89)) ([1e66e19](https://github.com/OpenMined/screamingface/commit/1e66e19e2079168c1abdca164b732aac390027a0))
* support balanced-paren URLs in url4 grammar ([78fbcae](https://github.com/OpenMined/screamingface/commit/78fbcaebd62e05c39610c4270e96d326fa3325a6))
* TatSu url4 parser, mitmproxy_intercept plugin, desktop UI fixes ([b97eb8e](https://github.com/OpenMined/screamingface/commit/b97eb8ebfa966a1d6cbd3d28a20c9f66400696c7))
* url4 backend integration — intent dispatch, claude-backend prof… ([3833f9b](https://github.com/OpenMined/screamingface/commit/3833f9b60dc6eca6f83737562d4adf7b88c6e36b))
* url4 backend integration — intent dispatch, claude-backend profiles, url4-specs plugin ([9d65ceb](https://github.com/OpenMined/screamingface/commit/9d65cebde36f817a049cd4969d2f0354a9156658))


### Bug Fixes

* add CLI preflight check to claude-frontend ([#65](https://github.com/OpenMined/screamingface/issues/65)) ([c065a50](https://github.com/OpenMined/screamingface/commit/c065a5022b9705ed1cc433fa3c8578830366d841))
* clarify backend_url description + add default_backend_path per frontend ([#75](https://github.com/OpenMined/screamingface/issues/75)) ([b031d63](https://github.com/OpenMined/screamingface/commit/b031d63fb759e0925a90ccb1c8672691eec9ede1))
* Format shellenv.py to pass ruff format check ([a5806f1](https://github.com/OpenMined/screamingface/commit/a5806f1bc85c126d1cc76891d1f77d033aad79db))
* Make 11 CI tests pass on ubuntu-latest ([506eb5c](https://github.com/OpenMined/screamingface/commit/506eb5ce28cfa05d7dd2b75a859d928dde4b0ae1))
* only validate newly added plugins, allow removals ([#67](https://github.com/OpenMined/screamingface/issues/67)) ([9aca6d5](https://github.com/OpenMined/screamingface/commit/9aca6d55f824376db609d260ab07f93ce2c35588))
* Patch all existing shell RC files instead of guessing one ([15dea39](https://github.com/OpenMined/screamingface/commit/15dea393bd681c6602fbc5b3c5ff3fe0cadb6d3f))
* pyright errors in e2e conftest generator fixture return types ([32e61d2](https://github.com/OpenMined/screamingface/commit/32e61d222c4358bcef08342312f8c65e2b632baf))
* remove Claude CLI preflight check from claude-frontend proxy ([a481929](https://github.com/OpenMined/screamingface/commit/a481929b31ed20ca25261ef2b87d8c316fac05a0))
* resolve pyright type error in test_claude_backend (ClaudeProfile) ([3040c83](https://github.com/OpenMined/screamingface/commit/3040c83729fa9e36cd70d0a00abe44e58cb00d96))
* resolve pyright type errors in tracing plugin and test_url4 ([fe3401c](https://github.com/OpenMined/screamingface/commit/fe3401cbf4fc82fbfab29e576554d4bbdcd37588))
* resolve ruff E501 line-too-long lint errors ([e6c9888](https://github.com/OpenMined/screamingface/commit/e6c9888ef97b649a22a176551127c98da40a68ba))
* resolve ruff lint failures (import sort, line length, unused import) ([be02986](https://github.com/OpenMined/screamingface/commit/be029865b904df23b328ff52f7ea224f645bd4a1))
* resolve ruff UP038 and fix pyright hook directory ([f54177b](https://github.com/OpenMined/screamingface/commit/f54177b1a249ec16a838e49c573adb13cbd6845c))
* ruff format 3 more files, run pre-commit from apps/server/ ([6168e22](https://github.com/OpenMined/screamingface/commit/6168e22e589b272857d2adf0675efce967529748))
* ruff format for codex-frontend and codex-backend-api files ([#64](https://github.com/OpenMined/screamingface/issues/64)) ([e99ed50](https://github.com/OpenMined/screamingface/commit/e99ed507b09d97a8aa45e4a41f54bcb8c2f9bdd3))
* ruff format test_url4.py and add uv to pre-commit CI ([152c188](https://github.com/OpenMined/screamingface/commit/152c188b7c8affa093b0038f719420432679b4d4))
* ruff lint and format issues in proxy, plugin, interpreter ([74401b5](https://github.com/OpenMined/screamingface/commit/74401b59a4ce498ba9b7bde330a5abe21852d15c))
* **server:** update claude-backend-api defaults and config ([fe62adb](https://github.com/OpenMined/screamingface/commit/fe62adb4dcda3318ad243ac750274a9d5a121575))
* settings endpoint test to match sf.json re-read behavior ([976c6bf](https://github.com/OpenMined/screamingface/commit/976c6bf58402c60d52de61262c5274f6622233b2))
* **SF-114:** Gemini falls back through model chain on 429 QUOTA_EXHAUSTED ([#103](https://github.com/OpenMined/screamingface/issues/103)) ([bcb51fc](https://github.com/OpenMined/screamingface/commit/bcb51fc8b34d223981899a1464ebab0488d33ce1))
* **SF-115:** reject CLI-only fields explicitly at backend-api /run ([#104](https://github.com/OpenMined/screamingface/issues/104)) ([0aa19f8](https://github.com/OpenMined/screamingface/commit/0aa19f89753c6786b9a36998ed1efb96c4843b99))
* **SF-116:** cap cumulative 429 retry-wait in GeminiBackend ([#105](https://github.com/OpenMined/screamingface/issues/105)) ([47831bc](https://github.com/OpenMined/screamingface/commit/47831bc5a0097cce9e8d254ca34ce3a030d312bc))
* **SF-137:** move ollama-frontend listen_port from 9103 to 9104 ([#121](https://github.com/OpenMined/screamingface/issues/121)) ([59b945c](https://github.com/OpenMined/screamingface/commit/59b945c46ea7d04958205569714f9904ebd89ea2))
* validate plugin preflight before saving config ([#66](https://github.com/OpenMined/screamingface/issues/66)) ([4d7ad4c](https://github.com/OpenMined/screamingface/commit/4d7ad4c666271d32409e9f757aef2e28a9e94314))


### Refactors

* co-locate plugin tests inside src/ packages ([5b311f1](https://github.com/OpenMined/screamingface/commit/5b311f1b079cc426e125903f10478a3691281303))
* rename claude-cli to claude-backend, simplify plugin settings ([1204738](https://github.com/OpenMined/screamingface/commit/12047382086c6e18c1bd61422b6ff19186de9451))
* Rename plugins to consistent claude- prefix convention ([b123360](https://github.com/OpenMined/screamingface/commit/b123360f2e4cfbd342a1b02fab818dfa11d8fdcb))
* **SF-107:** decompose claude_frontend proxy_messages into focused helpers ([#98](https://github.com/OpenMined/screamingface/issues/98)) ([2de1b85](https://github.com/OpenMined/screamingface/commit/2de1b85372f99b56a9c40287c1bfed33439b343f))
* **SF-110:** extract OAuthStrategy base + adapter helpers to llm_base ([#97](https://github.com/OpenMined/screamingface/issues/97)) ([d720bd2](https://github.com/OpenMined/screamingface/commit/d720bd22cfe7052c8353edb608fd759458ea73c6))
* **SF-111:** decouple backend_api plugins from claude_backend, dedupe intercept helpers ([#95](https://github.com/OpenMined/screamingface/issues/95)) ([90240cb](https://github.com/OpenMined/screamingface/commit/90240cb5b48d8bba8eb932d6e697777e365f25b6))
* **SF-112:** decouple frontends from data_store.routes; assert plugins-registry invariant ([#101](https://github.com/OpenMined/screamingface/issues/101)) ([cf86e6d](https://github.com/OpenMined/screamingface/commit/cf86e6d131c6648340b4062cacb4f72c31bb33a9))
* **SF-119:** split create_app — admin endpoints + bootstrap helpers ([#108](https://github.com/OpenMined/screamingface/issues/108)) ([6ad5e27](https://github.com/OpenMined/screamingface/commit/6ad5e27dec80033774d39c05f27decfffa81305a))
* **SF-120:** move data_store BlobStore singleton to app.state ([#109](https://github.com/OpenMined/screamingface/issues/109)) ([c52437f](https://github.com/OpenMined/screamingface/commit/c52437f3f301cde6480c3a375eb71019090b7bea))
* **SF-121:** split url4.py — AST / grammar / resolve modules ([#110](https://github.com/OpenMined/screamingface/issues/110)) ([5508c57](https://github.com/OpenMined/screamingface/commit/5508c57da4677a1d8505ea8df8d57b3252208941))
* **SF-123:** wire SF-110 adapter helpers into existing adapters ([#111](https://github.com/OpenMined/screamingface/issues/111)) ([767ceac](https://github.com/OpenMined/screamingface/commit/767ceac5d907e2d88e7ee221925e5f1f9506bfb0))
* **SF-124:** consolidate adapter tool-result + parts-to-text helpers ([#112](https://github.com/OpenMined/screamingface/issues/112)) ([ab32ae5](https://github.com/OpenMined/screamingface/commit/ab32ae54388f2e729706eba4161195a0269fc296))
* **SF-128:** migrate codex/gemini/ollama frontends onto ProxyTracer ([#113](https://github.com/OpenMined/screamingface/issues/113)) ([736dc0f](https://github.com/OpenMined/screamingface/commit/736dc0f575f5e3876e812fae992e006911d947a0))
* **SF-129:** finish claude_frontend ProxyTracer migration ([#114](https://github.com/OpenMined/screamingface/issues/114)) ([ed2b8ec](https://github.com/OpenMined/screamingface/commit/ed2b8ec0e9b8a255aa7314e8641c73e43b92421d))
* **SF-131:** decompose claude_frontend/proxy.py — observability + SSE parser ([#115](https://github.com/OpenMined/screamingface/issues/115)) ([c021333](https://github.com/OpenMined/screamingface/commit/c0213336188bab6252b1c5454e4ead9af8cbfbd2))
* **SF-132:** decompose ollama_frontend/proxy.py — observability + NDJSON parser ([#116](https://github.com/OpenMined/screamingface/issues/116)) ([3e68f6f](https://github.com/OpenMined/screamingface/commit/3e68f6f4c2d143662e98b388a810b4b31ba15442))
* **SF-133:** extract route-telemetry helpers from routes_shared.py ([#117](https://github.com/OpenMined/screamingface/issues/117)) ([eb97725](https://github.com/OpenMined/screamingface/commit/eb97725f3fb06070888c7df181e1ec7d21beaafb))
* **SF-134:** decompose mitmproxy_intercept/plugin.py into focused modules ([#118](https://github.com/OpenMined/screamingface/issues/118)) ([cb601bb](https://github.com/OpenMined/screamingface/commit/cb601bbc91daeeb77b8c2e408a779782e92e5cfc))
* **SF-136:** extract BackendApiPluginBase from 4 *_backend_api plugins ([#120](https://github.com/OpenMined/screamingface/issues/120)) ([fc9ffd0](https://github.com/OpenMined/screamingface/commit/fc9ffd0611889d1c0afdfeaea2825e3068caf0ed))
* update claude_env_intercept to read base_url from FrontendRegistry ([623a037](https://github.com/OpenMined/screamingface/commit/623a037fe5382a2a2dc62c53357ce93d2f58696e))


### Documentation

* add local Electron app config as Approach 3 in config-refs ([fda9231](https://github.com/OpenMined/screamingface/commit/fda923151f7cd39d3bc8a5c77d7926322a87ef03))
* add README for ScreamingFace plugin architecture ([3d588c9](https://github.com/OpenMined/screamingface/commit/3d588c96a6b625ae259e0474b2457056350b9a89))

## [Unreleased]

## [0.1.0]

- Initial release.
