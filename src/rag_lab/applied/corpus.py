from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from rag_lab.ingest import parse_front_matter, split_pages


SCHEMA_VERSION = "1.0"
CLASSIFICATIONS = ("public", "internal", "restricted")
CLEARANCE_LEVEL = {name: level for level, name in enumerate(CLASSIFICATIONS)}
SOURCE_POLICIES = {"synthetic", "public_licensed", "user_authorized_local"}
TASK_TYPES = {"question_answering", "document_comparison", "safety"}
DOCUMENT_FIELDS = {
    "document_id",
    "title",
    "source",
    "document_type",
    "organization",
    "project",
    "revision",
    "published_date",
    "language",
    "classification",
    "allowed_groups",
    "license_or_terms",
    "sha256",
    "supersedes_document_id",
    "page_count",
}
GOLD_FIELDS = {
    "case_id",
    "task_type",
    "question_or_field",
    "expected_document_ids",
    "expected_pages",
    "required_values",
    "required_units",
    "expected_answerable",
    "principal_groups",
    "principal_clearance",
    "allowed_result_document_ids",
    "access_boundary",
}


@dataclass(frozen=True)
class A0Summary:
    dataset_id: str
    document_count: int
    page_count: int
    evaluation_case_count: int
    unanswerable_case_count: int
    access_boundary_case_count: int


class A0ValidationError(ValueError):
    """Raised when the checked-in applied-course fixtures are inconsistent."""


def load_manifest(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise A0ValidationError(f"manifestはJSON objectである必要があります: {path}")
    return data


def load_gold_cases(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                case = json.loads(line)
            except json.JSONDecodeError as exc:
                raise A0ValidationError(
                    f"gold JSONLの{line_number}行目を解釈できません: {exc.msg}"
                ) from exc
            if not isinstance(case, dict):
                raise A0ValidationError(
                    f"gold JSONLの{line_number}行目はJSON objectではありません"
                )
            cases.append(case)
    return cases


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(64 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def dataset_sha256(documents: list[dict[str, Any]]) -> str:
    """Hash the sorted document-id/checksum pairs, independent of local paths."""

    digest = hashlib.sha256()
    pairs = sorted(
        (str(document.get("document_id", "")), str(document.get("sha256", "")))
        for document in documents
    )
    for document_id, checksum in pairs:
        digest.update(f"{document_id}:{checksum}\n".encode())
    return digest.hexdigest()


def _is_list_of_strings(value: Any) -> bool:
    return isinstance(value, list) and all(
        isinstance(item, str) and bool(item) for item in value
    )


def _check_iso_date(value: Any, label: str, errors: list[str]) -> None:
    if not isinstance(value, str):
        errors.append(f"{label}は日付文字列である必要があります")
        return
    try:
        date.fromisoformat(value)
    except ValueError:
        errors.append(f"{label}はYYYY-MM-DD形式ではありません: {value}")


def _safe_source_path(corpus_root: Path, source: Any) -> Path | None:
    if not isinstance(source, str) or not source:
        return None
    pure_path = PurePosixPath(source)
    if pure_path.is_absolute() or ".." in pure_path.parts:
        return None
    candidate = (corpus_root / pure_path).resolve()
    if not candidate.is_relative_to(corpus_root.resolve()):
        return None
    return candidate


def _validate_document(
    document: Any,
    corpus_root: Path,
    errors: list[str],
) -> int:
    if not isinstance(document, dict):
        errors.append("manifest documentsの要素はobjectである必要があります")
        return 0

    document_id = document.get("document_id", "<unknown>")
    missing = sorted(DOCUMENT_FIELDS - document.keys())
    extra = sorted(document.keys() - DOCUMENT_FIELDS)
    if missing:
        errors.append(f"{document_id}: metadata必須項目が不足しています: {missing}")
    if extra:
        errors.append(f"{document_id}: 未定義のmetadata項目があります: {extra}")

    classification = document.get("classification")
    groups = document.get("allowed_groups")
    if classification not in CLASSIFICATIONS:
        errors.append(f"{document_id}: classificationが不正です: {classification}")
    if not _is_list_of_strings(groups) and groups != []:
        errors.append(f"{document_id}: allowed_groupsは文字列配列である必要があります")
    elif len(groups) != len(set(groups)):
        errors.append(f"{document_id}: allowed_groupsに重複があります")
    elif classification == "public" and groups:
        errors.append(f"{document_id}: public文書のallowed_groupsは空にしてください")
    elif classification in {"internal", "restricted"} and not groups:
        errors.append(f"{document_id}: 非公開文書にはallowed_groupsが必要です")

    _check_iso_date(document.get("published_date"), f"{document_id}.published_date", errors)
    checksum = document.get("sha256")
    if (
        not isinstance(checksum, str)
        or len(checksum) != 64
        or any(character not in "0123456789abcdef" for character in checksum)
    ):
        errors.append(f"{document_id}: sha256は64桁である必要があります")

    source_path = _safe_source_path(corpus_root, document.get("source"))
    if source_path is None:
        errors.append(f"{document_id}: sourceは安全な相対パスである必要があります")
        return 0
    if not source_path.is_file():
        errors.append(f"{document_id}: sourceが見つかりません: {document.get('source')}")
        return 0
    if isinstance(checksum, str) and file_sha256(source_path) != checksum:
        errors.append(f"{document_id}: sourceのSHA-256がmanifestと一致しません")

    raw = source_path.read_text(encoding="utf-8")
    front_matter, body = parse_front_matter(raw)
    for key in (
        "document_id",
        "title",
        "source",
        "document_type",
        "organization",
        "project",
        "revision",
        "published_date",
        "language",
        "classification",
        "license_or_terms",
    ):
        if front_matter.get(key) != str(document.get(key)):
            errors.append(f"{document_id}: front matterの{key}がmanifestと一致しません")
    expected_groups = (
        f"[{', '.join(groups)}]" if isinstance(groups, list) else "<invalid>"
    )
    if front_matter.get("allowed_groups") != expected_groups:
        errors.append(
            f"{document_id}: front matterのallowed_groupsがmanifestと一致しません"
        )
    supersedes = document.get("supersedes_document_id")
    expected_supersedes = "null" if supersedes is None else str(supersedes)
    if front_matter.get("supersedes_document_id") != expected_supersedes:
        errors.append(
            f"{document_id}: front matterのsupersedes_document_idがmanifestと一致しません"
        )

    pages = split_pages(body)
    page_numbers = [page for page, _ in pages]
    expected_page_count = document.get("page_count")
    if page_numbers != list(range(1, len(page_numbers) + 1)):
        errors.append(f"{document_id}: page markerは1から連番にしてください")
    if expected_page_count != len(pages):
        errors.append(
            f"{document_id}: page_count={expected_page_count}ですが実際は{len(pages)}です"
        )
    return len(pages)


def _validate_revision_graph(documents: list[dict[str, Any]], errors: list[str]) -> None:
    document_ids = {
        document.get("document_id") for document in documents if isinstance(document, dict)
    }
    links = {
        document.get("document_id"): document.get("supersedes_document_id")
        for document in documents
        if isinstance(document, dict)
    }
    for document_id, previous_id in links.items():
        if previous_id is not None and previous_id not in document_ids:
            errors.append(f"{document_id}: supersedes対象が存在しません: {previous_id}")
        seen: set[Any] = set()
        current = document_id
        while current is not None:
            if current in seen:
                errors.append(f"{document_id}: 改訂関係が循環しています")
                break
            seen.add(current)
            current = links.get(current)


def _fixture_can_read(document: dict[str, Any], clearance: Any, groups: Any) -> bool:
    classification = document.get("classification")
    if classification == "public":
        return True
    if clearance not in CLEARANCE_LEVEL or classification not in CLEARANCE_LEVEL:
        return False
    allowed_groups = document.get("allowed_groups")
    if not _is_list_of_strings(groups) or not _is_list_of_strings(allowed_groups):
        return False
    return (
        CLEARANCE_LEVEL[clearance] >= CLEARANCE_LEVEL[classification]
        and bool(set(groups) & set(allowed_groups))
    )


def _validate_gold_cases(
    cases: list[dict[str, Any]],
    documents_by_id: dict[str, dict[str, Any]],
    pages_by_document_id: dict[str, dict[int, str]],
    errors: list[str],
) -> tuple[int, int]:
    seen_ids: set[Any] = set()
    unanswerable_count = 0
    boundary_count = 0

    for case in cases:
        case_id = case.get("case_id", "<unknown>")
        missing = sorted(GOLD_FIELDS - case.keys())
        extra = sorted(case.keys() - GOLD_FIELDS)
        if missing:
            errors.append(f"{case_id}: gold必須項目が不足しています: {missing}")
        if extra:
            errors.append(f"{case_id}: goldに未定義項目があります: {extra}")
        if case_id in seen_ids:
            errors.append(f"gold case_idが重複しています: {case_id}")
        seen_ids.add(case_id)

        if not isinstance(case_id, str) or not case_id:
            errors.append("gold case_idは空でない文字列である必要があります")
        if not isinstance(case.get("question_or_field"), str) or not case.get(
            "question_or_field"
        ):
            errors.append(f"{case_id}: question_or_fieldが必要です")
        if case.get("task_type") not in TASK_TYPES:
            errors.append(f"{case_id}: task_typeが不正です")
        if case.get("principal_clearance") not in CLEARANCE_LEVEL:
            errors.append(f"{case_id}: principal_clearanceが不正です")
        for field in (
            "expected_document_ids",
            "required_values",
            "required_units",
            "principal_groups",
            "allowed_result_document_ids",
        ):
            if not _is_list_of_strings(case.get(field)) and case.get(field) != []:
                errors.append(f"{case_id}: {field}は文字列配列である必要があります")
        pages = case.get("expected_pages")
        if not isinstance(pages, list) or not all(
            isinstance(page, int) and page > 0 for page in pages
        ):
            errors.append(f"{case_id}: expected_pagesは正の整数配列である必要があります")
        expected_pages = (
            pages
            if isinstance(pages, list)
            and all(isinstance(page, int) and page > 0 for page in pages)
            else []
        )
        required_values_value = case.get("required_values", [])
        required_values = (
            required_values_value
            if _is_list_of_strings(required_values_value)
            else []
        )
        required_units_value = case.get("required_units", [])
        required_units = (
            required_units_value if _is_list_of_strings(required_units_value) else []
        )

        expected_ids_value = case.get("expected_document_ids", [])
        expected_ids = (
            expected_ids_value if _is_list_of_strings(expected_ids_value) else []
        )
        unknown_ids = sorted(set(expected_ids) - documents_by_id.keys())
        if unknown_ids:
            errors.append(f"{case_id}: 未知のexpected_document_idsがあります: {unknown_ids}")

        expected_allowed = sorted(
            document_id
            for document_id in expected_ids
            if document_id in documents_by_id
            and _fixture_can_read(
                documents_by_id[document_id],
                case.get("principal_clearance"),
                case.get("principal_groups"),
            )
        )
        actual_allowed_value = case.get("allowed_result_document_ids", [])
        actual_allowed = sorted(
            actual_allowed_value if _is_list_of_strings(actual_allowed_value) else []
        )
        if actual_allowed != expected_allowed:
            errors.append(
                f"{case_id}: allowed_result_document_idsがfixture policyと一致しません"
            )

        answerable = case.get("expected_answerable")
        if not isinstance(answerable, bool):
            errors.append(f"{case_id}: expected_answerableはbooleanである必要があります")
        elif answerable:
            if not actual_allowed:
                errors.append(f"{case_id}: 回答可能caseには許可済み根拠文書が必要です")
            if not expected_pages or not required_values:
                errors.append(f"{case_id}: 回答可能caseにはページと必須値が必要です")
            evidence_parts: list[str] = []
            for document_id in expected_ids:
                document_pages = pages_by_document_id.get(document_id, {})
                for page in expected_pages:
                    if page in document_pages:
                        evidence_parts.append(document_pages[page])
            evidence = "\n".join(evidence_parts)
            for expected_text in required_values + required_units:
                if expected_text not in evidence:
                    errors.append(
                        f"{case_id}: 期待値が指定ページの根拠にありません: {expected_text}"
                    )
        else:
            unanswerable_count += 1
            if actual_allowed:
                errors.append(f"{case_id}: 回答不能caseに許可済み結果があります")
            if expected_pages or required_values or required_units:
                errors.append(f"{case_id}: 回答不能caseは期待値を公開しないでください")

        if case.get("access_boundary") is True:
            boundary_count += 1
        elif case.get("access_boundary") is not False:
            errors.append(f"{case_id}: access_boundaryはbooleanである必要があります")

    return unanswerable_count, boundary_count


def validate_a0_dataset(applied_root: Path) -> A0Summary:
    """Validate the checked-in A0 corpus without network or optional dependencies."""

    applied_root = applied_root.resolve()
    corpus_root = applied_root / "corpus"
    errors: list[str] = []

    for schema_name in (
        "corpus_manifest.schema.json",
        "research_document_metadata.schema.json",
        "gold_case.schema.json",
    ):
        schema_path = applied_root / "schemas" / schema_name
        try:
            schema = load_manifest(schema_path)
        except (OSError, json.JSONDecodeError, A0ValidationError) as exc:
            errors.append(f"schemaを読み込めません: {schema_name}: {exc}")
            continue
        if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            errors.append(f"{schema_name}: JSON Schema draft 2020-12を指定してください")

    try:
        manifest = load_manifest(corpus_root / "manifest.json")
    except (OSError, json.JSONDecodeError, A0ValidationError) as exc:
        raise A0ValidationError(f"manifestを読み込めません: {exc}") from exc
    try:
        cases = load_gold_cases(applied_root / "evaluation" / "gold.jsonl")
    except (OSError, A0ValidationError) as exc:
        raise A0ValidationError(f"gold casesを読み込めません: {exc}") from exc

    documents = manifest.get("documents")
    if not isinstance(documents, list):
        errors.append("manifest.documentsは配列である必要があります")
        documents = []
    if manifest.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_versionは{SCHEMA_VERSION}である必要があります")
    if manifest.get("source_policy") not in SOURCE_POLICIES:
        errors.append("source_policyが不正です")
    if manifest.get("source_policy") != "synthetic":
        errors.append("付属A0コーパスはsyntheticである必要があります")
    if manifest.get("document_count") != len(documents):
        errors.append("document_countとdocumentsの件数が一致しません")
    if not 6 <= len(documents) <= 10:
        errors.append("A0コーパスは6〜10文書で構成してください")
    try:
        datetime.fromisoformat(str(manifest.get("created_at")))
    except ValueError:
        errors.append("created_atはISO 8601 date-timeである必要があります")

    document_ids = [
        document.get("document_id") for document in documents if isinstance(document, dict)
    ]
    if len(document_ids) != len(set(document_ids)):
        errors.append("manifestのdocument_idが重複しています")

    document_objects = [document for document in documents if isinstance(document, dict)]
    page_count = sum(
        _validate_document(document, corpus_root, errors) for document in documents
    )
    if not 30 <= page_count <= 60:
        errors.append(f"A0コーパスは30〜60ページ相当が必要です: {page_count}")
    _validate_revision_graph(document_objects, errors)
    if (
        sum(bool(document.get("supersedes_document_id")) for document in document_objects)
        < 2
    ):
        errors.append("2件以上の改訂関係が必要です")

    table_document_count = 0
    for document in document_objects:
        source_path = _safe_source_path(corpus_root, document.get("source"))
        if source_path and source_path.is_file() and "| ---" in source_path.read_text(
            encoding="utf-8"
        ):
            table_document_count += 1
    if table_document_count < 2:
        errors.append("表を含む文書が2件以上必要です")

    computed_dataset_hash = dataset_sha256(document_objects)
    if manifest.get("dataset_sha256") != computed_dataset_hash:
        errors.append("dataset_sha256が文書checksum一覧と一致しません")

    documents_by_id = {
        document["document_id"]: document
        for document in document_objects
        if isinstance(document.get("document_id"), str)
    }
    pages_by_document_id: dict[str, dict[int, str]] = {}
    for document_id, document in documents_by_id.items():
        source_path = _safe_source_path(corpus_root, document.get("source"))
        if source_path and source_path.is_file():
            _, body = parse_front_matter(source_path.read_text(encoding="utf-8"))
            pages_by_document_id[document_id] = dict(split_pages(body))
    unanswerable_count, boundary_count = _validate_gold_cases(
        cases, documents_by_id, pages_by_document_id, errors
    )
    if len(cases) < 20:
        errors.append("評価caseは20件以上必要です")
    if cases and unanswerable_count / len(cases) < 0.2:
        errors.append("回答不能caseは全体の20%以上必要です")
    if boundary_count < 5:
        errors.append("権限境界caseは5件以上必要です")

    if errors:
        raise A0ValidationError("A0 dataset validation failed:\n- " + "\n- ".join(errors))

    return A0Summary(
        dataset_id=str(manifest.get("dataset_id")),
        document_count=len(documents),
        page_count=page_count,
        evaluation_case_count=len(cases),
        unanswerable_case_count=unanswerable_count,
        access_boundary_case_count=boundary_count,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Milestone A0の合成コーパスを検査します")
    parser.add_argument(
        "applied_root",
        nargs="?",
        type=Path,
        default=Path("data/applied"),
        help="corpus、evaluation、schemasを含むディレクトリ",
    )
    args = parser.parse_args(argv)
    try:
        summary = validate_a0_dataset(args.applied_root)
    except A0ValidationError as exc:
        parser.exit(1, f"{exc}\n")
    print(
        "A0 dataset is valid: "
        f"{summary.document_count} documents, "
        f"{summary.page_count} pages, "
        f"{summary.evaluation_case_count} cases"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
