# Logging

UPSTAGE exposes a :mod:`logging` hierarchy rooted at ``upstage_des``.  The
library is silent by default — a ``NullHandler`` is attached on import and
the package logger defaults to ``WARNING``.  Opt in at your application
entry point

```{python}
    import logging

    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    logging.getLogger("upstage_des").setLevel(logging.INFO)
```

Actor events go to ``upstage_des.actor.<actor.name>``.

```{python}
    logging.getLogger("upstage_des.actor").setLevel(logging.INFO)
    # Filter only for actors with certain values in the name
    logging.getLogger("upstage_des.actor").addFilter(
        lambda rec: "Plane" not in rec.name
    )
```

Inside a custom :class:`Task`, call ``actor.write_to_log`` with printf-style
arguments.  Formatting is deferred — when the log level is disabled and
``debug_logging=False`` on the actor, the interpolation never runs, so
``repr``/``str`` cost on your arguments is avoided in hot loops.

```{python}
    def task(self, *, actor):
        actor.log("picked up %s (qty=%d)", item, qty)        # INFO
        actor.log("low fuel: %.1f%%", remaining, level=logging.WARNING)
```

Two independent sinks are driven by every ``write_to_log`` call:

* The per-actor in-memory list (``actor.write_to_log()`` /
  ``actor.get_log()``) — controlled by the ``debug_loging`` flag set at
  actor construction.  Use this for post-run analysis in notebooks.
* Python's ``logging`` — controlled by the standard level hierarchy.
  Use this for structured sinks (files, JSON, stdout during dev).
