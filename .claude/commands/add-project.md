Add a new project to the `data/projects.json` registry by running:

```bash
python scripts/add_project.py $ARGUMENTS
```

The script takes a project filesystem path and optional flags:
- First argument: absolute path to the project (e.g. `/Users/david/projects/my-project`)
- `--git <path>`: git repo path if different from project path
- `--name "My Name"`: display name override (derived from path if omitted)

After the script succeeds, show the user the next steps to ingest the new project's sessions.
