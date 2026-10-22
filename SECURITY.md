# Security

Please report security problems privately through
[GitHub's private vulnerability reporting](https://github.com/Abtektas/param-lineage/security/advisories/new),
not in a public issue.

- The command and the page read parameter files. The page makes no network
  requests. A file that makes the page run script or insert markup, or makes
  the command crash, hang or write outside its output, is a security problem
  worth reporting.
- Extracting a release runs PX4's own generator scripts from that release's
  source. Only extract from the official PX4 repository.

A wrong or missing fact in the data is not a security problem. Please open a
normal issue for it.

Only the latest release is supported.
