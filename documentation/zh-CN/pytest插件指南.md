<!-- source: documentation/guides/pytest.md blob a44c1857df02 | translated: 2026-09-12 | reviewed: - -->

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
- **产物文件** —— 默认开启 *(since 0.1.2, unreleased)*:每个非空测试都会在 `NARRATIVETRACE_OUTPUT_DIR` 下写出一个追踪文件
  (默认为 `narrative-traces`;请将它加入 `.gitignore`,见 [应提交的内容](应提交的内容.md))——
  对于 markdown 格式,还会附带一个 `.json` 场景文档以及 `diagrams/<Class>/<slug>.mmd`。场景结果为
  `PASSED` 或 `FAILED`。可通过 `NARRATIVETRACE_OUTPUT=false`(或在配置文件中设置
  `output = false`,见 [配置指南](配置指南.md))关闭。PyPI 上发布的 `narrativetrace-pytest==0.1.1` 目前仍然默认关闭;在该版本上请显式设置
  `NARRATIVETRACE_OUTPUT=true`。
- **清晰度页脚** —— 套件页脚会打印 `Clarity: X% high | Y% moderate | Z% low` 的分布,并且(启用输出
  时)为每个被追踪的测试写出一条记录到 `clarity-results.json` + `clarity-report.md`。

> `@pytest.mark.parametrize` 的 id(如 `test_finds_it[KAYAK]`)会同时出现在产物的*文件名*和
> `scenario:`/`**Scenario:**` 头部——绝不会被裁剪或脱敏。这个插件写出的唯一产物就是携带值的那种
> (见[功能指南](功能指南.md):一个无值的结构化产物——按跨运行时的命名约定,它会不带
> `parametrize` 的 id——目前在 Python 里还没有对应实现)。请不要把敏感信息放进 `parametrize`
> 的 id 里;参见[隐私与脱敏 § 非保证](隐私与脱敏.md#非保证)。

## 测试中的级别

`NARRATIVETRACE_LEVEL=OFF` 不捕获任何内容(空树);未知的值会降级为 `DETAIL` 而不报错。级别同样
可以来自配置文件——环境变量只是优先级更高。
