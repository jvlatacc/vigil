#!/usr/bin/env python3
"""Generate the Vigil v1 API client (dart-dio) from the frozen contract.

Input (canonical, owned by the backend):
  core/api/v1/contract.snapshot.json   the frozen /api/v1 OpenAPI 3.1 document,
                                       CI-drift-checked against the mounted routes

Output (generated, committed under api/v1/):
  api/v1/  a pure-Dart package `vigil_api_v1` — built_value models, one API
           class per tag, serializers, plus the build_runner `*.g.dart` files

The generator is pinned (OPENAPI_GENERATOR_VERSION) and the jar is cached in
~/.cache/openapi-generator, so builds reproduce bit-for-bit from the snapshot.

Requires on PATH (or via FLUTTER_ROOT / JAVA_HOME):
  java    any JRE 17+ — runs the openapi-generator jar
  dart    the Dart SDK that ships inside the Flutter SDK

Usage:
  python3 tool/generate_api_client.py            regenerate into api/v1/
  python3 tool/generate_api_client.py --check    regenerate to a temp dir and
                                                 diff against the committed
                                                 output — CI-friendly drift
                                                 gate, exit 1 on any drift

Not covered by the diff in --check (derived, verified by analyze/test instead):
  api/v1/pubspec.lock    resolved by `pub get`, machine-specific
  api/v1/**.g.dart       produced by build_runner from the same models
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

# Pinned — bump deliberately, regenerate, and commit the new output.
OPENAPI_GENERATOR_VERSION = "7.26.0"
JAR_URL = (
    "https://repo1.maven.org/maven2/org/openapitools/openapi-generator-cli/"
    f"{OPENAPI_GENERATOR_VERSION}/openapi-generator-cli-{OPENAPI_GENERATOR_VERSION}.jar"
)

FLUTTER_CLIENT = Path(__file__).resolve().parents[1]
REPO_ROOT = FLUTTER_CLIENT.parents[1]
SNAPSHOT = REPO_ROOT / "core" / "api" / "v1" / "contract.snapshot.json"
OUT_DIR = FLUTTER_CLIENT / "api" / "v1"
JAR_CACHE = Path(os.environ.get("HOME", "/tmp")) / ".cache" / "openapi-generator"

# The snapshot carries no `info`/`servers` blocks (it is a paths+components
# extract). openapi-generator requires them, so a normalized copy is fed to
# the generator; neither value reaches the app — the client passes its own
# Dio/baseUrl at construction.
NORMALIZED_INFO = {
    "title": "Vigil API v1",
    "version": "1.0.0",
    "description": "Frozen /api/v1 surface of the Vigil SOC API.",
}
NORMALIZED_SERVERS = [{"url": "https://vigil.example.com"}]

GENERATOR_PROPS = ",".join(
    [
        "pubName=vigil_api_v1",
        "pubLibrary=vigil_api_v1",
        "pubVersion=1.0.0",
        "pubDescription=Generated Dart client for Vigil's frozen /api/v1 contract. Do not edit by hand.",
        "pubHomepage=https://github.com/jvlatacc/vigil",
    ]
)

# Derived/ephemeral artifacts excluded from the --check diff.
CHECK_EXCLUDES = {"pubspec.lock", ".dart_tool", "build", ".openapi-generator"}


def find_tool(name: str, env_var: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    root = os.environ.get(env_var)
    if root:
        candidate = Path(root) / "bin" / name
        if candidate.exists():
            return str(candidate)
    sys.exit(f"error: {name} not found on PATH and {env_var} is not set")


def fetch_jar() -> Path:
    JAR_CACHE.mkdir(parents=True, exist_ok=True)
    jar = JAR_CACHE / f"openapi-generator-cli-{OPENAPI_GENERATOR_VERSION}.jar"
    if not jar.exists():
        print(f"downloading {JAR_URL}")
        urllib.request.urlretrieve(JAR_URL, jar)
    return jar


def normalize_snapshot(temp_dir: Path) -> Path:
    doc = json.loads(SNAPSHOT.read_text())
    doc["info"] = NORMALIZED_INFO
    doc["servers"] = NORMALIZED_SERVERS
    normalized = temp_dir / "vigil-v1-openapi.json"
    normalized.write_text(json.dumps(doc, indent=2))
    return normalized


# dart-dio 7.26.0 emits `import 'package:<pubName>/src/model/any_of.dart'` for
# models with anyOf properties but never writes that support file (fixed later
# upstream to import the one_of package). The one_of package — already a
# generated dependency — provides AnyOf/AnyOfDynamic, so the broken local
# import is rewritten to it. Deterministic; applied on both generate and check.
ANY_OF_IMPORT_FIX = (
    "import 'package:vigil_api_v1/src/model/any_of.dart';",
    "import 'package:one_of/any_of.dart';",
)


snake = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def _to_snake(name: str) -> str:
    return snake.sub("_", name).lower()


def _nullable_fields(model_text: str) -> dict[str, str]:
    """field name -> declared type, for nullable object getters only."""
    return {
        name: type_
        for type_, name in re.findall(
            r"^\s+([A-Z]\w*)\?\s+get\s+(\w+);", model_text, re.M
        )
    }


def _has_builder(model_dir: Path, type_: str) -> bool:
    """True when `type_` is a generated built_value model (so `.toBuilder()`
    exists). AnyOf and one_of support types have no model file — the check
    must not depend on build_runner having run (it hasn't in --check mode)."""
    return (model_dir / f"{_to_snake(type_)}.dart").exists()


def fix_serializer_call_sites(out: Path) -> None:
    """Patch dart-dio 7.26.0 serializer bodies that don't compile.

    For a nullable object field the generated deserializer calls
    `result.<field>.replace(valueDes)` (AnyOf-typed — the builder holds the
    plain value) or `result.<field> = valueDes` (built_value-typed — the
    builder's setter takes `<T>Builder?`). Neither compiles under the strict
    analyzer: the receiver is nullable / the types don't line up. Both are
    rewritten to the builder-correct form; deterministic, applied on both
    generate and check so the drift gate stays honest.
    """
    model_dir = out / "lib" / "src" / "model"
    for path in sorted(model_dir.glob("*.dart")):
        if path.name.endswith(".g.dart"):
            continue
        text = path.read_text()
        fields = _nullable_fields(text)
        patched = text
        for name, type_ in fields.items():
            if type_ == "AnyOf":
                # Builder carries the plain AnyOf? value — assign directly.
                patched = patched.replace(
                    f"result.{name}.replace(valueDes);",
                    f"result.{name} = valueDes;",
                )
            elif _has_builder(model_dir, type_):
                # Builder's setter wants <T>Builder? — hand it the value's
                # builder.
                patched = patched.replace(
                    f"result.{name} = valueDes;",
                    f"result.{name} = valueDes.toBuilder();",
                )
        if patched != text:
            path.write_text(patched)



# The generator emits its own analysis_options.yaml; the project's curated
# generated-code policy replaces it on both the generate and check paths so
# the drift gate compares like against like.
ANALYSIS_OPTIONS = """\
# Analysis policy for the GENERATED api/v1 package (vigil_api_v1).
#
# Everything under lib/ is emitted by `tool/generate_api_client.py` — the
# app's own analysis options never apply here. The generator's output carries
# a handful of benign lints (model imports some API classes don't use, one
# raw-generic in the shared serializer registry); they are ignored as a
# generated-code policy so `flutter analyze` from the app stays clean and the
# drift gate (`generate_api_client.py --check`) stays the source of truth for
# this package. Real diagnostics (errors) are NOT downgraded — the generate
# script patches the generator's non-compiling serializer bodies instead.
analyzer:
  language:
    strict-inference: true
    strict-raw-types: true
    strict-casts: false
  exclude:
    - test/*.dart
  errors:
    deprecated_member_use_from_same_package: ignore
    unused_import: ignore
    duplicate_import: ignore
    strict_raw_type: ignore
"""


def fix_analysis_options(out: Path) -> None:
    (out / "analysis_options.yaml").write_text(ANALYSIS_OPTIONS)


def fix_any_of_imports(out: Path) -> None:
    for path in sorted((out / "lib").rglob("*.dart")):
        text = path.read_text()
        broken, fixed = ANY_OF_IMPORT_FIX
        if broken in text:
            path.write_text(text.replace(broken, fixed))


def run_generator(jar: Path, spec: Path, out: Path) -> None:
    java = find_tool("java", "JAVA_HOME")
    subprocess.run(
        [
            java,
            "-jar",
            str(jar),
            "generate",
            "-g",
            "dart-dio",
            "-i",
            str(spec),
            "-o",
            str(out),
            f"--additional-properties={GENERATOR_PROPS}",
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def post_process(out: Path) -> None:
    """Resolve deps and emit the built_value `*.g.dart` files."""
    dart = find_tool("dart", "FLUTTER_ROOT")
    subprocess.run(
        [dart, "pub", "get"],
        cwd=out,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [dart, "run", "build_runner", "build", "--delete-conflicting-outputs"],
        cwd=out,
        check=True,
        capture_output=True,
        text=True,
    )


def emitted_files(root: Path) -> dict[str, bytes]:
    """Every generator-emitted file, as relative path -> bytes."""
    files: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if any(rel == e or rel.startswith(e + "/") for e in CHECK_EXCLUDES):
            continue
        if rel.endswith(".g.dart"):
            continue  # build_runner output — derived, excluded per docstring
        files[rel] = path.read_bytes()
    return files


def check(jar: Path) -> int:
    dart = find_tool("dart", "FLUTTER_ROOT")
    with tempfile.TemporaryDirectory() as td:
        temp = Path(td)
        spec = normalize_snapshot(temp)
        fresh = temp / "fresh"
        run_generator(jar, spec, fresh)
        fix_any_of_imports(fresh)
        fix_serializer_call_sites(fresh)
        fix_analysis_options(fresh)
        # pub get only materializes pubspec.lock/.dart_tool — both excluded
        # from the diff; run it so the fresh tree is a valid package.
        subprocess.run(
            [dart, "pub", "get"],
            cwd=fresh,
            check=True,
            capture_output=True,
            text=True,
        )
        fresh_files = emitted_files(fresh)
        committed_files = emitted_files(OUT_DIR)

    drifted = sorted(
        rel
        for rel in set(fresh_files) | set(committed_files)
        if fresh_files.get(rel) != committed_files.get(rel)
    )
    if drifted:
        print(f"api/v1 drift against {SNAPSHOT} — regenerate and commit:")
        for rel in drifted:
            state = "missing" if rel not in committed_files else (
                "extra" if rel not in fresh_files else "changed"
            )
            print(f"  {state}: {rel}")
        return 1
    print("api/v1 is in sync with the contract snapshot")
    return 0


def regenerate(jar: Path) -> None:
    with tempfile.TemporaryDirectory() as td:
        spec = normalize_snapshot(Path(td))
        run_generator(jar, spec, OUT_DIR)
    fix_any_of_imports(OUT_DIR)
    fix_serializer_call_sites(OUT_DIR)
    fix_analysis_options(OUT_DIR)
    post_process(OUT_DIR)
    print(f"regenerated {OUT_DIR} from {SNAPSHOT}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify committed output matches the snapshot (CI drift gate)",
    )
    args = parser.parse_args()

    if not SNAPSHOT.exists():
        sys.exit(f"error: snapshot not found at {SNAPSHOT}")
    jar = fetch_jar()
    return check(jar) if args.check else (regenerate(jar), 0)[1]


if __name__ == "__main__":
    sys.exit(main())
