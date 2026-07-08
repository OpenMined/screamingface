---
description: Read-only view of product/marketing top-level tasks in Asana. Use to list, read, or search product context (projects, tasks, briefs) or when the user references an Asana task URL/GID. NEVER creates, updates, completes, or moves anything in Asana — technical work items live in Linear (task-management skill).
user_invocable: true
---

# Asana — read-only product/marketing source

**Announce at start:** "Using the asana-product skill — read-only Asana access."

## Hard rules

- **READ-ONLY. GET requests only.** Any request to create, update, complete, move, or
  section an Asana task → refuse and point to the `task-management` skill (Linear).
- Asana holds product/marketing top-level tasks defined by product/marketing tooling —
  it is a SOURCE of context, never a destination for technical work.
- A dev work item descending from an Asana task records the Asana permalink in its Linear
  description and in the `docs/tasks/` mirror frontmatter (`asana_url`).

## Defaults (OpenMined workspace)

- **Workspace:** `1185126988600652` (OpenMined)
- **Default project:** `1213628819033917`
- **User task list:** `1213642528476271` (Sergey Bershadsky)

## API Access

Always use Bash with `curl`. Do NOT use WebFetch — it doesn't support custom auth headers.

Locate `ASANA_PAT` from the first available source (check in this order):

1. Already exported in env: `printenv ASANA_PAT`
2. `$CLAUDE_PROJECT_DIR/.env` (if set and file exists)
3. `./.env` in the current working directory
4. `~/.config/asana/.env`
5. `~/.asana.env`

```bash
for f in "$CLAUDE_PROJECT_DIR/.env" "./.env" "$HOME/.config/asana/.env" "$HOME/.asana.env"; do
  [ -f "$f" ] && export $(grep -E '^ASANA_PAT=' "$f" | xargs) && break
done
[ -z "$ASANA_PAT" ] && echo "ASANA_PAT not found. Add ASANA_PAT=<token> to ~/.config/asana/.env" && exit 1

curl -s -H "Authorization: Bearer $ASANA_PAT" \
  "https://app.asana.com/api/1.0/<endpoint>" | python3 -m json.tool
```

If the PAT is missing, tell the user where to put it and stop.

## Parsing Asana URLs

`https://app.asana.com/1/<workspace>/project/<project_gid>/task/<task_gid>` → extract the
trailing `task/<task_gid>` segment and run the `task <gid>` operation.

## Operations (all GET)

### "my tasks" / "what's on my plate"
`GET /user_task_lists/1213642528476271/tasks?completed_since=now&opt_fields=name,due_on,assignee_section.name,permalink_url`

### "workspaces"
`GET /workspaces?opt_fields=name,gid`

### "projects" or "projects <workspace_gid>"
`GET /workspaces/{workspace_gid}/projects?opt_fields=name,gid,archived&limit=100` (filter archived)

### "tasks <project_gid>"
`GET /projects/{project_gid}/tasks?opt_fields=name,completed,due_on,assignee.name,assignee_section.name&limit=100`

### "task <task_gid>" (or pasted URL)
`GET /tasks/{task_gid}?opt_fields=name,notes,due_on,completed,assignee.name,projects.name,tags.name,permalink_url,custom_fields.name,custom_fields.display_value,memberships.section.name`

### "search <query>"
`GET /workspaces/1185126988600652/tasks/search?text={query}&opt_fields=name,completed,due_on,assignee.name,permalink_url&is_subtask=false&limit=20`
(URL-encode: `python3 -c 'import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))' "<text>"`)

### "sections <project_gid>"
`GET /projects/{project_gid}/sections?opt_fields=name,gid`

## Output format

- Clean markdown tables/lists; always include GIDs and permalink URLs.
- When the user wants to act on what was found (implement, fix, follow up): file the Linear
  work item via the `task-management` skill and carry the Asana permalink over.
