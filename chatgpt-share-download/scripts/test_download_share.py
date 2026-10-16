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
