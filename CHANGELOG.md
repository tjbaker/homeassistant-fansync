# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog and this project adheres to Semantic Versioning.

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
