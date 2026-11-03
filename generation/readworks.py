"""Convert ReadWorks product JSON into the generation input format."""
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import urlopen

PRODUCT_URL = 'https://s3.us-west-2.amazonaws.com/readworks-media-qa/data/p/{}'
LANGUAGES = {'EN': 'en-US'}
MAX_SOURCE_BYTES = 5_000_000
UUID = re.compile(r'[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}')


class _DisplayedText(HTMLParser):
    """Collect passage text from content HTML, leaving out figures and their captions."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.figure_depth = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == 'figure':
            self.figure_depth += 1

    def handle_endtag(self, tag):
        if tag == 'figure' and self.figure_depth:
            self.figure_depth -= 1

    def handle_data(self, data):
        if not self.figure_depth:
            self.parts.append(data)


def _without_whitespace(text):
    return ''.join(text.split())


def _check_text_matches_content(text, content):
    """Stop if the page shows words that narration would skip, such as headings."""
    parser = _DisplayedText()
    parser.feed(content)
    parser.close()
    expected, displayed = _without_whitespace(text), _without_whitespace(''.join(parser.parts))
    if expected == displayed:
        return
    index = next((i for i, (a, b) in enumerate(zip(expected, displayed)) if a != b),
                 min(len(expected), len(displayed)))
    raise ValueError(f'ReadWorks text and content differ: text has {expected[index:index + 30]!r}, '
                     f'content has {displayed[index:index + 30]!r}')


def is_readworks(data):
    return isinstance(data, dict) and 'uuid' in data and 'text' in data and 'paragraphs' not in data


def convert(product):
    """Return a generation passage for an article-style ReadWorks product document."""
    for field in ('uuid', 'title', 'lang', 'text', 'content'):
        if not isinstance(product.get(field), str) or not product[field].strip():
            raise ValueError(f'ReadWorks JSON needs a nonempty string field: {field}')
    if 'ebook' in (product.get('features') or []):
        raise ValueError('Ebook-style passages are not supported')
    language = LANGUAGES.get(product['lang'].upper())
    if language is None:
        raise ValueError(f"Unsupported ReadWorks language: {product['lang']}")
    _check_text_matches_content(product['text'], product['content'])
    lines = [line.strip() for line in product['text'].split('\n') if line.strip()]
    return {
        'id': product['uuid'],
        # ReadWorks has no integer revision. The input hash already covers text changes.
        'revision': 1,
        'title': product['title'],
        'language': language,
        'source': {'provider': 'readworks', 'uuid': product['uuid'], 'au': product.get('au')},
        'paragraphs': [{'id': f'p{index}', 'text': line} for index, line in enumerate(lines, 1)],
    }


def _read_url(url):
    with urlopen(url, timeout=30) as response:
        body = response.read(MAX_SOURCE_BYTES + 1)
    if len(body) > MAX_SOURCE_BYTES:
        raise ValueError('Source passage JSON is too large')
    return body


def load_passage(source):
    """Load a passage from a file, https URL, or ReadWorks UUID, converting ReadWorks JSON."""
    if UUID.fullmatch(source):
        body = _read_url(PRODUCT_URL.format(source))
    elif source.startswith('https://'):
        body = _read_url(source)
    else:
        body = Path(source).read_bytes()
    data = json.loads(body)
    return convert(data) if is_readworks(data) else data
