"""Conservative numeric typography normalization for evidence checks."""
import re


def numeric_text(text):
    """Recognize grouping and matching spelled-out duplicates, not arbitrary brackets."""
    text = re.sub(r'\b\d{1,3}(?: \d{3})+\b', lambda m: m[0].replace(' ', ''), text)
    labels = {'1': {'один', 'одного', 'одна', 'одной'},
              '2': {'два', 'две', 'двух'}, '3': {'три', 'трех', 'трёх'},
              '5': {'пять', 'пяти'}, '10': {'десять', 'десяти'},
              '15': {'пятнадцать', 'пятнадцати'}, '20': {'двадцать', 'двадцати'},
              '30': {'тридцать', 'тридцати'}, '45': {'сорок пять', 'сорока пяти'},
              '60': {'шестьдесят', 'шестидесяти'},
              '10000': {'десять тысяч', 'десяти тысяч'}}
    def duplicate(m):
        return m[1] if m[2].strip() in labels.get(m[1], set()) else m[0]
    return re.sub(r'(\d+)\s*\(([^()]*)\)', duplicate, text)

