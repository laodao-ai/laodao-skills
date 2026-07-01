/*
 * OpenSpec Review Engine — shared logic for every review.html shell in a project.
 * Zero build: loaded via a plain <script> tag. The `module.exports` guard below only
 * activates under Node (used by tests); browsers never define `module`, so it's inert there.
 */

function parseDirectoryListing(html) {
  const entries = [];
  const re = /<li><a href="([^"]+)">/g;
  let m;
  while ((m = re.exec(html)) !== null) {
    const rawHref = m[1];
    const isDir = rawHref.endsWith('/');
    const name = decodeURIComponent(isDir ? rawHref.slice(0, -1) : rawHref);
    entries.push({ name, href: rawHref, isDir });
  }
  return entries;
}

function linkifyBacktickPaths(html) {
  return html.replace(
    /<code>(openspec\/[A-Za-z0-9_\-./]+\.md)<\/code>/g,
    (_match, path) => `<a href="/${path}" class="auto-link">${path}</a>`
  );
}

function resolveLink(href, baseUrl) {
  return new URL(href, baseUrl).toString();
}

function isMarkdownPath(path) {
  return /\.md$/i.test(path);
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { parseDirectoryListing, linkifyBacktickPaths, resolveLink, isMarkdownPath };
}

// ---- DOM glue (browser-only; the `typeof document` guard keeps this inert under Node) ----

if (typeof document !== 'undefined') {
  (function () {
    const SCOPE = window.__OPENSPEC_REVIEW_SCOPE__ || '';
    const initialDir = SCOPE ? `/${SCOPE}` : '/';

    const app = document.getElementById('app');
    const sidebar = document.createElement('div');
    sidebar.id = 'sidebar';
    const content = document.createElement('div');
    content.id = 'content';
    app.appendChild(sidebar);
    app.appendChild(content);

    function escapeHtml(s) {
      return s.replace(/[&<>"']/g, (c) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
      }[c]));
    }

    async function fetchText(path) {
      const res = await fetch(path);
      if (!res.ok) throw new Error(`fetch failed: ${path} (${res.status})`);
      return res.text();
    }

    async function loadSidebar(dirPath) {
      const html = await fetchText(dirPath);
      const entries = parseDirectoryListing(html)
        .filter((e) => e.isDir || isMarkdownPath(e.name))
        .sort((a, b) => (a.isDir === b.isDir ? a.name.localeCompare(b.name) : a.isDir ? -1 : 1));
      sidebar.innerHTML = '';
      if (SCOPE !== '') {
        const back = document.createElement('a');
        back.href = '/review.html';
        back.className = 'back-link';
        back.textContent = '← 全部文档'; // ← 全部文档
        sidebar.appendChild(back);
      }
      const list = document.createElement('ul');
      entries.forEach((e) => {
        const li = document.createElement('li');
        const a = document.createElement('a');
        a.href = resolveLink(e.href, new URL(dirPath, window.location.href).toString());
        a.textContent = e.isDir ? `${e.name}/` : e.name;
        li.appendChild(a);
        list.appendChild(li);
      });
      sidebar.appendChild(list);
    }

    async function loadDir(path) {
      await loadSidebar(path);
      content.innerHTML = `<p class="hint">目录：${escapeHtml(path)}<br>请选择左侧的文档。</p>`;
      document.title = path;
    }

    async function loadDoc(path) {
      const md = await fetchText(path);
      const rendered = window.marked ? window.marked.parse(md) : `<pre>${escapeHtml(md)}</pre>`;
      content.innerHTML = linkifyBacktickPaths(rendered);
      document.title = path;
      const dir = path.replace(/[^/]*$/, '');
      await loadSidebar(dir);
    }

    async function navigate(path, push) {
      try {
        if (path.endsWith('/')) {
          await loadDir(path);
        } else {
          await loadDoc(path);
        }
        if (push) history.pushState({ path }, '', `#${path}`);
      } catch (err) {
        content.innerHTML = `<p class="error">加载失败：${escapeHtml(path)}</p>`;
      }
    }

    function onLinkClick(ev) {
      const a = ev.target.closest('a');
      if (!a) return;
      const href = a.getAttribute('href');
      if (!href) return;
      const resolved = resolveLink(href, window.location.href);
      const url = new URL(resolved);
      // resolveLink always returns an absolute URL (even for same-origin sidebar
      // links), so a naive `startsWith('http://')` check can't distinguish "real"
      // external links from internal ones — compare origins instead.
      if (url.origin !== window.location.origin) return;
      ev.preventDefault();
      navigate(url.pathname, true);
    }

    document.body.addEventListener('click', onLinkClick);
    window.addEventListener('popstate', (ev) => {
      const path = (ev.state && ev.state.path) || initialDir;
      navigate(path, false);
    });

    navigate(initialDir, false);
  })();
}
