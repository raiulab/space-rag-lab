# Applied Milestone A0 受け入れ記録

実施日: 2026-10-10
対象: `feature/applied-a0-corpus`
判定: passed

## 対象範囲

- 公開可能な合成研究所文書
- corpus manifestと研究文書metadata schema
- gold case schemaと評価fixture
- ネットワーク・APIキー・任意依存を使わない整合性検査

OCR、表構造抽出、外部LLM、権限付きretriever、Applied Lab UI・CLIはA0の対象外である。

## データ構成

| 項目 | 結果 |
| --- | ---: |
| 文書数 | 8 |
| ページ相当 | 32 |
| 改訂関係 | 2 |
| 表を含む文書 | 4 |
| 機密区分 | public / internal / restricted |
| 評価case | 29 |
| 回答不能case | 7（24.1 %） |
| 権限境界case | 12 |

文書はすべて合成データであり、実在組織、実在人物、未公開研究、認証情報を含まない。本文、正解値、権限なし文書名をこの受け入れ記録へ複製していない。

## 検査設定

```bash
python -m rag_lab.applied.corpus data/applied
python -m unittest discover -s tests -v
ruff check .
```

A0 validatorは次を検査する。

- 文書ファイルとdatasetのSHA-256
- sourceが相対パスであること
- front matterとmanifestの一致
- 1始まりのページ連番とpage count
- document ID重複と改訂循環
- public文書と非公開文書のallowed groups
- 評価caseの文書参照と教材用policyの期待値
- 回答不能率20 %以上、権限境界5件以上

## 結果

- A0 validator: passed
- 単体テスト: 117件 passed
- Ruff: passed
- 既存基礎編の評価ロジックとCLI: 変更なし

## 既知の制約と次の確認

- JSON Schemaファイルは配布したが、コア依存を増やさないため通常検査は標準ライブラリによる明示的検査を使う。
- Markdown表はfixtureとして含むが、セル構造の抽出はApplied Lab 2まで実装しない。
- 画像・スキャンfixtureとOCR方式はApplied Lab 2のADR後に追加する。
- Applied Lab 1へ進む前に、データと評価問題を人が読み、数値、版、権限境界、回答不能の妥当性を確認する。
