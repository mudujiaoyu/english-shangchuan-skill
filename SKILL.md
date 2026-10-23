---
name: mudu-question-upload
description: >
  木牍教育（Mudu）英语题库「录题」全流程 Skill。用于把本地真题/教辅原卷（.doc/.docx/.pdf + 听力 mp3）
  整理成题库 API 批次对象并写入上传暂存：正文/表格/图片提取、26 类题型映射、答案与解析核对、
  知识点打标（七维度、词性细分、子题继承）、听力音频按题切段、图片选项绑定、上传前查重、
  媒体部署、POST /api/uploads，以及确认后的 PATCH 补附件。
  触发词：录题、上传题目、题库上传、安徽中考真题、听力切分、题目批次、mudu upload。
metadata:
  category: workflow
  requires:
    bins: [python, ffmpeg, ffprobe, ssh, scp, curl]
---

# 木牍题库录题 Skill

把一份原卷变成 `POST /api/uploads` 能吃的批次对象，并安全地送进上传暂存。
本 Skill 来自 2010 / 2018 安徽中考英语两套卷的实战，踩过的坑都写在「注意点」里。

## 0. 一句话流程

**开工先看两个东西**：`.learnings/ISSUES.md`（已知坑）和 `references/structure.md`（怎么识别结构）。

**结构从原卷推，不从年份或卷型推。** 按 `structure.md` 三步走：切大题 → 查目录判题型 → 定题组与媒体，
产出「本卷结构清单」再动手。真题卷、模拟卷、月考卷、同步练习、单元测验形态差别很大，**没有固定模板**；
清单生成后与「已知形态」样例对一下，对不上是正常的，以原卷为准。

```
读文档(必读) → 建隧道 → 读目录 → 提原卷(文本/表/图) → 切音频(去试音) → 配题型/答案/解析
→ 打知识点(题型默认→逐题细分→子题→体检) → 生成批次 → 自检(答案比对/ID唯一/体积)
→ 查重 → 部署媒体 → POST /uploads → 交人工确认 → (确认后)PATCH 补附件 → 收尾记 .learnings/
```

## 1. 前置条件（缺一即停）

| 项 | 检查命令 | 说明 |
| --- | --- | --- |
| 隧道 | `curl -fsS http://127.0.0.1:8089/api/health` | 必须返回 `{"ok":true,...}`；8089 无监听就别往下走 |
| 隧道建立 | `ssh -N -L 8089:127.0.0.1:89 -i <key> -o IdentitiesOnly=yes -o ExitOnForwardFailure=yes -o ServerAliveInterval=60 ubuntu@101.43.1.57` | **远端是 89，不是 80** |
| API Base | `http://127.0.0.1:8089/api` | 严禁把 Key 发到公网 `http://101.43.1.57/` |
| Key | 存本地文件如 `%USERPROFILE%\.mudu\api_key.txt`，`icacls` 收紧 | scopes 只给 `query`/`call`/`draft` |
| 工具 | `python`、`ffmpeg`、`ffprobe`、`ssh`、`scp`、`curl` | Whisper 见 §5 |

先读文档：`http://gudi.metal-anchor.site/developer.md`（纯文本版，比渲染页全）。

## 2. 身份边界（Harness / API Key 永远不能做）

- `GET /api/uploads`（暂存列表只给人工）
- `POST /api/uploads/{id}/confirm`（逐题确认）→ 会返回 403 `human_confirmation_required`
- `DELETE /api/questions/{id}`、`publish`、`withdraw`、任何 `/api/admin/*` 写接口
- 改 `knowledgeStatus`、清 `warnings`、建正式知识点节点

能做：`GET /api/questions`、`/api/call`、目录读、`POST /api/uploads`、`PATCH /api/questions/{id}`（仅草稿）、`POST /api/compositions/export`。

## 3. 提取原卷

```bash
python scripts/extract_docx.py "<原卷.docx>" "<输出目录>"
```

产出：`正文.txt`（含 `[TABLE]` 标记的表格）、`media/`（内嵌图片）。

- **`.doc`（老二进制）**：先转 docx。本机有 Word 就用 COM：
  `$w.Documents.Open($src); $doc.SaveAs2($dst, 12)`（**用 `SaveAs2`，`SaveAs([ref]…)` 在 PowerShell 会报错**）。
- **`.pdf` 无文本库**时优先找同目录 docx；实在只有 PDF 且是扫描件 → 停下问用户要 Word 版。
- 表格要逐行导出，不能只留文字（信息转换题要用）。

## 4. 图片

- 图片在 `word/media/`，按文件名数字排序即文档顺序。
- **选项图数量由结构决定**：选项位置只有 `A.` `B.` `C.` 空壳的题才是图片题，张数 = 图片题数 × 选项数。
- **起点必须肉眼确认**：前面的 logo、二维码（"扫码练听力"）、整篇海报都不算选项图。
  举例：2018/2019 是 `image4–18`，2010 是 `image5–19`，2020 只有 `image4–9` 且阅读 A 篇本身是海报图——**不要套用上一年的范围**。
- 绑定用 `placement: "option"` + `optionKey: "A"/"B"/"C"`（`optionKey` 支持 A–Z，超过四个选项也够用）。
- 选项文字本身没意义，上传时写 `["A.","B.","C."]`，真实内容靠附件。

## 5. 听力音频切分（最容易出错的一步）

**不要只按静音切。** 每个小题读两遍，题内也有 1–2 秒停顿，按静音切会把「第一遍/第二遍」劈开。

正确做法：

1. `ffmpeg -af silencedetect=noise=-35dB:d=1.0` 拿到静音表，看时长分层（题间 vs 题内）。
2. 用本地 Whisper 转写定位（脚本已封装）：`python scripts/cut_audio.py --audio <mp3> --report` / `--transcribe`
   - `faster-whisper` 的 `decode_audio` 在新版 `av` 下会报 `metadata_errors` → **先 ffmpeg 转 16k 单声道 wav，再传 numpy 数组**，别直接喂 mp3。
   - 模型下载走 `HF_ENDPOINT=https://hf-mirror.com`，`tiny.en` 足够定位。
3. **优先用录音里念出的题号做锚点**（"Number 7" / "Nine" / "Thirteen" 会被识别成 `7.`、`Nine`、`Thirteen`），比静音中点准得多。
4. 段数 = **结构清单里的听力单元数**，不是题数；切完逐段回读首句，与听力材料逐行比对，**必须全中（或仅个别因音频质量存疑）**；不达标就调锚点重切，不要凑合。
5. 编码 `-ac 1 -ar 22050 -b:a 48k`。
6. 量级自检：同类单元时长应当接近（如短对话彼此差 2 倍以内）。某段明显长于同组其它段，说明切点把下一题的播报或大段空白吞进来了 → 用 `--ends` 收尾。

### 卷首试音要切掉

录音开头常有试音（1kHz 测试音、反复的 "Thank you."、中文设备说明），**这段不属于任何一道题**，不能留在 li-01 里。

- 先用 `--transcribe` 看第一条正文开口的时间（如 2019 是 37.72s、2018 是 60.74s）；
- 再 `--intro-end 37.7`，之前的内容全部丢弃；
- `--trim-intro` 只吸掉首段起点所在的那段静音（死气），**不会越过语音**——它不知道哪句是试音，别指望它自动识别。
- 首段尾部多余空白用 `--ends` 显式收尾。

> 没有听力材料（tapescript）也能切，但**必须**回读验证；两者都没有就只传文字，音频标待核。

## 6. 题型映射（26 主类 + 子类，只匹配不改名）

**两个层级都要落**：主类决定题型，**子类（建议存储值）决定筛选能不能命中**。子类漏写，这题在按子类筛选时会消失。

### 6.1 数据来源

- 主类与子类都取自 `http://127.0.0.1:8089/filter-framework.json` 的 `question_types`（根路径，`/static/` 下是 404）。
- 子类的判定线索见 **`references/type-subtypes.md`**（26 主类 × 全部子类 + 易错点）。
- 落库：`filterMetadata.subtypes`（数组）。无子类的题型留空数组，不要瞎填。

### 6.2 三步匹配

1. **定主类**：大题标题关键词 + 结构特征（共用材料/共用选项 → 题组；限词数 → 任务型；中文要点 + 80~100 词 → 书面表达）。
2. **定子类**：在主类的子类表里**逐条比对判定线索**，选唯一匹配；判不准就把候选列出来再说。
   例：单词拼写「汉语 + 首字母」→ `汉语及首字母`；补全对话「方框 7 选 5、2 个多余」→ `7选5`；
   阅读七选五 → `阅读回填`（不是 `选择5题`）。
3. **校验**：子类名必须是框架里的原文；上传前由 `preflight_check.py` 校验，写错会直接报错。

### 6.3 遇到不标准题型怎么办

**不要自己造类型，也不要按印象硬套主类。** 按这个顺序检索：

1. 先在大题标题里找线索词（选图片/排序/填表/七选五/首字母…）；
2. 到 `references/type-subtypes.md` 里**逐条比对**该主类的子类判定线索；
3. 命中就选；一条都不中且该主类有「其他」→ 选「其他」并在交接单注明理由；
4. 连主类都对不上（或两个主类同等合理）→ **暂停该批**，把候选主类/子类、依据、原文片段报给人工，等决定；
5. 目录里没有完全对应的形态（如安徽「关键词语选择」）→ 选语义最近的（`听力其他`），并在交接单登记。

**绝对禁止**：新增主类/子类、改名、合并、把两个子类合成一个。「只能选」是硬约束。

### 6.4 已知形态（样例，不是规则）

| 年份 | 短对话 | 长对话 | 短文 | 信息转换 | 单项 | 完形 | 补全对话 | 阅读 | 任务型 | 拼写 | 写作 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2018/2019 | 选图片/选文字 | 选择2题/3题 | 无子类 | 无子类 | 四个选项 | 10空 | 7选5 | 选择4题/5题 | 阅读问答 | 汉语及首字母 | 列中文要点 |
| 2020 | 选图片/选文字 | 选择2题/3题 | 无子类 | 无子类 | 四个选项 | 10空 | 7选5 | 选择3题/4题 | 阅读问答 | 汉语及首字母 | 列中文要点 |
| 2021/2022 | 选图片/选文字 | 选择2题/3题 | 无子类 | 无子类 | 四个选项 | 10空 | 7选5 | 选择3题/4题 | 阅读问答 | 汉语及首字母 | 列中文要点 |

换卷型（同步练习、月考卷）必须重新按 6.2/6.3 判，**不要照抄上表**。

## 7. 答案、解析、知识点

### 7.1 答案 / 解析 / 文章大意

- **答案**：原卷末尾的「参考答案」是唯一来源。写进 `answer`，只写内容，不加「答案：」。题组写进每个 `subquestions[].answer`，组级 `answer` 用 `; ` 拼接。
- **解析**：原卷给了就写进 `explanation`（去掉「【解析】」标记）；**没给就留空**，不编造、不写占位语。
- **文章大意**：原卷有【文章大意】→ 写 `articleSummary`；没有就留空。
- **难度**：不猜，留给编辑。

### 7.2 知识点：先认清「目录」这一层

| 文件 | 角色 |
| --- | --- |
| `references/knowledge-catalog-1.0.md` | 目录原文（设计稿，人读） |
| `references/knowledge-catalog.json` | 514 个节点的 `id/path/name`（机器读，**落库解析 ID 用**） |
| `references/knowledge-tagging.md` | 打标原则、七维度、禁标矩阵 |
| `references/knowledge-matching-rules.md` | **逐分支匹配细则**（主题/语音/词汇/语法/语篇体裁/阅读技能/语用） |
| `references/type-knowledge-map.json` / `.md` | 26 个题型 → 默认标签 + 需逐题判断的提示 |

**查节点必须用工具**：`python scripts/find_kp.py 被动语态`。不要凭记忆写路径；同名节点（多处「其他」）靠完整路径消歧；解析不到就留空，不猜 ID。

**服务端才是唯一可落库来源**：目录原文里的节点若服务端没有，不能写；反向缺节点走 `POST /api/catalog/knowledge-proposals` 提建议，等人工批准。

### 7.3 词分类是「详细匹配」，不是挂到大类（硬要求）

**`词汇`、`词汇辨析`、`语篇体裁/记叙文`、`语音/基本读音` 这些都是父节点，不能停在上面。**
父节点只表示初步判断，必须继续往下选到叶子：

| 父节点 | 必须细到 | 判断依据 |
| --- | --- | --- |
| 词汇/词汇辨析 | 名词辨析、动词辨析、形容词辨析、副词辨析、介词辨析、连词辨析、代词辨析 | 看四个选项/答案的**词性** |
| 词汇/短语与固定搭配 | 动词短语、介词短语、形容词短语、名词短语、固定搭配/句型 | 答案是**多词组合** |
| 词汇/构词法 | 派生法（前缀、后缀）、合成法、转化法、缩写和简写 | 答案需要**加前后缀或词性转换** |
| 语篇体裁/记叙文 | 故事、人物传记、童话、简版小说 | 叙事 / 记人 / 寓言 |
| 语篇体裁/说明文 | 介绍类短文、事理阐释、程序/现象说明、指令/指南/手册 | 介绍事物 / 讲道理 / 讲步骤 |
| 语篇体裁/日常口语 | 日常对话、独白 | 对话 / 独白 |
| 语篇体裁/应用文 | 私人信件、通知、活动计划、规则、问卷、海报/宣传册、产品介绍、日记 | 看格式与用途 |
| 语音/基本读音 | 字母在单词中的基本读音、常见元音字母组合读音、辅音字母组合读音、辅音连缀、失去爆破 | 辨音差异落在哪种组合 |
| 语法/…/被动语态 | 一般现在时/一般过去时/一般将来时的被动语态、含情态动词的被动语态 | 看助动词形式 |

体检会直接报「停在父节点」的标签：`python scripts/check_tags.py`，退出码非 0 就是没细到位。

### 7.4 单词拼写：用答案倒推词性（硬要求）

拼写题不挂父节点「词汇」，**看答案在句子里作什么成分**，落到对应辨析：

| 答案词性 | 落点 | 例 |
| --- | --- | --- |
| 名词 | `词汇/词汇辨析/名词辨析` | chalk、role、poems、party |
| 形容词 | `词汇/词汇辨析/形容词辨析` | safe、strict、busy、ready |
| 动词 | `词汇/词汇辨析/动词辨析` | invited、carry、adds、cross |
| 副词 | `词汇/词汇辨析/副词辨析` | twice、fast |

再按需要叠加：

- 需要变形 → `语法/名词/名词的数` 或 `语法/动词/动词的基本形式`；
- 需要派生 → `词汇/构词法/派生法（前缀、后缀）`；
- 看音标写词 → `语音/基本读音/字母在单词中的基本读音`；
- 看图填词 → `阅读技能/图片理解（交叉）`。

工具：`python scripts/spell_pos.py --list` 列出答案 → 人工定词性 → 写 `pos.json` → `--map pos.json --apply`。

### 7.5 七维度与禁标

七个维度：主题 / 语篇体裁 / 阅读技能 / 语法 / 词汇 / 语用 / 语音。
**一题 1–3 个标签，同维度只挂一个，跨维度可叠加**；多标签必须有依据，不为凑数。

| 题型 | 禁止 |
| --- | --- |
| 完形填空 | 语法、词汇辨析（考篇章，不考词义辨析） |
| 单项填空 | 主题、语篇体裁（没有篇章） |
| 语法选择 | 不限制（篇章型，但必须有一个语法点） |
| 听力各题型 | 语法 |
| 单词拼写 | 词汇父节点；语法仅限词形变化 |
| 阅读理解 | 语法、词汇辨析 |

### 7.6 题组与子题

- 组级 = 该组要考的能力（体裁 + 主题，或语法点）；子题 = 各自精确考点 `subquestions[].knowledge`。
- **每个阅读小题都必须有一个 `阅读技能/*`**，按设问方式判（best title → 最佳标题，infer → 推理判断 …）。
- 子题空缺用 `python scripts/fill_subtags.py --list` 找，`--apply` 按「阅读设问规则 + 组级继承」补；语法选择这类必须逐空判定的，用 `--map gram.json`。

### 7.7 关联表的维护（题型与知识点的对应会变）

**唯一的源是 `type-knowledge-map.json`**，`.md` 是它生成的可读版，桌面的 xlsx 是对外交付版。改动顺序：

1. 改 `type-knowledge-map.json`（`defaults` 必须能在目录里解析到；`hints` 是给人看的）；
2. 重新生成 `type-knowledge-map.md`；
3. 跑 `check_tags.py` 回归，确认没有新增禁标/未下钻；
4. 同步 CHANGELOG。

**什么时候要改这张表**：

- 目录升版（节点增删改名）→ 先更新 `knowledge-catalog.json`，再核 `defaults` 是否还有效；
- 题型框架调整（26 主类变多/变少）→ 同步 `type-knowledge-map.json` 的键；
- 编辑反馈某类题打偏了 → 改该题型的 `hints`，或补一条禁标到 `check_tags.py`。

**不要**在脚本里写死题型→知识点的映射，一切从 JSON 读。

### 7.8 上传前打标顺序

```bash
python scripts/apply_type_tags.py --batch b.json --out b_tagged.json   # 按题型补默认（只补空缺）
# 人工逐题判：单项的语法点、完形的体裁与主题、拼写的答案词性
python scripts/check_tags.py --ids AH-2020                              # 体检
python scripts/preflight_check.py --batch b_tagged.json --insert         # 服务端校验 + 写入模拟
python scripts/check_duplicates.py --batch b_tagged.json                # 查重
```

## 8. 批次与自检

批次对象：

```json
{"subject_id":"english","upload_mode":"source","upload_target":"中考真题",
 "batch_id":"anhui-2018-english-zhenti","name":"...","items":[...]}
```

自检清单（脚本化，别靠眼睛）：

- [ ] ID 唯一，格式 `AH-<年>-<三位序号>`，书面表达单列一个 ID
- [ ] 每个 `answer` 非空、无前缀；`explanation` 无前缀
- [ ] 答案与「参考答案」逐题比对，**不一致数必须为 0**
- [ ] 题组都有 `subquestions`；信息转换有 `materialBlocks`
- [ ] 题型都在 26 主类内，且 `filterMetadata.subtypes` 已填、属于该主类的子类（无子类的题型留空数组）
- [ ] `len(json.dumps(...).encode("utf-8")) < 2_000_000`（实测 96 题约 56 KB，远没到上限）

### 上传前查重（硬性闸门）

**题库里已有的题，一律不许再传。**

```bash
python scripts/check_duplicates.py --batch batch_2019.json
# 退出码 0 → 放行；1 → 有重复，禁止上传；2 → 连接/参数错误
```

三个维度任一命中即判重：

| 维度 | 说明 |
| --- | --- |
| ID 已存在 | `AH-2019-001` 已在库里（草稿或已发布） |
| 同年同题号 | id 命名变体也能抓到 |
| 内容相同 | 题干 + 选项 + 材料归一化后哈希，跨年份复用同一道题也能抓 |

默认走服务器只读库（草稿 + 已发布都能看到）；没有 SSH 时用 `--api` 退化为只查已发布题（覆盖面小，慎用）。

判重的处置：**不要上传**。确需修订就对现有草稿 PATCH，不要新传一批。

## 9. 媒体部署与上传

```bash
ssh -i <key> ubuntu@101.43.1.57 "mkdir -p /home/ubuntu/mudu-quiz/static/source-media/<批次>/"
scp -i <key> li-*.mp3 ubuntu@101.43.1.57:/home/ubuntu/mudu-quiz/static/source-media/<批次>/
curl -o NUL -w "%{http_code}" http://127.0.0.1:8089/source-media/<批次>/li-01.mp3   # 必须 200
```

```bash
curl -X POST http://127.0.0.1:8089/api/uploads \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json; charset=utf-8" \
  --data-binary @batch.json
# → 201 {"id":"<staging-id>","stage":"pending_confirmation"}
```

## 10. 确认之后（关键顺序陷阱）

- **同一批 id 不能二次确认**：v1 已确认后再传 v2，confirm 会 409 `question_id_exists`（不是格式错）。
  要补数据就 `PATCH` 已有草稿，别再上传一版。
- **PATCH 的 `attachments` 是整体覆盖**：先读现状（只读查库或 GET），合并后再提交，否则图片会被音频冲掉。
  用 `python scripts/patch_attachments.py --batch batch_2018.json --current current.json --dry-run` 先看合并结果，去掉 `--dry-run` 再提交。
- 只读查库（诊断用）：`sqlite3 "file:/home/ubuntu/mudu-quiz/data/mudu.sqlite3?mode=ro"`，查 `upload_staging` / `question_units` / `questions.attachments_json`。

## 11. 注意点速查（都是真踩过的）

1. **PowerShell 在受限沙箱下起不来**（`0xC0000142` / `STATUS_DLL_INIT_FAILED`）→ 需要 full access；不是命令写错。
2. **`Set-Content -Encoding UTF8` 写 BOM**，Python `json.load` 会炸 → 读用 `encoding="utf-8-sig"`。
3. **Word COM `SaveAs([ref]…)` 报「值不在预期范围内」** → 用 `SaveAs2($dst, 12)`；`Quit()` 偶发 RPC 错误可忽略。
4. **zip 里 `word/media/` 有目录条目**，`basename` 为空会抛 `FileNotFoundError` → 过滤 `endswith("/")`。
5. **`.jpeg` 和 `.png` 混用**：按 `image10` 之类的基名匹配，别写死 `.png`。
6. **scp 多个文件时中途报错仍会传一部分** → 传完必须 `ls | wc -l` 点数。
7. **OCR 错字要按语义修并登记**：如 `three clays`→`days`、`]3. skill`→`B. skill`、`all the timid`→`all the time`；修了哪些要写进交接单让编辑对照 PDF 复核。
8. **图片题选项文字留空会显得怪**，但这是对的——不要在 `options` 里编文字。
9. 上传成功只代表 `pending_confirmation`，**不代表草稿或已发布**；发布需人工且要 `explanation` 齐全，否则 `missing_explanation`。
10. **附件 `placement` 只有四个合法值**：`question` / `option` / `answer` / `explanation`。写 `stem` 之类会被 `normalize_attachments` 判 `invalid_attachment`，最终统一返回 **400 `invalid_request`**，而前端往往只弹一句就吞掉——人工点「逐题确认」会像没反应。音频用 `question`，选项图用 `option` + `optionKey`。
11. **确认失败先查日志**：`journalctl -u mudu-quiz --since '-10 min'` 看 `/confirm` 的 HTTP 码，再对照后端校验分支定位；不要从 UI 行为猜。
12. **上传前必须跑 `preflight_check.py`**：它用服务端同一套校验器回放，能在 POST 之前就暴露附件/知识点/表格格式问题；`--insert` 还会在数据库副本上模拟确认写入。2021 那次「点确认没反应」就是跳过了这一步。

## 12. 脚本清单

| 脚本 | 用途 | 典型调用 |
| --- | --- | --- |
| `scripts/extract_docx.py` | docx → 正文.txt + media/ | `python extract_docx.py 原卷.docx out/` |
| `scripts/find_kp.py` | 在 514 个知识点里按关键词查路径与 ID | `python find_kp.py 被动语态` |
| `scripts/apply_type_tags.py` | 按题型给题目补默认知识点 | `--batch b.json --out b_tagged.json` |
| `scripts/check_tags.py` | 全库标签体检（空标签/禁标/未下钻） | `python check_tags.py --ids AH-2020` |
| `scripts/fill_subtags.py` | 给空的子题补标签（阅读按设问、其余继承组级） | `--list` → `--apply`，语法选择用 `--map` |
| `scripts/spell_pos.py` | 单词拼写按答案词性细分 | `--list` → `--map pos.json --apply` |
| `scripts/retag_drafts.py` | 已入库草稿按题型规则重打（禁标纠正 + 维度兜底） | `--ids AH-2020 --apply` |
| `scripts/check_duplicates.py` | 上传前查重（ID / 同题号 / 内容指纹），有重复退出码 1 | `python check_duplicates.py --batch b.json` |
| `scripts/preflight_check.py` | **上传前用服务端校验器回放整批**，`--insert` 还会在库副本上模拟确认写入 | `python preflight_check.py --batch b.json --insert` |
| `scripts/cut_audio.py` | 停顿分层 / 转写 / 按锚点切段 / 去试音 / 回读验证 | `--report` → `--transcribe` → `--anchors ... --intro-end ... --out dir --verify` |
| `scripts/patch_attachments.py` | 确认后把附件合并进草稿（先 dry-run） | `--batch batch.json --current current.json` |

三个脚本都只依赖 `python` + `ffmpeg`；`cut_audio.py` 的转写功能额外需要 `pip install faster-whisper`。

## 13. 交付物

每次录一卷，产出三样：

1. `batch_<年>.json` — 实际提交的批次对象
2. `upload_report_<年>.md` — 暂存 ID、题型映射、切分表、待核项、OCR 修正清单
3. 口头回执：HTTP 状态 + `id` + 单元/子题数 + 未做的事（未确认/未发布）

## 14. 自进化（只记问题，不记流水）

**原则：台账是「问题清单」，不是「工作日志」。** 顺利跑完的年份不写任何东西——写了只会稀释信号，
下次读的人（包括你自己）会开始跳过。

**开工前**：翻 `.learnings/ISSUES.md` 看有没有同类坑；按 `references/structure.md` 三步识别本卷结构（见 §0，不需要逐年确认）。

**收尾只回答三个问题**，有答案才写：

| 问题 | 写到哪 |
| --- | --- |
| 这次哪里卡住了 / 返工了？根因是什么？ | `.learnings/ISSUES.md`（现象 → 根因 → 处置 → 预防） |
| 哪件事手写了两遍以上？ | `.learnings/IMPROVEMENTS.md` |
| 遇到**从没见过的卷型或大题形态**？ | `references/structure.md` 的「已知形态」补一行样例 |

**任何时候都不要把结构写成规则。** 补样例可以，改判定逻辑不行——判定永远是「切大题 → 查目录 → 定题组」这三步，
因为下一份卷子可能既不是真题也不是模拟卷。

**不写的情况**：一次跑通的卷子；形态能在已知样例里对上；已被 `ISSUES.md` 覆盖的同类问题（改那一条即可）；纯过程记录。

**晋升**：同一问题第三次出现，或某个坑连续两次导致返工 → 精炼成一条规则写进本 SKILL.md 对应章节，
并在 `ISSUES.md` 的「预防」列标注已固化位置。判断标准：**能避免重犯吗？** 答不上来就别写。

**CHANGELOG 只记 skill 本身的改动**（改规则、加脚本、调台账结构），不记每次录题。
