# product-radar-skill

产品雷达：把一份 `issue.json` 生成成单文件 `index.html` 的新闻页，并检查文案。

页面有三种视图：桌面报纸版面、手机翻页阅读器、无 JavaScript 时的静态版。样式、脚本和图标全部内联，不依赖外部资源。

## 安装

把整个仓库放进你的 skills 目录，文件夹名叫 `product-radar`。需要 Python 3，不需要装第三方库。

## 用法

1. 按 `references/schema.md` 写 `issue.json`，样例见 `references/issue.example.json`。
2. 生成页面：`python3 -I scripts/build.py issue.json --prev 上一版/index.html -o index.html`。第一次没有上一版就不带 `--prev`。
3. 检查文案：`python3 -I scripts/lint_radar.py index.html`。不通过就改 `issue.json`，再回到第 2 步。

页面只由 `build.py` 生成。不要手改生成后的 `index.html`，lint 会逐字比对静态版，手改了会报错。

写作规则见 `SKILL.md`。核心两条：题和副题只陈述事实，判断默认不写。
