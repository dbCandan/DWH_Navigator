"""The parity harness: the target against the source snapshot, and the source itself.

    python -m tests.parity.harness                    target vs. the committed snapshot
    python -m tests.parity.harness --verify-snapshot  rebuild the snapshot from the source copy,
                                                      require it byte-for-byte, then the target
    python -m tests.parity.harness --write-snapshot   write the snapshot from the source copy
    python -m tests.parity.harness --real             both sides side by side on the real
                                                      dictionary (outside the repository)

The source copy is given by ``DWHNAVIGATOR_PARITY_SOURCE_DIR`` (for example the output of
``git -C <source repo> archive 76e21a3``); its tree digest must be the 76e21a3 tree or the
harness stops. The source side runs in a Python 3.12 environment with the source's
``requirements.lock``: ``DWHNAVIGATOR_PARITY_SOURCE_PYTHON`` names one, otherwise a temporary
one is created. The real dictionary is ``DWHNAVIGATOR_PARITY_DICTIONARY`` and the optional
reference questions ``DWHNAVIGATOR_PARITY_QUESTIONS``; their outputs go to a temporary folder
that is removed at the end, and only counts and output digests are printed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[2]
ROOT = BACKEND.parents[1]
SOURCE_COMMIT = "76e21a3"
SOURCE_TREE = "b499981ef340d5c54ba4ead74ee20b2ac6c75f33"
SOURCE_LIBRARIES = {"openpyxl": "3.1.5", "defusedxml": "0.7.1", "yaml": "6.0.3"}
SNAPSHOT = BACKEND / "tests" / "parity" / "snapshots" / f"source-{SOURCE_COMMIT}"
FIXTURES = BACKEND / "tests" / "fixtures" / "parity"
WORKBOOK = FIXTURES / "sozluk_sentetik.xlsx"
QUESTIONS = FIXTURES / "sorular.yaml"
SEED = ROOT / "schema" / "alembic" / "seed" / "vocabulary"
TERMS = (SEED / "terms.jsonl", FIXTURES / "ek_terim_gruplari.jsonl")
STOPWORDS = SEED / "stopwords.jsonl"
INPUTS = (WORKBOOK, QUESTIONS, *TERMS, STOPWORDS)
HASH_SEEDS = ("0", "4242")


class ParityError(RuntimeError):
    pass


# --------------------------------------------------------------------------- source copy


def git_tree(path: Path) -> str:
    """The git tree digest of a folder, as ``git add -A && git write-tree`` gives it for the
    source's ``.gitattributes`` (``* text=auto eol=lf``, ``*.xlsx binary``): text files are
    hashed with LF line ends, so a ``git archive`` copy (which writes ``*.bat`` with CRLF)
    hashes to the commit's tree."""
    entries = []
    for child in path.iterdir():
        if child.is_dir():
            entries.append((child.name + "/", b"40000 " + child.name.encode(), git_tree(child)))
            continue
        data = child.read_bytes()
        if not child.name.endswith(".xlsx") and b"\0" not in data[:8000]:
            data = data.replace(b"\r\n", b"\n")
        blob = hashlib.sha1(b"blob %d\0" % len(data) + data, usedforsecurity=False).hexdigest()
        mode = b"100755" if os.access(child, os.X_OK) else b"100644"
        entries.append((child.name, mode + b" " + child.name.encode(), blob))
    body = b"".join(head + b"\0" + bytes.fromhex(sha) for _, head, sha in sorted(entries))
    return hashlib.sha1(b"tree %d\0" % len(body) + body, usedforsecurity=False).hexdigest()


def verify_source_copy(path: Path, expected: str = SOURCE_TREE) -> None:
    if not (path / "src" / "vsa").is_dir():
        raise ParityError(f"kaynak kopyası değil: {path}")
    actual = git_tree(path)
    if actual != expected:
        raise ParityError(
            f"kaynak kopyasının ağaç özeti {actual}; beklenen {expected} ({SOURCE_COMMIT}). "
            f"Kopyayı `git archive {SOURCE_COMMIT}` ile yeniden çıkarın."
        )


def source_dir() -> Path:
    raw = os.environ.get("DWHNAVIGATOR_PARITY_SOURCE_DIR", "")
    if not raw:
        raise ParityError("DWHNAVIGATOR_PARITY_SOURCE_DIR verilmedi (kaynak kopyası)")
    path = Path(raw).resolve()
    verify_source_copy(path)
    return path


@contextmanager
def source_python(copy: Path) -> Iterator[str]:
    """A Python 3.12 with the source's locked libraries: the given one, or a temporary one."""
    given = os.environ.get("DWHNAVIGATOR_PARITY_SOURCE_PYTHON", "")
    if given:
        _check_source_python(given)
        yield given
        return
    with tempfile.TemporaryDirectory(prefix="parity-source-venv-") as tmp:
        base = os.environ.get("DWHNAVIGATOR_PARITY_PYTHON312", "python3.12")
        subprocess.run([base, "-m", "venv", tmp], check=True)
        python = str(Path(tmp) / "bin" / "python")
        subprocess.run(
            [
                python,
                "-m",
                "pip",
                "install",
                "--quiet",
                "--require-hashes",
                "-r",
                str(copy / "requirements.lock"),
            ],
            check=True,
        )
        _check_source_python(python)
        yield python


def _check_source_python(python: str) -> None:
    probe = (
        "import json, sys, openpyxl, defusedxml, yaml; print(json.dumps({'python': "
        "sys.version_info[:2], 'openpyxl': openpyxl.__version__, 'defusedxml': "
        "defusedxml.__version__, 'yaml': yaml.__version__}))"
    )
    found = json.loads(
        subprocess.run([python, "-c", probe], check=True, capture_output=True, text=True).stdout
    )
    wanted = {"python": [3, 12], **SOURCE_LIBRARIES}
    if found != wanted:
        raise ParityError(f"kaynak ortamı {found}; beklenen {wanted}")


# --------------------------------------------------------------------------- running sides


def _side_args(workbook: Path, questions: Path, out: Path, full: bool) -> list[str]:
    args = ["--workbook", str(workbook), "--questions", str(questions), "--out", str(out)]
    for path in TERMS:
        args += ["--terms", str(path)]
    args += ["--stopwords", str(STOPWORDS)]
    return [*args, "--full"] if full else args


def start_target(
    out: Path,
    *,
    hash_seed: str,
    workbook: Path = WORKBOOK,
    questions: Path = QUESTIONS,
    full: bool = False,
) -> subprocess.Popen[bytes]:
    env = {**os.environ, "PYTHONHASHSEED": hash_seed, "PYTHONPATH": str(BACKEND)}
    return subprocess.Popen(
        [
            sys.executable,
            "-B",
            "-m",
            "tests.parity.run_target",
            *_side_args(workbook, questions, out, full),
        ],
        cwd=BACKEND,
        env=env,
    )


def run_targets(
    tmp: Path, *, workbook: Path = WORKBOOK, questions: Path = QUESTIONS, full: bool = False
) -> dict[str, Path]:
    """The target once per hash seed, side by side; the output file of each seed."""
    outs = {seed: tmp / f"target-{seed}.jsonl" for seed in HASH_SEEDS}
    running = [
        start_target(out, hash_seed=seed, workbook=workbook, questions=questions, full=full)
        for seed, out in outs.items()
    ]
    if any(p.wait() for p in running):
        raise ParityError("hedef tarafı hata verdi")
    return outs


def run_source(
    copy: Path,
    python: str,
    out: Path,
    *,
    hash_seed: str = "0",
    workbook: Path = WORKBOOK,
    questions: Path = QUESTIONS,
    full: bool = False,
) -> None:
    env = {
        **os.environ,
        "PYTHONHASHSEED": hash_seed,
        "PYTHONDONTWRITEBYTECODE": "1",  # the verified copy stays as it is
        "PYTHONPATH": os.pathsep.join([str(BACKEND), str(copy / "src")]),
    }
    subprocess.run(
        [
            python,
            "-B",
            "-m",
            "tests.parity.run_source",
            *_side_args(workbook, questions, out, full),
        ],
        cwd=BACKEND,
        env=env,
        check=True,
    )
    verify_source_copy(copy)


def target_constants() -> dict[str, Any]:
    """The target's constants from a fresh interpreter, as the source's are read (a module's
    runtime caches start empty)."""
    env = {**os.environ, "PYTHONPATH": str(BACKEND)}
    done = subprocess.run(
        [sys.executable, "-B", "-m", "tests.parity.constants", "target"],
        cwd=BACKEND,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(done.stdout)  # type: ignore[no-any-return]


# Collector module -> its snapshot file: the source's settings schema and word list behaviour
# (admin) and the dictionary explorer (explorer).
COLLECTORS = {
    "admin": "admin.json",
    "explorer": "explorer.json",
}


def source_collect(copy: Path, python: str, collector: str) -> dict[str, Any]:
    """One collector's output on the source side (``tests/parity/<collector>.py``)."""
    env = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": os.pathsep.join([str(BACKEND), str(copy / "src")]),
    }
    done = subprocess.run(
        [python, "-B", "-m", f"tests.parity.{collector}", "source"],
        cwd=BACKEND,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(done.stdout)  # type: ignore[no-any-return]


def source_constants(copy: Path, python: str) -> dict[str, Any]:
    env = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": os.pathsep.join([str(BACKEND), str(copy / "src")]),
    }
    done = subprocess.run(
        [python, "-B", "-m", "tests.parity.constants", "source"],
        cwd=BACKEND,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(done.stdout)  # type: ignore[no-any-return]


# --------------------------------------------------------------------------- comparing


def compare(expected: Path, actual: Path) -> tuple[int, list[str]]:
    """(outputs compared, differences): every output of every question and variant."""
    want = expected.read_text(encoding="utf-8").splitlines()
    got = actual.read_text(encoding="utf-8").splitlines()
    diffs: list[str] = []
    compared = 0
    if len(want) != len(got):
        diffs.append(f"satır sayısı farklı: beklenen {len(want)}, gelen {len(got)}")
    for w_line, g_line in zip(want, got, strict=False):
        if w_line == g_line:
            w = json.loads(w_line)
            compared += len(w.get("outputs", {})) or 1
            continue
        w, g = json.loads(w_line), json.loads(g_line)
        where = f"{w.get('question', w['record'])} / {w.get('variant', '-')}"
        if w["record"] != g["record"] or w.get("question") != g.get("question"):
            diffs.append(f"{where}: kayıt sırası farklı")
            continue
        if w["record"] != "outputs":
            compared += 1
            diffs.append(f"{where}: {w['record']} farklı")
            continue
        for name, value in w["outputs"].items():
            compared += 1
            if g["outputs"].get(name) != value:
                diffs.append(f"{where}: {name} farklı")
    return compared, diffs


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest() -> dict[str, Any]:
    from tests.parity.driver import OUTPUTS, VARIANTS, read_questions

    return {
        "source_commit": SOURCE_COMMIT,
        "source_tree": SOURCE_TREE,
        "source_environment": {"python": "3.12", **SOURCE_LIBRARIES},
        "hash_seed": "0",
        "inputs": {str(p.relative_to(ROOT)): file_digest(p) for p in INPUTS},
        "questions": len(read_questions(QUESTIONS)),
        "variants": list(VARIANTS),
        "outputs": list(OUTPUTS),
    }


def _dump_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


# --------------------------------------------------------------------------- modes


def check_target(tmp: Path) -> int:
    """The target with both hash seeds against the committed snapshot."""
    total = 0
    for seed, out in run_targets(tmp).items():
        compared, diffs = compare(SNAPSHOT / "outputs.jsonl", out)
        label = f"hedef (PYTHONHASHSEED={seed}) / kaynak anlık görüntüsü"
        _report(label, SNAPSHOT / "outputs.jsonl", compared, diffs)
        total += len(diffs)
    return total


def build_snapshot(copy: Path, python: str, folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    run_source(copy, python, folder / "outputs.jsonl", hash_seed="0")
    (folder / "constants.json").write_text(_dump_json(source_constants(copy, python)), "utf-8")
    for collector, name in COLLECTORS.items():
        (folder / name).write_text(_dump_json(source_collect(copy, python, collector)), "utf-8")
    (folder / "manifest.json").write_text(_dump_json(manifest()), "utf-8")


def verify_snapshot(tmp: Path) -> int:
    copy = source_dir()
    with source_python(copy) as python:
        build_snapshot(copy, python, tmp / "snapshot")
        other = tmp / "source-4242.jsonl"
        run_source(copy, python, other, hash_seed="4242")
    problems = 0
    for name in ("outputs.jsonl", "constants.json", *COLLECTORS.values(), "manifest.json"):
        same = (tmp / "snapshot" / name).read_bytes() == (SNAPSHOT / name).read_bytes()
        print(f"anlık görüntü {name}: {'bayt bayt aynı' if same else 'FARKLI'}")
        problems += not same
    compared, diffs = compare(SNAPSHOT / "outputs.jsonl", other)
    _report(
        "kaynak (PYTHONHASHSEED=4242) / anlık görüntü", SNAPSHOT / "outputs.jsonl", compared, diffs
    )
    return problems + len(diffs) + check_target(tmp)


def real_dictionary(tmp: Path) -> int:
    raw = os.environ.get("DWHNAVIGATOR_PARITY_DICTIONARY", "")
    if not raw or not Path(raw).is_file():
        raise ParityError("DWHNAVIGATOR_PARITY_DICTIONARY verilmedi ya da dosya yok")
    questions = Path(os.environ.get("DWHNAVIGATOR_PARITY_QUESTIONS", "") or QUESTIONS)
    copy = source_dir()
    with source_python(copy) as python:
        source_out = tmp / "source.jsonl"
        run_source(copy, python, source_out, workbook=Path(raw), questions=questions, full=True)
    problems = 0
    targets = run_targets(tmp, workbook=Path(raw), questions=questions, full=True)
    for seed, target_out in targets.items():
        compared, diffs = compare(source_out, target_out)
        label = f"gerçek sözlük, hedef (PYTHONHASHSEED={seed}) / kaynak"
        _report(label, source_out, compared, diffs)
        print(f"  kaynak çıktısı sha256:{file_digest(source_out)}")
        print(f"  hedef çıktısı  sha256:{file_digest(target_out)}")
        problems += len(diffs)
    return problems


def _report(label: str, expected: Path, compared: int, diffs: Sequence[str]) -> None:
    from tests.parity.driver import OUTPUTS, VARIANTS

    lines = [json.loads(line) for line in expected.read_text(encoding="utf-8").splitlines()]
    questions = len({rec["question"] for rec in lines if rec["record"] == "outputs"})
    print(
        f"{label}: soru {questions}, çeşit {len(VARIANTS)}, çıktı türü {len(OUTPUTS)}, "
        f"karşılaştırılan {compared}, fark {len(diffs)}"
    )
    for line in diffs[:20]:
        print(f"  {line}")


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--verify-snapshot", action="store_true")
    mode.add_argument("--write-snapshot", action="store_true")
    mode.add_argument("--real", action="store_true")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="parity-") as raw:
        tmp = Path(raw)
        if args.write_snapshot:
            copy = source_dir()
            with source_python(copy) as python:
                build_snapshot(copy, python, SNAPSHOT)
            print(f"anlık görüntü yazıldı: {SNAPSHOT.relative_to(BACKEND)}")
            return 0
        if args.verify_snapshot:
            return 1 if verify_snapshot(tmp) else 0
        if args.real:
            return 1 if real_dictionary(tmp) else 0
        return 1 if check_target(tmp) else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ParityError as exc:
        print(f"fark düzeneği durdu: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
