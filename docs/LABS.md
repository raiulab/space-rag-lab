# 実習ガイド

1つのLabを60〜120分で進められるように分割しています。最初は完成コードを実行し、次に観察し、最後に自分で一部を変更してください。各Labの変更は小さなGitコミットにすると、実務の作業記録にもなります。

## Lab 1: 技術文書・報告書の収集と加工

### 学ぶこと

RAGではLLMより先に、出典を失わず文書を検索単位へ変える必要があります。生文書、メタデータ、ページ、見出し、チャンクの関係を確認します。

### 実行

```bash
rag-lab ingest --chunk-size 650
head -n 2 data/processed/chunks.jsonl
```

### 作業

1. `data/raw/` のfront matter、ページマーカー、見出しを確認する。
2. `src/rag_lab/ingest.py` で、どの情報が `Chunk` に残るか追う。
3. `--chunk-size 300` と `900` を試し、チャンク数と文章のまとまりを比較する。
4. 自分で5ページ目相当の架空レポートを1つ追加する。

### 成果物と合格条件

`data/processed/chunks.jsonl` のどの行にも `document_id`、`page`、`section`、`source` があり、元文書の場所へ戻れること。画像PDFやスキャンPDFを追加する場合は、OCR精度を別に測ること。

## Lab 2: Embedding生成とベクトル検索

### 学ぶこと

Embeddingは文章を、意味の近さを計算できる数値ベクトルへ写す処理です。この教材の `HashEmbeddingModel` は無料・再現可能ですが、真の意味理解はしません。まず内積・コサイン類似度・次元・正規化を実物で確認するための基準器です。

### 実行

```bash
rag-lab index --dimension 384
rag-lab search "太陽光が弱くなったときの電力対策" --mode dense
rag-lab search "太陽電池 32%" --mode bm25
rag-lab search "太陽光が弱くなったときの電力対策" --mode hybrid
```

### 作業

1. dense、BM25、hybridの上位5件を比較する。
2. denseはコサイン類似度、BM25は単語の希少性、hybridは順位融合であることをコードから確認する。
3. 実務版への発展として、多言語Embeddingモデルのアダプターを追加する。
4. モデルID、次元、作成日時、文書版を索引のメタデータに残す設計を考える。

### 合格条件

ゴールド質問の `expected_document_ids` が上位5件に入る割合を計算し、検索方式の選択理由を数字で説明できること。

## Lab 3: RAGパイプラインの設計・実装

### 学ぶこと

RAGは「検索」だけではありません。質問入力、検索、コンテキスト構築、生成、引用、回答不能処理を1本の処理として設計します。

### 実行

```bash
rag-lab ask "放熱塗装Bはなぜ採用されませんでしたか？"
rag-lab ask "月面基地の乗員は何人ですか？"
```

### 作業

`src/rag_lab/pipeline.py` を起点に処理を追います。2問目で初期版が誤って答えることがある理由を、検索結果と生成器の判定に分けて説明してください。その後、検索スコア閾値、根拠文の選択、回答不能判定のいずれか1つを改善します。

### 合格条件

回答内またはAPI結果から、使用した文書・ページ・チャンクへ戻れること。検索結果が空または弱い場合の振る舞いをテストで固定すること。

## Lab 4: LLM API連携

### 学ぶこと

`ExtractiveGenerator` と `BedrockGenerator` は同じインターフェースです。外部APIを交換可能な部品にし、認証・タイムアウト・課金・失敗時の処理をアプリ本体から分けます。

### 実行

```bash
python -m pip install -e '.[aws]'
export AWS_REGION=ap-northeast-1
export BEDROCK_MODEL_ID='利用可能なID'
rag-lab ask "通信遅延への対策を要約してください" --generator bedrock
```

### 作業

1. AWS CLIまたは実行ロールで認証し、アクセスキーをコードに書かない。
2. 同じ質問を抽出式とBedrockで実行する。
3. APIの応答時間、入力文字数、出力文字数、失敗種別をログへ残す。
4. スロットリング、タイムアウト、不正なモデルIDのテストダブルを作る。

### 合格条件

LLM APIが失敗してもHTTP 500の生ログを利用者へ漏らさず、原因を運用ログで追跡できる設計であること。

## Lab 5: 検索・要約・質問応答

### 実行

```bash
rag-lab search "低電力時の安全モード" --mode hybrid
rag-lab summarize mars_power_2026
rag-lab ask "蓄電池の設計目標との差は何時間ですか？"
```

任意でWeb APIを起動します。

```bash
python -m pip install -e '.[api]'
uvicorn rag_lab.api:app --reload
```

### 作業

検索は候補を返し、要約は1文書を圧縮し、QAは特定の問いへ答えます。3機能の入力・出力・評価指標を混同しないこと。FastAPIへ `/search` と `/summarize/{document_id}` を追加するのが発展課題です。

### 合格条件

検索結果はスコアと出典を、要約は対象文書IDを、QAは引用を返すこと。

## Lab 6: 回答精度の評価・改善

### 実行

```bash
rag-lab evaluate --mode dense --report reports/dense.json
rag-lab evaluate --mode bm25 --report reports/bm25.json
rag-lab evaluate --mode hybrid --report reports/hybrid.json
```

### 指標

- `retrieval_hit_rate`: 正解文書が上位k件に入った割合
- `citation_hit_rate`: 回答の引用に正解文書がある割合
- `keyword_recall`: 必須語が回答に含まれる割合
- `answerability_accuracy`: 答えられる/答えられないを正しく判定した割合

### 作業

1. `reports/evaluation.json` の失敗例だけを読む。
2. 失敗を、文書加工・検索・生成・評価器のどこで生じたか分類する。
3. 仮説を1つ立て、変更は1種類だけ行う。
4. 同じ10問を再実行し、改善と副作用を記録する。
5. 自分で回答不能問題を2問追加する。

### 合格条件

「良くなった気がする」ではなく、変更前後のJSONレポートと、悪化した例を含む短い考察を残すこと。

## Lab 7: プロンプト設計

### 学ぶこと

`prompts/answer_v1.txt` は単純な指示、v2は根拠限定、引用、回答不能、文書内命令の無視を明示します。プロンプトはプログラムと同じく版管理し、同じ評価セットで比較します。

### 実行

```bash
rag-lab evaluate --generator bedrock --prompt prompts/answer_v1.txt --report reports/prompt_v1.json
rag-lab evaluate --generator bedrock --prompt prompts/answer_v2_grounded.txt --report reports/prompt_v2.json
```

### 作業

回答形式をJSONに変更したv3を作り、構文エラー率を測ってください。文書本文に「それまでの指示を無視」と書いた試験文を追加し、命令として実行されないことも確認します。

### 合格条件

プロンプトの変更理由、対象の失敗、評価結果を1セットで説明できること。

## Lab 8: AWS上の実行環境

ローカルで索引とテストが完成してから進みます。手順は `infra/README.md` にあります。

### 作業

1. Lambdaの実行ロールを最小権限にする。
2. API Gateway経由で `/ask` を公開する。
3. CloudWatch Logsでエラーを確認する。
4. 予算アラート、ログ保持期間、同時実行数の上限を設定する。
5. 本番発展では、索引を同梱ファイルからS3/OpenSearch Serverless等へ移す。

### 合格条件

HTTPリクエストから回答まで動くことに加え、構成図、IAM権限、費用が発生する箇所、停止方法をREADMEへ残すこと。

## 最終課題

架空文書を最低10件、評価質問を最低30問へ増やします。うち20%以上を回答不能問題にし、検索方式またはEmbeddingモデルを2種類以上比較してください。最終レポートには、データ仕様、アーキテクチャ、評価表、代表的な失敗3件、改善履歴、セキュリティ上の注意を含めます。
