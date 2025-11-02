# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog and this project adheres to Semantic Versioning.

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
