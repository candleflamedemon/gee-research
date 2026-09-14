# Earth Engine Project selection

Use this reference before initializing Earth Engine. A computation Project is a
per-task/per-workspace choice, not a permanent property of this skill.

## Resolution order

1. If the user explicitly names a Project for the current task, use that value.
   In helper CLIs, pass it with `--project`. This always overrides local config.
2. Otherwise, look only for `.gee-project.json` in the current workspace root.
   If it contains a valid `project`, use that value.
3. Otherwise, call `ee.Initialize()` without a Project so the Earth Engine
   client can use its currently configured default. Report the effective
   Project exposed by the initialized client when available.
4. If no effective Project can be established, ask the user. Do not guess.

Never select a computation Project from an Asset ID, even when the Asset name
contains `projects/PROJECT/assets/...`. Asset ownership/access and the Project
used to initialize or bill a different computation are separate decisions.

## Optional workspace config

At the root of a research workspace, the user may create:

```json
{
  "project": "your-google-cloud-project-id"
}
```

The filename is `.gee-project.json`. It stores only a non-secret Project ID or
number. Never place OAuth tokens, passwords, credential JSON, service-account
keys, or other secrets in this file. The shared `initialize_ee` helper rejects
credential-like keys and does not search parent directories, preventing an
unrelated parent workspace from silently changing the Project.

Do not create or rewrite this file unless the user asks. Do not run
`earthengine set_project` merely to satisfy one task because that mutates the
Earth Engine CLI default beyond the current process.

## Reporting

Record the effective Project and one of these selection sources:

- `explicit_argument`
- `project_config`
- `earth_engine_default`

If the API accepts initialization but does not expose the effective default,
mark it unknown and ask before a Project-sensitive write or export.
