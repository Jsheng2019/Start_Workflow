# Release 工作流详解

文件路径：`.github/workflows/release.yml`

---

## 整体结构概览

```
name → on(tag push + workflow_dispatch) → jobs → build-and-test → create-release → notify
```

---

## 逐行说明

### 第 1 行：`name: Release`

用于自动化软件发布流程的工作流。

---

### 第 3-16 行：`on:` Tag 触发 + 手动触发

```yaml
on:
  push:
    tags:
      - 'v*.*.*'
  workflow_dispatch:
    inputs: ...
```

- **`push.tags:`** — 只监听 tag 的推送，而不是所有 push 事件。
- **`'v*.*.*'`** — **Glob 模式匹配**。匹配如 `v1.0.0`、`v2.14.3` 的语义化版本标签。
  - `*` 匹配任意字符串，`.` 匹配 `.` 字符。
  - 不会匹配 `v1.0`（少了一级）或 `release-1.0.0`（前缀不匹配）。

#### 为什么用 tag 触发 release？

这是 GitHub Actions 的标准实践：
1. 开发者推送一个 tag → 工作流自动构建并创建 GitHub Release
2. 版本号从 tag 中提取，确保一致性
3. 避免了手动填写版本号的可能错误

#### workflow_dispatch 的额外参数

```yaml
version:
  description: '发布版本号（如 1.2.0）'
  required: true
  type: string
prerelease:
  description: '是否为预发布版本？'
  required: false
  type: boolean
  default: false
```

- **`type: boolean`** — 渲染为复选框，用户勾选/取消。
- 手动触发给了团队一个不需要创建 tag 就能发布的后备方案。

---

### 第 18-56 行：`build-and-test` Job

```yaml
build-and-test:
  runs-on: ubuntu-latest
```

这个 Job 的结构与 CI 类似，关键区别在最后的打包步骤。

#### 打包构建产物

```yaml
- name: Package release assets
  run: |
    mkdir -p release
    if [ -d "dist" ]; then
      tar -czf release/dist.tar.gz dist/
    fi
    if [ -f "package.json" ]; then
      cp package.json release/
    fi
```

- **条件打包**：只有在文件/目录存在时才打包，避免报错。
- **`tar -czf`** — 创建 gzip 压缩的 tar 归档文件。
  - `-c` — create
  - `-z` — gzip 压缩
  - `-f` — 指定文件名
- **目的**：将多个构建产物打包成一个便于下载的归档文件。

```yaml
- name: Upload release assets for next job
  uses: actions/upload-artifact@v4
  with:
    name: release-assets
    path: release/
```

- 上传为 workflow artifact，在下个 job 中通过 `download-artifact` 获取。

---

### 第 58-108 行：`create-release` Job — 核心发布逻辑

```yaml
create-release:
  needs: build-and-test
  runs-on: ubuntu-latest
  permissions:
    contents: write
  outputs:
    upload_url: ${{ steps.create-release.outputs.upload_url }}
```

- **`permissions.contents: write`** — 创建 Release 需要仓库内容的写权限。
- **`outputs.upload_url`** — `softprops/action-gh-release` 会输出一个 `upload_url`，可用于上传额外资源。这里将其传给下游 job。

#### 下载产物

```yaml
- uses: actions/download-artifact@v4
  with:
    name: release-assets
    path: release/
```

- **`actions/download-artifact@v4`** — 与 `upload-artifact` 配对使用，下载之前上传的产物。
- **`name:`** 必须与上传时的名称完全一致。

#### 版本号提取逻辑

```yaml
- name: Determine version
  id: version
  run: |
    if [ "${{ github.event_name }}" = "push" ]; then
      VERSION="${{ github.ref_name }}"
      VERSION="${VERSION#v}"
    else
      VERSION="${{ github.event.inputs.version }}"
      IS_PRERELEASE="${{ github.event.inputs.prerelease }}"
    fi
    echo "version=$VERSION" >> $GITHUB_OUTPUT
    echo "is_prerelease=${IS_PRERELEASE:-false}" >> $GITHUB_OUTPUT
```

- **`github.ref_name`** — 触发工作流的 ref 的简短名称。对于 tag 触发 (`refs/tags/v1.2.3`)，它的值是 `v1.2.3`。
- **`${VERSION#v}`** — Bash 参数扩展，去掉开头的 `v` 前缀。`v1.2.3` → `1.2.3`。
- **`${IS_PRERELEASE:-false}`** — Bash 参数扩展，如果 `IS_PRERELEASE` 未设置或为空，则使用 `false` 作为默认值。
- **双路径设计**：
  - tag 触发 → 版本号从 tag 推导
  - 手动触发 → 版本号从用户输入获取

#### 自动生成 Changelog

```yaml
- name: Generate changelog
  id: changelog
  uses: mikepenz/release-changelog-builder-action@v4
  with:
    fromTag: ${{ github.ref }}
    toTag: ${{ github.ref }}
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

- **`mikepenz/release-changelog-builder-action@v4`** — 社区 Action，自动从提交历史中生成变更日志。
- **`fromTag:` / `toTag:`** — 指定 changelog 的范围。这里 from 和 to 相同，工具会自动找到前一个 tag 作为起始点。
- **工作原理**：收集两次 tag 之间的所有 PR 标题和 commit 信息，按类型（feat、fix 等）分类整理输出。

#### 创建 GitHub Release

```yaml
- uses: softprops/action-gh-release@v2
  with:
    name: Release ${{ steps.version.outputs.version }}
    tag_name: ${{ github.ref_name }}
    body: ${{ steps.changelog.outputs.changelog }}
    prerelease: ${{ steps.version.outputs.is_prerelease }}
    files: release/**
    make_latest: true
```

- **`softprops/action-gh-release@v2`** — 最流行的创建 GitHub Release 的 Action。
- **`name:`** — Release 的标题，显示在 Releases 页面。
- **`tag_name:`** — 关联的 git tag。
- **`body:`** — Release 的描述内容，这里使用自动生成的 changelog。
- **`prerelease:`** — 是否为预发布版本。预发布版本在 GitHub 上有特殊标识，不会作为 latest release 显示。
- **`files: release/**`** — 上传 `release/` 目录下的所有文件作为 Release 附件。
- **`make_latest: true`** — 将此 Release 标记为 latest（最新的稳定版）。

---

### 第 110-126 行：`notify` Job — 发布后处理

```yaml
notify:
  needs: create-release
  runs-on: ubuntu-latest
  if: always()
```

- **`if: always()`** — 无论发布成功还是失败，都会运行通知步骤。
- 如果省略 `if: always()`，当 `create-release` 失败时，`notify` 会被跳过（默认行为是 `success()`）。

#### 条件通知分支

```yaml
- name: Notify on success
  if: needs.create-release.result == 'success'
  run: echo "Release published successfully!"

- name: Notify on failure
  if: needs.create-release.result == 'failure'
  run: echo "Release failed! Please check the logs."
```

- **`needs.create-release.result`** — 检查依赖 job 的执行结果，而不只是当前 job 的步骤结果。
- **`result` 的可能值**：
  - `success` — 所有步骤成功
  - `failure` — 有步骤失败
  - `cancelled` — 被手动取消
  - `skipped` — 被条件跳过
- **实际场景**：成功时发 Slack 通知 / 失败时发告警。当前用 `echo` 占位，实际项目可替换为 `slackapi/slack-github-action` 或 `actions/email-notification`。

---

## 关键概念总结

| 概念 | 说明 |
|------|------|
| `push.tags` | 只在推送 tag 时触发（如 `v1.0.0`） |
| glob 模式 `v*.*.*` | 匹配语义化版本标签 |
| `github.ref_name` | 短 ref 名称，tag 时为 `v1.2.3` |
| `actions/download-artifact@v4` | 下载之前上传的 workflow artifact |
| `softprops/action-gh-release@v2` | 创建 GitHub Release 并上传附件 |
| `mikepenz/release-changelog-builder-action` | 自动从提交历史生成 changelog |
| `prerelease` | 标记为预发布版本 |
| `needs.<job>.result` | 检查依赖 job 的执行结果 |
| `make_latest` | 将 Release 标记为 latest |
