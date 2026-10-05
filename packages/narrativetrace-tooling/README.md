# narrativetrace-tooling

The free-tier tooling library, standard library only and zero network:

- **The doctor** — every check `narrativetrace doctor` runs, as pure functions over one read-only
  snapshot of a project (`narrativetrace_tooling.doctor`). The snapshot is built by the
  `narrativetrace` distribution, which owns the console script; the checks, the report and both
  renderings live here.
- **The installer** — the carrier reader, the project snapshot, the pure planners, the one writer
  and the renderers behind `narrativetrace init` / `narrativetrace uninstall`
  (`narrativetrace_tooling.init`).

Nothing here links against the runtime it diagnoses. This library never imports `narrativetrace`:
it reads a project's configuration, source tree and rendered output as text, and it reads a skills
carrier through `importlib.metadata`, which resolves an installed distribution's own files without
importing it. The `narrativetrace` console script therefore sits *above* this library and depends on
it, exactly as the Java port's CLI and Gradle plugin both embed `narrativetrace-tooling` and neither
depends on the other.

Reached through the `narrativetrace` console script, not imported by consumers.
