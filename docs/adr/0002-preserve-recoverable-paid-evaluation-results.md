# Preserve recoverable results when a paid Evaluation aborts

Pre-spend planning and authentication failures raise without producing a Report, while normal
Benchmark and provider failures are represented in a returned Report. If an infrastructure or
protocol failure aborts a multi-Candidate Evaluation after paid work begins, the Client raises an
`ExecutionError` carrying an optional Partial Report with every recoverable completed Candidate
Result. Returning that Partial Report as though the Evaluation completed would hide missing
Candidates; discarding it would lose paid audit evidence.
