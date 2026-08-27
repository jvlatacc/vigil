# The only place that speaks Bifrost's logging REST API. The admin surface
# (provider credentials + model allow-list) is gone: keys live in the encrypted
# store and AI Gateway routes by URL path. The cost read-side client here is the
# last of it, pending the AI Gateway analytics rework.
