# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html
import os
import sys

from datetime import datetime

import upstage

sys.path.insert(0, os.path.abspath("../../src"))

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/mast er/usage/configuration.html#project-information

project = "UPSTAGE"
copyright = f"{datetime.now().year}, {upstage.__authors__}"
author = upstage.__authors__
release = upstage.__version__

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.coverage",
    "sphinx.ext.githubpages",
    "myst_parser",
]
templates_path = ["_templates"]
nbsphinx_allow_errors = True
add_module_names = False

autodoc_default_options = {
    "ignore-module-all": True,
}

# ---- MYST options -----------
myst_enable_extensions = ["colon_fence", "substitution"]
myst_heading_anchors = 2
myst_substitutions = {
    "rtd": "[Read the Docs](https://readthedocs.org/)",
    "Actor": "{py:class}`Actor <upstage.actor.Actor>`",
    "State": "{py:class}`~upstage.states.State`",
    "Task": "{py:class}`~upstage.task.Task`",
    "TaskNetwork": "{py:class}`~upstage.task_network.TaskNetwork`",
    "EnvironmentContext": "{py:class}`~upstage.base.EnvironmentContext`",
    "UpstageBase": "{py:class}`~upstage.base.UpstageBase`",
    "NamedEntity": "{py:class}`~upstage.base.NamedUpstageEntity`",
    "LinearChangingState": "{py:class}`~upstage.states.LinearChangingState`",
    "CartesianLocation": "{py:class}`~upstage.data_types.CartesianLocation`",
    "GeodeticLocationChangingState": "{py:class}`~upstage.states.GeodeticLocationChangingState`",
    "ResourceState": "{py:class}`~upstage.states.ResourceState`",
    "SelfMonitoringStore": "{py:class}`~upstage.stores.SelfMonitoringStore`",
    "DecisionTask": "{py:class}`~upstage.task.DecisionTask`",
}


# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

# html_theme = "sphinxdoc"
html_theme = "pydata_sphinx_theme"
html_static_path = ["_static"]
html_logo = "_static/upstage-logo-medium.png"
html_theme_options = {
  "show_nav_level": 2,
  "navbar_center": ["navbar-nav"],
  "logo": {
        "text": "UPSTAGE",
    },
  "show_toc_level": 1,
    "icon_links": [
        {
            "name": "GitHub",
            "url": "https://github.com/JamesArruda/upstage/",
            "icon": "fa-brands fa-square-github",
            "type": "fontawesome",
        },
    ]
}


# html_sidebars = { '**': ["sidebar-nav-bs",] }
