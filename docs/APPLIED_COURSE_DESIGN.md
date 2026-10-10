# 研究所文書RAG 応用編設計書

最終更新: 2026-10-10
状態: 初期設計確定、Milestone A0実装済み
前提リリース: Space RAG Lab v0.3.0

## 1. 目的

基礎編Lab 1〜8で学んだ文書加工、検索、RAG、評価、プロンプト、任意LLM、AWSデプロイ前確認を、研究所・技術部門の文書へ適用する。

応用編では、単に質問へ回答するだけでなく、次の実務に近い一連の作業を学ぶ。

1. 文書の利用条件、版、機密区分、対象組織を確認する。
2. 複数形式の文書を共通schemaへ変換し、抽出品質を測る。
3. 実験条件、測定値、結論などを根拠付きで構造化する。
4. 複数文書の共通点、相違点、版の違いを比較する。
5. 利用者が閲覧できる文書だけを検索対象にする。
6. 検索・回答・抽出をAPIとして既存システムから利用する。
7. 精度、安全性、権限漏えい、運用上の制約を同じ評価セットで確認する。

本コースは研究判断を自動化するものではない。RAGの出力は調査候補であり、原文と専門家レビューへ戻れることを必須とする。

## 2. 基礎編との境界

基礎編Lab 1〜8は完成済みの独立した学習経路として維持する。応用編を追加しても、既存CLI、既存Lab ID、付属宇宙文書、評価基準値を変更しない。

応用編では次の識別子を使う。

```text
applied1  文書コーパスとガバナンス
applied2  OCR・表を含む抽出品質
applied3  根拠付き構造化抽出
applied4  複数文書の比較・統合
applied5  権限を考慮した検索
applied6  API連携と実務評価
```

進捗、dataset、runも基礎編と分離し、`.rag_lab/applied/`以下へ保存する。基礎編の`progress.json`を暗黙に移行・上書きしない。

## 3. 対象者と前提

対象者は基礎編の主要操作を終えた大学生・社会人とする。

必要な前提:

- Pythonの基本文法、関数、辞書、ファイル操作を扱える。
- 仮想環境、CLI、JSON、単体テストの基本操作ができる。
- チャンク、Embedding、top-k、引用、回答不能の意味を説明できる。
- 同じ評価セットで変更前後を比較できる。

RAG、OCR、アクセス制御、API開発の実務経験は前提にしない。SQL、クラウド、画像機械学習、LangGraphも必須にしない。

1 Labは90〜180分を目安とする。OCR依存の導入や任意LLM・クラウド確認は別枠とする。

## 4. 扱う利用例

初期応用編では次の4タスクを扱う。

### 4.1 根拠付き質問応答

例: 「装置Aの校正周期は、どの版の手順書で何日に変更されたか」

回答には文書ID、版、ページ、チャンクIDを付ける。根拠がない場合は回答不能にする。

### 4.2 構造化情報抽出

実験報告書から次のような項目を抽出する。

- 試料・装置
- 実験条件
- 測定値と単位
- 不確かさ・誤差
- 結果
- 制約・注意事項
- 根拠箇所

値だけを保存せず、必ず根拠ページとチャンクを保持する。

### 4.3 複数文書比較

複数の報告書や改訂版から、条件、結果、結論の一致・相違・未記載を表にする。新しい文書が常に正しいとは仮定せず、版と日付を表示する。

### 4.4 権限付きナレッジ検索

利用者の所属グループと文書の許可グループを照合し、許可された文書だけを検索・生成へ渡す。取得後に隠す方式ではなく、検索候補を作る前に除外する。

## 5. データ方針

### 5.1 初期データセット

最初の実装では、公開可能な合成研究所文書をリポジトリへ追加する。実在組織、実在人物、未公開研究、個人情報、営業秘密を含めない。

推奨する最小コーパス:

- 文書数: 6〜10件
- ページ相当: 30〜60ページ
- 文書種別: 研究報告書、実験記録、標準手順書、改訂通知
- 改訂関係: 同一手順書の2版以上
- 表: 2件以上
- スキャン相当fixture: 2〜3ページ
- 機密区分: `public`、`internal`、`restricted`の合成ラベル
- 評価質問: 20問以上
- 回答不能: 全体の20%以上
- 権限境界質問: 5問以上

宇宙分野に限定しない。材料、環境計測、装置保守など、専門知識がなくても根拠を照合できる架空テーマを使う。

### 5.2 実データ

利用者自身のデータはローカルでのみ扱い、Gitへ追加しない。初期応用編で正式に扱える実データは、利用条件が確認できる公開文書、または組織内でローカル処理を許可された文書に限定する。

次の文書は初期応用編の対象外とする。

- 個人情報、医療情報、輸出管理情報を含む文書
- 契約上、学習環境への投入が禁止された文書
- 外部LLM送信の可否を確認できない機密文書
- マルウェア混入の疑いがあるファイル
- パスワード付き・暗号化文書

アプリは法務・情報セキュリティ承認を代行しない。利用者が「入力できた」ことを「利用許可がある」ことの証明にしない。

### 5.3 形式の段階導入

| 段階 | 対応形式 | 方針 |
| --- | --- | --- |
| Applied 1 | Markdown、TXT、文字レイヤー付きPDF | 既存処理を再利用し、複数文書と研究メタデータへ拡張 |
| Applied 2A | スキャンPDF、PNG、JPEG | ローカルOCR。画像を外部サービスへ送らない |
| Applied 2B | PDF内の表 | セル、行、列、ページ、抽出方式を保持 |
| 後続候補 | DOCX | セクション、表、脚注の保持方式を別途決定 |
| 後続候補 | 図・グラフの意味解析 | 任意のローカルvisionまたは明示確認付き外部モデルとして分離 |

図のキャプションと周辺本文は通常テキストとして扱えるが、グラフから数値を自動読取した結果は初期版で正式な根拠にしない。

## 6. 共通データモデル

### 6.1 Corpus manifest

dataset単位で次を持つ。

```text
schema_version
dataset_id
display_name
description
created_at
source_policy
license_or_terms
document_count
dataset_sha256
default_access_group
documents[]
```

`source_policy`は`synthetic`、`public_licensed`、`user_authorized_local`のいずれかとする。絶対パス、認証情報、文書本文はmanifestへ保存しない。

### 6.2 Research document metadata

基礎編の出典情報に次を追加する。

```text
document_id
title
source
document_type
organization
project
revision
published_date
language
classification
allowed_groups[]
license_or_terms
sha256
supersedes_document_id | null
```

必須値が欠けた文書は`needs_review`とする。`classification`または`allowed_groups`が欠けた文書は権限付き検索でfail closedとし、検索対象に含めない。

### 6.3 Content block

既存の`SourceDocument`、`SourcePage`、`ContentBlock`を拡張して利用する。

```text
block_id
kind: heading | text | table | figure_caption
text
page
section
extraction_method: native_text | ocr | table_parser | manual
confidence: float | null
bbox: [x0, y0, x1, y1] | null
metadata
```

OCRや表抽出器が信頼度を返さない場合、架空の数値を生成せず`null`とする。座標系と単位は抽出器ごとに変えず、manifestへ記録する。

### 6.4 Extracted fact

構造化抽出結果は次を持つ。

```text
fact_id
document_id
field_name
value
unit | null
qualifiers
evidence_chunk_ids[]
evidence_pages[]
extractor_name
extractor_version
verification_status: unreviewed | confirmed | rejected
```

`confidence`だけで`confirmed`にしない。人が確認した場合だけ`confirmed`へ変更する。

## 7. 応用Lab

### Applied Lab 1: 文書コーパスとガバナンス

#### 学習目標

- 複数文書をdatasetとして登録する。
- 文書版、利用条件、機密区分、許可グループを検索前に保持する。
- 原文からチャンクまで追跡可能にする。

#### 作業

1. 合成研究所コーパスのmanifestを確認する。
2. 文字レイヤー付きPDFとMarkdown/TXTを一括取り込みする。
3. document ID、版、日付、利用条件、分類の不足を検査する。
4. 同一文書の改訂関係を確認する。
5. 利用者データをGitへ含めず`.rag_lab/applied/`へ保存する。

#### 合格条件

- 6件以上の文書を取り込み、全チャンクから文書・版・ページへ戻れる。
- SHA-256と利用条件がmanifestへ記録される。
- 重複ID、欠損分類、改訂循環を検出できる。
- 文書本文、絶対パス、秘密情報を公開レポートへ複製しない。

### Applied Lab 2: OCR・表を含む抽出品質

#### 学習目標

- native text、OCR、表抽出を区別する。
- ページ画像と抽出結果を比較し、誤りを分類する。
- OCRや表抽出の改善が検索へ与える影響を測る。

#### 作業

1. ローカルOCRの環境チェックを実行する。
2. 合成fixtureの日本語・英数字・単位を抽出する。
3. 表を行・列・セルとMarkdown表示へ変換する。
4. ページ別の抽出方法、警告、確認状態を保存する。
5. OCR前後で同じ検索質問を評価する。

#### 合格条件

- 画像を外部ネットワークへ送らず処理できる。
- 正解fixtureで文字認識率と重要フィールド正解率を測れる。
- 表セルの位置、見出し、単位、ページを追跡できる。
- 低品質ページを成功扱いにせず`needs_review`へ送る。

#### 実装前ゲート

OCR実装前に、Tesseract系、PaddleOCR系、ONNXベース候補を、Windows・macOS・Linux、日本語、オフライン動作、ライセンス、モデル容量、導入失敗時の回復性で比較する。選定結果をADRへ残すまで依存を追加しない。

### Applied Lab 3: 根拠付き構造化抽出

#### 学習目標

- 自由文回答とschema付き抽出を区別する。
- 値、単位、条件、根拠を一体で扱う。
- 未記載と抽出失敗を区別する。

#### 作業

1. 抽出schemaをYAMLまたはJSONで定義する。
2. オフライン規則ベースを基準器として実行する。
3. 任意LLMを同じ根拠で比較する。
4. 単位正規化前後の評価を比較する。
5. 抽出結果を原文ページと照合して確認・却下する。

#### 合格条件

- 必須キー、型、単位、引用のschema検査が通る。
- 根拠のない値を出力しない。
- 未記載は`null`と理由で表し、推測値を作らない。
- 20件以上の正解factでフィールド別精度を計算する。

### Applied Lab 4: 複数文書の比較・統合

#### 学習目標

- 改訂版、日付、測定条件を考慮して文書を比較する。
- 一致、相違、未記載、比較不能を区別する。
- 1つの要約へ潰さず、根拠を文書ごとに保持する。

#### 作業

1. 同一テーマの2〜4文書を選ぶ。
2. 比較軸を先に定義する。
3. 各セルに根拠文書、版、ページを付けた比較表を作る。
4. 矛盾候補と単なる条件違いを分ける。
5. 文書追加前後で比較結果を再評価する。

#### 合格条件

- 全ての比較セルが出典へ戻れる。
- 比較対象外・未記載を空文字で隠さない。
- 新旧版の優先規則を設定として記録する。
- 代表的な不一致3件を人がレビューする。

### Applied Lab 5: 権限を考慮した検索

#### 学習目標

- 認証と認可を区別する。
- アクセス制御を検索前に適用する。
- 権限漏えいを通常の検索精度とは別に評価する。

#### 初期権限モデル

実在IdPへ接続せず、合成した次の属性で学ぶ。

```text
principal_id
groups[]
clearance
```

文書は`classification`と`allowed_groups[]`を持つ。許可判定を通った文書だけをretrieverへ渡す。許可されない文書のタイトル、チャンクID、件数、存在を回答やログへ出さない。

教材用policyは次に固定する。

- `public`: 全principalへ許可する。`allowed_groups`は空でよい。
- `internal`: `clearance >= internal`かつ、principalと文書のgroupが1件以上一致した場合だけ許可する。
- `restricted`: `clearance >= restricted`かつ、principalと文書のgroupが1件以上一致した場合だけ許可する。
- 不明なclassification、欠損clearance、欠損allowed groupsは拒否する。

`clearance`は`public < internal < restricted`の順序を持つ列挙値とし、任意文字列の大小比較をしない。principal IDは氏名やメールではなく、合成または仮名化した識別子を使う。

#### 合格条件

- 権限なし文書の検索・引用・回答への漏えいが0件である。
- metadata欠損時はfail closedになる。
- 権限変更後にキャッシュや索引から古い結果を返さない。
- 利用者、判定結果、policy版を本文なしの監査ログへ記録できる。

#### 境界

UIやローカルAPIのロール選択は教材用シミュレーションであり、本番認証ではない。本番ではOIDC等で検証済みidentityを受け取り、利用者入力のroleヘッダーを信用しない。

### Applied Lab 6: API連携と実務評価

#### 学習目標

- 検索、質問応答、抽出を別エンドポイントとして設計する。
- schema、入力上限、認証境界、監査ログ、エラー形式を定義する。
- 機能精度と安全性を継続評価する。

#### 学習用API案

```text
GET  /health
POST /search
POST /ask
POST /extract
GET  /documents/{document_id}
```

`/documents/{document_id}`は本文全体ではなく、許可判定後のメタデータと参照可能な箇所を返す。開発用の合成principalはアプリ内部で選択し、公開HTTPヘッダーを本番認証として扱わない。

#### 合格条件

- API schemaとエラー形式をテストで固定する。
- 入力サイズ、質問長、top-k、timeout、同時実行数に上限がある。
- 権限検査を迂回するエンドポイントがない。
- 回答と抽出結果から引用へ戻れる。
- 回答本文・原文本文・認証情報を通常ログへ保存しない。
- 同じ評価セットをCLI、UI、APIで再利用できる。

## 8. 評価設計

平均値だけでなく、問題IDごとの失敗と権限境界を保存する。

| 分類 | 指標 | 初期合格条件 |
| --- | --- | ---: |
| 取り込み | page coverage | 1.00 |
| メタデータ | provenance completeness | 1.00 |
| 検索 | Recall@5 | 0.90以上 |
| 検索 | MRR | 基準器から悪化しない |
| 回答 | citation hit rate | 0.90以上 |
| 回答 | answerability accuracy | 0.90以上 |
| 抽出 | required field accuracy | 0.85以上 |
| 表 | critical cell accuracy | 0.90以上 |
| 権限 | unauthorized retrieval/citation | 0件 |
| 安全 | 文書内命令への追従 | 0件 |
| 保存 | 本文・秘密情報のログ混入 | 0件 |

OCR文字認識率は言語・レイアウト別に示し、全体平均だけで合格にしない。外部LLMを使う評価はモデルID、リージョン、プロンプト版、日時、料金見積りを記録するが、認証情報と本文は保存しない。

正解データは少なくとも次を持つ。

```text
case_id
task_type
question_or_field
expected_document_ids[]
expected_pages[]
required_values[]
required_units[]
expected_answerable
principal_groups[]
allowed_result_document_ids[]
```

正解値を検索・生成コードへ埋め込まない。

## 9. 安全性とプライバシー

- 既定はローカル・オフラインとする。
- 実データ、抽出本文、索引、OCR画像、監査ログはGit対象外とする。
- 文書内の命令をデータとして扱い、システム命令として実行しない。
- 外部LLMへ送る前に、送信先、対象データ、料金、保持条件を明示確認する。
- アクセス制御は取得後の表示フィルターではなく、検索前の必須条件にする。
- 権限なし文書の存在をエラー文、件数、ログ、候補IDから推測できないようにする。
- OCR・PDF解析は信頼境界と考え、サイズ、ページ数、ピクセル数、処理時間に上限を設ける。
- 任意のシェル、マクロ、埋め込みファイル、PDF内リンクを実行しない。
- LLMや抽出器の出力を、schema検証なしでファイル名、クエリ、コードとして使用しない。
- 実在組織の法令・規程準拠を、この教材の完了表示で保証しない。

## 10. アーキテクチャ

既存のingestion、retrieval、generation、evaluationの分離を維持する。

```text
Streamlit applied UI / CLI / local API
                  |
            Learning services
                  |
     +------------+-------------+
     |            |             |
Ingestion      Access       Evaluation
     |         policy            |
Normalized        |               |
documents --------+--> Retriever  |
                         |        |
                    Generator ----+
                         |
                 Answers / Facts
```

アクセス判定はretrieverの入力境界に置く。UI、CLI、APIごとに別実装を作らず、同じpolicy関数を使用する。

モジュール案:

```text
src/rag_lab/applied/
  corpus.py           manifestと文書版
  extraction.py       構造化fact
  comparison.py       文書比較
  access.py           fail-closed policy
  evaluation.py       応用評価
src/rag_lab/learning/
  applied1.py ... applied6.py
src/rag_lab/ui/
  applied.py
```

OCRと表抽出は`source_documents.py`の共通型へ変換するアダプターとし、RAGパイプラインへ直接混在させない。

## 11. 保存と公開

```text
.rag_lab/applied/
  progress.json
  datasets/<dataset_id>/
    manifest.json
    processed/pages.jsonl
    processed/chunks.jsonl
    processed/facts.jsonl
    indexes/
    runs/
    audit/
```

- `raw/`保存は利用者が明示した場合だけ許可する。
- auditには仮名化したprincipal IDのdigest、policy版、許可・拒否、対象文書IDのdigestを保存し、本文を保存しない。
- 公開レポートは利用者が内容を確認して明示的にexportした場合だけ`reports/`へ出す。
- 公開レポートには文書本文、OCR画像、絶対パス、個人情報、内部文書名を含めない。
- dataset削除は原本、抽出物、索引、run、auditを対象にした確認付き操作として後続設計する。

## 12. テスト方針

各振る舞い変更にテストを追加する。

- 小さい合成fixtureで正常系と異常系を固定する。
- OCRと表抽出は実エンジン依存テストと、保存済み小型fixtureによる単体テストを分離する。
- ネットワーク、実LLM、実IdP、実AWSを通常CIで呼ばない。
- 権限テストでは、許可ありだけでなく拒否、metadata欠損、キャッシュ、複数グループを確認する。
- prompt injection文を含む合成文書をデータとして処理し、命令として実行しないことを検査する。
- Windows、macOS、Linuxのパス差を考慮し、絶対パスを成果物へ保存しない。
- 既存基礎編の109テストと評価基準値を維持する。

## 13. 実装マイルストーン

### Milestone A0: 合成コーパスとschema

- 合成研究所文書6〜10件
- corpus manifestと研究メタデータschema
- 評価質問20問以上
- 権限境界ケース5問以上
- 本文を含まない受け入れレポート

### Milestone A1: Applied Lab 1の縦切り

- 複数文書取り込み
- manifest検査
- 改訂関係
- `.rag_lab/applied/`保存
- UI、CLI、単体テスト

### Milestone A2: OCR・表

- OCR方式ADR
- 小型スキャンfixture
- 表schemaと抽出品質評価
- 処理上限と失敗分類

### Milestone A3: 構造化抽出と比較

- fact schema
- オフライン基準器
- 任意LLM比較
- 文書別の根拠表

### Milestone A4: 権限付き検索

- 合成principalとpolicy
- pre-retrieval filter
- 権限漏えい評価
- 本文なし監査ログ

### Milestone A5: APIと統合評価

- `/search`、`/ask`、`/extract`
- 共通request/response schema
- 入力上限と安全なエラー
- CLI、UI、APIの同一評価

各マイルストーンは個別PRとし、前段の受け入れ結果を`reports/`へ残してから次へ進む。

## 14. 最初の実装範囲

設計承認後の最初の実装はMilestone A0だけとする。OCR、表抽出、外部LLM、権限判定APIはまだ実装しない。

A0で決めるもの:

1. 合成研究所文書のテーマと文書間関係
2. corpus manifest schema
3. 研究文書metadata schema
4. gold case schema
5. データ生成・検査テスト
6. ライセンスと架空データ表示

A0は2026-10-10に実装した。合成文書8件・32ページ相当、JSON Schema 3件、評価case 29件（回答不能7件、権限境界12件）、オフライン検査を追加した。受け入れ結果は`reports/applied_a0_acceptance_2026-10-10.md`に記録する。次はデータと評価問題の人手レビューを行い、その後にApplied Lab 1のUI・CLIを実装する。

## 15. 明示的な非目標

- 実在研究所の機密文書を付属データとして配布すること
- 法務、輸出管理、個人情報保護の適合証明
- 本番IdP、SSO、組織ディレクトリへの接続
- 完全なPDFレイアウト復元
- グラフ画像からの高精度な数値読取
- 研究結論、安全判断、特許性を自動決定すること
- 大規模分散ベクトルDBの性能検証
- エージェントによる自律的な外部操作
- LangGraphを導入すること

これらは教材の安全な範囲を超えるため、必要性と受け入れ条件を別途設計してから追加する。

## 16. 未決定事項と決定時期

初回実装を妨げない項目だけを未決定として残す。

| 項目 | 決定時期 | 判断基準 |
| --- | --- | --- |
| OCRエンジン | Milestone A2着手前 | 3 OS、日本語、オフライン、ライセンス、モデル容量 |
| 表抽出ライブラリ | Milestone A2着手前 | native/scan PDF、座標保持、依存負荷 |
| DOCX対応 | A1完了後 | 利用例、表・脚注、ライセンス |
| 実Embeddingモデル | A3着手前 | 日本語、CPU、オフライン、モデル配布条件 |
| 本番認証方式 | 教材外の実システム設計時 | 組織IdP、監査、失効、運用責任 |
| クラウド配置 | A5完了後の任意工程 | データ送信、料金、IAM、削除計画 |

未決定項目は、選定対象を実装するPRへ混ぜない。比較結果と決定をADRへ記録してから依存関係を追加する。

## 17. 自己実装とコーディングAI協働

各Applied Labは基礎編と同じく、自己実装とコーディングAI協働の両方を案内する。

- AIへ渡す依頼は1回30〜60分でレビューできる単位にする。
- 付属の合成文書と最小fixtureだけを依頼へ含める。
- 実在の内部文書、OCR画像、抽出本文、認証情報を外部AIへ貼り付けない。
- AIの変更は差分、テスト、評価値、権限境界を利用者自身が確認する。
- 「テストが通った」だけで完了せず、改善理由と悪化例を説明する。
- アプリからClaude Code、Cursor、Codex等を自動起動しない。

Milestone A0の実装時に、Applied Lab向けの小さい依頼例を`docs/CURSOR_AGENT_TASKS.md`へ追加する。特定のAI製品を必須にしない。
