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
