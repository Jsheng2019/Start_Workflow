# 工作流 5：复合操作（Composite Action）— Hello World 入门

> **受众：** 零基础，想了解复合操作的最简语法和效果。
>
> **文件：** `.github/actions/node-ci-gate/action.yml` + `.github/workflows/demo-composite.yml`

---

## 1. 这是什么？

复合操作 = 把多个 `run` 步骤打包成一个**可复用单元**，用 `uses` 一行调用。

```
不用复合操作:                  用复合操作:
  - run: echo step1               - uses: ./.github/actions/hello
  - run: echo step2                 with:
  - run: echo step3                   name: 'World'
```

---

## 2. action.yml（定义端）逐段解析

```yaml
# .github/actions/node-ci-gate/action.yml

name: Hello Printer                          # UI 中显示的名称
description: 打印问候语的教学 demo

# ── 输入：调用方传进来的参数 ──
inputs:
  name:
    description: '要打招呼的人名'
    required: false
    default: 'World'                         # 可选参数必须有 default

# ── 输出：返回给调用方的结果 ──
outputs:
  greeting:
    description: '组装好的问候语'
    value: ${{ steps.assemble.outputs.greeting }}  # 引用了内部 step 的 output

# ── 执行逻辑 ──
runs:
  using: composite                           # 必须写 "composite"
  steps:                                     # 语法和 workflow job steps 完全一样
    - name: Step 1
      shell: bash
      run: echo "Hello, ${{ inputs.name }}!"

    - name: Step 2
      shell: bash
      run: echo "Today is $(date +%Y-%m-%d)"

    - name: Step 3 — 设置输出
      id: assemble
      shell: bash
      run: |
        echo "greeting=Hello, ${{ inputs.name }}! Have a nice day." >> "$GITHUB_OUTPUT"
```

### 三个关键规则

| 规则 | 说明 |
|------|------|
| `runs.using: composite` | 必须声明 |
| 每个 `run` 步骤必须有 `shell` | `shell: bash` |
| output 的 `value` 引用 `${{ steps.<内部step的id>.outputs.<名字> }}` | 透传机制 |

---

## 3. 工作流（调用端）

```yaml
# .github/workflows/demo-composite.yml

name: Demo - Composite Action
on: workflow_dispatch                          # 手动触发

jobs:
  hello:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4              # 先 checkout（复合操作在仓库里）

      - name: Run hello printer
        id: hello                              # 给 step 一个 id，用于读取输出
        uses: ./.github/actions/node-ci-gate   # 引用本地复合操作
        with:
          name: 'GitHub Actions'               # 传参

      - name: Show output
        run: echo "${{ steps.hello.outputs.greeting }}"  # 读取输出
```

---

## 4. 运行方式

1. 推送到 `Jsheng2019/Start_Workflow`
2. Actions tab → **"Demo - Composite Action"** → Run workflow
3. 在 job log 中看到 3 个 step 依次打印，最后打印 composite action 的返回值
