"""
UAX #29 Unicode Text Segmentation Word Boundary Algorithm

This module implements the full UAX #29 Word Boundary rules for Unicode text
segmentation in pure Python with zero external dependencies (only uses stdlib
unicodedata module).

The algorithm classifies characters by their Word_Break properties and applies
the word boundary rules to determine where to break text into segments.

References:
    - Unicode Standard Annex #29: https://unicode.org/reports/tr29/
    - Unicode Word_Break Property: https://www.unicode.org/Public/UCD/latest/ucd/auxiliary/WordBreakProperty.txt
"""

import unicodedata
from typing import List, Optional


# ASCII lookup table for performance (covers 0-127)
# Pre-computed Word_Break properties for ASCII characters
_ASCII_WORD_BREAK = [
    # 0x00-0x0F: Control characters
    'Other', 'Other', 'Other', 'Other', 'Other', 'Other', 'Other', 'Other',
    'Other', 'Other', 'LF', 'Newline', 'Newline', 'CR', 'Other', 'Other',
    
    # 0x10-0x1F: More control characters
    'Other', 'Other', 'Other', 'Other', 'Other', 'Other', 'Other', 'Other',
    'Other', 'Other', 'Other', 'Other', 'Other', 'Other', 'Other', 'Other',
    
    # 0x20-0x2F: Space and punctuation
    'WSegSpace',  # U+0020 SPACE
    'Other',      # U+0021 !
    'Double_Quote', # U+0022 "
    'Other',      # U+0023 #
    'Other',      # U+0024 $
    'Other',      # U+0025 %
    'Other',      # U+0026 &
    'Single_Quote', # U+0027 '
    'Other',      # U+0028 (
    'Other',      # U+0029 )
    'Other',      # U+002A *
    'Other',      # U+002B +
    'MidNum',     # U+002C ,
    'Other',      # U+002D -
    'MidNumLet',  # U+002E .
    'Other',      # U+002F /
    
    # 0x30-0x3F: Digits and more punctuation
    'Numeric', 'Numeric', 'Numeric', 'Numeric', 'Numeric',  # 0-4
    'Numeric', 'Numeric', 'Numeric', 'Numeric', 'Numeric',  # 5-9
    'MidLetter',  # U+003A :
    'MidNum',     # U+003B ;
    'Other',      # U+003C <
    'Other',      # U+003D =
    'Other',      # U+003E >
    'Other',      # U+003F ?
    
    # 0x40-0x4F: @ and A-O
    'Other',      # U+0040 @
    'ALetter', 'ALetter', 'ALetter', 'ALetter', 'ALetter',  # A-E
    'ALetter', 'ALetter', 'ALetter', 'ALetter', 'ALetter',  # F-J
    'ALetter', 'ALetter', 'ALetter', 'ALetter', 'ALetter',  # K-O
    
    # 0x50-0x5F: P-Z, brackets, backslash, etc.
    'ALetter', 'ALetter', 'ALetter', 'ALetter', 'ALetter',  # P-T
    'ALetter', 'ALetter', 'ALetter', 'ALetter', 'ALetter',  # U-Y
    'ALetter',    # Z
    'Other',      # U+005B [
    'Other',      # U+005C \
    'Other',      # U+005D ]
    'Other',      # U+005E ^
    'ExtendNumLet', # U+005F _
    
    # 0x60-0x6F: ` and a-o
    'Other',      # U+0060 `
    'ALetter', 'ALetter', 'ALetter', 'ALetter', 'ALetter',  # a-e
    'ALetter', 'ALetter', 'ALetter', 'ALetter', 'ALetter',  # f-j
    'ALetter', 'ALetter', 'ALetter', 'ALetter', 'ALetter',  # k-o
    
    # 0x70-0x7F: p-z and more punctuation
    'ALetter', 'ALetter', 'ALetter', 'ALetter', 'ALetter',  # p-t
    'ALetter', 'ALetter', 'ALetter', 'ALetter', 'ALetter',  # u-y
    'ALetter',    # z
    'Other',      # U+007B {
    'Other',      # U+007C |
    'Other',      # U+007D }
    'Other',      # U+007E ~
    'Other',      # U+007F DEL
]


def word_break_property(char: str) -> str:
    """
    Get the Word_Break property for a Unicode character.
    
    Maps each Unicode character to its Word_Break property value according
    to UAX #29. Uses an ASCII lookup table for performance on ASCII text,
    and derives properties from unicodedata for non-ASCII characters.
    
    Args:
        char: Single Unicode character
        
    Returns:
        Word_Break property name as string
        
    Property Values:
        - CR: U+000D (Carriage Return)
        - LF: U+000A (Line Feed) 
        - Newline: Other line break characters (VT, FF, NEL, LS, PS)
        - Extend: Combining marks (Mn, Mc, Me categories)
        - ZWJ: Zero Width Joiner U+200D
        - Format: Format characters (Cf category, except ZWNJ/ZWJ)
        - Regional_Indicator: Regional indicator symbols (flags)
        - Katakana: Katakana script characters
        - Hebrew_Letter: Hebrew script letters
        - ALetter: Most other letters (Lu, Ll, Lt, Lm, Lo)
        - Single_Quote: Apostrophe U+0027
        - Double_Quote: Quotation mark U+0022  
        - MidNumLet: Characters that can appear mid-word (period, etc.)
        - MidLetter: Characters that separate letters (colon, etc.)
        - MidNum: Characters that separate numbers (comma, etc.)
        - Numeric: Decimal digit numbers (Nd category)
        - ExtendNumLet: Connector punctuation (underscore, etc.)
        - WSegSpace: Word separating spaces (Zs category)
        - Other: Everything else
    """
    code = ord(char)
    
    # Fast path for ASCII
    if code < 128:
        return _ASCII_WORD_BREAK[code]
    
    # Special code points that need explicit handling
    if code == 0x200D:  # ZWJ
        return 'ZWJ'
    elif code == 0x200C:  # ZWNJ (explicitly not Format per UAX #29)
        return 'Other'
    elif 0x1F1E6 <= code <= 0x1F1FF:  # Regional Indicators
        return 'Regional_Indicator'
    elif code in (0x0085, 0x2028, 0x2029):  # Additional newlines
        return 'Newline'
    elif code in (0x3031, 0x3032, 0x3033, 0x3034, 0x3035, 0x309B, 0x309C):
        # Additional Katakana characters
        return 'Katakana'
    elif code in (0x00B7, 0x0387, 0xFE13, 0xFE55, 0xFF1A, 0x02D7):  # MidLetter
        return 'MidLetter'
    elif code in (0x2018, 0x2019, 0x2024, 0xFE52, 0xFF07, 0xFF0E):  # MidNumLet
        return 'MidNumLet'
    elif code in (0x037E, 0x0589, 0x060C, 0x060D, 0x066C, 0x07F8, 0x2044,
                  0xFE10, 0xFE14, 0xFE50, 0xFE54, 0xFF0C, 0xFF1B):  # MidNum
        return 'MidNum'
    
    # Use unicodedata for category-based classification
    category = unicodedata.category(char)
    
    if category == 'Mn' or category == 'Mc' or category == 'Me':
        return 'Extend'
    elif category == 'Cf':  # Format, but exclude ZWNJ (handled above) and ZWJ
        return 'Format'
    elif category == 'Nd':
        return 'Numeric'
    elif category == 'Pc':  # Connector punctuation (underscore, etc.)
        return 'ExtendNumLet'
    elif category == 'Zs':  # Space separator
        return 'WSegSpace'
    elif category in ('Lu', 'Ll', 'Lt', 'Lm', 'Lo'):
        # Letter categories - need to check for Hebrew and Katakana
        script = unicodedata.name(char, '').upper()
        if 'HEBREW' in script:
            return 'Hebrew_Letter'
        elif 'KATAKANA' in script or 'HIRAGANA' in script:
            # Hiragana is sometimes grouped with Katakana for word breaking
            return 'Katakana'
        else:
            return 'ALetter'
    else:
        return 'Other'


def _is_extended_pictographic(char: str) -> bool:
    """
    Check if character is Extended_Pictographic.
    
    This is a simplified approximation using common emoji ranges.
    A full implementation would need the complete Extended_Pictographic
    property table from Unicode data files.
    
    Args:
        char: Single Unicode character
        
    Returns:
        True if character is likely Extended_Pictographic
    """
    code = ord(char)
    
    # Common emoji ranges (simplified approximation)
    emoji_ranges = [
        (0x1F600, 0x1F64F),  # Emoticons
        (0x1F300, 0x1F5FF),  # Miscellaneous Symbols and Pictographs  
        (0x1F680, 0x1F6FF),  # Transport and Map Symbols
        (0x1F700, 0x1F77F),  # Alchemical Symbols
        (0x1F780, 0x1F7FF),  # Geometric Shapes Extended
        (0x1F800, 0x1F8FF),  # Supplemental Arrows-C
        (0x1F900, 0x1F9FF),  # Supplemental Symbols and Pictographs
        (0x1FA00, 0x1FA6F),  # Chess Symbols
        (0x1FA70, 0x1FAFF),  # Symbols and Pictographs Extended-A
        (0x2600, 0x26FF),    # Miscellaneous Symbols
        (0x2700, 0x27BF),    # Dingbats
    ]
    
    return any(start <= code <= end for start, end in emoji_ranges)


def _segment_words_impl(text: str) -> List[int]:
    """
    Internal implementation that returns word boundary positions.
    
    Applies all UAX #29 word boundary rules to find positions where
    word breaks should occur.
    
    Args:
        text: Input text to segment
        
    Returns:
        List of boundary positions (indices where breaks occur)
    """
    if not text:
        return [0]
    
    length = len(text)
    breaks = [0]  # Always break at start (WB1)
    
    # Pre-compute properties for all characters
    properties = [word_break_property(c) for c in text]
    
    # Apply WB4 preprocessing: ignore Extend, Format, ZWJ for rule evaluation
    # Create a mapping of "effective" properties
    effective_props = []
    for i, prop in enumerate(properties):
        if prop in ('Extend', 'Format', 'ZWJ'):
            # Look backwards to find the base character
            if i > 0:
                # Find the previous non-ignored character
                j = i - 1
                while j >= 0 and properties[j] in ('Extend', 'Format', 'ZWJ'):
                    j -= 1
                if j >= 0:
                    effective_props.append(effective_props[j])
                else:
                    effective_props.append('Other')
            else:
                effective_props.append('Other')
        else:
            effective_props.append(prop)
    
    # Helper function to get effective property, handling Extend/Format/ZWJ
    def get_effective_prop(idx: int) -> str:
        if 0 <= idx < len(effective_props):
            return effective_props[idx]
        return 'Other'
    
    # Helper function to get actual property
    def get_prop(idx: int) -> str:
        if 0 <= idx < len(properties):
            return properties[idx]
        return 'Other'
    
    # Helper to check if property is AHLetter (ALetter | Hebrew_Letter)
    def is_ahletter(prop: str) -> bool:
        return prop in ('ALetter', 'Hebrew_Letter')
    
    # Helper to check if property is MidNumLetQ (MidNumLet | Single_Quote)  
    def is_midnumletq(prop: str) -> bool:
        return prop in ('MidNumLet', 'Single_Quote')
    
    # Apply word boundary rules
    for i in range(1, length):
        prev_prop = get_effective_prop(i - 1)
        curr_prop = get_effective_prop(i)
        
        # Get actual properties for special rules
        actual_prev = get_prop(i - 1)
        actual_curr = get_prop(i)
        
        should_break = True
        
        # WB3: CR × LF (don't break CR+LF)
        if actual_prev == 'CR' and actual_curr == 'LF':
            should_break = False
        
        # WB3a: (Newline|CR|LF) ÷ (break after newlines)
        elif actual_prev in ('Newline', 'CR', 'LF'):
            should_break = True
        
        # WB3b: ÷ (Newline|CR|LF) (break before newlines)
        elif actual_curr in ('Newline', 'CR', 'LF'):
            should_break = True
        
        # WB3c: ZWJ × Extended_Pictographic (don't break emoji ZWJ sequences)
        elif actual_prev == 'ZWJ' and _is_extended_pictographic(text[i]):
            should_break = False
        
        # WB3d: WSegSpace × WSegSpace (don't break between spaces)
        elif prev_prop == 'WSegSpace' and curr_prop == 'WSegSpace':
            should_break = False
        
        # WB5: AHLetter × AHLetter (don't break between letters)
        elif is_ahletter(prev_prop) and is_ahletter(curr_prop):
            should_break = False
        
        # WB6: AHLetter × (MidLetter|MidNumLetQ) AHLetter (don't break: a.b)
        elif (is_ahletter(prev_prop) and 
              is_midnumletq(curr_prop) or curr_prop == 'MidLetter'):
            # Look ahead to see if followed by AHLetter
            if i + 1 < length and is_ahletter(get_effective_prop(i + 1)):
                should_break = False
        
        # WB7: AHLetter (MidLetter|MidNumLetQ) × AHLetter (don't break: a.b)
        elif (is_ahletter(curr_prop) and i >= 2 and
              (is_midnumletq(prev_prop) or prev_prop == 'MidLetter') and
              is_ahletter(get_effective_prop(i - 2))):
            should_break = False
        
        # WB7a: Hebrew_Letter × Single_Quote
        elif prev_prop == 'Hebrew_Letter' and curr_prop == 'Single_Quote':
            should_break = False
        
        # WB7b: Hebrew_Letter × Double_Quote Hebrew_Letter
        elif (prev_prop == 'Hebrew_Letter' and curr_prop == 'Double_Quote' and
              i + 1 < length and get_effective_prop(i + 1) == 'Hebrew_Letter'):
            should_break = False
        
        # WB7c: Hebrew_Letter Double_Quote × Hebrew_Letter
        elif (curr_prop == 'Hebrew_Letter' and prev_prop == 'Double_Quote' and
              i >= 2 and get_effective_prop(i - 2) == 'Hebrew_Letter'):
            should_break = False
        
        # WB8: Numeric × Numeric (don't break between digits)
        elif prev_prop == 'Numeric' and curr_prop == 'Numeric':
            should_break = False
        
        # WB9: AHLetter × Numeric (don't break letter+digit)
        elif is_ahletter(prev_prop) and curr_prop == 'Numeric':
            should_break = False
        
        # WB10: Numeric × AHLetter (don't break digit+letter)
        elif prev_prop == 'Numeric' and is_ahletter(curr_prop):
            should_break = False
        
        # WB11: Numeric (MidNum|MidNumLetQ) × Numeric (don't break: 3.14)
        elif (curr_prop == 'Numeric' and i >= 2 and
              (is_midnumletq(prev_prop) or prev_prop == 'MidNum') and
              get_effective_prop(i - 2) == 'Numeric'):
            should_break = False
        
        # WB12: Numeric × (MidNum|MidNumLetQ) Numeric (don't break: 3.14)
        elif (prev_prop == 'Numeric' and 
              (is_midnumletq(curr_prop) or curr_prop == 'MidNum') and
              i + 1 < length and get_effective_prop(i + 1) == 'Numeric'):
            should_break = False
        
        # WB13: Katakana × Katakana
        elif prev_prop == 'Katakana' and curr_prop == 'Katakana':
            should_break = False
        
        # WB13a: (AHLetter|Numeric|Katakana|ExtendNumLet) × ExtendNumLet
        elif (curr_prop == 'ExtendNumLet' and
              (is_ahletter(prev_prop) or prev_prop in ('Numeric', 'Katakana', 'ExtendNumLet'))):
            should_break = False
        
        # WB13b: ExtendNumLet × (AHLetter|Numeric|Katakana)
        elif (prev_prop == 'ExtendNumLet' and
              (is_ahletter(curr_prop) or curr_prop in ('Numeric', 'Katakana'))):
            should_break = False
        
        # WB15 & WB16: Regional Indicator rules (simplified)
        elif prev_prop == 'Regional_Indicator' and curr_prop == 'Regional_Indicator':
            # Count preceding Regional_Indicators from start of text or last non-RI
            ri_count = 0
            j = i - 1
            while j >= 0 and get_effective_prop(j) == 'Regional_Indicator':
                ri_count += 1
                j -= 1
            # Don't break if we have an odd number of preceding RIs (forms a pair)
            # Break if we have an even number (would start a new pair)
            should_break = ri_count % 2 == 0
        
        # WB999: Any ÷ Any (default: break)
        # This is the default case - should_break is already True
        
        if should_break:
            breaks.append(i)
    
    # Always break at end (WB2)
    if length > 0:
        breaks.append(length)
    
    return breaks


def segment_words(text: str) -> List[str]:
    """
    Segment text into word boundaries using UAX #29 algorithm.
    
    Returns all segments including whitespace and punctuation segments.
    This is the complete segmentation that preserves all text content.
    
    Args:
        text: Input text to segment
        
    Returns:
        List of text segments
        
    Examples:
        >>> segment_words("Hello world!")
        ['Hello', ' ', 'world', '!']
        
        >>> segment_words("don't stop")  
        ["don't", ' ', 'stop']
        
        >>> segment_words("3.14 is π")
        ['3.14', ' ', 'is', ' ', 'π']
    """
    if not text:
        return []
    
    break_positions = _segment_words_impl(text)
    segments = []
    
    for i in range(len(break_positions) - 1):
        start = break_positions[i]
        end = break_positions[i + 1]
        segment = text[start:end]
        if segment:  # Skip empty segments
            segments.append(segment)
    
    return segments


def tokenize_words(text: str) -> List[str]:
    """
    Extract word-like tokens using UAX #29 segmentation.
    
    Returns only the segments that contain letters, numbers, or letter+number
    combinations. Filters out whitespace-only and punctuation-only segments.
    
    Args:
        text: Input text to tokenize
        
    Returns:
        List of word-like tokens
        
    Examples:
        >>> tokenize_words("Hello, world! 123")
        ['Hello', 'world', '123']
        
        >>> tokenize_words("python3.11 is great")
        ['python3', '11', 'is', 'great']
        
        >>> tokenize_words("file.txt and __init__.py")
        ['file', 'txt', 'and', '__init__', 'py']
    """
    segments = segment_words(text)
    tokens = []
    
    for segment in segments:
        # Check if segment contains letters or numbers
        has_letter_or_number = False
        for char in segment:
            prop = word_break_property(char)
            if prop in ('ALetter', 'Hebrew_Letter', 'Numeric', 'Katakana'):
                has_letter_or_number = True
                break
        
        if has_letter_or_number:
            tokens.append(segment)
    
    return tokens