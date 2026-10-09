# Space Research RAG Lab

[![CI](https://github.com/raiulab/space-rag-lab/actions/workflows/ci.yml/badge.svg)](https://github.com/raiulab/space-rag-lab/actions/workflows/ci.yml)

宇宙技術に関する架空の報告書を使い、文書処理からAWS公開までを段階的に学ぶ実習プロジェクトです。Notebookは使わず、Pythonモジュール、CLI、テスト、評価レポートを成果物として残します。

教材の文書・数値・組織はすべて架空です。実在するミッションの判断や設計には使用しないでください。

## v0.2.0の公開範囲

APIキー不要のCLIと、Lab 1〜3・5、評価診断・比較のローカル学習ナビゲーションが動作します。Lab 4・6〜8にはガイド、CLI、一部のAPI・Bedrock・AWS基盤がありますが、同じブラウザ学習画面はまだありません。

| 項目 | v0.2.0の状態 |
| --- | --- |
| Lab 1 文書加工・PDF取り込み | UI・CLI実装済み |
| Lab 2 検索比較 | UI・CLI実装済み |
| Lab 3 根拠付きRAG | UI・CLI実装済み |
| Lab 5 検索・要約・QA | UI・CLI実装済み |
| 評価診断・比較 | UI実装済み |
| Lab 4・6〜8 | ガイド・CLI・一部基盤、UI未実装 |
| APIキーなしの実行 | 対応 |
| 自分のPDF | 文字レイヤー付きPDFに対応 |
| OCR・表・図・一般画像解析 | 未対応 |

## 対象者と前提知識

基本対象者は、Pythonの基本文法、関数、リスト・辞書、ファイル操作の基礎を理解し、ターミナルと仮想環境を手順に沿って扱える大学生・社会人です。割合や平均を読めれば十分で、専門的な統計知識は必要ありません。

RAG、Embedding、ベクトル検索、LLM API、画像機械学習、AWSは未経験または初級で構いません。クラス、型ヒント、JSONL、テスト、検索評価指標は実習内で段階的に扱います。

Pythonを一度も書いたことがない人は、現行本編の基本対象には含めません。将来、Python、ターミナル、仮想環境、JSON、テストの基礎を扱う任意のPre-Labを追加する方針です。LangGraphも現在の8 Labには含まれず、必要になった場合は発展Labとして別途設計します。

## このプロジェクトで作るもの

質問を受け取ると関連箇所を検索し、文書ID・ページ・チャンクIDを付けて回答する小さなRAGアプリです。APIキーがなくても、文書加工、Embedding生成、ハイブリッド検索、質問応答、評価まで実行できます。Lab 4でAmazon Bedrockへ切り替え、Lab 8でAWSへ配置します。

```mermaid
flowchart LR
    A[Markdown / TXT / PDF] --> B[整形・分割]
    B --> C[Embedding索引]
    Q[質問] --> D[BM25 + ベクトル検索]
    C --> D
    D --> E[根拠付きプロンプト]
    E --> F[抽出式 / Bedrock]
    F --> G[回答・引用]
    G --> H[自動評価]
    H --> B
```

## 最短の実行方法

Python 3.10以上だけで、コア実習を動かせます。

```bash
git clone https://github.com/raiulab/space-rag-lab.git
cd space-rag-lab
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
rag-lab all
rag-lab ask "火星の砂嵐で太陽電池出力は何%まで低下しましたか？"
rag-lab search "放射線によるビット反転" --mode hybrid
rag-lab summarize europa_comm_2026
```

`rag-lab all` は、生文書の加工、Embedding索引の作成、10問の評価を順に実行します。詳しい結果は `reports/evaluation.json` に保存されます。

インストールせずに試す場合は、各コマンドの先頭を `PYTHONPATH=src python3 -m rag_lab.cli` に置き換えられます。

ブラウザでLab 1〜3・5と評価診断を進める場合は、PDFとUIの任意依存を追加します。

```bash
python -m pip install -e '.[ui,pdf]'
rag-lab ui
```

対応環境はPython 3.10〜3.12、Windows、macOS、Linuxです。Windowsでは仮想環境を`.venv\Scripts\activate`で有効化してください。

## 8つの実習

| Lab | 実務工程 | 作るもの | 合格条件 |
| --- | --- | --- | --- |
| 1 | 技術文書の収集・加工 | メタデータ付きチャンクJSONL | 文書ID・ページを失わない |
| 2 | Embedding・ベクトル検索 | 再現可能な索引と検索CLI | 代表5問の検索ヒット率80%以上 |
| 3 | RAG設計・実装 | 検索→生成→引用のパイプライン | 回答から根拠へ戻れる |
| 4 | LLM API連携 | Amazon Bedrock生成器 | API障害と秘密情報を安全に扱う |
| 5 | 検索・要約・QA | CLIと任意のFastAPI | 3機能を別々に実行できる |
| 6 | 精度評価・改善 | ゴールドデータと比較レポート | 変更前後を同じ質問で比較する |
| 7 | プロンプト設計 | v1/v2プロンプト比較 | 引用・拒否ルールを検証する |
| 8 | AWS実行環境 | SAM構成とHTTP API | ログ・権限・費用上限も説明できる |

各Labの手順と課題は [docs/LABS.md](docs/LABS.md)、Cursor Agentへ渡せる小さな依頼文は [docs/CURSOR_AGENT_TASKS.md](docs/CURSOR_AGENT_TASKS.md) にあります。

プロジェクトの決定事項、現在状態、今後のローカル学習アプリ方針は [docs/PROJECT_HANDOFF.md](docs/PROJECT_HANDOFF.md) にまとめています。新しいCodexスレッドへ移行するときは [docs/NEW_THREAD_PROMPT.md](docs/NEW_THREAD_PROMPT.md) を使用してください。

ローカル学習ナビゲーションアプリの初期設計、PDF対応範囲、保存形式、テスト、受け入れ条件は [docs/LOCAL_LEARNING_APP_DESIGN.md](docs/LOCAL_LEARNING_APP_DESIGN.md) にまとめています。

## ローカル学習ナビゲーション

Lab 1〜3・5と、Milestone 3の評価診断・比較はブラウザ画面から進められます。StreamlitとPDF機能を追加し、プロジェクトルートから起動してください。

```bash
python -m pip install -e '.[ui,pdf]'
rag-lab ui
```

画面は`127.0.0.1`だけで待ち受け、Streamlitの利用統計送信を無効にします。全8 Labの状態、Python・PDF環境を表示します。Lab 1では「付属Markdown/TXT」と「自分のPDF」のどちらか一方を選べます。

Lab 1では、実行前の予想、加工結果、文書・ページ・チャンク数、出典、実行後の観察、完了条件を順に確認します。PDFでは元PDFとページ別抽出テキストを並べ、警告を確認してから記録します。結果は`.rag_lab/`へ保存され、Git対象にはなりません。

Lab 2では、付属データまたはLab 1で保存したデータセットを使い、dense・BM25・hybridを同じ質問とtop-kで比較します。付属データでは回答可能な8問のHit@kを表示し、実データでは正解ラベルを仮定せず目視評価します。学習記録には設定、スコア、チャンクID、観察を保存し、チャンク本文は複製しません。

Lab 3では、質問、検索結果、抽出式回答、引用、回答可能性判定を順番に表示します。実行前に回答可能かを予想し、予想と判定が異なる場合は`needs_review`として根拠を見直します。外部LLMは使わず、回答不能時に引用を付けないこと、回答時に引用チャンクへ戻れることを確認します。

Lab 5では、同じデータセットを使って検索、1文書の要約、質問応答を実行します。検索は順位・スコア・出典、要約は対象文書と要約元チャンク、QAは回答可能性・回答・引用を表示し、3機能を混同せず比較します。保存する学習記録には生成文とチャンク本文を複製しません。

「診断・比較」では、`reports/*.json`の評価値と失敗問題を読み込み、検索・引用・回答内容・回答可能性のどこに問題があるかを分類します。3段階のヒントで原因を切り分け、2つのレポート間の改善と新たな失敗を比較できます。学習レポートは回答本文を複製せず、`.rag_lab/reports/`へ保存するかMarkdownでダウンロードします。

比較用レポートは、条件を1つだけ変えて作成してください。

```bash
rag-lab evaluate --mode dense --report reports/dense.json
rag-lab evaluate --mode hybrid --report reports/hybrid.json
rag-lab ui
```

### PDF取り込みCLI

文字レイヤー付きPDFをページ単位で抽出し、既存の`Chunk`形式へ変換できます。PDF機能だけを追加でインストールしてください。

```bash
python -m pip install -e '.[pdf]'
rag-lab ingest-pdf INPUT.pdf \
  --document-id example \
  --title "表示名" \
  --classification user_provided \
  --output .rag_lab/example-chunks.jsonl
```

出力には`document_id`、1始まりの`page`、`section`、`source`が残ります。空ページと20文字未満のページを警告し、空ページ率が20%以上なら`needs_review`になります。文書全体から文字を抽出できないPDFは`OCR_REQUIRED`として終了コード2を返し、チャンクを書き出しません。

対応上限は1件25 MB、200ページで、暗号化されていない文字レイヤー付きPDFが対象です。スキャンPDFのOCR、表・図、一般画像解析はまだ対象外です。元PDFを正解と考えず、ページ表示と抽出テキストを目視比較してください。

PDF結果を`.rag_lab/datasets/<dataset_id>/`へ保存するサービス層も実装済みです。manifest、ページ、チャンク、実行記録、完了検査をdataset単位で保持し、既存datasetを上書きしません。PDF原本は明示指定時だけ`raw/source.pdf`へ保存します。

### 公開PDFの受け入れ記録

公開条件を確認した実在PDFを手動検査するときは、PDFをリポジトリ外へ用意し、先頭・中央・末尾ページを元PDFと抽出結果で比較してから記録します。このコマンドはネットワークへ接続せず、PDF本体や抽出本文をレポートへコピーしません。

```bash
rag-lab accept-pdf /path/to/public-report.pdf \
  --document-id public_report \
  --title "公開技術報告書" \
  --source-url "https://example.org/report.pdf" \
  --catalog-url "https://example.org/report" \
  --distribution "Public" \
  --license-terms "利用条件を確認して記入" \
  --inspected-page 1 \
  --inspected-page 5 \
  --inspected-page 10 \
  --decision accepted_with_limitations \
  --observation "代表ページを比較した結果と制約" \
  --report reports/lab1-public-pdf-acceptance.md
```

実施済みのNASA技術報告書による確認結果は[`reports/lab1_public_pdf_acceptance_2026-10-03.md`](reports/lab1_public_pdf_acceptance_2026-10-03.md)にあります。第三者PDF本体はGitへ保存していません。

初期対応は、付属Markdown/TXTと、暗号化されていない文字レイヤー付きPDF 1件です。個人の進捗と実データはGit対象外の`.rag_lab/`へ保存し、生PDFはUIから明示選択された場合だけ保存する設計です。

UI/PDF機能はPython 3.10〜3.12、Windows、macOS、Linuxを対象にし、APIキーやAWS設定なしで動作させます。詳細は設計書を参照してください。

## ディレクトリ

```text
data/raw/                 架空の生文書（編集してよい教材）
data/evaluation/          正解付き質問
data/processed/           Lab 1で生成するチャンク
data/index/               Lab 2で生成するベクトル索引
src/rag_lab/              実装
prompts/                  プロンプトの版
reports/                  評価結果
infra/                    AWS SAM構成
tests/                    回帰テスト
```

## ローカルAPI

このAPIは学習用です。認証、利用者ごとの権限、レート制限を備えた公開サービスではありません。既定の`127.0.0.1`から外部ネットワークへ公開しないでください。

```bash
python -m pip install -e '.[api]'
uvicorn rag_lab.api:app --reload
curl -X POST http://127.0.0.1:8000/ask \
  -H 'content-type: application/json' \
  -d '{"question":"蓄電池だけで重要機器を何時間維持できますか？"}'
```

## Bedrockへの切り替え

AWSアカウント、利用可能なモデル、認証情報が必要です。モデルIDは利用するリージョンで確認してください。秘密鍵はソースコードや `.env` へコミットしません。

```bash
python -m pip install -e '.[aws]'
export AWS_REGION=ap-northeast-1
export BEDROCK_MODEL_ID='利用可能なモデルまたは推論プロファイルのID'
rag-lab ask "TMR方式の試験結果を説明してください" --generator bedrock
```

AWS配置は [infra/README.md](infra/README.md) を参照してください。

## セキュリティ

公開リポジトリではSecret scanningとpush protectionを有効にし、依存関係は`pip-audit`とDependabot、PythonコードはCodeQLで継続検査します。GitHub Actionsは検証したcommit SHAへ固定しています。脆弱性は公開Issueではなく、GitHubのPrivate vulnerability reportingから連絡してください。

PDFにはサイズ・ページ数・暗号化の検査がありますが、PDFパーサーをOSレベルで隔離してはいません。出所を信頼できないPDF、機密文書、利用条件が不明な文書を入力しないでください。詳細は[SECURITY.md](SECURITY.md)を参照してください。

## テスト

外部パッケージなしでも標準ライブラリのテストを実行できます。

```bash
python -m unittest discover -s tests -v
```

PDF extraが未導入の場合、PDF抽出を必要とするテストだけがskipされます。PDF機能を含む全テストは`python -m pip install -e '.[pdf]'`の後に同じコマンドで実行できます。

任意で開発用ツールを入れる場合:

```bash
python -m pip install -e '.[dev]'
pytest
ruff check .
```

## 最初に観察する失敗

初期の抽出式生成器は、検索結果に似た単語があるだけで「回答可能」と誤判定する場合があります。また、同じ意味の表記揺れ（例: `℃` と `°C`）で文字列評価が下がります。これはバグを隠さず、Lab 6と7で次を比較するための教材です。

- チャンクサイズと検索件数
- dense / BM25 / hybrid
- 正規化した評価と単純な文字列評価
- 回答不能を判定する閾値
- プロンプトv1 / v2
- 抽出式生成 / LLM生成

目標は「一度だけ良い回答を出すこと」ではなく、失敗例を再現し、修正が別の質問を悪化させていないと説明できることです。

## 公開情報

- 変更履歴: [CHANGELOG.md](CHANGELOG.md)
- v0.1.0リリースノート: [docs/releases/v0.1.0.md](docs/releases/v0.1.0.md)
- 貢献方法: [CONTRIBUTING.md](CONTRIBUTING.md)
- セキュリティ方針: [SECURITY.md](SECURITY.md)
- 第三者パッケージ: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
- ライセンス: [MIT License](LICENSE)
