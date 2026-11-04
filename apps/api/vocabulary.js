import { Parser } from 'htmlparser2';

export const USER_AGENT = 'SoundWorksReader/0.1 (https://github.com/yufeiihuang/ReadWorks48)';
export function plainText(html) {
  let text = '';
  const parser = new Parser({ ontext: value => { text += value; } }, { decodeEntities: true });
  parser.end(html || '');
  return text;
}
export function cleanWiki(text) {
  return text.replace(/\[\[([^\]|]+)\|([^\]]+)\]\]/g, '$2').replace(/\[\[([^\]]+)\]\]/g, '$1')
    .replace(/\{\{[^{}]*\}\}/g, '').replace(/'{2,3}/g, '').replace(/<ref\b[^>]*>[\s\S]*?<\/ref>/g, '').replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim();
}
export function parseWikitext(text) {
  let partOfSpeech = '', base = null;
  const senses = [];
  for (const line of text.split('\n')) {
    const heading = /^={2,}\s*([^=]+?)\s*={2,}\s*$/.exec(line);
    if (heading) { partOfSpeech = /^(noun|verb|adjective|adverb|pronoun|preposition|conjunction|interjection|determiner|article|proper noun)$/i.test(heading[1]) ? heading[1] : ''; continue; }
    if (!partOfSpeech || !/^#(?![:*#])/.test(line)) continue;
    const form = /\{\{(?:plural of|past of|past tense of|past tense and participle of|past participle of|present participle of|present participle and gerund of|third-person singular of|third-person singular present of|comparative of|superlative of)\|(?:en\|)?([^|}]+)/i.exec(line);
    if (form) { base ||= form[1].trim(); continue; }
    const definition = cleanWiki(line.replace(/^#\s*/, ''));
    if (definition) senses.push({ partOfSpeech, definition });
  }
  return { senses, base };
}
const simpleSource = word => ({ name: 'Simple English Wiktionary', license: 'CC BY-SA 4.0', url: `https://simple.wiktionary.org/wiki/${encodeURIComponent(word)}` });
export function createDictionary(fetcher = fetch) {
  const cache = new Map();
  const upstreamCache = new Map();
  const fetchJson = async url => {
    const response = await fetcher(url, { headers: { 'User-Agent': USER_AGENT }, signal: AbortSignal.timeout(8000) });
    if (response.status === 404) return null;
    if (!response.ok) throw new Error(`Dictionary request failed: ${response.status}`);
    return response.json();
  };
  const get = url => {
    if (!upstreamCache.has(url)) {
      if (upstreamCache.size >= 2000) upstreamCache.delete(upstreamCache.keys().next().value);
      upstreamCache.set(url, fetchJson(url).catch(error => { upstreamCache.delete(url); throw error; }));
    }
    return upstreamCache.get(url);
  };
  async function lookup(word) {
    const data = await get(`https://simple.wiktionary.org/w/api.php?action=parse&page=${encodeURIComponent(word)}&prop=wikitext&format=json&formatversion=2`);
    const parsed = parseWikitext(data?.parse?.wikitext || '');
    let lemma = word, senses = parsed.senses;
    if (parsed.base && parsed.base.toLowerCase() !== word.toLowerCase()) {
      lemma = parsed.base;
      const base = await get(`https://simple.wiktionary.org/w/api.php?action=parse&page=${encodeURIComponent(lemma)}&prop=wikitext&format=json&formatversion=2`);
      senses = parseWikitext(base?.parse?.wikitext || '').senses;
    }
    let source = simpleSource(lemma);
    if (!senses.length) {
      const fallback = await get(`https://en.wiktionary.org/api/rest_v1/page/definition/${encodeURIComponent(word)}`);
      senses = (fallback?.en || []).flatMap(section => (section.definitions || []).map(item => ({ partOfSpeech: section.partOfSpeech, definition: plainText(item.definition) }))).filter(item => item.definition);
      if (senses.length) source = { name: 'English Wiktionary', license: 'CC BY-SA 4.0', url: `https://en.wiktionary.org/wiki/${encodeURIComponent(word)}` };
    }
    return { word, lemma, senses: senses.slice(0, 3), source };
  }
  return word => {
    const key = word.toLowerCase();
    if (!cache.has(key)) {
      // Bound warm-Lambda memory. Failed requests are retried, not cached as missing words.
      if (cache.size >= 2000) cache.delete(cache.keys().next().value);
      cache.set(key, lookup(key).catch(error => { cache.delete(key); throw error; }));
    }
    return cache.get(key);
  };
}

// The only ReadWorks vocabulary fields read here are the word list and marked content.
// Offsets count non-whitespace characters, matching generation/readworks.py's text check.
export function mapOfficialWords(product, passage) {
  const marks = [], stack = [];
  let text = '', offset = 0, figureDepth = 0;
  const parser = new Parser({
    onopentag(name, attrs) { if (name === 'figure') figureDepth++; stack.push({ name, start: offset, marked: !figureDepth && name === 'span' && Object.hasOwn(attrs, 'data-vocab-sense-id') }); },
    ontext(value) { if (figureDepth) return; const normalized = value.replace(/\s/g, ''); text += normalized; offset += normalized.length; },
    onclosetag(name) { if (name === 'figure') figureDepth--; const tag = stack.pop(); if (tag?.marked) marks.push({ start: tag.start, end: offset }); },
  }, { decodeEntities: true });
  parser.end(product.content || '');
  const paragraphs = passage.paragraphs || [];
  if (text !== paragraphs.map(p => p.text.replace(/\s/g, '')).join('')) return [];
  let before = 0;
  const tokens = [];
  for (const paragraph of paragraphs) {
    for (const token of passage.tokens || []) if (token.paragraphId === paragraph.id) {
      tokens.push({ ...token, start: before + paragraph.text.slice(0, token.start).replace(/\s/g, '').length, end: before + paragraph.text.slice(0, token.end).replace(/\s/g, '').length });
    }
    before += paragraph.text.replace(/\s/g, '').length;
  }
  return (product.vocab?.support?.word_list || []).map(word => ({ word, occurrences: marks.filter(mark => text.slice(mark.start, mark.end).toLowerCase() === word.replace(/\s/g, '').toLowerCase()).map(mark => ({ tokenIds: tokens.filter(token => token.start < mark.end && token.end > mark.start).map(token => token.id) })).filter(item => item.tokenIds.length) })).filter(item => item.occurrences.length);
}
