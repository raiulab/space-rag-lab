# Changelog

このプロジェクトの利用者に影響する変更を記録します。

## [0.1.1] - 2026-10-09

公開リポジトリと任意APIのセキュリティを強化したメンテナンスリリースです。

### Added

- Python依存関係を検査する`pip-audit` CI
- Pythonコードを検査するCodeQL workflow
- pipとGitHub Actionsを月次確認するDependabot設定
- Lambda入力検証とエラー秘匿の回帰テスト

### Changed

- GitHub Actionsを検証済みcommit SHAへ固定
- Lambdaの質問長をローカルAPIと同じ2〜500文字へ統一
- 内部例外の型・メッセージをHTTP 500レスポンスへ含めないよう変更
- ローカルAPIとPDF解析のセキュリティ境界を文書化

### Security

- GitHub Secret scanning、push protection、Dependabot security updates、private vulnerability reportingを有効化
- `main`のforce push・削除を禁止し、必須CIを設定

## [0.1.0] - 2026-10-06

初回公開版です。

### Added

- APIキー不要で動作する文書加工、HashEmbedding、dense・BM25・hybrid検索、抽出式RAG、評価CLI
- 4件の架空宇宙技術文書と10問の評価データ
- Lab 1〜3を段階的に進めるStreamlitローカル学習UI
- 文字レイヤー付きPDFのページ抽出、品質警告、出典保持、ローカルdataset保存
- 公開PDFを本文なしで検査記録する受け入れコマンド
- 任意のFastAPI、Amazon Bedrock生成器、AWS SAM教材
- Python 3.10〜3.12のCIと公開向け文書

### Known limitations

- ローカル学習UIはLab 1〜3までです。Lab 4〜8は教材、CLI、一部基盤が中心です。
- PDFのOCR、表構造、図、一般画像解析には対応していません。
- HashEmbeddingと抽出式生成器は学習用ベースラインであり、本格的な意味検索・LLMではありません。
- 回答不能問題の誤判定を含む既知の失敗を、Lab 6・7の改善教材として残しています。
- AWS SAMの実デプロイは未検証です。
