# Changelog

## [0.2.0](https://github.com/OpenMined/screamingface/compare/scoreboard-v0.1.1...scoreboard-v0.2.0) (2026-08-19)


### Features

* **benchmarks:** flatten public identities ([dfd8eb9](https://github.com/OpenMined/screamingface/commit/dfd8eb97b431d9ae02cf51edc334bd357c0b9b10))
* replace binary accuracy submissions with benchmark-native Leaderboard scores ([8bb79e1](https://github.com/OpenMined/screamingface/commit/8bb79e13d2002236e95646e788040f5f2b76de94))
* **scoreboard:** accept, store and rank benchmark-native scores ([44d5496](https://github.com/OpenMined/screamingface/commit/44d54967c38bde87faee817458d0d4958b2c8654))
* **scoreboard:** adopt the leaderboard-mvp masthead nav and landing copy ([#609](https://github.com/OpenMined/screamingface/issues/609)) ([0b191c7](https://github.com/OpenMined/screamingface/commit/0b191c755cc29e71194fde28475bbc29dbd47557))
* **scoreboard:** authenticate leaderboard submissions via mesh identity header ([#466](https://github.com/OpenMined/screamingface/issues/466)) ([a062e5e](https://github.com/OpenMined/screamingface/commit/a062e5e8733a12a4e3f9c889d7a6dd728d669399))
* **scoreboard:** compute open-vs-closed frontier statistics ([#519](https://github.com/OpenMined/screamingface/issues/519)) ([62a0735](https://github.com/OpenMined/screamingface/commit/62a0735d5555a63bc978bfe0b854bb1bb759aecf))
* **scoreboard:** default new submissions to verified as a placeholder ([#588](https://github.com/OpenMined/screamingface/issues/588)) ([f9bd72f](https://github.com/OpenMined/screamingface/commit/f9bd72fef7477cc484ad2ece7c737bcd6a042c16))
* **scoreboard:** fill the leaderboard board with ranked rows and core columns ([#569](https://github.com/OpenMined/screamingface/issues/569)) ([2a20c15](https://github.com/OpenMined/screamingface/commit/2a20c1540c925f53c280569c9eb8eaaade301b34))
* **scoreboard:** publish only the local part of a submitter's email ([#602](https://github.com/OpenMined/screamingface/issues/602)) ([7c036d9](https://github.com/OpenMined/screamingface/commit/7c036d90e8f885237f4673e0fa85d9340a503f7f))
* **scoreboard:** rebuild leaderboard portal shell on SFDS v2 ([#558](https://github.com/OpenMined/screamingface/issues/558)) ([f43bd4a](https://github.com/OpenMined/screamingface/commit/f43bd4a8dc453c214838d28f5572fa759cc536ea))
* **scoreboard:** register DRACO, IFEval and HealthBench with revision identity ([#611](https://github.com/OpenMined/screamingface/issues/611)) ([e431b71](https://github.com/OpenMined/screamingface/commit/e431b71544ee89a65d3524ce141bfc3dacecad0f))
* **scoreboard:** rename the verification field to verified_by_screamingface ([#624](https://github.com/OpenMined/screamingface/issues/624)) ([d32ef0a](https://github.com/OpenMined/screamingface/commit/d32ef0ac81163d2c0942658095439509970ad61f))
* **scoreboard:** render benchmark explainer infographics on the portal ([fda71ce](https://github.com/OpenMined/screamingface/commit/fda71ced5b8e52b7a9525821680a855519cc6b18))
* **scoreboard:** render benchmark-native scores in the portal ([4259b7c](https://github.com/OpenMined/screamingface/commit/4259b7c198e6d5d81f95c41b671f9fb20225f07b))
* **scoreboard:** wire SCOREBOARD_SUBMISSION_API_KEY as a secret-backed env var ([#403](https://github.com/OpenMined/screamingface/issues/403)) ([d2b77d6](https://github.com/OpenMined/screamingface/commit/d2b77d6aa0a5c990ded24801cdefc6d0518cf977))
* **screamingface-engine:** rename apps/url4-cloud to apps/screamingface-engine ([3246d96](https://github.com/OpenMined/screamingface/commit/3246d96d05673e0707cf938cae65de2e696154c8))


### Bug Fixes

* address Filip's PR [#626](https://github.com/OpenMined/screamingface/issues/626) review (both passes on bf7f12f) ([99ab98c](https://github.com/OpenMined/screamingface/commit/99ab98c3b76b509170cb9b13ef0b99fb211949a4))
* **repo:** align aigateway and scoreboard Dockerfiles on Python 3.13 ([#502](https://github.com/OpenMined/screamingface/issues/502)) ([1513af0](https://github.com/OpenMined/screamingface/commit/1513af0c756defa1332e2abc4594612b2583abf7))
* **scoreboard:** call results reproducible, not rerunnable, on the masthead ([ae15b9c](https://github.com/OpenMined/screamingface/commit/ae15b9c56d52d8816760f894741551f035b8108e))
* **scoreboard:** give the frontier and openness test helpers a benchmark revision ([#617](https://github.com/OpenMined/screamingface/issues/617)) ([f4684a8](https://github.com/OpenMined/screamingface/commit/f4684a833645480b443c33f1b623074a0f09baa8))
* **screamingface:** point the runtime build hook at the renamed Engine ([b184878](https://github.com/OpenMined/screamingface/commit/b184878f924c74953d1984458cda1c648dd1879e))


### Documentation

* additively refresh repo READMEs — product framing + doc links ([c41c3b5](https://github.com/OpenMined/screamingface/commit/c41c3b5813014020b424aab10bd94648a807f361))
* additively refresh repo READMEs — product framing + doc links ([bed4b12](https://github.com/OpenMined/screamingface/commit/bed4b121a4c0569bb31923a258feb0dcbefa3325))
* **screamingface-engine:** update agent config, diagrams and stale paths ([1d2c047](https://github.com/OpenMined/screamingface/commit/1d2c047b2c522dee3df2dc9ea920d36f05584eea))
