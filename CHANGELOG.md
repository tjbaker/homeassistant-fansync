# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog and this project adheres to Semantic Versioning.

## [0.2.4](https://github.com/tjbaker/homeassistant-fansync/compare/v0.2.3...v0.2.4) (2025-10-28)


### Performance Improvements

* reduce recv-loop CPU (lock timeout) and drop redundant decode ([#44](https://github.com/tjbaker/homeassistant-fansync/issues/44)) ([cb059e6](https://github.com/tjbaker/homeassistant-fansync/commit/cb059e6ef04b45f8b80d789b5417df29fa12feb4))

## [0.2.3](https://github.com/tjbaker/homeassistant-fansync/compare/v0.2.2...v0.2.3) (2025-10-28)


### Features

* add fallback polling ([#39](https://github.com/tjbaker/homeassistant-fansync/issues/39)) ([86926c1](https://github.com/tjbaker/homeassistant-fansync/commit/86926c11dd4afceabc8421f0af38a2c77a709dfe))

## [0.2.2](https://github.com/tjbaker/homeassistant-fansync/compare/v0.2.1...v0.2.2) (2025-10-28)


### Features

* add targeted DEBUG logs; tests for fan/client logging ([#34](https://github.com/tjbaker/homeassistant-fansync/issues/34)) ([d1335e4](https://github.com/tjbaker/homeassistant-fansync/commit/d1335e4051a5a9cc298d4d87f382a5bdfc38afba))

## [0.2.1](https://github.com/tjbaker/homeassistant-fansync/compare/v0.2.0...v0.2.1) (2025-10-28)


### Miscellaneous Chores

* release 0.2.1 ([#32](https://github.com/tjbaker/homeassistant-fansync/issues/32)) ([242bdb5](https://github.com/tjbaker/homeassistant-fansync/commit/242bdb5a6e6ba869a202bf03fdb98e0e9708adfc))

## [0.2.0](https://github.com/tjbaker/homeassistant-fansync/compare/0.1.0...v0.2.0) (2025-10-27)


### Features

* add multi-device support and per-device entities ([bd0de31](https://github.com/tjbaker/homeassistant-fansync/commit/bd0de31f755edd234dfd32e762f1c445a638e962))
* add multi-device support and per-device entities ([782f2f6](https://github.com/tjbaker/homeassistant-fansync/commit/782f2f6b38a1922537382016a45654c38688c982))


### Bug Fixes

* remove unreachable branch in push callback and satisfy mypy ([36d0870](https://github.com/tjbaker/homeassistant-fansync/commit/36d087034cf86213f277061da5228b3b16409484))

## [Unreleased]

### Added
- 

### Changed
- 

### Fixed
- 

## [0.1.0] - 2025-10-27
### Added
- Initial release.

[Unreleased]: https://github.com/tjbaker/homeassistant-fansync/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/tjbaker/homeassistant-fansync/releases/tag/v0.1.0
