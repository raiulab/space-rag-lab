# Lab 8 ローカルデプロイ前準備の受け入れ結果

- 実施日: 2026-10-09
- AWS認証情報・AWS API・SAM CLI: 未使用
- 生成器: 抽出式
- 対象: `infra/template.yaml`、Lambda相当のローカルHTTP入出力

ローカルHTTPスモークテストはstatus 200、回答可能、引用ありで成功した。

| 判定 | 項目 |
| --- | --- |
| passed | 認証情報の非埋め込み |
| passed | Lambda timeout 30秒 |
| passed | 予約同時実行数2 |
| passed | CloudWatch Logs保持14日 |
| passed | Lambda tracing有効 |
| review | HTTP API認証が未設定 |
| review | Bedrock Resourceが利用モデルARNへ未限定 |
| review | 予算通知はテンプレート外 |

ローカル学習記録にはテンプレートのSHA-256、判定コード、HTTP status、回答可能性、引用ID、利用者のIAM・料金・削除計画を保存する。回答本文、チャンク本文、AWS認証情報は保存しない。

この受け入れ結果は、AWSへの実デプロイ成功を示さない。実AWSは利用者のアカウント、認証、利用可能モデル、料金承認を伴う任意実習とする。
