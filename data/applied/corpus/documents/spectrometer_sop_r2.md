---
document_id: ari_spectrometer_sop_r2
title: 分光計 SP-4 校正手順 第2版
source: documents/spectrometer_sop_r2.md
document_type: standard_operating_procedure
organization: 架空先端材料研究所
project: 分析装置保守
revision: 2.0
published_date: 2026-04-15
language: ja
classification: internal
allowed_groups: [materials]
license_or_terms: MIT; synthetic training data
supersedes_document_id: ari_spectrometer_sop_r1
---

<!-- page: 1 -->
# 改訂概要

本書は教材用の架空手順書である。ドリフト監視結果を受け、定期校正周期、ウォームアップ時間、合格許容差を更新した。

# 校正周期

定期校正は60日ごとに行う。装置移動、光源交換、基準試料の逸脱があった場合は、周期内でも再校正する。

<!-- page: 2 -->
# 起動前確認

室温を20 ℃から24 ℃、相対湿度を40 %から60 %に保つ。基準ランプL-4を装着し、装置を30分間ウォームアップする。

# 基準測定

400 nm、550 nm、700 nmの3点を各3回測定する。各点の測定前に暗電流を記録する。

<!-- page: 3 -->
# 判定基準

各基準点の公称値との差が±0.5 nm以内なら合格とする。1点でも範囲外なら再測定し、再測定でも外れた場合は使用を停止する。

# 変更理由

第1版の運用記録で60日を超えた装置に緩やかな波長ドリフトが見られたため、予防的に基準を厳しくした。原因を特定したという意味ではない。

<!-- page: 4 -->
# 記録と異常時対応

装置ID、基準ランプID、環境条件、暗電流、各測定値、判定、実施者の仮名化IDを保存する。内部調整は行わず、範囲外が続く場合は修理担当へ引き渡す。

# 版の適用

2026年4月15日以降に開始する校正へ第2版を適用する。過去記録の判定を新しい許容差で書き換えない。
