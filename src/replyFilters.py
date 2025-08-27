def cleanReply(reply):
    # First extract any caps-marked text
    import re
    caps_texts = {}
    counter = 0
    
    def save_caps(match):
        nonlocal counter
        text = match.group(1)
        placeholder = f"__caps_{counter}__"
        caps_texts[placeholder] = text
        counter += 1
        return placeholder
        
    # Save uppercase sections before lowercasing
    reply = re.sub(r'\{\s*caps\s*\}(.*?)\{\s*/caps\s*\}', save_caps, reply)
    
    # Convert to lowercase
    reply = reply.lower().strip()
    
    # Restore uppercase sections
    for placeholder, text in caps_texts.items():
        reply = reply.replace(placeholder, text)
        
    return reply

def stripSelfTag(reply):
  if reply.startswith('compubot: '):
    reply = reply[10:]  # strip out self tags
  return reply

def stripQuotations(reply):
  if reply[0] == '"' and reply[-1] == '"':
    return stripQuotations(reply[1:-1])
  return reply

def replaceEmotes(reply: str) -> str:
    """Replace emote placeholders with actual emotes"""
    import re

    from src.utils.emotes import emotes
    
    def replace_emote(match):
        full_match = match.group(0)
        
        # If this is a Discord emote ID pattern (has numbers after the colon), return as-is
        if full_match.startswith('<') and any(c.isdigit() for c in full_match):
            return full_match
            
        # If this is "Using emote: <emote_id>", extract just the emote
        if full_match.startswith('Using emote:'):
            emote_match = re.search(r'<[^>]+>', full_match)
            return emote_match.group(0) if emote_match else full_match
            
        # Find which group matched (will be the only non-None group after group 0)
        groups = match.groups()
        emote_name = None
        for group in groups:
            if group is not None:
                if ':' in group and not group.startswith('<'):  # Handle ":emotename:" format
                    emote_name = group.strip(':')
                else:  # Handle {use_emote: name} or <use_emote: name> format
                    emote_name = group.strip()
                break
                
        if emote_name:
            emote = emotes.get_emote(emote_name)
            return emote if emote else full_match
        return full_match
    
    # Single pattern that matches all cases
    pattern = (
        r'<a?:[\w]+:\d+>|'                                 # Discord emote ID
        r'Using emote:\s*<[^>]+>|'                        # Function response
        r'\{\s*use[_\s]?emote\s*:\s*([^}\s]+)\s*\}|'     # {use_emote: name}
        r'<\s*use[_\s]?emote\s*:\s*([^>\s]+)\s*>|'       # <use_emote: name>
        r':([^:\s]+):'                                     # :emotename:
    )
              
    reply = re.sub(pattern, replace_emote, reply, flags=re.IGNORECASE)
    return reply