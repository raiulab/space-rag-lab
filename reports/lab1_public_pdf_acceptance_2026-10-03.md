# Lab 1 公開PDF受け入れ試験

- 実行日時（UTC）: `2026-10-03T11:05:36.406204+00:00`
- 結果: `passed_with_limitations`
- 手動判定: `accepted_with_limitations`

## 資料

- 表示ファイル名: `space-rag-lab-nasa-tm-105232.pdf`
- 文書名: Effect of Particle Size of Martian Dust on the Degradation of Photovoltaic Cell Performance
- 出典URL: https://ntrs.nasa.gov/api/citations/19920001915/downloads/19920001915.pdf
- カタログURL: https://ntrs.nasa.gov/citations/19920001915
- 配布区分: Public
- 利用条件: Work of the US Gov. Public Use Permitted. NASAを出典として明記し、NASAによる推奨・承認を示唆しない。
- SHA-256: `aa4b3ea139677211c076da649d2cb8c3d3a4448352cd0ad58dc8dba62836f09e`
- ファイルサイズ: 7159446 bytes

第三者PDF本体と抽出本文は、このリポジトリへ保存していない。

## 抽出設定と結果

- 抽出器: `pypdf 6.19.0`
- chunk_size: `650`
- ページ数: 17
- チャンク数: 58
- 抽出状態: `ok`
- 空ページ数: 0
- ページ文字数（最小 / 中央値 / 最大）: 144 / 1127 / 2965
- 警告コード: なし

## 確認結果

| 検査 | 結果 | 内容 |
| --- | --- | --- |
| `text_extraction` | PASS | PDF抽出状態がokである: ok |
| `chunks_created` | PASS | 1件以上のチャンクを生成した: 58件 |
| `provenance_complete` | PASS | 全チャンクに文書ID・ページ・節・出典がある |
| `visual_pages_confirmed` | PASS | 先頭・中央・末尾ページを元PDFと目視比較した |
| `manual_decision` | PASS | 手動判定を記録した: accepted_with_limitations |

- 必須確認ページ（先頭・中央・末尾）: 1, 9, 17
- 目視確認したページ: 1, 9, 17
- 観察: 1ページ目は表題・著者・会議情報を抽出できたが、手書き管理番号にOCR由来のノイズがある。9ページ目の参考文献は読める順序で抽出された。17ページ目の帳票は主要項目を抽出できたが、表のセル境界と読み順は完全には保持されない。これは初期版で表構造抽出を対象外としている既知の制約であり、文字レイヤー抽出とページ出典保持の受け入れ条件は満たす。

## 判定上の注意

この試験は、文字レイヤー抽出、チャンク生成、出典保持、および代表ページの
目視比較を確認する。段組み、表、図、脚注の構造復元やOCR精度は、初期版の
合格条件には含めない。抽出文書は証拠であり、アプリへの命令として扱わない。
