"""Optional AI pronunciation layer: detect onomatopoeia / sound-effect words with
Amazon Bedrock and turn validated suggestions into Polly ``<sub alias>`` SSML.

Design notes (read before changing offset logic):

* The displayed passage text is NEVER modified. Suggestions only change what Polly
  *speaks*, via SSML ``<sub alias="...">original</sub>``. Tokens, timings, and the
  reader's UTF-16 offsets stay keyed to the original display text.
* Bedrock output is untrusted. Every suggestion's character span is re-validated
  against the real display text; the model's offsets are never trusted blindly.
* The feature is OFF by default. With it off, or on any Bedrock error, callers get
  an empty suggestion list and the pipeline falls back to today's plain-text path.

SSML speech-mark offset assumption (verified against AWS docs, see tests):
  Polly reports word speech marks as substrings of the SSML *input*, with
  byte offsets into that SSML string (not the plain text). Inside a
  ``<sub alias>`` the exact ``value``/offsets Polly emits for the spoken alias are
  treated as UNKNOWN on purpose: map_ssml_marks never relies on them. It uses the
  span positions we control and takes only the timestamp. See
  generation/tests/test_pronunciation.py for the behaviors we guard against.
"""
import json
import re

# Pronunciations are a deliberately narrow character set so a model response can
# never inject SSML/XML markup. Letters, spaces, hyphen, apostrophe only.
_PRONUNCIATION_RE = re.compile(r"^[A-Za-z][A-Za-z '\-]*[A-Za-z]$|^[A-Za-z]$")

# Default to a cross-region inference profile (the "us." prefix). The newer
# Anthropic Claude models in our account only support INFERENCE_PROFILE
# invocation, so a bare on-demand model id is rejected with
# "on-demand throughput isn't supported". This profile was verified invokable in
# us-west-2. Override with --bedrock-model / BEDROCK_MODEL_ID when needed.
DEFAULT_MODEL_ID = 'us.anthropic.claude-haiku-4-5-20251001-v1:0'

_SYSTEM_PROMPT = (
    "You help a children's reading app pronounce unusual words. "
    "Find onomatopoeia and sound-effect expressions (for example \"Brrr\", "
    "\"Vroom\", \"Achoo\") in the text. For each, give a plain spelling that a "
    "text-to-speech engine will say naturally (for example \"Brrr\" -> \"burr\"). "
    "Return ONLY JSON of the form "
    '{"suggestions":[{"original":"Brrr","start":0,"end":4,"pronunciation":"burr"}]} '
    "where start/end are character offsets into the provided text and "
    "text[start:end] equals original exactly. If there are none, return "
    '{"suggestions":[]}. Do not include any prose.'
)


def _xml_escape(text):
    return (text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                .replace('"', '&quot;').replace("'", '&apos;'))


def make_detector(client, *, model_id=DEFAULT_MODEL_ID, enabled=False):
    """Bind a Bedrock client + model into a ``detect(text) -> suggestions`` callable
    for the pipeline. Returns None when disabled so the pipeline stays on the plain
    Polly path with zero Bedrock calls."""
    if not enabled or client is None:
        return None
    return lambda text: detect_pronunciations(text, client, model_id=model_id, enabled=True)


def detect_pronunciations(text, client, *, model_id=DEFAULT_MODEL_ID, enabled=False):
    """Return raw suggestions from Bedrock, or [] when disabled / on any failure.

    ``client`` is a boto3 ``bedrock-runtime`` client (or a compatible fake in
    tests). Never raises: detection must never block narration.
    """
    if not enabled or client is None or not text or not text.strip():
        return []
    try:
        response = client.converse(
            modelId=model_id,
            system=[{'text': _SYSTEM_PROMPT}],
            messages=[{'role': 'user', 'content': [{'text': text}]}],
            inferenceConfig={'maxTokens': 1024, 'temperature': 0},
        )
        parts = response['output']['message']['content']
        raw = ''.join(part.get('text', '') for part in parts)
        return _parse_suggestions(raw)
    except Exception:
        # Any malformed response, missing key, throttling, or AWS error -> fallback.
        return []


def _parse_suggestions(raw):
    """Pull the suggestions array out of a model reply. Tolerates surrounding
    prose or code fences by scanning for the first JSON object."""
    if not isinstance(raw, str) or not raw.strip():
        return []
    candidate = raw.strip()
    # Strip a ```json ... ``` fence if present.
    fence = re.search(r'\{.*\}', candidate, re.DOTALL)
    if not fence:
        return []
    try:
        data = json.loads(fence.group(0))
    except (ValueError, TypeError):
        return []
    suggestions = data.get('suggestions') if isinstance(data, dict) else None
    return suggestions if isinstance(suggestions, list) else []


def validate_suggestions(text, suggestions):
    """Keep only suggestions that are safe and consistent with the display text.

    Rejects: wrong/That don't match offsets, overlaps, multi-word spans, empty or
    out-of-range spans, and pronunciations that aren't plain alphabetic words.
    Returns a list of clean dicts sorted by start offset, with no overlaps.
    """
    if not isinstance(suggestions, list):
        return []
    clean = []
    for item in suggestions:
        if not isinstance(item, dict):
            continue
        start, end = item.get('start'), item.get('end')
        original = item.get('original')
        pronunciation = item.get('pronunciation')
        if not (isinstance(start, int) and isinstance(end, int)):
            continue
        if isinstance(start, bool) or isinstance(end, bool):
            continue
        if not (0 <= start < end <= len(text)):
            continue
        if not isinstance(original, str) or not isinstance(pronunciation, str):
            continue
        # The model's offsets are untrusted: the span must actually be `original`.
        if text[start:end] != original:
            continue
        # Prototype scope: single display word only (no spaces inside the span).
        if original.strip() != original or re.search(r'\s', original):
            continue
        if not _PRONUNCIATION_RE.match(pronunciation):
            continue
        # No-op guard: if the suggested pronunciation equals the original word
        # (ignoring case), the substitution would not change synthesis. Drop it so
        # the word uses the normal Polly path without a pointless <sub>.
        if pronunciation.casefold() == original.casefold():
            continue
        clean.append({'start': start, 'end': end, 'original': original,
                      'pronunciation': pronunciation})
    clean.sort(key=lambda s: s['start'])
    # Drop overlaps, keeping the earliest.
    result, last_end = [], -1
    for item in clean:
        if item['start'] >= last_end:
            result.append(item)
            last_end = item['end']
    return result


def build_segments(text, suggestions):
    """Describe how `text` maps into SSML as an ordered list of segments:
      {'kind':'plain','text':<display>} | {'kind':'sub','text':<display>,'alias':<str>}
    Concatenating the display text of all segments reproduces `text` exactly, so
    display offsets are recoverable. Assumes `suggestions` is already validated
    (sorted, non-overlapping, in range)."""
    segments, cursor = [], 0
    for item in suggestions:
        if item['start'] > cursor:
            segments.append({'kind': 'plain', 'text': text[cursor:item['start']]})
        segments.append({'kind': 'sub', 'text': item['original'], 'alias': item['pronunciation']})
        cursor = item['end']
    if cursor < len(text):
        segments.append({'kind': 'plain', 'text': text[cursor:]})
    return segments


def build_ssml(text, suggestions):
    """Wrap `text` as SSML, substituting validated spans with <sub alias>.
    Everything is XML-escaped; display text outside spans is preserved verbatim."""
    body = []
    for segment in build_segments(text, suggestions):
        if segment['kind'] == 'sub':
            body.append(f'<sub alias="{_xml_escape(segment["alias"])}">'
                        f'{_xml_escape(segment["text"])}</sub>')
        else:
            body.append(_xml_escape(segment['text']))
    return '<speak>' + ''.join(body) + '</speak>'
