# 一级市场每日资讯 Agent

用一个小应用练习如何在 GitHub 维护自己的仓库。

第一版流程：**RSS 资讯 → 融资/创投关键词筛选 → 时间筛选 → 去重 → Markdown 简报**。
目前使用规则筛选和原文摘要摘录，没有调用大模型；邮件、飞书等主动推送作为后续练习。

## 1. 本地运行

需要 Python 3.10 或更高版本，使用标准库，无需安装依赖。

在 PowerShell 中进入项目目录：

```powershell
cd D:\APPdata\codex\github_practicing
python agent.py --demo
```

离线示例会生成 `output/demo.md`。示例新闻是虚构的，专门用于验证流程。

读取真实资讯：

```powershell
python agent.py
```

结果写入 `output/digest-YYYY-MM-DD.md`，日期按北京时间计算。
默认筛选最近 24 小时内发布的新闻，没有匹配时也会生成说明，避免把旧闻当作今日资讯。
部分来源失败时会在简报中注明；所有来源失败时以非零状态退出。

默认源是 TechCrunch Venture 和 Crunchbase News，以英文资讯为主。
可在 `config.json` 调整 RSS 地址、关键词、时间窗口和最多显示条数。
关键词仅用于初筛，可能漏报或误报；简报保留原文链接以便核对。

## 2. 每日自动生成

`.github/workflows/daily-digest.yml` 配置每天 **北京时间 08:17** 运行，也支持手动触发：

1. 打开仓库的 **Actions** 页面。
2. 选择 **Daily digest**，点击 **Run workflow**。
3. 等待完成，在运行详情的 **Artifacts** 下载 `daily-digest`。
4. 运行摘要中也会展示当天简报。

GitHub 定时任务可能延迟，需工作流位于默认分支且 Actions 已启用。
简报保留为运行产物，不会每天向源码仓库写入提交。
当前还没有配置邮件或聊天工具推送。

## 3. 理解第一次 push

这个仓库原本已经有一次提交，因此从 `git clone` 开始。
以下命令是操作说明，**当前目录已克隆后，不要重复 clone**。

```powershell
git clone https://github.com/qipengxiang504-web/practice.git
cd practice
```

日常保存并上传一版代码的流程：

```powershell
# 看清改了哪些文件
git status
git diff

# 运行检查
python -m unittest discover -s tests -v
python agent.py --demo

# 选择要放进本次版本的文件
git add README.md agent.py config.json examples tests .github .gitignore .gitattributes
git diff --cached --stat

# 在本机保存一个版本（此时还没上传）
git commit -m "feat: add primary market daily digest starter"

# 把本地提交上传到 GitHub
git push -u origin main
```

| 命令/概念 | 作用 |
| --- | --- |
| 工作区 | 你正在编辑的文件 |
| `git add` | 把选定改动放入暂存区 |
| `git commit` | 把暂存区保存为本地版本 |
| `origin` | 克隆时自动配置的远程仓库别名 |
| `main` | 当前主分支名称 |
| `git push` | 把本地提交上传到远程仓库 |

上传后检查：

```powershell
git status -sb
git log -3 --oneline
git rev-parse HEAD
git ls-remote origin refs/heads/main
```

最后两条命令显示的提交哈希一致，说明本地这一版已到 GitHub。
GitHub 上的 **Checks** 工作流会在 push 和 pull request 时运行离线测试。

## 4. 练习下一次更新

第一次上传成功后，可以把 `config.json` 的 `max_items` 从 10 改为 5，完整练习一次更新：

```powershell
# 编辑前，确认工作区干净，再同步远程
git status
git pull --ff-only

# 编辑 config.json 后
python -m unittest discover -s tests -v
python agent.py --demo
git diff
git add config.json
git commit -m "chore: limit daily digest to five items"
git push
```

以后再练习分支、Pull Request、解决冲突，以及接入推送渠道和 AI 摘要。
如果未来需要 API key 或 webhook，请使用环境变量或 GitHub Actions Secrets；不要写入源码。
`.gitignore` 已忽略 `.env`、运行产物和 Python 缓存。

## 文件说明

```text
agent.py                            资讯读取、筛选与简报生成
config.json                         资讯源与筛选配置
examples/sample.xml                 离线示例新闻（虚构）
tests/test_agent.py                  核心行为测试
.github/workflows/checks.yml         每次更新的自动检查
.github/workflows/daily-digest.yml   每日生成与手动运行
output/                             本地生成结果（不提交）
```

参考：[GitHub 首次上传说明](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github)、[工作流定时触发说明](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)。
