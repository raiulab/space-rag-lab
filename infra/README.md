# AWS実習: Lambda + API Gateway + Amazon Bedrock

この構成は学習用の最小構成です。生成済みの小さなJSONL索引をLambdaへ同梱し、HTTP APIからBedrockを呼びます。多数文書・多数利用者を扱う本番構成では、索引更新をデプロイから分離し、S3、OpenSearch Serverless、Bedrock Knowledge Basesなどを比較してください。

## 前提

- AWS CLIとAWS SAM CLIがインストール済み
- デプロイ先AWSアカウントへの認証が完了済み
- 利用リージョンでAmazon Bedrockの対象モデルを呼び出せる
- 費用管理のためAWS Budgets等で通知を設定済み

モデルIDや利用可能リージョンは変わり得るため、デプロイ時に公式コンソールまたはドキュメントで確認します。アクセスキーをリポジトリへ保存しないでください。

## 1. ローカル成果物を作る

リポジトリのルートで実行します。

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m rag_lab.cli all
test -s data/index/index.jsonl
```

索引は `infra/template.yaml` の `CodeUri` によってコードと一緒にパッケージ化されます。教材文書だけが入っていることを確認してください。

## 2. 検証とビルド

```bash
sam validate --lint --template-file infra/template.yaml
sam build --template-file infra/template.yaml
```

オフライン生成器でLambdaの入出力だけ試す場合は、デプロイ時の `Generator` を `extractive` にします。Bedrock利用時は `bedrock` にします。

## 3. デプロイ

```bash
sam deploy --guided
```

質問に対して次を設定します。

- Stack Name: `space-rag-lab-dev`
- AWS Region: Bedrockモデルが利用可能なリージョン
- Parameter BedrockModelId: 利用可能なモデルまたは推論プロファイルID
- Parameter Generator: `bedrock`
- Allow SAM CLI IAM role creation: `Y`

デプロイ後のOutputにあるURLへ送信します。

```bash
curl -X POST 'OUTPUTのAskEndpoint' \
  -H 'content-type: application/json' \
  -d '{"question":"エウロパ探査機の通信遅延対策は？"}'
```

## 4. 観察するもの

- LambdaのDuration、Errors、Throttles
- Bedrockの応答時間とスロットリング
- 引用の文書ID・ページ・チャンクID
- 4xxと5xxで本文が適切に分かれているか
- ログへ質問本文を残す場合の個人情報・機密情報対策

テンプレートは同時実行数を2、ログ保持を14日へ抑えています。これは教材の初期値であり、実運用要件に合わせて変更します。IAMはBedrock呼び出しを許可していますが、本番では利用モデルのARNへさらに絞ってください。

## 5. 片付け

実習後は課金を止めるため、スタックを削除します。

```bash
sam delete --stack-name space-rag-lab-dev
```

CloudWatch Logs、S3のSAMパッケージ用バケット、AWS Budgetsの通知など、スタック外のリソースもコンソールで確認してください。

## 本番へ発展させる課題

1. 索引をS3またはOpenSearchへ移し、文書更新だけで再索引できるようにする。
2. API Gatewayへ認証、レート制限、WAFを追加する。
3. AWS Secrets ManagerまたはIAMロールで秘密情報を管理する。
4. X-Rayまたは構造化ログで検索時間と生成時間を分けて計測する。
5. Blue/Green方式でプロンプトとモデルを比較する。

公式資料:

- [Amazon Bedrock Knowledge Bases](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base.html)
- [Knowledge Basesの処理概要](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-how-it-works.html)
- [Amazon OpenSearch Serviceのベクトル検索](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/vector-search.html)
- [AWS Well-Architected Generative AI Lens](https://docs.aws.amazon.com/wellarchitected/latest/generative-ai-lens/)
