# Arc → Zen · Agent Skill

把 Arc 的使用习惯迁到 Zen：工作区、容器、收藏、固定标签、书签、扩展数据、快捷键，以及可选的 Little Arc 风格外链小窗。

一个可安装到 **Codex / Claude Code / 兼容 Agent Skills 的代理**中的技能包。来自一次实际 macOS 迁移的操作经验，附可运行脚本、验证步骤和回滚工具。

[English](README.md) · [技能入口](skills/arc-to-zen/SKILL.md) · [完整流程](skills/arc-to-zen/references/migration-workflow.md)

## 安装后直接交给 Agent

需要 Python 3.9+ 和 Git。迁移脚本使用 Python 标准库，无需 `pip install`。

```sh
git clone https://github.com/AntonyLL/arc-to-zen-skill.git
cd arc-to-zen-skill
python3 install.py --agent codex
```

Claude Code：

```sh
python3 install.py --agent claude
```

其他代理可用 `--agent agents` 安装至 `~/.agents/skills/arc-to-zen`，或用 `--dest /你的技能目录/arc-to-zen`。已有同名目录时安装器会停止，避免覆盖自定义版本。也可以下载仓库 ZIP，解压后执行安装命令。

打开新对话，输入：

> 使用 $arc-to-zen 帮我从 Arc 迁移到 Zen，保留工作区、收藏、固定标签、书签、扩展保存内容和快捷键。先检查当前配置，再执行迁移并验证重启后的结果。

Claude Code 等使用斜杠命令的工具可调用 `/arc-to-zen`。也可以直接让 Agent 阅读 `skills/arc-to-zen/SKILL.md`。

**安装技能只复制技能文件。** 迁移、安装扩展、设置外链小窗和更改系统默认浏览器，均在实际调用技能时按你的需求进行。

## 包含什么

| 内容 | 实现方式 |
|---|---|
| Spaces、Favorites、固定/普通标签 | 原生会话适配器，保留已有 Zen 数据，新增迁入内容 |
| Arc Profile → Zen 容器 | 每个 Arc Profile 分配独立新容器；共享 Profile 的 Spaces 共用容器 |
| 多 Profile 书签、侧栏存档 | 生成可导入的 HTML，保留嵌套书签和重复网址 |
| 扩展、OneTab、uBlock 设置、保存内容 | Agent 按官方导入/导出流程处理，记录不兼容项 |
| 快捷键、主题、布局 | 根据你的实际配置逐项对应和检查冲突 |
| 备份、校验、回滚 | 文件哈希、完整 Profile 备份、原子文件替换和恢复命令 |
| Little Arc 替代 | 可选 Swift/WebKit 小窗源码，单窗复用、⌘O 交给 Zen |
| Easel / FigJam | 固定画板、系统快捷键、按工作区路由的操作指南 |

## 适用范围

- **原生写入和小窗：macOS。** Arc 和 Zen 先正常安装、启动一次。小窗构建另需 macOS 13+ 与 Xcode Command Line Tools。
- 原始迁移基于 **Arc 1.169.0 → Zen 1.23.4b**。新版浏览器需检查实际数据格式。
- 原生适配器处理**含置顶（可嵌套）文件夹的侧栏、单个已保存 Zen 窗口**。文件夹会转换为 Zen 原生文件夹。分屏及非置顶区域的文件夹会导出并交给 Agent 在 Zen 中重建；遇到这些结构时不直接写入原生会话。
- 容器保留账户隔离的组织关系；网站需重新登录。密码、Cookies、支付信息、钱包密钥、历史记录不在默认迁移范围。
- 原生小窗使用独立、持久的 WebKit 登录状态；“在 Zen 中打开”转交当前 URL。它不共享 Zen 的扩展、容器或未提交表单。

迁移前的一项实际经验：**先检查 Zen 的“退出时清理 Cookies/网站数据”设置，再重启**，避免意外丢失原有登录。

## 直接使用脚本

让 Agent 自动发现路径即可；下面是手动入口。工作目录应位于浏览器 Profile 和本仓库之外。

```sh
python3 skills/arc-to-zen/scripts/migrate.py discover
python3 skills/arc-to-zen/scripts/migrate.py inspect \
  --arc "$HOME/Library/Application Support/Arc"

# 只导出本地书签和迁移清单，不改浏览器。
python3 skills/arc-to-zen/scripts/migrate.py prepare \
  --arc "$HOME/Library/Application Support/Arc" \
  --out "$HOME/Documents/Arc-to-Zen-export"
```

关闭 Zen 后，使用新的工作目录并加 `--zen-profile '/实际的 Zen Profile 路径'` 可准备原生迁移。审阅生成的 `manifest.json` 后执行：

```sh
python3 skills/arc-to-zen/scripts/migrate.py apply --work '/你的迁移工作目录'
python3 skills/arc-to-zen/scripts/migrate.py verify --work '/你的迁移工作目录'
# 如需恢复，先退出 Zen。回滚前的完整状态也会被保留。
python3 skills/arc-to-zen/scripts/migrate.py rollback --work '/你的迁移工作目录'
```

书签通过 Zen 的 **Import HTML** 导入。只导入一次，重复导入会产生重复书签。`verify` 是磁盘核对，Agent 还需检查 UI 和重启后的持久性。

## 测试与数据

```sh
python3 -m unittest discover -s tests -v
```

测试用临时合成 Profile 检查解析、导出、增量会话写入、过期计划拦截、失败恢复和回滚。[可选 GitHub Actions 模板](examples/github-actions.yml)可放入 `.github/workflows/test.yml`，自动运行 Python 测试并构建 Swift 小窗；当前发布未启用远程 CI。原始方案的本机验证与通用脚本的自动测试分开记录；没有把通用版本宣称为已经完成一次新的真实迁移。

仓库只包含通用代码、说明和合成测试数据；没有真实书签、浏览器 Profile、登录数据或个人画板地址。实际运行产生的文件保留在使用者本地。源码采用 [MIT License](LICENSE)。
