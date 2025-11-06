# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog and this project adheres to Semantic Versioning.

## [0.5.2](https://github.com/tjbaker/homeassistant-fansync/compare/0.5.1...0.5.2) (2025-11-06)


### Bug Fixes

* use bracket notation for TypedDict access in diagnostics ([d725b72](https://github.com/tjbaker/homeassistant-fansync/commit/d725b7233341bf3a0e7766c0870c2f4cbe4f36db))


### Code Refactoring

* improve code quality for Bronze tier compliance ([6dcac4e](https://github.com/tjbaker/homeassistant-fansync/commit/6dcac4e392cafa639f53885b7cc9352fd9d5de57))
* modernize to HA best practices (config_entry, type alias, manifest) ([dd99e16](https://github.com/tjbaker/homeassistant-fansync/commit/dd99e162aa1f12acc130c6308c2319967db46a06))

## [0.5.1](https://github.com/tjbaker/homeassistant-fansync/compare/0.5.0...0.5.1) (2025-11-04)


### Bug Fixes

* validate predicate on early termination ([240af40](https://github.com/tjbaker/homeassistant-fansync/commit/240af40e9ba31e7f16b8a9854e1c2151d44fb236))


### Performance Improvements

* add early termination for confirmation polling ([8947ca2](https://github.com/tjbaker/homeassistant-fansync/commit/8947ca263d4db41e0c98e8d1fdb10fa4a04371c8))


### Code Refactoring

* address Copilot feedback ([94f7cd0](https://github.com/tjbaker/homeassistant-fansync/commit/94f7cd0c66ef60736a933d71402f51991a6618e0))

## [0.5.0](https://github.com/tjbaker/homeassistant-fansync/compare/0.4.0...0.5.0) (2025-11-04)


### Features

* capture and display diagnostics on config flow timeout ([e6f86d6](https://github.com/tjbaker/homeassistant-fansync/commit/e6f86d679458dda11504bf444ffea1fb58423f64))

## [0.4.0](https://github.com/tjbaker/homeassistant-fansync/compare/0.3.4...0.4.0) (2025-11-03)


### Features

* add comprehensive diagnostics and issue templates ([89415d2](https://github.com/tjbaker/homeassistant-fansync/commit/89415d285433d876c06106245eb6d35a66ac34c2))

## [0.3.4](https://github.com/tjbaker/homeassistant-fansync/compare/0.3.3...0.3.4) (2025-11-03)


### Performance Improvements

* fix blocking I/O in async_connect and token refresh ([d94c965](https://github.com/tjbaker/homeassistant-fansync/commit/d94c965a27efd6e9dabed4a794c34fc93cdf0d64))
* reduce aggressive confirmation polling after commands ([f8b6f2c](https://github.com/tjbaker/homeassistant-fansync/commit/f8b6f2c760dbd64e6ee9800bebb327a7cfc9b32a))


### Code Refactoring

* use dict[str, Any] type hint for JSON data ([7c765bc](https://github.com/tjbaker/homeassistant-fansync/commit/7c765bc7aade02ae2ad3f7280544f10f91cf92f4))

## [0.3.3](https://github.com/tjbaker/homeassistant-fansync/compare/0.3.2...0.3.3) (2025-11-03)


### Bug Fixes

* address Copilot PR feedback ([b0d530f](https://github.com/tjbaker/homeassistant-fansync/commit/b0d530f122e17a1998d4c79706c2ce95a83c853a))
* address Copilot PR review suggestions ([c92674b](https://github.com/tjbaker/homeassistant-fansync/commit/c92674b84758cdafe1483f56efb316fdb8cd973c))
* address remaining Copilot PR feedback ([c8c13d2](https://github.com/tjbaker/homeassistant-fansync/commit/c8c13d2ad82baa437231fc805ef4614995ac62b3))
* resolve WebSocket concurrency error with message routing ([5941afb](https://github.com/tjbaker/homeassistant-fansync/commit/5941afb01056618fe913d152633d4d2bd4dad9f4))


### Code Refactoring

* add type parameter to _pending_requests dict ([29758b2](https://github.com/tjbaker/homeassistant-fansync/commit/29758b23d927514855aa3d960cc8c7c6d210b47b))
* address final Copilot feedback ([901885a](https://github.com/tjbaker/homeassistant-fansync/commit/901885a00632a4080f2a1f449fcbfb6bdea67a00))
* clean up skipped tests and improve test suite ([9543d1c](https://github.com/tjbaker/homeassistant-fansync/commit/9543d1c0ffc3bf4eb0c24222f00f8cf6853537a2))

## [0.3.2](https://github.com/tjbaker/homeassistant-fansync/compare/0.3.1...0.3.2) (2025-11-03)


### Bug Fixes

* add type annotations and use State.OPEN for mypy ([3cc6492](https://github.com/tjbaker/homeassistant-fansync/commit/3cc64928bf675caeb4b86bedbef0b5437f2dab9b))
* avoid blocking I/O and unnecessary reconnections ([b431f08](https://github.com/tjbaker/homeassistant-fansync/commit/b431f08d547df9f76e892734b33340fd4fb8c5b3))


### Code Refactoring

* address Copilot feedback ([4f0e681](https://github.com/tjbaker/homeassistant-fansync/commit/4f0e681a5a4b8bac1f63ad631f8a931f1d41bb10))
* extract test helpers and improve docstring accuracy ([d268abb](https://github.com/tjbaker/homeassistant-fansync/commit/d268abbe0eeed95a5c18d8893e7510b8710524c9))

## [0.3.1](https://github.com/tjbaker/homeassistant-fansync/compare/0.3.0...0.3.1) (2025-11-03)


### Bug Fixes

* require explicit SSL context for wss:// URIs ([930099b](https://github.com/tjbaker/homeassistant-fansync/commit/930099b234b9b4afe701177277bb3db85d2cd918))


### Code Refactoring

* simplify SSL context creation ([157378e](https://github.com/tjbaker/homeassistant-fansync/commit/157378e69b0cdddc108d018cda1943eabe12b3d2))

## [0.3.0](https://github.com/tjbaker/homeassistant-fansync/compare/0.2.25...0.3.0) (2025-11-03)


### ⚠ BREAKING CHANGES

* The websocket-client library has been replaced with websockets>=12.0. All client methods now use native async/await patterns. Direct client users must update their code to use async/await. Home Assistant integration users are unaffected (integration already used async).

### Features

* add enhanced error logging for debugging ([7213660](https://github.com/tjbaker/homeassistant-fansync/commit/7213660b1d459cadd4ba95b0e1292737dcf8c73b))
* migrate from websocket-client to async websockets ([95a587f](https://github.com/tjbaker/homeassistant-fansync/commit/95a587f0e8c1ae764f52d584ac3f96a4d1b84ba8))


### Bug Fixes

* add explanatory comment to WebSocket cleanup exception ([febc2b6](https://github.com/tjbaker/homeassistant-fansync/commit/febc2b6be33b0cfd7995ecf5fe7dfeb8204c9f82))
* add explanatory comments and mypy type narrowing ([9c9b22e](https://github.com/tjbaker/homeassistant-fansync/commit/9c9b22ef91eb40db153a790eeb9375a6c05e3f9d))
* improve warning messages to reflect cloud-side latency ([60a5a6c](https://github.com/tjbaker/homeassistant-fansync/commit/60a5a6c821394658f4f60aba4ce5353337fce679))
* replace websocket-client exceptions with async equivalents ([af71943](https://github.com/tjbaker/homeassistant-fansync/commit/af71943ff9950d6bbf76817270f82570a3bbb1f7))
* update requirements-dev.txt for websockets library ([891d608](https://github.com/tjbaker/homeassistant-fansync/commit/891d608f798256a9248f419cad3bf529608ea13b))

## [0.2.25](https://github.com/tjbaker/homeassistant-fansync/compare/0.2.24...0.2.25) (2025-11-03)


### Bug Fixes

* handle WebSocket timeouts gracefully and fix device metadata timing ([8dee65b](https://github.com/tjbaker/homeassistant-fansync/commit/8dee65b24b67d56ddf335f4258d6495810e4a1cb))

## [0.2.24](https://github.com/tjbaker/homeassistant-fansync/compare/0.2.23...0.2.24) (2025-11-03)


### Bug Fixes

* ensure device metadata visible and add latency diagnostics ([c1511e1](https://github.com/tjbaker/homeassistant-fansync/commit/c1511e166fa45f3d8214cb7fd149258c45573143))

## [0.2.23](https://github.com/tjbaker/homeassistant-fansync/compare/0.2.22...0.2.23) (2025-11-03)


### Features

* add diagnostics platform for connection metrics ([a759f8d](https://github.com/tjbaker/homeassistant-fansync/commit/a759f8d86ed51ea34eb1931642fbf55fd8416876))


### Bug Fixes

* add type annotations to test helper functions ([7d1ebb8](https://github.com/tjbaker/homeassistant-fansync/commit/7d1ebb876f6750148427155b05a79a87b90db60e))
* address Copilot AI review feedback ([73946e4](https://github.com/tjbaker/homeassistant-fansync/commit/73946e47816f78a7e66547990afcb97a1e020a8c))
* address second round of Copilot review feedback ([0e78926](https://github.com/tjbaker/homeassistant-fansync/commit/0e78926228f18201aa711b846e70093a1a315dfe))
* improve type hints and edge case handling ([78d9b86](https://github.com/tjbaker/homeassistant-fansync/commit/78d9b8640191e7d0b5bbb3583bd5e5d6a2d1e697))
* mask MAC addresses and simplify test helper ([9489686](https://github.com/tjbaker/homeassistant-fansync/commit/94896860169e69a20d50ada0cdfdd50b5f0a2ff8))
* remove non-actionable recommendation message ([d248e77](https://github.com/tjbaker/homeassistant-fansync/commit/d248e7717e42ac447f8502ee97636ab825e4f824))
* update device registry when profile data arrives ([41c9c45](https://github.com/tjbaker/homeassistant-fansync/commit/41c9c45ff4bb5911e50922ca05c8c00ef1b61d98))


### Code Refactoring

* simplify ternary to or expression ([8f3739d](https://github.com/tjbaker/homeassistant-fansync/commit/8f3739d14506ee72f01752be812d785bb1262d66))

## [0.2.22](https://github.com/tjbaker/homeassistant-fansync/compare/0.2.21...0.2.22) (2025-11-03)


### Bug Fixes

* add connection lock to prevent blocking I/O under locks ([52b1b3e](https://github.com/tjbaker/homeassistant-fansync/commit/52b1b3eecbbb86ef768a31f5a58ab2073ca45246))
* address Copilot feedback on deadlock fix ([6387ae6](https://github.com/tjbaker/homeassistant-fansync/commit/6387ae603c262d889ac4feda165f85e07eb67639))
* address lock ordering and test determinism feedback ([b6f00b1](https://github.com/tjbaker/homeassistant-fansync/commit/b6f00b16135126ab2bc6a9c34a8eff2575db9649))
* prevent double-release of recv_lock in reconnect path ([a50ea93](https://github.com/tjbaker/homeassistant-fansync/commit/a50ea930d97ba29486c6981e965ff25da890bc57))
* resolve critical deadlock in WebSocket locking ([2369a6c](https://github.com/tjbaker/homeassistant-fansync/commit/2369a6c2d4bfbe86c922c0ad0c34e8bd61f38f16))
* resolve critical nested lock deadlock issues ([bb68266](https://github.com/tjbaker/homeassistant-fansync/commit/bb68266ab4a7c12e614374797abb8c679ffaa791))


### Code Refactoring

* extract magic number and add test docstring ([e996a5e](https://github.com/tjbaker/homeassistant-fansync/commit/e996a5e24ee10a6d0479b5d5ff4df4d3fc52ebac))
* simplify recv_loop lock management ([77fe221](https://github.com/tjbaker/homeassistant-fansync/commit/77fe22165e174d6b8d2434fec76dc9b6820efb67))

## [0.2.21](https://github.com/tjbaker/homeassistant-fansync/compare/0.2.20...0.2.21) (2025-11-03)


### Bug Fixes

* remove blocking recv from async_set to prevent 30s timeout ([31f7a95](https://github.com/tjbaker/homeassistant-fansync/commit/31f7a951500e5f9644f1d5c61a24c0b023444921))

## [0.2.20](https://github.com/tjbaker/homeassistant-fansync/compare/0.2.19...0.2.20) (2025-11-02)


### Bug Fixes

* add detailed logging for set command ack handling ([3cbfa7a](https://github.com/tjbaker/homeassistant-fansync/commit/3cbfa7ac7278d5a6f6704cbef108769235ef050b))

## [0.2.19](https://github.com/tjbaker/homeassistant-fansync/compare/0.2.18...0.2.19) (2025-11-02)


### Bug Fixes

* add debug logging for device profile caching ([1805e49](https://github.com/tjbaker/homeassistant-fansync/commit/1805e4966b1ea09a66327c43b7f7c4b24c1d6029))

## [0.2.18](https://github.com/tjbaker/homeassistant-fansync/compare/0.2.17...0.2.18) (2025-11-02)


### Features

* add diagnostics, metrics, and circuit breaker ([bc4756b](https://github.com/tjbaker/homeassistant-fansync/commit/bc4756b30365ffb0466baaf82fde9f61328364d4))


### Bug Fixes

* rely on push updates instead of post-set status fetch ([edfd5b6](https://github.com/tjbaker/homeassistant-fansync/commit/edfd5b666557d8f1a0b1a5944b7cc5a03af64d6a))

## [0.2.17](https://github.com/tjbaker/homeassistant-fansync/compare/0.2.16...0.2.17) (2025-11-02)


### Bug Fixes

* keep entities available when coordinator polls timeout ([7c56710](https://github.com/tjbaker/homeassistant-fansync/commit/7c567108980dcce04c51828b253d2cffbb92700e))

## [0.2.16](https://github.com/tjbaker/homeassistant-fansync/compare/0.2.15...0.2.16) (2025-11-02)


### Bug Fixes

* avoid premature timeouts; skip light when devices lack light ([863794a](https://github.com/tjbaker/homeassistant-fansync/commit/863794a8c8771cdcb9a45656f2a8bed70f5623b9))
* resolve light entity creation race condition ([54fa335](https://github.com/tjbaker/homeassistant-fansync/commit/54fa3357e09a582d224f52d138950493e880ce3e))

## [0.2.15](https://github.com/tjbaker/homeassistant-fansync/compare/0.2.14...0.2.15) (2025-11-02)


### Bug Fixes

* align poll/first-refresh timeouts with WS setting to avoid premature cancel ([ef83607](https://github.com/tjbaker/homeassistant-fansync/commit/ef836070a31bdd2108a24d27d1981d4aaf5268f9))

## [0.2.14](https://github.com/tjbaker/homeassistant-fansync/compare/0.2.13...0.2.14) (2025-11-02)


### Bug Fixes

* options flow init; raise poll timeout; improve timeout logging ([6ba5929](https://github.com/tjbaker/homeassistant-fansync/commit/6ba59297c8d18d8e732f7bc0e7cceee45ac11bf6))

## [0.2.13](https://github.com/tjbaker/homeassistant-fansync/compare/0.2.12...0.2.13) (2025-11-02)


### Bug Fixes

* bound first refresh and parallelize status fetches to prevent UI spin ([8de8779](https://github.com/tjbaker/homeassistant-fansync/commit/8de8779f0470ad2b27d7608104be42d4ed48ddbd))

## [0.2.12](https://github.com/tjbaker/homeassistant-fansync/compare/0.2.11...0.2.12) (2025-11-02)


### Features

* improve connection resilience and user-facing errors ([47581b8](https://github.com/tjbaker/homeassistant-fansync/commit/47581b819fd5ff69497d75cbb4ea154142754b8b))

## [0.2.11](https://github.com/tjbaker/homeassistant-fansync/compare/0.2.10...0.2.11) (2025-10-31)


### Bug Fixes

* avoid httpx.Timeout error by setting total timeout ([c76da1a](https://github.com/tjbaker/homeassistant-fansync/commit/c76da1a6a10a30654197d64e217a6357f37bb8d1))

## [0.2.10](https://github.com/tjbaker/homeassistant-fansync/compare/0.2.9...0.2.10) (2025-10-31)


### Features

* configurable HTTP/WS timeouts; docs and logging updates ([#66](https://github.com/tjbaker/homeassistant-fansync/issues/66)) ([fc12cc6](https://github.com/tjbaker/homeassistant-fansync/commit/fc12cc636f297e5773fa8629e372b653b113c93b))

## [0.2.9](https://github.com/tjbaker/homeassistant-fansync/compare/0.2.8...0.2.9) (2025-10-30)


### Features

* **ui:** add default icons for fan and light entities ([#63](https://github.com/tjbaker/homeassistant-fansync/issues/63)) ([efd9a37](https://github.com/tjbaker/homeassistant-fansync/commit/efd9a376d54cad189c56e2a24425dbc9b9c39dac))

## [0.2.8](https://github.com/tjbaker/homeassistant-fansync/compare/0.2.7...0.2.8) (2025-10-30)


### Bug Fixes

* **i18n:** use translations/en.json for config flow errors ([#61](https://github.com/tjbaker/homeassistant-fansync/issues/61)) ([d6c4309](https://github.com/tjbaker/homeassistant-fansync/commit/d6c430999aafba14b5cdcc995649ca287f1d143c))

## [0.2.7](https://github.com/tjbaker/homeassistant-fansync/compare/0.2.6...0.2.7) (2025-10-30)


### Features

* improve setup UX and diagnostics (specific errors, logs) ([#58](https://github.com/tjbaker/homeassistant-fansync/issues/58)) ([647b2d0](https://github.com/tjbaker/homeassistant-fansync/commit/647b2d0f261eff9f9db336c39d3fefd2696d2f9e))

## [0.2.6](https://github.com/tjbaker/homeassistant-fansync/compare/v0.2.5...0.2.6) (2025-10-29)


* release 0.2.6 ([#56](https://github.com/tjbaker/homeassistant-fansync/issues/56)) ([24cc021](https://github.com/tjbaker/homeassistant-fansync/commit/24cc021e2975dc84eeeea1e7e6dcbe371e3f0cf3))

## [0.2.5](https://github.com/tjbaker/homeassistant-fansync/compare/v0.2.4...v0.2.5) (2025-10-29)


### Features

* surface more device info ([#46](https://github.com/tjbaker/homeassistant-fansync/issues/46)) ([06bc99f](https://github.com/tjbaker/homeassistant-fansync/commit/06bc99f1259aea1857d13d3458fe0c1702a6f4fe))

## [0.2.4](https://github.com/tjbaker/homeassistant-fansync/compare/v0.2.3...v0.2.4) (2025-10-28)
