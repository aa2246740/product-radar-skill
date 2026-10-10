#!/usr/bin/env python3
"""把一期 issue.json 生成完整的产品雷达 index.html。

用法：
  python3 -I build.py issue.json -o index.html                     # 只有这一期
  python3 -I build.py issue.json --prev 上一版/index.html -o index.html  # 并入历史，日报最多留 6 期
选项：
  --keep N            日报最多保留几期（默认 6）
  --now "YYYY-MM-DD HH:MM"  生成时间（上海时间），默认取当前时间

issue.json 有错时不生成，逐条列出错误，退出码 1。
"""
import argparse
import datetime as dt
import json
import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
import radar  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description='issue.json → index.html')
    ap.add_argument('issue')
    ap.add_argument('-o', '--out', default='index.html')
    ap.add_argument('--prev')
    ap.add_argument('--keep', type=int, default=6)
    ap.add_argument('--now')
    a = ap.parse_args()

    try:
        src = json.load(open(a.issue, encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as ex:
        print(f'✗ 读不了 {a.issue}：{ex}')
        return 1
    errs = radar.validate(src)
    if errs:
        for e in errs:
            print('✗', e)
        print(f'issue.json 有 {len(errs)} 处错误，没有生成')
        return 1

    now = (dt.datetime.strptime(a.now, '%Y-%m-%d %H:%M').replace(tzinfo=radar.SHANGHAI)
           if a.now else radar.now_shanghai())
    issue = radar.derive(src, now)

    prev = []
    if a.prev:
        pd = radar.load_data(open(a.prev, encoding='utf-8').read())
        if not pd:
            print(f'✗ {a.prev} 里找不到 window.RADAR_DATA')
            return 1
        prev = pd['issues']

    data = {
        'generatedAt': now.strftime('%Y-%m-%d %H:%M') + '（Asia/Shanghai）',
        'latest': issue['id'],
        'issues': radar.merge(prev, issue, a.keep),
    }
    kept = {i['id'] for i in data['issues']}
    dropped = [i['id'] for i in prev if i.get('id') not in kept]
    template = open(os.path.join(HERE, '..', 'assets', 'template.html'), encoding='utf-8').read()
    open(a.out, 'w', encoding='utf-8').write(radar.render(template, data))
    print(f'已生成 {a.out}：本期 {issue["id"]}（{len(issue["items"])} 条），共 {len(data["issues"])} 期：'
          + '、'.join(i['id'] for i in data['issues']))
    if dropped:
        print('移出页面的旧期次：' + '、'.join(dropped) + '（判断里不要再连这些期次的条目）')
    here = os.path.dirname(os.path.abspath(__file__))
    print(f'下一步：python3 -I {os.path.join(here, "lint_radar.py")} {a.out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
