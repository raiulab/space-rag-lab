from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from .embeddings import HashEmbeddingModel, build_index, load_index
from .evaluation import evaluate_pipeline, write_report
from .generation import make_generator
from .ingest import collect_chunks, load_chunks, write_chunks
from .models import SearchResult
from .pipeline import RAGPipeline
from .retrieval import Retriever


DEFAULT_RAW = Path("data/raw")
DEFAULT_CHUNKS = Path("data/processed/chunks.jsonl")
DEFAULT_INDEX = Path("data/index/index.jsonl")
DEFAULT_GOLD = Path("data/evaluation/gold.jsonl")
DEFAULT_PROMPT = Path("prompts/answer_v2_grounded.txt")
DEFAULT_REPORT = Path("reports/evaluation.json")


def _print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def _build_pipeline(args: argparse.Namespace) -> RAGPipeline:
    return RAGPipeline(
        retriever=Retriever.from_path(args.index),
        generator=make_generator(args.generator),
        prompt_path=args.prompt,
        search_mode=args.mode,
        top_k=args.top_k,
    )


def command_ingest(args: argparse.Namespace) -> None:
    chunks = collect_chunks(args.raw_dir, chunk_size=args.chunk_size)
    if not chunks:
        raise SystemExit(f"文書が見つかりません: {args.raw_dir}")
    write_chunks(chunks, args.output)
    _print_json(
        {
            "status": "ok",
            "documents": len({chunk.document_id for chunk in chunks}),
            "chunks": len(chunks),
            "output": str(args.output),
        }
    )


def command_index(args: argparse.Namespace) -> None:
    chunks = load_chunks(args.chunks)
    count = build_index(chunks, args.output, HashEmbeddingModel(args.dimension))
    _print_json(
        {
            "status": "ok",
            "vectors": count,
            "dimension": args.dimension,
            "output": str(args.output),
        }
    )


def command_search(args: argparse.Namespace) -> None:
    results = Retriever.from_path(args.index).search(
        args.query, top_k=args.top_k, mode=args.mode
    )
    _print_json([result.to_dict() for result in results])


def command_ask(args: argparse.Namespace) -> None:
    _print_json(_build_pipeline(args).ask(args.question).to_dict())


def command_summarize(args: argparse.Namespace) -> None:
    rows = load_index(args.index)
    document_rows = [row for row in rows if row[0].document_id == args.document_id]
    if not document_rows:
        available = sorted({chunk.document_id for chunk, _ in rows})
        message = (
            f"document_id が見つかりません: {args.document_id}; "
            f"候補: {', '.join(available)}"
        )
        raise SystemExit(message)
    results = [
        SearchResult(chunk=chunk, score=1.0, rank=rank, method="document")
        for rank, (chunk, _) in enumerate(document_rows, start=1)
    ]
    prompt = args.prompt.read_text(encoding="utf-8")
    question = (
        "この文書の目的、重要な数値、結論を"
        "3点以内で要約してください。"
    )
    text, answerable = make_generator(args.generator).generate(question, results, prompt)
    _print_json(
        {
            "document_id": args.document_id,
            "summary": text,
            "answerable": answerable,
            "source_chunks": [result.chunk.chunk_id for result in results],
        }
    )


def command_evaluate(args: argparse.Namespace) -> None:
    report = evaluate_pipeline(_build_pipeline(args), args.gold)
    write_report(report, args.report)
    _print_json({"summary": report["summary"], "report": str(args.report)})


def command_all(args: argparse.Namespace) -> None:
    chunks = collect_chunks(args.raw_dir, chunk_size=args.chunk_size)
    if not chunks:
        raise SystemExit(f"文書が見つかりません: {args.raw_dir}")
    write_chunks(chunks, args.chunks)
    build_index(chunks, args.index, HashEmbeddingModel(args.dimension))
    pipeline = RAGPipeline(
        Retriever.from_path(args.index),
        make_generator(args.generator),
        args.prompt,
        search_mode=args.mode,
        top_k=args.top_k,
    )
    report = evaluate_pipeline(pipeline, args.gold)
    write_report(report, args.report)
    _print_json(
        {
            "status": "ok",
            "documents": len({chunk.document_id for chunk in chunks}),
            "chunks": len(chunks),
            "index": str(args.index),
            "evaluation": report["summary"],
            "report": str(args.report),
        }
    )


def _add_pipeline_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--generator", choices=["extractive", "bedrock"], default="extractive")
    parser.add_argument("--prompt", type=Path, default=DEFAULT_PROMPT)
    parser.add_argument("--mode", choices=["dense", "bm25", "hybrid"], default="hybrid")
    parser.add_argument("--top-k", type=int, default=5)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rag-lab",
        description="宇宙技術レポートで学ぶ、Notebookを使わないRAG実習",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest = subparsers.add_parser("ingest", help="生文書をチャンクへ変換")
    ingest.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW)
    ingest.add_argument("--output", type=Path, default=DEFAULT_CHUNKS)
    ingest.add_argument("--chunk-size", type=int, default=650)
    ingest.set_defaults(func=command_ingest)

    index = subparsers.add_parser("index", help="Embeddingと索引を生成")
    index.add_argument("--chunks", type=Path, default=DEFAULT_CHUNKS)
    index.add_argument("--output", type=Path, default=DEFAULT_INDEX)
    index.add_argument("--dimension", type=int, default=384)
    index.set_defaults(func=command_index)

    search = subparsers.add_parser("search", help="索引を検索")
    search.add_argument("query")
    search.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    search.add_argument("--mode", choices=["dense", "bm25", "hybrid"], default="hybrid")
    search.add_argument("--top-k", type=int, default=5)
    search.set_defaults(func=command_search)

    ask = subparsers.add_parser("ask", help="根拠付き質問応答")
    ask.add_argument("question")
    _add_pipeline_options(ask)
    ask.set_defaults(func=command_ask)

    summarize = subparsers.add_parser("summarize", help="1文書を要約")
    summarize.add_argument("document_id")
    summarize.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    summarize.add_argument(
        "--generator", choices=["extractive", "bedrock"], default="extractive"
    )
    summarize.add_argument("--prompt", type=Path, default=DEFAULT_PROMPT)
    summarize.set_defaults(func=command_summarize)

    evaluate = subparsers.add_parser("evaluate", help="ゴールドデータで評価")
    evaluate.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    evaluate.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    _add_pipeline_options(evaluate)
    evaluate.set_defaults(func=command_evaluate)

    all_command = subparsers.add_parser("all", help="収集後から評価まで一括実行")
    all_command.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW)
    all_command.add_argument("--chunks", type=Path, default=DEFAULT_CHUNKS)
    all_command.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    all_command.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    all_command.add_argument("--prompt", type=Path, default=DEFAULT_PROMPT)
    all_command.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    all_command.add_argument("--chunk-size", type=int, default=650)
    all_command.add_argument("--dimension", type=int, default=384)
    all_command.add_argument(
        "--generator", choices=["extractive", "bedrock"], default="extractive"
    )
    all_command.add_argument("--mode", choices=["dense", "bm25", "hybrid"], default="hybrid")
    all_command.add_argument("--top-k", type=int, default=5)
    all_command.set_defaults(func=command_all)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
