import os as os
import random
import re

_pattern = re.compile('\\{[^}]+\\}')

STRINGS_PATH = './resources/strings'

# String key-value lookup
string_dict = {}
for filename in os.listdir(STRINGS_PATH):
    with open(f'{STRINGS_PATH}/{filename}') as f:
        string_dict[filename[:-len('.txt')]] = [line for line in [line.strip() for line in f] if line and not line.startswith('#')]


# Resolve variables in a line of text with an optional scope and fallback in case of unresolved patterns
def resolve(text, scope=None, scope_prefix='', error_when_unresolved=False):
    last_text = None
    while last_text != text:
        last_text = text
        for key, options in string_dict.items():
            s = f'{{{key}}}'
            while s in text:
                text = text.replace(s, random.choice(options), 1)
        if scope is not None:
            for key, value in scope.items():
                text = text.replace(f'{{{scope_prefix}{key}}}', str(random.choice(value) if isinstance(value, list) else value))
    unresolved = _pattern.findall(text)
    if unresolved and error_when_unresolved:
        raise Exception('Unresolved patterns: ' + ', '.join(unresolved))
    return text


__all__ = ['string_dict', 'resolve']

# Debug string configuration
if __name__ == '__main__':
    for key, options in string_dict.items():
        print(key)
        for option in options:
            print(f'  {option}')
        print()

    print(resolve('{msg_kill}', dict(name='USER', caller_name='CALLER')))
    print(resolve('{msg_kill_admin}', dict(name='ADMIN', caller_name='CALLER')))
