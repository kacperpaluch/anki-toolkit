"""Starter prompt templates for the "Nowy prompt" wizard.

Field references inside template texts use «param» placeholders — the wizard
maps each param to a real note field and `build_prompt()` rewrites them to
{{field}} / {% if field %} syntax understood by the template engine.

Template dict keys:
  id            — stable identifier,
  name / desc   — shown in the wizard list,
  target_hints  — lowercase field-name guesses for preselecting the target,
  params        — [(key, label, hints)] mapped to note fields by the user,
  prompt        — template body (None when `conditional` provides branches),
  conditional   — optional {label, param: (key, label, hints),
                   prompt_with, prompt_without}; when enabled the wizard
                   assembles {% if field %}…{% else %}…{% endif %} itself.
"""

_DEFINITION_PROMPT = """++role++
You are an experienced English teacher creating clear, learner-friendly definitions suitable for intermediate (B1/B2) English learners.

++task++
Write a concise dictionary-style definition of an English word based solely on the given Polish translation.

++rules++
1. Your definition must closely align with the provided Polish translation.
2. Do NOT use the English word itself in the definition.
3. Write in simple language appropriate for intermediate (B1/B2) learners.
4. Keep the definition short, clear, and dictionary-like.

++output format++
Only provide your simple dictionary-style definition in plain text, with no extra commentary.

Example input:
English word: bag
Polish translation: torba

Correct example definition:
A soft container made of cloth, leather, or plastic, used for holding or carrying things.

Now provide definition for:
English word: {{«word»}}
Polish translation: {{«translation»}}"""

_EXAMPLES_WITH_DEF = """++role++
You are an expert English language educator specializing in vocabulary acquisition for intermediate learners.

++task++
Craft exactly three clear, natural English example sentences illustrating the precise context and meaning of a given English word ("EN") as specified by its Polish translation ("PL") and supported by a concise English definition ("DEF").

++rules++
- Use only the context and meaning indicated by the provided Polish translation and English definition.
- Provide exactly three separate English sentences.
- Each sentence must be clear, natural, and appropriate for intermediate learners (B1/B2).
- Place "<br><br>" after sentences 1 and 2 only; do not place it after sentence 3.
- Do not include definitions, explanations, translations, numbering, or commentary.
- Avoid illustrating irrelevant, figurative, or alternative meanings.

++output format++
sentence 1<br><br>
sentence 2<br><br>
sentence 3

++input++
EN: {{«word»}}
PL: {{«translation»}}
DEF: {{«definition»}}"""

_EXAMPLES_WITHOUT_DEF = """++role++
You are an English assistant creating example sentences for intermediate (B1/B2) language learners.

++task++
You get an English word ("EN") with its Polish meaning ("PL"). Provide exactly three clear, natural example sentences illustrating exclusively this indicated meaning/context.

++rules++
- Provide exactly three English sentences.
- Only illustrate the context indicated by the provided Polish meaning.
- Place "<br><br>" after sentences 1 and 2 only.
- No definitions, explanations, translations into Polish, numbering, or additional commentary.
- Keep grammar and vocabulary suitable for intermediate learners (B1/B2).

++output format++
sentence 1<br><br>
sentence 2<br><br>
sentence 3

++input++
EN: {{«word»}}
PL: {{«translation»}}"""

_PART_OF_SPEECH_PROMPT = """++role++
Expert linguist categorizing English vocabulary.

++task++
Classify English words/phrases into grammatical categories based on Polish translations.

++rules++
- Use exactly ONE category from:
n (noun), v (verb), adj (adjective), adv (adverb),
prep (preposition), conj (conjunction), pron (pronoun),
int (interjection), pv (phrasal verb),
i (idiom), coll (collocation or expression)
- NO punctuation, explanations, or commentary.

++output format++
ONLY single abbreviation (no punctuation).

Example format:
EN: look forward to PL: czekać z niecierpliwością
pv

EN: beautiful PL: piękny
adj

Input:
EN: {{«word»}} PL: {{«translation»}}"""

_IPA_PROMPT = """++role++
You are an expert in British English Received Pronunciation (RP) and IPA transcription.

++task++
Provide the standard IPA pronunciation transcription (British English RP) for the given English word or phrase.

++rules++
- Use only standard British RP pronunciation (as per Collins, Cambridge, or Oxford dictionaries).
- Always use standard IPA symbols.
- Provide only one, most common IPA transcription.
- Enclose your transcription strictly between forward slashes (/ /).
- Do not include additional text, punctuation, or comments.

++output format++
Only IPA transcription enclosed in forward slashes. Absolutely no other text.

Good examples:

Input: dog
Output: /dɒɡ/

Input: schedule
Output: /ˈʃɛdjuːl/

Now generate the IPA transcription for this English expression:

{{«word»}}"""


TEMPLATES: list[dict] = [
    {
        "id": "definition",
        "name": "Definicja po angielsku",
        "desc": "Krótka, prosta definicja słownikowa (poziom B1/B2) na podstawie słowa i tłumaczenia.",
        "target_hints": ["def", "definicja", "definition"],
        "params": [
            ("word", "Słowo / wyrażenie (EN)", ["ang", "en", "word", "front"]),
            ("translation", "Tłumaczenie (PL)", ["pol", "pl", "back", "tlumaczenie"]),
        ],
        "prompt": _DEFINITION_PROMPT,
        "conditional": None,
    },
    {
        "id": "examples",
        "name": "Przykładowe zdania (3 szt.)",
        "desc": "Trzy naturalne zdania ilustrujące znaczenie słowa, rozdzielone <br><br>.",
        "target_hints": ["przyklad", "przyklady", "example", "examples", "sentences"],
        "params": [
            ("word", "Słowo / wyrażenie (EN)", ["ang", "en", "word", "front"]),
            ("translation", "Tłumaczenie (PL)", ["pol", "pl", "back", "tlumaczenie"]),
        ],
        "prompt": None,
        "conditional": {
            "label": "Jeśli pole z definicją jest już wypełnione, wykorzystaj je w prompcie",
            "param": ("definition", "Pole z definicją (EN)", ["def", "definicja", "definition"]),
            "prompt_with": _EXAMPLES_WITH_DEF,
            "prompt_without": _EXAMPLES_WITHOUT_DEF,
        },
    },
    {
        "id": "part_of_speech",
        "name": "Część mowy / kategoria",
        "desc": "Jeden skrót gramatyczny (n, v, adj, pv, idiom…) na podstawie słowa i tłumaczenia.",
        "target_hints": ["cz_mowy", "pos", "kategoria", "czesc_mowy"],
        "params": [
            ("word", "Słowo / wyrażenie (EN)", ["ang", "en", "word", "front"]),
            ("translation", "Tłumaczenie (PL)", ["pol", "pl", "back", "tlumaczenie"]),
        ],
        "prompt": _PART_OF_SPEECH_PROMPT,
        "conditional": None,
    },
    {
        "id": "ipa",
        "name": "Transkrypcja IPA",
        "desc": "Brytyjska wymowa RP w slashach, np. /ˈʃɛdjuːl/.",
        "target_hints": ["ipa", "wymowa", "transkrypcja"],
        "params": [
            ("word", "Słowo / wyrażenie (EN)", ["ang", "en", "word", "front"]),
        ],
        "prompt": _IPA_PROMPT,
        "conditional": None,
    },
    {
        "id": "custom",
        "name": "Własny prompt (pusty)",
        "desc": "Zacznij od pustego edytora — sam napiszesz treść promptu.",
        "target_hints": [],
        "params": [],
        "prompt": "",
        "conditional": None,
    },
]


def guess_field(hints: list[str], fields: list[str]) -> str:
    """Pick the note field best matching the given lowercase hints ('' = none)."""
    lowered = {f.lower(): f for f in fields}
    for hint in hints:
        if hint in lowered:
            return lowered[hint]
    for hint in hints:
        for low, original in lowered.items():
            if hint in low:
                return original
    return ""


def build_prompt(template: dict, mapping: dict[str, str],
                 use_conditional: bool = False) -> str:
    """Assemble the final prompt text with «param» placeholders resolved.

    `mapping` maps param keys (including the conditional param) to note field
    names. With `use_conditional` the {% if %}/{% else %} block is generated
    here, so the user never writes the syntax by hand.
    """
    cond = template.get("conditional")
    if cond and use_conditional:
        cond_field = mapping.get(cond["param"][0], "").strip()
        body = (
            "{% if " + cond_field + " %}\n"
            + cond["prompt_with"].strip()
            + "\n{% else %}\n"
            + cond["prompt_without"].strip()
            + "\n{% endif %}"
        )
    elif cond:
        body = cond["prompt_without"].strip()
    else:
        body = template.get("prompt") or ""

    for key, field in mapping.items():
        if field:
            body = body.replace("«" + key + "»", field)
    return body
