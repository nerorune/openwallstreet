# OpenWallStreet launcher extensions

The `openwallstreet` command treats each executable file in this directory as
a local subcommand. For example, an executable `research` script is available
as:

```bash
openwallstreet research --help
```

Extensions receive the resolved checkout directory in `$OPENWALLSTREET_ROOT`.
They should implement `--help`, use existing local lifecycle wrappers for
Gateway/MMR operations, and preserve the defaults of paper mode, locked
execution, localhost-only networking, and MFA. Do not put credentials or MFA
values in an extension, its output, or its configuration.
