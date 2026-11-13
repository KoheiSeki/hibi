# Hibi

## docstring と JSDoc

コードを書くときは、言語ごとに次のドキュメントを付ける。日本語で書く。

### Python(`apps/api`)

- 関数、メソッド、クラスに docstring を付ける。private(`_` 始まり)でも、振る舞いや理由が名前から分からないものには付ける。テスト関数には付けない
- 形式は Google style。見出しは `Args:`、`Returns:`、`Raises:`、dataclass のフィールドは `Attributes:`
- 1 行目は「何をするか」を 1 文で書く。長い説明は 1 行空けて続ける。「なぜそうするか」(例外や境界の扱い、順序の理由)を、実装を読めば分かる内容より優先して書く
- `Args:` と `Returns:` に型は書かない。型は型注釈に任せる
- 全角括弧は使わない。ruff の RUF002 と RUF003 が検出する。括弧は半角にするか、言い換える
- router 関数の docstring は OpenAPI の `description` になり、生成される TypeScript client にも載る。API の利用者が読む文として書く

### TypeScript(`apps/web`、`packages`)

- export する関数、React コンポーネント、型に JSDoc(`/** ... */`)を付ける。export しないものは、理由が自明でないときだけ付ける。テストには付けない
- 引数は `@param 名前 - 説明`、戻り値は `@returns 説明`。`{型}` は書かない。型は TypeScript に任せる
- 1 行目は「何をするか」を 1 文で書く。「なぜそうするか」を実装の説明より優先して書く
- `packages/api-client/src/generated/` は生成物なので手で書かない。説明を変えたいときは、API 側の docstring を直して `just openapi` で再生成する
