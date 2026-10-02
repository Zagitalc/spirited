"""Road scoring: how enjoyable each stretch of road is to drive, and how sure we are.

The pure parts (geometry, speed limits, the score components, corridor joining) take
plain data and can be tested without OSM files or a Valhalla server. `build` reads the
filtered extract and writes `scores.sqlite`; `evaluate` ranks the reference roads.
"""
