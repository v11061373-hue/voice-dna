# HANDOFF-P4-D — 个人账号（供应商 + key + `llm.py` 抽象）

状态：完成 ✅ · 2026-10-19

## 完成度

- **D1 `/api/config` GET/POST**（`web_server.py`）：`provider/base_url/model/key` + judge 组
  - 供应商下拉预设 `src/config.py PROVIDERS`（全 OpenAI 兼容，加一个 = 一行）：
    DeepSeek / 通义 Qwen / 智谱 GLM / Kimi / 腾讯混元 / OpenAI 兼容（custom，base_url+model 用户填）
  - 每预设 = `{label, base_url, model}`，`base_url` 不含 `/chat/completions` 末段
- **D2 key 铁律**：key 只落 `os.environ`（`VOICEDNA_API_KEY`，内存，重启失效）
  - `config.py` 无 sqlite/aiosqlite/open/json.dump/.write，只写 os.environ（grep 已核）
  - `/api/config` GET 只回「已配/未配」`masked()`，不吐 key 明文
- **D3 `src/llm.py`**：通用 OpenAI 兼容 client `call_llm(prompt, *, base_url, model, key, system, temperature)` + `has_key()`
  - 缺省读 `VOICEDNA_BASE_URL/MODEL/API_KEY`；显式传参覆盖（judge 独立 provider 用）
  - `style_mimic._call_deepseek` 已删，`run()` 改 `llm.has_key()` + `llm.call_llm()`
- **D4 judge 解耦**：`/api/config` 加 `judge_provider/judge_base_url/judge_key` 字段组
  - `config.judge_settings()` 默认回退主 provider；给独立 provider 即独立 base_url/model/key
  - `judge_model` 从 judge provider 预设派生，存 `VOICEDNA_JUDGE_MODEL`（POST 体不含，PLAN §六只列 3 字段）
- **前端 config 面板**：`static/index.html` 侧栏「👤 个人账号」→ 配置弹窗
  - 供应商下拉（读 GET `providers`）+ base_url/model 输入 + key 密码框 + judge 组（默认「复用主供应商」）
  - 选预设供应商自动填 base_url/model；key 留空 = 不改旧值；GET 只回「已配」状态不回 key

## 铁律核验

- key 只 `os.environ`：`VOICEDNA_API_KEY` 全库仅 `config.py`（env 名）与 `llm.py`（`os.environ.get`）两处，无 sessions.db/checkpoints.db/json 写路径
- cookie 只落 `~/.voice-dna/cookies.json`（A4 已定，本阶段未动 `src/cookies.py`）
- 检索型源走 stdio npx（本阶段未动 trend_hunter）
- handoff 含 `unverified_assumptions`

## 测试证据

- `pytest`：**103 passed**（90 → +13：config 8 + llm 5）
- `ruff check src/config.py src/llm.py src/tools/style_mimic.py web_server.py`：All checks passed
- `mypy src/config.py src/llm.py src/tools/style_mimic.py`：Success（3 files）
- 端到端 sanity（monkeypatch httpx.post）：
  - 填 DeepSeek key → style_mimic `POST https://api.deepseek.com/chat/completions` model=deepseek-chat，非降级卡
  - 填 Qwen key + 自定义 base_url → `POST https://my-qwen-proxy/v1/chat/completions` model=qwen-plus
  - 无 key → 降级 FALLBACK_STYLE_CARD
- **真实 LLM 联调（放行 #1/#4）**：用 env 已有 `DEEPSEEK_API_KEY` + `DASHSCOPE_API_KEY` 真调
  - DeepSeek：`provider=deepseek` → style_mimic 真调成功，degraded=False，返回真实中文风格卡
  - Qwen：`provider=qwen` → 真调成功，degraded=False
  - 即 `https://api.deepseek.com` + `/chat/completions` 与 `https://dashscope.aliyuncs.com/compatible-mode/v1` + `/chat/completions` 拼接、model 名 `deepseek-chat`/`qwen-plus`、`choices[0].message.content` 字段、`Bearer` 鉴权全对

## 未完成 / 待办

- 前端 config 面板为纯 JS，pytest 不覆盖；JS 已 node --check 语法通过 + `/api/config` 经 TestClient 验 GET/POST/key 掩码，但弹窗交互（下拉自动填、填 key 保存、已配状态）需手动开浏览器验 `/` 页面
- 6 agent 里仅 style_mimic 接了 llm.py，其余 5 个 agent 待 P4-C LLM 化时接

## unverified_assumptions（未验证假设，待放行）

1. ~~**真实 LLM API 未联调**~~ ✅ **已放行**：真实 `DEEPSEEK_API_KEY` + `DASHSCOPE_API_KEY` 跑通 DeepSeek + Qwen，base_url/model/响应字段/鉴权全对（见测试证据）。
2. **provider/base_url/model 同放内存不持久**：PLAN §六未要求持久化，key 铁律只针对 key；非密配置重启也失效。若后续要「记住上次选的供应商」需另加落盘（json/DB），当前未做。
3. **judge model 派生规则**：judge 用 `judge_provider` 预设的 model；judge_provider="custom" 或空时回退主 model。PLAN §六 judge 字段组只列 provider/base_url/key 无 model，此派生是拍脑袋补齐，真用 judge 时需确认 model 名。
4. ~~**Qwen base_url 末段**~~ ✅ **已放行**：`.../compatible-mode/v1` + `/chat/completions` 真实调通。

## 下阶段入口

P4-C 6 agent LLM 化（C1 persona → C2 三段式 → C3 5 门 LLM-judge）。依赖已就位：D 的 `llm.call_llm`（6 agent 共用）+ B 的门禁（`src/mcp_guard/`）+ `config.judge_settings()`（C3 LLM-judge 独立 provider 入口）。
