# issue.json 字段说明

一个文件写一期。`build.py` 会先校验，未知字段、缺字段、栏目对不上都会报错，并且不生成页面。

## 期次

| 字段 | 必填 | 说明 |
|---|---|---|
| `kind` | 是 | `digest`（日报）或 `week`（周览） |
| `date` | digest 必填 | `YYYY-MM-DD`，按上海日期 |
| `slot` | 否 | `morning` 是早刊，`evening` 是晚刊。不写时按生成时间判断，上海 15 点前算早刊 |
| `start`、`end` | week 必填 | `YYYY-MM-DD`，周览覆盖的起止日期 |
| `headline` | 是 | 封面题 |
| `deck` | 是 | 封面副题 |
| `intro` | 是 | 导语，字符串或字符串数组 |
| `window` | 是 | 覆盖行：时间窗、来源范围、榜单状态 |
| `groups` | 否 | 栏目列表 `[{"key": "new", "label": "新品"}, ...]`。digest 默认是新品、访谈；week 默认是 `theme` 主线、`pick` 清单、`talk` 访谈 |
| `items` | 是 | 条目数组，按想要的顺序排 |

## 条目

| 字段 | 必填 | 说明 |
|---|---|---|
| `group` | 是 | 必须是 `groups` 里的某个 key |
| `title` | 是 | 题 |
| `deck` | 否 | 副题。建议每条都写，产品条目尤其需要 |
| `body` | 是 | 正文，字符串或字符串数组（多段） |
| `badges` | 否 | 来源名数组，如 `["PH #1"]`、`["HN", "博客"]` |
| `links` | 否 | `[{"label": "HN", "url": "https://..."}]`，url 必须以 http(s) 开头 |
| `judge` | 否 | 判断。默认不写，规则见 SKILL.md 第 6 节 |
| `id` | 否 | 一般不写，脚本按栏目自动编号，如 `n1`、`i2`、`f1` |

## 脚本推导的字段（不要写）

`id`、`eyebrow`、`label`、`short`、`title`（期次标题）、`weekday`、条目的 `num`、`lead`、`judgeLabel`、`generatedAt`、`latest`。

## 栏目和版式

| key | 版式 |
|---|---|
| `new` | 第一条是头条，大标题、正文分两栏；第二、三条次之；其余是短讯 |
| `interview`、`talk` | 三栏，薄荷色栏目头 |
| `theme` | 周览主线，三栏 |
| `pick` | 周览清单，四栏短条 |
| 其他自定义 key | 三栏，用新品栏的图标和颜色 |

## 历史

- `--prev` 读上一版 index.html 里的全部期次，把这一期并进去。
- 同一个期号会被覆盖，所以重跑同一期不会出现重复。
- 日报按时间倒序，最多保留 `--keep` 期（默认 6）。周览只留最新一期，排在最后。
- 新生成的这一期一定会保留，补发旧日期的也一样。
- 页面默认打开日期最新的那一期。无 JS 静态版放最新一期，再加周览。

## 周览最小样例

```json
{
  "kind": "week", "start": "2026-10-05", "end": "2026-10-11",
  "headline": "……", "deck": "……", "intro": ["……"], "window": "10 月 5 日至 11 日",
  "items": [
    {"group": "theme", "title": "……", "deck": "……", "body": ["……"], "judge": "……"},
    {"group": "pick", "title": "产品名", "body": ["一句话"], "links": [{"label": "官网", "url": "https://..."}]},
    {"group": "talk", "title": "人名 谈 话题", "badges": ["YouTube"], "body": ["一句话"]}
  ]
}
```
