# Security Policy

## Supported versions

現在は最新の`0.3.x`を対象にセキュリティ修正を行います。

## Reporting a vulnerability

公開後は、GitHubリポジトリのSecurityタブにあるPrivate vulnerability reportingまたはSecurity Advisoryから非公開で報告してください。有効化されていない場合は、秘密情報を含めずにIssueで連絡方法を問い合わせてください。

認証情報、個人情報、未公開の脆弱性詳細を公開Issueへ投稿しないでください。報告には影響範囲、再現条件、確認したバージョンを含めてください。

## Local execution boundary

- 学習UIは既定で`127.0.0.1`だけを待ち受けます。信頼できないネットワークへ公開しないでください。
- アップロードしたPDFは信頼された命令ではなくデータとして扱います。機密文書や利用条件が不明な文書を入力しないでください。
- `.rag_lab/`には個人の進捗と抽出結果が保存される場合があります。共有前に内容を確認してください。
- BedrockとAWS機能は任意です。長期認証情報をソース、`.env`、レポートへ保存しないでください。
- Lab 4のBedrock実行では、質問、取得チャンク本文、プロンプトがAWSへ送信されます。機密文書や外部送信の許可がない文書では実行しないでください。
- Lab 4 UIはアクセスキーを受け取らず、料金とデータ送信を明示確認した場合だけ実API呼び出しを有効にします。失敗時の例外全文、モデルID、回答本文、チャンク本文は学習記録へ保存しません。
- この教材は本番向けマルチユーザーサービスとしての防御や隔離を提供しません。

## Repository controls

- GitHub Secret scanningとpush protectionを有効にします。
- Python依存関係はDependabotと`pip-audit`で検査します。
- PythonコードはCodeQLで検査します。
- GitHub Actionsは完全なcommit SHAへ固定し、既定のworkflow権限を読み取りに限定します。
- `main`はCIとセキュリティ検査を通した変更だけを取り込み、force pushと削除を禁止します。

## Known security limitations

- FastAPIとAWSサンプルは、認証、認可、レート制限を備えた本番APIではありません。
- PDFはサイズ、ページ数、シグネチャ、暗号化を検査しますが、解析処理は別プロセスやOS sandboxへ隔離していません。出所を信頼できないPDFを処理しないでください。
- 依存関係のバージョン範囲は教材の導入しやすさを優先しています。再現性や規制要件がある配布では、別途lockファイルとSBOMを作成してください。
