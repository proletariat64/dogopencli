# 领域文档维护

阅读根目录 [CONTEXT.md](../../CONTEXT.md) 和与任务相关的当前开发指南。
CONTEXT 只定义业务对象、身份、时间和质量含义；实现协议放入
[leaf 手册](../../tools/leaf-dev/handbook.md)，领域与认证协议放入
[domain 指南](domain-components.md)。

术语确定时直接更新 CONTEXT；当前行为改变时更新唯一负责该行为的指南和示例。
指向其他指南时说明何时需要读取，避免复制整段规则。

需求、验收范围和任务状态记录在分配的 GitHub Issue。当前文档只保留有效契约和
操作方法，不累积决策经过、版本过程、旧 UAT 日记或历史规格副本。
历史业务源码核对使用任务中固定的 GitHub release/commit，在新运行时之外隔离执行。
