# 応用編A0 合成データ

このディレクトリは、研究所文書RAG応用編のMilestone A0で使用する公開可能な教材fixtureです。文書、組織、装置、ロット、数値はすべて架空であり、実際の研究、製品、安全判断には使用できません。リポジトリのMIT Licenseに従って利用できます。

## 構成

- `corpus/manifest.json`: datasetと8文書のmetadata、checksum、改訂関係
- `corpus/documents/`: 合成Markdown文書8件・32ページ相当
- `evaluation/gold.jsonl`: 回答可能性と権限境界を含む評価case 29件
- `schemas/`: JSON Schema draft 2020-12によるデータ契約

`public`、`internal`、`restricted`はアクセス制御を学ぶための合成ラベルです。付属文書自体に秘密情報はありません。教材上の権限なしcaseであっても、実在組織の認証・認可を再現するものではありません。

## オフライン検査

プロジェクトルートで次を実行します。ネットワーク、APIキー、追加ライブラリは不要です。

```bash
python -m rag_lab.applied.corpus data/applied
```

`dataset_sha256`は、各文書の`document_id:sha256`をdocument ID順に並べ、各行末へLFを付けたUTF-8バイト列のSHA-256です。ローカル絶対パスや本文をmanifestへ埋め込まずに、datasetの構成を再現確認できます。

利用者自身の実データはこのディレクトリへ追加せず、Git対象外の`.rag_lab/applied/`へ保存してください。OCR画像、抽出本文、索引、監査ログもコミットしません。
