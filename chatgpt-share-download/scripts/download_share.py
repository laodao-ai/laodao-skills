"""下载 ChatGPT 分享页；解析当前 React Router 引用表，保留原始证据。"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET


ENQUEUE = re.compile(r'streamController\.enqueue\(("(?:[^"\\]|\\.)*")\)')
CONTAINERS = re.compile(r'<(/?)(box|row|grid|list)\b[^>]*>')


def validate_url(url):
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or parsed.hostname not in ('chatgpt.com', 'chat.openai.com')
            or parsed.username or parsed.password or parsed.port
            or not re.fullmatch(r'/share/[A-Za-z0-9-]+/?', parsed.path)):
        raise ValueError('需要 https://chatgpt.com/share/<id> 格式的分享链接')
    return f'https://{parsed.hostname}{parsed.path.rstrip("/")}'


def fetch(url):
    result = subprocess.run(['curl', '--fail', '--location', '--silent', '--show-error',
                             '--max-time', '60', '--max-filesize', '52428800',
                             '--proto', '=https', '--proto-redir', '=https', url],
                            capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.decode('utf-8', errors='replace').strip())
    return result.stdout


def extract(html):
    # 只解码包含 linear_conversation 的数据表，避免遍历页面配置中的循环引用。
    for match in ENQUEUE.finditer(html):
        try:
            table = json.loads(json.loads(match[1]))
        except (ValueError, TypeError):
            continue
        if not isinstance(table, list) or 'linear_conversation' not in table:
            continue
        key = '_' + str(table.index('linear_conversation'))
        candidates = [item for item in table if isinstance(item, dict) and key in item]
        if not candidates:
            continue

        def decode(index, ancestors=()):
            if not isinstance(index, int) or isinstance(index, bool):
                return index
            if index < 0:
                return None
            if index >= len(table):
                raise ValueError('引用表索引越界')
            if index in ancestors:
                return {'_archive_cycle_reference': index}
            item = table[index]
            ancestors += (index,)
            if isinstance(item, dict):
                return {str(table[int(k[1:])]): decode(v, ancestors) for k, v in item.items()}
            if isinstance(item, list):
                return [decode(v, ancestors) for v in item]
            return item

        # 当前协议以带 linear_conversation 字段的对象承载标题等元数据。
        candidate = candidates[0]
        data = {str(table[int(k[1:])]): decode(v) for k, v in candidate.items()}
        if isinstance(data.get('linear_conversation'), list):
            return data
    raise ValueError('未找到可解析的分享消息。页面可能需要登录、已失效或协议发生变化。')


def visible_messages(data):
    result = []
    for node in data['linear_conversation']:
        message = node.get('message') or {}
        if message.get('author', {}).get('role') not in ('user', 'assistant'):
            continue
        if message.get('recipient', 'all') != 'all':
            continue
        if message.get('metadata', {}).get('is_visually_hidden_from_conversation'):
            continue
        content = message.get('content', {})
        if content.get('content_type') == 'text' and any(content.get('parts', [])):
            result.append(message)
        elif content.get('content_type') not in ('thoughts', 'reasoning_recap', 'model_editable_context', 'text'):
            result.append(message)
    return result


def fence(text, language='text'):
    runs = [len(x) for x in re.findall(r'`+', text)]
    marker = '`' * max(3, max(runs, default=0) + 1)
    return f'{marker}{language}\n{text}\n{marker}'


def image_extension(blob):
    if blob.startswith(b'\x89PNG\r\n\x1a\n'):
        return '.png'
    if blob.startswith(b'\xff\xd8\xff'):
        return '.jpg'
    if blob.startswith((b'GIF87a', b'GIF89a')):
        return '.gif'
    if blob.startswith(b'RIFF') and blob[8:12] == b'WEBP':
        return '.webp'
    raise ValueError('图片响应不是支持的 PNG/JPEG/GIF/WebP 文件')


def convert_visuals(body, message, assets, manifest, download_images):
    body = re.sub(r'<CodeBlock\s+language="([A-Za-z0-9_-]+)"\s*>([\s\S]*?)</CodeBlock>',
                  lambda match: fence(match[2], match[1]), body)
    components = message.get('metadata', {}).get('genui_components', [])
    images = iter(x for x in components if x.get('type') == 'async_image')

    def image(match):
        component = next(images, {})
        urls = [x['url'] for x in component.get('safe_urls', []) if isinstance(x, dict) and x.get('url')]
        urls = [u for u in urls if urlsplit(u).scheme == 'https'
                and urlsplit(u).hostname == 'images.openai.com']
        urls.sort(key=lambda u: 'purpose=fullsize' not in u)
        entry = {'kind': 'image', 'message_id': message.get('id'), 'source': match[0], 'urls': urls}
        manifest.append(entry)
        if download_images:
            for url in urls:
                try:
                    blob = fetch(url)
                    name = 'image-' + hashlib.sha256(blob).hexdigest()[:16] + image_extension(blob)
                    (assets / name).write_bytes(blob)
                    entry.update(status='downloaded', path='assets/' + name, selected_url=url)
                    return f'\n![分享页原图]({entry["path"]})\n'
                except (RuntimeError, ValueError, OSError) as error:
                    entry['error'] = str(error)
        entry['status'] = 'unavailable'
        return '\n> 图片未下载：原始引用见 source.json 和 manifest.json。\n'

    body = re.sub(r'<AsyncImage\b[^>]*?/>', image, body)
    # 外层组件整体处理，避免把不能执行的模板误当成有效 SVG。
    blocks, depth, start = [], 0, 0
    for match in CONTAINERS.finditer(body):
        if match[0].endswith('/>'):
            continue
        if not match[1]:
            if depth == 0:
                start = match.start()
            depth += 1
        elif depth:
            depth -= 1
            if depth == 0:
                blocks.append((start, match.end(), body[start:match.end()]))
    for start, end, block in reversed(blocks):
        svg_match = re.search(r'<svg\b[\s\S]*?</svg>', block)
        replacement = None
        if svg_match and '{' not in svg_match[0]:
            svg = svg_match[0]
            for old, new in [('fontSize', 'font-size'), ('fontWeight', 'font-weight'),
                             ('textAnchor', 'text-anchor'), ('strokeWidth', 'stroke-width'),
                             ('fillOpacity', 'fill-opacity'), ('strokeOpacity', 'stroke-opacity')]:
                svg = svg.replace(old + '=', new + '=')
            if 'xmlns=' not in svg:
                svg = svg.replace('<svg ', '<svg xmlns="http://www.w3.org/2000/svg" ', 1)
            try:
                root = ET.fromstring(svg)
                # 不把脚本、外部资源或事件处理器带入独立 SVG。
                safe_tags = {'svg', 'g', 'rect', 'text', 'tspan', 'path', 'line', 'polyline',
                             'polygon', 'circle', 'ellipse', 'defs', 'marker', 'title', 'desc'}
                safe = all(element.tag.split('}')[-1] in safe_tags and
                           all(not key.lower().startswith('on') and key.split('}')[-1] not in ('href', 'style')
                               for key in element.attrib) for element in root.iter())
                if safe:
                    number = sum(x['kind'] == 'svg' for x in manifest) + 1
                    name = f'visual-{number:03d}.svg'
                    (assets / name).write_text(svg, encoding='utf-8')
                    manifest.append({'kind': 'svg', 'status': 'converted', 'path': 'assets/' + name,
                                     'message_id': message.get('id')})
                    replacement = (f'![原对话静态图示](assets/{name})\n\n'
                                   '<details>\n<summary>原始组件及图注</summary>\n\n'
                                   + fence(block) + '\n\n</details>')
            except ET.ParseError:
                pass
        if replacement is None:
            # Mermaid 是可移植源格式，直接保留代码块；其余组件由 agent 核对后恢复。
            mermaid = re.search(r'```mermaid\n[\s\S]*?\n```', block)
            if mermaid:
                replacement = mermaid[0] + '\n\n<details>\n<summary>原始组件</summary>\n\n' + fence(block) + '\n\n</details>'
            elif '![分享页原图]' in block:
                replacement = re.sub(r'</?(?:box|row|text)\b[^>]*>', '', block)
            else:
                manifest.append({'kind': 'component', 'status': 'unrendered',
                                 'message_id': message.get('id'), 'source': block})
                replacement = '> 图示未渲染：ChatGPT 专用组件源码如下。\n\n' + fence(block)
        body = body[:start] + replacement + body[end:]
    return body


def convert_references(body, message, manifest):
    def links(items):
        result = []
        for item in items:
            url = item.get('url') if isinstance(item, dict) else item
            if not isinstance(url, str) or urlsplit(url).scheme != 'https':
                continue
            title = item.get('title') or urlsplit(url).hostname if isinstance(item, dict) else urlsplit(url).hostname
            title = str(title).replace('[', '\\[').replace(']', '\\]')
            result.append(f'[{title}]({url.replace(")", "%29")})')
        return ', '.join(dict.fromkeys(result))

    components = message.get('metadata', {}).get('genui_components', [])

    def cite(match):
        # entities 可能是 null；此时只能靠 start_index 与原文位置对应。
        for component in components:
            if (component.get('type') == 'cite' and component.get('start_index') == match.start()
                    and original[match.start():component.get('end_index')] == match[0]):
                replacement = links(component.get('safe_urls', []))
                if replacement:
                    return replacement
        refs = set(re.findall(r'"([^"]+)"', match[0]))
        for component in components:
            entity_refs = {x.get('ref') for x in component.get('entities') or []}
            if component.get('type') == 'cite' and refs and refs == entity_refs:
                replacement = links(component.get('safe_urls', []))
                if replacement:
                    return replacement
        manifest.append({'kind': 'reference', 'status': 'unavailable',
                         'message_id': message.get('id'), 'source': match[0]})
        return '[引用未恢复，见 source.json]'

    # 位置按未改动的原文计算，所以 <Cite> 必须先于下面会改变长度的替换。
    original = body
    body = re.sub(r'<Cite\b[^>]*?/>', cite, body)

    for reference in message.get('metadata', {}).get('content_references', []):
        marker = reference.get('matched_text')
        if not isinstance(marker, str):
            continue
        # \u65b0\u7248\u5206\u4eab\u9875\u628a\u5f15\u7528\u5199\u6210 genui \u5b9e\u4f53\uff08\u6b63\u6587 {"citation":{"ref":...}}\uff09\uff0c\u6761\u76ee\u7ed3\u6784\u4e0e cite \u76f8\u540c\u3002
        if (marker.startswith('\ue200cite')
                or (marker.startswith('\ue200genui') and '"citation"' in marker)):
            replacement = links(reference.get('items', []) or reference.get('safe_urls', []))
        elif reference.get('type') == 'url' and marker.startswith('\ue200url'):
            # alt 已是完成的 [标题](链接)；只接受 https 目标。
            alt = reference.get('alt')
            ok = isinstance(alt, str) and re.fullmatch(r'\[[\s\S]*\]\(https://\S+\)', alt)
            replacement = alt if ok else ''
        else:
            continue
        if replacement:
            body = body.replace(marker, replacement)

    # 没被元数据覆盖的实体统一记为未恢复，不留原始私有字符。
    for marker in dict.fromkeys(re.findall(r'\ue200[^\ue201]*\ue201', body)):
        manifest.append({'kind': 'reference', 'status': 'unavailable',
                         'message_id': message.get('id'), 'source': marker})
        body = body.replace(marker, '[引用未恢复，见 source.json]')

    def link_tag(match):
        attrs = dict(re.findall(r'(\w+)="([^"]*)"', match[0]))
        replacement = links([{'url': attrs.get('url'), 'title': attrs.get('title')}])
        if replacement:
            return replacement
        manifest.append({'kind': 'reference', 'status': 'unavailable',
                         'message_id': message.get('id'), 'source': match[0]})
        return attrs.get('title') or '[链接未恢复，见 source.json]'

    body = re.sub(r'<Link\b[^>]*?/>', link_tag, body)
    body = re.sub(r'<MemoryCite\s*/>', '［此处原为 ChatGPT 记忆引用，分享页不显示内容］', body)

    def writing_open(match):
        attrs = dict(re.findall(r'(\w+)="([^"]*)"', match[0]))
        return (f'\n\n> 写作块开始（ChatGPT 写作组件 {attrs.get("variant", "未知")}，'
                f'id {attrs.get("id", "未知")}）\n\n')

    body = re.sub(r'<WritingBlock\b[^>]*>', writing_open, body)
    body = re.sub(r'</WritingBlock>', '\n\n> 写作块结束\n\n', body)
    return body


def archive(html, url, output, download_images=True):
    data = extract(html)
    messages = visible_messages(data)
    if not messages:
        raise ValueError('分享页没有可归档的用户或助手消息')
    output.mkdir(parents=True, exist_ok=False)
    assets = output / 'assets'
    assets.mkdir()
    (output / 'source.html').write_text(html, encoding='utf-8')
    (output / 'source.json').write_text(json.dumps({'url': url, 'conversation': data}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    manifest = []
    chunks = [f'# {data.get("title") or "ChatGPT 分享对话"}\n\n- 来源：{url}\n- 保存时间：{datetime.now(timezone.utc).isoformat()}\n- 消息数：{len(messages)}\n\n'
              '## 覆盖范围\n\n按分享页顺序保留可访问的 User / Assistant 消息及助手进度。仅排除页面明确标记隐藏的片段、系统消息、工具调用和思考提示，不按文本去重。'
              '原始页面见 source.html，正文及引用元数据见 source.json，图片恢复状态见 manifest.json。'
              '图片和图示使用本地文件；无法恢复的组件明确标注。仅覆盖本分享页，未确认原会话其他分支或附件是否完整。\n\n']
    for number, message in enumerate(messages, 1):
        content = message['content']
        if content.get('content_type') == 'text':
            body = '\n\n'.join(part if isinstance(part, str) else json.dumps(part, ensure_ascii=False)
                               for part in content['parts'])
        else:
            body = '> 非文本消息，原始数据如下；媒体未恢复。\n\n' + fence(json.dumps(content, ensure_ascii=False, indent=2), 'json')
            manifest.append({'kind': 'media', 'status': 'unavailable', 'message_id': message.get('id')})
        body = convert_references(body, message, manifest)
        body = convert_visuals(body, message, assets, manifest, download_images)
        timestamp = message.get('create_time')
        when = datetime.fromtimestamp(timestamp, timezone.utc).isoformat() if isinstance(timestamp, (int, float)) else '未知'
        chunks.append(f'## M{number:03d} · {message["author"]["role"].title()}\n\n- 消息 ID：`{message.get("id", "未知")}`\n- 时间：{when}\n\n{body}\n\n')
        urls = []
        for component in message.get('metadata', {}).get('genui_components', []):
            urls.extend(x.get('url') for x in component.get('safe_urls', []) if isinstance(x, dict))
        for reference in message.get('metadata', {}).get('content_references', []):
            urls.extend(x.get('url') for x in reference.get('items', []) if isinstance(x, dict))
        urls = list(dict.fromkeys(u for u in urls if isinstance(u, str) and urlsplit(u).scheme == 'https'
                                  and urlsplit(u).hostname != 'images.openai.com'))
        if urls:
            chunks.append('引用链接（分享页元数据）：\n\n' + ''.join(f'- <{u}>\n' for u in urls) + '\n')
    (output / 'conversation.md').write_text(''.join(chunks), encoding='utf-8')
    result = {'messages': len(messages), 'visuals': manifest,
              'unresolved': sum(x['status'] in ('unavailable', 'unrendered') for x in manifest)}
    (output / 'manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    for entry in manifest:
        if 'path' in entry and not (output / entry['path']).is_file():
            raise ValueError('生成的图片引用缺少文件')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('url')
    parser.add_argument('--output', type=Path, required=True, help='新建归档目录；已有目录拒绝覆盖')
    parser.add_argument('--html', type=Path, help='使用已下载 HTML，便于离线重放')
    parser.add_argument('--skip-images', action='store_true', help='离线模式；未下载图片计入 unresolved')
    args = parser.parse_args()
    try:
        url = validate_url(args.url)
        html = args.html.read_text(encoding='utf-8') if args.html else fetch(url).decode('utf-8')
        result = archive(html, url, args.output, not args.skip_images)
        print(json.dumps({'output': str(args.output), 'messages': result['messages'],
                          'unresolved': result['unresolved']}, ensure_ascii=False))
        return 2 if result['unresolved'] else 0
    except (ValueError, RuntimeError, OSError) as error:
        print(f'归档失败：{error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
