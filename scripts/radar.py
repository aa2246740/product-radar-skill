"""产品雷达：数据格式、字段推导、校验和无脚本静态版渲染。build.py 和 lint_radar.py 共用。"""
import datetime as dt
import json
import re

SHANGHAI = dt.timezone(dt.timedelta(hours=8))
WEEKDAYS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
SLOT = {'morning': ('上午', '早刊'), 'evening': ('晚上', '晚刊')}
DEFAULT_GROUPS = {
    'digest': [{'key': 'new', 'label': '新品'}, {'key': 'interview', 'label': '访谈'}],
    'week': [{'key': 'theme', 'label': '主线'}, {'key': 'pick', 'label': '清单'}, {'key': 'talk', 'label': '访谈'}],
}
ID_PREFIX = {'new': 'n', 'interview': 'i', 'theme': 't', 'pick': 'p', 'talk': 'v'}
ISSUE_KEYS = {'kind', 'date', 'slot', 'start', 'end', 'headline', 'deck', 'intro', 'window', 'groups', 'items'}
ITEM_KEYS = {'id', 'group', 'title', 'deck', 'badges', 'body', 'judge', 'links'}
DATA_RE = re.compile(r'window\.RADAR_DATA = (\{.*\});')
STATIC_RE = re.compile(r'(<div class="static" id="static">\n)(.*?)(\n</div>)', re.S)


# ---------------------------------------------------------------- 读写
def load_data(html):
    m = DATA_RE.search(html)
    return json.loads(m.group(1)) if m else None


def data_js(data):
    # 防止正文里的 </script> 提前结束脚本
    return json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')


def static_block(html):
    m = STATIC_RE.search(html)
    return m.group(2) if m else None


def now_shanghai():
    return dt.datetime.now(SHANGHAI)


# ---------------------------------------------------------------- 校验输入的 issue.json
def _date(s):
    try:
        return dt.date.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def validate(src):
    """返回错误列表。src 是 bot 写的 issue.json。"""
    e = []
    if not isinstance(src, dict):
        return ['issue.json 顶层必须是对象']
    for k in sorted(set(src) - ISSUE_KEYS):
        e.append(f'未知字段 {k}（允许：{", ".join(sorted(ISSUE_KEYS))}）')
    kind = src.get('kind')
    if kind not in ('digest', 'week'):
        e.append('kind 必须是 digest 或 week')
    if kind == 'digest':
        if not _date(src.get('date')):
            e.append('digest 需要 date，格式 YYYY-MM-DD')
        if src.get('slot') not in (None, 'morning', 'evening'):
            e.append('slot 只能是 morning 或 evening（不写则按上海时间 15 点前后自动判断）')
    if kind == 'week':
        a, b = _date(src.get('start')), _date(src.get('end'))
        if not a or not b or b < a:
            e.append('week 需要 start 和 end，格式 YYYY-MM-DD，且 end 不早于 start')
    for k in ('headline', 'deck', 'window'):
        if not isinstance(src.get(k), str) or not src.get(k).strip():
            e.append(f'{k} 必填，且是非空字符串')
    intro = src.get('intro')
    if isinstance(intro, str):
        intro = [intro]
    if not isinstance(intro, list) or not intro or not all(isinstance(p, str) and p.strip() for p in intro):
        e.append('intro 必填：字符串，或字符串数组')
    groups = src.get('groups') or DEFAULT_GROUPS.get(kind, [])
    keys = []
    for g in groups:
        if not isinstance(g, dict) or not re.fullmatch(r'[a-z][a-z0-9_-]*', str(g.get('key', ''))) or not g.get('label'):
            e.append(f'groups 里每项要有 key（小写英文）和 label：{g}')
        else:
            keys.append(g['key'])
    if len(keys) != len(set(keys)):
        e.append('groups 的 key 有重复')
    items = src.get('items')
    if not isinstance(items, list) or not items:
        e.append('items 必填，且至少一条')
        return e
    ids = []
    for n, it in enumerate(items, 1):
        w = f'items[{n}]'
        if not isinstance(it, dict):
            e.append(f'{w} 必须是对象')
            continue
        for k in sorted(set(it) - ITEM_KEYS):
            e.append(f'{w} 未知字段 {k}（允许：{", ".join(sorted(ITEM_KEYS))}）')
        if it.get('group') not in keys:
            e.append(f'{w} group「{it.get("group")}」不在 groups 里（{", ".join(keys)}）')
        if not isinstance(it.get('title'), str) or not it.get('title', '').strip():
            e.append(f'{w} title 必填')
        body = it.get('body')
        if isinstance(body, str):
            body = [body]
        if not isinstance(body, list) or not body or not all(isinstance(p, str) and p.strip() for p in body):
            e.append(f'{w} body 必填：字符串，或字符串数组')
        for k in ('deck', 'judge'):
            if k in it and not (isinstance(it[k], str) and it[k].strip()):
                e.append(f'{w} {k} 要么不写，要么是非空字符串')
        b = it.get('badges', [])
        if not isinstance(b, list) or not all(isinstance(x, str) and x for x in b):
            e.append(f'{w} badges 是字符串数组，写来源名，如 ["HN", "X"]')
        for ln in it.get('links', []) or []:
            if not isinstance(ln, dict) or not ln.get('label') or not re.match(r'https?://', str(ln.get('url', ''))):
                e.append(f'{w} links 每项要有 label 和 http(s) url：{ln}')
        if it.get('id') is not None:
            ids.append(str(it['id']))
    if len(ids) != len(set(ids)):
        e.append('items 的 id 有重复')
    for g in keys:
        if not any(it.get('group') == g for it in items if isinstance(it, dict)):
            e.append(f'栏目 {g} 没有条目，删掉它或补条目')
    return e


# ---------------------------------------------------------------- 推导页面需要的字段
def derive(src, now=None):
    now = now or now_shanghai()
    kind = src['kind']
    groups = src.get('groups') or DEFAULT_GROUPS[kind]
    iss = {'kind': kind}
    if kind == 'digest':
        d = dt.date.fromisoformat(src['date'])
        slot = src.get('slot') or ('morning' if now.hour < 15 else 'evening')
        part, ed = SLOT[slot]
        wd = WEEKDAYS[d.weekday()]
        md = f'{d.month}/{d.day}'
        iss.update(id=f'{d.isoformat()}-{slot}', date=d.isoformat(), slot=slot, weekday=wd,
                   eyebrow=f'{ed} · {d.month} 月 {d.day} 日 {wd}',
                   label=f'{md} {wd} {part}', short=f'{md} {part}',
                   title=f'{part}雷达 · {md}（{wd}）')
    else:
        a, b = dt.date.fromisoformat(src['start']), dt.date.fromisoformat(src['end'])
        end_id = f'{b.day:02d}' if (a.year, a.month) == (b.year, b.month) else b.isoformat()[5:]
        span = f'{a.month}/{a.day}–{b.month}/{b.day}'
        cn_end = f'{b.day} 日' if a.month == b.month else f'{b.month} 月 {b.day} 日'
        iss.update(id=f'week-{a.isoformat()}-to-{end_id}', start=a.isoformat(), end=b.isoformat(),
                   eyebrow=f'周览 · {a.month} 月 {a.day} 日至 {cn_end}',
                   label=f'一周总览 {span}', short='一周总览', title=f'产品雷达周览 · {span}')
    intro = src['intro'] if isinstance(src['intro'], list) else [src['intro']]
    iss.update(headline=src['headline'].strip(), deck=src['deck'].strip(), window=src['window'].strip(),
               intro=[p.strip() for p in intro], groups=[{'key': g['key'], 'label': g['label']} for g in groups])
    items, count, first_new = [], {}, True
    for it in src['items']:
        g = it['group']
        count[g] = count.get(g, 0) + 1
        body = it['body'] if isinstance(it['body'], list) else [it['body']]
        out = {
            'id': str(it.get('id') or f'{ID_PREFIX.get(g, g[0])}{count[g]}'),
            'group': g,
            'lead': g == 'new' and first_new,
            'num': count[g],
            'title': it['title'].strip(),
            'badges': list(it.get('badges') or []),
            'body': [p.strip() for p in body],
            'links': [{'label': ln['label'], 'url': ln['url']} for ln in (it.get('links') or [])],
        }
        if g == 'new':
            first_new = False
        if it.get('deck'):
            out['deck'] = it['deck'].strip()
        if it.get('judge'):
            out['judge'] = it['judge'].strip()
            out['judgeLabel'] = '对你：' if kind == 'week' else '判断：'
        items.append(out)
    iss['items'] = items
    return iss


def issue_days(iss):
    """这一期覆盖的日期，写成 m/d。周览没有 start/end 时从期号里解析。"""
    if iss.get('kind') == 'week':
        a, b = iss.get('start'), iss.get('end')
        if not (a and b):
            m = re.match(r'week-(\d{4})-(\d{2}-\d{2})-to-(\d{2}(?:-\d{2})?)$', iss.get('id', ''))
            if not m:
                return set()
            a = f'{m.group(1)}-{m.group(2)}'
            b = f'{m.group(1)}-{m.group(3) if "-" in m.group(3) else m.group(2)[:2] + "-" + m.group(3)}'
        a, b = dt.date.fromisoformat(a), dt.date.fromisoformat(b)
        days = [a + dt.timedelta(n) for n in range((b - a).days + 1)]
    elif iss.get('date'):
        days = [dt.date.fromisoformat(iss['date'])]
    else:
        return set()
    return {f'{d.month}/{d.day}' for d in days}


def merge(prev_issues, new_issue, keep=6):
    """新一期放进历史：同 id 覆盖；日报按时间倒序、最多留 keep 期；周览只留最新一期，排在最后。"""
    def week_start(i):
        m = re.search(r'\d{4}-\d{2}-\d{2}', i.get('start') or i.get('id', ''))
        return m.group(0) if m else ''

    issues = [i for i in prev_issues if i.get('id') != new_issue['id']] + [new_issue]
    digests = [i for i in issues if i.get('kind') == 'digest']
    weeks = [i for i in issues if i.get('kind') == 'week']
    digests.sort(key=lambda i: (i.get('date', ''), i.get('slot') == 'evening'), reverse=True)
    weeks.sort(key=week_start, reverse=True)
    digests, weeks = digests[:keep], weeks[:1]
    # 新出的这一期一定保留（补发旧日期时也一样）
    if new_issue['kind'] == 'digest' and new_issue not in digests:
        digests = digests[:max(keep - 1, 0)] + [new_issue]
    if new_issue['kind'] == 'week':
        weeks = [new_issue]
    return digests + weeks


# ---------------------------------------------------------------- 无脚本静态版
TOKEN = re.compile(r'(`[^`]+`)|(\*\*[^*]+\*\*)|(https?://[^\s<>"\'）)」』，。；、]+)')


def esc(s):
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')


def inline(text):
    """和页面脚本里的 inline() 一致：`code`、**粗体**、裸链接。"""
    out, last = '', 0
    for m in TOKEN.finditer(text):
        out += esc(text[last:m.start()])
        if m.group(1):
            out += '<code>' + esc(m.group(1)[1:-1]) + '</code>'
        elif m.group(2):
            out += '<strong>' + esc(m.group(2)[2:-2]) + '</strong>'
        else:
            url, tail = m.group(3), ''
            t = re.search(r'[.,;:!?]+$', url)
            if t:
                tail, url = t.group(0), url[:-len(t.group(0))]
            out += f'<a class="inl" href="{esc(url)}" target="_blank" rel="noopener">{esc(url)}</a>{esc(tail)}'
        last = m.end()
    return out + esc(text[last:])


def lead_html(ps):
    out = []
    for i, p in enumerate(ps):
        m = re.match(r'^[^。]+。', p) if i == 0 else None
        out.append('<p>' + (f'<b class="s1">{inline(m.group(0))}</b>{inline(p[m.end():])}' if m else inline(p)) + '</p>')
    return ''.join(out)


def _issue_html(iss):
    iid = esc(iss['id'])
    label = {g['key']: g['label'] for g in iss['groups']}
    chips = ''.join(
        f'<span class="count-chip{" peach" if i == 0 else ""}">{esc(g["label"])} '
        f'{sum(1 for it in iss["items"] if it["group"] == g["key"])}</span>'
        for i, g in enumerate(iss['groups']))
    toc = ''.join(f'<li><a href="#card-{iid}-{esc(it["id"])}">{it["num"]}. {inline(it["title"])}</a></li>'
                  for it in iss['items'])
    h = (f'<section class="static-issue" id="issue-{iid}"><div class="static-cover">'
         f'<p class="eyebrow">{esc(iss["eyebrow"])}</p><h1>{esc(iss["headline"])}</h1>'
         f'<p class="cover-deck">{inline(iss["deck"])}</p>'
         f'<div class="lead">{lead_html(iss["intro"])}</div>'
         f'<p class="window"><span>覆盖</span>{esc(iss["window"])}</p>'
         f'<div class="counts">{chips}</div><ol class="static-toc">{toc}</ol></div>')
    for it in iss['items']:
        h += (f'<article class="static-card" id="card-{iid}-{esc(it["id"])}">'
              f'<div class="num-row"><span class="num">{it["num"]}</span><span class="kind-tag">{esc(label[it["group"]])}</span></div>'
              f'<h2 class="item-title">{inline(it["title"])}</h2>')
        if it.get('deck'):
            h += f'<p class="item-deck">{inline(it["deck"])}</p>'
        if it.get('badges'):
            h += '<div class="badges">' + ''.join(f'<span class="badge">{esc(b)}</span>' for b in it['badges']) + '</div>'
        if it.get('judge'):
            h += (f'<p class="judge"><span class="lbl">{esc(it.get("judgeLabel", "判断："))}</span>{inline(it["judge"])}</p>'
                  '<div class="rule" role="presentation"></div>')
        h += '<div class="body">' + ''.join(f'<p>{inline(p)}</p>' for p in it['body']) + '</div>'
        if it.get('links'):
            h += '<div class="links">' + ''.join(
                f'<a class="link" href="{esc(ln["url"])}" target="_blank" rel="noopener">{esc(ln["label"])}</a>'
                for ln in it['links']) + '</div>'
        h += f'<a class="jump-top" href="#issue-{iid}">回到本期封面</a></article>'
    return h + '</section>'


def static_html(data):
    """静态版放最新一期，再加周览（如果有）。"""
    issues = data['issues']
    shown = issues[:1] + [i for i in issues[1:] if i.get('kind') == 'week'][:1]
    nav = ''.join(f'<a href="#issue-{esc(i["id"])}">{esc(i["label"])}</a>' for i in shown)
    return ('<header class="static-top" id="static-top"><div class="static-brand">产品雷达 · 静态阅读</div>'
            f'<nav class="static-nav" aria-label="期次">{nav}</nav></header>'
            + ''.join(_issue_html(i) for i in shown)
            + f'<p class="static-foot">无脚本模式 · 生成于 {esc(data["generatedAt"])}<br/>开启 JavaScript 可使用翻页阅读器</p>')


def render(template, data):
    assert '__RADAR_DATA__' in template and '__RADAR_STATIC__' in template, '模板缺占位符'
    return (template.replace('__RADAR_STATIC__', static_html(data))
                    .replace('__RADAR_DATA__', data_js(data)))
