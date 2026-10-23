# Changelog

只登记**对 skill 本身的改动**（规则、脚本、台账结构调整），不登记每次录题的流水。

<!-- SCHEMA: {"ts":"ISO-8601","action":"add|promote|extract|resolve|restructure","type":"skill|script|issue|improvement","id":"条目","summary":"≤100字","target":"涉及文件"} -->

```jsonl
{"ts":"2026-10-22T17:35:00+08:00","action":"restructure","type":"skill","id":"learnings","summary":"台账改为问题导向：ISSUES 记坑与卡点、IMPROVEMENTS 记待优化、year-notes 只记差异","target":".learnings/"}
{"ts":"2026-10-22T17:46:00+08:00","action":"add","type":"script","id":"cut_audio-ends","summary":"cut_audio.py 新增 --ends 显式终点，修复锚点连切吞掉中文题头；subprocess 显式 UTF-8 解码","target":"scripts/cut_audio.py"}
{"ts":"2026-10-22T17:46:00+08:00","action":"add","type":"issue","id":"issue-11-anchor-cut","summary":"记录锚点连切吞播报的坑与判据；修正 issue-4 的 502 根因（未提交事务持锁，非重启窗口）","target":".learnings/ISSUES.md"}
{"ts":"2026-10-22T17:46:00+08:00","action":"add","type":"skill","id":"year-notes-2020","summary":"year-notes 增 2020 改制差异（9 段音频/6 张选项图/阅读A海报图），并限定 2010-2019 复用规律","target":"references/year-notes.md"}
{"ts":"2026-10-22T17:50:00+08:00","action":"add","type":"script","id":"check-duplicates","summary":"新增上传前查重脚本：ID/同题号/内容指纹三维度，重复则退出码1","target":"scripts/check_duplicates.py"}
{"ts":"2026-10-22T17:50:00+08:00","action":"add","type":"skill","id":"audio-intro","summary":"切音频支持 --intro-end 去卷首试音，--trim-intro 只吸死气","target":"scripts/cut_audio.py"}
{"ts": "2026-10-22T18:00:00+08:00", "action": "restructure", "type": "skill", "id": "structure-first", "summary": "结构判定改为「切大题→查目录→定题组」三步，删除甲乙范式与逐年固定规则；year-notes 并入 structure.md", "target": "references/structure.md"}
{"ts": "2026-10-22T18:45:00+08:00", "action": "add", "type": "skill", "id": "knowledge-tagging", "summary": "新增知识点打标标准：七维度 + 按题型的主标签/禁标项 + 多标签边界", "target": "references/knowledge-tagging.md"}
{"ts": "2026-10-22T18:45:00+08:00", "action": "resolve", "type": "issue", "id": "ISSUES-15", "summary": "2010/2018/2019 三批共 98 个单元补标完成，覆盖 100%", "target": "references/knowledge-tagging.md"}
{"ts": "2026-10-22T18:55:00+08:00", "action": "add", "type": "skill", "id": "type-knowledge-map", "summary": "26 主类逐条知识点对照表（与框架 xlsx F 列同源），含交叉匹配规则", "target": "references/type-knowledge-map.md"}
{"ts": "2026-10-22T19:05:00+08:00", "action": "add", "type": "skill", "id": "knowledge-index", "summary": "知识点目录原文与 514 节点索引入技能；新增 find_kp.py 查询、apply_type_tags.py 按题型补标签", "target": "references/knowledge-catalog.json"}
{"ts": "2026-10-22T19:20:00+08:00", "action": "add", "type": "script", "id": "retag-drafts", "summary": "新增草稿重打标脚本：按禁标维度纠正 + 维度兜底 + 逐篇覆盖，默认 dry-run", "target": "scripts/retag_drafts.py"}
{"ts": "2026-10-22T19:40:00+08:00", "action": "resolve", "type": "issue", "id": "ISSUES-17", "summary": "全库 243 单元多维度复核：改错 1、细化 7、补多标签 31，单维度从 114 降到 88", "target": "references/knowledge-tagging.md"}
{"ts": "2026-10-22T19:55:00+08:00", "action": "add", "type": "skill", "id": "matching-rules", "summary": "按目录原文补齐逐分支匹配细则（主题/语音/词汇/语法/语篇体裁/阅读技能/语用），新增 check_tags.py 体检", "target": "references/knowledge-matching-rules.md"}
{"ts": "2026-10-22T20:10:00+08:00", "action": "resolve", "type": "issue", "id": "subs-coverage", "summary": "子题知识点补齐：297 个空子题清零（继承 245 + 语法选择逐空判定 52），544/544 覆盖", "target": "scripts/check_tags.py"}
{"ts": "2026-10-22T20:45:00+08:00", "action": "resolve", "type": "issue", "id": "spelling-pos", "summary": "单词拼写按答案词性细分到 词汇辨析/<词性>：名词 8、形容词 7、动词 4、副词 2，词汇父节点清零", "target": "references/knowledge-matching-rules.md"}
{"ts": "2026-10-22T21:05:00+08:00", "action": "edit", "type": "skill", "id": "v-final", "summary": "技能收尾：§7 重写为 7.1–7.8（词分类详细匹配、拼写按答案倒推、关联表维护）；新增 spell_pos.py / fill_subtags.py；流程与脚本清单同步", "target": "SKILL.md"}
{"ts": "2026-10-22T22:05:00+08:00", "action": "add", "type": "script", "id": "preflight-check", "summary": "新增 preflight_check.py：上传前用服务端校验器回放整批并在库副本模拟确认写入；SKILL §11 增第 12 条", "target": "scripts/preflight_check.py"}
{"ts": "2026-10-23T09:35:00+08:00", "action": "edit", "type": "skill", "id": "subtypes", "summary": "§6 重写为主类+子类两级匹配；新增 references/type-subtypes.md；preflight 增加子类校验；补 2021/2022 的 subtypes", "target": "references/type-subtypes.md"}
{"ts": "2026-10-23T10:40:00+08:00", "action": "add", "type": "script", "id": "pdf-extract", "summary": "新增 pdf_extract.py：无文字层 PDF 的渲染/分页分栏/OCR(RapidOCR)/选项图与表格切分/题号归集；补 references/pdf-extraction.md", "target": "scripts/pdf_extract.py"}
{"ts": "2026-10-23T11:05:00+08:00", "action": "add", "type": "skill", "id": "difficulty-category", "summary": "§7.9 难度与分类：按文档填 difficulty/categories/difficultyValue；新增 assign_meta.py 特征打分 + 待定清单；preflight 校验取值", "target": "references/difficulty-category.json"}
{"ts": "2026-10-23T11:40:00+08:00", "action": "edit", "type": "skill", "id": "difficulty-fill", "summary": "assemble_meta 支持 --tapescripts/--durations；六套安徽卷 250 个单元的 difficulty/difficultyValue/categories 已录入（容易 84 / 适中 166）", "target": "scripts/assign_meta.py"}
{"ts": "2026-10-23T13:55:00+08:00", "action": "edit", "type": "skill", "id": "type-knowledge-map", "summary": "按 10-23 修订表重建映射；新增「听力关键词语选择」行按听力其他变体执行；19 个单元按答案词性回填标签", "target": "references/type-knowledge-map.json"}
{"ts": "2026-10-23T13:58:00+08:00", "action": "edit", "type": "skill", "id": "catalog-1.1", "summary": "知识点目录换 1.1（522 节点，设题角度/听力+阅读）；题型 27 类含听力关键词语选择；15 个单元改判、4 个图片题改 scope", "target": "references/knowledge-catalog.json"}
{"ts": "2026-10-23T14:10:00+08:00", "action": "edit", "type": "rule", "id": "publish-gate", "summary": "解析不再作为发布阻断项；publish_check 改为提示；同步阶段文档与上传口径", "target": "scripts/06-upload/publish_check.py"}
{"ts": "2026-10-23T14:35:00+08:00", "action": "edit", "type": "script", "id": "publish-check", "summary": "publish_check 补齐组题两项校验；250 个安徽单元经服务端真实 publish_blockers 复测 0 阻断", "target": "scripts/06-upload/publish_check.py"}
{"ts": "2026-10-23T14:40:00+08:00", "action": "fix", "type": "rule", "id": "difficulty-label", "summary": "difficulty 统一为 容易/适中/困难；61 条旧短码归一，16 条补 difficultyValue；publish_check 提示非标准写法", "target": "references/difficulty-category.json"}
{"ts": "2026-10-23T16:20:00+08:00", "action": "fix", "type": "script", "id": "preflight-not-null", "summary": "preflight 增加 NOT NULL 空值校验；2023 批次补齐 material/curriculum 等字段后重新上传", "target": "scripts/06-upload/preflight_check.py"}
```
{"ts": "2026-10-23T16:45:00+08:00", "action": "add", "type": "skill", "id": "answers-gate", "summary": "新增 extract_answers.py / check_answers.py：答案册机器抽表 + 批次逐题比对（客观硬拦、主观提示、空答案硬拦），smoke 带正反样例", "target": "scripts/06-upload/check_answers.py"}
{"ts": "2026-10-23T16:45:00+08:00", "action": "add", "type": "skill", "id": "img-markers", "summary": "extract_docx.py 在正文留 [IMG] 位置标记；新增 contact_sheet.py 出缩略图清单，图片归属不再靠序号反推", "target": "scripts/01-extract/extract_docx.py"}
{"ts": "2026-10-23T16:45:00+08:00", "action": "fix", "type": "rule", "id": "doc-consistency", "summary": "口径统一：difficulty 容易/适中/困难、主题只写叶子、主类 27；check_tags / check_text 增加 --batch 上传前模式", "target": "SKILL.md"}
{"ts": "2026-10-23T17:05:00+08:00", "action": "add", "type": "script", "id": "audit-reading", "summary": "新增 audit_reading.py：查阅读类选项图/材料图/文章大意/子题空答案；preflight 同步加两条校验并报「选项图挂到单元上」", "target": "scripts/06-upload/audit_reading.py"}
{"ts": "2026-10-23T17:05:00+08:00", "action": "fix", "type": "rule", "id": "reading-image-level", "summary": "阅读图片层级定稿：材料图挂单元 question、选项图挂子题 option+optionKey；材料是图时 material 留空不转写", "target": "references/stages/06-upload.md"}
{"ts": "2026-10-23T17:05:00+08:00", "action": "fix", "type": "rule", "id": "patch-overwrite", "summary": "PATCH 三条铁律：subquestions/attachments/filterMetadata 整体替换要先读后合并；子题 textbookMappings 会带回旧知识点", "target": "references/stages/06-upload.md"}
