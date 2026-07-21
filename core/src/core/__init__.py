"""Shared DB layer used by backend AND the ml worker glue.

Friend A's pipeline code must NEVER import this package — it depends only on
`contracts`. The worker glue (ml/glue.py, George's) is the only ML-side code
that touches the database.
"""
