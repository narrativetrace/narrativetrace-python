<!-- source: documentation/guides/pytest.md blob 58aa4f70d42a | translated: 2026-09-12 | reviewed: - -->

# pytest 插件

`narrativetrace-pytest` 会自动注册(通过 entry point)。请求 `narrative_trace` fixture 即可为每个
测试获得一个全新的捕获上下文。

```python
from narrativetrace import trace_object

def test_place_order(narrative_trace):
    service = trace_object(OrderService(narrative_trace), narrative_trace)
    service.place_order("cust-1", "prod-42", 3)
```

## 你会获得什么

- **失败叙事** —— 失败的测试会打印一个带边框的 `Scenario: …` 区块,附带缩进的执行追踪,让调用路径
  本身*就是*诊断结果。
- **模板警告** —— 未解析的 `@narrated`/`@on_error` 占位符每次运行只报告一次。
- **产物文件** —— 默认开启 *(since 0.1.2, unreleased)*:每个非空测试都会写出一个追踪文件——对于
  markdown 格式,还会附带一个 `.json` 场景文档、`diagrams/<Class>/<slug>.mmd`,以及一份无值的
  `structural/<Class>/<slug>.nt` 产物 *(since 0.1.2, unreleased)*——都写在 `NARRATIVETRACE_OUTPUT_DIR`
  下(默认为 `narrative-traces`;请将它加入 `.gitignore`,见 [应提交的内容](应提交的内容.md))。
  场景结果为 `PASSED` 或 `FAILED`。可通过 `NARRATIVETRACE_OUTPUT=false`(或在配置文件中设置
  `output = false`,见 [配置指南](配置指南.md))关闭。PyPI 上发布的 `narrativetrace-pytest==0.1.1`
  目前仍然默认关闭;在该版本上请显式设置 `NARRATIVETRACE_OUTPUT=true`。
- **结构化差异 + 审批模式** *(since 0.1.2, unreleased)* —— 磁盘上的 `.nt` 文件就是最近一次绿色
  基线;套件页脚会打印一行 `Since last green: …` 摘要,当形状发生变化时,失败测试的报告会打印其
  结构化差异,而不是完整的追踪。开启 `NARRATIVETRACE_APPROVAL=true` 可以改为让测试针对一份已
  提交的 `.approved.nt` 追踪失败——见[结构化追踪格式](结构化追踪格式.md)和[配置指南](配置指南.md)。
- **清晰度页脚** —— 套件页脚会打印 `Clarity: X% high | Y% moderate | Z% low` 的分布,并且(启用输出
  时)为每个被追踪的测试写出一条记录到 `clarity-results.json` + `clarity-report.md`。

> `@pytest.mark.parametrize` 的 id(如 `test_finds_it[KAYAK]`)会同时出现在携带值的产物的
> *文件名*、`scenario:`/`**Scenario:**` 头部,以及 `manifest.json` 中——和以前完全一样,绝不会
> 被裁剪或脱敏。无值的结构化 `.nt` 产物是唯一一个为你处理好这件事的地方:一次调用的结构化头部
> 会由方法及其调用索引来命名,绝不会用 parametrize 的 id *(since 0.1.2, unreleased)*——见
> [结构化追踪格式](结构化追踪格式.md)。无论如何都不要把敏感信息放进 `parametrize`
> 的 id 里;参见[隐私与脱敏 § 非保证](隐私与脱敏.md#非保证)。

## 测试中的级别

`NARRATIVETRACE_LEVEL=OFF` 不捕获任何内容(空树);未知的值会降级为 `DETAIL` 而不报错。级别同样
可以来自配置文件——环境变量只是优先级更高。
