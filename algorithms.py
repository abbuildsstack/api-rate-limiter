"""Atomic Redis Lua scripts for rate-limiting algorithms."""

# Scripts return: allowed (0/1), remaining quota, retry-after seconds, reset epoch.
FIXED_WINDOW_SCRIPT = r"""
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
local ttl = redis.call('TTL', KEYS[1])
if ttl < 0 then redis.call('EXPIRE', KEYS[1], ARGV[1]); ttl = tonumber(ARGV[1]) end
local allowed = 0
if count <= tonumber(ARGV[2]) then allowed = 1 end
local remaining = math.max(0, tonumber(ARGV[2]) - count)
return {allowed, remaining, math.max(1, ttl), tonumber(ARGV[3])}
"""

SLIDING_LOG_SCRIPT = r"""
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now - window)
local count = redis.call('ZCARD', KEYS[1])
local allowed = 0
local retry = window
if count < limit then
  redis.call('ZADD', KEYS[1], now, member)
  redis.call('EXPIRE', KEYS[1], window + 1)
  count = count + 1
  allowed = 1
else
  local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
  if oldest[2] then retry = math.max(1, math.ceil((tonumber(oldest[2]) + window - now) / 1000)) end
end
local remaining = math.max(0, limit - count)
return {allowed, remaining, retry, math.floor(now / 1000) + retry}
"""

TOKEN_BUCKET_SCRIPT = r"""
local now = tonumber(ARGV[1])
local capacity = tonumber(ARGV[2])
local refill_rate = tonumber(ARGV[3])
local cost = tonumber(ARGV[4])
local state = redis.call('HMGET', KEYS[1], 'tokens', 'updated')
local tokens = tonumber(state[1]) or capacity
local updated = tonumber(state[2]) or now
tokens = math.min(capacity, tokens + math.max(0, now - updated) * refill_rate)
local allowed = 0
local retry = 0
if tokens >= cost then
  tokens = tokens - cost
  allowed = 1
else
  retry = math.max(1, math.ceil((cost - tokens) / refill_rate))
end
redis.call('HSET', KEYS[1], 'tokens', tokens, 'updated', now)
redis.call('EXPIRE', KEYS[1], math.max(2, math.ceil(capacity / refill_rate) + 1))
local remaining = math.floor(tokens)
return {allowed, remaining, retry, math.floor(now / 1000) + retry}
"""
