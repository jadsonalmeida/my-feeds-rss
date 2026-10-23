import json
import os
import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
}

OUTPUT_DIR = "public"
FEEDS_DIR = os.path.join(OUTPUT_DIR, "feeds")


def fetch_html(url: str, render_js: bool = False, wait_for: str = "") -> str:
    """Busca o HTML de uma página via requests (rápido) ou Playwright (para SPAs/React)."""
    if not render_js:
        resp = requests.get(url, headers=HEADERS, timeout=25)
        resp.raise_for_status()
        return resp.text

    # Renderização com JavaScript usando Playwright
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=HEADERS["User-Agent"])
        page = context.new_page()
        page.goto(url, wait_until="networkidle", timeout=45000)
        if wait_for:
            try:
                page.wait_for_selector(wait_for, timeout=10000)
            except Exception as e:
                print(f"  [Aviso] Timeout aguardando seletor '{wait_for}': {e}")
        else:
            page.wait_for_timeout(2000)
        html = page.content()
        browser.close()
        return html


def extract_auto(soup: BeautifulSoup, base_url: str, max_items: int = 20) -> list[dict]:
    """Heurística estilo RSS.app para detectar artigos/notícias automaticamente sem seletores."""
    items = []
    seen_links = set()
    base_domain = urlparse(base_url).netloc

    # 1. Tenta procurar tags <article> ou containers comuns de post
    candidates = soup.select("article, .post, .card, .news-item, .entry, [class*='post-'], [class*='article-']")

    if candidates:
        for el in candidates:
            a_tag = el.select_one("h1 a, h2 a, h3 a, h4 a, a[href]")
            if not a_tag:
                continue
            href = a_tag.get("href", "").strip()
            if not href or href.startswith("#") or href.startswith("javascript:"):
                continue
            full_url = urljoin(base_url, href)
            if full_url in seen_links:
                continue

            # Título
            heading = el.select_one("h1, h2, h3, h4")
            title = heading.get_text(" ", strip=True) if heading else a_tag.get_text(" ", strip=True)
            if not title or len(title) < 8:
                continue

            # Descrição
            p_tag = el.select_one("p, .summary, .excerpt, .description")
            desc = p_tag.get_text(" ", strip=True) if p_tag else ""

            # Imagem
            img_tag = el.select_one("img")
            img_url = ""
            if img_tag:
                img_src = img_tag.get("src") or img_tag.get("data-src") or ""
                if img_src and not img_src.startswith("data:"):
                    img_url = urljoin(base_url, img_src)

            seen_links.add(full_url)
            items.append({
                "title": title,
                "link": full_url,
                "description": desc,
                "image": img_url,
            })
            if len(items) >= max_items:
                return items

    # 2. Fallback: Procura links dentro de títulos (h1, h2, h3)
    for a_tag in soup.select("h1 a[href], h2 a[href], h3 a[href], a[href] h2, a[href] h3"):
        if a_tag.name != "a":
            a_tag = a_tag.find_parent("a")
        if not a_tag:
            continue

        href = a_tag.get("href", "").strip()
        if not href or href.startswith("#") or href.startswith("javascript:"):
            continue
        full_url = urljoin(base_url, href)
        if full_url in seen_links:
            continue

        title = a_tag.get_text(" ", strip=True)
        if not title or len(title) < 10:
            continue

        # Evita links de menu genéricos
        if urlparse(full_url).netloc == base_domain and full_url.rstrip("/") == base_url.rstrip("/"):
            continue

        seen_links.add(full_url)
        items.append({
            "title": title,
            "link": full_url,
            "description": "",
            "image": "",
        })
        if len(items) >= max_items:
            break

    return items


def extract_with_selectors(soup: BeautifulSoup, base_url: str, selectors: dict, max_items: int = 20) -> list[dict]:
    """Extrai itens usando seletores CSS definidos no feeds.json."""
    items = []
    seen_links = set()

    item_sel = selectors.get("item", "").strip()
    if not item_sel:
        return extract_auto(soup, base_url, max_items)

    title_sel = selectors.get("title", "").strip()
    link_sel = selectors.get("link", "").strip()
    desc_sel = selectors.get("description", "").strip()
    img_sel = selectors.get("image", "").strip()

    for el in soup.select(item_sel):
        # Título
        if title_sel:
            t_el = el.select_one(title_sel)
            title = t_el.get_text(" ", strip=True) if t_el else ""
        else:
            title = el.get_text(" ", strip=True)

        # Link
        link = ""
        if link_sel:
            l_el = el.select_one(link_sel)
            if l_el:
                link = l_el.get("href", "")
        elif el.name == "a":
            link = el.get("href", "")
        else:
            a_el = el.select_one("a[href]")
            if a_el:
                link = a_el.get("href", "")

        if not title or not link:
            continue

        full_url = urljoin(base_url, link.strip())
        if full_url in seen_links:
            continue

        # Descrição
        desc = ""
        if desc_sel:
            d_el = el.select_one(desc_sel)
            if d_el:
                desc = d_el.get_text(" ", strip=True)

        # Imagem
        img_url = ""
        if img_sel:
            i_el = el.select_one(img_sel)
            if i_el:
                src = i_el.get("src") or i_el.get("data-src") or ""
                if src and not src.startswith("data:"):
                    img_url = urljoin(base_url, src)

        seen_links.add(full_url)
        items.append({
            "title": title,
            "link": full_url,
            "description": desc,
            "image": img_url,
        })
        if len(items) >= max_items:
            break

    return items


def build_rss_xml(feed_cfg: dict, items: list[dict], output_path: str):
    """Gera o arquivo XML do RSS 2.0 compatível com qualquer leitor de RSS."""
    fg = FeedGenerator()
    fg.id(feed_cfg["url"])
    fg.title(feed_cfg.get("title", feed_cfg["id"]))
    fg.link(href=feed_cfg["url"], rel="alternate")
    fg.description(feed_cfg.get("description") or f"Feed RSS gerado automaticamente de {feed_cfg['url']}")
    fg.language("pt-BR")
    fg.lastBuildDate(datetime.now(timezone.utc))

    # Invertemos na inserção ou mantemos a ordem de relevância
    for item in reversed(items):
        fe = fg.add_entry()
        fe.id(item["link"])
        fe.title(item["title"])
        fe.link(href=item["link"])

        desc_html = ""
        if item.get("image"):
            desc_html += f'<p><img src="{item["image"]}" alt="{item["title"]}" style="max-width:100%;"/></p>'
        if item.get("description"):
            desc_html += f"<p>{item['description']}</p>"
        if not desc_html:
            desc_html = f'<p><a href="{item["link"]}">Ler artigo completo</a></p>'

        fe.description(desc_html)

    fg.rss_file(output_path, pretty=True)


def build_dashboard_html(metadata_list: list[dict], updated_at: str):
    """Gera o painel visual (index.html) estilo RSS.app para gerenciar e copiar links."""
    cards_html = ""
    for meta in metadata_list:
        status_badge = (
            f'<span class="badge success">Ativo ({meta["count"]} itens)</span>'
            if meta["status"] == "ok"
            else f'<span class="badge error">Erro: {meta.get("error", "Falha")}</span>'
        )
        mode_badge = (
            '<span class="badge js">JS / Dinâmico</span>'
            if meta.get("render_js")
            else '<span class="badge static">HTML Rápido</span>'
        )

        preview_items = ""
        for it in meta.get("preview", [])[:4]:
            preview_items += f'<li><a href="{it["link"]}" target="_blank" rel="noopener">{it["title"]}</a></li>'
        if not preview_items:
            preview_items = '<li class="empty">Nenhum item extraído na última execução.</li>'

        cards_html += f"""
        <div class="card">
            <div class="card-header">
                <div>
                    <h3>{meta["title"]}</h3>
                    <a href="{meta["source_url"]}" target="_blank" class="source-link">{meta["source_url"]}</a>
                </div>
                <div class="badges">
                    {mode_badge}
                    {status_badge}
                </div>
            </div>
            <p class="desc">{meta.get("description", "")}</p>
            <div class="rss-box">
                <input type="text" readonly value="{meta["xml_rel_path"]}" class="rss-input" data-rel="{meta["xml_rel_path"]}" />
                <button onclick="copyRss(this)" class="btn-copy">Copiar Link RSS</button>
                <a href="{meta["xml_rel_path"]}" target="_blank" class="btn-open">Abrir XML</a>
            </div>
            <div class="preview">
                <h4>Últimos itens capturados:</h4>
                <ul>{preview_items}</ul>
            </div>
        </div>
        """

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Meu Servidor RSS Pessoal</title>
    <style>
        :root {{
            --bg: #0f172a;
            --surface: #1e293b;
            --border: #334155;
            --text: #f8fafc;
            --muted: #94a3b8;
            --primary: #f97316;
            --primary-hover: #ea580c;
            --success: #22c55e;
            --error: #ef4444;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.5;
            padding: 2rem 1rem;
        }}
        .container {{ max-width: 1000px; margin: 0 auto; }}
        header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 1rem;
            margin-bottom: 2rem;
            padding-bottom: 1.5rem;
            border-bottom: 1px solid var(--border);
        }}
        .brand h1 {{ font-size: 1.75rem; display: flex; align-items: center; gap: 0.5rem; }}
        .brand p {{ color: var(--muted); font-size: 0.9rem; margin-top: 0.25rem; }}
        .btn-builder {{
            background: var(--primary);
            color: white;
            border: none;
            padding: 0.65rem 1.2rem;
            border-radius: 8px;
            font-weight: 600;
            cursor: pointer;
            text-decoration: none;
            font-size: 0.95rem;
        }}
        .btn-builder:hover {{ background: var(--primary-hover); }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(440px, 1fr)); gap: 1.5rem; }}
        @media (max-width: 600px) {{ .grid {{ grid-template-columns: 1fr; }} }}
        .card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 1.5rem;
            display: flex;
            flex-direction: column;
            gap: 1rem;
        }}
        .card-header {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; }}
        .card-header h3 {{ font-size: 1.15rem; }}
        .source-link {{ color: var(--muted); font-size: 0.82rem; text-decoration: none; word-break: break-all; }}
        .source-link:hover {{ text-decoration: underline; }}
        .badges {{ display: flex; gap: 0.4rem; flex-wrap: wrap; flex-shrink: 0; }}
        .badge {{ font-size: 0.72rem; padding: 0.2rem 0.55rem; border-radius: 999px; font-weight: 600; }}
        .badge.success {{ background: rgba(34, 197, 94, 0.15); color: #4ade80; }}
        .badge.error {{ background: rgba(239, 68, 68, 0.15); color: #f87171; }}
        .badge.js {{ background: rgba(168, 85, 247, 0.15); color: #c084fc; }}
        .badge.static {{ background: rgba(56, 189, 248, 0.15); color: #38bdf8; }}
        .desc {{ color: var(--muted); font-size: 0.9rem; }}
        .rss-box {{ display: flex; gap: 0.5rem; }}
        .rss-input {{
            flex: 1;
            background: #0f172a;
            border: 1px solid var(--border);
            color: var(--text);
            padding: 0.5rem 0.75rem;
            border-radius: 6px;
            font-size: 0.85rem;
            font-family: monospace;
        }}
        .btn-copy, .btn-open {{
            background: #334155;
            color: white;
            border: none;
            padding: 0.5rem 0.8rem;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.82rem;
            font-weight: 500;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
        }}
        .btn-copy:hover, .btn-open:hover {{ background: #475569; }}
        .preview h4 {{ font-size: 0.82rem; text-transform: uppercase; color: var(--muted); margin-bottom: 0.5rem; letter-spacing: 0.04em; }}
        .preview ul {{ list-style: none; display: flex; flex-direction: column; gap: 0.4rem; }}
        .preview li {{ font-size: 0.88rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
        .preview a {{ color: #e2e8f0; text-decoration: none; }}
        .preview a:hover {{ color: var(--primary); text-decoration: underline; }}
        .modal {{
            display: none;
            position: fixed;
            inset: 0;
            background: rgba(0,0,0,0.75);
            align-items: center;
            justify-content: center;
            padding: 1rem;
            z-index: 50;
        }}
        .modal.active {{ display: flex; }}
        .modal-content {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 12px;
            max-width: 600px;
            width: 100%;
            padding: 1.5rem;
            max-height: 90vh;
            overflow-y: auto;
        }}
        .form-group {{ margin-bottom: 1rem; }}
        .form-group label {{ display: block; font-size: 0.85rem; margin-bottom: 0.3rem; color: var(--muted); }}
        .form-group input, .form-group select {{
            width: 100%;
            padding: 0.55rem 0.75rem;
            background: #0f172a;
            border: 1px solid var(--border);
            border-radius: 6px;
            color: white;
        }}
        pre {{
            background: #0f172a;
            padding: 1rem;
            border-radius: 8px;
            overflow-x: auto;
            font-size: 0.82rem;
            border: 1px solid var(--border);
            margin-top: 1rem;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="brand">
                <h1>📡 Meu Servidor RSS</h1>
                <p>Atualizado automaticamente via GitHub Actions • Última atualização: {updated_at}</p>
            </div>
            <button class="btn-builder" onclick="toggleModal()">+ Gerar Novo Feed (JSON)</button>
        </header>

        <div class="grid">
            {cards_html}
        </div>
    </div>

    <!-- Gerador Visual de Configuração -->
    <div id="builderModal" class="modal">
        <div class="modal-content">
            <h2 style="margin-bottom: 0.5rem;">Adicionar Novo Site</h2>
            <p style="color: var(--muted); font-size: 0.88rem; margin-bottom: 1rem;">
                Preencha os campos abaixo e copie o bloco gerado para colar no seu arquivo <code>feeds.json</code> no GitHub.
            </p>
            <div class="form-group">
                <label>ID do Feed (sem espaços, ex: g1-tecnologia)</label>
                <input type="text" id="f_id" placeholder="meu-site" oninput="updateJson()">
            </div>
            <div class="form-group">
                <label>Nome / Título do Feed</label>
                <input type="text" id="f_title" placeholder="Notícias do Meu Site" oninput="updateJson()">
            </div>
            <div class="form-group">
                <label>URL da Página</label>
                <input type="url" id="f_url" placeholder="https://exemplo.com/noticias" oninput="updateJson()">
            </div>
            <div class="form-group">
                <label>O site precisa de JavaScript para carregar? (React/SPA)</label>
                <select id="f_js" onchange="updateJson()">
                    <option value="false">Não (HTML normal - Mais rápido)</option>
                    <option value="true">Sim (Usar navegador Playwright)</option>
                </select>
            </div>
            <div class="form-group">
                <label>Modo de Extração</label>
                <select id="f_auto" onchange="updateJson()">
                    <option value="true">Automático (Detectar artigos sozinho)</option>
                    <option value="false">Manual (Usar seletores CSS específicos)</option>
                </select>
            </div>
            <div id="cssFields" style="display:none;">
                <div class="form-group">
                    <label>Seletor CSS do Card/Artigo (item)</label>
                    <input type="text" id="f_item" placeholder="article.post-card" oninput="updateJson()">
                </div>
                <div class="form-group">
                    <label>Seletor CSS do Título (title)</label>
                    <input type="text" id="f_sel_title" placeholder="h2" oninput="updateJson()">
                </div>
                <div class="form-group">
                    <label>Seletor CSS do Link (link)</label>
                    <input type="text" id="f_sel_link" placeholder="a" oninput="updateJson()">
                </div>
            </div>
            <pre id="jsonOutput"></pre>
            <div style="display:flex; justify-content:flex-end; gap:0.5rem; margin-top:1rem;">
                <button class="btn-copy" onclick="copyJson()">Copiar JSON</button>
                <button class="btn-open" onclick="toggleModal()">Fechar</button>
            </div>
        </div>
    </div>

    <script>
        // Converte caminhos relativos para URL completa do GitHub Pages automaticamente
        window.addEventListener('DOMContentLoaded', () => {{
            const base = window.location.origin + window.location.pathname.replace(/index\\.html$/, '').replace(/\\/?$/, '/');
            document.querySelectorAll('.rss-input').forEach(inp => {{
                const rel = inp.getAttribute('data-rel');
                inp.value = base + rel;
            }});
            updateJson();
        }});

        function copyRss(btn) {{
            const input = btn.parentElement.querySelector('.rss-input');
            navigator.clipboard.writeText(input.value);
            const old = btn.textContent;
            btn.textContent = 'Copiado! ✓';
            setTimeout(() => btn.textContent = old, 2000);
        }}

        function toggleModal() {{
            document.getElementById('builderModal').classList.toggle('active');
        }}

        function updateJson() {{
            const isAuto = document.getElementById('f_auto').value === 'true';
            document.getElementById('cssFields').style.display = isAuto ? 'none' : 'block';
            const obj = {{
                id: document.getElementById('f_id').value || 'novo-site',
                title: document.getElementById('f_title').value || 'Título do Feed',
                url: document.getElementById('f_url').value || 'https://exemplo.com',
                description: '',
                render_js: document.getElementById('f_js').value === 'true',
                auto_detect: isAuto,
                max_items: 20
            }};
            if (!isAuto) {{
                obj.selectors = {{
                    item: document.getElementById('f_item').value || 'article',
                    title: document.getElementById('f_sel_title').value || 'h2',
                    link: document.getElementById('f_sel_link').value || 'a',
                    description: 'p',
                    image: 'img'
                }};
            }}
            document.getElementById('jsonOutput').textContent = JSON.stringify(obj, null, 2);
        }}

        function copyJson() {{
            navigator.clipboard.writeText(document.getElementById('jsonOutput').textContent);
            alert('Configuração copiada! Agora basta colar dentro da lista no arquivo feeds.json.');
        }}
    </script>
</body>
</html>"""

    with open(os.path.join(OUTPUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)


def main():
    os.makedirs(FEEDS_DIR, exist_ok=True)

    with open("feeds.json", "r", encoding="utf-8") as f:
        feeds_config = json.load(f)

    metadata_list = []
    now_str = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")

    for cfg in feeds_config:
        feed_id = cfg["id"]
        url = cfg["url"]
        render_js = cfg.get("render_js", False)
        auto_detect = cfg.get("auto_detect", True)
        max_items = cfg.get("max_items", 20)

        print(f"-> Processando [{feed_id}] ({url}) | JS={render_js} | Auto={auto_detect}")
        try:
            html = fetch_html(url, render_js=render_js, wait_for=cfg.get("wait_for", ""))
            soup = BeautifulSoup(html, "lxml")

            if auto_detect or not cfg.get("selectors"):
                items = extract_auto(soup, url, max_items=max_items)
            else:
                items = extract_with_selectors(soup, url, cfg["selectors"], max_items=max_items)

            xml_filename = f"{feed_id}.xml"
            xml_path = os.path.join(FEEDS_DIR, xml_filename)
            build_rss_xml(cfg, items, xml_path)

            print(f"   [OK] {len(items)} itens extraídos -> {xml_path}")
            metadata_list.append({
                "id": feed_id,
                "title": cfg.get("title", feed_id),
                "description": cfg.get("description", ""),
                "source_url": url,
                "render_js": render_js,
                "xml_rel_path": f"feeds/{xml_filename}",
                "status": "ok",
                "count": len(items),
                "preview": items[:5],
            })
        except Exception as e:
            print(f"   [ERRO] Falha ao processar {feed_id}: {e}")
            metadata_list.append({
                "id": feed_id,
                "title": cfg.get("title", feed_id),
                "description": cfg.get("description", ""),
                "source_url": url,
                "render_js": render_js,
                "xml_rel_path": f"feeds/{feed_id}.xml",
                "status": "error",
                "error": str(e),
                "count": 0,
                "preview": [],
            })

    build_dashboard_html(metadata_list, now_str)
    print(f"\nPainel gerado com sucesso em: {os.path.join(OUTPUT_DIR, 'index.html')}")


if __name__ == "__main__":
    main()
