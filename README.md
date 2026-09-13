# cpa-plugin-deepseek-harness-session

A focused CLIProxyAPI request interceptor that maps the DeepSeek Harness conversation header:

```text
X-DeepSeek-Harness-Session-Id -> X-Session-ID
```

This lets deepseek-harness clients participate in CLIProxyAPI session-affinity routing and retain stable upstream selection across turns.

## Behavior

The plugin runs on both `request.intercept_before` and `request.intercept_after`:

- Header-name matching is case-insensitive.
- Leading and trailing whitespace is removed from the source value.
- A missing or blank source header is a no-op.
- An existing `X-Session-ID` header is authoritative and is never overwritten.
- The plugin changes headers only; request bodies, credentials, routing configuration, and responses are untouched.

## Install

The existing official Store identity remains:

- ID: `deepseek-harness-session`
- Name: `DeepSeek Harness Session Affinity`

Once the Store record points to this dedicated repository, install or update that existing entry through the CLIProxyAPI plugin-management API. Example configuration:

```yaml
plugins:
  enabled: true
  configs:
    deepseek-harness-session:
      enabled: true
      priority: 1
```

CLIProxyAPI loads Go shared libraries only at startup, so restart the host after installing or replacing the artifact.

## Build

The build script uses a pinned Debian/glibc builder, mounts this repository read-only, runs formatting/module/vet/test/race and package-helper gates, and writes to repository-local staging by default:

```bash
./build.sh
# dist/local/linux_amd64/deepseek-harness-session-v0.1.2.so
```

Override the staging location with `PLUGIN_OUT_DIR`. Do not build directly into a live plugin mount.

Direct source checks:

```bash
test -z "$(gofmt -l ./*.go ./.github/scripts/*.go)"
go mod verify
go vet ./...
go vet ./.github/scripts
go test ./...
go test ./.github/scripts
go test -race ./...
```

## Releases

A `v<version>` tag builds five native archives named:

```text
deepseek-harness-session_<version>_<goos>_<goarch>.zip
```

Each archive contains exactly one canonical root library (`deepseek-harness-session.so`, `.dylib`, or `.dll`) with deterministic metadata. `checksums.txt` uses `sha256sum` format, and the workflow refuses to replace an existing GitHub Release.

### Historical release correction

The legacy `ahoo/cliproxy-plugins` v0.1.0 and v0.1.1 tags both pointed to a registry-only commit; their generated source archives contained no plugin source. The v0.1.1 binary also recorded a dirty CLIProxyAPI checkout rather than a clean plugin source revision. Those historical tags and assets remain unchanged in the legacy repository.

This dedicated repository preserves the original four-commit history but intentionally does not recreate the defective old tags. `v0.1.2` is the first clean, source-bearing release whose binary provenance resolves to the tagged dedicated-repository commit.

## Provenance and license

Plugin-specific session mapping was introduced by `ahoo` in legacy commit [`3192d9a`](https://github.com/ahoo/cliproxy-plugins/commit/3192d9a378149845931d9166eab7df237c4d19a6). The c-shared ABI bridge derives from Router-For.ME CLIProxyAPI examples by Luis Pater. See [NOTICE](NOTICE) for immutable source references and [LICENSE](LICENSE) for the complete MIT notices.
