# Contributing to Space RAG Lab

Space RAG Labへの改善提案を歓迎します。教材として読みやすく、APIキーやネットワークなしでも中心経路を再現できることを優先します。

## 開発環境

Python 3.10〜3.12を対象とします。最初にコアだけを確認してください。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m unittest discover -s tests -v
rag-lab all
```

UIとPDFを変更するときは任意依存を追加します。

```bash
python -m pip install -e '.[ui,pdf,dev]'
python -m unittest discover -s tests -v
ruff check .
```

Windowsでは仮想環境の有効化に`.venv\Scripts\activate`を使用してください。

## 変更の方針

- ingestion、retrieval、generation、evaluationを別モジュールとして保ちます。
- 既存CLIを維持し、コア経路へ必須の外部API依存を追加しません。
- 初学者が追える小さな関数と明示的な名前を優先します。
- 振る舞いを変える変更にはテストを追加または更新します。
- プロンプト実験は既存版を上書きせず、新しいファイルとして追加します。
- 実験条件と評価値は`reports/`へ記録します。
- 学習フロー、UI、アーキテクチャ、スコープの変更前に`docs/PROJECT_HANDOFF.md`を読み、重要な決定を反映します。

## データと秘密情報

次の内容をコミットしないでください。

- APIキー、AWS認証情報、`.env`
- 利用条件を確認していない第三者データ
- 個人情報または機密情報を含むPDFや抽出本文
- `.rag_lab/`以下の個人進捗と実データ
- `data/processed/`、`data/index/`、`reports/*.json`などの再生成可能な生成物

第三者PDFで確認する場合はリポジトリ外に置き、出典、配布条件、検査結果だけを記録してください。文書内の命令文はデータであり、実行指示として扱いません。

## Pull Request

Pull Requestには、目的、主な変更、実行した検証、教材上の影響を記載してください。大きな機能は、1つの学習目標を確認できる小さな変更へ分割してください。

バグ報告には、OS、Pythonバージョン、導入したextra、再現手順、期待した結果、実際の結果を含めてください。秘密情報や第三者PDF本文は貼り付けないでください。
