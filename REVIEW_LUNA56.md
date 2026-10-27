<!-- Reviewed by OpenAI Codex (gpt-6-luna) | Session ID: 01a17da7-14e2-7910-ab1f-c028d3235ef2 | Timestamp: 2026-10-27T22:58:44+09:00 -->

# `DESIGN_OPUS55.md` — Architecture & Security Review

## 総評

**判定: 条件付きで有望。ただし、現状の仕様をそのまま実装すると、提出期限・API互換性・実行安全性・評価指標の整合性で重大な失敗リスクがある。**

Nemotron のモデル階層、決定論的な検証器、監査記録を組み合わせる方針は、Coding and Agentic Engineering のデモとして筋が通っています。Simulation mode と各ステップの `source` 表示も、鍵なしで動く提出物を作るうえで有効です。

一方、設計書は未検証の外部仕様を「設定で吸収できる」と扱いすぎています。エンドポイント、MCP、Tavily、Nebius Serverless の契約は、環境変数の変更だけでは直せない可能性があります。また、サンドボックスの脅威モデル、HTTP サーバーの並行処理・リソース上限、メトリクスの算出法は、実装可能な仕様としてまだ不足しています。§4以降の本文が提示されていないため、そこで定義される予定のスキーマ・実装詳細は評価できません。

## 重大な指摘

### 1. 提出期限と内部目標が矛盾している

期限は **2026-10-31 02:00 JST** と記載されていますが、内部提出目標は **2026-10-30 18:00 JST** です。これは期限の8時間前ではなく、**期限の8時間後**です。日付・時刻のどれかが誤っており、リリース計画の根拠として使えません。

### 2. 外部 API 契約を「設定で直せる」とする前提が不十分

Nebius Token Factory の URL、モデル ID、推論パラメーター、Tavily の認証方式とレスポンス形状、Serverless の manifest/CLI は未確認事項のままです。A1〜A7は重要な実装依存です。たとえば、API が `response_format`、`chat_template_kwargs`、指定した `/models` パスをサポートしなければ、環境変数の変更だけでは解決しません。

`selfcheck` は疎通・認証・必要機能を個別に確認し、機能非対応を区別して報告する必要があります。モデル名の fuzzy match は候補の提案にとどめ、誤ったモデルを自動選択して実行してはいけません。

### 3. stdlib-only と展開仕様が食い違う

設計は runtime を Python stdlib のみに限定しますが、配置先の `python:3.12-slim` にそのバージョンが必ず含まれる保証はありません。また、配布可能な package metadata、実行エントリーポイント、Docker build context、`deploy.sh` の前提も提示範囲では明確ではありません。`pip install` をしない方針なら、コンテナ内で `python -m nemotron_forge...` が成立するファイル配置と作業ディレクトリを明記する必要があります。

### 4. ローカル sandbox は信頼境界として成立していない

`subprocess`、`rlimits`、AST 検査だけでは、敵対的な Python コードを安全に実行できるとはいえません。プロセス・ファイルシステム・ネットワーク・子プロセス・資源消費に対する制限の具体的な仕様がありません。AST gate は難読化・動的実行・危険な標準ライブラリ利用を完全には防止できません。

「一般用途の安全な sandbox ではない」という非目標と、外部入力を受け付ける MCP tool `forge_verify_code` は、互いに強く緊張しています。API を通じて任意コードを実行可能にするなら、ローカル実行を無効化する条件、入力制限、worker 隔離、最大出力・時間・メモリー・ファイル数、ネットワーク遮断と、隔離できない環境での拒否動作が必要です。`network: none` は「対応していれば」とするだけでは安全策になりません。

### 5. HTTP API の認証・CSRF・DoS 対策が不完全

認証を「bind host が loopback でない場合に必須」とするだけでは、プロキシ越しの公開、誤設定、ブラウザー利用を十分に扱えません。ブラウザー向け dashboard と bearer token の組み合わせでは、トークンの保管・送信方法、CSRF、Origin 検査、CORS、Host ヘッダー、DNS rebinding の扱いが定義されていません。

`ThreadingHTTPServer` についても、同時 run 数、キュー長、SSE 接続数、request body 上限、接続・アイドル timeout、worker の終了処理がありません。重い LLM 呼び出しや遅延した SSE 接続を多数受けると、スレッドとメモリーを消費し、サービス全体が応答不能になる可能性があります。

### 6. 実行状態と失敗結果の契約に曖昧さがある

状態一覧には `budget_capped` と `cancelled` がありますが、`budget_capped` が run の終端状態なのか、部分結果を保持した `completed` の属性なのかが不明です。`physical_check` は任意なのに、他状態との遷移・失敗時の最終状態も定義されていません。

`POST /api/runs` の同期モードが `200 + full result` を返す一方、非同期モードでは `202` です。同期モードの最大待ち時間、上限超過時の挙動、クライアント切断時の run 継続・キャンセル、再送による重複実行を仕様化してください。キャンセルも、すでに実行中の subprocess や HTTP request にどう伝播するかが必要です。

### 7. Retry・rate limit・circuit breaker の安全条件が不足

図と説明には retry、`Retry-After`、jitter、circuit breaker、token bucket がありますが、適用範囲と上限が定義されていません。特に `POST` の再試行では、同じ run の重複コストや副作用が起きます。リクエストの idempotency、リトライ可能なエラー分類、最大試行回数、総 deadline、応答本文のサイズ制限を指定してください。

rate limit では、プロセス単位の token bucket が複数 worker/replica 全体の制限を守る保証はありません。429 が続く場合に run をどう終端するか、`Retry-After` の不正値・上限値をどう扱うかも未定義です。provider ごとのフォールバックは便利ですが、認証失敗や不正リクエストのような恒久エラーをシミュレーションで隠してはなりません。

### 8. Audit trail の完全性・機密性が混同されている

hash chain と任意 HMAC は改ざん検出には役立ちますが、秘密情報を安全に保存する機構ではありません。イベントに prompt、コード、例外、URL、モデル出力が含まれる場合の保存項目、秘匿化、保持期間、エクスポート、アクセス制御を定義してください。API key のログ除外だけでなく、タスク本文や生成物に含まれる個人情報・秘密鍵・認証情報も対象です。

HMAC key が未設定なら監査ログは署名されず、複数 replica 間でイベント順序も保証されません。監査ログの永続化先、クラッシュ時の末尾破損、HMAC key のローテーション、監査取得権限が未指定です。`verified: true` が何を検証した結果なのか（hash chain のみか、HMAC も含むか）を API で区別してください。

### 9. Citation support ratio の定義が再現可能でない

検索結果の `score` やモデル判定だけでは、引用された主張が出典に支持されている根拠になりません。claim と source passage の対応付け、支持判定基準、複数出典・否定証拠・古い情報・取得失敗時の扱いが未定義です。`unsupported` を「削除」する場合、ユーザーが生成物から省略された事実を把握できるようにしてください。`extract` の取得失敗を「支持なし」と扱うのか「未検証」と扱うのかも分ける必要があります。

### 10. Cost と成果指標が測定仕様になっていない

`baseline_all_deep_usd`、`cost_savings_pct`、`tests_pass_rate` は、価格表、モデルの usage 欠損、試行・repair・fallback の費用をどう扱うかが明確でありません。simulation の料金や latency が実測値に見えると、hackathon の評価指標を誤認させます。live と simulated のメトリクスを分離し、推定 usage と実測 usage、モデル価格の出典・取得日を明示してください。

`tests_pass_rate` は、生成コードのテスト成功を品質全体の成功と誤解させる可能性があります。ベンチマークのシナリオ・固定 seed・採点基準・失敗ケース・all-deep baseline の実行条件がなければ、コスト削減率は比較できません。

## 要件・賞トラック適合性

- **Coding and Agentic Engineering:** 生成コード、テスト、修復、実行、security review の流れは要件に沿っています。ただし、信頼できる sandbox と再現可能な評価が示されるまで、実行安全性と品質の主張は裏付け不足です。
- **Best Apps and Agents:** dashboard、CLI、API、MCP は製品としての見せ方を支えます。ただし、実装範囲が大きく、提出までにすべての入口を完成・接続・文書化できるかがリスクです。優先順位と、未完成機能の明示が必要です。
- **Best Use of Tavily:** search と extract を使う構成は有力ですが、引用検証が本当に根拠を確認しているか、失敗時にどう表示するかが評価を左右します。Tavily API 契約・クレジットの予算・失敗時の動作も必要です。
- **Most Valuable Feedback:** `FeedbackRecorder` が開発中の実際の摩擦を記録する方針は適合します。ただし、デザインに書かれただけの想定イベントやシミュレーション上の障害を実体験として提出してはいけません。フィードバックの出所と再現条件が必要です。
- **提出成果物:** §10 のチェックリスト本文が提示されていません。少なくとも Devpost の提出ページ、公開可能な repository、demo video、セットアップ・実行手順、使用モデルと外部サービスの説明、制約・ライセンス、動作するデモ URL（該当する場合）、提出前のリンク検証が deliverable として必要です。設計上の「3-minute video walkthrough」だけでは提出要件を満たした確認になりません。

## API・プロトコルの確認事項

- MCP の記述は **JSON-RPC 2.0 の単発 HTTP request/response** と MCP の Streamable HTTP を同一視しないよう整理してください。プロトコルバージョン、HTTP transport のメッセージ形式、セッション・初期化・通知・batch の扱いを、採用する MCP 仕様と SDK の契約に合わせて固定し、独自互換層を実装する場合は準拠範囲を明記してください。
- `Origin` 検証だけでは HTTP MCP の認証・CSRF 対策にはなりません。`Host`、非ブラウザー client、loopback 以外の bind、認証なし接続をどう扱うかが必要です。
- `tools/call` の tool-level error と JSON-RPC error の使い分けを明記してください。スキーマ違反は MCP の tool エラーとして返すのか JSON-RPC `-32602` とするのか、クライアントとの期待を統一してください。
- Tavily の `Authorization: Bearer`、`/extract` の request/response、検索 credit の算出は実 API で確認が必要です。仕様が異なる場合に、局所的な adapter で変換できる契約を定義してください。
- Nebius の `/models` と `/chat/completions` のパス、モデル固有パラメーター、`usage`・拒否・空 choices・`finish_reason` の取り扱いを実機で確認してください。部分応答、空文字、JSON fence、切り詰められた JSON の処理も必要です。

## テスト容易性と再現性

テスト suite が **5秒未満**という目標だけでは、決定性や安全性の証拠になりません。設計には、次のテスト仕様が必要です。

- Simulation mode で同一入力・同一 `SIM_VERSION` の `result_digest` が一致し、ID・時刻のみが除外されること。
- HTTP provider の stub を使い、200/400/401/403/404/429/5xx、timeout、壊れた JSON、空 response、usage 欠落、`Retry-After` を検証すること。
- escalation、budget cap、修復上限、キャンセル、部分失敗、circuit open、fallback の全遷移を検証すること。
- subprocess timeout、出力肥大、メモリー制限、子プロセス生成、書き込み、ネットワークアクセスを含む sandbox の拒否テストを設計すること。OS ごとの差を明示し、隔離機能がない場合の fail-closed 動作を確認すること。
- MCP stdio で stdout が JSON-RPC 以外の出力を含まないこと、notifications/batches/初期化・不正プロトコル・oversized input を検証すること。
- SSE の切断・再接続・イベント順序・buffer 上限を検証すること。
- API schema の適合性テストと Devpost の提出物・リンクの完成確認を、リリースゲートにすること。

## 実装前に修正すべき設計項目

1. **日程を訂正する。** Deadline と内部 submit target の日付・時刻・タイムゾーンを一つの基準から再計算し、提出用の余裕時間を確保する。
2. **外部契約を確定する。** Token Factory、Tavily、MCP、Serverless を live API／公式仕様で確認し、確認日、対応パラメーター、失敗時の挙動を記録する。未対応機能は「環境変数で解決」とせず、機能を無効化するか adapter を定義する。
3. **最小提出スコープを固定する。** Coding and Agentic Engineering の一連のデモを先に成立させ、Dashboard・REST・MCP・Cosmos・Serverless のうち提出に不可欠な機能と optional 機能を明示する。
4. **sandbox の境界を定義する。** ローカルで実行可能なコードの脅威モデル、OS 依存の制限、リソース上限、ネットワーク遮断、隔離不能時の拒否を仕様化する。未信頼コードを安全に実行するとの主張は、実装とテストが確認できる範囲に限定する。
5. **HTTP/MCP を保護する。** bind address、認証、Origin/Host、CORS/CSRF、body・接続・同時実行の上限、SSE、MCP 初期化と transport の準拠範囲を固定する。公開 bind で認証が無効な構成は起動時に拒否する。
6. **状態と再試行契約を完成する。** 終端状態、同期実行 deadline、キャンセル伝播、idempotency、retryable error、最大 retry/cost、429・circuit-open 時の結果を定義する。認証・schema error を simulation fallback で隠さない。
7. **データ保護を仕様化する。** audit に保存するフィールド、redaction、ログ除外、保持期間、アクセス制御、HMAC の有無・ローテーションを明記する。simulation/live と推定/実測 telemetry を分ける。
8. **評価指標を再現可能にする。** 価格表の出典・日付、baseline の実行条件、repair を含むコスト、citation 判定根拠、固定シナリオ・seed・合否基準を定義する。シミュレーションの数値を実測効果として表示しない。
9. **提出ゲートを追加する。** 完成した Devpost submission、動画、README、ライセンス、公開 repository、デモの起動手順とリンクをチェックリスト化し、提出前に実際の提出先で確認する。

## 実装必須チェックリスト — Sakura `preview/Kimi-K2.7-Code`

- [ ] 内部提出目標を訂正済み期限に合わせ、README・設計書・提出計画で統一する。
- [ ] Simulation mode をオフラインで実行でき、全 run に `live` / `simulated` / `fallback` を表示する。
- [ ] Simulation の固定 seed、固定シナリオ、`result_digest` の決定性をテストする。
- [ ] Nebius と Tavily の API 契約を実機確認し、timeout・429・5xx・認証失敗・404・不正 JSON・空応答・usage 欠落の処理を実装する。
- [ ] Retry 回数、全体 deadline、`Retry-After` 上限、idempotency、budget cap を実装し、恒久エラーを fallback で隠さない。
- [ ] モデル ID を未確認の fuzzy match で自動選択せず、`selfcheck` で候補と機能対応を報告する。
- [ ] `TaskRequest`、provider response、`RunResult`、MCP tool input/output をスキーマ検証し、切り詰め出力・JSON fence・部分応答をテストする。
- [ ] `budget_capped`、`cancelled`、失敗、部分成功の状態遷移と同期/非同期 API 契約を統一する。
- [ ] 公開 bind で認証なしを拒否し、body・接続・同時 run・SSE・キューに上限を設ける。
- [ ] `forge_verify_code` の入力・出力・時間・資源を制限し、隔離できない場合は拒否する。AST 検査を sandbox の代替として扱わない。
- [ ] Audit log の redaction、HMAC 未設定時の表示、保持期間、アクセス制御を実装する。生の秘密・認証情報・全文 reasoning をログや UI に出さない。
- [ ] Citation を `supported` / `weak` / `unsupported` / `unverified` に区別し、判定根拠と取得失敗をユーザーに示す。
- [ ] Simulation と live、推定値と実測値を metrics で区別し、baseline と費用計算の条件を記録する。
- [ ] MCP transport/version の準拠範囲を固定し、stdio stdout、初期化、notification、batch、Origin/Host、巨大入力を検証する。
- [ ] Devpost の提出本文、demo video、README、公開 repository、必要なデプロイ情報、リンクを提出前チェックに含める。
- [ ] CI とデモ手順で再現できる deterministic test suite を用意し、期限前にクリーン環境で `git clone` から実演する。
