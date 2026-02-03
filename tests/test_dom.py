"""
Tests for the DOM tree parser module.
"""

import unittest
from doc_search.dom import (
    Node, Element, Text, DOMTreeBuilder, parse_html,
    extract_text_dom, strip_boilerplate, extract_main_content,
    _is_boilerplate
)


class TestNode(unittest.TestCase):
    """Tests for the Node base class."""
    
    def test_node_parent_default_none(self):
        """Node parent should be None by default."""
        node = Node()
        self.assertIsNone(node.parent)
    
    def test_node_remove(self):
        """Node.remove() should detach from parent."""
        parent = Element('div')
        child = Element('p')
        parent.append(child)
        
        self.assertEqual(child.parent, parent)
        self.assertIn(child, parent.children)
        
        child.remove()
        
        self.assertIsNone(child.parent)
        self.assertNotIn(child, parent.children)


class TestText(unittest.TestCase):
    """Tests for the Text node class."""
    
    def test_text_content(self):
        """Text should store content."""
        text = Text('Hello, world!')
        self.assertEqual(text.content, 'Hello, world!')
    
    def test_text_repr(self):
        """Text repr should show content preview."""
        text = Text('Short')
        self.assertIn('Short', repr(text))
        
        long_text = Text('A' * 50)
        self.assertIn('...', repr(long_text))


class TestElement(unittest.TestCase):
    """Tests for the Element class."""
    
    def test_element_tag_lowercase(self):
        """Element tag should be lowercased."""
        elem = Element('DIV')
        self.assertEqual(elem.tag, 'div')
    
    def test_element_attrs(self):
        """Element should store attributes."""
        elem = Element('a', {'href': '/page', 'class': 'link'})
        self.assertEqual(elem.attrs['href'], '/page')
        self.assertEqual(elem.attrs['class'], 'link')
    
    def test_element_append(self):
        """Element.append() should add child and set parent."""
        parent = Element('div')
        child = Element('p')
        
        parent.append(child)
        
        self.assertIn(child, parent.children)
        self.assertEqual(child.parent, parent)
    
    def test_element_find(self):
        """Element.find() should return first matching descendant."""
        root = Element('div')
        p1 = Element('p')
        p2 = Element('p')
        root.append(p1)
        root.append(p2)
        
        found = root.find('p')
        self.assertEqual(found, p1)
    
    def test_element_find_nested(self):
        """Element.find() should search nested elements."""
        root = Element('div')
        inner = Element('section')
        p = Element('p')
        root.append(inner)
        inner.append(p)
        
        found = root.find('p')
        self.assertEqual(found, p)
    
    def test_element_find_not_found(self):
        """Element.find() should return None if not found."""
        root = Element('div')
        self.assertIsNone(root.find('span'))
    
    def test_element_find_all(self):
        """Element.find_all() should return all matching descendants."""
        root = Element('div')
        p1 = Element('p')
        p2 = Element('p')
        span = Element('span')
        root.append(p1)
        root.append(span)
        span.append(p2)
        
        found = root.find_all('p')
        self.assertEqual(len(found), 2)
        self.assertIn(p1, found)
        self.assertIn(p2, found)
    
    def test_element_get_text(self):
        """Element.get_text() should return all text content."""
        root = Element('div')
        root.append(Text('Hello '))
        p = Element('p')
        p.append(Text('world'))
        root.append(p)
        
        text = root.get_text()
        self.assertIn('Hello', text)
        self.assertIn('world', text)
    
    def test_element_get_attr(self):
        """Element.get_attr() should return attribute value."""
        elem = Element('a', {'href': '/page'})
        self.assertEqual(elem.get_attr('href'), '/page')
        self.assertIsNone(elem.get_attr('class'))
        self.assertEqual(elem.get_attr('class', 'default'), 'default')
    
    def test_element_descendants(self):
        """Element.descendants() should iterate all descendants."""
        root = Element('div')
        p = Element('p')
        span = Element('span')
        root.append(p)
        p.append(span)
        
        descendants = list(root.descendants())
        self.assertEqual(len(descendants), 2)
        self.assertIn(p, descendants)
        self.assertIn(span, descendants)


class TestDOMTreeBuilder(unittest.TestCase):
    """Tests for the DOMTreeBuilder class."""
    
    def test_basic_parsing(self):
        """Should parse basic HTML structure."""
        builder = DOMTreeBuilder()
        builder.feed('<html><body><p>Hello</p></body></html>')
        
        root = builder.root
        body = root.find('body')
        p = root.find('p')
        
        self.assertIsNotNone(body)
        self.assertIsNotNone(p)
        self.assertEqual(p.get_text(), 'Hello')
    
    def test_void_elements(self):
        """Should handle void elements (br, img, etc.)."""
        builder = DOMTreeBuilder()
        builder.feed('<p>Line 1<br>Line 2</p>')
        
        p = builder.root.find('p')
        self.assertIsNotNone(p)
        # br should not consume following text
        self.assertIn('Line 2', p.get_text())
    
    def test_attributes(self):
        """Should preserve element attributes."""
        builder = DOMTreeBuilder()
        builder.feed('<a href="/page" class="link">Click</a>')
        
        a = builder.root.find('a')
        self.assertEqual(a.get_attr('href'), '/page')
        self.assertEqual(a.get_attr('class'), 'link')
    
    def test_malformed_html(self):
        """Should handle malformed HTML gracefully."""
        builder = DOMTreeBuilder()
        # Missing closing tags
        builder.feed('<div><p>Text</div>')
        
        # Should not raise, should still find elements
        div = builder.root.find('div')
        self.assertIsNotNone(div)
    
    def test_self_closing_tags(self):
        """Should handle self-closing tags like <br/>."""
        builder = DOMTreeBuilder()
        builder.feed('<p>Before<br/>After</p>')
        
        p = builder.root.find('p')
        text = p.get_text()
        self.assertIn('Before', text)
        self.assertIn('After', text)
    
    def test_entities(self):
        """Should handle HTML entities."""
        builder = DOMTreeBuilder()
        builder.feed('<p>&amp; &lt; &gt;</p>')
        
        p = builder.root.find('p')
        text = p.get_text()
        self.assertIn('&', text)
        self.assertIn('<', text)
        self.assertIn('>', text)


class TestParseHtml(unittest.TestCase):
    """Tests for the parse_html function."""
    
    def test_parse_html(self):
        """parse_html should return root Element."""
        root = parse_html('<html><body>Test</body></html>')
        self.assertIsInstance(root, Element)
        self.assertIsNotNone(root.find('body'))


class TestStripBoilerplate(unittest.TestCase):
    """Tests for boilerplate stripping."""
    
    def test_strip_nav(self):
        """Should strip <nav> elements."""
        root = parse_html('<body><nav>Menu</nav><main>Content</main></body>')
        body = root.find('body')
        strip_boilerplate(body)
        
        self.assertIsNone(body.find('nav'))
        self.assertIsNotNone(body.find('main'))
    
    def test_strip_script_style(self):
        """Should strip <script> and <style> elements."""
        root = parse_html('<body><script>code</script><style>css</style><p>Text</p></body>')
        body = root.find('body')
        strip_boilerplate(body)
        
        self.assertIsNone(body.find('script'))
        self.assertIsNone(body.find('style'))
        self.assertIsNotNone(body.find('p'))
    
    def test_strip_by_role(self):
        """Should strip elements with navigation role."""
        root = parse_html('<body><div role="navigation">Nav</div><p>Content</p></body>')
        body = root.find('body')
        strip_boilerplate(body)
        
        text = body.get_text()
        self.assertNotIn('Nav', text)
        self.assertIn('Content', text)
    
    def test_strip_by_class(self):
        """Should strip elements with boilerplate class names."""
        root = parse_html('<body><div class="sidebar">Side</div><p>Main</p></body>')
        body = root.find('body')
        strip_boilerplate(body)
        
        text = body.get_text()
        self.assertNotIn('Side', text)
        self.assertIn('Main', text)


class TestExtractMainContent(unittest.TestCase):
    """Tests for main content extraction."""
    
    def test_find_main_tag(self):
        """Should prefer <main> tag."""
        root = parse_html('<body><header>H</header><main>Content</main><footer>F</footer></body>')
        body = root.find('body')
        
        main = extract_main_content(body)
        self.assertEqual(main.tag, 'main')
    
    def test_find_article_tag(self):
        """Should use <article> if no <main>."""
        root = parse_html('<body><article>Content</article><aside>Side</aside></body>')
        body = root.find('body')
        
        main = extract_main_content(body)
        self.assertEqual(main.tag, 'article')
    
    def test_fallback_to_body(self):
        """Should fallback to body if no main/article."""
        root = parse_html('<body><p>Simple content</p></body>')
        body = root.find('body')
        
        main = extract_main_content(body)
        self.assertEqual(main.tag, 'body')


class TestExtractTextDom(unittest.TestCase):
    """Tests for the extract_text_dom function."""
    
    def test_extracts_title(self):
        """Should extract title from <title> tag."""
        html = '<html><head><title>My Page</title></head><body>Content</body></html>'
        result = extract_text_dom(html)
        self.assertEqual(result['title'], 'My Page')
    
    def test_extracts_description(self):
        """Should extract meta description."""
        html = '<html><head><meta name="description" content="Page desc"></head><body>Content</body></html>'
        result = extract_text_dom(html)
        self.assertEqual(result['description'], 'Page desc')
    
    def test_extracts_text(self):
        """Should extract main content text."""
        html = '<html><body><main><p>Hello world</p></main></body></html>'
        result = extract_text_dom(html)
        self.assertIn('Hello world', result['text'])
    
    def test_extracts_headings(self):
        """Should extract headings with levels."""
        html = '<html><body><h1>Title</h1><h2>Subtitle</h2></body></html>'
        result = extract_text_dom(html)
        
        headings = result['headings']
        self.assertTrue(any(h[0] == 1 and 'Title' in h[1] for h in headings))
        self.assertTrue(any(h[0] == 2 and 'Subtitle' in h[1] for h in headings))
    
    def test_strips_nav_by_default(self):
        """Should strip navigation by default."""
        html = '<html><body><nav>Menu</nav><main>Content</main></body></html>'
        result = extract_text_dom(html)
        
        self.assertNotIn('Menu', result['text'])
        self.assertIn('Content', result['text'])
    
    def test_include_nav_option(self):
        """Should include nav when include_nav=True."""
        html = '<html><body><nav>Menu</nav><main>Content</main></body></html>'
        result = extract_text_dom(html, include_nav=True)
        
        self.assertIn('Menu', result['text'])
        self.assertIn('Content', result['text'])
    
    def test_returns_dict_format(self):
        """Should return dict with expected keys."""
        result = extract_text_dom('<html><body>Test</body></html>')
        
        self.assertIn('title', result)
        self.assertIn('description', result)
        self.assertIn('text', result)
        self.assertIn('headings', result)


if __name__ == '__main__':
    unittest.main()
