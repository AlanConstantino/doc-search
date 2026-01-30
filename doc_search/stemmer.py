"""
Porter Stemmer implementation in pure Python.

Based on the Porter Stemming Algorithm by Martin Porter (1980).
Reference: https://tartarus.org/martin/PorterStemmer/def.txt

This is a complete implementation with all 5 steps.
"""

import re


def _is_consonant(word: str, i: int) -> bool:
    """Check if character at position i is a consonant."""
    if i >= len(word):
        return False
    c = word[i].lower()
    if c in 'aeiou':
        return False
    if c == 'y':
        # Y is a consonant if it's the first letter or follows a vowel
        return i == 0 or not _is_consonant(word, i - 1)
    return True


def _measure(word: str) -> int:
    """
    Calculate the 'measure' of a word - the number of VC (vowel-consonant) sequences.
    
    [C](VC){m}[V] where m is the measure.
    
    Examples:
        tr -> 0, ee -> 0, tree -> 0, y -> 0
        by -> 1, trouble -> 2, oats -> 1, trees -> 1
        ivy -> 2, troubles -> 2, private -> 3
    """
    if not word:
        return 0
    
    # Build consonant/vowel pattern
    pattern = []
    for i in range(len(word)):
        pattern.append('C' if _is_consonant(word, i) else 'V')
    
    pattern_str = ''.join(pattern)
    
    # Count VC sequences
    count = 0
    i = 0
    # Skip initial consonants
    while i < len(pattern_str) and pattern_str[i] == 'C':
        i += 1
    
    while i < len(pattern_str):
        # Find V
        if i < len(pattern_str) and pattern_str[i] == 'V':
            # Skip vowels
            while i < len(pattern_str) and pattern_str[i] == 'V':
                i += 1
            # Find C after V
            if i < len(pattern_str) and pattern_str[i] == 'C':
                count += 1
                # Skip consonants
                while i < len(pattern_str) and pattern_str[i] == 'C':
                    i += 1
        else:
            i += 1
    
    return count


def _has_vowel(stem: str) -> bool:
    """Check if stem contains a vowel."""
    for i in range(len(stem)):
        if not _is_consonant(stem, i):
            return True
    return False


def _ends_double_consonant(word: str) -> bool:
    """Check if word ends with a double consonant."""
    if len(word) < 2:
        return False
    return (word[-1] == word[-2] and 
            _is_consonant(word, len(word) - 1))


def _ends_cvc(word: str) -> bool:
    """
    Check if word ends with consonant-vowel-consonant,
    where the final consonant is not w, x, or y.
    """
    if len(word) < 3:
        return False
    
    return (_is_consonant(word, len(word) - 1) and
            not _is_consonant(word, len(word) - 2) and
            _is_consonant(word, len(word) - 3) and
            word[-1].lower() not in 'wxy')


def _replace_suffix(word: str, suffix: str, replacement: str) -> str:
    """Replace suffix with replacement."""
    if word.endswith(suffix):
        return word[:-len(suffix)] + replacement
    return word


def _step1a(word: str) -> str:
    """
    Step 1a: Handle plurals and past tenses.
    
    SSES -> SS    caresses -> caress
    IES  -> I     ponies -> poni, ties -> ti
    SS   -> SS    caress -> caress
    S    ->       cats -> cat
    """
    if word.endswith('sses'):
        return word[:-2]
    if word.endswith('ies'):
        return word[:-2]
    if word.endswith('ss'):
        return word
    if word.endswith('s'):
        return word[:-1]
    return word


def _step1b(word: str) -> str:
    """
    Step 1b: Handle -ed and -ing suffixes.
    
    (m>0) EED -> EE    feed -> feed, agreed -> agree
    (*v*) ED  ->       plastered -> plaster, bled -> bled
    (*v*) ING ->       motoring -> motor, sing -> sing
    
    If the second or third rule results in a word ending in:
    AT -> ATE    conflat(ed) -> conflate
    BL -> BLE    troubl(ed) -> trouble
    IZ -> IZE    siz(ed) -> size
    (*d and not (*L or *S or *Z)) -> single letter
                 hopp(ing) -> hop, tann(ed) -> tan
    (m=1 and *o) -> E    fail(ing) -> fail, fil(ing) -> file
    """
    if word.endswith('eed'):
        stem = word[:-3]
        if _measure(stem) > 0:
            return word[:-1]  # EED -> EE
        return word
    
    changed = False
    if word.endswith('ed'):
        stem = word[:-2]
        if _has_vowel(stem):
            word = stem
            changed = True
    elif word.endswith('ing'):
        stem = word[:-3]
        if _has_vowel(stem):
            word = stem
            changed = True
    
    if changed:
        if word.endswith('at') or word.endswith('bl') or word.endswith('iz'):
            return word + 'e'
        if (_ends_double_consonant(word) and 
            word[-1].lower() not in 'lsz'):
            return word[:-1]
        if _measure(word) == 1 and _ends_cvc(word):
            return word + 'e'
    
    return word


def _step1c(word: str) -> str:
    """
    Step 1c: Turn terminal y to i when there is another vowel in the stem.
    
    (*v*) Y -> I    happy -> happi, sky -> sky
    """
    if word.endswith('y') and len(word) > 1:
        stem = word[:-1]
        if _has_vowel(stem):
            return stem + 'i'
    return word


def _step2(word: str) -> str:
    """
    Step 2: Handle various suffixes when m > 0.
    """
    pairs = [
        ('ational', 'ate'),
        ('tional', 'tion'),
        ('enci', 'ence'),
        ('anci', 'ance'),
        ('izer', 'ize'),
        ('abli', 'able'),
        ('alli', 'al'),
        ('entli', 'ent'),
        ('eli', 'e'),
        ('ousli', 'ous'),
        ('ization', 'ize'),
        ('ation', 'ate'),
        ('ator', 'ate'),
        ('alism', 'al'),
        ('iveness', 'ive'),
        ('fulness', 'ful'),
        ('ousness', 'ous'),
        ('aliti', 'al'),
        ('iviti', 'ive'),
        ('biliti', 'ble'),
    ]
    
    for suffix, replacement in pairs:
        if word.endswith(suffix):
            stem = word[:-len(suffix)]
            if _measure(stem) > 0:
                return stem + replacement
            break
    
    return word


def _step3(word: str) -> str:
    """
    Step 3: Handle various suffixes when m > 0.
    """
    pairs = [
        ('icate', 'ic'),
        ('ative', ''),
        ('alize', 'al'),
        ('iciti', 'ic'),
        ('ical', 'ic'),
        ('ful', ''),
        ('ness', ''),
    ]
    
    for suffix, replacement in pairs:
        if word.endswith(suffix):
            stem = word[:-len(suffix)]
            if _measure(stem) > 0:
                return stem + replacement
            break
    
    return word


def _step4(word: str) -> str:
    """
    Step 4: Remove various suffixes when m > 1.
    """
    suffixes = [
        'al', 'ance', 'ence', 'er', 'ic', 'able', 'ible', 'ant', 'ement',
        'ment', 'ent', 'ion', 'ou', 'ism', 'ate', 'iti', 'ous', 'ive', 'ize'
    ]
    
    for suffix in suffixes:
        if word.endswith(suffix):
            stem = word[:-len(suffix)]
            if suffix == 'ion':
                # Special case: ion only removed if preceded by s or t
                if stem and stem[-1] in 'st' and _measure(stem) > 1:
                    return stem
            elif _measure(stem) > 1:
                return stem
            break
    
    return word


def _step5a(word: str) -> str:
    """
    Step 5a: Remove final -e.
    
    (m>1) E ->     probate -> probat, rate -> rate
    (m=1 and not *o) E ->  cease -> ceas
    """
    if word.endswith('e'):
        stem = word[:-1]
        m = _measure(stem)
        if m > 1:
            return stem
        if m == 1 and not _ends_cvc(stem):
            return stem
    return word


def _step5b(word: str) -> str:
    """
    Step 5b: Remove double consonant -ll when m > 1.
    
    (m>1 and *d and *L) -> single letter
    controll -> control, roll -> roll
    """
    if (word.endswith('ll') and _measure(word[:-1]) > 1):
        return word[:-1]
    return word


def stem(word: str) -> str:
    """
    Apply the Porter Stemming algorithm to a word.
    
    Args:
        word: The word to stem.
        
    Returns:
        The stemmed word.
        
    Examples:
        >>> stem('running')
        'run'
        >>> stem('files')
        'file'
        >>> stem('caresses')
        'caress'
    """
    # Handle edge cases
    if not word or len(word) <= 2:
        return word.lower()
    
    word = word.lower()
    
    # Apply all steps
    word = _step1a(word)
    word = _step1b(word)
    word = _step1c(word)
    word = _step2(word)
    word = _step3(word)
    word = _step4(word)
    word = _step5a(word)
    word = _step5b(word)
    
    return word


def stem_tokens(tokens: list) -> list:
    """Stem a list of tokens."""
    return [stem(token) for token in tokens]
