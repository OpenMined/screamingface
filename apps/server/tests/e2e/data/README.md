# url4 E2E Test Matrix

Each `*.yaml` file in this directory defines test cases for the
YAML-driven parametrized runner (`test_url4_matrix.py`). All files
are loaded and merged automatically — add a new file to add a new
topic.

## YAML schema

```yaml
- id: unique_test_id
  description: "Human description"
  ticket: SF-XX
  backends: [claude]           # required backends (health-checked)
  expression: "/claude()!..."  # the url4 q= parameter
  params: {processor: /claude} # extra query params (optional)
  setup_blob:                  # create a /data blob before test (optional)
    content: "..."
    content_type: text/plain
  raw_get: false               # GET expression directly, not /ensemble (optional)
  expect:
    status: 200                # HTTP status (default 200)
    contains_any: [a, b]       # at least one (case-insensitive)
    contains_all: [a, b]       # all required (case-insensitive)
    not_contains: [err]        # none allowed (case-insensitive)
    min_length: 5
    max_length: 500
    min_results: 3             # newline-separated line count
    max_results: 10
    pattern: "\\d+"            # regex
    judge:
      question: "Yes/no question about the response"
```
