#!/usr/bin/env python3
"""检查产品雷达 index.html 是否符合 SKILL.md 的规则。

用法：python3 -I lint_radar.py index.html          # 只查本次 build 出的那一期
      python3 -I lint_radar.py index.html --all    # 查文件里所有期次
有违规时退出码为 1。通过时打印剩下的「判断」，供人工做替换测试。
"""
import json
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import radar  # noqa: E402

# ---------------------------------------------------------------- 词表
BAN_WORDS = [
    '赋能', '重塑', '颠覆', '炸裂', '破局', '改牌桌', '牌桌', '一等公民', '一等功能',
    '护城河', '吵成一团', '最吵', '变硬', '变厚', '回击', '寒蝉', '终于', '真正',
    '惊人', '重磅', '刷屏', '狂飙', '爆发', '赛道', '抢入口', '正面撞', '正面打',
    '值得关注', '值得一看', '不容忽视', '深度解析', '一文读懂',
    # unslop 3 空转修饰
    '彰显', '凸显', '助力', '旨在', '致力于', '标志着', '体现了',
    # unslop 5 含糊出处
    '业内人士', '有观点认为', '分析人士', '外界普遍',
    # unslop 23 填充语
    '值得注意的是', '需要指出的是', '据了解', '可以说',
    # unslop 30 副词，要写就写数字
    '显著', '大幅', '大大', '极大', '明显',
]
BAN_PATTERNS = [
    (r'不是[^，。；：]{1,20}[，,]\s*(而)?是', '「不是X，是Y」'),
    (r'而不是', '「X 而不是 Y」'),
    (r'(从|由)[^，。；]{1,12}(变成|变为|转到|转向|走向|进到)', '「从X变成/转到Y」'),
    (r'为什么[^，。；]*——', '「为什么…——因为…」'),
    (r'[？?！!]', '问号 / 感叹号'),
    (r'——', '破折号'),
    (r'已经(成为|成了|变成|变为|是)', '「已经成为 / 已经是…」'),
]
# unslop 14：题、副题、导语、判断里不用冒号
NO_COLON_KINDS = ('headline', 'title', 'deck', 'lead', 'judge')
# 题里出现就是在下判断
TITLE_VERDICT = ['短板', '亮点', '神器', '最强', '碾压', '吊打', '野心', '豪赌', '王炸', '杀手级', '天花板', '封神']
INTRO_PREVIEW = ['最值得看', '值得看的', '大新闻', '信息量', '这班', '这一窗', '来自 PH', '来自 HN', '来自 X', '来自 YouTube']

# 判断：空话、观望、泛泛推荐、重复口径
JUDGE_BAN = [
    '少见', '罕见', '信号是', '是个信号', '一个信号', '方向', '值得', '参考价值', '可以参考', '可以试', '可以看看', '看看就行',
    '观察名单', '分量轻', '小工具', '真实存在', '同一条线', '一条线', '默认出口', '刚需', '卖点',
    '拭目以待', '有待观察', '后续披露', '再深看', '意味着', '本质上', '说明了',
]
# 观望：「要等…」「等…再…」。列举用的「A、B 等」前面不是句首，不算
JUDGE_WAIT = r'(要等|再等|先等|得等|等到|(^|[，。；：])等)[^。；]{0,24}(再|之后|以后|结果|反馈|披露|案例|验证|消息)?'
JUDGE_CAVEAT = ['官方口径', '官方称', '自测', '自家测', '作者自己说', '创始人自述', '佐证', '宣称', '没给数', '没有公开']

LIMIT = dict(headline=30, title=26, deck=54, lead=130, judge=70)
DIGEST_JUDGE_MAX = 3


def width(s):
    """汉字和全角标点（含 … — ·）算 1，其余算 0.5。"""
    return sum(1 if unicodedata.east_asian_width(c) in 'WFA' else 0.5 for c in s)


def sentences(s):
    return [x for x in re.split(r'(?<=[。！？])', s) if x.strip()]


def clauses(s):
    """切成分句，只留至少 3 个汉字、宽度 ≥ 7 的，用来查原句重复。"""
    out = []
    for c in re.split(r'[，。；：、（）()「」]', s):
        c = c.strip()
        if len(re.findall(r'[一-鿿]', c)) >= 3 and width(c) >= 7:
            out.append(c)
    return out


def norm_num(s):
    return re.sub(r'(?<=\d)[,\s](?=\d)', '', s)


def squash(s):
    """去空白、连字符和千分位，× 视同「倍」，便于原样比对。"""
    s = re.sub(r'(?<=[A-Za-z])[-–](?=[A-Za-z0-9])', '', norm_num(s))   # GPT-6 → GPT6，保留 50–80
    return re.sub(r'\s+', '', s).replace('×', '倍')


STRICT_UNITS = '倍万亿千百%'


def number_errors(text, title, src):
    """题 / 副题里的每个数字都要在正文里原样出现。

    - 版本号（GPT-6、Llama2、Pi 1.0、Large 4）：连英文名一起比，题里出现过就当产品名放行。
    - 倍、万、亿、% 这类会改变量级的单位连单位一起比：「快 30 倍」不能靠正文的「30 万次」过关。
    - 一位数带量词（9 个月）也连量词比。
    - 其余数字只要在正文里单独出现过就行。
    """
    bad = []
    flat_src, flat_title = squash(src), squash(title)
    t = norm_num(text)
    for m in re.finditer(r'\d[\d.]*', t):
        n = m.group(0).rstrip('.')
        if not n:
            continue
        before, after = t[:m.start()], t[m.end():]
        u = re.match(r'\s*([一-鿿%×])', after)
        unit = u.group(1).replace('×', '倍') if u else ''
        glued = re.search(r'([A-Za-z][A-Za-z0-9]*)[-.]?$', before)       # GPT-6、Llama2
        spaced = re.search(r'([A-Z][A-Za-z0-9]*) $', before)             # Pi 1.0、Large 4
        word = glued or (spaced if not unit else None)
        if word:
            key = squash(word.group(1) + n)
            if key in flat_title or key in flat_src:
                continue
        # 一位数带量词（9 个月、2 个）也连单位比，不然正文里随便哪个「9」都能让它过关
        if unit and (unit in STRICT_UNITS or (len(n) == 1 and re.match(r'[一-鿿]', unit))):
            ok = squash(n + unit) in flat_src
        else:
            ok = re.search(r'(?<![\d.])' + re.escape(n) + r'(?![\d])', flat_src) is not None
        if not ok:
            bad.append(n + unit)
    return bad


COMMON_CAPS = {'ai', 'api', 'mcp', 'llm', 'gpu', 'cpu', 'ui', 'ux', 'sdk', 'cli', 'pr', 'ceo', 'cto', 'pm', 'ph', 'hn', 'x', 'saas', 'byok'}


def latin_words(s, proper=False):
    words = re.findall(r'[A-Za-z][A-Za-z0-9+#.]*[A-Za-z0-9+#]|[A-Za-z]{2,}', s)
    if proper:
        words = [w for w in words if re.search(r'[A-Z]', w)]
    return set(w.lower() for w in words) - (COMMON_CAPS if proper else set())


def overlap4(a, b):
    """a 里任意 4 个连续字符（至少 2 个汉字）原样出现在 b 里，返回它。"""
    a2, b2 = squash(a), squash(b)
    for i in range(len(a2) - 3):
        g = a2[i:i + 4]
        if len(re.findall(r'[一-鿿]', g)) >= 2 and g in b2:
            return g
    return None


def main(path, check_all=False):
    html = open(path, encoding='utf-8').read()
    data = radar.load_data(html)
    if not data or not data.get('issues'):
        print('✗ 找不到 window.RADAR_DATA，或里面没有期次')
        return 1
    latest = data.get('latest') or data['issues'][0]['id']
    days = set().union(*(radar.issue_days(i) for i in data['issues']))   # C 连线只能连这些日期
    checked = [i for i in data['issues'] if check_all or i['id'] == latest]
    errs = []

    def common(where, kind, text):
        if not text:
            return
        if kind in LIMIT and width(text) > LIMIT[kind]:
            errs.append(f'{where} [{kind}] 过长 {width(text):.0f}>{LIMIT[kind]}：{text}')
        for w in BAN_WORDS:
            if w in text:
                errs.append(f'{where} [{kind}] 禁用词「{w}」：{text}')
        for pat, name in BAN_PATTERNS:
            if re.search(pat, text):
                errs.append(f'{where} [{kind}] 句式 {name}：{text}')
        if kind in NO_COLON_KINDS and re.search(r'[：:]', text):
            errs.append(f'{where} [{kind}] 冒号：{text}')

    for iss in checked:
        iid = iss['id']
        week = iss.get('kind') == 'week'
        head, deck = iss.get('headline', ''), iss.get('deck', '')
        lead = ''.join(iss.get('intro', []))

        # ---- 封面区
        for f in ('headline', 'deck', 'window'):
            if not iss.get(f):
                errs.append(f'{iid} 缺字段 {f}')
        eb = iss.get('eyebrow', '')
        if re.search(r'[A-Z ]{8,}', eb) or not re.match(r'^(早刊|晚刊|周览) · ', eb):
            errs.append(f'{iid} [eyebrow] 应为「早刊/晚刊/周览 · 日期」：{eb}')
        common(iid, 'headline', head)
        common(iid, 'deck', deck)
        common(iid, 'lead', lead)
        if len(sentences(lead)) > 3:
            errs.append(f'{iid} [lead] 超过 3 句')
        for kw in INTRO_PREVIEW:
            if kw in lead:
                errs.append(f'{iid} [lead] 预告 / 时间窗 / 来源清单「{kw}」，挪到 window 或删掉')
        for c in clauses(head) + clauses(deck):
            if c in lead:
                errs.append(f'{iid} [lead] 复述了封面题或副题「{c}」')
        for c in clauses(deck):
            if c in head:
                errs.append(f'{iid} [deck] 复述了封面题「{c}」')
        all_src = ' '.join(' '.join(it.get('body', [])) + ' ' + ' '.join(it.get('badges', [])) for it in iss['items'])
        all_titles = ' '.join(it.get('title', '') for it in iss['items'])
        for k, text in (('headline', head), ('deck', deck), ('lead', lead)):
            for n in number_errors(text, all_titles, all_src):
                errs.append(f'{iid} [{k}] 封面里的「{n}」在本期任何一条正文里都找不到原样')

        lead_item = next((it for it in iss['items'] if it.get('lead')), iss['items'][0] if iss['items'] else None)
        # 封面副题只讲封面题那件事：副题里的英文专名要在题或头条条目里出现过
        if iss['items'] and not week:
            hw = latin_words(head)
            top = max(iss['items'], key=lambda it: (len(hw & latin_words(it.get('title', ''))), it is lead_item))
            story = head + ' ' + top.get('title', '') + ' ' + ' '.join(top.get('body', []))
            for w in sorted(latin_words(deck, proper=True) - latin_words(story)):
                errs.append(f'{iid} [deck] 封面副题里的「{w}」不在头条那条的正文里；如果是另一件事，放进导语')

        # ---- 条目
        n_judge = 0
        for it in iss['items']:
            where = f'{iid}/{it["id"]}'
            t, d, j = it.get('title', ''), it.get('deck'), it.get('judge')
            body = ' '.join(it.get('body', []))
            if not week and len(sentences(''.join(it.get('body', [])))) > 6:
                errs.append(f'{where} [body] 正文超过 6 句，删掉次要信息')
            common(where, 'title', t)
            common(where, 'deck', d)
            for w in BAN_WORDS:
                if w in body:
                    errs.append(f'{where} [body] 禁用词「{w}」：{body}')
            for w in TITLE_VERDICT:
                if w in t:
                    errs.append(f'{where} [title] 题里下了判断「{w}」：{t}')
            if d and t:
                g = overlap4(t, d)
                if t in d or g:
                    errs.append(f'{where} [deck] 复述了题「{g or t}」')
            src = body + ' ' + ' '.join(it.get('badges', []))
            for n in number_errors(t, t, src) + number_errors(d or '', t, src):
                errs.append(f'{where} 题/副题里的「{n}」在正文里找不到原样')
            if d:
                for w in sorted(latin_words(d, proper=True) - latin_words(t + ' ' + src)):
                    errs.append(f'{where} [deck] 副题里的「{w}」在正文里找不到')
            if it is lead_item and d:
                for c in clauses(deck) + clauses(lead):
                    if c in d:
                        errs.append(f'{where} [deck] 头条条目副题重复了封面区「{c}」')

            # ---- 判断
            if not j:
                continue
            n_judge += 1
            if week and it.get('group') != 'theme':
                errs.append(f'{where} [judge] 周览只有主线条目可以带判断')
            common(where, 'judge', j)
            if len(sentences(j)) > 2:
                errs.append(f'{where} [judge] 超过 2 句：{j}')
            for w in JUDGE_BAN:
                if w in j:
                    errs.append(f'{where} [judge] 空话「{w}」：{j}')
            if re.search(JUDGE_WAIT, j):
                errs.append(f'{where} [judge] 观望式结尾（等…再…），这不是判断：{j}')
            for w in JUDGE_CAVEAT:
                if w in j:
                    errs.append(f'{where} [judge] 口径提醒「{w}」应写在正文，不进判断：{j}')
            for c in clauses(j):
                if width(c) >= 10 and c in body:
                    errs.append(f'{where} [judge] 照抄正文「{c}」')
            for md in re.findall(r'(?<![\d/])(\d{1,2}/\d{1,2})(?![\d/])', j):
                if md not in days:
                    errs.append(f'{where} [judge] 提到 {md}，但页面里没有这一天的期次（可能已被 --keep 挤出），换一条连')
        if not week and n_judge > DIGEST_JUDGE_MAX:
            errs.append(f'{iid} 判断 {n_judge} 条，日报每期最多 {DIGEST_JUDGE_MAX} 条')


    # ---- 无脚本静态版必须是 build.py 按数据生成的
    if radar.static_block(html) != radar.static_html(data):
        errs.append('静态版（#static）和数据不一致：别手改 index.html，改 issue.json 后重新跑 build.py')

    errs = list(dict.fromkeys(errs))
    for e in errs:
        print('✗', e)
    n_items = sum(len(i['items']) for i in checked)
    scope = '全部' if check_all else f'本期 {latest}'
    print(f'检查{scope}：{len(checked)} 期、{n_items} 条：{"通过" if not errs else str(len(errs)) + " 处违规"}')
    if not errs:
        print('\n剩下的判断，逐条做替换测试（把这条新闻换成同类的另一条，判断还成立就删）：')
        for iss in checked:
            for it in iss['items']:
                if it.get('judge'):
                    print(f'  {iss["id"]}/{it["id"]} {it["title"]}：{it["judge"]}')
    return 1 if errs else 0


if __name__ == '__main__':
    args = [x for x in sys.argv[1:] if not x.startswith('--')]
    sys.exit(main(args[0] if args else 'index.html', '--all' in sys.argv))
