# Changelog

All notable changes to the ScreamingFace Desktop app are documented here.
This project follows [Semantic Versioning](https://semver.org/) and uses
release tags of the form `desktop-v<version>`.

## [0.2.0](https://github.com/OpenMined/screamingface/compare/desktop-v0.1.0...desktop-v0.2.0) (2026-05-14)


### Features

* add linux/arm64 CI support and remove hardcoded x64 arch ([e24c2a2](https://github.com/OpenMined/screamingface/commit/e24c2a2835384569561e903f8e0aa3ee5888883e))
* alphabetical plugin list with letter groups + dependency map ([#71](https://github.com/OpenMined/screamingface/issues/71)) ([3fb7d19](https://github.com/OpenMined/screamingface/commit/3fb7d195df33b5259fa0ba588f2f0696b336f9d1))
* **backends:** direct API access for all 3 providers + 74 YAML e2e tests ([6ff26f4](https://github.com/OpenMined/screamingface/commit/6ff26f4a09925ebc33658f6e5e2181a11d7208b0))
* e2e testing pipeline, OTel trace coverage, configurable context embedding ([b2c46f5](https://github.com/OpenMined/screamingface/commit/b2c46f58d0d1b75036c4e025b633b34364796b9c))
* e2e testing pipeline, OTel tracing, configurable embedding, session edit ([7587f93](https://github.com/OpenMined/screamingface/commit/7587f93ed480f04c1648f82ba6bcc5a4927d9a72))
* FrontendRegistry, mitmproxy_intercept routing, desktop plugin settings UI ([8ff63ec](https://github.com/OpenMined/screamingface/commit/8ff63eceff8139ff68597073e923510bd0367a86))
* generate Electron app icon from screamingface emoji ([916d053](https://github.com/OpenMined/screamingface/commit/916d0537ba26ebd3d77240167d3680a513035be5))
* generate Electron app icon from screamingface emoji ([d801702](https://github.com/OpenMined/screamingface/commit/d8017028ea425086c1b83cfeb335283f0fb2cb8f))
* per-session proxy, url4 interpreter, /ensemble + /claude endpoints ([91e7ff2](https://github.com/OpenMined/screamingface/commit/91e7ff2c499bac8bfaeacae929d5ec4fd329777e))
* **SF-79:** Ensemble fan-out-reduce + claude-backend-api defaults & desktop fixes ([#60](https://github.com/OpenMined/screamingface/issues/60)) ([b604ef0](https://github.com/OpenMined/screamingface/commit/b604ef064287c1461f61bcf564d33e8642be9764))
* **SF-87:** product tags on all plugins + grouped Settings UI ([#72](https://github.com/OpenMined/screamingface/issues/72)) ([872348a](https://github.com/OpenMined/screamingface/commit/872348a27817b3eb6dd5d95237764c2d8228a77c))
* TatSu url4 parser, mitmproxy_intercept plugin, desktop UI fixes ([b97eb8e](https://github.com/OpenMined/screamingface/commit/b97eb8ebfa966a1d6cbd3d28a20c9f66400696c7))
* url4 backend integration — intent dispatch, claude-backend prof… ([3833f9b](https://github.com/OpenMined/screamingface/commit/3833f9b60dc6eca6f83737562d4adf7b88c6e36b))
* url4 backend integration — intent dispatch, claude-backend profiles, url4-specs plugin ([9d65ceb](https://github.com/OpenMined/screamingface/commit/9d65cebde36f817a049cd4969d2f0354a9156658))


### Bug Fixes

* add spacing between plugins in group, remove gradient line from header ([#74](https://github.com/OpenMined/screamingface/issues/74)) ([c721e61](https://github.com/OpenMined/screamingface/commit/c721e61c4a460f264365404bdad7a9637b4434e9))
* **desktop:** squished status dot + app lingering in dock after dev exit ([a422a13](https://github.com/OpenMined/screamingface/commit/a422a139eee6d4a79c85865dad1119489e5959bb))
* enable SpecSelectorWidget for all frontend plugins ([#70](https://github.com/OpenMined/screamingface/issues/70)) ([ad845f3](https://github.com/OpenMined/screamingface/commit/ad845f380882ea3b85ddafdb58cd46584173ac8c))
* hide session types when frontend plugin is not active ([#68](https://github.com/OpenMined/screamingface/issues/68)) ([85c51f3](https://github.com/OpenMined/screamingface/commit/85c51f3937f4214151c7a2d4f9b5d6e5fae8304a))
* only validate newly added plugins, allow removals ([#67](https://github.com/OpenMined/screamingface/issues/67)) ([9aca6d5](https://github.com/OpenMined/screamingface/commit/9aca6d55f824376db609d260ab07f93ce2c35588))
* remove dead showHeader/letter code from SettingsView ([#73](https://github.com/OpenMined/screamingface/issues/73)) ([ac99012](https://github.com/OpenMined/screamingface/commit/ac99012ceca1c2c252b68a2eb3c5bcf44625bbf8))
* resolve electron-builder CI failure by adding repository and disabling publish ([77898c5](https://github.com/OpenMined/screamingface/commit/77898c58bf855467bc139aef04ea49ae15bc7a07))
* resolve electron-builder CI packaging failure ([cbad66c](https://github.com/OpenMined/screamingface/commit/cbad66c279fad34e038af2d1942046fe15abeb7e))
* show all session types with install prompt for missing CLI tools ([#69](https://github.com/OpenMined/screamingface/issues/69)) ([54856d4](https://github.com/OpenMined/screamingface/commit/54856d4b4dfa70b14cb43c81117b62e62276732e))
* show session defaults disclaimer on all frontend plugins ([#76](https://github.com/OpenMined/screamingface/issues/76)) ([271fc16](https://github.com/OpenMined/screamingface/commit/271fc163eace8a62f9d52cfeb1a2d7941b415a55))
* validate plugin preflight before saving config ([#66](https://github.com/OpenMined/screamingface/issues/66)) ([4d7ad4c](https://github.com/OpenMined/screamingface/commit/4d7ad4c666271d32409e9f757aef2e28a9e94314))


### Refactors

* rename claude-cli to claude-backend, simplify plugin settings ([1204738](https://github.com/OpenMined/screamingface/commit/12047382086c6e18c1bd61422b6ff19186de9451))
* Rename plugins to consistent claude- prefix convention ([b123360](https://github.com/OpenMined/screamingface/commit/b123360f2e4cfbd342a1b02fab818dfa11d8fdcb))

## [Unreleased]

## [0.1.0]

- Initial release.
