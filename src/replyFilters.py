def cleanReply(reply):
  return reply.lower().strip()

def stripSelfTag(reply):
  if reply.startswith('compubot: '):
    reply = reply[10:]  # strip out self tags
  return reply

def stripQuotations(reply):
  if reply[0] == '"' and reply[-1] == '"':
    return stripQuotations(reply[1:-1])
  return reply