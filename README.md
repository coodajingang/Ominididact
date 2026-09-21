# 🏛️ 研学知识库 多材料静态发布包

本压缩包是由 **Omnididact · 全材料系统化自我教育与研学引擎** 构建的纯静态研习空间，**无需任何 Python 或后端服务器依赖**。
解压后可直接部署到 **GitHub Pages**、**Cloudflare Pages**、**Nginx**、**Vercel** 或任何静态 Web 托管服务。

---

## 📁 目录结构
* `index.html`: 个人研习大厅门户（含独立 SEO/GEO、结构化元数据、即时搜索与主题切换）
* `docs.json`: 站点研习材料清单数据源
* `robots.txt`: 搜索引擎爬虫协议规范
* `sitemap.xml`: 站点地图，助力 Google / Bing / 百度 等搜索引擎及 AI 引擎快速收录
* `docs/`: 各材料研学独立子空间（每个子目录下包含独有 SEO/GEO 双语阅读器与离线闪卡系统）
* `README.md`: 本部署与维护指引

---

## 🚀 部署指引

### 方式一：GitHub Pages（极简免费）
1. 在 GitHub 创建新仓库（如 `my-study-hall`）。
2. 将本压缩包内的所有文件解压后推送到仓库的 `main` 分支（或 `gh-pages` 分支）。
3. 在 GitHub 仓库的 **Settings** -> **Pages** 中，将 Source 选为 **Deploy from a branch**，Branch 选择 `main` / `root`。
4. 保存后约 1 分钟即可通过 `https://<用户名>.github.io/my-study-hall/` 在线访问！

### 方式二：Cloudflare Pages（推荐，全球极速）
1. 登录 [Cloudflare Dashboard](https://dash.cloudflare.com/)，进入 **Workers & Pages** -> **Create application** -> **Pages** -> **Upload assets**。
2. 项目名称填写（如 `my-study-hall`）。
3. 将本压缩包解压后的**整个文件夹**直接拖入网页上传区。
4. 点击 **Deploy site**，10 秒内即可拥有全局 CDN 加速的专属个人研习空间！

### 方式二：Nginx 服务器
解压到目标目录（如 `/var/www/study-library`）：
```nginx
server {
    listen 80;
    server_name library.yourdomain.com;
    root /var/www/study-library;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    gzip on;
    gzip_types text/plain text/css application/javascript application/json text/html;
}
```
执行 `nginx -s reload` 即刻上线！

---

## 🧩 后续如何增量添加新文档？
后续若有新材料处理完成，无需重新全量打包整站：
1. 在研学系统中选择该文档导出 **【🧩 增量补丁包 (.zip)】**；
2. 将补丁包解压后的 `docs/doc_20260917_154617_792a69` 放入服务器/站点的 `docs/` 目录下；
3. 将补丁包中的 `patch_entry.json` 内容追加粘贴进站点根目录的 `docs.json` 数组中；
4. 刷新首页，新文档即可自动在导航大厅中亮相！
