# 仓库目录与命名规范

## Python 代码与测试目录

业务代码采用 `src/` 布局。宿主提供协议、认证、传输和安装运行机制；四个业务 adapter 位于独立 leaf package，不保留旧业务运行时。

```text
dogopencli/
├── pyproject.toml                 # 包元数据、依赖、CLI 入口及检查配置
├── src/dogopencli/
│   ├── cli.py                     # 当前公共命令入口
│   ├── contracts.py               # 中立 endpoint/capability/result 协议
│   ├── domain_contracts.py        # 无业务加载副作用的 domain/auth 声明
│   ├── browser/                   # CDP、登录与浏览器生命周期
│   ├── transport/                 # 允许清单、请求执行与错误处理
│   ├── leaves/                    # 安装、发现、文档、共享运行时及临时缓存
│   └── leaf_packages/             # 按 domain/dotted-leaf 布置 manifest/adapter
├── examples/leaf_simple/           # 独立合成列表叶子的可执行开发参考
├── tests/                         # 公开 CLI、宿主、分发及合成响应测试
├── scripts/                       # 仓库维护工具，不承载业务查询实现
└── docs/                          # 规范、研究、领域决策与配图
```

Python 包、模块和函数使用 `snake_case`，类使用 `PascalCase`；测试文件使用 `test_<module>.py`。独立叶子目录使用 manifest 声明的 dotted identity；`__init__.py` 和 `__main__.py` 遵循 Python 特殊模块命名。

业务测试使用 pytest，集中在 `pyproject.toml` 配置；现有文档工具测试继续通过 `make test-doc-guard` 运行。单元测试使用假 CDP 响应；集成测试默认使用本地替身，生产只读验证须显式启用。所有测试均禁用 CDP 端口 9330–9340。

认证、只读限制和通用错误处理集中在宿主；业务叶子自行拥有原生请求、解析、身份、过滤和采集策略。当前四个 bundled leaf 范围及验收见根目录 [AGENTS.md](../../AGENTS.md#scope-and-architecture) 和 [#255](https://github.com/proletariat64/dogopencli/issues/255)。历史查询文档不代表当前注册或生产验收；后续迁移地图 #241 保持暂停。凭证、浏览器 profile、`.venv/`、缓存和构建产物不进入版本控制。

2026-09-11 用户明确指定本仓库 `tmp/` 保存私有探查导出和 Channel 替代数据集，避免系统 `/tmp/` 清理导致丢失。该目录由根 `.gitignore` 的 `/tmp/` 排除，使用 0700 目录和 0600 数据文件；不得作为可提交 fixture 或文档资产。真实数据写入仍拒绝仓库内其他目录，详见 [ADR 0005](../adr/0005-channel-snapshot-source.md)。

## 文档目录职责

| 位置 | 职责与命名 |
| --- | --- |
| 根目录 `README.md` | 项目入口与实际可运行命令 |
| 根目录 `AGENTS.md` | 贡献及代理协作指南 |
| 根目录 `CONTEXT.md` | 单一领域术语表；术语确定后按领域文档流程创建 |
| 根目录 `CHANGELOG.md`、`LICENSE.md` | 按需创建的变更记录和许可说明 |
| `docs/README.md` | 文档导航，新增报告时更新 |
| `docs/agents/<slug>.md` | 持续维护的协作规范 |
| `docs/adr/NNNN-<slug>.md` | 已形成的架构决策；从 0001 编号，编号唯一 |
| `docs/design/<slug>-vMAJOR.MINOR.PATCH.md` | 已发布 GitHub Issue 规格的版本化可读副本，必须链接权威 Issue；保留历史基线，注明后续实施状态 |
| `docs/research/general/YYYY-MM-DD-<slug>.md` | 跨产品的平台、访问和技术研究快照 |
| `docs/research/payment/YYYY-MM-DD-<slug>.md` | 付款产品设计与运行态研究快照 |
| `docs/assets/<scope>/` | 按需保存已脱敏的文档配图；不存业务原始响应或凭证 |

普通 Markdown 文件名使用小写英文、数字和连字符，例如 `platform-access.md`；日期使用真实日历日期。根目录和文档索引中的大写文件名为明确例外。保持扁平分类，暂不增加其他研究 scope。

需求与规格继续使用 [GitHub Issues](issue-tracker.md)，不新增本地 `docs/spec/`。`docs/design/` 仅保存已发布 Issue 的可读副本，不建立另一套本地规格权威；版本段使用无多余前导零的三段数字。历史规格状态与后续实施记录分别标注，避免把设计树当作当前可执行目录。领域术语与架构决策遵循 [领域文档约定](domain.md)。这些目录按需建立，不创建空文档。

## 研究快照

每份研究文档使用一个 H1 标题，并包含以下三行独立元数据；日期与文件名前缀一致，Scope 与目录一致：

```markdown
# 运营平台访问研究

Observed: 2026-09-08
Scope: general
Status: snapshot
```

日期表示证据观察日，不是 PRD 文件名中的日期。报告应包含结论、证据来源、方法和未验证事项，明确区分设计文档、运行态事实、参考实现和建议。文内建议不自动成为产品规格。

通用报告持有平台和传输层结论；付款报告持有付款领域、菜单和接口事实，通过相对链接引用通用结论。后续观测另建日期快照并更新索引；纠正原报告时注明纠正内容及原因。

## 格式与引用

- 使用 UTF-8、一个 H1、文件末尾换行；标题和列表之间留空行。
- 仓库内引用使用相对 Markdown 链接；本机外部资料用代码格式路径，并附文档 ID、行号或段落，避免把机器路径作为仓库链接。
- 生产页面和原始在线资料使用完整 HTTPS 链接；不包含登录票据、Cookie、token 值、完整银行账号或生产请求原文。
- 知识库检索先用 graphify，再按命中文档核对原文。保存已授权的研究摘要不等于授权重建知识图谱。

## Doc Guard

提交文档变更前运行 `rtk proxy make doc-guard`。校验器扫描仓库可见的 Markdown，包括未跟踪文件；忽略隐藏目录、依赖目录、构建产物及 Git 忽略的私有 `tmp/` 工作目录。

自动检查文档路径/命名、唯一 H1、UTF-8、末尾换行、研究日期与元数据、ADR 编号唯一性，以及行内 Markdown 链接的仓库内目标是否存在。失败输出文件和原因并返回非零退出码。

校验不联网，不写文件；跳过代码示例中的标题和链接。它不校验 Python 代码与测试目录布局、远程链接、标题锚点、引用式链接、配图命名、文档覆盖率或事实真实性，这些由人工核对。新增文档目录类别时同步修改本规范和 `scripts/doc_guard.py`，然后运行 `rtk proxy make test-doc-guard`。
