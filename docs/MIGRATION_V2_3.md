# Migrating To v2.3

Previous Linux installations may have been created by
`scripts/install-user-service.sh`. Upgrade the package, then run:

```bash
synkraken install
synkraken status
synkraken doctor
```

The installer rewrites the user service with the current Python environment
and selected configuration.

For a new macOS machine:

```bash
pip install -e .
synkraken config
synkraken install
```

Do not copy Linux service files to macOS. SynKraken creates the correct native
LaunchAgent automatically. Copy `config.local.json` and the `data` directory
only when migrating existing local state, then run `synkraken install` from
the directory containing that configuration.

Uninstalling v2.3 preserves migrated data by default.
