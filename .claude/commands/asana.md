# Asana Task Manager

Manage Asana tasks via REST API. Parse the user's argument: `$ARGUMENTS`

## Defaults

- **User GID:** `1213642528342317` (Sergey Bershadsky)
- **Default project:** `1213628819033917`
- **Workspace:** `1185126988600652` (OpenMined)

When a command needs a project and none is specified, use the default project.

## API Access

Load the PAT and call the API using Bash with curl:

```bash
export $(grep ASANA_PAT "$CLAUDE_PROJECT_DIR/.env" | xargs) && curl -s \
  -H "Authorization: Bearer $ASANA_PAT" \
  -H "Content-Type: application/json" \
  "https://app.asana.com/api/1.0/<endpoint>" | python3 -m json.tool
```

**Important:** Always use Bash with `curl` for API calls. Do NOT use WebFetch (it doesn't support custom auth headers). Use `export $(grep ASANA_PAT ... | xargs)` instead of `source .env` to avoid shell parsing issues.

## Routing

Based on `$ARGUMENTS`, perform the matching operation:

### No arguments / `my tasks`
1. Get tasks from user task list: `GET /user_task_lists/1213642528476271/tasks?completed_since=now&opt_fields=name,due_on,assignee_section.name,permalink_url` (OpenMined workspace)
2. Display as a formatted list with names, due dates, sections, and links

### `workspaces`
- `GET /workspaces?opt_fields=name,gid`
- Display workspace names and GIDs

### `projects` or `projects <workspace_gid>`
- If workspace GID provided: `GET /workspaces/{workspace_gid}/projects?opt_fields=name,gid,archived&limit=100`
- If not: first get workspaces, then list projects for each
- Filter out archived projects. Display names and GIDs.

### `tasks <project_gid>`
- `GET /projects/{project_gid}/tasks?opt_fields=name,completed,due_on,assignee.name,assignee_section.name&limit=100`
- Display incomplete tasks grouped by section

### `task <task_gid>`
- `GET /tasks/{task_gid}?opt_fields=name,notes,due_on,completed,assignee.name,projects.name,tags.name,permalink_url,custom_fields.name,custom_fields.display_value,memberships.section.name`
- Display full task details in a readable format

### `create <name>` with optional `project:<gid>` `due:<date>` `assignee:me`
- Build JSON body: `{"data": {"name": "<name>", ...}}`
- Always set `"assignee": "1213642528342317"` (unless a different assignee is specified)
- If `project:<gid>`: add `"projects": ["<gid>"]`, otherwise use default project `"projects": ["1213628819033917"]`
- If `due:<date>`: add `"due_on": "<date>"` (YYYY-MM-DD format)
- `POST /tasks` with the JSON body using `-d`
- Confirm creation with task name, GID, and permalink

### `update <task_gid>` with `field:value` pairs
- Supported fields: `name`, `due_on` (alias: `due`), `notes`, `assignee`
- Build JSON `{"data": {field: value, ...}}`
- `PUT /tasks/{task_gid}` with `-X PUT -d`
- Confirm what was updated

### `complete <task_gid>`
- `PUT /tasks/{task_gid}` with body `{"data": {"completed": true}}`
- Confirm task marked complete with its name

### `search <query>`
- `GET /workspaces/1185126988600652/tasks/search?text={query}&opt_fields=name,completed,due_on,assignee.name,permalink_url&is_subtask=false&limit=20`
- Display matching tasks

### `sections <project_gid>`
- `GET /projects/{project_gid}/sections?opt_fields=name,gid`
- Display section names and GIDs

### `move <task_gid> <section_gid>`
- `POST /sections/{section_gid}/addTask` with body `{"data": {"task": "<task_gid>"}}`
- Confirm task moved to section

## Output Format

- Present results in clean markdown tables or lists
- Always include GIDs so the user can reference them in follow-up commands
- Include permalink URLs when available
- For errors, show the Asana API error message and suggest corrections
