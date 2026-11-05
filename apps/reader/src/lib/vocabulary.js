import { splitSentences } from './readingParts.js';
export function ensureTokens(passage) {
  if (passage.tokens?.length) return;
  passage.tokens = passage.paragraphs.flatMap(p => [...p.text.matchAll(/[\p{L}\p{N}]+(?:['’-][\p{L}\p{N}]+)*/gu)].map(m => ({ id: `${p.id}-${m.index}`, paragraphId: p.id, text: m[0], start: m.index, end: m.index + m[0].length })));
}
export function wordContext(passage, tokenId) {
  const token = passage.tokens.find(t => t.id === tokenId);
  if (!token) return null;
  const paragraph = [...passage.paragraphs, ...(passage.narrationTitle ? [passage.narrationTitle] : [])].find(p => p.id === token.paragraphId);
  const parts = splitSentences(paragraph.text, passage.tokens.filter(t => t.paragraphId === paragraph.id)).find(s => s.parts?.some(t => t.id === tokenId))?.parts || [];
  const sentence = parts.map(t => t.text).join('');
  const index = parts.findIndex(t => t.id === tokenId);
  return { word: token.text, tokenId, sentence, before: parts.slice(0, index).map(t => t.text).join(''), after: parts.slice(index + 1).map(t => t.text).join(''), midSentence: parts.slice(0, index).some(t => t.id) };
}
export function readMyWords(storage, id) {
  try {
    const list = JSON.parse(storage.getItem(`soundworks.myWords.${id}`) || '[]');
    return Array.isArray(list) ? list.filter(item => item && typeof item.word === 'string' && typeof item.sentence === 'string' && typeof item.definition === 'string') : [];
  } catch { return []; }
}

// Our original demo passage isn't in the ReadWorks catalog, so it has no official word list. Matched by
// word, not token ID, because a recording that reads the title first shifts every ID.
const DEMO_WORDS = ['community', 'sunrise', 'seedlings'];
export function demoWordList(tokens = []) {
  return DEMO_WORDS.map(word => ({
    word,
    occurrences: tokens.filter(token => token.text.toLowerCase() === word).map(token => ({ tokenIds: [token.id] })),
  })).filter(entry => entry.occurrences.length);
}
