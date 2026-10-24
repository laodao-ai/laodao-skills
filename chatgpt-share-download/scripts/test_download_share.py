import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).with_name('download_share.py')
spec = importlib.util.spec_from_file_location('download_share', SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def page(nodes):
    # 模拟 React Router 的引用表；不是普通内嵌 JSON 对象。
    table = []
    def pack(value):
        index = len(table)
        table.append(None)
        if isinstance(value, dict):
            table[index] = {'_' + str(pack(k)): pack(v) for k, v in value.items()}
        elif isinstance(value, list):
            table[index] = [pack(x) for x in value]
        else:
            table[index] = value
        return index
    pack({'title': '示例', 'linear_conversation': nodes})
    return 'streamController.enqueue(' + json.dumps(json.dumps(table)) + ')'


def message(role, text, **kwargs):
    return {'message': {'id': text[:8], 'author': {'role': role},
                        'content': {'content_type': 'text', 'parts': [text]}, **kwargs}}


class DownloadTests(unittest.TestCase):
    def test_visible_messages_keep_duplicates_and_preambles(self):
        nodes = [message('user', '问'), message('assistant', '进度', channel='commentary'),
                 message('assistant', '相同回答'), message('assistant', '相同回答'),
                 message('assistant', '隐藏', metadata={'is_visually_hidden_from_conversation': True}),
                 message('assistant', '调用', recipient='web.run'), message('tool', '返回')]
        data = mod.extract(page(nodes))
        self.assertEqual([x['content']['parts'][0] for x in mod.visible_messages(data)],
                         ['问', '进度', '相同回答', '相同回答'])

    def test_failure_is_not_an_empty_success(self):
        with self.assertRaises(ValueError):
            mod.extract('<html>Sign in / challenge</html>')

    def test_invalid_urls(self):
        for url in ['https://example.com/share/abc', 'http://chatgpt.com/share/abc',
                    'https://chatgpt.com@evil.example/share/abc']:
            with self.assertRaises(ValueError):
                mod.validate_url(url)

    def test_component_code_block_keeps_mermaid_branch_labels(self):
        original = '<box><text>状态机</text><CodeBlock language="mermaid">flowchart TD\n A --> B{输入有效?}</CodeBlock></box>'
        with tempfile.TemporaryDirectory() as tmp:
            mod.archive(page([message('assistant', original)]), 'https://chatgpt.com/share/abc',
                        Path(tmp) / 'archive', download_images=False)
            text = (Path(tmp) / 'archive/conversation.md').read_text()
            self.assertIn('```mermaid\nflowchart TD\n A --> B{输入有效?}\n```', text)

    def test_citations_resolve_from_message_metadata(self):
        node = message('assistant', '来源 citeturn1search0')
        node['message']['id'] = 'citation-message'
        node['message']['metadata'] = {'content_references': [
            {'matched_text': 'citeturn1search0', 'items': [
                {'title': '官方资料', 'url': 'https://example.com/docs'}]}]}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'archive'
            result = mod.archive(page([node]), 'https://chatgpt.com/share/abc', out, False)
            text = (out / 'conversation.md').read_text()
            self.assertIn('[官方资料](https://example.com/docs)', text)
            self.assertNotIn('cite', text)
            self.assertEqual(result['unresolved'], 0)

    def archive_one(self, node):
        node['message']['id'] = 'test-message'  # 默认 id 取正文前 8 字，会带入原始字符
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'archive'
            result = mod.archive(page([node]), 'https://chatgpt.com/share/abc', out, False)
            return (out / 'conversation.md').read_text(), result

    def test_url_entities_resolve_from_alt(self):
        direct = '\ue200url\ue202标题甲\ue202https://example.com/a\ue201'
        by_turn = '\ue200url\ue202标题乙\ue202turn738729reddit10\ue201'
        unknown = '\ue200url\ue202没有元数据\ue202turn1view1\ue201'
        node = message('assistant', f'甲 {direct} 乙 {by_turn} 丙 {unknown}')
        node['message']['metadata'] = {'content_references': [
            {'type': 'url', 'matched_text': direct, 'alt': '[标题甲](https://example.com/a)'},
            {'type': 'url', 'matched_text': by_turn, 'alt': '[标题乙](https://example.com/b)'}]}
        text, result = self.archive_one(node)
        self.assertIn('[标题甲](https://example.com/a)', text)
        self.assertIn('[标题乙](https://example.com/b)', text)
        self.assertIn('[引用未恢复，见 source.json]', text)
        for char in '\ue200\ue201\ue202':
            self.assertNotIn(char, text)
        self.assertEqual(result['unresolved'], 1)

    def test_url_entity_ignores_non_https_alt(self):
        entity = '\ue200url\ue202坏链接\ue202turn1view1\ue201'
        node = message('assistant', f'见 {entity}')
        node['message']['metadata'] = {'content_references': [
            {'type': 'url', 'matched_text': entity, 'alt': '[坏链接](javascript:alert(1))'}]}
        text, result = self.archive_one(node)
        self.assertNotIn('javascript', text)
        self.assertEqual(result['unresolved'], 1)

    def test_cite_with_null_entities_resolves_by_position(self):
        entity = '\ue200cite\ue202turn1search0\ue201'
        tag = '<Cite ref="turn106433reddit55"/>'
        text = f'前文 {entity} 中间 {tag} 结尾'
        start = text.index(tag)
        node = message('assistant', text)
        node['message']['metadata'] = {
            'content_references': [{'matched_text': entity, 'items': [
                {'title': '官方', 'url': 'https://example.com/docs'}]}],
            'genui_components': [{'type': 'cite', 'start_index': start, 'end_index': start + len(tag),
                                  'safe_urls': [{'url': 'https://www.reddit.com/r/x/comments/1/'}],
                                  'entities': None}]}
        out, result = self.archive_one(node)
        self.assertIn('[官方](https://example.com/docs)', out)
        self.assertIn('[www.reddit.com](https://www.reddit.com/r/x/comments/1/)', out)
        self.assertNotIn('<Cite', out)
        self.assertEqual(result['unresolved'], 0)

    def test_link_writing_block_and_memory_cite_tags(self):
        body = ('看 **<Link url="https://example.com/a" title="含[括号]标题"/>** 和 '
                '<Link url="http://example.com/insecure" title="不安全"/>\n'
                '<MemoryCite />\n'
                '<WritingBlock id="58321" variant="chat_message">\n# 标题\n正文\n</WritingBlock>')
        text, result = self.archive_one(message('assistant', body))
        self.assertIn('**[含\\[括号\\]标题](https://example.com/a)**', text)
        self.assertNotIn('http://example.com/insecure', text)
        self.assertIn('［此处原为 ChatGPT 记忆引用，分享页不显示内容］', text)
        self.assertIn('\n\n> 写作块开始（ChatGPT 写作组件 chat_message，id 58321）\n\n', text)
        self.assertIn('\n\n# 标题\n正文\n\n', text)
        self.assertIn('\n\n> 写作块结束\n\n', text)
        for tag in ('<Link', '<WritingBlock', '</WritingBlock', '<MemoryCite'):
            self.assertNotIn(tag, text)
        self.assertEqual(result['unresolved'], 1)

    def test_export_preserves_source_and_marks_dynamic_visual(self):
        body = '正文\n<box><svg viewBox="0 0 10 10"><text x="1">静态</text></svg></box>\n<box>{#each items as x}<text>{x}</text>{/each}</box>'
        html = page([message('user', '问题'), message('assistant', body)])
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'archive'
            result = mod.archive(html, 'https://chatgpt.com/share/abc', out, download_images=False)
            text = (out / 'conversation.md').read_text()
            source = json.loads((out / 'source.json').read_text())
            self.assertEqual(mod.visible_messages(source['conversation'])[1]['content']['parts'][0], body)
            self.assertEqual((out / 'source.html').read_text(), html)
            self.assertIn('assets/visual-001.svg', text)
            self.assertIn('未渲染', text)
            self.assertEqual(result['messages'], 2)
            with self.assertRaises(FileExistsError):
                mod.archive(html, 'https://chatgpt.com/share/abc', out, download_images=False)


if __name__ == '__main__':
    unittest.main()
